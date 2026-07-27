"""Clôture d'exercice — snapshot Archives N + ouverture N+1 (soldes 142/148, sans 68)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ValidationError
from app.data.el_amana_referentiel import NATURE_IMMO_CODES_OFFICIELS, TYPES_IMMOBILISATION_EL_AMANA
from app.models import (
    Agence,
    Amortissement,
    ArchiveDossier,
    ArchiveFichier,
    ArchiveLigne,
    Immobilisation,
    User,
)
from app.services.archive_service import KIND_CLOTURE, nature_label
from app.services.bank_immo_import import PERIODE_ARRETE, PERIODE_ARRETE_ANNUELLE
from app.services.recap_amortissement import (
    _dotations_par_immo,
    _historique_banque_par_immo,
    _is_import_banque,
    _mouvements_immo,
    _q,
    _zero,
)
from app.storage.local_storage import LocalStorageService

# Réexport pour les tests / API qui importaient depuis ce module
__all__ = ["KIND_CLOTURE", "ExerciceClotureService", "build_cloture_xlsx", "periode_ouverture"]

NATURE_BY_CODE: dict[str, dict] = {str(t["code"]): t for t in TYPES_IMMOBILISATION_EL_AMANA}


@dataclass
class ClotureResult:
    annee: int
    natures_creees: int
    lignes: int
    ouvertures_seed: int
    message: str
    dossier_id: UUID


def periode_ouverture(annee_cloture: int) -> str:
    """Période de report 148 fin N → ouverture N+1 (ex. 2026-12)."""
    return f"{annee_cloture}-12"


def _is_report_immo(immo: Immobilisation) -> bool:
    meta = getattr(immo, "metadata_json", None) or {}
    if isinstance(meta, dict):
        bank = meta.get("bank") or {}
        if isinstance(bank, dict) and bank.get("is_report"):
            return True
        if meta.get("is_report"):
            return True
    designation = (immo.designation or "").strip().upper()
    return designation.startswith("REPORT")


def _bank_snapshot_amounts(immo: Immobilisation) -> dict[str, Decimal] | None:
    """Montants Excel (Fin Exr.Précé / Dotation / Fin) stockés à l'import banque.

    Snapshot archives : colonnes Excel telles quelles.
    Ouverture N+1 (148) : cumul = ``amt_fin`` (fin d'exercice du tableau importé),
    car un import « stock historique » (ex. AAI clôturé) a amt_fin = solde 01/01/N+1.
    """
    if not _is_import_banque(immo):
        return None
    meta = getattr(immo, "metadata_json", None) or {}
    if not isinstance(meta, dict):
        return None
    bank = meta.get("bank")
    if not isinstance(bank, dict):
        return None
    try:
        amt_n1 = _q(Decimal(str(bank.get("amt_n1") or "0")))
        dotation = _q(Decimal(str(bank.get("dotation") or "0")))
        amt_fin = _q(Decimal(str(bank.get("amt_fin") or "0")))
        if bank.get("vnc") is not None:
            vnc = _q(Decimal(str(bank.get("vnc"))))
        else:
            vnc = _q(Decimal(immo.valeur_brute or 0) - amt_fin)
    except Exception:  # noqa: BLE001
        return None
    vb = _q(Decimal(immo.valeur_brute or 0))
    seed_mode = str(bank.get("seed_mode") or "")
    # stock_ouverture / défaut : amt_fin = cumul fin N → ouverture N+1
    # arrete_courant : amt_n1 = déjà le cumul d'ouverture N+1
    if seed_mode == "arrete_courant":
        cumul_ouv = amt_n1
    else:
        cumul_ouv = amt_fin
    return {
        "valeur_brute": vb,
        "amorts_cumules_n1": amt_n1,
        "cessions_annee": _zero(),
        "dotations_annee": dotation,
        "amorts_cumules_n": amt_fin,
        "vnc": vnc,
        "cumul_ouverture_n1": cumul_ouv,
        "vnc_ouverture_n1": _q(vb - cumul_ouv),
        "seed_mode": seed_mode or "stock_ouverture",
    }


def build_cloture_xlsx(
    *,
    annee: int,
    nature_code: str,
    lignes: list[dict],
) -> bytes:
    """Excel synthétique style tableau banque pour re-téléchargement."""
    nature = NATURE_BY_CODE.get(nature_code, {})
    famille = str(nature.get("famille") or nature_label(nature_code))
    compte = str(nature.get("compte_immobilisation") or "")

    wb = Workbook()
    ws = wb.active
    ws.title = (famille or "cloture")[:31]
    ws.append(["BEA"])
    ws.append([f"TABLEAU D'AMORTISSEMENT — CLÔTURE 31/12/{annee}"])
    ws.append([f"COMPTE N°: {compte}" if compte else f"NATURE: {nature_code}"])
    ws.append(
        [
            "Date",
            "Qté",
            "Désignation",
            "d'Acquisition MRU",
            "Taux",
            "Fin Exr.Précé",
            "Exer. En. C",
            "Fin Exercice",
            "Comptable",
            "AGENCE",
        ]
    )
    for row in lignes:
        d = row.get("date_acquisition")
        date_s = d.strftime("%d/%m/%Y") if isinstance(d, date) else ""
        ws.append(
            [
                date_s,
                row.get("quantite") or 1,
                row.get("designation") or "",
                float(row.get("valeur_brute") or 0),
                float(row["taux"]) if row.get("taux") is not None else None,
                float(row.get("amt_n1") or 0),
                float(row.get("dotation") or 0),
                float(row.get("amt_fin") or 0),
                float(row.get("vnc") or 0),
                row.get("agence_label") or "",
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ExerciceClotureService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = LocalStorageService()

    async def cloturer(
        self,
        *,
        annee: int,
        force: bool = False,
        user: User | None = None,
    ) -> ClotureResult:
        if annee < 1990 or annee > 2100:
            raise ValidationError("Année invalide")

        dossier = await self._get_or_create_dossier(annee=annee, user=user)
        await self._ensure_can_generate(dossier, force=force)

        # Snapshot montants exercice N
        lines_by_nature, held_for_opening = await self._collect_snapshot_lines(annee)

        natures_creees = 0
        total_lignes = 0
        for nature_code in NATURE_IMMO_CODES_OFFICIELS:
            rows = lines_by_nature.get(nature_code) or []
            if not rows:
                continue
            await self._write_nature_archive(
                dossier=dossier,
                annee=annee,
                nature_code=nature_code,
                rows=rows,
                user=user,
            )
            natures_creees += 1
            total_lignes += len(rows)

        if total_lignes == 0:
            raise ValidationError(
                f"Aucune opération à archiver pour {annee} "
                "(vérifiez le parc et les amortissements comptabilisés)."
            )

        ouvertures = await self._seed_ouvertures_n1(annee, held_for_opening)

        await self.db.flush()
        return ClotureResult(
            annee=annee,
            natures_creees=natures_creees,
            lignes=total_lignes,
            ouvertures_seed=ouvertures,
            dossier_id=dossier.id,
            message=(
                f"Clôture 31/12/{annee} générée : {natures_creees} nature(s), "
                f"{total_lignes} ligne(s), {ouvertures} ouverture(s) 148 pour {annee + 1}."
            ),
        )

    async def _get_or_create_dossier(self, *, annee: int, user: User | None) -> ArchiveDossier:
        result = await self.db.execute(
            select(ArchiveDossier)
            .where(ArchiveDossier.annee == annee)
            .options(selectinload(ArchiveDossier.fichiers))
        )
        dossier = result.scalar_one_or_none()
        if dossier is not None:
            return dossier
        dossier = ArchiveDossier(
            annee=annee,
            libelle=f"Clôture 31/12/{annee}",
            created_by_id=user.id if user else None,
        )
        self.db.add(dossier)
        await self.db.flush()
        await self.db.refresh(dossier)
        # recharge avec fichiers
        result = await self.db.execute(
            select(ArchiveDossier)
            .where(ArchiveDossier.id == dossier.id)
            .options(selectinload(ArchiveDossier.fichiers))
        )
        return result.scalar_one()

    async def _ensure_can_generate(self, dossier: ArchiveDossier, *, force: bool) -> None:
        existing = [f for f in (dossier.fichiers or []) if f.kind == KIND_CLOTURE]
        if not existing:
            return
        if not force:
            raise ValidationError(
                f"Une clôture système existe déjà pour {dossier.annee}. "
                "Relancez avec force=true pour la régénérer."
            )
        for f in existing:
            path = self.storage.absolute_path(f.stored_path)
            await self.db.delete(f)
            if path.exists():
                path.unlink(missing_ok=True)
        await self.db.flush()
        dossier.fichiers = [f for f in (dossier.fichiers or []) if f.kind != KIND_CLOTURE]

    async def _collect_snapshot_lines(
        self, annee: int
    ) -> tuple[dict[str, list[dict]], list[tuple[Immobilisation, dict[str, Decimal]]]]:
        """Retourne lignes archive par nature + immos détenues fin N (pour seed 148)."""
        dotations_db = await _dotations_par_immo(self.db, annee)
        hist_banque = await _historique_banque_par_immo(self.db, annee)

        result = await self.db.execute(
            select(Immobilisation)
            .where(Immobilisation.deleted_at.is_(None))
            .options(selectinload(Immobilisation.categorie))
            .order_by(Immobilisation.date_acquisition.asc(), Immobilisation.code_inventaire.asc())
        )
        immos = list(result.scalars().all())

        agence_ids = {i.agence_id for i in immos if i.agence_id}
        agence_map: dict[UUID, str] = {}
        if agence_ids:
            ag_res = await self.db.execute(select(Agence).where(Agence.id.in_(agence_ids)))
            for ag in ag_res.scalars().all():
                agence_map[ag.id] = ag.code or ag.libelle

        by_nature: dict[str, list[dict]] = defaultdict(list)
        held: list[tuple[Immobilisation, dict[str, Decimal]]] = []
        date_n = date(annee, 12, 31)

        for immo in immos:
            bank_mvts = _bank_snapshot_amounts(immo)
            if bank_mvts is not None:
                # Hors périmètre si acquis après l'exercice clôturé
                if immo.date_acquisition is None or immo.date_acquisition > date_n:
                    continue
                if immo.date_fin is not None and immo.date_fin < date(annee, 1, 1):
                    continue
                mvts = bank_mvts
            else:
                hist = hist_banque.get(immo.id) if _is_import_banque(immo) else None
                mvts = _mouvements_immo(
                    immo,
                    annee,
                    montants_dotation_db=dotations_db.get(immo.id, []),
                    cumul_n1_db=hist["cumul_n1"] if hist else None,
                    cumul_fin_n_db=hist["cumul_fin"] if hist else None,
                    vnc_fin_n_db=hist["vnc_fin"] if hist else None,
                )
            if mvts is None:
                continue

            nature_code = (immo.categorie.code if immo.categorie else None) or ""
            if nature_code not in NATURE_IMMO_CODES_OFFICIELS:
                # fallback via compte → nature officielle
                nature_code = self._nature_from_compte(immo.compte_immobilisation) or nature_code
            if nature_code not in NATURE_IMMO_CODES_OFFICIELS:
                continue

            detenue_fin_n = immo.date_fin is None or immo.date_fin > date_n
            row = {
                "date_acquisition": immo.date_acquisition,
                "quantite": immo.quantite or 1,
                "designation": immo.designation or immo.code_inventaire,
                "valeur_brute": _q(mvts["valeur_brute"]),
                "taux": immo.taux,
                "amt_n1": _q(mvts["amorts_cumules_n1"]),
                "dotation": _q(mvts["dotations_annee"]),
                "amt_fin": _q(mvts["amorts_cumules_n"]),
                "vnc": _q(mvts["vnc"]),
                "agence_label": agence_map.get(immo.agence_id) if immo.agence_id else None,
                "is_report": _is_report_immo(immo),
                "code_inventaire": immo.code_inventaire,
            }
            by_nature[nature_code].append(row)

            if detenue_fin_n:
                held.append((immo, mvts))

        return by_nature, held

    @staticmethod
    def _nature_from_compte(compte: str | None) -> str | None:
        c = (compte or "").strip()
        if not c:
            return None
        for code, meta in NATURE_BY_CODE.items():
            if str(meta.get("compte_immobilisation") or "") == c:
                return code
        return None

    async def _write_nature_archive(
        self,
        *,
        dossier: ArchiveDossier,
        annee: int,
        nature_code: str,
        rows: list[dict],
        user: User | None,
    ) -> ArchiveFichier:
        filename = f"cloture-{nature_code}-{annee}.xlsx"
        content = build_cloture_xlsx(annee=annee, nature_code=nature_code, lignes=rows)
        relative, size = self.storage.save_bytes(
            content, filename=filename, subdir=f"archives/{annee}"
        )
        fichier = ArchiveFichier(
            dossier_id=dossier.id,
            kind=KIND_CLOTURE,
            filename=filename,
            stored_path=relative,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=size,
            nature_code=nature_code,
            sheet_names=[nature_label(nature_code)],
            uploaded_by_id=user.id if user else None,
            parse_status="ok",
            parse_error=None,
            lines_count=len(rows),
        )
        self.db.add(fichier)
        await self.db.flush()

        for idx, row in enumerate(rows, start=1):
            self.db.add(
                ArchiveLigne(
                    fichier_id=fichier.id,
                    categorie_code=nature_code,
                    feuille=nature_label(nature_code),
                    row_number=idx,
                    date_acquisition=row["date_acquisition"],
                    quantite=int(row.get("quantite") or 1),
                    designation=str(row.get("designation") or ""),
                    valeur_brute=_q(Decimal(row.get("valeur_brute") or 0)),
                    taux=row.get("taux"),
                    amt_n1=_q(Decimal(row.get("amt_n1") or 0)),
                    dotation=_q(Decimal(row.get("dotation") or 0)),
                    amt_fin=_q(Decimal(row.get("amt_fin") or 0)),
                    vnc=_q(Decimal(row.get("vnc") or 0)),
                    agence_label=row.get("agence_label"),
                    is_report=bool(row.get("is_report")),
                    source_kind=KIND_CLOTURE,
                    raw_json={
                        "code_inventaire": row.get("code_inventaire"),
                        "cloture_annee": annee,
                    },
                )
            )
        await self.db.flush()
        return fichier

    async def _seed_ouvertures_n1(
        self,
        annee: int,
        held: list[tuple[Immobilisation, dict[str, Decimal]]],
    ) -> int:
        """Report solde 148 fin N → période {N}-12 (montant 0 pour ne pas gonfler le 68).

        Pour un import « stock historique », on retire aussi les fausses périodes
        d'arrêté N+1 (ex. 2026-06) qui reprenaient la dotation de l'exercice
        clôturé — afin que le calcul T1/T2 de N+1 reconstitue le solde 30/06.
        """
        periode = periode_ouverture(annee)
        seeded = 0
        for immo, mvts in held:
            if "cumul_ouverture_n1" in mvts:
                cumul = _q(mvts["cumul_ouverture_n1"])
                vnc = _q(mvts["vnc_ouverture_n1"])
            else:
                cumul = _q(mvts["amorts_cumules_n"])
                vnc = _q(mvts["vnc"])
            result = await self.db.execute(
                select(Amortissement).where(
                    Amortissement.immobilisation_id == immo.id,
                    Amortissement.periode == periode,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                existing.montant = _zero()
                existing.cumul = cumul
                existing.vnc = vnc
                existing.valide = True
                existing.annule = False
                existing.simule = False
            else:
                self.db.add(
                    Amortissement(
                        immobilisation_id=immo.id,
                        periode=periode,
                        montant=_zero(),
                        cumul=cumul,
                        vnc=vnc,
                        valide=True,
                        annule=False,
                        simule=False,
                    )
                )

            seed_mode = str(mvts.get("seed_mode") or "")
            # Ancien import sans seed_mode + acquis avant N+1 → traité comme stock
            acq = getattr(immo, "date_acquisition", None)
            is_stock = seed_mode in ("", "stock_ouverture") and (
                acq is None or getattr(acq, "year", annee + 1) <= annee
            )
            if is_stock and _is_import_banque(immo):
                await self.db.execute(
                    delete(Amortissement).where(
                        Amortissement.immobilisation_id == immo.id,
                        Amortissement.periode.in_(
                            [PERIODE_ARRETE, PERIODE_ARRETE_ANNUELLE]
                        ),
                    )
                )
            seeded += 1
        return seeded
