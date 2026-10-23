"""Réclamations : état « Suspendue », règles par motif validées par le porteur du projet, unités
Marketing dans l'organigramme CORE, retrait des dernières mentions « délais ».

- ``reclamations.statut`` accepte ``SUSPENDUE`` ; un dossier suspendu conserve son étape et le statut
  ouvert d'avant la suspension (``statut_avant_suspension``), rétabli à la reprise. Aucun délai,
  aucune échéance ni alerte n'est associé à cet état ;
- ``reclamation_regles_motif.validation_origine`` : origine de la validation (``PORTEUR_PROJET`` ou
  ``HABILITE``). Les règles encore proposées sont validées par le porteur du projet, valeurs inchangées
  — validation fonctionnelle, pas une validation réglementaire de la Conformité ;
- ``departements`` : « MARKETING & COMMUNICATION » (département) et « MARKETING ET COMMUNICATION »
  (service rattaché), libellés repris tels quels du référentiel métier existant (unités Réclamations,
  liste Formation), ``a_confirmer`` tant que la banque n'a pas fourni sa liste officielle ; les unités
  Réclamations de même libellé y sont rattachées ;
- descriptions du module et du rôle ``reclamations.admin`` : plus de mention des délais (retirés).

Revision ID: 20261023_reclamations_11
Revises: 20261022_mg_stock_alertes
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_reclamations_11"
down_revision: Union[str, None] = "20261022_mg_stock_alertes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUTS_AVANT = ("A_QUALIFIER", "A_AFFECTER", "EN_TRAITEMENT", "RETOUR_RECU", "A_CLOTURER", "CLOTUREE", "REJETEE",
                 "ANNULEE", "REOUVERTE")
STATUTS = (*STATUTS_AVANT, "SUSPENDUE")
STATUTS_SUSPENDABLES = ("A_QUALIFIER", "A_AFFECTER", "EN_TRAITEMENT", "RETOUR_RECU", "A_CLOTURER", "REOUVERTE")
ORIGINES_VALIDATION = ("PORTEUR_PROJET", "HABILITE")

SOURCE_MARKETING = "REFERENTIEL_METIER_2026_10"
NOTE_MARKETING = ("Libellé repris du référentiel métier existant (unités Réclamations, liste Formation). "
                  "Rattachement hiérarchique et positionnement à confirmer par la banque.")
MARKETING = (
    # code, libellé, type, code parent
    ("MKT-COM", "MARKETING & COMMUNICATION", "DEPARTEMENT", None),
    ("MKT-COM-SVC", "MARKETING ET COMMUNICATION", "SERVICE", "MKT-COM"),
)
UNITES_MARKETING = (("MKT-COM", "DEPARTEMENT"), ("MKT-COM-SVC", "SERVICE"))

DESCRIPTION_MODULE = (
    "Réclamations clients pilotées par le Service Réclamations : réception multicanal, qualification, "
    "transfert aux services, réponse au client, clôture et tableau de bord 360°.",
    "Réclamations clients pilotées par le Service Réclamations : réception multicanal, qualification, "
    "transfert aux services, réponse au client, clôture, délais et tableau de bord 360°.",
)
DESCRIPTION_ADMIN = ("Administration complète : paramètres, référentiels, droits",
                     "Administration complète : paramètres, délais, droits")


def _in(colonne: str, valeurs: tuple[str, ...], nullable: bool = False) -> str:
    liste = ",".join(repr(v) for v in valeurs)
    return f"{colonne} IS NULL OR {colonne} IN ({liste})" if nullable else f"{colonne} IN ({liste})"


def upgrade() -> None:
    bind = op.get_bind()

    op.drop_constraint("ck_reclamations_statut", "reclamations")
    op.create_check_constraint("ck_reclamations_statut", "reclamations", _in("statut", STATUTS))
    op.create_check_constraint(
        "ck_reclamations_suspension", "reclamations",
        f"statut <> 'SUSPENDUE' OR ({_in('statut_avant_suspension', STATUTS_SUSPENDABLES)})")

    op.add_column("reclamation_regles_motif", sa.Column("validation_origine", sa.String(20), nullable=True))
    op.create_check_constraint("ck_reclamation_regles_motif_origine", "reclamation_regles_motif",
                               _in("validation_origine", ORIGINES_VALIDATION, nullable=True))
    op.execute("UPDATE reclamation_regles_motif SET validation_origine = 'HABILITE' "
               "WHERE statut_validation = 'VALIDEE'")
    op.execute("UPDATE reclamation_regles_motif SET statut_validation = 'VALIDEE', valide_le = now(), "
               "valide_par_id = NULL, validation_origine = 'PORTEUR_PROJET', updated_at = now() "
               "WHERE statut_validation = 'PROPOSEE'")

    for code, libelle, type_entite, parent in MARKETING:
        bind.execute(sa.text("""
            INSERT INTO departements (id, code, libelle, type_entite, parent_id, ordre, a_confirmer,
                                      note_confirmation, source, metadonnees, is_active)
            SELECT gen_random_uuid(), :code, :libelle, :type, p.id,
                   (SELECT coalesce(max(s.ordre), 0) + 1 FROM departements s
                     WHERE s.parent_id IS NOT DISTINCT FROM p.id),
                   true, :note, :source, CAST(:meta AS jsonb), true
            FROM (SELECT (SELECT id FROM departements
                           WHERE code = CAST(:parent AS varchar) AND deleted_at IS NULL) AS id) p
            WHERE (CAST(:parent AS varchar) IS NULL OR p.id IS NOT NULL)
              AND NOT EXISTS (SELECT 1 FROM departements WHERE upper(code) = upper(:code))
              AND NOT EXISTS (SELECT 1 FROM departements d WHERE d.parent_id IS NOT DISTINCT FROM p.id
                              AND d.deleted_at IS NULL AND d.cle = org_cle(:libelle))
        """), {"code": code, "libelle": libelle, "type": type_entite, "parent": parent, "note": NOTE_MARKETING,
               "source": SOURCE_MARKETING, "meta": json.dumps({"statut_validation": "a_confirmer"})})
    for code, type_unite in UNITES_MARKETING:
        bind.execute(sa.text("""
            UPDATE reclamation_unites u SET org_entite_id = d.id
              FROM departements d
             WHERE d.code = :code AND d.deleted_at IS NULL AND u.org_entite_id IS NULL
               AND u.type_unite = :type AND u.cle = d.cle
        """), {"code": code, "type": type_unite})

    bind.execute(sa.text("UPDATE plateforme_modules SET description = :n WHERE code = 'reclamations' "
                         "AND description = :a"), {"n": DESCRIPTION_MODULE[0], "a": DESCRIPTION_MODULE[1]})
    bind.execute(sa.text("UPDATE roles SET description = :n WHERE code = 'reclamations.admin' AND description = :a"),
                 {"n": DESCRIPTION_ADMIN[0], "a": DESCRIPTION_ADMIN[1]})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE roles SET description = :a WHERE code = 'reclamations.admin' AND description = :n"),
                 {"n": DESCRIPTION_ADMIN[0], "a": DESCRIPTION_ADMIN[1]})
    bind.execute(sa.text("UPDATE plateforme_modules SET description = :a WHERE code = 'reclamations' "
                         "AND description = :n"), {"n": DESCRIPTION_MODULE[0], "a": DESCRIPTION_MODULE[1]})

    op.execute(f"""
        UPDATE reclamation_unites SET org_entite_id = NULL
         WHERE org_entite_id IN (SELECT id FROM departements WHERE source = '{SOURCE_MARKETING}')
    """)
    # Retire les entités que rien ne référence ; les autres (dossiers, sous-entités) sont désactivées.
    op.execute(f"""
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN SELECT id FROM departements WHERE source = '{SOURCE_MARKETING}' ORDER BY length(code) DESC LOOP
            BEGIN
              DELETE FROM departements WHERE id = r.id;
            EXCEPTION WHEN foreign_key_violation THEN
              UPDATE departements SET is_active = false WHERE id = r.id;
            END;
          END LOOP;
        END $$;
    """)

    op.execute("UPDATE reclamation_regles_motif SET statut_validation = 'PROPOSEE', valide_le = NULL, "
               "valide_par_id = NULL WHERE validation_origine = 'PORTEUR_PROJET'")
    op.drop_constraint("ck_reclamation_regles_motif_origine", "reclamation_regles_motif")
    op.drop_column("reclamation_regles_motif", "validation_origine")

    # Un dossier suspendu reprend le statut qu'il avait avant la suspension.
    op.execute("UPDATE reclamations SET statut = statut_avant_suspension, statut_avant_suspension = NULL "
               "WHERE statut = 'SUSPENDUE'")
    op.drop_constraint("ck_reclamations_suspension", "reclamations")
    op.drop_constraint("ck_reclamations_statut", "reclamations")
    op.create_check_constraint("ck_reclamations_statut", "reclamations", _in("statut", STATUTS_AVANT))
