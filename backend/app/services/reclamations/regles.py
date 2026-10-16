"""Règles de saisie par motif et devises autorisées.

La règle d'un motif fixe les champs obligatoires de chaque opération, la nature attendue, un contrôle
spécifique (doublon, mauvais compte, montant incorrect, extourne partielle, annulation, correction),
l'exigence d'un justificatif et l'ouverture d'une régularisation après décision favorable. Sans règle
enregistrée, ``REGLE_PAR_DEFAUT`` s'applique. Les mêmes contrôles servent à la saisie manuelle, à
l'import Excel et à la vérification avant transmission : le frontend n'est qu'un confort.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.reclamations_regles import CHAMPS_OPERATION, CONTROLES, REGLE_PAR_DEFAUT
from app.models import ReclamationDocument, ReclamationParametre, ReclamationReferentiel, ReclamationRegleMotif
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.outils import auditer, erreur, iso, maintenant, propre, texte_long

PARAM_DEVISES = "devises_autorisees"
# Pièces qui satisfont l'exigence « justificatif » d'un motif.
CATEGORIES_JUSTIFICATIF = frozenset({"JUSTIFICATIF", "PIECE_CLIENT", "COURRIER", "JUSTIFICATIF_SERVICE", "ORIGINAL"})


@dataclass(frozen=True)
class Exigences:
    """Règle effective d'un dossier (motif) et devises acceptées."""

    regle: dict = field(default_factory=lambda: dict(REGLE_PAR_DEFAUT))
    devises: frozenset[str] = frozenset({C.DEVISE})
    motif_id: uuid.UUID | None = None
    statut_validation: str | None = None

    @property
    def champs_requis(self) -> frozenset[str]:
        return frozenset(self.regle.get("champs_requis") or ())

    def requis(self, champ: str) -> bool:
        return champ in self.champs_requis

    @property
    def controle(self) -> str | None:
        return self.regle.get("controle")

    @property
    def nature_attendue(self) -> str | None:
        return self.regle.get("nature_attendue")

    def to_dict(self) -> dict:
        return {
            "motif_id": str(self.motif_id) if self.motif_id else None,
            "personnalisee": self.statut_validation is not None,
            "statut_validation": self.statut_validation,
            "champs_requis": sorted(self.champs_requis),
            "operations_min": int(self.regle.get("operations_min") or 0),
            "nature_attendue": self.nature_attendue,
            "controle": self.controle,
            "controle_libelle": CONTROLES.get(self.controle or ""),
            "justificatif_requis": bool(self.regle.get("justificatif_requis")),
            "regularisation": bool(self.regle.get("regularisation")),
            "consigne": self.regle.get("consigne"),
            "devises": sorted(self.devises, key=lambda d: (d != C.DEVISE, d)),
        }


def normaliser_regle(brute: dict | None) -> dict:
    """Règle complète et valide (clés inconnues ignorées, valeurs hors liste refusées)."""
    r = {**REGLE_PAR_DEFAUT, **{k: v for k, v in (brute or {}).items() if k in REGLE_PAR_DEFAUT}}
    champs = [c for c in (r.get("champs_requis") or []) if c in CHAMPS_OPERATION]
    inconnus = set(r.get("champs_requis") or []) - set(CHAMPS_OPERATION)
    if inconnus:
        raise erreur(f"Champs inconnus : {', '.join(sorted(inconnus))}", "REGLE_INVALIDE")
    if r.get("nature_attendue") not in (None, "DEBIT", "CREDIT"):
        raise erreur("Nature attendue : DEBIT, CREDIT ou vide", "REGLE_INVALIDE")
    if r.get("controle") not in (None, *CONTROLES):
        raise erreur("Contrôle inconnu", "REGLE_INVALIDE")
    try:
        minimum = int(r.get("operations_min") or 0)
    except (TypeError, ValueError):
        raise erreur("Nombre minimal d'opérations invalide", "REGLE_INVALIDE") from None
    if not 0 <= minimum <= C.MAX_OPERATIONS:
        raise erreur("Nombre minimal d'opérations invalide", "REGLE_INVALIDE")
    if r.get("controle") == "DOUBLE":
        minimum = max(minimum, 2)
    return {
        "champs_requis": list(dict.fromkeys(champs)), "operations_min": minimum,
        "nature_attendue": r.get("nature_attendue"), "controle": r.get("controle"),
        "justificatif_requis": bool(r.get("justificatif_requis")), "regularisation": bool(r.get("regularisation")),
        "consigne": texte_long(r.get("consigne")),
    }


