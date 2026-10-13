"""Référentiels (types, motifs, sous-motifs, canaux) et unités organisationnelles du module.

Une valeur ou une unité utilisée se désactive, elle ne se supprime pas : les dossiers gardent
leur classement d'origine. Toute écriture est auditée (avant / après).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agence, ReclamationReferentiel, ReclamationUnite, ReclamationUniteMembre, User
from app.services.permission_service import load_user_permission_codes
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope, permissions_effectives
from app.services.reclamations.outils import auditer, cle, code_propre, conflit, erreur, iso, propre, texte_long


# ------------------------------------------------------------------ référentiels
def referentiel_dict(r: ReclamationReferentiel, usage: int = 0) -> dict:
    return {
        "id": str(r.id), "domaine": r.domaine, "code": r.code, "libelle": r.libelle,
        "parent_id": str(r.parent_id) if r.parent_id else None, "description": r.description,
        "ordre": r.ordre, "actif": r.actif, "usage": usage,
    }


async def _usages_referentiels(db: AsyncSession) -> dict[uuid.UUID, int]:
    sql = text(
        """
        SELECT id, sum(n)::int FROM (
          SELECT type_id AS id, count(*) n FROM reclamations WHERE type_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT motif_id, count(*) FROM reclamations WHERE motif_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT sous_motif_id, count(*) FROM reclamations WHERE sous_motif_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT canal_id, count(*) FROM reclamations GROUP BY 1
          UNION ALL SELECT canal_envoi_id, count(*) FROM reclamation_reponses WHERE canal_envoi_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT type_id, count(*) FROM reclamation_regles_delai WHERE type_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT motif_id, count(*) FROM reclamation_regles_delai WHERE motif_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT parent_id, count(*) FROM reclamation_referentiels WHERE parent_id IS NOT NULL GROUP BY 1
        ) u GROUP BY id
        """
    )
    return {row[0]: row[1] for row in (await db.execute(sql)).all()}


async def lister_referentiels(db: AsyncSession, domaine: str | None = None) -> list[dict]:
    q = select(ReclamationReferentiel).order_by(
        ReclamationReferentiel.domaine, ReclamationReferentiel.ordre, ReclamationReferentiel.libelle)
    if domaine:
        q = q.where(ReclamationReferentiel.domaine == domaine)
    usages = await _usages_referentiels(db)
    return [referentiel_dict(r, usages.get(r.id, 0)) for r in (await db.scalars(q)).all()]


async def _referentiel(db: AsyncSession, rid: uuid.UUID) -> ReclamationReferentiel:
    r = await db.get(ReclamationReferentiel, rid)
    if r is None:
        raise erreur("Valeur de référentiel introuvable", "NOT_FOUND", 404)
    return r


async def _verifier_unicite(db: AsyncSession, domaine: str, parent_id: uuid.UUID | None, libelle: str,
                            code: str | None, exclure: uuid.UUID | None = None) -> None:
    q = select(ReclamationReferentiel).where(
        ReclamationReferentiel.domaine == domaine, ReclamationReferentiel.cle == cle(libelle),
        ReclamationReferentiel.parent_id.is_(None) if parent_id is None
        else ReclamationReferentiel.parent_id == parent_id)
    if exclure:
        q = q.where(ReclamationReferentiel.id != exclure)
    existant = await db.scalar(q)
    if existant:
        etat = "" if existant.actif else " (désactivée — réactivez-la)"
        raise conflit(f"« {existant.libelle} » existe déjà{etat}", "REFERENTIEL_EXISTANT",
                      existant=referentiel_dict(existant))
    if code:
        q = select(ReclamationReferentiel.id).where(
            ReclamationReferentiel.domaine == domaine, ReclamationReferentiel.code == code)
        if exclure:
            q = q.where(ReclamationReferentiel.id != exclure)
        if await db.scalar(q):
            raise conflit(f"Le code {code} est déjà utilisé dans ce référentiel", "CODE_EXISTANT")


async def creer_referentiel(db: AsyncSession, s: ReclamationsScope, data: dict) -> dict:
    s.exiger("reclamations.references.manage")
    domaine = data["domaine"]
    libelle = propre(data.get("libelle"))
    if not cle(libelle):
        raise erreur("Libellé obligatoire", "LIBELLE_OBLIGATOIRE")
    parent_id = data.get("parent_id")
    domaine_parent = C.DOMAINE_PARENT.get(domaine)
    if domaine_parent:
        if not parent_id:
            raise erreur(f"Un {C.DOMAINE_LIBELLES[domaine].lower()} est rattaché à un "
                         f"{C.DOMAINE_LIBELLES[domaine_parent].lower()}", "PARENT_OBLIGATOIRE")
        parent = await _referentiel(db, parent_id)
        if parent.domaine != domaine_parent:
            raise erreur(f"Le parent doit être un {C.DOMAINE_LIBELLES[domaine_parent].lower()}", "PARENT_INVALIDE")
        if not parent.actif:
            raise erreur(f"« {parent.libelle} » est désactivé", "PARENT_INACTIF")
    elif parent_id:
        raise erreur(f"Le domaine {C.DOMAINE_LIBELLES[domaine]} n'a pas de parent", "PARENT_INVALIDE")
    code = code_propre(data.get("code"))
    await _verifier_unicite(db, domaine, parent_id, libelle, code)
    ordre = await db.scalar(select(func.coalesce(func.max(ReclamationReferentiel.ordre), 0)).where(
        ReclamationReferentiel.domaine == domaine))
    r = ReclamationReferentiel(
        domaine=domaine, code=code, libelle=libelle, cle=cle(libelle), parent_id=parent_id,
        description=texte_long(data.get("description")), ordre=(ordre or 0) + 1, actif=True,
        created_by_id=s.user_id, updated_by_id=s.user_id)
    db.add(r)
    await db.flush()
    apres = referentiel_dict(r)
    await auditer(db, s, "reclamations.referentiel.create", "reclamation_referentiel", r.id, after=apres)
    return apres


async def modifier_referentiel(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    s.exiger("reclamations.references.manage")
    r = await _referentiel(db, rid)
    avant = referentiel_dict(r)
    libelle = propre(data["libelle"]) if data.get("libelle") is not None else r.libelle
    if not cle(libelle):
        raise erreur("Libellé obligatoire", "LIBELLE_OBLIGATOIRE")
    code = code_propre(data["code"]) if "code" in data and data["code"] is not None else r.code
    await _verifier_unicite(db, r.domaine, r.parent_id, libelle, code if code != r.code else None, exclure=r.id)
    r.libelle, r.cle, r.code = libelle, cle(libelle), code
    if "description" in data and data["description"] is not None:
        r.description = texte_long(data["description"])
    if data.get("ordre") is not None:
        r.ordre = data["ordre"]
    if data.get("actif") is not None:
        if data["actif"] and r.parent_id:
            parent = await _referentiel(db, r.parent_id)
            if not parent.actif:
                raise erreur(f"Réactivez d'abord « {parent.libelle} »", "PARENT_INACTIF")
        r.actif = data["actif"]
    r.updated_by_id = s.user_id
    await db.flush()
    apres = referentiel_dict(r)
    await auditer(db, s, "reclamations.referentiel.update", "reclamation_referentiel", r.id,
                  before=avant, after=apres)
    return apres


async def supprimer_referentiel(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID) -> None:
    s.exiger("reclamations.references.manage")
    r = await _referentiel(db, rid)
    if (await _usages_referentiels(db)).get(r.id, 0):
        raise conflit("Valeur utilisée : désactivez-la plutôt que de la supprimer", "REFERENTIEL_UTILISE")
    avant = referentiel_dict(r)
    await db.delete(r)
    await db.flush()
    await auditer(db, s, "reclamations.referentiel.delete", "reclamation_referentiel", rid, before=avant)


# ---------------------------------------------------------------------- unités
def unite_dict(u: ReclamationUnite, *, agences: dict[uuid.UUID, str] | None = None,
               membres: int = 0, dossiers: int = 0) -> dict:
    return {
        "id": str(u.id), "type_unite": u.type_unite, "type_libelle": C.TYPE_UNITE_LIBELLES.get(u.type_unite),
        "code": u.code, "libelle": u.libelle, "parent_id": str(u.parent_id) if u.parent_id else None,
        "agence_id": str(u.agence_id) if u.agence_id else None,
        "agence": (agences or {}).get(u.agence_id) if u.agence_id else None,
        "est_service_reclamations": u.est_service_reclamations, "email": u.email,
        "description": u.description, "ordre": u.ordre, "actif": u.actif,
        "nb_membres": membres, "nb_dossiers": dossiers,
    }


async def _agences(db: AsyncSession) -> dict[uuid.UUID, str]:
    rows = (await db.execute(select(Agence.id, Agence.code, Agence.libelle))).all()
    return {i: f"{c} — {lib}" for i, c, lib in rows}


async def lister_unites(db: AsyncSession) -> list[dict]:
    unites = (await db.scalars(select(ReclamationUnite).order_by(
        ReclamationUnite.ordre, ReclamationUnite.libelle))).all()
    membres = dict((await db.execute(
        select(ReclamationUniteMembre.unite_id, func.count()).where(ReclamationUniteMembre.actif.is_(True))
        .group_by(ReclamationUniteMembre.unite_id))).all())
    dossiers = {row[0]: row[1] for row in (await db.execute(text(
        """
        SELECT u, count(DISTINCT r) FROM (
          SELECT unite_reception_id u, id r FROM reclamations WHERE unite_reception_id IS NOT NULL
          UNION ALL SELECT unite_destinataire_id, reclamation_id FROM reclamation_affectations
        ) x GROUP BY u
        """))).all()}
    agences = await _agences(db)
    return [unite_dict(u, agences=agences, membres=membres.get(u.id, 0), dossiers=dossiers.get(u.id, 0))
            for u in unites]


async def _unite(db: AsyncSession, uid: uuid.UUID) -> ReclamationUnite:
    u = await db.get(ReclamationUnite, uid)
    if u is None:
        raise erreur("Unité introuvable", "NOT_FOUND", 404)
    return u


async def _cle_unite_libre(db: AsyncSession, libelle: str, exclure: uuid.UUID | None = None) -> None:
    q = select(ReclamationUnite).where(ReclamationUnite.cle == cle(libelle))
    if exclure:
        q = q.where(ReclamationUnite.id != exclure)
    existant = await db.scalar(q)
    if existant:
        etat = "" if existant.actif else " (désactivée — réactivez-la)"
        raise conflit(f"L'unité « {existant.libelle} » existe déjà{etat}", "UNITE_EXISTANTE")


async def _verifier_parent(db: AsyncSession, parent_id: uuid.UUID, unite_id: uuid.UUID | None = None) -> None:
    """Refuse un parent inexistant, inactif, ou qui créerait un cycle dans l'arborescence."""
    parent = await _unite(db, parent_id)
    if not parent.actif:
        raise erreur(f"L'unité parente « {parent.libelle} » est désactivée", "PARENT_INACTIF")
    if unite_id is None:
        return
    courant: ReclamationUnite | None = parent
    vus: set[uuid.UUID] = set()
    while courant is not None and courant.id not in vus:
        if courant.id == unite_id:
            raise erreur("Une unité ne peut pas être rattachée à elle-même ni à l'une de ses sous-unités",
                         "HIERARCHIE_CIRCULAIRE")
        vus.add(courant.id)
        courant = await db.get(ReclamationUnite, courant.parent_id) if courant.parent_id else None


