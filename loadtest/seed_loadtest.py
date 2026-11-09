"""Données SYNTHÉTIQUES de l'environnement de charge (base bea_digital_test uniquement).

Exécuté dans le conteneur lt-backend par loadtest/setup-env.ps1 :
    python /loadtest/seed_loadtest.py

Crée :
- comptes de test (@loadtest.example.com, mot de passe LOADTEST_PASSWORD, sans 2FA) par profil :
  mg (Moyens Généraux), compta (Immobilisations), employe (demandeurs) ;
- Stock & Fournitures : articles, 12 mois de périodes et de mouvements (via le service métier,
  soldes et reports compris) ;
- Immobilisations : parc d'immobilisations en service ;
- notifications par utilisateur.

Refuse toute autre base que bea_digital_test. Idempotent : ne fait rien si les comptes existent.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, "/app")

from sqlalchemy import select, text  # noqa: E402

from app.core.exceptions import AppError  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.audit import Notification  # noqa: E402
from app.models.auth import Agence, User  # noqa: E402
from app.models.enums import ModeAmortissement, StatutImmobilisation, TypeNotification  # noqa: E402
from app.models.immobilisation import CategorieImmobilisation, Immobilisation  # noqa: E402
from app.models.mg_stock import MgArticle, MgArticleFamille  # noqa: E402
from app.services.mg_stock_periodes import MgStockPeriodeService  # noqa: E402
from app.services.mg_stock_service import MgStockService  # noqa: E402

BASE_AUTORISEE = "bea_digital_test"
DOMAINE = "loadtest.example.com"
MOIS_HISTORIQUE = 12
N_ARTICLES = int(os.getenv("LT_ARTICLES", "300"))
N_IMMOS = int(os.getenv("LT_IMMOBILISATIONS", "1500"))
NOTIFS_PAR_USER = 15

PROFILS: dict[str, dict] = {
    "mg": {
        "nombre": int(os.getenv("LT_USERS_MG", "40")),
        "libelle": "Agent Moyens Généraux",
        "espaces": ["moyens-generaux"],
        "modules": ["stock-fournitures", "demandes-mg", "achats-appro", "notes-frais",
                    "contrats-echeances", "facturation-fournisseurs", "archives-mg"],
        "roles": ["stock-fournitures.magasinier", "stock-fournitures.lecteur", "demandes-mg.gestionnaire",
                  "demandes-mg.lecteur", "achats-appro.lecteur", "notes-frais.lecteur",
                  "contrats-echeances.lecteur", "facturation-fournisseurs.lecteur", "archives-mg.lecteur"],
    },
    "compta": {
        "nombre": int(os.getenv("LT_USERS_COMPTA", "30")),
        "libelle": "Comptable",
        "espaces": ["comptabilite"],
        "modules": ["immobilisations"],
        "roles": ["comptable", "consultation", "lecture_seule"],
    },
    "employe": {
        "nombre": int(os.getenv("LT_USERS_EMPLOYE", "80")),
        "libelle": "Employé demandeur",
        "espaces": ["moyens-generaux", "employe"],
        "modules": ["demandes-mg"],
        "roles": ["demandes-mg.demandeur"],
    },
}

rnd = random.Random(20261105)


def log(msg: str) -> None:
    print(f"[seed {datetime.now():%H:%M:%S}] {msg}", flush=True)


async def ids(db, sql: str, codes: list[str]) -> dict[str, uuid.UUID]:
    rows = (await db.execute(text(sql), {"codes": codes})).all()
    trouves = {c: i for c, i in rows}
    manquants = sorted(set(codes) - set(trouves))
    if manquants:
        raise SystemExit(f"Référentiel incomplet dans {BASE_AUTORISEE} : {manquants}")
    return trouves


async def creer_utilisateurs(db, mot_de_passe: str) -> dict[str, list[User]]:
    hash_commun = get_password_hash(mot_de_passe)
    agences = list((await db.scalars(select(Agence.id).where(Agence.deleted_at.is_(None)))).all())
    out: dict[str, list[User]] = {}
    for profil, cfg in PROFILS.items():
        espaces = await ids(db, "select code, id from plateforme_espaces where code = any(:codes)", cfg["espaces"])
        modules = await ids(db, "select code, id from plateforme_modules where code = any(:codes) and is_active", cfg["modules"])
        roles = await ids(db, "select code, id from roles where code = any(:codes)", cfg["roles"])
        users = []
        for n in range(1, cfg["nombre"] + 1):
            u = User(
                email=f"lt.{profil}.{n:03d}@{DOMAINE}",
                full_name=f"{cfg['libelle']} Test {n:03d}",
                hashed_password=hash_commun,
                is_superuser=False,
                totp_enabled=False,
                is_active=True,
                must_change_password=False,
                agence_id=rnd.choice(agences) if agences else None,
            )
            db.add(u)
            users.append(u)
        await db.flush()
        for u in users:
            for e in espaces.values():
                await db.execute(text("insert into user_espace_acces (user_id, espace_id) values (:u, :e)"),
                                 {"u": u.id, "e": e})
            for m in modules.values():
                await db.execute(text("insert into user_module_acces (user_id, module_id) values (:u, :m)"),
                                 {"u": u.id, "m": m})
            for r in roles.values():
                await db.execute(text("insert into user_roles (user_id, role_id) values (:u, :r)"),
                                 {"u": u.id, "r": r})
        out[profil] = users
        log(f"{len(users)} comptes « {profil} » créés")
    await db.commit()
    return out


def _mois(decalage: int) -> tuple[int, int]:
    today = date.today()
    index = today.year * 12 + today.month - 1 - decalage
    return index // 12, index % 12 + 1


def _instant(annee: int, mois: int, jour_max: int | None = None) -> datetime:
    now = datetime.now(timezone.utc)
    dernier = (date(annee + mois // 12, mois % 12 + 1, 1) - timedelta(days=1)).day
    if (annee, mois) == (now.year, now.month):
        dernier = max(1, now.day - 1)
    jour = rnd.randint(1, min(dernier, jour_max or dernier))
    quand = datetime(annee, mois, jour, rnd.randint(8, 16), rnd.randint(0, 59), tzinfo=timezone.utc)
    return min(quand, now - timedelta(hours=1))


async def creer_stock(db, auteur: User) -> None:
    familles = list((await db.scalars(select(MgArticleFamille).where(MgArticleFamille.deleted_at.is_(None)))).all())
    if not familles:
        famille = MgArticleFamille(code="LT-FOURN", libelle="Fournitures (test)")
        db.add(famille)
        await db.flush()
        familles = [famille]
    articles = []
    for n in range(1, N_ARTICLES + 1):
        a = MgArticle(code=f"LT{n:04d}", designation=f"Article synthétique {n:04d}",
                      famille_id=rnd.choice(familles).id, uom=rnd.choice(["U", "Ramette", "Boîte", "Paquet"]),
                      stockable=True, stock_actuel=Decimal("0"), stock_min=Decimal(rnd.choice([0, 5, 10, 20])))
        db.add(a)
        articles.append(a)
    await db.flush()

    # Base de test = copie de bea_digital : les périodes passées y sont clôturées, les mouvements
    # synthétiques vont alors dans la seule période ouverte du mois courant.
    copie = bool(await db.scalar(text("select count(*) from mg_stock_periodes")))
    historique = 1 if copie else MOIS_HISTORIQUE
    psvc = MgStockPeriodeService(db)
    if not copie:
        await psvc._create_periode(*_mois(historique - 1), user=auteur, precedente=None)
    await psvc.ensure_open_periode(auteur)
    await db.commit()
    log(f"{len(articles)} articles, mouvements depuis {_mois(historique - 1)}")

    svc = MgStockService(db)
    total = 0
    debut = time.monotonic()
    for i, article in enumerate(articles, 1):
        plan: list[tuple[datetime, str, Decimal]] = []
        for decalage in range(historique - 1, -1, -1):
            annee, mois = _mois(decalage)
            if decalage == historique - 1 or rnd.random() < 0.25:
                plan.append((_instant(annee, mois, 5), "ENTREE", Decimal(rnd.choice([50, 100, 200, 500]))))
            for _ in range(rnd.randint(0, 3)):
                plan.append((_instant(annee, mois), "SORTIE", Decimal(rnd.randint(1, 20))))
            if rnd.random() < 0.05:
                plan.append((_instant(annee, mois), "AJUSTEMENT", Decimal(rnd.choice([-2, -1, 1]))))
        plan.sort(key=lambda p: p[0])
        stock = Decimal("0")
        for quand, type_mvt, qty in plan:
            if type_mvt == "SORTIE":
                qty = min(qty, stock)
            if type_mvt == "AJUSTEMENT" and stock + qty < 0:
                continue
            if qty == 0:
                continue
            await svc._apply_mouvement(article=article, type_mouvement=type_mvt, quantite=qty, agence_id=None,
                                       initiateur=auteur, motif="Mouvement synthétique (test de charge)",
                                       date_mouvement=quand)
            stock += -qty if type_mvt == "SORTIE" else qty
            total += 1
        await db.commit()
        if i % 50 == 0:
            log(f"  {i}/{len(articles)} articles, {total} mouvements ({time.monotonic() - debut:.0f} s)")
    log(f"{total} mouvements de stock créés")
    if copie:
        return

    clotures = 0
    for periode in sorted(await psvc.periodes_non_cloturees(), key=lambda p: p.date_debut)[:-2]:
        try:
            await psvc.cloturer(periode.id, auteur)
            await db.commit()
            clotures += 1
        except AppError as exc:
            await db.rollback()
            log(f"clôture {periode.libelle} non effectuée : {exc.message[:120]}")
            break
    log(f"{clotures} période(s) clôturée(s)")


async def creer_immobilisations(db) -> None:
    categories = list((await db.scalars(select(CategorieImmobilisation.id).where(
        CategorieImmobilisation.is_active.is_(True), CategorieImmobilisation.deleted_at.is_(None)))).all())
    agences = list((await db.scalars(select(Agence.id).where(Agence.deleted_at.is_(None)))).all())
    types = ["Ordinateur portable", "Imprimante", "Climatiseur", "Bureau", "Armoire", "Serveur",
             "Véhicule", "Onduleur", "Chaise", "Coffre-fort"]
    today = date.today()
    for n in range(1, N_IMMOS + 1):
        acquis = today - timedelta(days=rnd.randint(30, 6 * 365))
        db.add(Immobilisation(
            code_inventaire=f"LT-IMM-{n:05d}",
            designation=f"{rnd.choice(types)} {n:05d}",
            categorie_id=rnd.choice(categories) if categories else None,
            agence_id=rnd.choice(agences) if agences else None,
            date_acquisition=acquis,
            date_mise_en_service=acquis,
            valeur_brute=Decimal(rnd.randint(50, 5000) * 1000),
            valeur_residuelle=Decimal("0"),
            duree_mois=rnd.choice([36, 60, 120, 240]),
            mode_amortissement=ModeAmortissement.LINEAIRE,
            devise="MRU",
            statut=StatutImmobilisation.EN_SERVICE,
            is_active=True,
        ))
        if n % 500 == 0:
            await db.flush()
    await db.commit()
    log(f"{N_IMMOS} immobilisations créées")


async def creer_notifications(db, users: list[User]) -> None:
    for u in users:
        for k in range(NOTIFS_PAR_USER):
            db.add(Notification(user_id=u.id, type_notification=TypeNotification.SYSTEME,
                                titre=f"Notification de test {k + 1}", message="Message synthétique.",
                                lu=k % 3 != 0, portee="plateforme", categorie="systeme"))
    await db.commit()
    log(f"{len(users) * NOTIFS_PAR_USER} notifications créées")


async def main() -> int:
    mot_de_passe = os.environ.get("LOADTEST_PASSWORD", "")
    if len(mot_de_passe) < 12:
        raise SystemExit("LOADTEST_PASSWORD absent ou trop court (12 caractères minimum).")
    async with AsyncSessionLocal() as db:
        base = await db.scalar(text("select current_database()"))
        if base != BASE_AUTORISEE:
            raise SystemExit(f"ARRÊT : base « {base} » — ce script ne s'exécute que sur {BASE_AUTORISEE}.")
        if await db.scalar(select(User.id).where(User.email.like(f"%@{DOMAINE}")).limit(1)):
            log("Comptes de test déjà présents : rien à faire (recréer la base pour régénérer).")
            return 0
        users = await creer_utilisateurs(db, mot_de_passe)
        await creer_stock(db, users["mg"][0])
        await creer_immobilisations(db)
        await creer_notifications(db, [u for liste in users.values() for u in liste])
        await db.execute(text("analyze"))
    log("Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