async def devises_autorisees(db: AsyncSession) -> frozenset[str]:
    p = await db.get(ReclamationParametre, PARAM_DEVISES)
    valeurs = p.valeur if p is not None and isinstance(p.valeur, list) else [C.DEVISE]
    return frozenset(str(v).upper() for v in valeurs if isinstance(v, str) and len(v) == 3) or frozenset({C.DEVISE})


async def exigences(db: AsyncSession, motif_id: uuid.UUID | None) -> Exigences:
    devises = await devises_autorisees(db)
    if motif_id is None:
        return Exigences(devises=devises)
    r = await db.scalar(select(ReclamationRegleMotif).where(ReclamationRegleMotif.motif_id == motif_id))
    if r is None:
        return Exigences(devises=devises, motif_id=motif_id)
    return Exigences(regle=normaliser_regle(r.regles), devises=devises, motif_id=motif_id,
                     statut_validation=r.statut_validation)


async def nb_justificatifs(db: AsyncSession, rid: uuid.UUID) -> int:
    from app.models import GedDocument

    return await db.scalar(select(func.count()).select_from(ReclamationDocument).join(
        GedDocument, GedDocument.id == ReclamationDocument.document_id).where(
        ReclamationDocument.reclamation_id == rid, GedDocument.deleted_at.is_(None),
        ReclamationDocument.categorie.in_(CATEGORIES_JUSTIFICATIF))) or 0


def controles_dossier(ex: Exigences, operations: list, nb_pieces: int) -> list[str]:
    """Conditions bloquantes avant transmission au service (le dossier peut être enregistré incomplet).

    ``operations`` : objets portant ``reference`` et ``role_operation`` (lignes ou opérations enregistrées)."""
    manques: list[str] = []
    minimum = int(ex.regle.get("operations_min") or 0)
    if len(operations) < minimum:
        manques.append(f"au moins {minimum} opération(s) exigée(s) pour ce motif ({len(operations)} saisie(s))")
    if ex.controle == "DOUBLE" and operations:
        roles = {getattr(o, "role_operation", None) for o in operations}
        if not {"INITIALE", "DOUBLON"} <= roles:
            manques.append("opération en double : indiquez l'opération initiale et l'opération en double")
    if ex.regle.get("justificatif_requis") and nb_pieces == 0:
        manques.append("justificatif obligatoire pour ce motif (onglet Documents)")
    return manques


# ------------------------------------------------------------------ paramétrage
def _regle_dict(m: ReclamationReferentiel, r: ReclamationRegleMotif | None, types: dict) -> dict:
    t = types.get(m.parent_id)
    regle = normaliser_regle(r.regles) if r else dict(REGLE_PAR_DEFAUT)
    return {
        "motif_id": str(m.id), "motif": m.libelle, "motif_code": m.code, "motif_actif": m.actif,
        "type_id": str(m.parent_id) if m.parent_id else None, "type": t.libelle if t else None,
        "personnalisee": r is not None, "statut_validation": r.statut_validation if r else None,
        "valide_le": iso(r.valide_le) if r else None, "updated_at": iso(r.updated_at) if r else None,
        **regle,
    }


async def lister(db: AsyncSession, type_id: uuid.UUID | None = None) -> dict:
    q = select(ReclamationReferentiel).where(ReclamationReferentiel.domaine == "MOTIF",
                                             ReclamationReferentiel.supprime_le.is_(None))
    if type_id:
        q = q.where(ReclamationReferentiel.parent_id == type_id)
    motifs = list((await db.scalars(q.order_by(ReclamationReferentiel.ordre, ReclamationReferentiel.libelle))).all())
    types = {t.id: t for t in (await db.scalars(select(ReclamationReferentiel).where(
        ReclamationReferentiel.domaine == "TYPE"))).all()}
    regles = {r.motif_id: r for r in (await db.scalars(select(ReclamationRegleMotif))).all()}
    return {
        "items": [_regle_dict(m, regles.get(m.id), types) for m in motifs],
        "champs": [{"code": k, "libelle": v} for k, v in CHAMPS_OPERATION.items()],
        "controles": [{"code": k, "libelle": v} for k, v in CONTROLES.items()],
        "defaut": dict(REGLE_PAR_DEFAUT),
        "devises": sorted(await devises_autorisees(db)),
    }


