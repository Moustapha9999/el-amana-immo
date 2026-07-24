from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Amortissement, EcritureComptable, Immobilisation, ParametrageEcriture
from app.models.enums import StatutImmobilisation
from app.services.amortissement_engine import build_amortissement_schedule


class AmortissementService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_immobilisation(self, immobilisation_id: UUID) -> Immobilisation:
        result = await self.db.execute(
            select(Immobilisation)
            .options(selectinload(Immobilisation.categorie))
            .where(Immobilisation.id == immobilisation_id, Immobilisation.deleted_at.is_(None))
        )
        immo = result.scalar_one_or_none()
        if immo is None:
            raise NotFoundError("Immobilisation", str(immobilisation_id))
        return immo

    async def list_for_immobilisation(self, immobilisation_id: UUID) -> list[Amortissement]:
        result = await self.db.execute(
            select(Amortissement)
            .where(Amortissement.immobilisation_id == immobilisation_id)
            .order_by(Amortissement.periode.asc())
        )
        return list(result.scalars().all())

    async def simulate(self, immobilisation_id: UUID, periode: str) -> Amortissement:
        """Conservé pour compatibilité API — une ligne simulée sur la 1ère période du plan."""
        immo = await self._load_immobilisation(immobilisation_id)
        schedule = build_amortissement_schedule(immo)
        if not schedule:
            raise ValidationError("Impossible de simuler : immobilisation non amortissable ou durée nulle.")
        montant = schedule[0][1]
        cumul = montant
        vnc = immo.valeur_brute - cumul
        row = Amortissement(
            immobilisation_id=immobilisation_id,
            periode=periode,
            montant=montant,
            cumul=cumul,
            vnc=vnc,
            simule=True,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def generer_plan(self, immobilisation_id: UUID) -> list[Amortissement]:
        immo = await self._load_immobilisation(immobilisation_id)
        if immo.statut != StatutImmobilisation.EN_SERVICE:
            raise ValidationError("Le plan d'amortissement ne peut être généré que pour une immobilisation en service.")
        categorie = immo.categorie
        if categorie is None or not categorie.amortissable:
            raise ValidationError("Cette immobilisation n'est pas amortissable.")
        if not immo.compte_dotation or not immo.compte_amortissement:
            raise ValidationError("Comptes de dotation et d'amortissement requis.")

        await self.db.execute(
            delete(Amortissement).where(
                Amortissement.immobilisation_id == immobilisation_id,
                Amortissement.valide.is_(False),
                Amortissement.simule.is_(False),
            )
        )

        schedule = build_amortissement_schedule(immo)
        if not schedule:
            raise ValidationError("Durée ou base amortissable invalide.")

        cumul = Decimal("0")
        rows: list[Amortissement] = []
        for periode, montant in schedule:
            cumul = (cumul + montant).quantize(Decimal("0.01"))
            vnc = (immo.valeur_brute - cumul).quantize(Decimal("0.01"))
            row = Amortissement(
                immobilisation_id=immobilisation_id,
                periode=periode,
                montant=montant,
                cumul=cumul,
                vnc=vnc,
                simule=False,
                valide=False,
            )
            self.db.add(row)
            rows.append(row)
        await self.db.flush()
        return rows

    async def comptabiliser(
        self,
        immobilisation_id: UUID,
        periode: str,
        date_ecriture: date,
    ) -> tuple[Amortissement, EcritureComptable]:
        immo = await self._load_immobilisation(immobilisation_id)
        if immo.statut != StatutImmobilisation.EN_SERVICE:
            raise ValidationError("Comptabilisation réservée aux immobilisations en service.")

        result = await self.db.execute(
            select(Amortissement).where(
                Amortissement.immobilisation_id == immobilisation_id,
                Amortissement.periode == periode,
                Amortissement.annule.is_(False),
                Amortissement.simule.is_(False),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Ligne d'amortissement", f"{immobilisation_id}/{periode}")
        if row.valide:
            raise ValidationError(f"La période {periode} est déjà comptabilisée.")

        compte_debit = immo.compte_dotation
        compte_credit = immo.compte_amortissement
        if not compte_debit or not compte_credit:
            raise ValidationError("Comptes 681 / 148 manquants sur la fiche.")

        journal_code = "OD"
        if immo.categorie is not None:
            param = await self.db.execute(
                select(ParametrageEcriture).where(ParametrageEcriture.categorie_id == immo.categorie_id)
            )
            param_row = param.scalar_one_or_none()
            if param_row is not None:
                journal_code = param_row.journal_code
                compte_debit = param_row.compte_debit
                compte_credit = param_row.compte_credit
                libelle = param_row.libelle_modele.format(code_inventaire=immo.code_inventaire)
            else:
                libelle = f"Dotation amortissement — {immo.code_inventaire} ({periode})"
        else:
            libelle = f"Dotation amortissement — {immo.code_inventaire} ({periode})"

        ecriture = EcritureComptable(
            journal_code=journal_code,
            date_ecriture=date_ecriture,
            libelle=libelle,
            compte_debit=compte_debit,
            compte_credit=compte_credit,
            montant=row.montant,
            reference=f"AMORT-{immo.code_inventaire}-{periode}",
            immobilisation_id=immo.id,
            generee_auto=True,
            validee=True,
        )
        self.db.add(ecriture)
        row.valide = True
        # date_comptabilisation reste la date de comptabilisation d'acquisition (note banque)
        await self.db.flush()
        await self._notify_fin_amortissement_if_needed(immo, row)
        return row, ecriture

    async def _notify_fin_amortissement_if_needed(self, immo: Immobilisation, last_row: Amortissement) -> None:
        from decimal import Decimal

        from app.models.enums import TypeNotification
        from app.services.notification_service import NotificationService

        pending = await self.db.execute(
            select(func.count())
            .select_from(Amortissement)
            .where(
                Amortissement.immobilisation_id == immo.id,
                Amortissement.annule.is_(False),
                Amortissement.simule.is_(False),
                Amortissement.valide.is_(False),
            )
        )
        if int(pending.scalar_one()) > 0:
            return
        if last_row.vnc > immo.valeur_residuelle + Decimal("0.01"):
            return
        await NotificationService(self.db).notify_staff(
            role_codes={"administrateur", "comptable"},
            type_notification=TypeNotification.FIN_AMORTISSEMENT,
            titre=f"Fin d'amortissement — {immo.code_inventaire}",
            message=f"L'immobilisation {immo.designation} est entièrement amortie (VNC {last_row.vnc}).",
            entity="immobilisation",
            entity_id=str(immo.id),
        )

    async def mettre_en_service(self, immobilisation_id: UUID) -> Immobilisation:
        immo = await self._load_immobilisation(immobilisation_id)
        if immo.statut in (
            StatutImmobilisation.CEDEE,
            StatutImmobilisation.MISE_AU_REBUT,
            StatutImmobilisation.ARCHIVEE,
            StatutImmobilisation.SORTIE,
        ):
            raise ValidationError("Impossible de mettre en service une immobilisation sortie ou archivée.")
        if not immo.date_mise_en_service:
            raise ValidationError("La date de mise en service est obligatoire.")
        if immo.statut == StatutImmobilisation.EN_SERVICE:
            return immo

        immo.statut = StatutImmobilisation.EN_SERVICE
        await self.db.flush()

        categorie = immo.categorie
        if categorie and categorie.amortissable:
            existing = await self.db.execute(
                select(func.count())
                .select_from(Amortissement)
                .where(
                    Amortissement.immobilisation_id == immobilisation_id,
                    Amortissement.simule.is_(False),
                )
            )
            if int(existing.scalar_one()) == 0:
                await self.generer_plan(immobilisation_id)
                await self.db.refresh(immo)

        return immo
