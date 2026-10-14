"""Réponse au client : information de la fiche, enregistrée par le SR à l'étape Clôture.

Une seule action : « réponse envoyée » (texte, canal, date d'envoi). Corriger une réponse
enregistre une nouvelle version ; la précédente est conservée (statut ``ANNULEE``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReclamationReponse
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.circuit import _appliquer, _charger, _ouvert, _pieces_circuit, fiche
from app.services.reclamations.dossiers import Contexte, _date_passee, _ref_valide
from app.services.reclamations.outils import conflit, erreur, maintenant, propre, texte_long


async def enregistrer_envoi(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.response.send")
    if r.statut != "A_CLOTURER":
        raise conflit("La réponse au client s'enregistre une fois le retour du service examiné", "ACTION_INVALIDE")
    contenu = texte_long(data.get("contenu"))
    if not contenu:
        raise erreur("Le texte de la réponse envoyée est obligatoire", "CHAMPS_OBLIGATOIRES")
    ctx = await Contexte.charger(db)
    canal = _ref_valide(ctx, data.get("canal_envoi_id"), "CANAL_REPONSE")
    if canal is None:
        raise erreur("Le canal d'envoi est obligatoire", "CANAL_OBLIGATOIRE")
    envoye = _date_passee(data.get("envoye_le") or maintenant(), "Date d'envoi")
    if envoye < r.date_premiere_reception:
        raise erreur("L'envoi ne peut pas précéder la réception de la réclamation", "DATE_INCOHERENTE")

    _, _, _, precedente, _ = await _pieces_circuit(db, r)
    if precedente is not None:
        precedente.statut = "ANNULEE"
        precedente.revision += 1
    n = (await db.scalar(select(func.coalesce(func.max(ReclamationReponse.numero), 0)).where(
        ReclamationReponse.reclamation_id == r.id))) + 1
    p = ReclamationReponse(
        reclamation_id=r.id, numero=n, statut="ENVOYEE", redige_par_id=s.user_id,
        objet=propre(data.get("objet")) or r.objet, contenu=contenu, resultat=data.get("resultat"),
        canal_envoi_id=canal.id, destinataire=propre(data.get("destinataire")) or r.client_nom,
        envoye_le=envoye, envoye_par_id=s.user_id, reference_envoi=propre(data.get("reference_envoi")) or None,
    )
    db.add(p)
    await db.flush()
    r.date_reponse_client = envoye
    if p.resultat:
        r.resultat = p.resultat
    await _appliquer(db, s, r, statut="A_CLOTURER", type_evenement="REPONSE_ENVOYEE", reponse_id=p.id,
                     donnees={"canal": canal.libelle, "destinataire": p.destinataire, "version": n,
                              "remplace": precedente.numero if precedente else None},
                     commentaire=texte_long(data.get("motif")))
    return await fiche(db, s, r, ctx)
