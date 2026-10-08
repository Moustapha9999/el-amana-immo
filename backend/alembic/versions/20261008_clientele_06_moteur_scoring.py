"""Moteur de scoring LBC/FT : référentiels versionnés, divergences, évaluations.

Additif. Ne classe personne. Ne s'applique pas à la production ``bea_digital``.
Copie de test / recette uniquement.

Revision ID: 20261008_clientele_06
Revises: 20261008_clientele_05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.clientele_classif_matrice import CRITERES_MAITRE, VERSION_REGLES
from app.data.clientele_classif_referentiel import REFERENTIEL
from app.services.clientele.scoring import slug_cle

revision: str = "20261008_clientele_06"
down_revision: Union[str, None] = "20261008_clientele_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)


def _table(name: str, *cols: sa.Column, **kwargs) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(name):
        op.create_table(name, *cols, **kwargs)


def _widen_source() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("clientele_classifications"):
        return
    cols = {c["name"]: c for c in insp.get_columns("clientele_classifications")}
    if "source" in cols:
        op.execute("ALTER TABLE clientele_classifications ALTER COLUMN source TYPE varchar(32)")
    op.execute("ALTER TABLE clientele_classifications DROP CONSTRAINT IF EXISTS "
               "ck_clientele_classifications_source")
    op.execute("""
        ALTER TABLE clientele_classifications ADD CONSTRAINT ck_clientele_classifications_source
        CHECK (source IN ('MOTEUR','MANUEL','EXCEL','EXCEL_CONFORMITE','MANUEL_SURCHARGE'))
    """)
    if insp.has_table("clientele_classif_historique"):
        op.execute("ALTER TABLE clientele_classif_historique ALTER COLUMN source TYPE varchar(32)")


def upgrade() -> None:
    _widen_source()

    _table(
        "clientele_classif_pays",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("nom_fr", sa.String(160), nullable=False),
        sa.Column("nom_en", sa.String(160), nullable=True),
        sa.Column("nationalite", sa.String(80), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("niveau_matrice", sa.String(12), nullable=True),
        sa.Column("poids_pays_v4", sa.Integer(), nullable=True),
        sa.Column("niveau_pays_v4", sa.String(12), nullable=True),
        sa.Column("poids_nationalite_v4", sa.Integer(), nullable=True),
        sa.Column("label_v4", sa.String(80), nullable=True),
        sa.Column("sources", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("version_regles", sa.String(40), nullable=False),
        sa.UniqueConstraint("code", "version_regles", name="uq_clientele_classif_pays"),
    )
    _table(
        "clientele_classif_secteurs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("libelle", sa.String(255), nullable=False),
        sa.Column("famille", sa.String(120), nullable=True),
        sa.Column("niveau_matrice", sa.String(12), nullable=True),
        sa.Column("poids_v4", sa.Integer(), nullable=True),
        sa.Column("niveau_v4", sa.String(12), nullable=True),
        sa.Column("origine", sa.String(16), nullable=False),
        sa.Column("version_regles", sa.String(40), nullable=False),
        sa.UniqueConstraint("code", "version_regles", "origine", name="uq_clientele_classif_secteurs"),
    )
    _table(
        "clientele_classif_formes",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("libelle", sa.String(160), nullable=False),
        sa.Column("profil", sa.String(40), nullable=True),
        sa.Column("niveau_matrice", sa.String(12), nullable=True),
        sa.Column("poids_v4", sa.Integer(), nullable=True),
        sa.Column("niveau_v4", sa.String(12), nullable=True),
        sa.Column("origine", sa.String(16), nullable=False),
        sa.Column("version_regles", sa.String(40), nullable=False),
        sa.UniqueConstraint("code", "version_regles", "origine", name="uq_clientele_classif_formes"),
    )
    _table(
        "clientele_classif_divergences",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("domaine", sa.String(40), nullable=False),
        sa.Column("cle", sa.String(255), nullable=False),
        sa.Column("source_a", sa.String(40), nullable=False),
        sa.Column("valeur_a", sa.Text(), nullable=False),
        sa.Column("source_b", sa.String(40), nullable=False),
        sa.Column("valeur_b", sa.Text(), nullable=False),
        sa.Column("statut", sa.String(24), nullable=False, server_default="A_ARBITRER"),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("version_regles", sa.String(40), nullable=False),
        sa.Column("validee_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validee_le", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "statut IN ('A_ARBITRER','VALIDEE','INVALIDE_SOURCE','ALIGNEE')",
            name="ck_clientele_classif_div_statut"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_clientele_classif_div_domaine "
               "ON clientele_classif_divergences (domaine, statut)")

    _table(
        "clientele_classif_evaluations",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("racine_client", sa.String(6),
                  sa.ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT",
                                onupdate="RESTRICT"), nullable=False),
        sa.Column("version_moteur", sa.String(40), nullable=False),
        sa.Column("version_regles", sa.String(40), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="SCORE"),
        sa.Column("score_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_evalues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("niveau_score", sa.String(12), nullable=True),
        sa.Column("niveau_score_v4", sa.String(12), nullable=True),
        sa.Column("niveau_max", sa.String(12), nullable=True),
        sa.Column("niveau_final", sa.String(12), nullable=True),
        sa.Column("statut", sa.String(24), nullable=False),
        sa.Column("coherence", sa.String(24), nullable=False),
        sa.Column("motif_principal", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mode IN ('SCORE','MAX_NIVEAU')", name="ck_clientele_classif_eval_mode"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_clientele_classif_eval_racine "
               "ON clientele_classif_evaluations (racine_client, created_at)")

    _table(
        "clientele_classif_evaluation_lignes",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("evaluation_id", _UUID,
                  sa.ForeignKey("clientele_classif_evaluations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("critere", sa.String(40), nullable=False),
        sa.Column("libelle", sa.String(160), nullable=False),
        sa.Column("etat", sa.String(24), nullable=False),
        sa.Column("valeur", sa.Text(), nullable=True),
        sa.Column("source_donnee", sa.String(40), nullable=True),
        sa.Column("poids", sa.Integer(), nullable=True),
        sa.Column("niveau_matrice", sa.String(12), nullable=True),
        sa.Column("niveau_v4", sa.String(12), nullable=True),
        sa.Column("niveau_retenu", sa.String(12), nullable=True),
        sa.Column("type_decision", sa.String(16), nullable=False, server_default="SCORE"),
        sa.Column("motif", sa.Text(), nullable=False),
        sa.Column("divergence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("blocking_propose", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("statut_regle", sa.String(24), nullable=False, server_default="A_ARBITRER"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_clientele_classif_eval_lignes_eval "
               "ON clientele_classif_evaluation_lignes (evaluation_id)")

    _seed()


def _seed() -> None:
    bind = op.get_bind()
    vr = VERSION_REGLES
    import json

    for c in CRITERES_MAITRE:
        if c["code"] in ("RACINE_CLIENT",):
            continue
        bind.execute(sa.text("""
            INSERT INTO clientele_classif_criteres (id, code, libelle, description, champ_defaut, actif)
            VALUES (gen_random_uuid(), :code, :libelle, :description, :champ, true)
            ON CONFLICT (code) DO UPDATE SET
                libelle = EXCLUDED.libelle,
                description = EXCLUDED.description
        """), {
            "code": c["code"][:40],
            "libelle": c["libelle"][:120],
            "description": (
                f"[{c['statut']}] source={c['source']} dispo={c['disponible']} "
                f"decision={c['type_decision']}. {c['note']}"
            )[:2000],
            "champ": (c.get("champ") or None),
        })

    deja = bind.execute(sa.text(
        "SELECT 1 FROM clientele_classif_pays WHERE version_regles = :v LIMIT 1"
    ), {"v": vr}).scalar()
    if not deja:
        for p in REFERENTIEL.get("pays") or []:
            bind.execute(sa.text("""
                INSERT INTO clientele_classif_pays
                    (id, code, nom_fr, nom_en, nationalite, aliases, niveau_matrice,
                     poids_pays_v4, niveau_pays_v4, poids_nationalite_v4, label_v4,
                     sources, version_regles)
                VALUES (gen_random_uuid(), :code, :nom_fr, :nom_en, :nationalite,
                        CAST(:aliases AS jsonb), :niveau_matrice, :poids_pays_v4,
                        :niveau_pays_v4, :poids_nationalite_v4, :label_v4,
                        CAST(:sources AS jsonb), :vr)
            """), {
                "code": (p.get("code") or slug_cle(p.get("nom_fr")))[:48],
                "nom_fr": (p.get("nom_fr") or "")[:160],
                "nom_en": (p.get("nom_en") or None),
                "nationalite": (p.get("nationalite") or None),
                "aliases": json.dumps(p.get("aliases") or [], ensure_ascii=False),
                "niveau_matrice": p.get("niveau_matrice"),
                "poids_pays_v4": p.get("poids_pays_v4"),
                "niveau_pays_v4": p.get("niveau_pays_v4"),
                "poids_nationalite_v4": p.get("poids_nationalite_v4"),
                "label_v4": (p.get("label_v4") or None),
                "sources": json.dumps(p.get("sources") or [], ensure_ascii=False),
                "vr": vr,
            })

        for it in (REFERENTIEL.get("matrice_client") or {}).get("Sous secteur d'activité") or []:
            lib = (it.get("libelle") or "").strip()
            if not lib:
                continue
            bind.execute(sa.text("""
                INSERT INTO clientele_classif_secteurs
                    (id, code, libelle, famille, niveau_matrice, poids_v4, niveau_v4, origine, version_regles)
                VALUES (gen_random_uuid(), :code, :libelle, NULL, :nm, NULL, NULL, 'MATRICE_V1', :vr)
                ON CONFLICT DO NOTHING
            """), {"code": slug_cle(lib)[:80], "libelle": lib[:255],
                   "nm": it.get("niveau_matrice"), "vr": vr})
        for it in (REFERENTIEL.get("listes_v4") or {}).get("secteur") or []:
            lib = (it.get("libelle") or "").strip()
            if not lib:
                continue
            bind.execute(sa.text("""
                INSERT INTO clientele_classif_secteurs
                    (id, code, libelle, famille, niveau_matrice, poids_v4, niveau_v4, origine, version_regles)
                VALUES (gen_random_uuid(), :code, :libelle, NULL, NULL, :p, :nv, 'SCORING_V4', :vr)
                ON CONFLICT DO NOTHING
            """), {"code": slug_cle(lib)[:80], "libelle": lib[:255],
                   "p": it.get("poids_v4"), "nv": it.get("niveau_v4"), "vr": vr})

        formes_v4 = (
            ("personne_physique", "Personne_Physique"),
            ("personne_morale_publique", "Personne_Morale_Publique"),
            ("personne_morale_privee", "Personne_Morale_Privee"),
            ("personne_morale_association", "Personne_Morale_Association"),
        )
        for bloc, profil in formes_v4:
            for it in (REFERENTIEL.get("listes_v4") or {}).get(bloc) or []:
                lib = (it.get("libelle") or "").strip()
                if not lib:
                    continue
                bind.execute(sa.text("""
                    INSERT INTO clientele_classif_formes
                        (id, code, libelle, profil, niveau_matrice, poids_v4, niveau_v4, origine, version_regles)
                    VALUES (gen_random_uuid(), :code, :libelle, :profil, NULL, :p, :nv, 'SCORING_V4', :vr)
                    ON CONFLICT DO NOTHING
                """), {"code": slug_cle(lib)[:80], "libelle": lib[:160], "profil": profil,
                       "p": it.get("poids_v4"), "nv": it.get("niveau_v4"), "vr": vr})
        for dim in ("Personne_Physique", "Personne_Morale_Publique",
                    "Personne_Morale_Privée", "Personne_Morale_Association"):
            for it in (REFERENTIEL.get("matrice_client") or {}).get(dim) or []:
                lib = (it.get("libelle") or "").strip()
                if not lib:
                    continue
                bind.execute(sa.text("""
                    INSERT INTO clientele_classif_formes
                        (id, code, libelle, profil, niveau_matrice, poids_v4, niveau_v4, origine, version_regles)
                    VALUES (gen_random_uuid(), :code, :libelle, :profil, :nm, NULL, NULL, 'MATRICE_V1', :vr)
                    ON CONFLICT DO NOTHING
                """), {"code": slug_cle(lib)[:80], "libelle": lib[:160], "profil": dim[:40],
                       "nm": it.get("niveau_matrice"), "vr": vr})

        for d in REFERENTIEL.get("divergences") or []:
            bind.execute(sa.text("""
                INSERT INTO clientele_classif_divergences
                    (id, domaine, cle, source_a, valeur_a, source_b, valeur_b, statut, note, version_regles)
                VALUES (gen_random_uuid(), :domaine, :cle, :sa, :va, :sb, :vb, :statut, :note, :vr)
            """), {
                "domaine": (d.get("domaine") or "AUTRE")[:40],
                "cle": (d.get("cle") or "")[:255],
                "sa": (d.get("source_a") or "")[:40],
                "va": str(d.get("valeur_a") or ""),
                "sb": (d.get("source_b") or "")[:40],
                "vb": str(d.get("valeur_b") or ""),
                "statut": d.get("statut") if d.get("statut") in (
                    "A_ARBITRER", "VALIDEE", "INVALIDE_SOURCE", "ALIGNEE") else "A_ARBITRER",
                "note": d.get("note"),
                "vr": vr,
            })

    bind.execute(sa.text("""
        INSERT INTO clientele_classif_versions
            (id, numero, libelle, mode, seuils, date_effet, statut)
        SELECT gen_random_uuid(), COALESCE((SELECT max(numero) FROM clientele_classif_versions), 0) + 1,
               :libelle, 'SCORE', CAST(:seuils AS jsonb), CURRENT_DATE, 'BROUILLON'
        WHERE NOT EXISTS (
            SELECT 1 FROM clientele_classif_versions WHERE libelle = :libelle)
    """), {
        "libelle": VERSION_REGLES,
        "seuils": '{"ELEVE": 100000, "MOYEN": 10000, "source": "PROPOSITION_BEA_DIGITAL", "statut": "A_ARBITRER"}',
    })


def downgrade() -> None:
    for table in (
        "clientele_classif_evaluation_lignes",
        "clientele_classif_evaluations",
        "clientele_classif_divergences",
        "clientele_classif_formes",
        "clientele_classif_secteurs",
        "clientele_classif_pays",
    ):
        op.drop_table(table)
