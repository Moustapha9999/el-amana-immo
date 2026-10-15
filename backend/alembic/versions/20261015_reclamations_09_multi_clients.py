"""Réclamations : dossier multi-clients / multi-comptes, import Excel, nomenclature métier.

- ``reclamation_participants`` (clients du dossier, un seul PRINCIPAL), ``reclamation_comptes``
  (comptes concernés, rattachés à un client quand il est connu), ``reclamation_imports`` (fichiers
  importés et leur résultat) ;
- ``reclamation_operations`` : compte, client, date, montant contesté, motif détaillé, ligne
  d'import. Une référence répétée n'est plus refusée par la base (contextes différents possibles) ;
- ``reclamations.justification_regroupement`` : obligatoire quand le dossier réunit plusieurs clients ;
- ``reclamation_referentiels.supprime_le`` : suppression logique d'un type / motif déjà utilisé ;
- nomenclature des 26 types et de leurs motifs (proposés) ; l'ancienne proposition initiale non
  validée est désactivée (réactivable, rien n'est effacé).

Revision ID: 20261015_reclamations_09
Revises: 20261015_reclamations_08
"""

import re
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.reclamations_nomenclature import NOMENCLATURE, code_motif, code_type, description_type

revision: str = "20261015_reclamations_09"
down_revision: Union[str, None] = "20261015_reclamations_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ANCIENNE_PROPOSITION = "Proposition initiale — nomenclature à valider par la banque."
CATEGORIES_DOCUMENT = (
    "NOTE", "COURRIER", "JUSTIFICATIF", "ORIGINAL", "PIECE_CLIENT", "TRANSMISSION", "FICHE_TRAITEMENT",
    "JUSTIFICATIF_SERVICE", "RETOUR_SERVICE", "REPONSE_CLIENT", "PREUVE_ENVOI", "AUTRE",
)


def _cle(texte: str) -> str:
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _in(colonne: str, valeurs: tuple[str, ...]) -> str:
    return f"{colonne} IN ({','.join(repr(v) for v in valeurs)})"


