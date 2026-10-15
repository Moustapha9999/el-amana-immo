"""Organigramme : compléments provisoires (ajouts suggérés 🟡) en attendant l'organigramme réel.

Ajoute aux entités officielles de juillet 2024 les services usuels d'une banque (achats, archives,
back-office, fiscalité, LCB-FT, réseau d'agences…), tous ``a_confirmer`` et ``source =
SUGGESTION_2026_10`` : ils restent distincts de l'officiel et se valident ou se désactivent dans
CORE ADMIN → Organigramme. Aucune entité existante n'est modifiée ; une entité déjà présente
(même code, ou même libellé sous le même parent) n'est pas recréée.

Revision ID: 20261015_org_02
Revises: 20261015_mg_stock_entrees
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.data.organigramme_bea_suggestions import SOURCE, aplatir_suggestions

# Anciennes saisies texte encore non rattachées : rattachement exact uniquement (comme org_01).
TABLES_TEXTE = (
    ("mg_stock_mouvements", "departement", "TRUE"),
    ("mg_demandes_fourniture", "departement", "TRUE"),
    ("mg_bons_commande", "departement", "TRUE"),
    ("mg_bc_lignes", "departement", "TRUE"),
    ("mg_notes_frais", "departement", "TRUE"),
    ("reclamation_unites", "libelle", "type_unite <> 'AGENCE'"),
    ("formation_entites", "libelle", "agence_id IS NULL"),
)

revision: str = "20261015_org_02"
down_revision: Union[str, None] = "20261015_mg_stock_entrees"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RATTACHER_TEXTE_V2 = """
    CREATE OR REPLACE FUNCTION org_rattacher_texte() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE e uuid;
    BEGIN
      -- Texte modifié sans changement explicite de l'entité : le rattachement suit le nouveau texte.
      IF TG_OP = 'UPDATE'
         AND NEW.org_entite_id IS NOT DISTINCT FROM OLD.org_entite_id
         AND org_cle(to_jsonb(NEW) ->> TG_ARGV[0]) IS DISTINCT FROM org_cle(to_jsonb(OLD) ->> TG_ARGV[0]) THEN
        NEW.org_entite_id := NULL;
      END IF;
      IF NEW.org_entite_id IS NOT NULL THEN RETURN NEW; END IF;
      e := org_entite_par_texte(to_jsonb(NEW) ->> TG_ARGV[0]);
      IF e IS NOT NULL THEN NEW.org_entite_id := e; END IF;
      RETURN NEW;
    END $$;
"""
RATTACHER_TEXTE_V1 = """
    CREATE OR REPLACE FUNCTION org_rattacher_texte() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE e uuid;
    BEGIN
      IF NEW.org_entite_id IS NOT NULL THEN RETURN NEW; END IF;
      e := org_entite_par_texte(to_jsonb(NEW) ->> TG_ARGV[0]);
      IF e IS NOT NULL THEN NEW.org_entite_id := e; END IF;
      RETURN NEW;
    END $$;
"""


def upgrade() -> None:
    op.execute(RATTACHER_TEXTE_V2)
    bind = op.get_bind()
    for n in aplatir_suggestions():
        bind.execute(sa.text("""
            INSERT INTO departements (id, code, libelle, type_entite, parent_id, ordre, a_confirmer,
                                      note_confirmation, source, metadonnees, is_active)
            SELECT gen_random_uuid(), :code, :libelle, :type, p.id,
                   (SELECT coalesce(max(s.ordre), 0) + 1 FROM departements s WHERE s.parent_id = p.id),
                   true, :note, :source, CAST(:meta AS jsonb), true
            FROM departements p
            WHERE p.code = :parent AND p.deleted_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM departements WHERE upper(code) = upper(:code))
              AND NOT EXISTS (SELECT 1 FROM departements d WHERE d.parent_id = p.id
                              AND d.deleted_at IS NULL AND d.cle = org_cle(:libelle))
        """), {
            "code": n["code"], "libelle": n["libelle"], "type": n["type_entite"], "parent": n["parent_code"],
            "note": n["note"], "source": SOURCE, "meta": json.dumps({"statut_validation": "suggere"}),
        })
        for ordre, p in enumerate(n["postes"], start=1):
            bind.execute(sa.text("""
                INSERT INTO org_postes (id, entite_id, intitule, est_responsable, a_confirmer,
                                        note_confirmation, ordre, source)
                SELECT gen_random_uuid(), e.id, :intitule, :resp, true, :note, :ordre, :source
                FROM departements e WHERE e.code = :code AND e.source = :source
                  AND NOT EXISTS (SELECT 1 FROM org_postes op WHERE op.entite_id = e.id AND op.cle = org_cle(:intitule))
            """), {
                "intitule": p["intitule"], "resp": p["est_responsable"], "note": p["note"], "ordre": ordre,
                "source": SOURCE, "code": n["code"],
            })
    for table, col, filtre in TABLES_TEXTE:
        op.execute(f"""
            UPDATE {table} SET org_entite_id = org_entite_par_texte({col})
            WHERE org_entite_id IS NULL AND {col} IS NOT NULL AND {filtre}
              AND org_entite_par_texte({col}) IS NOT NULL
        """)


def downgrade() -> None:
    op.execute(RATTACHER_TEXTE_V1)
    # Retire uniquement les suggestions que rien ne référence (dossiers, affectations, agences,
    # sous-entités ajoutées) : les clés étrangères sans cascade font échouer la suppression des autres.
    op.execute(f"""
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN SELECT id FROM departements WHERE source = '{SOURCE}' ORDER BY length(code) DESC LOOP
            BEGIN
              DELETE FROM org_postes WHERE entite_id = r.id AND source = '{SOURCE}';
              DELETE FROM departements WHERE id = r.id;
            EXCEPTION WHEN foreign_key_violation THEN NULL;
            END;
          END LOOP;
        END $$;
    """)
