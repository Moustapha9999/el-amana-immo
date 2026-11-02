"""Mise à niveau des périodes de stock laissées par l'ancienne règle « une seule période ouverte ».

À lancer une fois, après la migration 20261102_mg_stock_periodes_02 :

- période OUVERTE dont le dernier événement est une REOUVERTURE (ancien code) → ROUVERTE ;
  l'instantané de référence est ajouté à cet événement, à condition qu'aucun mouvement
  n'ait été saisi depuis (sinon arrêt : l'instantané ne serait plus celui de la réouverture) ;
- période CLOTUREE dont le dernier événement est une CLOTURE_OFFICE (jamais clôturée par un
  utilisateur) → OUVERTE, avec un événement REOUVERTURE_OFFICE.

Simulation par défaut ; ``--appliquer`` pour écrire. Aucun mouvement ni solde n'est modifié.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.mg_stock import MgStockMouvement, MgStockPeriode, MgStockPeriodeEvenement
from app.services.mg_stock_events import audit_stock
from app.services.mg_stock_periodes import CLOTUREE, OUVERTE, ROUVERTE, MgStockPeriodeService

AUTEUR = "Mise à niveau BEA DIGITAL (réouverture de période)"


async def _dernier_evenement(db, periode: MgStockPeriode) -> MgStockPeriodeEvenement | None:
    return await db.scalar(
        select(MgStockPeriodeEvenement)
        .where(MgStockPeriodeEvenement.periode_id == periode.id, MgStockPeriodeEvenement.resultat == "SUCCES")
        .order_by(MgStockPeriodeEvenement.created_at.desc())
        .limit(1)
    )


async def main(appliquer: bool) -> int:
    async with AsyncSessionLocal() as db:
        svc = MgStockPeriodeService(db)
        await svc.verrouiller()
        periodes = list(
            (await db.execute(select(MgStockPeriode).order_by(MgStockPeriode.date_debut).with_for_update()))
            .scalars()
            .all()
        )
        a_rouvrir: list[tuple[MgStockPeriode, MgStockPeriodeEvenement]] = []
        a_ouvrir: list[MgStockPeriode] = []
        for p in periodes:
            evt = await _dernier_evenement(db, p)
            if evt is None:
                continue
            if p.statut == OUVERTE and evt.action == "REOUVERTURE":
                a_rouvrir.append((p, evt))
            elif p.statut == CLOTUREE and evt.action == "CLOTURE_OFFICE":
                a_ouvrir.append(p)

        deja = [p.libelle for p in periodes if p.statut == ROUVERTE]
        if len(a_rouvrir) + len(deja) > 1:
            print("ARRÊT : plusieurs périodes seraient rouvertes :", [p.libelle for p, _ in a_rouvrir] + deja)
            return 1
        for p, evt in a_rouvrir:
            depuis = await db.scalar(
                select(func.count()).select_from(MgStockMouvement).where(MgStockMouvement.created_at >= evt.created_at)
            )
            if depuis:
                print(f"ARRÊT : {depuis} mouvement(s) saisi(s) depuis la réouverture de {p.libelle}.")
                return 1

        for p, evt in a_rouvrir:
            print(f"{p.libelle} : OUVERTE → ROUVERTE (réouverture du {evt.created_at:%d/%m/%Y %H:%M}, motif « {evt.motif} »)")
        for p in a_ouvrir:
            print(f"{p.libelle} : CLOTUREE → OUVERTE (clôture d'office de l'ancienne règle annulée)")
        if not (a_rouvrir or a_ouvrir):
            print("Rien à mettre à niveau.")
            return 0
        if not appliquer:
            print("Simulation : relancer avec --appliquer pour écrire.")
            await db.rollback()
            return 0

        for p, evt in a_rouvrir:
            evt.details = {**(evt.details or {}), "instantane": await svc.instantane(p), "instantane_ajoute_par": AUTEUR}
            p.statut = ROUVERTE
            await audit_stock(db, None, "mise_a_niveau_periode", "mg_stock_periode", p.id,
                              before={"statut": OUVERTE}, after={"statut": ROUVERTE, "auteur": AUTEUR})
        for p in a_ouvrir:
            evt = await svc._evenement(
                p,
                "REOUVERTURE_OFFICE",
                None,
                statut_avant=CLOTUREE,
                statut_apres=OUVERTE,
                motif="Annulation de la clôture d'office imposée par l'ancienne règle (une seule période ouverte)",
                details={"auteur": AUTEUR},
            )
            evt.user_nom = AUTEUR
            p.statut = OUVERTE
            p.nb_reouvertures = (p.nb_reouvertures or 0) + 1
            await audit_stock(db, None, "mise_a_niveau_periode", "mg_stock_periode", p.id,
                              before={"statut": CLOTUREE}, after={"statut": OUVERTE, "auteur": AUTEUR})
        await db.commit()
        print("Mise à niveau appliquée.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--appliquer" in sys.argv)))