async def enregistrer(db: AsyncSession, s: ReclamationsScope, motif_id: uuid.UUID, data: dict) -> dict:
    s.exiger("reclamations.references.manage")
    m = await db.get(ReclamationReferentiel, motif_id)
    if m is None or m.domaine != "MOTIF" or m.supprime_le is not None:
        raise erreur("Motif introuvable", "NOT_FOUND", 404)
    regle = normaliser_regle(data)
    r = await db.scalar(select(ReclamationRegleMotif).where(ReclamationRegleMotif.motif_id == motif_id))
    avant = dict(r.regles) if r else None
    if r is None:
        r = ReclamationRegleMotif(motif_id=motif_id, regles=regle, statut_validation="PROPOSEE",
                                  created_by_id=s.user_id, updated_by_id=s.user_id)
        db.add(r)
    else:
        if r.regles != regle:
            r.statut_validation, r.valide_par_id, r.valide_le = "PROPOSEE", None, None
        r.regles, r.updated_by_id = regle, s.user_id
    await db.flush()
    await auditer(db, s, "reclamations.regle_motif.update", "reclamation_regle_motif", r.id,
                  before=avant, after={"motif": m.libelle, **regle})
    types = {m.parent_id: await db.get(ReclamationReferentiel, m.parent_id)} if m.parent_id else {}
    return _regle_dict(m, r, types)


async def valider(db: AsyncSession, s: ReclamationsScope, motif_id: uuid.UUID, statut: str) -> dict:
    s.exiger("reclamations.references.validate")
    r = await db.scalar(select(ReclamationRegleMotif).where(ReclamationRegleMotif.motif_id == motif_id))
    if r is None:
        raise erreur("Aucune règle enregistrée pour ce motif", "NOT_FOUND", 404)
    if statut not in ("VALIDEE", "PROPOSEE"):
        raise erreur("Statut de validation inconnu", "STATUT_INVALIDE")
    avant = r.statut_validation
    r.statut_validation = statut
    r.valide_par_id, r.valide_le = (s.user_id, maintenant()) if statut == "VALIDEE" else (None, None)
    await db.flush()
    m = await db.get(ReclamationReferentiel, motif_id)
    await auditer(db, s, "reclamations.regle_motif.validation", "reclamation_regle_motif", r.id,
                  before={"statut_validation": avant}, after={"statut_validation": statut, "motif": m.libelle})
    types = {m.parent_id: await db.get(ReclamationReferentiel, m.parent_id)} if m.parent_id else {}
    return _regle_dict(m, r, types)


async def modifier_devises(db: AsyncSession, s: ReclamationsScope, devises: list[str]) -> list[str]:
    s.exiger("reclamations.references.manage")
    propres = []
    for d in devises:
        code = propre(d).upper()
        if len(code) != 3 or not code.isalpha():
            raise erreur(f"Code devise « {d} » invalide (3 lettres ISO 4217)", "DEVISE_INVALIDE")
        if code not in propres:
            propres.append(code)
    if C.DEVISE not in propres:
        raise erreur(f"La devise de référence {C.DEVISE} ne peut pas être retirée", "DEVISE_REFERENCE")
    p = await db.get(ReclamationParametre, PARAM_DEVISES)
    avant = p.valeur if p else None
    if p is None:
        p = ReclamationParametre(cle=PARAM_DEVISES, valeur=propres,
                                 description="Devises acceptées sur les opérations (codes ISO 4217).")
        db.add(p)
    else:
        p.valeur = propres
    p.updated_by_id = s.user_id
    await db.flush()
    await auditer(db, s, "reclamations.parametre.update", "reclamation_parametre", None,
                  before={PARAM_DEVISES: avant}, after={PARAM_DEVISES: propres})
    return propres
