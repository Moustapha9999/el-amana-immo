"""Situation PP / PM : vues sur CLIENT + COMPTES, sans copie indépendante.

Le profil PP / PM est une heuristique ORION (agent économique puis catégorie juridique),
pas le « Profil ORION retraité » du classeur Situation. L'état client est OUVERT / CLOTURE
selon les comptes ; Actif / inactif n'est pas dérivé (source future).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models import (
    Agence,
    ClienteleAlerte,
    ClienteleClassification,
    ClienteleClient,
    ClienteleCompte,
    ClienteleImport,
    ClienteleRapprochement,
    ClienteleSituation,
)
from app.services.clientele.service import Ctx, ClienteleService

VERSION_MAPPING_SITUATION = "2026.10.situation.1"

_MOIS_FR = (
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
_NIVEAUX = (
    ("FAIBLE", "Faible"),
    ("MOYEN", "Moyen"),
    ("ELEVE", "Élevé"),
    ("INTERDIT", "Interdit"),
)
_ALERTES_A_TRAITER = ("NOUVELLE", "A_ANALYSER", "EN_INVESTIGATION")


def _colonne(colonne: str, source: str, champ: str | None, detail: str, etat: str,
             colonne_orion: str | None) -> dict:
    return {
        "colonne": colonne,
        "source": source,
        "champ": champ,
        "detail": detail,
        "etat": etat,
        "colonne_orion": colonne_orion,
        "version_regle": VERSION_MAPPING_SITUATION,
        "verifie_le": None,
    }


SOURCES_COLONNES = [
    _colonne("CODE AG", "ORION", "code_agence",
             "Agence du compte le plus ancien (min DATOUV). 12 clients multi-agences dans l'extrait d'octobre 2026.",
             "CONFIRME", "CODE_AGENCE du compte min(DATOUV)"),
    _colonne("AGENCE_COMPTE", "ORION + référentiel agences", "agence",
             "Libellé de agences.libelle pour le code retenu. Le libellé n'est pas une colonne brute ORION.",
             "CONFIRME", "CODE_AGENCE → agences.libelle"),
    _colonne("CLIENT", "ORION", "racine_client",
             "Racine ORION, 6 chiffres, colonne CLIENT. Jamais compte[0:6] ni un entier.",
             "CONFIRME", "CLIENT"),
    _colonne("NOM CLIENT", "ORION", "nom_client",
             "RAISON_SOCIAL (tronqué à 25 caractères par ORION).",
             "CONFIRME", "RAISON_SOCIAL"),
    _colonne("date ouv", "ORION", "date_ouverture",
             "MIN(DATOUV) des comptes du client.",
             "CONFIRME", "DATOUV"),
    _colonne("statut", "PARTIEL", "etat_client",
             "OUVERT si au moins un compte ouvert, CLOTURE si tous fermés. "
             "Actif / inactif du classeur Situation n'est pas dans ORION (source future).",
             "PARTIEL", "état des comptes (dérivation partielle)"),
    _colonne("Profil ORION retraité", "DERIVE_ORION", "profil_derive",
             "Heuristique agent économique puis catégorie juridique (accord ~94 % avec le classeur Situation). "
             "Ce n'est pas une copie du champ Excel. NON_IDENTIFIE si DIVERS / vide.",
             "DERIVE", "agent économique, puis catégorie juridique"),
    _colonne("Profil pointage stagiaire", "ABSENT", None,
             "Absent d'ORION. Source future : classeur Situation ou phase classification.",
             "ABSENT", None),
    _colonne("NIF", "ORION", "nif",
             "IDENTIFIANT_LISTE lorsque TYPE_IDENTIFIANT = NIF et valeur unique.",
             "CONFIRME", "IDENTIFIANT_LISTE (TYPE_IDENTIFIANT = NIF)"),
    _colonne("NNI", "ORION", "nni",
             "IDENTIFIANT_LISTE lorsque TYPE_IDENTIFIANT = NNI et valeur unique.",
             "CONFIRME", "IDENTIFIANT_LISTE (TYPE_IDENTIFIANT = NNI)"),
    _colonne("Statut résident", "ORION", "statut_resident",
             "R / N (colonne R/N — Statut résident).",
             "CONFIRME", "R/N — Statut résident"),
    _colonne("Secteur d'activité", "ORION", "secteur_activite",
             "SECTEUR_ACTIVITE (souvent vide dans le classeur Situation).",
             "CONFIRME", "SECTEUR_ACTIVITE"),
    _colonne("Catégorie juridique", "ORION", "categorie_juridique",
             "CATEGORIE_JURIDIQUE.",
             "CONFIRME", "CATEGORIE_JURIDIQUE"),
    _colonne("Classe risque LBC FT", "CLASSIFICATION", "niveau",
             "Module classification (CLIENT = racine). Règles configurables, non hardcodées — à valider.",
             "A_VALIDER", None),
    _colonne("Motif de risque", "CLASSIFICATION", "motif_risque",
             "Motifs expliqués par le moteur ou la saisie manuelle / Excel.",
             "A_VALIDER", None),
    _colonne("Nationnalité", "ORION", "nationalite",
             "NATIONALITE.",
             "CONFIRME", "NATIONALITE"),
    _colonne("Date MAJ", "ABSENT", None,
             "Absent d'ORION. updated_at est technique, pas une date métier.",
             "ABSENT", None),
]


def _iso(valeur: date | datetime | None) -> str | None:
    return valeur.isoformat() if valeur else None


def _vide(colonne):
    return or_(colonne.is_(None), colonne == "")


def _dict_situation(row: ClienteleSituation) -> dict:
    return {
        "racine_client": row.racine_client,
        "nom_client": row.nom_client,
        "prenoms": row.prenoms,
        "nationalite": row.nationalite,
        "statut_resident": row.statut_resident,
        "nni": row.nni,
        "nif": row.nif,
        "rcs": row.rcs,
        "type_identifiant": row.type_identifiant,
        "categorie_juridique": row.categorie_juridique,
        "situation_juridique": row.situation_juridique,
        "agent_economique": row.agent_economique,
        "secteur_activite": row.secteur_activite,
        "date_naissance": row.date_naissance.isoformat() if row.date_naissance else None,
        "type_client": row.type_client,
        "profil_derive": row.profil_derive,
        "etat_client": row.etat_client,
        "date_ouverture": row.date_ouverture.isoformat() if row.date_ouverture else None,
        "code_agence": row.code_agence,
        "agence": row.agence,
        "nb_comptes": row.nb_comptes,
        "nb_comptes_ouverts": row.nb_comptes_ouverts,
        "nb_agences": row.nb_agences,
        "date_extraction": row.date_extraction.isoformat() if row.date_extraction else None,
    }


class ClienteleSituationService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    def _filtre(self, q: Select, *, profil: str | None, recherche: str | None, racine: str | None,
                nom: str | None, compte: str | None, rib: str | None, agence: str | None,
                etat: str | None, type_identifiant: str | None) -> Select:
        if profil in ("PP", "PM", "NON_IDENTIFIE"):
            q = q.where(ClienteleSituation.profil_derive == profil)
        if racine:
            q = q.where(ClienteleSituation.racine_client == racine.strip())
        if nom:
            q = q.where(ClienteleSituation.nom_client.ilike(f"%{nom.strip()}%"))
        if etat in ("OUVERT", "CLOTURE"):
            q = q.where(ClienteleSituation.etat_client == etat)
        if agence:
            q = q.where(ClienteleSituation.code_agence == agence.strip())
        if type_identifiant in ("NNI", "NIF"):
            q = q.where(ClienteleSituation.type_identifiant == type_identifiant)
        if recherche:
            t = f"%{recherche.strip()}%"
            q = q.where(or_(
                ClienteleSituation.racine_client.ilike(t),
                ClienteleSituation.nom_client.ilike(t),
                ClienteleSituation.nni.ilike(t),
                ClienteleSituation.nif.ilike(t),
            ))
        if compte or rib:
            sub = select(ClienteleCompte.racine_client)
            if compte:
                sub = sub.where(ClienteleCompte.compte == compte.strip())
            if rib:
                sub = sub.where(ClienteleCompte.rib == rib.strip())
            q = q.where(ClienteleSituation.racine_client.in_(sub))
        return q

    async def lister(self, *, profil: str | None = None, q: str | None = None, racine: str | None = None,
                     nom: str | None = None, compte: str | None = None, rib: str | None = None,
                     agence: str | None = None, etat: str | None = None, type_identifiant: str | None = None,
                     page: int = 1, taille: int = 50) -> dict:
        self.ctx.exiger("clientele.view")
        taille = min(max(taille, 1), 200)
        page = max(page, 1)
        base = self._filtre(select(ClienteleSituation), profil=profil, recherche=q, racine=racine, nom=nom,
                            compte=compte, rib=rib, agence=agence, etat=etat, type_identifiant=type_identifiant)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = list((await self.db.scalars(
            base.order_by(ClienteleSituation.racine_client)
            .offset((page - 1) * taille).limit(taille)
        )).all())
        return {
            "total": int(total),
            "page": page,
            "taille": taille,
            "items": [_dict_situation(r) for r in rows],
        }

    async def tableau_de_bord(self) -> dict:
        self.ctx.exiger("clientele.view")
        total = await self.db.scalar(select(func.count()).select_from(ClienteleSituation)) or 0
        par_profil = dict((await self.db.execute(
            select(ClienteleSituation.profil_derive, func.count())
            .group_by(ClienteleSituation.profil_derive)
        )).all())
        par_etat = dict((await self.db.execute(
            select(ClienteleSituation.etat_client, func.count())
            .group_by(ClienteleSituation.etat_client)
        )).all())
        nb_comptes = await self.db.scalar(select(func.count()).select_from(ClienteleCompte)) or 0
        nb_rib = await self.db.scalar(select(func.count(func.distinct(ClienteleCompte.rib)))) or 0
        extraction = await self.db.scalar(select(func.max(ClienteleSituation.date_extraction)))

        sans_identifiant = await self.db.scalar(select(func.count()).select_from(ClienteleSituation).where(
            _vide(ClienteleSituation.nni), _vide(ClienteleSituation.nif),
            _vide(ClienteleSituation.identifiant_orion),
        )) or 0
        agence_inconnue = await self.db.scalar(select(func.count()).select_from(ClienteleSituation).where(
            or_(_vide(ClienteleSituation.code_agence), _vide(ClienteleSituation.agence)),
        )) or 0
        multi_agences = await self.db.scalar(select(func.count()).select_from(ClienteleSituation).where(
            ClienteleSituation.nb_agences > 1,
        )) or 0
        secteur_vide = await self.db.scalar(select(func.count()).select_from(ClienteleSituation).where(
            _vide(ClienteleSituation.secteur_activite),
        )) or 0
        nationalite_vide = await self.db.scalar(select(func.count()).select_from(ClienteleSituation).where(
            _vide(ClienteleSituation.nationalite),
        )) or 0

        risques_db = dict((await self.db.execute(
            select(ClienteleClassification.niveau, func.count())
            .group_by(ClienteleClassification.niveau)
        )).all())
        non_classes = await self.db.scalar(select(func.count()).select_from(ClienteleSituation).where(
            ClienteleSituation.racine_client.notin_(select(ClienteleClassification.racine_client)),
        )) or 0
        connus = {code for code, _lib in _NIVEAUX}
        risques = [{"niveau": code, "libelle": lib, "clients": int(risques_db.get(code, 0))}
                   for code, lib in _NIVEAUX]
        risques.extend(
            {"niveau": code, "libelle": code, "clients": int(nb)}
            for code, nb in risques_db.items() if code not in connus
        )

        agences = [
            {"code": code or "—", "libelle": libelle or "Libellé absent", "clients": int(nb)}
            for code, libelle, nb in (await self.db.execute(
                select(ClienteleSituation.code_agence, ClienteleSituation.agence, func.count())
                .group_by(ClienteleSituation.code_agence, ClienteleSituation.agence)
                .order_by(func.count().desc())
                .limit(8)
            )).all()
        ]

        mois = func.date_trunc("month", ClienteleClient.premiere_extraction)
        evolution = []
        for debut, nb in reversed((await self.db.execute(
            select(mois, func.count()).group_by(mois).order_by(mois.desc()).limit(6)
        )).all()):
            if debut is None:
                continue
            jour = debut.date() if isinstance(debut, datetime) else debut
            evolution.append({
                "mois": jour.strftime("%Y-%m"),
                "libelle": f"{_MOIS_FR[jour.month]} {jour.year}",
                "nouveaux": int(nb),
            })

        imports = list((await self.db.scalars(
            select(ClienteleImport).order_by(ClienteleImport.created_at.desc()).limit(5)
        )).all())
        dernier = imports[0] if imports else None
        alertes_ouvertes = await self.db.scalar(select(func.count()).select_from(ClienteleAlerte).where(
            ClienteleAlerte.statut.in_(_ALERTES_A_TRAITER),
        )) or 0
        rejets = int(dernier.nb_rejets or 0) if dernier else 0
        anomalies_import = int(dernier.nb_anomalies or 0) if dernier else 0

        activite = []
        for imp in imports:
            activite.append({
                "type": "import",
                "id": str(imp.id),
                "libelle": imp.fichier_nom,
                "statut": imp.statut,
                "le": _iso(imp.importe_le or imp.created_at),
                "detail": f"{imp.nb_clients} clients · {imp.nb_anomalies} anomalies · {imp.nb_rejets} rejets",
            })
        for rap in (await self.db.scalars(
            select(ClienteleRapprochement).order_by(ClienteleRapprochement.created_at.desc()).limit(5)
        )).all():
            activite.append({
                "type": "rapprochement",
                "id": str(rap.id),
                "libelle": "Rapprochement d'imports",
                "statut": "RAPPROCHE",
                "le": _iso(rap.created_at),
                "detail": "Comparaison de deux extractions ORION",
            })
        activite.sort(key=lambda e: e["le"] or "", reverse=True)

        return {
            "nb_clients": int(total),
            "nb_comptes": int(nb_comptes),
            "nb_rib": int(nb_rib),
            "pp": int(par_profil.get("PP", 0)),
            "pm": int(par_profil.get("PM", 0)),
            "non_identifies": int(par_profil.get("NON_IDENTIFIE", 0)),
            "constructions_juridiques": None,
            "ouverts": int(par_etat.get("OUVERT", 0)),
            "clotures": int(par_etat.get("CLOTURE", 0)),
            "date_extraction": _iso(extraction),
            "periode_libelle": (
                f"Stock au {extraction.strftime('%d/%m/%Y')}" if extraction else "Aucun stock chargé"
            ),
            "dernier_import": (
                {
                    "id": str(dernier.id),
                    "fichier_nom": dernier.fichier_nom,
                    "statut": dernier.statut,
                    "importe_le": _iso(dernier.importe_le),
                    "cree_le": _iso(dernier.created_at),
                    "date_extraction": _iso(dernier.date_extraction),
                    "nb_clients": dernier.nb_clients,
                    "nb_comptes": dernier.nb_comptes,
                    "nb_rejets": dernier.nb_rejets,
                    "nb_anomalies": dernier.nb_anomalies,
                } if dernier else None
            ),
            "anomalies": {
                "a_traiter": int(sans_identifiant) + int(agence_inconnue) + int(alertes_ouvertes) + rejets,
                "sans_identifiant": int(sans_identifiant),
                "agence_inconnue": int(agence_inconnue),
                "alertes_ouvertes": int(alertes_ouvertes),
                "rejets_dernier_import": rejets,
                "anomalies_dernier_import": anomalies_import,
                "multi_agences": int(multi_agences),
                "secteur_vide": int(secteur_vide),
                "nationalite_vide": int(nationalite_vide),
            },
            "risques": risques,
            "non_classes": int(non_classes),
            "agences": agences,
            "evolution": evolution,
            "activite": activite[:8],
            "sources": SOURCES_COLONNES,
        }

    async def fiche(self, racine: str) -> dict:
        self.ctx.exiger("clientele.view")
        racine = (racine or "").strip()
        if len(racine) != 6:
            raise AppError("Racine client invalide (6 chiffres)", 422, code="RACINE_INVALIDE")
        sit = await self.db.get(ClienteleSituation, racine)
        client = await self.db.scalar(
            select(ClienteleClient).where(ClienteleClient.racine_client == racine)
            .options(selectinload(ClienteleClient.comptes)))
        if not client:
            raise AppError("Client introuvable", 404, code="NOT_FOUND")
        agences = {a.id: a for a in (await self.db.scalars(select(Agence))).all()}
        comptes = []
        for c in client.comptes:
            ag = agences.get(c.agence_id)
            comptes.append({
                "compte": c.compte, "rib": c.rib, "etat_compte": c.etat_compte, "devise": c.devise,
                "ncg": c.ncg, "rubrique_comptable": c.rubrique_comptable,
                "code_agence": ag.code if ag else None, "agence": ag.libelle if ag else None,
                "date_ouverture": c.date_ouverture.isoformat() if c.date_ouverture else None,
                "ddc": c.ddc.isoformat() if c.ddc else None,
                "ddd": c.ddd.isoformat() if c.ddd else None,
                "conformite_compte": c.conformite_compte,
                "liste_interdiction": c.liste_interdiction,
                "date_extraction": c.date_extraction.isoformat() if c.date_extraction else None,
            })
        dernier = await self.db.scalar(
            select(ClienteleImport).where(ClienteleImport.statut == "IMPORTE")
            .order_by(ClienteleImport.importe_le.desc()).limit(1))
        classif = await self.db.get(ClienteleClassification, racine)
        alertes = list((await self.db.scalars(
            select(ClienteleAlerte).where(
                ClienteleAlerte.racine_client == racine, ClienteleAlerte.statut != "CLOTUREE")
            .order_by(ClienteleAlerte.created_at.desc())
        )).all())
        await self.svc.audit("clientele.client.view", "clientele_client", racine,
                             after={"nb_comptes": len(comptes)})
        return {
            "client": {
                "racine_client": client.racine_client,
                "raison_sociale": client.raison_sociale,
                "prenoms": client.prenoms,
                "date_naissance": client.date_naissance.isoformat() if client.date_naissance else None,
                "date_naissance_orion": client.date_naissance_orion,
                "nationalite": client.nationalite,
                "statut_resident": client.statut_resident,
                "agent_economique": client.agent_economique,
                "situation_juridique": client.situation_juridique,
                "categorie_juridique": client.categorie_juridique,
                "secteur_activite": client.secteur_activite,
                "famille_secteur_activite": client.famille_secteur_activite,
                "type_identifiant": client.type_identifiant,
                "identifiant_orion": client.identifiant_orion,
                "nni": client.nni, "nif": client.nif, "rcs": client.rcs,
                "type_client": client.type_client,
                "premiere_extraction": client.premiere_extraction.isoformat() if client.premiere_extraction else None,
                "date_extraction": client.date_extraction.isoformat() if client.date_extraction else None,
            },
            "situation": _dict_situation(sit) if sit else None,
            "comptes": comptes,
            "dernier_import": (
                {"id": str(dernier.id), "fichier_nom": dernier.fichier_nom,
                 "importe_le": dernier.importe_le.isoformat() if dernier.importe_le else None}
                if dernier else None),
            "classification": (
                {"niveau": classif.niveau, "source": classif.source,
                 "motif_risque": classif.motif_risque, "motif_classement": classif.motif_classement,
                 "motifs": classif.motifs or [],
                 "classifie_le": classif.classifie_le.isoformat() if classif.classifie_le else None}
                if classif else None),
            "alertes_ouvertes": [{"id": str(a.id), "statut": a.statut, "motif": a.motif,
                                  "precedent_faux_positif": a.precedent_faux_positif}
                                 for a in alertes],
            "sources": SOURCES_COLONNES,
        }
