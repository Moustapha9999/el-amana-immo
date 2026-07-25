import enum


class TypeImmobilisation(str, enum.Enum):
    TERRAIN = "terrain"
    CONSTRUCTION = "construction"
    AAI = "aai"
    MATERIEL_INFORMATIQUE = "materiel_informatique"
    MATERIEL_BUREAU = "materiel_bureau"
    TRANSPORT = "transport"
    LOGICIEL = "logiciel"
    LICENCE = "licence"
    FRAIS_IMMOBILISES = "frais_immobilises"
    TITRES = "titres"
    EN_COURS = "immobilisation_en_cours"
    AUTRES = "autres_immobilisations"
    COFFRES = "coffres"
    AUTRES_CORPORELLES = "autres_corporelles"
    FRAIS_EMRT = "frais_emrt"


class ModeAmortissement(str, enum.Enum):
    LINEAIRE = "lineaire"
    DEGRESSIF = "degressif"


class StatutImmobilisation(str, enum.Enum):
    """Cycle de vie §6 — valeurs legacy (cession, rebut…) conservées pour compatibilité."""

    BROUILLON = "brouillon"
    EN_COURS_ACQUISITION = "en_cours_acquisition"
    EN_SERVICE = "en_service"
    SUSPENDUE = "suspendue"
    CEDEE = "cedee"
    MISE_AU_REBUT = "mise_au_rebut"
    TRANSFEREE = "transferee"
    RECLASSEE = "reclassee"
    ARCHIVEE = "archivee"
    CESSION = "cession"
    REBUT = "rebut"
    EN_COURS = "en_cours"
    SORTIE = "sortie"


class PeriodiciteAmortissement(str, enum.Enum):
    ANNUEL = "annuel"
    TRIMESTRIEL = "trimestriel"
    MENSUEL = "mensuel"


class TypeComptePlan(str, enum.Enum):
    IMMOBILISATION = "immobilisation"
    AMORTISSEMENT = "amortissement"
    DOTATION = "dotation"
    REPRISE = "reprise"
    CESSION = "cession"
    REBUT = "rebut"


class TypeAjustement(str, enum.Enum):
    CORRECTION = "correction"
    REPRISE = "reprise"


class TypePieceComptable(str, enum.Enum):
    """Pièces comptables relatives aux immobilisations."""

    FACTURE = "facture"
    PV = "pv"
    BON_COMMANDE = "bon_commande"
    BON_LIVRAISON = "bon_livraison"
    CONTRAT = "contrat"
    PROTOCOLE_ACCORD = "protocole_accord"
    AUTRE = "autre"


class TypeNotification(str, enum.Enum):
    FIN_AMORTISSEMENT = "fin_amortissement"
    MAINTENANCE = "maintenance"
    ASSURANCE = "assurance"
    INVENTAIRE = "inventaire"
    SYSTEME = "systeme"
