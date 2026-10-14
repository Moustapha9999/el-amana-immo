"""Référentiel organisationnel central BEA DIGITAL (organigramme juillet 2024).

Pas de nouvelle table d'entités : ``departements`` (vide jusqu'ici, déjà référencée par
immobilisations, achats, demandes, GED et centres de coût) devient l'arborescence commune à tous
les niveaux (conseil, comités, direction générale, directions, départements, services, sections).
Les clés étrangères existantes pointent ainsi vers l'entité centrale sans migration de données.

Tables ajoutées (aucune structure existante ne les couvre) :
- ``org_postes``       : postes / fonctions d'une entité (≠ personne, ≠ rôle applicatif) ;
- ``org_affectations`` : rattachement historisé compte utilisateur → entité + périmètre de données.
  ``user_espace_acces`` (départements plateforme) et ``reclamation_unite_membres`` (propre au module)
  ne décrivent pas l'appartenance organisationnelle.

Raccordement des modules (colonne ``org_entite_id``, ancienne valeur texte conservée intacte) :
mouvements de stock, demandes de fournitures, bons de commande (+ lignes), notes de frais,
unités Réclamations, entités Formation, agences (rattachement hiérarchique). Seules les
correspondances **exactes** (libellé normalisé ou alias validé) sont appliquées ; le reste est
listé dans CORE ADMIN → Organigramme → Correspondances, jamais deviné.

Revision ID: 20261015_org_01
Revises: 20261014_reclamations_07
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.organigramme_bea_2024 import RATTACHEMENTS_AGENCES, SOURCE, aplatir

revision: str = "20261015_org_01"
down_revision: Union[str, None] = "20261014_reclamations_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TYPES_ENTITE = ("CONSEIL", "COMITE", "DIRECTION_GENERALE", "DIRECTION", "DEPARTEMENT", "SERVICE", "SECTION", "CELLULE")

# (table, colonne texte, filtre des lignes concernées) — rattachées par libellé exact.
TABLES_TEXTE = (
    ("mg_stock_mouvements", "departement"),
    ("mg_demandes_fourniture", "departement"),
    ("mg_bons_commande", "departement"),
    ("mg_bc_lignes", "departement"),
    ("mg_notes_frais", "departement"),
)
TABLES_REFERENTIEL = (
    ("reclamation_unites", "libelle", "type_unite <> 'AGENCE'"),
    ("formation_entites", "libelle", "agence_id IS NULL"),
)

PERMISSIONS = (
    ("core.admin.organisation", "Administration de l'organigramme et des affectations (CORE ADMIN)", "core"),
    ("org.scope.all", "Périmètre organisationnel global (toutes entités)", "organisation"),
)

_ACCENTS_DE = "ÀÁÂÃÄÅàáâãäåÇçÈÉÊËèéêëÌÍÎÏìíîïÑñÒÓÔÕÖòóôõöÙÚÛÜùúûüÝýÿ"
_ACCENTS_EN = "AAAAAAaaaaaaCcEEEEeeeeIIIIiiiiNnOOOOOoooooUUUUuuuuYyy"
assert len(_ACCENTS_DE) == len(_ACCENTS_EN)


def _types_sql() -> str:
    return ",".join(f"'{t}'" for t in TYPES_ENTITE)


def upgrade() -> None:
    # ------------------------------------------------------------------ fonctions
    op.execute(f"""
        CREATE OR REPLACE FUNCTION org_cle(t text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
          SELECT NULLIF(btrim(regexp_replace(
            lower(translate(coalesce(t, ''), '{_ACCENTS_DE}', '{_ACCENTS_EN}')),
            '[^a-z0-9]+', ' ', 'g')), '')
        $$;
    """)

    # --------------------------------------------------- departements → entités
    op.add_column("departements", sa.Column("type_entite", sa.String(30), nullable=False,
                                            server_default="DEPARTEMENT"))
    op.add_column("departements", sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("departements", sa.Column("cle", sa.String(255), nullable=False, server_default=""))
    op.add_column("departements", sa.Column("sigle", sa.String(40), nullable=True))
    op.add_column("departements", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("departements", sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("departements", sa.Column("alias", postgresql.ARRAY(sa.String(255)), nullable=False,
                                            server_default="{}"))
    op.add_column("departements", sa.Column("a_confirmer", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("departements", sa.Column("note_confirmation", sa.Text(), nullable=True))
    op.add_column("departements", sa.Column("source", sa.String(40), nullable=False, server_default="MANUEL"))
    op.add_column("departements", sa.Column("metadonnees", postgresql.JSONB(), nullable=False,
                                            server_default=sa.text("'{}'::jsonb")))
    op.add_column("departements", sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("departements", sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("ALTER TABLE departements ALTER COLUMN is_active SET DEFAULT true")
    op.create_foreign_key("fk_departements_parent", "departements", "departements", ["parent_id"], ["id"],
                          ondelete="RESTRICT")
    op.create_foreign_key("fk_departements_created_by", "departements", "users", ["created_by_id"], ["id"],
                          ondelete="SET NULL")
    op.create_foreign_key("fk_departements_updated_by", "departements", "users", ["updated_by_id"], ["id"],
                          ondelete="SET NULL")
    op.create_check_constraint("ck_departements_type_entite", "departements", f"type_entite IN ({_types_sql()})")
    op.create_check_constraint("ck_departements_parent_soi", "departements", "parent_id IS NULL OR parent_id <> id")
    op.create_index("ix_departements_parent_id", "departements", ["parent_id"])
    op.create_index("ix_departements_type_entite", "departements", ["type_entite"])

    # Clé normalisée et alias toujours calculés par la base (aucune divergence possible côté code).
    op.execute("""
        CREATE OR REPLACE FUNCTION org_entite_normaliser() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          NEW.cle := coalesce(org_cle(NEW.libelle), '');
          NEW.alias := coalesce(ARRAY(
            SELECT DISTINCT org_cle(a) FROM unnest(NEW.alias) a WHERE org_cle(a) IS NOT NULL ORDER BY 1
          ), '{}');
          RETURN NEW;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_departements_normaliser BEFORE INSERT OR UPDATE OF libelle, alias ON departements
        FOR EACH ROW EXECUTE FUNCTION org_entite_normaliser();
    """)
    # Anti-cycle : un parent ne peut pas être l'entité elle-même ni l'une de ses descendantes.
    op.execute("""
        CREATE OR REPLACE FUNCTION org_entite_sans_cycle() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.parent_id IS NULL THEN RETURN NEW; END IF;
          IF EXISTS (
            WITH RECURSIVE ancetres(id, parent_id, profondeur) AS (
              SELECT d.id, d.parent_id, 1 FROM departements d WHERE d.id = NEW.parent_id
              UNION ALL
              SELECT d.id, d.parent_id, a.profondeur + 1 FROM departements d
              JOIN ancetres a ON d.id = a.parent_id WHERE a.profondeur < 64
            ) SELECT 1 FROM ancetres WHERE id = NEW.id
          ) THEN
            RAISE EXCEPTION 'Rattachement circulaire interdit dans l''organigramme'
              USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_departements_sans_cycle';
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_departements_sans_cycle BEFORE INSERT OR UPDATE OF parent_id ON departements
        FOR EACH ROW EXECUTE FUNCTION org_entite_sans_cycle();
    """)
    op.execute("UPDATE departements SET libelle = libelle")
    op.execute("""
        CREATE UNIQUE INDEX uq_departements_parent_cle ON departements
        (COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), cle) WHERE deleted_at IS NULL
    """)

    # -------------------------------------------------------------------- postes
    op.create_table(
        "org_postes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entite_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("departements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("intitule", sa.String(200), nullable=False),
        sa.Column("cle", sa.String(200), nullable=False, server_default=""),
        sa.Column("est_responsable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("effectif_prevu", sa.Integer(), nullable=True),
        sa.Column("titulaire_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("a_confirmer", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("note_confirmation", sa.Text(), nullable=True),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(40), nullable=False, server_default="MANUEL"),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("effectif_prevu IS NULL OR effectif_prevu > 0", name="ck_org_postes_effectif"),
    )
    op.create_index("ix_org_postes_entite_id", "org_postes", ["entite_id"])
    op.create_index("ix_org_postes_titulaire_user_id", "org_postes", ["titulaire_user_id"])
    op.execute("""
        CREATE OR REPLACE FUNCTION org_poste_normaliser() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN NEW.cle := coalesce(org_cle(NEW.intitule), ''); RETURN NEW; END $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_org_postes_normaliser BEFORE INSERT OR UPDATE OF intitule ON org_postes
        FOR EACH ROW EXECUTE FUNCTION org_poste_normaliser();
    """)

    # --------------------------------------------------------------- affectations
    op.create_table(
        "org_affectations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("entite_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("departements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("poste_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("org_postes.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("type_affectation", sa.String(20), nullable=False, server_default="PRINCIPALE"),
        sa.Column("perimetre", sa.String(30), nullable=False, server_default="PERSONNEL"),
        sa.Column("date_debut", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("date_fin", sa.Date(), nullable=True),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("type_affectation IN ('PRINCIPALE','SECONDAIRE','INTERIM')",
                           name="ck_org_affectations_type"),
        sa.CheckConstraint("perimetre IN ('PERSONNEL','ENTITE','ENTITE_ET_SOUS_ENTITES')",
                           name="ck_org_affectations_perimetre"),
        sa.CheckConstraint("date_fin IS NULL OR date_fin >= date_debut", name="ck_org_affectations_dates"),
    )
    op.create_index("ix_org_affectations_user_id", "org_affectations", ["user_id"])
    op.create_index("ix_org_affectations_entite_id", "org_affectations", ["entite_id"])
    op.create_index("ix_org_affectations_actif", "org_affectations", ["actif"])
    op.create_index("uq_org_affectations_principale", "org_affectations", ["user_id"], unique=True,
                    postgresql_where=sa.text("actif AND type_affectation = 'PRINCIPALE'"))

    # ------------------------------------------------- raccordement des modules
    op.add_column("agences", sa.Column("org_entite_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_agences_org_entite", "agences", "departements", ["org_entite_id"], ["id"],
                          ondelete="SET NULL")
    op.create_index("ix_agences_org_entite_id", "agences", ["org_entite_id"])
    for table, _col in TABLES_TEXTE:
        _ajouter_lien(table)
    for table, _col, _filtre in TABLES_REFERENTIEL:
        _ajouter_lien(table)

    # Entité unique désignée par un texte (libellé ou alias normalisé) ; NULL si absente ou ambiguë.
    op.execute("""
        CREATE OR REPLACE FUNCTION org_entite_par_texte(t text) RETURNS uuid LANGUAGE sql STABLE AS $$
          SELECT CASE WHEN count(*) = 1 THEN (array_agg(id))[1] END
          FROM departements
          WHERE deleted_at IS NULL AND is_active AND org_cle(t) IS NOT NULL
            AND (cle = org_cle(t) OR org_cle(t) = ANY(alias))
        $$;
    """)
    # Nouvelle saisie texte → entité rattachée automatiquement si (et seulement si) la correspondance est exacte.
    op.execute("""
        CREATE OR REPLACE FUNCTION org_rattacher_texte() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE e uuid;
        BEGIN
          IF NEW.org_entite_id IS NOT NULL THEN RETURN NEW; END IF;
          e := org_entite_par_texte(to_jsonb(NEW) ->> TG_ARGV[0]);
          IF e IS NOT NULL THEN NEW.org_entite_id := e; END IF;
          RETURN NEW;
        END $$;
    """)
    for table, col in TABLES_TEXTE:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_org BEFORE INSERT OR UPDATE OF {col} ON {table}
            FOR EACH ROW EXECUTE FUNCTION org_rattacher_texte('{col}');
        """)

    # ----------------------------------------------------- organigramme 2024
    bind = op.get_bind()
    legacy_dg = bind.execute(sa.text(
        "SELECT id::text FROM directions WHERE deleted_at IS NULL AND org_cle(libelle) = 'direction generale' LIMIT 1"
    )).scalar()
    for n in aplatir():
        meta = {"profondeur_import": n["profondeur"]}
        if n["code"] == "DG" and legacy_dg:
            meta["legacy_direction_id"] = legacy_dg
        bind.execute(sa.text("""
            INSERT INTO departements (id, code, libelle, type_entite, parent_id, ordre, a_confirmer,
                                      note_confirmation, source, metadonnees, is_active)
            SELECT gen_random_uuid(), :code, :libelle, :type, p.id, :ordre, :a_conf, :note, :source,
                   CAST(:meta AS jsonb), true
            FROM (SELECT 1) x LEFT JOIN departements p ON p.code = :parent
            WHERE NOT EXISTS (SELECT 1 FROM departements WHERE code = :code)
        """), {
            "code": n["code"], "libelle": n["libelle"], "type": n["type_entite"], "parent": n["parent_code"],
            "ordre": n["ordre"], "a_conf": n["a_confirmer"], "note": n["note"], "source": SOURCE,
            "meta": json.dumps(meta),
        })
        for ordre, p in enumerate(n["postes"], start=1):
            bind.execute(sa.text("""
                INSERT INTO org_postes (id, entite_id, intitule, est_responsable, a_confirmer,
                                        note_confirmation, ordre, source)
                SELECT gen_random_uuid(), e.id, :intitule, :resp, :a_conf, :note, :ordre, :source
                FROM departements e WHERE e.code = :code
                  AND NOT EXISTS (SELECT 1 FROM org_postes op WHERE op.entite_id = e.id AND op.cle = org_cle(:intitule))
            """), {
                "intitule": p["intitule"], "resp": p["est_responsable"], "a_conf": p["a_confirmer"],
                "note": p["note"], "ordre": ordre, "source": SOURCE, "code": n["code"],
            })
    for code_agence, code_entite in RATTACHEMENTS_AGENCES.items():
        bind.execute(sa.text("""
            UPDATE agences a SET org_entite_id = e.id FROM departements e
            WHERE a.code = :agence AND e.code = :entite AND a.org_entite_id IS NULL
        """), {"agence": code_agence, "entite": code_entite})

    # -------------------------------- correspondances exactes des données existantes
    for table, col in TABLES_TEXTE:
        op.execute(f"""
            UPDATE {table} SET org_entite_id = org_entite_par_texte({col})
            WHERE org_entite_id IS NULL AND {col} IS NOT NULL AND org_entite_par_texte({col}) IS NOT NULL
        """)
    for table, col, filtre in TABLES_REFERENTIEL:
        op.execute(f"""
            UPDATE {table} SET org_entite_id = org_entite_par_texte({col})
            WHERE org_entite_id IS NULL AND {filtre} AND org_entite_par_texte({col}) IS NOT NULL
        """)

    # ---------------------------------------------------------------- permissions
    for code, libelle, module in PERMISSIONS:
        bind.execute(sa.text(
            "INSERT INTO permissions (id, code, label, module) SELECT gen_random_uuid(), :c, :l, :m "
            "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)"), {"c": code, "l": libelle, "m": module})