async def _verifier_agence(db: AsyncSession, agence_id: uuid.UUID) -> None:
    if not await db.get(Agence, agence_id):
        raise erreur("Agence introuvable", "AGENCE_INCONNUE")


async def creer_unite(db: AsyncSession, s: ReclamationsScope, data: dict) -> dict:
    s.exiger("reclamations.services.manage")
    libelle = propre(data.get("libelle"))
    if not cle(libelle):
        raise erreur("Libellé obligatoire", "LIBELLE_OBLIGATOIRE")
    await _cle_unite_libre(db, libelle)
    if data.get("parent_id"):
        await _verifier_parent(db, data["parent_id"])
    if data.get("agence_id"):
        await _verifier_agence(db, data["agence_id"])
    ordre = await db.scalar(select(func.coalesce(func.max(ReclamationUnite.ordre), 0)))
    u = ReclamationUnite(
        type_unite=data["type_unite"], code=code_propre(data.get("code")), libelle=libelle, cle=cle(libelle),
        parent_id=data.get("parent_id"), agence_id=data.get("agence_id"), est_service_reclamations=False,
        email=propre(data.get("email")) or None, description=texte_long(data.get("description")),
        ordre=(ordre or 0) + 1, actif=True, created_by_id=s.user_id, updated_by_id=s.user_id)
    db.add(u)
    await db.flush()
    apres = unite_dict(u, agences=await _agences(db))
    await auditer(db, s, "reclamations.unite.create", "reclamation_unite", u.id, after=apres)
    return apres


