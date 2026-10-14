"""Réclamations — circuit en 4 étapes, opérations multiples, motif « Autre ».

Additif et compatible avec les dossiers existants :
- table ``reclamation_operations`` (1-N) alimentée depuis ``operation_reference`` /
  ``montant_conteste`` / ``devise`` (colonnes historiques conservées, plus saisies) ;
- colonnes ``date_reclamation``, ``motif_autre``, ``sous_motif_autre``, ``unite_concernee_id`` ;
- statuts et étapes ramenés au circuit Réception → Affectation → Traitement → Clôture ; chaque
  dossier repris reçoit un événement ``MIGRATION_CIRCUIT`` (statut avant / après) dans son
  historique, qui reste en ajout seul ;
- motifs proposés (non réglementaires, « à valider par la banque ») sous les types existants,
  uniquement pour un type qui n'a encore aucun motif ;
- canal « Papier » renommé « Dépôt physique » s'il n'a pas été modifié par la banque.

Revision ID: 20261014_reclamations_02
Revises: 20261013_reclamations_01
"""

import re
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_reclamations_02"
down_revision: Union[str, None] = "20261013_reclamations_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUTS = ("A_QUALIFIER", "A_AFFECTER", "EN_TRAITEMENT", "RETOUR_RECU", "A_CLOTURER", "CLOTUREE", "REJETEE",
           "ANNULEE", "REOUVERTE")
ETAPES = ("RECEPTION", "AFFECTATION", "TRAITEMENT", "CLOTURE")
ANCIENS_STATUTS = ("RECUE", "RECUE_SR", "A_QUALIFIER", "AFFECTEE", "EN_TRAITEMENT", "ATTENTE_INFO", "RETOUR_RECU",
                   "REPONSE_A_PREPARER", "REPONSE_ENVOYEE", "SUSPENDUE", "REFUSEE", "CLOTUREE", "REOUVERTE",
                   "ANNULEE")
ANCIENNES_ETAPES = ("RECEPTION", "QUALIFICATION", "AFFECTATION", "TRAITEMENT", "RETOUR", "REPONSE", "CLOTURE")

CORRESPONDANCE = {
    "RECUE": "A_QUALIFIER",
    "RECUE_SR": "A_QUALIFIER",
    "A_QUALIFIER": "A_AFFECTER",
    "AFFECTEE": "EN_TRAITEMENT",
    "EN_TRAITEMENT": "EN_TRAITEMENT",
    "RETOUR_RECU": "RETOUR_RECU",
    "REPONSE_A_PREPARER": "A_CLOTURER",
    "REPONSE_ENVOYEE": "A_CLOTURER",
    "REFUSEE": "REJETEE",
    "CLOTUREE": "CLOTUREE",
    "REOUVERTE": "REOUVERTE",
    "ANNULEE": "ANNULEE",
}
ETAPE_DU_STATUT = {
    "A_QUALIFIER": "RECEPTION",
    "A_AFFECTER": "AFFECTATION",
    "REOUVERTE": "AFFECTATION",
    "EN_TRAITEMENT": "TRAITEMENT",
}

MOTIF_DESCRIPTION = "Proposition initiale — nomenclature à valider par la banque."
MOTIFS = {
    "Opérations et virements": [
        "Virement non reçu", "Virement non exécuté ou en retard", "Opération non reconnue",
        "Erreur de montant", "Annulation d'écriture",
    ],
    "Compte bancaire": [
        "Ouverture de compte", "Clôture de compte", "Relevé ou attestation non délivré", "Blocage de compte",
    ],
    "Carte bancaire": [
        "Retrait GAB non servi", "Transaction carte non reconnue", "Carte capturée ou bloquée",
        "Délai de délivrance de la carte",
    ],
    "Frais et commissions": ["Frais contestés", "Agios ou intérêts contestés"],
    "Crédit et remboursement": [
        "Échéance prélevée à tort", "Remboursement anticipé", "Délai de traitement du crédit",
    ],
    "Accueil et qualité de service": [
        "Temps d'attente", "Comportement du personnel", "Information erronée ou insuffisante",
    ],
    "Amanty Wallet": ["Transaction échouée", "Accès au compte Amanty", "Paiement marchand"],
    "Banque digitale et moyens de paiement": [
        "Accès à la banque en ligne", "Chèque ou chéquier", "Règlement d'impôts ou de factures via plateforme",
    ],
}