def _ajouter_lien(table: str) -> None:
    op.add_column(table, sa.Column("org_entite_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(f"fk_{table}_org_entite", table, "departements", ["org_entite_id"], ["id"],
                          ondelete="RESTRICT")
    op.create_index(f"ix_{table}_org_entite_id", table, ["org_entite_id"])


def downgrade() -> None:
    for code, _l, _m in PERMISSIONS:
        op.execute(sa.text("DELETE FROM permissions WHERE code = :c").bindparams(c=code))
    for table, _col in TABLES_TEXTE:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_org ON {table}")
    op.execute("DROP FUNCTION IF EXISTS org_rattacher_texte()")
    op.execute("DROP FUNCTION IF EXISTS org_entite_par_texte(text)")
    for table in [t for t, _c in TABLES_TEXTE] + [t for t, _c, _f in TABLES_REFERENTIEL] + ["agences"]:
        op.drop_index(f"ix_{table}_org_entite_id", table_name=table)
        op.drop_constraint(f"fk_{table}_org_entite", table, type_="foreignkey")
        op.drop_column(table, "org_entite_id")
    op.drop_table("org_affectations")
    op.drop_table("org_postes")
    op.execute("DROP FUNCTION IF EXISTS org_poste_normaliser()")
    op.execute("DROP TRIGGER IF EXISTS trg_departements_sans_cycle ON departements")
    op.execute("DROP TRIGGER IF EXISTS trg_departements_normaliser ON departements")
    op.execute("DROP INDEX IF EXISTS uq_departements_parent_cle")
    # Entités importées : retirées seulement si rien d'autre ne les référence (FK sans cascade).
    op.execute(f"UPDATE departements SET parent_id = NULL WHERE source = '{SOURCE}'")
    op.execute(f"""
        DELETE FROM departements d WHERE d.source = '{SOURCE}'
          AND NOT EXISTS (SELECT 1 FROM immobilisations WHERE departement_id = d.id)
          AND NOT EXISTS (SELECT 1 FROM mg_achat_demandes WHERE departement_id = d.id)
          AND NOT EXISTS (SELECT 1 FROM mg_employee_requests WHERE department_id = d.id)
          AND NOT EXISTS (SELECT 1 FROM mg_procurement_batches WHERE department_id = d.id)
          AND NOT EXISTS (SELECT 1 FROM ged_documents WHERE department_id = d.id)
          AND NOT EXISTS (SELECT 1 FROM centres_cout WHERE departement_id = d.id)
    """)
    op.execute("DROP FUNCTION IF EXISTS org_entite_sans_cycle()")
    op.execute("DROP FUNCTION IF EXISTS org_entite_normaliser()")
    op.drop_index("ix_departements_type_entite", table_name="departements")
    op.drop_index("ix_departements_parent_id", table_name="departements")
    op.drop_constraint("ck_departements_parent_soi", "departements", type_="check")
    op.drop_constraint("ck_departements_type_entite", "departements", type_="check")
    op.drop_constraint("fk_departements_updated_by", "departements", type_="foreignkey")
    op.drop_constraint("fk_departements_created_by", "departements", type_="foreignkey")
    op.drop_constraint("fk_departements_parent", "departements", type_="foreignkey")
    for col in ("updated_by_id", "created_by_id", "metadonnees", "source", "note_confirmation", "a_confirmer",
                "alias", "ordre", "description", "sigle", "cle", "parent_id", "type_entite"):
        op.drop_column("departements", col)
    op.execute("DROP FUNCTION IF EXISTS org_cle(text)")