async def modifier_unite(db: AsyncSession, s: ReclamationsScope, uid: uuid.UUID, data: dict) -> dict:
    s.exiger("reclamations.services.manage")
    u = await _unite(db, uid)
    agences = await _agences(db)
    avant = unite_dict(u, agences=agences)
    if data.get("libelle") is not None:
        libelle = propre(data["libelle"])
        if not cle(libelle):
            raise erreur("Libellé obligatoire", "LIBELLE_OBLIGATOIRE")
        await _cle_unite_libre(db, libelle, exclure=u.id)
        u.libelle, u.cle = libelle, cle(libelle)
    if data.get("type_unite"):
        u.type_unite = data["type_unite"]
    if data.get("code") is not None:
        u.code = code_propre(data["code"])
    if data.get("detacher_parent"):
        u.parent_id = None
    elif data.get("parent_id"):
        await _verifier_parent(db, data["parent_id"], u.id)
        u.parent_id = data["parent_id"]
    if data.get("detacher_agence"):
        u.agence_id = None
    elif data.get("agence_id"):
        await _verifier_agence(db, data["agence_id"])
        u.agence_id = data["agence_id"]
    if data.get("email") is not None:
        u.email = propre(data["email"]) or None
    if data.get("description") is not None:
        u.description = texte_long(data["description"])
    if data.get("ordre") is not None:
        u.ordre = data["ordre"]
    if data.get("actif") is not None and data["actif"] != u.actif:
        if not data["actif"] and u.est_service_reclamations:
            raise erreur("Le Service Réclamations central ne peut pas être désactivé", "SERVICE_CENTRAL")
        if data["actif"] and u.parent_id:
            parent = await _unite(db, u.parent_id)
            if not parent.actif:
                raise erreur(f"Réactivez d'abord l'unité parente « {parent.libelle} »", "PARENT_INACTIF")
        u.actif = data["actif"]
    u.updated_by_id = s.user_id
    await db.flush()
    apres = unite_dict(u, agences=agences)
    await auditer(db, s, "reclamations.unite.update", "reclamation_unite", u.id, before=avant, after=apres)
    return apres


