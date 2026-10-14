"""Réponse au client : brouillon → à valider → validée → envoyée (canal + date obligatoires)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReclamationReponse
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.circuit import _appliquer, _charger, _ouvert, _pieces_circuit, fiche
from app.services.reclamations.dossiers import Contexte, _date_passee, _ref_valide
from app.services.reclamations.notifier import destinataires_sr, notifier
from app.services.reclamations.outils import erreur, maintenant, propre, texte_long


async def _courante(db: AsyncSession, r) -> ReclamationReponse | None:
    _, _, _, courante, _ = await _pieces_circuit(db, r)
    return courante


async def enregistrer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.response.prepare")
    if r.statut not in {"REPONSE_A_PREPARER", "REOUVERTE"}:
        raise erreur("La réponse se rédige après un retour suffisant (ou un traitement interne)",
                     "ACTION_INVALIDE")
    contenu = texte_long(data.get("contenu"))
    if not contenu:
        raise erreur("Le texte de la réponse est obligatoire", "CHAMPS_OBLIGATOIRES")
    p = await _courante(db, r)
    if p is None or p.statut == "ENVOYEE":
        n = (await db.scalar(select(func.coalesce(func.max(ReclamationReponse.numero), 0)).where(
            ReclamationReponse.reclamation_id == r.id))) + 1
        p = ReclamationReponse(
            reclamation_id=r.id, numero=n, statut="BROUILLON", redige_par_id=s.user_id,
            objet=propre(data.get("objet")) or r.objet, contenu=contenu,
            resultat=data.get("resultat"),
        )
        db.add(p)
        await db.flush()
    elif p.statut not in {"BROUILLON", "A_VALIDER"}:
        raise erreur("Cette réponse n'est plus modifiable", "ACTION_INVALIDE")
    elif p.statut == "A_VALIDER":
        p.statut = "BROUILLON"
        p.objet = propre(data.get("objet")) or r.objet
        p.contenu = contenu
        p.resultat = data.get("resultat")
    else:
        p.objet = propre(data.get("objet")) or r.objet
        p.contenu = contenu
        p.resultat = data.get("resultat")
    p.redige_par_id = s.user_id
    p.revision += 1
    await _appliquer(db, s, r, statut="REPONSE_A_PREPARER", etape="REPONSE",
                     type_evenement="REPONSE_BROUILLON", commentaire=texte_long(data.get("motif")),
                     reponse_id=p.id)
    return await fiche(db, s, r)


async def soumettre(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.response.prepare")
    p = await _courante(db, r)
    if p is None or p.statut != "BROUILLON":
        raise erreur("Enregistrez un brouillon avant de le soumettre", "ACTION_INVALIDE")
    if not p.contenu:
        raise erreur("Le texte de la réponse est obligatoire", "CHAMPS_OBLIGATOIRES")
    p.statut = "A_VALIDER"
    p.soumis_le = maintenant()
    p.revision += 1
    dest = await destinataires_sr(db, await Contexte.charger(db))
    await _appliquer(db, s, r, statut="REPONSE_A_PREPARER", etape="REPONSE",
                     type_evenement="REPONSE_SOUMISE", reponse_id=p.id,
                     destinataires=dest, titre="Réponse à valider")
    return await fiche(db, s, r)


async def valider(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.response.validate")
    p = await _courante(db, r)
    if p is None or p.statut != "A_VALIDER":
        raise erreur("Aucune réponse en attente de validation", "ACTION_INVALIDE")
    p.statut = "VALIDEE"
    p.valide_par_id = s.user_id
    p.valide_le = maintenant()
    p.commentaire_validation = texte_long(data.get("commentaire") or data.get("motif"))
    p.revision += 1
    await _appliquer(db, s, r, statut="REPONSE_A_PREPARER", etape="REPONSE",
                     type_evenement="REPONSE_VALIDEE", commentaire=p.commentaire_validation, reponse_id=p.id)
    return await fiche(db, s, r)


async def renvoyer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.response.validate")
    p = await _courante(db, r)
    if p is None or p.statut != "A_VALIDER":
        raise erreur("Aucune réponse à renvoyer", "ACTION_INVALIDE")
    p.statut = "BROUILLON"
    p.commentaire_validation = texte_long(data.get("motif") or data.get("commentaire"))
    if not p.commentaire_validation:
        raise erreur("Indiquez pourquoi la réponse est renvoyée", "MOTIF_OBLIGATOIRE")
    p.revision += 1
    dest = {p.redige_par_id} if p.redige_par_id else set()
    await _appliquer(db, s, r, statut="REPONSE_A_PREPARER", etape="REPONSE",
                     type_evenement="REPONSE_RENVOYEE", commentaire=p.commentaire_validation, reponse_id=p.id,
                     destinataires=dest, titre="Réponse à retravailler")
    return await fiche(db, s, r)


async def envoyer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.response.send")
    p = await _courante(db, r)
    if p is None or p.statut != "VALIDEE":
        raise erreur("La réponse doit être validée avant l'envoi", "ACTION_INVALIDE")
    ctx = await Contexte.charger(db)
    canal = _ref_valide(ctx, data.get("canal_envoi_id"), "CANAL_REPONSE")
    if canal is None:
        raise erreur("Le canal d'envoi est obligatoire", "CANAL_OBLIGATOIRE")
    envoye = _date_passee(data.get("envoye_le") or maintenant(), "Date d'envoi")
    if envoye < r.date_premiere_reception:
        raise erreur("L'envoi ne peut pas précéder la première réception", "DATE_INCOHERENTE")
    p.statut = "ENVOYEE"
    p.canal_envoi_id = canal.id
    p.destinataire = propre(data.get("destinataire")) or r.client_nom
    p.envoye_le = envoye
    p.envoye_par_id = s.user_id
    p.reference_envoi = propre(data.get("reference_envoi")) or None
    p.revision += 1
    r.date_reponse_client = envoye
    if p.resultat:
        r.resultat = p.resultat
    await _appliquer(db, s, r, statut="REPONSE_ENVOYEE", etape="CLOTURE",
                     type_evenement="REPONSE_ENVOYEE", reponse_id=p.id,
                     donnees={"canal": canal.libelle, "destinataire": p.destinataire},
                     commentaire=texte_long(data.get("motif")))
    return await fiche(db, s, r)