def _cle(texte: str) -> str:
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _in(colonne: str, valeurs: tuple[str, ...]) -> str:
    return f"{colonne} IN ({','.join(repr(v) for v in valeurs)})"


def _case(colonne: str, table: dict[str, str], defaut: str) -> str:
    branches = " ".join(f"WHEN {k!r} THEN {v!r}" for k, v in table.items())
    return f"CASE {colonne} {branches} ELSE {defaut} END"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colonnes = {c["name"] for c in insp.get_columns("reclamations")}

    if "date_reclamation" not in colonnes:
        op.add_column("reclamations", sa.Column("date_reclamation", sa.Date(), nullable=True))
    if "motif_autre" not in colonnes:
        op.add_column("reclamations", sa.Column("motif_autre", sa.String(200), nullable=True))
    if "sous_motif_autre" not in colonnes:
        op.add_column("reclamations", sa.Column("sous_motif_autre", sa.String(200), nullable=True))
    if "unite_concernee_id" not in colonnes:
        op.add_column("reclamations", sa.Column(
            "unite_concernee_id", sa.UUID(),
            sa.ForeignKey("reclamation_unites.id", ondelete="RESTRICT"), nullable=True))
        op.create_index("ix_reclamations_unite_concernee_id", "reclamations", ["unite_concernee_id"])
    op.execute("UPDATE reclamations SET date_reclamation = (date_premiere_reception AT TIME ZONE 'UTC')::date "
               "WHERE date_reclamation IS NULL")

    if not insp.has_table("reclamation_operations"):
        op.create_table(
            "reclamation_operations",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("ordre", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("reference", sa.String(120), nullable=False),
            sa.Column("montant", sa.Numeric(18, 2), nullable=True),
            sa.Column("devise", sa.String(3), nullable=False, server_default="MRU"),
            sa.Column("created_by_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.CheckConstraint("montant IS NULL OR montant > 0", name="ck_reclamation_operations_montant"),
            sa.CheckConstraint("length(btrim(reference)) > 0", name="ck_reclamation_operations_reference"),
            sa.UniqueConstraint("reclamation_id", "reference", name="uq_reclamation_operations_reference"),
        )
        op.create_index("ix_reclamation_operations_reclamation_id", "reclamation_operations", ["reclamation_id"])
        op.execute(
            """
            INSERT INTO reclamation_operations
                (id, reclamation_id, ordre, reference, montant, devise, created_by_id, created_at, updated_at)
            SELECT gen_random_uuid(), id, 1,
                   COALESCE(NULLIF(btrim(operation_reference), ''), 'Non renseignée'),
                   CASE WHEN montant_conteste > 0 THEN montant_conteste END,
                   COALESCE(NULLIF(upper(btrim(devise)), ''), 'MRU'),
                   created_by_id, created_at, now()
              FROM reclamations
             WHERE NULLIF(btrim(operation_reference), '') IS NOT NULL OR montant_conteste > 0
            """
        )

    # Circuit : contraintes relâchées le temps de la reprise, puis reposées sur les nouvelles valeurs.
    for nom in ("ck_reclamations_statut", "ck_reclamations_etape", "ck_reclamations_statut_avant_suspension"):
        op.execute(f"ALTER TABLE reclamations DROP CONSTRAINT IF EXISTS {nom}")
    origine = "CASE WHEN statut IN ('ATTENTE_INFO', 'SUSPENDUE') THEN COALESCE(statut_avant_suspension, 'RECUE') " \
              "ELSE statut END"
    nouveau = _case(f"({origine})", CORRESPONDANCE, "'A_QUALIFIER'")
    op.execute(f"CREATE TEMP TABLE _rc_reprise ON COMMIT DROP AS SELECT id, statut AS statut_avant, "
               f"etape AS etape_avant, {nouveau} AS statut_apres FROM reclamations")
    op.execute(
        f"""
        UPDATE reclamations r
           SET statut = p.statut_apres,
               etape = {_case('p.statut_apres', ETAPE_DU_STATUT, "'CLOTURE'")},
               statut_avant_suspension = NULL,
               revision = r.revision + 1
          FROM _rc_reprise p
         WHERE p.id = r.id
        """
    )
    op.execute(
        """
        INSERT INTO reclamation_evenements
            (id, reclamation_id, type_evenement, statut_avant, statut_apres, etape_avant, etape_apres,
             date_effet, commentaire, donnees)
        SELECT gen_random_uuid(), r.id, 'MIGRATION_CIRCUIT', p.statut_avant, r.statut, p.etape_avant, r.etape,
               now(), 'Reprise dans le circuit en 4 étapes (Réception, Affectation, Traitement, Clôture).',
               jsonb_build_object('statut_avant', p.statut_avant, 'etape_avant', p.etape_avant)
          FROM reclamations r JOIN _rc_reprise p ON p.id = r.id
         WHERE p.statut_avant IS DISTINCT FROM r.statut OR p.etape_avant IS DISTINCT FROM r.etape
        """
    )
    op.create_check_constraint("ck_reclamations_statut", "reclamations", _in("statut", STATUTS))
    op.create_check_constraint("ck_reclamations_etape", "reclamations", _in("etape", ETAPES))

    _seed_motifs(bind)
    op.execute("UPDATE reclamation_referentiels SET libelle = 'Dépôt physique (agence / siège)', "
               "cle = 'depot physique agence siege', updated_at = now() "
               "WHERE domaine = 'CANAL' AND code = 'PAPIER' AND libelle = 'Papier (agence / siège)'")


def _seed_motifs(bind) -> None:
    types = {row.cle: row.id for row in bind.execute(sa.text(
        "SELECT id, cle FROM reclamation_referentiels WHERE domaine = 'TYPE' AND parent_id IS NULL"))}
    deja = {row.parent_id for row in bind.execute(sa.text(
        "SELECT DISTINCT parent_id FROM reclamation_referentiels WHERE domaine = 'MOTIF'"))}
    ins = sa.text(
        """
        INSERT INTO reclamation_referentiels (id, domaine, libelle, cle, parent_id, description, ordre, actif)
        VALUES (gen_random_uuid(), 'MOTIF', :libelle, :cle, :parent, :description, :ordre, true)
        ON CONFLICT DO NOTHING
        """
    )
    for type_libelle, motifs in MOTIFS.items():
        parent = types.get(_cle(type_libelle))
        if parent is None or parent in deja:
            continue
        for i, libelle in enumerate(motifs, start=1):
            bind.execute(ins, {"libelle": libelle, "cle": _cle(libelle), "parent": parent,
                               "description": MOTIF_DESCRIPTION, "ordre": i})


def downgrade() -> None:
    """Retour au circuit 7 étapes (correspondance approchée ; l'historique garde la trace de la reprise)."""
    for nom in ("ck_reclamations_statut", "ck_reclamations_etape"):
        op.execute(f"ALTER TABLE reclamations DROP CONSTRAINT IF EXISTS {nom}")
    retour = {"A_QUALIFIER": "RECUE_SR", "A_AFFECTER": "A_QUALIFIER", "A_CLOTURER": "REPONSE_A_PREPARER",
              "REJETEE": "REFUSEE"}
    etapes = {"RECUE_SR": "RECEPTION", "A_QUALIFIER": "QUALIFICATION", "EN_TRAITEMENT": "TRAITEMENT",
              "RETOUR_RECU": "RETOUR", "REPONSE_A_PREPARER": "REPONSE", "REOUVERTE": "QUALIFICATION"}
    op.execute(f"UPDATE reclamations SET statut = {_case('statut', retour, 'statut')}")
    op.execute(f"UPDATE reclamations SET etape = {_case('statut', etapes, repr('CLOTURE'))}")
    op.create_check_constraint("ck_reclamations_statut", "reclamations", _in("statut", ANCIENS_STATUTS))
    op.create_check_constraint("ck_reclamations_etape", "reclamations", _in("etape", ANCIENNES_ETAPES))
    op.create_check_constraint("ck_reclamations_statut_avant_suspension", "reclamations",
                               f"statut_avant_suspension IS NULL OR {_in('statut_avant_suspension', ANCIENS_STATUTS)}")
    op.execute("UPDATE reclamation_referentiels SET libelle = 'Papier (agence / siège)', "
               "cle = 'papier agence siege' WHERE domaine = 'CANAL' AND code = 'PAPIER' "
               "AND libelle = 'Dépôt physique (agence / siège)'")
    op.drop_table("reclamation_operations")
    op.drop_index("ix_reclamations_unite_concernee_id", table_name="reclamations")
    for col in ("unite_concernee_id", "sous_motif_autre", "motif_autre", "date_reclamation"):
        op.drop_column("reclamations", col)