def _user(nom: str) -> sa.Column:
    return sa.Column(nom, sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("reclamation_referentiels", sa.Column("supprime_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reclamation_referentiels", _user("supprime_par_id"))
    op.add_column("reclamations", sa.Column("justification_regroupement", sa.Text(), nullable=True))

    op.create_table(
        "reclamation_participants",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("client_racine", sa.String(6), nullable=True),
        sa.Column("client_nom", sa.String(255), nullable=True),
        sa.Column("client_categorie", sa.String(12), nullable=True),
        sa.Column("statut_identification", sa.String(12), nullable=False),
        _user("created_by_id"),
        *_ts(),
        sa.CheckConstraint(_in("role", ("PRINCIPAL", "ASSOCIE")), name="ck_reclamation_participants_role"),
        sa.CheckConstraint(_in("statut_identification", ("VERIFIE", "A_VERIFIER", "A_RENSEIGNER")),
                           name="ck_reclamation_participants_statut"),
        sa.CheckConstraint("client_racine IS NULL OR client_racine ~ '^[0-9]{6}$'",
                           name="ck_reclamation_participants_racine"),
        sa.CheckConstraint("role = 'PRINCIPAL' OR client_racine IS NOT NULL",
                           name="ck_reclamation_participants_associe_identifie"),
    )
    op.create_index("ix_reclamation_participants_reclamation_id", "reclamation_participants", ["reclamation_id"])
    op.create_index("ix_reclamation_participants_client_racine", "reclamation_participants", ["client_racine"])
    op.execute("CREATE UNIQUE INDEX uq_reclamation_participants_racine ON reclamation_participants "
               "(reclamation_id, client_racine) WHERE client_racine IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_reclamation_participants_principal ON reclamation_participants "
               "(reclamation_id) WHERE role = 'PRINCIPAL'")

    op.create_table(
        "reclamation_comptes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_id", sa.UUID(), sa.ForeignKey("reclamation_participants.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("compte_reference", sa.String(60), nullable=False),
        sa.Column("devise", sa.String(3), nullable=True),
        sa.Column("statut_verification", sa.String(12), nullable=False),
        _user("created_by_id"),
        *_ts(),
        sa.CheckConstraint(_in("statut_verification", ("VERIFIE", "A_VERIFIER")),
                           name="ck_reclamation_comptes_statut"),
        sa.CheckConstraint("length(btrim(compte_reference)) > 0", name="ck_reclamation_comptes_reference"),
        sa.UniqueConstraint("reclamation_id", "compte_reference", name="uq_reclamation_comptes_reference"),
    )
    op.create_index("ix_reclamation_comptes_reclamation_id", "reclamation_comptes", ["reclamation_id"])
    op.create_index("ix_reclamation_comptes_compte_reference", "reclamation_comptes", ["compte_reference"])

    op.create_table(
        "reclamation_imports",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("ged_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("nom_fichier", sa.String(255), nullable=False),
        sa.Column("empreinte", sa.String(64), nullable=False),
        sa.Column("statut", sa.String(12), nullable=False, server_default="ANALYSE"),
        sa.Column("mode", sa.String(12), nullable=True),
        sa.Column("nb_lignes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_valides", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_erreurs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_avertissements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resultat", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confirme_le", sa.DateTime(timezone=True), nullable=True),
        _user("confirme_par_id"),
        _user("created_by_id"),
        *_ts(),
        sa.CheckConstraint(_in("statut", ("ANALYSE", "CONFIRME", "ABANDONNE")), name="ck_reclamation_imports_statut"),
        sa.CheckConstraint(f"mode IS NULL OR {_in('mode', ('AJOUT', 'REMPLACEMENT'))}",
                           name="ck_reclamation_imports_mode"),
    )
    op.create_index("ix_reclamation_imports_reclamation_id", "reclamation_imports", ["reclamation_id"])

    op.execute("ALTER TABLE reclamation_operations DROP CONSTRAINT IF EXISTS uq_reclamation_operations_reference")
    op.create_index("ix_reclamation_operations_reference", "reclamation_operations", ["reclamation_id", "reference"])
    op.add_column("reclamation_operations", sa.Column(
        "participant_id", sa.UUID(), sa.ForeignKey("reclamation_participants.id", ondelete="SET NULL"), nullable=True))
    op.add_column("reclamation_operations", sa.Column(
        "compte_id", sa.UUID(), sa.ForeignKey("reclamation_comptes.id", ondelete="SET NULL"), nullable=True))
    op.add_column("reclamation_operations", sa.Column("date_operation", sa.Date(), nullable=True))
    op.add_column("reclamation_operations", sa.Column("montant_conteste", sa.Numeric(18, 2), nullable=True))
    op.add_column("reclamation_operations", sa.Column("motif_detail", sa.Text(), nullable=True))
    op.add_column("reclamation_operations", sa.Column(
        "import_id", sa.UUID(), sa.ForeignKey("reclamation_imports.id", ondelete="SET NULL"), nullable=True))
    op.add_column("reclamation_operations", sa.Column("ligne_import", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_reclamation_operations_montant_conteste", "reclamation_operations",
                               "montant_conteste IS NULL OR montant_conteste > 0")
    op.create_index("ix_reclamation_operations_compte_id", "reclamation_operations", ["compte_id"])
    op.create_index("ix_reclamation_operations_participant_id", "reclamation_operations", ["participant_id"])

    op.execute("ALTER TABLE reclamation_documents DROP CONSTRAINT IF EXISTS ck_reclamation_documents_categorie")
    op.create_check_constraint("ck_reclamation_documents_categorie", "reclamation_documents",
                               _in("categorie", (*CATEGORIES_DOCUMENT, "IMPORT_OPERATIONS")))

    # Reprise : le client et le compte saisis sur chaque dossier deviennent son client principal / compte.
    op.execute(
        """
        INSERT INTO reclamation_participants
            (id, reclamation_id, ordre, role, client_racine, client_nom, client_categorie, statut_identification,
             created_by_id, created_at, updated_at)
        SELECT gen_random_uuid(), r.id, 1, 'PRINCIPAL', r.client_racine, r.client_nom, r.client_categorie,
               CASE WHEN r.client_racine IS NULL THEN 'A_RENSEIGNER'
                    WHEN EXISTS (SELECT 1 FROM clientele_clients c WHERE c.racine_client = r.client_racine)
                         THEN 'VERIFIE' ELSE 'A_VERIFIER' END,
               r.created_by_id, r.created_at, now()
          FROM reclamations r
        """
    )
    op.execute(
        """
        INSERT INTO reclamation_comptes
            (id, reclamation_id, participant_id, compte_reference, statut_verification, created_by_id,
             created_at, updated_at)
        SELECT gen_random_uuid(), r.id, p.id, btrim(r.compte_reference),
               CASE WHEN EXISTS (SELECT 1 FROM clientele_comptes k WHERE k.compte = btrim(r.compte_reference))
                    THEN 'VERIFIE' ELSE 'A_VERIFIER' END,
               r.created_by_id, r.created_at, now()
          FROM reclamations r
          JOIN reclamation_participants p ON p.reclamation_id = r.id AND p.role = 'PRINCIPAL'
         WHERE NULLIF(btrim(r.compte_reference), '') IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE reclamation_operations o SET participant_id = p.id
          FROM reclamation_participants p
         WHERE p.reclamation_id = o.reclamation_id AND p.role = 'PRINCIPAL' AND p.client_racine IS NOT NULL
        """
    )

    op.execute(
        """
        INSERT INTO reclamation_parametres (cle, valeur, description, updated_at)
        VALUES ('regroupement_multi_clients_autorise', 'true'::jsonb,
                'Un dossier peut réunir les opérations de plusieurs clients (justification obligatoire).', now())
        ON CONFLICT (cle) DO NOTHING
        """
    )
    _nomenclature(bind)


def _nomenclature(bind) -> None:
    bind.execute(sa.text(
        """
        UPDATE reclamation_referentiels SET actif = false, updated_at = now()
         WHERE domaine IN ('TYPE', 'MOTIF', 'SOUS_MOTIF') AND description = :d AND statut_validation = 'PROPOSEE'
        """), {"d": ANCIENNE_PROPOSITION})
    ins_type = sa.text(
        """
        INSERT INTO reclamation_referentiels (id, domaine, code, libelle, cle, description, ordre, actif)
        VALUES (gen_random_uuid(), 'TYPE', :code, :libelle, :cle, :description, :ordre, true)
        ON CONFLICT DO NOTHING
        """
    )
    ins_motif = sa.text(
        """
        INSERT INTO reclamation_referentiels (id, domaine, code, libelle, cle, parent_id, ordre, actif)
        SELECT gen_random_uuid(), 'MOTIF', :code, :libelle, :cle, t.id, :ordre, true
          FROM reclamation_referentiels t
         WHERE t.domaine = 'TYPE' AND t.parent_id IS NULL AND t.cle = :type_cle
        ON CONFLICT DO NOTHING
        """
    )
    for rang, (famille, libelle, note, motifs) in enumerate(NOMENCLATURE, start=1):
        bind.execute(ins_type, {"code": code_type(rang), "libelle": libelle, "cle": _cle(libelle),
                                "description": description_type(famille, note), "ordre": 100 + rang})
        for rang_motif, motif in enumerate(motifs, start=1):
            bind.execute(ins_motif, {"code": code_motif(rang, rang_motif), "libelle": motif, "cle": _cle(motif),
                                     "ordre": rang_motif, "type_cle": _cle(libelle)})


def downgrade() -> None:
    op.execute("DELETE FROM reclamation_referentiels r WHERE r.domaine = 'MOTIF' AND r.code ~ '^T[0-9]{2}_M[0-9]{2}$' "
               "AND NOT EXISTS (SELECT 1 FROM reclamations x WHERE x.motif_id = r.id)")
    op.execute("DELETE FROM reclamation_referentiels r WHERE r.domaine = 'TYPE' AND r.code ~ '^T[0-9]{2}$' "
               "AND NOT EXISTS (SELECT 1 FROM reclamations x WHERE x.type_id = r.id) "
               "AND NOT EXISTS (SELECT 1 FROM reclamation_referentiels m WHERE m.parent_id = r.id)")
    op.execute("DELETE FROM reclamation_parametres WHERE cle = 'regroupement_multi_clients_autorise'")
    op.execute("ALTER TABLE reclamation_documents DROP CONSTRAINT IF EXISTS ck_reclamation_documents_categorie")
    op.create_check_constraint("ck_reclamation_documents_categorie", "reclamation_documents",
                               _in("categorie", CATEGORIES_DOCUMENT))
    op.drop_constraint("ck_reclamation_operations_montant_conteste", "reclamation_operations")
    for col in ("ligne_import", "import_id", "motif_detail", "montant_conteste", "date_operation", "compte_id",
                "participant_id"):
        op.drop_column("reclamation_operations", col)
    op.drop_index("ix_reclamation_operations_reference", table_name="reclamation_operations")
    op.drop_table("reclamation_imports")
    op.drop_table("reclamation_comptes")
    op.drop_table("reclamation_participants")
    op.drop_column("reclamations", "justification_regroupement")
    op.drop_column("reclamation_referentiels", "supprime_par_id")
    op.drop_column("reclamation_referentiels", "supprime_le")