# --------------------------------------------------------------------- membres
async def lister_membres(db: AsyncSession, uid: uuid.UUID) -> list[dict]:
    await _unite(db, uid)
    rows = (await db.execute(
        select(ReclamationUniteMembre, User.full_name, User.email, User.is_active)
        .join(User, User.id == ReclamationUniteMembre.user_id)
        .where(ReclamationUniteMembre.unite_id == uid)
        .order_by(ReclamationUniteMembre.actif.desc(), ReclamationUniteMembre.role_membre.desc(), User.full_name)
    )).all()
    return [_membre_dict(m, nom, email, compte_actif) for m, nom, email, compte_actif in rows]


def _membre_dict(m: ReclamationUniteMembre, nom: str | None, email: str | None, compte_actif: bool) -> dict:
    return {
        "id": str(m.id), "unite_id": str(m.unite_id), "user_id": str(m.user_id), "nom": nom or email,
        "email": email, "role_membre": m.role_membre, "actif": m.actif, "compte_actif": compte_actif,
        "depuis": iso(m.created_at),
    }


async def ajouter_membre(db: AsyncSession, s: ReclamationsScope, uid: uuid.UUID, data: dict) -> list[dict]:
    s.exiger("reclamations.services.manage")
    u = await _unite(db, uid)
    if not u.actif:
        raise erreur("Unité désactivée", "UNITE_INACTIVE")
    user = await db.get(User, data["user_id"])
    if user is None or not user.is_active or user.deleted_at is not None:
        raise erreur("Utilisateur introuvable ou inactif", "UTILISATEUR_INCONNU")
    m = await db.scalar(select(ReclamationUniteMembre).where(
        ReclamationUniteMembre.unite_id == uid, ReclamationUniteMembre.user_id == user.id))
    if m and m.actif:
        raise conflit(f"{user.full_name} est déjà membre de « {u.libelle} »", "MEMBRE_EXISTANT")
    avant = {"role_membre": m.role_membre, "actif": m.actif} if m else None
    if m:
        m.actif, m.role_membre, m.updated_by_id = True, data["role_membre"], s.user_id
    else:
        m = ReclamationUniteMembre(unite_id=uid, user_id=user.id, role_membre=data["role_membre"], actif=True,
                                   created_by_id=s.user_id, updated_by_id=s.user_id)
        db.add(m)
    await db.flush()
    await auditer(db, s, "reclamations.membre.add", "reclamation_unite", uid, before=avant,
                  after={"utilisateur": user.full_name, "user_id": str(user.id), "role_membre": m.role_membre})
    return await lister_membres(db, uid)


