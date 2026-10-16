"""Règles de saisie par motif de réclamation (proposition à valider par la banque).

Une règle décrit, pour un motif :
- ``champs_requis`` : colonnes obligatoires sur chaque opération (voir ``CHAMPS_OPERATION``) ;
- ``operations_min`` : nombre d'opérations exigé avant la transmission au service (0 = aucune) ;
- ``nature_attendue`` : ``DEBIT`` / ``CREDIT`` — une nature renseignée différente est refusée ;
- ``controle`` : contrôle spécifique (``CONTROLES``) ;
- ``justificatif_requis`` : au moins une pièce (justificatif, pièce client, courrier) avant transmission ;
- ``regularisation`` : une décision favorable ouvre une régularisation à confirmer (jamais exécutée par
  BEA DIGITAL : la confirmation est documentée par un utilisateur habilité) ;
- ``consigne`` : texte d'aide affiché à la saisie.

Sans règle enregistrée pour le motif, ``REGLE_PAR_DEFAUT`` s'applique (comportement historique :
référence et montant obligatoires). Les valeurs ci-dessous initialisent la table
``reclamation_regles_motif`` (migration ``20261016_reclamations_10``) ; elles se modifient ensuite
dans Paramètres, jamais dans ce fichier.
"""

from __future__ import annotations

CHAMPS_OPERATION: dict[str, str] = {
    "client_racine": "Client concerné",
    "compte_reference": "Référence du compte",
    "reference": "Référence de l'opération",
    "date_operation": "Date de l'opération",
    "nature_mouvement": "Nature du mouvement",
    "devise": "Devise",
    "montant": "Montant initial",
    "montant_conteste": "Montant à extourner / régulariser",
    "montant_attendu": "Montant attendu",
    "compte_attendu": "Compte attendu",
    "role_operation": "Rôle (initiale / en double)",
    "motif_detail": "Motif de la ligne",
}
CONTROLES: dict[str, str] = {
    "DOUBLE": "Opération en double : au moins deux lignes, une initiale et une en double",
    "MAUVAIS_COMPTE": "Mauvais compte : compte attendu différent du compte mouvementé",
    "MONTANT_INCORRECT": "Montant incorrect : montant attendu différent ; montant à régulariser = écart",
    "PARTIELLE": "Extourne partielle : montant à extourner inférieur au montant initial",
    "ANNULATION": "Annulation : opération non comptabilisée (sinon, motif d'extourne)",
    "CORRECTION": "Correction comptable : justification détaillée par ligne",
}

REGLE_PAR_DEFAUT: dict = {
    "champs_requis": ["reference", "montant"],
    "operations_min": 0,
    "nature_attendue": None,
    "controle": None,
    "justificatif_requis": False,
    "regularisation": False,
    "consigne": None,
}

TYPE_EXTOURNES = "Extournes et annulations d'opérations"

_BASE = ["reference", "date_operation", "compte_reference", "montant", "devise"]


def _regle(champs: list[str], *, nature: str | None = None, controle: str | None = None,
           justificatif: bool = False, regularisation: bool = True, operations_min: int = 1,
           consigne: str | None = None) -> dict:
    return {"champs_requis": champs, "operations_min": operations_min, "nature_attendue": nature,
            "controle": controle, "justificatif_requis": justificatif, "regularisation": regularisation,
            "consigne": consigne}


REGLES_EXTOURNES: dict[str, dict] = {
    "Extourne d'un débit erroné": _regle(
        [*_BASE, "montant_conteste"], nature="DEBIT",
        consigne="Opération débitée à tort : montant initial et montant à extourner obligatoires."),
    "Extourne d'un crédit erroné": _regle(
        [*_BASE, "montant_conteste"], nature="CREDIT",
        consigne="Opération créditée à tort : montant initial et montant à extourner obligatoires."),
    "Extourne d'une opération comptabilisée en double": _regle(
        [*_BASE, "role_operation"], controle="DOUBLE", operations_min=2,
        consigne="Saisissez l'opération initiale et l'opération en double (une ligne chacune)."),
    "Extourne d'une opération passée sur le mauvais compte": _regle(
        ["reference", "compte_reference", "compte_attendu", "montant", "devise"], controle="MAUVAIS_COMPTE",
        consigne="Compte mouvementé et compte attendu obligatoires. Aucun transfert n'est effectué "
                 "automatiquement."),
    "Extourne d'une opération d'un montant incorrect": _regle(
        ["reference", "montant", "montant_attendu", "devise"], controle="MONTANT_INCORRECT",
        consigne="Montant comptabilisé et montant attendu ; le montant à régulariser, s'il est saisi, doit "
                 "être égal à l'écart."),
    "Extourne d'une opération comptabilisée à tort": _regle(
        ["reference", "date_operation", "montant", "devise"], justificatif=True,
        consigne="Justificatif obligatoire avant transmission."),
    "Annulation d'une opération en attente, si autorisée": _regle(
        ["reference", "montant", "devise"], controle="ANNULATION", regularisation=False,
        consigne="Annulation d'une opération non encore comptabilisée. Aucune annulation n'est exécutée "
                 "automatiquement."),
    "Annulation d'une opération non exécutée": _regle(
        ["reference", "devise"], controle="ANNULATION", regularisation=False,
        consigne="Vérifiez que l'opération n'a pas été comptabilisée ; sinon, choisissez un motif d'extourne."),
    "Correction d'une erreur de comptabilisation": _regle(
        ["reference", "montant", "devise", "motif_detail"], controle="CORRECTION", justificatif=True,
        consigne="Justification détaillée sur chaque ligne et pièces justificatives obligatoires."),
    "Contrepassation d'une écriture": _regle(["reference", "date_operation", "montant", "devise"]),
    "Régularisation d'une opération": _regle(["reference", "montant", "devise"]),
    "Extourne partielle": _regle(
        ["reference", "montant", "montant_conteste", "devise"], controle="PARTIELLE",
        consigne="Montant à extourner > 0 et inférieur au montant initial. Le solde encore extournable n'est "
                 "pas connu sans ORION : il reste à vérifier par le service."),
}
