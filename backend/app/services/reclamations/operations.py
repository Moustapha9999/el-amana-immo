"""Opérations d'un dossier, clients participants et comptes concernés.

Modèle : un dossier → 1 client principal (+ clients associés, cas exceptionnel justifié) → comptes
→ opérations. Chaque opération porte sa référence, son montant, et quand ils sont connus son compte
et son client. Un client ou un compte absent de la base clientèle reste « à vérifier » ; une
information non fournie reste « à renseigner » : rien n'est présumé vérifié.

Contrôles partagés par la saisie manuelle et l'import Excel :
- erreurs (bloquantes) : référence ou montant absent, montant invalide, contesté > montant, date
  future, racine mal formée, compte rattaché à un autre client, ligne strictement identique ;
- avertissements : référence répétée dans un autre contexte, client / compte à vérifier ou à renseigner.

Les totaux restent calculés par dossier (``GROUP BY reclamation_id``) : un dossier à plusieurs
opérations compte pour **un** dossier, et chaque montant n'est additionné qu'une fois.
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
from app.services.reclamations import constantes as C
from app.services.reclamations.outils import conflit, erreur, maintenant, propre, texte_long

CENTIME = Decimal("0.01")
MONTANT_MAX = Decimal("9999999999999999.99")
OK, AVERTISSEMENT, ERREUR = "OK", "AVERTISSEMENT", "ERREUR"


@dataclass
class Ligne:
    """Opération en cours de contrôle. ``rang`` : position saisie, ou n° de ligne Excel."""

    rang: int
    reference: str = ""
    montant: Decimal | None = None
    montant_conteste: Decimal | None = None
    date_operation: date | None = None
    client_racine: str | None = None
    compte_reference: str | None = None
    motif_detail: str | None = None
    erreurs: list[tuple[str, str]] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    client_nom: str | None = None
    statut_client: str | None = None
    statut_compte: str | None = None

    @property
    def statut(self) -> str:
        return ERREUR if self.erreurs else AVERTISSEMENT if self.avertissements else OK

    def cle_identique(self) -> tuple:
        return (self.reference.casefold(), (self.compte_reference or "").casefold(), self.client_racine,
                self.date_operation, self.montant, self.montant_conteste)

    def brut(self) -> dict:
        return {"ligne": self.rang, "reference": self.reference, "montant": _s(self.montant),
                "montant_conteste": _s(self.montant_conteste),
                "date_operation": self.date_operation.isoformat() if self.date_operation else None,
                "client_racine": self.client_racine, "compte_reference": self.compte_reference,
                "motif_detail": self.motif_detail}

    def apercu(self) -> dict:
        return {**self.brut(), "client_nom": self.client_nom, "statut_client": self.statut_client,
                "statut_compte": self.statut_compte, "statut": self.statut,
                "erreurs": [m for _c, m in self.erreurs], "avertissements": self.avertissements}


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


def lire(brut: dict, rang: int) -> Ligne:
    """Contrôles propres à une ligne (format, présence, cohérence interne)."""
    lg = Ligne(rang=rang)
    reference = brut.get("reference")
    if isinstance(reference, float) and reference.is_integer():
        reference = int(reference)
    lg.reference = "" if _vide(reference) else propre(str(reference))
    if not lg.reference:
        lg.erreurs.append(("OPERATION_REFERENCE_OBLIGATOIRE", "la référence de l'opération est obligatoire"))
    elif len(lg.reference) > 120:
        lg.erreurs.append(("OPERATION_REFERENCE_INVALIDE", "référence trop longue (120 caractères)"))
    if _vide(brut.get("montant")):
        lg.erreurs.append(("MONTANT_OBLIGATOIRE", "le montant de l'opération est obligatoire"))
    else:
        try:
            lg.montant = _montant(brut["montant"])
        except ValueError as e:
            lg.erreurs.append(("MONTANT_INVALIDE", f"montant de l'opération : {e}"))
    if not _vide(brut.get("montant_conteste")):
        try:
            lg.montant_conteste = _montant(brut["montant_conteste"])
        except ValueError as e:
            lg.erreurs.append(("MONTANT_INVALIDE", f"montant contesté : {e}"))
        else:
            if lg.montant is not None and lg.montant_conteste > lg.montant:
                lg.erreurs.append(("MONTANT_CONTESTE_SUPERIEUR",
                                   "le montant contesté dépasse le montant de l'opération"))
            elif lg.montant_conteste == lg.montant:
                lg.montant_conteste = None
    if not _vide(brut.get("date_operation")):
        try:
            lg.date_operation = _date(brut["date_operation"])
        except ValueError as e:
            lg.erreurs.append(("DATE_INVALIDE", str(e)))
        else:
            if lg.date_operation > maintenant().date():
                lg.erreurs.append(("DATE_FUTURE", "la date de l'opération est dans le futur"))
    if not _vide(brut.get("client_racine")):
        racine = racine_texte(brut["client_racine"])
        if len(racine) == 6 and racine.isdigit():
            lg.client_racine = racine
        else:
            lg.erreurs.append(("RACINE_INVALIDE", f"identifiant client « {racine} » : 6 chiffres attendus"))
    if not _vide(brut.get("compte_reference")):
        compte = compte_texte(brut["compte_reference"])
        if len(compte) > 60:
            lg.erreurs.append(("COMPTE_INVALIDE", "référence de compte trop longue (60 caractères)"))
        else:
            lg.compte_reference = compte
    lg.motif_detail = texte_long(str(brut["motif_detail"])) if not _vide(brut.get("motif_detail")) else None
    return lg


def controler(lignes: list[Ligne], existantes: list[Ligne] | None = None) -> None:
    """Doublons : une ligne strictement identique est une erreur ; une référence répétée dans un
    autre contexte (compte, date, montant) n'est qu'un avertissement."""
    vues: dict[tuple, int] = {}
    refs: dict[str, int] = {}
    for e in existantes or []:
        vues.setdefault(e.cle_identique(), 0)
        refs.setdefault(e.reference.casefold(), 0)
    for lg in lignes:
        if not lg.reference:
            continue
        cle = lg.cle_identique()
        if cle in vues:
            origine = "déjà présente dans le dossier" if vues[cle] == 0 else f"identique à la ligne {vues[cle]}"
            lg.erreurs.append(("OPERATION_DOUBLON", f"opération « {lg.reference} » {origine}"))
            continue
        vues[cle] = lg.rang
        ref = lg.reference.casefold()
        if ref in refs:
            ou = "dans le dossier" if refs[ref] == 0 else f"ligne {refs[ref]}"
            lg.avertissements.append(f"référence « {lg.reference} » déjà utilisée ({ou}) dans un autre contexte")
        else:
            refs[ref] = lg.rang


async def resoudre(db: AsyncSession, lignes: list[Ligne], racine_principale: str | None,
                   comptes_dossier: dict[str, str | None] | None = None) -> None:
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
            lg.erreurs.append(("COMPTE_AUTRE_CLIENT",
                               f"le compte {lg.compte_reference} appartient au client {titulaire}, "
                               f"pas à {lg.client_racine}"))
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
                lg.erreurs.append(("COMPTE_AUTRE_CLIENT",
                                   f"le compte {lg.compte_reference} est déjà rattaché à un autre client "
                                   "dans ce dossier"))
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


def normaliser(brutes: list[dict] | None) -> list[Ligne]:
    """Saisie manuelle : contrôles de format, première erreur levée (voir ``preparer`` pour la suite)."""
    brutes = brutes or []
    if len(brutes) > C.MAX_OPERATIONS:
        raise erreur(f"{C.MAX_OPERATIONS} opérations au plus par réclamation", "TROP_D_OPERATIONS")
    lignes = [lire(b, rang) for rang, b in enumerate(brutes, start=1)]
    premiere_erreur(lignes)
    return lignes


async def preparer(db: AsyncSession, lignes: list[Ligne], racine_principale: str | None,
                   comptes_dossier: dict[str, str | None] | None = None,
                   existantes: list[Ligne] | None = None) -> list[Ligne]:
    """Rapprochement base puis doublons ; saisie manuelle : la première erreur est levée."""
    await resoudre(db, lignes, racine_principale, comptes_dossier)
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
            reclamation_id=r.id, ordre=ordre, reference=lg.reference, montant=lg.montant, devise=C.DEVISE,
            participant_id=participant.id, compte_id=compte.id if compte else None,
            date_operation=lg.date_operation, montant_conteste=lg.montant_conteste, motif_detail=lg.motif_detail,
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
    return [Ligne(rang=0, reference=o.reference, montant=o.montant, montant_conteste=o.montant_conteste,
                  date_operation=o.date_operation,
                  client_racine=par_p[o.participant_id].client_racine if o.participant_id in par_p else None,
                  compte_reference=par_c[o.compte_id].compte_reference if o.compte_id in par_c else None,
                  motif_detail=o.motif_detail)
            for o in ops]


def total(montants: list[Decimal | None]) -> Decimal | None:
    connus = [m for m in montants if m is not None]
    return sum(connus, Decimal("0")) if connus else None


def conteste(o: ReclamationOperation | Ligne) -> Decimal | None:
    return o.montant_conteste if o.montant_conteste is not None else o.montant


async def resumes(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, Decimal | None]]:
    """Nombre d'opérations et montant total par dossier."""
    if not ids:
        return {}
    rows = (await db.execute(
        select(ReclamationOperation.reclamation_id, func.count(), func.sum(ReclamationOperation.montant))
        .where(ReclamationOperation.reclamation_id.in_(ids))
        .group_by(ReclamationOperation.reclamation_id))).all()
    return {rid: (n, somme) for rid, n, somme in rows}


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
        "motif_detail": o.motif_detail,
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
        "masque": masque, "nb_operations": len(siens),
        "montant_total": _s(total([o.montant for o in siens])),
        "montant_conteste_total": _s(total([conteste(o) for o in siens])),
    }


def compte_dict(c: ReclamationCompte, ops: list[ReclamationOperation], masque: bool) -> dict:
    siens = [o for o in ops if o.compte_id == c.id]
    return {
        "id": str(c.id), "participant_id": str(c.participant_id) if c.participant_id else None,
        "compte_reference": masquer_compte(c.compte_reference) if masque else c.compte_reference,
        "statut": c.statut_verification, "statut_libelle": C.STATUT_IDENTIFICATION_LIBELLES.get(c.statut_verification),
        "masque": masque, "nb_operations": len(siens),
        "montant_total": _s(total([o.montant for o in siens])),
        "montant_conteste_total": _s(total([conteste(o) for o in siens])),
    }
