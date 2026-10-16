"""Opérations d'un dossier, clients participants et comptes concernés.

Modèle : un dossier → 1 client principal (+ clients associés, cas exceptionnel justifié) → comptes
→ opérations. Chaque opération porte sa référence, son montant, et quand ils sont connus son compte
et son client. Un client ou un compte absent de la base clientèle reste « à vérifier » ; une
information non fournie reste « à renseigner » : rien n'est présumé vérifié.

Contrôles partagés par la saisie manuelle et l'import Excel :
- erreurs (bloquantes) : champ exigé par la règle du motif absent (``regles.Exigences``), montant
  invalide, montant sans devise ou devise non autorisée, contesté > montant, date future, racine mal
  formée, nature contraire à celle du motif, contrôle du motif non satisfait (extourne partielle,
  montant incorrect, mauvais compte), compte rattaché à un autre client, ligne strictement identique ;
- avertissements : référence répétée dans un autre contexte, doublon potentiel (même compte, date,
  montant), client / compte à vérifier ou à renseigner, annulation à vérifier.

Les totaux sont calculés par dossier **et par devise** : des montants de devises différentes ne sont
jamais additionnés. Un dossier à plusieurs opérations compte pour **un** dossier.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ClienteleClient,
    ClienteleCompte,
    Reclamation,
    ReclamationCompte,
    ReclamationOperation,
    ReclamationParametre,
    ReclamationParticipant,
)
from app.data.reclamations_regles import CHAMPS_OPERATION
from app.services.reclamations import constantes as C
from app.services.reclamations.outils import conflit, erreur, maintenant, propre, texte_long
from app.services.reclamations.regles import Exigences, controles_dossier

CENTIME = Decimal("0.01")
MONTANT_MAX = Decimal("9999999999999999.99")
OK, AVERTISSEMENT, ERREUR = "OK", "AVERTISSEMENT", "ERREUR"
NATURES = {"DEBIT": "DEBIT", "D": "DEBIT", "DB": "DEBIT", "CREDIT": "CREDIT", "C": "CREDIT", "CR": "CREDIT"}
ROLES = {"INITIALE": "INITIALE", "INITIAL": "INITIALE", "ORIGINE": "INITIALE",
         "DOUBLON": "DOUBLON", "DOUBLE": "DOUBLON", "EN DOUBLE": "DOUBLON"}


@dataclass
class Ligne:
    """Opération en cours de contrôle. ``rang`` : position saisie, ou n° de ligne Excel.

    Chaque erreur porte le champ concerné (``erreurs_champs``) pour l'affichage dans le tableau."""

    rang: int
    reference: str = ""
    montant: Decimal | None = None
    montant_conteste: Decimal | None = None
    date_operation: date | None = None
    client_racine: str | None = None
    compte_reference: str | None = None
    motif_detail: str | None = None
    nature_mouvement: str | None = None
    devise: str | None = None
    montant_attendu: Decimal | None = None
    compte_attendu: str | None = None
    role_operation: str | None = None
    commentaire: str | None = None
    erreurs: list[tuple[str, str]] = field(default_factory=list)
    erreurs_champs: list[str | None] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    client_nom: str | None = None
    statut_client: str | None = None
    statut_compte: str | None = None

    @property
    def statut(self) -> str:
        return ERREUR if self.erreurs else AVERTISSEMENT if self.avertissements else OK

    def ajouter_erreur(self, code: str, message: str, champ: str | None = None) -> None:
        self.erreurs.append((code, message))
        self.erreurs_champs.append(champ)

    def cle_identique(self) -> tuple:
        return (self.reference.casefold(), (self.compte_reference or "").casefold(), self.client_racine,
                self.date_operation, self.montant, self.montant_conteste, self.devise, self.nature_mouvement)

    def brut(self) -> dict:
        return {"ligne": self.rang, "reference": self.reference or None, "montant": _s(self.montant),
                "montant_conteste": _s(self.montant_conteste),
                "date_operation": self.date_operation.isoformat() if self.date_operation else None,
                "client_racine": self.client_racine, "compte_reference": self.compte_reference,
                "motif_detail": self.motif_detail, "nature_mouvement": self.nature_mouvement,
                "devise": self.devise, "montant_attendu": _s(self.montant_attendu),
                "compte_attendu": self.compte_attendu, "role_operation": self.role_operation,
                "commentaire": self.commentaire}

    def apercu(self) -> dict:
        return {**self.brut(), "client_nom": self.client_nom, "statut_client": self.statut_client,
                "statut_compte": self.statut_compte, "statut": self.statut,
                "erreurs": [m for _c, m in self.erreurs],
                "erreurs_detail": [{"code": c, "message": m, "champ": ch}
                                   for (c, m), ch in zip(self.erreurs, self.erreurs_champs, strict=False)],
                "avertissements": self.avertissements}


