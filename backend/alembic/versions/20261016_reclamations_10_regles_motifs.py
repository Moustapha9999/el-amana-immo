"""Réclamations : point de réception, département / service concernés (organigramme CORE), règles par
motif, opérations multi-devises, régularisation documentée.

- ``reclamation_referentiels`` : domaine ``POINT_RECEPTION`` (« Point de réception », « Service concerné ») ;
- ``reclamations`` : ``point_reception_id``, ``agence_reception_id``, ``org_departement_id`` et
  ``org_service_id`` (entités de l'organigramme central ``departements``), suivi de régularisation
  (à effectuer / effectuée : date, agent, référence de preuve, confirmation) — sans nouveau statut ;
- ``reclamation_operations`` : nature (débit / crédit), devise réelle, montant et compte attendus, rôle
  (opération initiale / en double), commentaire ; référence facultative (exigée par les règles du motif) ;
- ``reclamation_documents.operation_reference`` : pièce rattachée à une opération ; catégorie
  ``PREUVE_REGULARISATION`` (pièce exigée pour confirmer une régularisation) ;
- ``reclamation_regles_motif`` : champs requis et contrôles par motif (proposés, à valider par la banque),
  initialisés pour le type « Extournes et annulations d'opérations » ;
- paramètre ``devises_autorisees`` : MRU, USD, EUR + devises présentes dans la base clientèle ;
- permission ``reclamations.regularisation.confirm`` (responsable SR, admin).

Aucune donnée existante n'est modifiée (colonnes nullables, ajouts seulement).

Revision ID: 20261016_reclamations_10
Revises: 20261015_org_02
"""

import json
import re
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.reclamations_regles import REGLES_EXTOURNES, TYPE_EXTOURNES

revision: str = "20261016_reclamations_10"
down_revision: Union[str, None] = "20261015_org_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOMAINES_AVANT = ("TYPE", "MOTIF", "SOUS_MOTIF", "CANAL", "CANAL_REPONSE")
DOMAINES = (*DOMAINES_AVANT, "POINT_RECEPTION")
POINTS_RECEPTION = (("POINT_RECEPTION", "Point de réception", 1), ("SERVICE_CONCERNE", "Service concerné", 2))
DEVISES_DE_BASE = ("MRU", "USD", "EUR")
CATEGORIES_DOCUMENT_AVANT = ("NOTE", "COURRIER", "JUSTIFICATIF", "ORIGINAL", "PIECE_CLIENT", "TRANSMISSION",
                             "FICHE_TRAITEMENT", "JUSTIFICATIF_SERVICE", "RETOUR_SERVICE", "REPONSE_CLIENT",
                             "PREUVE_ENVOI", "AUTRE", "IMPORT_OPERATIONS")
CATEGORIES_DOCUMENT = (*CATEGORIES_DOCUMENT_AVANT, "PREUVE_REGULARISATION")
PERMISSION = ("reclamations.regularisation.confirm",
              "Confirmation documentée d'une régularisation (extourne, correction) effectuée hors BEA DIGITAL")
ROLES_PERMISSION = ("reclamations.responsable_sr", "reclamations.admin")


def _cle(texte: str) -> str:
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _in(colonne: str, valeurs: tuple[str, ...], nullable: bool = False) -> str:
    liste = ",".join(repr(v) for v in valeurs)
    return f"{colonne} IS NULL OR {colonne} IN ({liste})" if nullable else f"{colonne} IN ({liste})"