async def modifier_membre(db: AsyncSession, s: ReclamationsScope, uid: uuid.UUID, mid: uuid.UUID,
                          data: dict) -> list[dict]:
    s.exiger("reclamations.services.manage")
    m = await db.get(ReclamationUniteMembre, mid)
    if m is None or m.unite_id != uid:
        raise erreur("Membre introuvable", "NOT_FOUND", 404)
    avant = {"role_membre": m.role_membre, "actif": m.actif}
    if data.get("role_membre"):
        m.role_membre = data["role_membre"]
    if data.get("actif") is not None:
        m.actif = data["actif"]
    m.updated_by_id = s.user_id
    await db.flush()
    await auditer(db, s, "reclamations.membre.update", "reclamation_unite", uid, before=avant,
                  after={"user_id": str(m.user_id), "role_membre": m.role_membre, "actif": m.actif})
    return await lister_membres(db, uid)


async def rechercher_utilisateurs(db: AsyncSession, q: str) -> list[dict]:
    motif = f"%{propre(q)}%"
    users = (await db.scalars(
        select(User).where(User.is_active.is_(True), User.deleted_at.is_(None),
                           (User.full_name.ilike(motif)) | (User.email.ilike(motif)))
        .order_by(User.full_name).limit(20))).all()
    out = []
    for u in users:
        perms = permissions_effectives(await load_user_permission_codes(db, u))
        out.append({"id": str(u.id), "nom": u.full_name, "email": u.email,
                    "acces_module": "reclamations.view" in perms})
    return out