def _s(m: Decimal | None) -> str | None:
    return str(m) if m is not None else None


def _montant(valeur: Any) -> Decimal:
    """Montant > 0, deux décimales au plus ; accepte « 1 250 000,00 » comme « 1250000.00 »."""
    if isinstance(valeur, str):
        valeur = valeur.replace("\u202f", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        m = Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        raise ValueError("montant non numérique") from None
    if not m.is_finite() or m <= 0:
        raise ValueError("le montant doit être strictement positif")
    if isinstance(valeur, float):
        m = m.quantize(CENTIME) if abs(m - m.quantize(CENTIME)) < Decimal("0.000001") else m
    if m != m.quantize(CENTIME):
        raise ValueError("deux décimales au plus")
    if m > MONTANT_MAX:
        raise ValueError("montant trop élevé")
    return m.quantize(CENTIME)


def _date(valeur: Any) -> date:
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    texte = propre(str(valeur))
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(texte, fmt).date()
        except ValueError:
            continue
    raise ValueError("date illisible (JJ/MM/AAAA attendu)")


def _vide(valeur: Any) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def racine_texte(valeur: Any) -> str:
    """Racine saisie ou lue dans Excel (où les zéros de tête disparaissent des nombres)."""
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    if isinstance(valeur, int):
        return str(valeur).zfill(6)
    return propre(str(valeur))


def compte_texte(valeur: Any) -> str:
    """Compte ORION (11 chiffres) ; un RIB (23 chiffres) est ramené à son numéro de compte."""
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    if isinstance(valeur, int):
        valeur = str(valeur).zfill(11) if len(str(valeur)) <= 11 else str(valeur)
    texte = propre(str(valeur)).replace(" ", "")
    return texte[10:21] if len(texte) == 23 and texte.isdigit() else texte


def _texte_reference(valeur: Any) -> str:
    """Référence lue telle quelle : jamais tronquée ni privée de ses zéros (Excel : nombre entier → texte)."""
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    return "" if _vide(valeur) else propre(str(valeur))


def _montant_champ(lg: Ligne, brut: dict, champ: str, libelle: str) -> Decimal | None:
    if _vide(brut.get(champ)):
        return None
    try:
        return _montant(brut[champ]) if champ != "montant_attendu" else _montant_positif_ou_nul(brut[champ])
    except ValueError as e:
        lg.ajouter_erreur("MONTANT_INVALIDE", f"{libelle} : {e}", champ)
        return None


def _montant_positif_ou_nul(valeur: Any) -> Decimal:
    if isinstance(valeur, str):
        valeur = valeur.replace("\u202f", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        m = Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        raise ValueError("montant non numérique") from None
    if not m.is_finite() or m < 0:
        raise ValueError("le montant ne peut pas être négatif")
    if m == 0:
        return Decimal("0.00")
    return _montant(m)


def lire(brut: dict, rang: int, ex: Exigences | None = None, *, devise_defaut: str | None = None) -> Ligne:
    """Contrôles propres à une ligne : format, champs exigés par le motif, cohérence interne.

    ``devise_defaut`` : saisie manuelle uniquement (MRU présélectionnée et visible) ; l'import n'en a pas."""
    ex = ex or Exigences()
    lg = Ligne(rang=rang)
    lg.reference = _texte_reference(brut.get("reference"))
    if len(lg.reference) > 120:
        lg.ajouter_erreur("OPERATION_REFERENCE_INVALIDE", "référence trop longue (120 caractères)", "reference")
    lg.montant = _montant_champ(lg, brut, "montant", "montant initial")
    lg.montant_conteste = _montant_champ(lg, brut, "montant_conteste", "montant à extourner")
    lg.montant_attendu = _montant_champ(lg, brut, "montant_attendu", "montant attendu")
    if lg.montant is not None and lg.montant_conteste is not None and lg.montant_conteste > lg.montant:
        lg.ajouter_erreur("MONTANT_CONTESTE_SUPERIEUR",
                          "le montant à extourner dépasse le montant initial de l'opération", "montant_conteste")
    if not _vide(brut.get("date_operation")):
        try:
            lg.date_operation = _date(brut["date_operation"])
        except ValueError as e:
            lg.ajouter_erreur("DATE_INVALIDE", str(e), "date_operation")
        else:
            if lg.date_operation > maintenant().date():
                lg.ajouter_erreur("DATE_FUTURE", "la date de l'opération est dans le futur", "date_operation")
    if not _vide(brut.get("client_racine")):
        racine = racine_texte(brut["client_racine"])
        if len(racine) == 6 and racine.isdigit():
            lg.client_racine = racine
        else:
            lg.ajouter_erreur("RACINE_INVALIDE", f"identifiant client « {racine} » : 6 chiffres attendus",
                              "client_racine")
    for champ in ("compte_reference", "compte_attendu"):
        if not _vide(brut.get(champ)):
            compte = compte_texte(brut[champ])
            if len(compte) > 60:
                lg.ajouter_erreur("COMPTE_INVALIDE", "référence de compte trop longue (60 caractères)", champ)
            else:
                setattr(lg, champ, compte)
    if not _vide(brut.get("nature_mouvement")):
        nature = NATURES.get(propre(str(brut["nature_mouvement"])).upper().replace("É", "E"))
        if nature is None:
            lg.ajouter_erreur("NATURE_INVALIDE", "nature du mouvement : DEBIT ou CREDIT attendu", "nature_mouvement")
        lg.nature_mouvement = nature
    if not _vide(brut.get("role_operation")):
        role = ROLES.get(propre(str(brut["role_operation"])).upper())
        if role is None:
            lg.ajouter_erreur("ROLE_INVALIDE", "rôle : INITIALE ou DOUBLON attendu", "role_operation")
        lg.role_operation = role
    devise = propre(str(brut["devise"])).upper() if not _vide(brut.get("devise")) else None
    montants = any(m is not None for m in (lg.montant, lg.montant_conteste, lg.montant_attendu))
    if devise is None and montants and devise_defaut and not ex.requis("devise"):
        devise = devise_defaut
        lg.avertissements.append(f"devise non précisée : {devise_defaut} retenue")
    if devise is not None and devise not in ex.devises:
        lg.ajouter_erreur("DEVISE_INVALIDE", f"devise « {devise} » non autorisée ({', '.join(sorted(ex.devises))})",
                          "devise")
    elif devise is None and montants:
        lg.ajouter_erreur("DEVISE_OBLIGATOIRE", "la devise est obligatoire dès qu'un montant est renseigné", "devise")
    lg.devise = devise
    lg.motif_detail = texte_long(str(brut["motif_detail"])) if not _vide(brut.get("motif_detail")) else None
    lg.commentaire = texte_long(str(brut["commentaire"])) if not _vide(brut.get("commentaire")) else None
    appliquer_regle(lg, ex)
    return lg


def _valeur(lg: Ligne, champ: str) -> Any:
    v = getattr(lg, champ)
    return v if v not in ("", None) else None


CODES_REQUIS = {"reference": "OPERATION_REFERENCE_OBLIGATOIRE", "montant": "MONTANT_OBLIGATOIRE",
                "devise": "DEVISE_OBLIGATOIRE"}


def appliquer_regle(lg: Ligne, ex: Exigences) -> None:
    """Champs obligatoires et contrôle spécifique du motif (les erreurs de format sont déjà posées)."""
    deja = set(lg.erreurs_champs)
    for champ in sorted(ex.champs_requis, key=list(CHAMPS_OPERATION).index):
        # Client vide = client principal ou titulaire du compte : contrôlé après rapprochement (``resoudre``).
        if champ != "client_racine" and champ not in deja and _valeur(lg, champ) is None:
            lg.ajouter_erreur(CODES_REQUIS.get(champ, "CHAMP_REQUIS"),
                              f"{CHAMPS_OPERATION[champ].lower()} obligatoire pour ce motif", champ)
    attendue = ex.nature_attendue
    if attendue and lg.nature_mouvement and lg.nature_mouvement != attendue:
        lg.ajouter_erreur("NATURE_INCOHERENTE", f"le motif concerne une opération au {attendue.lower()}, "
                          f"la ligne indique un {lg.nature_mouvement.lower()}", "nature_mouvement")
    controle = ex.controle
    if controle == "PARTIELLE" and lg.montant is not None and lg.montant_conteste is not None:
        if lg.montant_conteste >= lg.montant and "montant_conteste" not in lg.erreurs_champs:
            lg.ajouter_erreur("EXTOURNE_NON_PARTIELLE", "extourne partielle : le montant à extourner doit être "
                              "inférieur au montant initial (sinon, motif d'extourne totale)", "montant_conteste")
        lg.avertissements.append("solde encore extournable non vérifié (aucun accès ORION) : à contrôler par le "
                                 "service")
    elif controle == "MONTANT_INCORRECT" and lg.montant is not None and lg.montant_attendu is not None:
        if lg.montant_attendu == lg.montant:
            lg.ajouter_erreur("MONTANT_ATTENDU_IDENTIQUE", "le montant attendu est égal au montant comptabilisé",
                              "montant_attendu")
        elif lg.montant_conteste is not None and lg.montant_conteste != abs(lg.montant - lg.montant_attendu):
            lg.ajouter_erreur("ECART_INCOHERENT", f"montant à régulariser {lg.montant_conteste} ≠ écart "
                              f"{abs(lg.montant - lg.montant_attendu)} entre montant comptabilisé et attendu",
                              "montant_conteste")
    elif controle == "MAUVAIS_COMPTE" and lg.compte_reference and lg.compte_attendu \
            and lg.compte_reference.casefold() == lg.compte_attendu.casefold():
        lg.ajouter_erreur("COMPTE_ATTENDU_IDENTIQUE", "le compte attendu est identique au compte mouvementé",
                          "compte_attendu")
    elif controle == "ANNULATION":
        lg.avertissements.append("annulation : vérifier que l'opération n'a pas été comptabilisée (sinon, extourne)")


def controler(lignes: list[Ligne], existantes: list[Ligne] | None = None) -> None:
    """Doublons : une ligne strictement identique est une erreur ; une référence répétée dans un
    autre contexte (compte, date, montant) n'est qu'un avertissement."""
    vues: dict[tuple, int] = {}
    refs: dict[str, int] = {}
    contextes: dict[tuple, int] = {}

    def contexte(lg: Ligne) -> tuple | None:
        if not (lg.compte_reference and lg.date_operation and lg.montant is not None):
            return None
        return (lg.compte_reference.casefold(), lg.date_operation, lg.montant, lg.devise)

    for e in existantes or []:
        vues.setdefault(e.cle_identique(), 0)
        if e.reference:
            refs.setdefault(e.reference.casefold(), 0)
        if (c := contexte(e)) is not None:
            contextes.setdefault(c, 0)
    for lg in lignes:
        cle = lg.cle_identique()
        if cle in vues and (lg.reference or lg.compte_reference or lg.montant is not None):
            origine = "déjà présente dans le dossier" if vues[cle] == 0 else f"identique à la ligne {vues[cle]}"
            lg.ajouter_erreur("OPERATION_DOUBLON", f"opération « {lg.reference or '—'} » {origine}")
            continue
        vues[cle] = lg.rang
        if lg.reference:
            ref = lg.reference.casefold()
            if ref in refs:
                ou = "dans le dossier" if refs[ref] == 0 else f"ligne {refs[ref]}"
                lg.avertissements.append(f"référence « {lg.reference} » déjà utilisée ({ou}) dans un autre contexte")
            else:
                refs[ref] = lg.rang
        if (c := contexte(lg)) is not None:
            if c in contextes:
                ou = "une opération du dossier" if contextes[c] == 0 else f"la ligne {contextes[c]}"
                lg.avertissements.append(f"doublon potentiel : même compte, date et montant que {ou}")
            else:
                contextes[c] = lg.rang


async def resoudre(db: AsyncSession, lignes: list[Ligne], racine_principale: str | None,
                   comptes_dossier: dict[str, str | None] | None = None, ex: Exigences | None = None) -> None:
    """Rapproche clients et comptes de la base clientèle ; complète le client par défaut.

    Client vide → titulaire du compte s'il est connu, sinon client principal du dossier.
    ``comptes_dossier`` : comptes déjà rattachés au dossier (compte → racine du client)."""
    racines = {lg.client_racine for lg in lignes if lg.client_racine}
    if racine_principale:
        racines.add(racine_principale)
    comptes = {lg.compte_reference for lg in lignes if lg.compte_reference}
    titulaires: dict[str, str] = {}
    if comptes:
        titulaires = {c: r for c, r in (await db.execute(
            select(ClienteleCompte.compte, ClienteleCompte.racine_client)
            .where(ClienteleCompte.compte.in_(comptes)))).all()}
        racines |= set(titulaires.values())
    clients: dict[str, ClienteleClient] = {}
    if racines:
        clients = {c.racine_client: c for c in (await db.scalars(
            select(ClienteleClient).where(ClienteleClient.racine_client.in_(racines)))).all()}
    rattachement = dict(comptes_dossier or {})
    for lg in lignes:
        titulaire = titulaires.get(lg.compte_reference or "")
        if lg.client_racine and titulaire and titulaire != lg.client_racine:
            lg.ajouter_erreur("COMPTE_AUTRE_CLIENT", f"le compte {lg.compte_reference} appartient au client "
                              f"{titulaire}, pas à {lg.client_racine}", "compte_reference")
            continue
        if not lg.client_racine:
            if titulaire:
                lg.client_racine = titulaire
                if titulaire != racine_principale:
                    lg.avertissements.append(f"rattachée au client {titulaire}, titulaire du compte")
            else:
                lg.client_racine = racine_principale
        if lg.compte_reference:
            deja = rattachement.get(lg.compte_reference, "∅")
            if deja != "∅" and deja != lg.client_racine:
                lg.ajouter_erreur("COMPTE_AUTRE_CLIENT", f"le compte {lg.compte_reference} est déjà rattaché à un "
                                  "autre client dans ce dossier", "compte_reference")
                continue
            rattachement[lg.compte_reference] = lg.client_racine
            lg.statut_compte = "VERIFIE" if titulaire else "A_VERIFIER"
            if not titulaire:
                lg.avertissements.append(f"compte {lg.compte_reference} absent de la base clientèle : à vérifier")
        else:
            lg.statut_compte = "A_RENSEIGNER"
        client = clients.get(lg.client_racine or "")
        if lg.client_racine is None:
            lg.statut_client = "A_RENSEIGNER"
            if ex is not None and ex.requis("client_racine"):
                lg.ajouter_erreur("CHAMP_REQUIS", "client obligatoire pour ce motif", "client_racine")
        elif client is not None:
            lg.statut_client, lg.client_nom = "VERIFIE", nom_client(client)
        else:
            lg.statut_client = "A_VERIFIER"
            lg.avertissements.append(f"client {lg.client_racine} absent de la base clientèle : à vérifier")


def nom_client(c: ClienteleClient) -> str:
    return propre(f"{c.prenoms or ''} {c.raison_sociale}") if c.prenoms else c.raison_sociale


def premiere_erreur(lignes: list[Ligne], prefixe: str = "Opération") -> None:
    for lg in lignes:
        if lg.erreurs:
            code, message = lg.erreurs[0]
            raise erreur(f"{prefixe} {lg.rang} : {message}", code)


def lire_saisie(brutes: list[dict] | None, ex: Exigences) -> list[Ligne]:
    """Saisie manuelle : toutes les lignes contrôlées (format + règle du motif), sans lever d'erreur."""
    brutes = brutes or []
    if len(brutes) > C.MAX_OPERATIONS:
        raise erreur(f"{C.MAX_OPERATIONS} opérations au plus par réclamation", "TROP_D_OPERATIONS")
    return [lire(b, rang, ex, devise_defaut=C.DEVISE) for rang, b in enumerate(brutes, start=1)]


def normaliser(brutes: list[dict] | None, ex: Exigences | None = None) -> list[Ligne]:
    """Saisie manuelle : contrôles de format, première erreur levée (voir ``preparer`` pour la suite)."""
    lignes = lire_saisie(brutes, ex or Exigences())
    premiere_erreur(lignes)
    return lignes


async def preparer(db: AsyncSession, lignes: list[Ligne], racine_principale: str | None,
                   comptes_dossier: dict[str, str | None] | None = None,
                   existantes: list[Ligne] | None = None, ex: Exigences | None = None) -> list[Ligne]:
    """Rapprochement base puis doublons ; saisie manuelle : la première erreur est levée."""
    await resoudre(db, lignes, racine_principale, comptes_dossier, ex)
    premiere_erreur(lignes)
    controler(lignes, existantes)
    premiere_erreur(lignes)
    return lignes


# ------------------------------------------------------------------ persistance
async def participants(db: AsyncSession, rid: uuid.UUID) -> list[ReclamationParticipant]:
    return list((await db.scalars(select(ReclamationParticipant).where(
        ReclamationParticipant.reclamation_id == rid).order_by(
        ReclamationParticipant.ordre, ReclamationParticipant.created_at))).all())


async def comptes(db: AsyncSession, rid: uuid.UUID) -> list[ReclamationCompte]:
    return list((await db.scalars(select(ReclamationCompte).where(
        ReclamationCompte.reclamation_id == rid).order_by(ReclamationCompte.compte_reference))).all())


async def comptes_du_dossier(db: AsyncSession, rid: uuid.UUID) -> dict[str, str | None]:
    """Compte → racine du client auquel il est rattaché dans le dossier."""
    rows = (await db.execute(
        select(ReclamationCompte.compte_reference, ReclamationParticipant.client_racine)
        .outerjoin(ReclamationParticipant, ReclamationParticipant.id == ReclamationCompte.participant_id)
        .where(ReclamationCompte.reclamation_id == rid))).all()
    return {c: r for c, r in rows}


async def synchroniser_principal(db: AsyncSession, r: Reclamation, user_id: uuid.UUID | None) -> ReclamationParticipant:
    """Client principal = client saisi sur le dossier (identifié ou non) ; son compte saisi est rattaché."""
    liste = await participants(db, r.id)
    principal = next((p for p in liste if p.role == "PRINCIPAL"), None)
    statut = "A_RENSEIGNER" if not r.client_racine else "VERIFIE" if await db.scalar(
        select(ClienteleClient.id).where(ClienteleClient.racine_client == r.client_racine)) else "A_VERIFIER"
    homonyme = next((p for p in liste if p.role == "ASSOCIE" and r.client_racine
                     and p.client_racine == r.client_racine), None)
    if principal is None:
        principal = ReclamationParticipant(reclamation_id=r.id, ordre=1, role="PRINCIPAL", created_by_id=user_id,
                                           client_racine=None, statut_identification=statut)
        db.add(principal)
        await db.flush()
    if homonyme is not None:
        # Le client associé devient le principal : ses opérations et comptes le suivent.
        for o in (await db.scalars(select(ReclamationOperation).where(
                ReclamationOperation.participant_id == homonyme.id))).all():
            o.participant_id = principal.id
        for c in (await db.scalars(select(ReclamationCompte).where(
                ReclamationCompte.participant_id == homonyme.id))).all():
            c.participant_id = principal.id
        await db.flush()
        await db.delete(homonyme)
        await db.flush()
    principal.client_racine, principal.client_nom = r.client_racine, r.client_nom
    principal.client_categorie, principal.statut_identification = r.client_categorie, statut
    if r.compte_reference:
        compte = await db.scalar(select(ReclamationCompte).where(
            ReclamationCompte.reclamation_id == r.id, ReclamationCompte.compte_reference == r.compte_reference))
        if compte is None:
            connu = await db.scalar(select(ClienteleCompte.compte).where(ClienteleCompte.compte == r.compte_reference))
            db.add(ReclamationCompte(reclamation_id=r.id, participant_id=principal.id,
                                     compte_reference=r.compte_reference, created_by_id=user_id,
                                     statut_verification="VERIFIE" if connu else "A_VERIFIER"))
    await db.flush()
    return principal


async def ecrire(db: AsyncSession, r: Reclamation, lignes: list[Ligne], user_id: uuid.UUID | None, *,
                 import_id: uuid.UUID | None = None) -> None:
    """Ajoute les opérations (lignes déjà contrôlées et résolues) après celles du dossier."""
    principal = await synchroniser_principal(db, r, user_id)
    par_racine = {p.client_racine: p for p in await participants(db, r.id) if p.client_racine}
    par_compte = {c.compte_reference: c for c in await comptes(db, r.id)}
    ordre = await db.scalar(select(func.coalesce(func.max(ReclamationOperation.ordre), 0)).where(
        ReclamationOperation.reclamation_id == r.id)) or 0
    for lg in lignes:
        participant = principal
        if lg.client_racine and lg.client_racine != principal.client_racine:
            participant = par_racine.get(lg.client_racine)
            if participant is None:
                participant = ReclamationParticipant(
                    reclamation_id=r.id, ordre=len(par_racine) + 2, role="ASSOCIE", client_racine=lg.client_racine,
                    client_nom=lg.client_nom, statut_identification=lg.statut_client or "A_VERIFIER",
                    created_by_id=user_id)
                db.add(participant)
                await db.flush()
                par_racine[lg.client_racine] = participant
        compte = None
        if lg.compte_reference:
            compte = par_compte.get(lg.compte_reference)
            if compte is None:
                compte = ReclamationCompte(reclamation_id=r.id, participant_id=participant.id,
                                           compte_reference=lg.compte_reference, created_by_id=user_id,
                                           statut_verification="VERIFIE" if lg.statut_compte == "VERIFIE"
                                           else "A_VERIFIER")
                db.add(compte)
                await db.flush()
                par_compte[lg.compte_reference] = compte
            else:
                compte.participant_id = participant.id
        ordre += 1
        db.add(ReclamationOperation(
            reclamation_id=r.id, ordre=ordre, reference=lg.reference or None, montant=lg.montant, devise=lg.devise,
            participant_id=participant.id, compte_id=compte.id if compte else None,
            date_operation=lg.date_operation, montant_conteste=lg.montant_conteste, motif_detail=lg.motif_detail,
            nature_mouvement=lg.nature_mouvement, montant_attendu=lg.montant_attendu,
            compte_attendu=lg.compte_attendu, role_operation=lg.role_operation, commentaire=lg.commentaire,
            import_id=import_id, ligne_import=lg.rang if import_id else None, created_by_id=user_id))
    await db.flush()


async def nettoyer(db: AsyncSession, r: Reclamation) -> None:
    """Retire les comptes et clients associés qui ne portent plus aucune opération."""
    utilises_c = set((await db.scalars(select(ReclamationOperation.compte_id).where(
        ReclamationOperation.reclamation_id == r.id, ReclamationOperation.compte_id.is_not(None)))).all())
    for c in await comptes(db, r.id):
        if c.id not in utilises_c and c.compte_reference != r.compte_reference:
            await db.delete(c)
    await db.flush()
    utilises_p = set((await db.scalars(select(ReclamationOperation.participant_id).where(
        ReclamationOperation.reclamation_id == r.id))).all())
    utilises_p |= {c.participant_id for c in await comptes(db, r.id)}
    for p in await participants(db, r.id):
        if p.role == "ASSOCIE" and p.id not in utilises_p:
            await db.delete(p)
    await db.flush()


async def regroupement_autorise(db: AsyncSession) -> bool:
    p = await db.get(ReclamationParametre, C.PARAM_MULTI_CLIENTS)
    return True if p is None else bool(p.valeur)


async def verifier_regroupement(db: AsyncSession, r: Reclamation, justification: str | None,
                                 racines: set[str] | None = None) -> bool:
    """Plusieurs clients identifiés dans le dossier : autorisé par la banque et justifié. Renvoie « multi ».

    ``racines`` : clients prévus, pour contrôler avant toute écriture ; sinon ceux du dossier."""
    if racines is None:
        racines = {p.client_racine for p in await participants(db, r.id) if p.client_racine}
    if len(racines) <= 1:
        return False
    if not await regroupement_autorise(db):
        raise conflit("La banque n'autorise pas le regroupement de plusieurs clients dans un même dossier : "
                      "créez un dossier par client", "REGROUPEMENT_NON_AUTORISE")
    justification = texte_long(justification) or r.justification_regroupement
    if not justification:
        raise erreur(f"Les opérations concernent {len(racines)} clients : justifiez le regroupement dans un "
                     "même dossier", "JUSTIFICATION_REGROUPEMENT_OBLIGATOIRE")
    r.justification_regroupement = justification
    return True


async def lister(db: AsyncSession, reclamation_id: uuid.UUID) -> list[ReclamationOperation]:
    return list((await db.scalars(select(ReclamationOperation).where(
        ReclamationOperation.reclamation_id == reclamation_id).order_by(
        ReclamationOperation.ordre, ReclamationOperation.created_at))).all())


def lignes_existantes(ops: list[ReclamationOperation], par_p: dict, par_c: dict) -> list[Ligne]:
    """Opérations enregistrées, sous forme comparable aux lignes à ajouter (détection des doublons)."""
    return [Ligne(rang=0, reference=o.reference or "", montant=o.montant, montant_conteste=o.montant_conteste,
                  date_operation=o.date_operation,
                  client_racine=par_p[o.participant_id].client_racine if o.participant_id in par_p else None,
                  compte_reference=par_c[o.compte_id].compte_reference if o.compte_id in par_c else None,
                  motif_detail=o.motif_detail, nature_mouvement=o.nature_mouvement, devise=o.devise,
                  montant_attendu=o.montant_attendu, compte_attendu=o.compte_attendu,
                  role_operation=o.role_operation, commentaire=o.commentaire)
            for o in ops]


def total(montants: list[Decimal | None]) -> Decimal | None:
    connus = [m for m in montants if m is not None]
    return sum(connus, Decimal("0")) if connus else None


def conteste(o: ReclamationOperation | Ligne) -> Decimal | None:
    return o.montant_conteste if o.montant_conteste is not None else o.montant


def par_devise(items: list[ReclamationOperation | Ligne]) -> list[dict]:
    """Totaux par devise : jamais de somme entre devises différentes (aucune conversion n'est prévue)."""
    groupes: dict[str | None, list] = {}
    for o in items:
        groupes.setdefault(o.devise, []).append(o)
    return [{"devise": d, "nb": len(liste), "montant": montant_str(total([o.montant for o in liste])),
             "montant_conteste": montant_str(total([conteste(o) for o in liste]))}
            for d, liste in sorted(groupes.items(), key=lambda x: (x[0] != C.DEVISE, x[0] or "~"))]


def montant_unique(items: list[ReclamationOperation | Ligne], valeur=None) -> tuple[Decimal | None, str | None]:
    """(total, devise) si toutes les opérations chiffrées sont dans la même devise, sinon (None, None)."""
    valeur = valeur or (lambda o: o.montant)
    chiffrees = [o for o in items if valeur(o) is not None]
    devises = {o.devise for o in chiffrees}
    if len(devises) > 1:
        return None, None
    return total([valeur(o) for o in chiffrees]), (next(iter(devises)) if devises else C.DEVISE)


async def resumes(db: AsyncSession, ids) -> dict[uuid.UUID, tuple[int, Decimal | None, str | None]]:
    """Nombre d'opérations, montant total et devise par dossier (montant ``None`` si devises mélangées).

    ``ids`` : liste ou sous-requête d'identifiants."""
    if isinstance(ids, list) and not ids:
        return {}
    rows = (await db.execute(
        select(ReclamationOperation.reclamation_id, ReclamationOperation.devise, func.count(),
               func.sum(ReclamationOperation.montant))
        .where(ReclamationOperation.reclamation_id.in_(ids))
        .group_by(ReclamationOperation.reclamation_id, ReclamationOperation.devise))).all()
    groupes: dict[uuid.UUID, list[tuple[str | None, int, Decimal | None]]] = {}
    for rid, devise, n, somme in rows:
        groupes.setdefault(rid, []).append((devise, n, somme))
    out: dict[uuid.UUID, tuple[int, Decimal | None, str | None]] = {}
    for rid, liste in groupes.items():
        nb = sum(n for _d, n, _s in liste)
        chiffrees = [(d, s) for d, _n, s in liste if s is not None]
        if len(chiffrees) > 1:
            out[rid] = (nb, None, None)
        elif chiffrees:
            out[rid] = (nb, chiffrees[0][1], chiffrees[0][0])
        else:
            out[rid] = (nb, None, C.DEVISE)
    return out


def recapitulatif(lignes: list[Ligne], ex: Exigences, *, nb_pieces: int = 0, racine_principale: str | None = None,
                  manques: list[str] | None = None) -> dict:
    """Résumé calculé sur les lignes réellement saisies / importées (vérification avant enregistrement)."""
    valides = [lg for lg in lignes if not lg.erreurs]
    clients = {lg.client_racine for lg in lignes if lg.client_racine} | ({racine_principale} if racine_principale
                                                                          else set())
    montant, devise = montant_unique(valides)
    conteste_total, _ = montant_unique(valides, conteste)
    manques = manques if manques is not None else controles_dossier(ex, lignes, nb_pieces)
    return {
        "nb_operations": len(lignes), "nb_valides": len(valides),
        "nb_clients": len(clients), "nb_comptes": len({lg.compte_reference for lg in lignes if lg.compte_reference}),
        "par_devise": par_devise(valides), "devises_multiples": len({lg.devise for lg in valides
                                                                     if lg.devise}) > 1,
        "montant_total": montant_str(montant), "montant_conteste_total": montant_str(conteste_total),
        "devise": devise,
        "nb_erreurs": sum(len(lg.erreurs) for lg in lignes), "nb_lignes_en_erreur": len(lignes) - len(valides),
        "nb_avertissements": sum(len(lg.avertissements) for lg in lignes), "nb_pieces": nb_pieces,
        "a_completer_avant_transmission": manques,
        "regle": ex.to_dict(),
    }


def montant_str(m: Decimal | None) -> str | None:
    return str(m) if m is not None else None


# ------------------------------------------------------------------ sérialisation
def masquer_racine(racine: str | None) -> str | None:
    return f"****{racine[-2:]}" if racine else None


def masquer_compte(compte: str) -> str:
    return f"••••{compte[-4:]}" if len(compte) > 4 else "••••"


def en_dict(o: ReclamationOperation, par_p: dict, par_c: dict, masques: set[uuid.UUID]) -> dict:
    p = par_p.get(o.participant_id)
    c = par_c.get(o.compte_id)
    masque = bool(p and p.id in masques)
    return {
        "id": str(o.id), "ordre": o.ordre, "reference": o.reference,
        "montant": _s(o.montant), "montant_conteste": _s(o.montant_conteste),
        "montant_conteste_effectif": _s(conteste(o)), "devise": o.devise,
        "date_operation": o.date_operation.isoformat() if o.date_operation else None,
        "motif_detail": o.motif_detail, "nature_mouvement": o.nature_mouvement,
        "montant_attendu": _s(o.montant_attendu),
        "compte_attendu": (masquer_compte(o.compte_attendu) if masque else o.compte_attendu) if o.compte_attendu
        else None,
        "role_operation": o.role_operation, "commentaire": o.commentaire,
        "participant_id": str(o.participant_id) if o.participant_id else None,
        "compte_id": str(o.compte_id) if o.compte_id else None,
        "client_racine": (masquer_racine(p.client_racine) if masque else p.client_racine) if p else None,
        "compte_reference": (masquer_compte(c.compte_reference) if masque else c.compte_reference) if c else None,
        "statut_compte": c.statut_verification if c else "A_RENSEIGNER",
        "import_id": str(o.import_id) if o.import_id else None, "ligne_import": o.ligne_import,
    }


def participant_dict(p: ReclamationParticipant, ops: list[ReclamationOperation], masque: bool) -> dict:
    siens = [o for o in ops if o.participant_id == p.id]
    return {
        "id": str(p.id), "role": p.role, "role_libelle": C.ROLE_PARTICIPANT_LIBELLES.get(p.role),
        "racine": masquer_racine(p.client_racine) if masque else p.client_racine,
        "nom": (f"Client associé n° {p.ordre}" if masque else p.client_nom),
        "categorie": None if masque else p.client_categorie,
        "statut": p.statut_identification,
        "statut_libelle": C.STATUT_IDENTIFICATION_LIBELLES.get(p.statut_identification),
        "masque": masque, "nb_operations": len(siens), **_sous_totaux(siens),
    }


def _sous_totaux(siens: list[ReclamationOperation]) -> dict:
    montant, devise = montant_unique(siens)
    conteste_total, _ = montant_unique(siens, conteste)
    return {"montant_total": _s(montant), "montant_conteste_total": _s(conteste_total), "devise": devise,
            "par_devise": par_devise(siens)}


def compte_dict(c: ReclamationCompte, ops: list[ReclamationOperation], masque: bool) -> dict:
    siens = [o for o in ops if o.compte_id == c.id]
    return {
        "id": str(c.id), "participant_id": str(c.participant_id) if c.participant_id else None,
        "compte_reference": masquer_compte(c.compte_reference) if masque else c.compte_reference,
        "statut": c.statut_verification, "statut_libelle": C.STATUT_IDENTIFICATION_LIBELLES.get(c.statut_verification),
        "masque": masque, "nb_operations": len(siens), **_sous_totaux(siens),
    }