def _user(nom: str) -> sa.Column:
    return sa.Column(nom, sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    bind = op.get_bind()

    op.drop_constraint("ck_reclamation_referentiels_domaine", "reclamation_referentiels")
    op.create_check_constraint("ck_reclamation_referentiels_domaine", "reclamation_referentiels",
                               _in("domaine", DOMAINES))
    for code, libelle, ordre in POINTS_RECEPTION:
        bind.execute(sa.text(
            "INSERT INTO reclamation_referentiels (id, domaine, code, libelle, cle, ordre, actif) "
            "VALUES (gen_random_uuid(), 'POINT_RECEPTION', :code, :libelle, :cle, :ordre, true) "
            "ON CONFLICT DO NOTHING"), {"code": code, "libelle": libelle, "cle": _cle(libelle), "ordre": ordre})

    op.add_column("reclamations", sa.Column(
        "point_reception_id", sa.UUID(), sa.ForeignKey("reclamation_referentiels.id", ondelete="RESTRICT"),
        nullable=True))
    op.add_column("reclamations", sa.Column(
        "agence_reception_id", sa.UUID(), sa.ForeignKey("agences.id", ondelete="SET NULL"), nullable=True))
    op.add_column("reclamations", sa.Column(
        "org_departement_id", sa.UUID(), sa.ForeignKey("departements.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("reclamations", sa.Column(
        "org_service_id", sa.UUID(), sa.ForeignKey("departements.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("reclamations", sa.Column("regularisation_statut", sa.String(12), nullable=True))
    op.add_column("reclamations", sa.Column("regularisation_le", sa.Date(), nullable=True))
    op.add_column("reclamations", _user("regularisation_agent_id"))
    op.add_column("reclamations", sa.Column("regularisation_reference", sa.String(120), nullable=True))
    op.add_column("reclamations", sa.Column("regularisation_commentaire", sa.Text(), nullable=True))
    op.add_column("reclamations", _user("regularisation_confirme_par_id"))
    op.add_column("reclamations", sa.Column("regularisation_confirme_le", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_reclamations_regularisation", "reclamations",
                               _in("regularisation_statut", ("A_EFFECTUER", "EFFECTUEE"), nullable=True))
    op.create_check_constraint(
        "ck_reclamations_regularisation_preuve", "reclamations",
        "regularisation_statut IS DISTINCT FROM 'EFFECTUEE' OR (regularisation_le IS NOT NULL "
        "AND regularisation_reference IS NOT NULL AND regularisation_confirme_le IS NOT NULL)")
    for col in ("point_reception_id", "agence_reception_id", "org_departement_id", "org_service_id"):
        op.create_index(f"ix_reclamations_{col}", "reclamations", [col])
    op.create_index("ix_reclamations_regularisation", "reclamations", ["regularisation_statut"],
                    postgresql_where=sa.text("regularisation_statut IS NOT NULL"))

    op.alter_column("reclamation_operations", "reference", existing_type=sa.String(120), nullable=True)
    op.drop_constraint("ck_reclamation_operations_reference", "reclamation_operations")
    op.create_check_constraint("ck_reclamation_operations_reference", "reclamation_operations",
                               "reference IS NULL OR length(btrim(reference)) > 0")
    op.add_column("reclamation_operations", sa.Column("nature_mouvement", sa.String(6), nullable=True))
    op.add_column("reclamation_operations", sa.Column("montant_attendu", sa.Numeric(18, 2), nullable=True))
    op.add_column("reclamation_operations", sa.Column("compte_attendu", sa.String(60), nullable=True))
    op.add_column("reclamation_operations", sa.Column("role_operation", sa.String(10), nullable=True))
    op.add_column("reclamation_operations", sa.Column("commentaire", sa.Text(), nullable=True))
    op.create_check_constraint("ck_reclamation_operations_nature", "reclamation_operations",
                               _in("nature_mouvement", ("DEBIT", "CREDIT"), nullable=True))
    op.create_check_constraint("ck_reclamation_operations_role", "reclamation_operations",
                               _in("role_operation", ("INITIALE", "DOUBLON"), nullable=True))
    op.create_check_constraint("ck_reclamation_operations_montant_attendu", "reclamation_operations",
                               "montant_attendu IS NULL OR montant_attendu >= 0")
    op.alter_column("reclamation_operations", "devise", existing_type=sa.String(3), nullable=True,
                    server_default=None)
    op.create_check_constraint("ck_reclamation_operations_devise", "reclamation_operations",
                               "devise IS NULL OR devise ~ '^[A-Z]{3}$'")
    op.create_index("ix_reclamation_operations_ref_globale", "reclamation_operations", ["reference"])

    op.add_column("reclamation_documents", sa.Column("operation_reference", sa.String(120), nullable=True))
    op.drop_constraint("ck_reclamation_documents_categorie", "reclamation_documents")
    op.create_check_constraint("ck_reclamation_documents_categorie", "reclamation_documents",
                               _in("categorie", CATEGORIES_DOCUMENT))

    op.create_table(
        "reclamation_regles_motif",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("motif_id", sa.UUID(), sa.ForeignKey("reclamation_referentiels.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("regles", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("statut_validation", sa.String(20), nullable=False, server_default="PROPOSEE"),
        _user("valide_par_id"),
        sa.Column("valide_le", sa.DateTime(timezone=True), nullable=True),
        _user("created_by_id"),
        _user("updated_by_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in("statut_validation", ("PROPOSEE", "VALIDEE")),
                           name="ck_reclamation_regles_motif_validation"),
    )
    ins = sa.text(
        """
        INSERT INTO reclamation_regles_motif (id, motif_id, regles)
        SELECT gen_random_uuid(), m.id, CAST(:regles AS jsonb)
          FROM reclamation_referentiels m
          JOIN reclamation_referentiels t ON t.id = m.parent_id AND t.domaine = 'TYPE' AND t.cle = :type_cle
         WHERE m.domaine = 'MOTIF' AND m.cle = :motif_cle
        ON CONFLICT (motif_id) DO NOTHING
        """
    )
    for libelle, regles in REGLES_EXTOURNES.items():
        bind.execute(ins, {"regles": json.dumps(regles, ensure_ascii=False), "type_cle": _cle(TYPE_EXTOURNES),
                           "motif_cle": _cle(libelle)})

    presentes = [d for (d,) in bind.execute(sa.text(
        "SELECT DISTINCT upper(btrim(devise)) FROM clientele_comptes WHERE devise ~* '^[A-Z]{3}$' ORDER BY 1"))]
    devises = list(DEVISES_DE_BASE) + [d for d in presentes if d not in DEVISES_DE_BASE]
    bind.execute(sa.text(
        "INSERT INTO reclamation_parametres (cle, valeur, description, updated_at) "
        "VALUES ('devises_autorisees', CAST(:v AS jsonb), :d, now()) ON CONFLICT (cle) DO NOTHING"),
        {"v": json.dumps(devises), "d": "Devises acceptées sur les opérations (codes ISO 4217). Deux décimales."})

    code, libelle = PERMISSION
    bind.execute(sa.text(
        "INSERT INTO permissions (id, code, label, module) SELECT gen_random_uuid(), :c, :l, 'reclamations' "
        "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)"), {"c": code, "l": libelle})
    for role in ROLES_PERMISSION:
        bind.execute(sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = :c WHERE r.code = :r "
            "AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)"),
            {"c": code, "r": role})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM permissions WHERE code = :c").bindparams(c=PERMISSION[0]))
    op.execute("DELETE FROM reclamation_parametres WHERE cle = 'devises_autorisees'")
    op.drop_table("reclamation_regles_motif")
    op.execute("UPDATE reclamation_documents SET categorie = 'JUSTIFICATIF' WHERE categorie = 'PREUVE_REGULARISATION'")
    op.drop_constraint("ck_reclamation_documents_categorie", "reclamation_documents")
    op.create_check_constraint("ck_reclamation_documents_categorie", "reclamation_documents",
                               _in("categorie", CATEGORIES_DOCUMENT_AVANT))
    op.drop_column("reclamation_documents", "operation_reference")
    op.drop_index("ix_reclamation_operations_ref_globale", table_name="reclamation_operations")
    for ck in ("devise", "montant_attendu", "role", "nature"):
        op.drop_constraint(f"ck_reclamation_operations_{ck}", "reclamation_operations")
    # Avant cette révision, toute opération était en MRU (devise non nulle).
    op.execute("UPDATE reclamation_operations SET devise = 'MRU' WHERE devise IS NULL")
    op.alter_column("reclamation_operations", "devise", existing_type=sa.String(3), nullable=False)
    for col in ("commentaire", "role_operation", "compte_attendu", "montant_attendu", "nature_mouvement"):
        op.drop_column("reclamation_operations", col)
    op.drop_constraint("ck_reclamation_operations_reference", "reclamation_operations")
    # Les opérations sans référence (permises depuis cette révision) n'ont pas d'équivalent avant.
    op.execute("DELETE FROM reclamation_operations WHERE reference IS NULL")
    op.alter_column("reclamation_operations", "reference", existing_type=sa.String(120), nullable=False)
    op.create_check_constraint("ck_reclamation_operations_reference", "reclamation_operations",
                               "length(btrim(reference)) > 0")
    op.drop_index("ix_reclamations_regularisation", table_name="reclamations")
    for col in ("point_reception_id", "agence_reception_id", "org_departement_id", "org_service_id"):
        op.drop_index(f"ix_reclamations_{col}", table_name="reclamations")
    op.drop_constraint("ck_reclamations_regularisation_preuve", "reclamations")
    op.drop_constraint("ck_reclamations_regularisation", "reclamations")
    for col in ("regularisation_confirme_le", "regularisation_confirme_par_id", "regularisation_commentaire",
                "regularisation_reference", "regularisation_agent_id", "regularisation_le",
                "regularisation_statut", "org_service_id", "org_departement_id", "agence_reception_id",
                "point_reception_id"):
        op.drop_column("reclamations", col)
    op.execute("DELETE FROM reclamation_referentiels r WHERE r.domaine = 'POINT_RECEPTION'")
    op.drop_constraint("ck_reclamation_referentiels_domaine", "reclamation_referentiels")
    op.create_check_constraint("ck_reclamation_referentiels_domaine", "reclamation_referentiels",
                               _in("domaine", DOMAINES_AVANT))
