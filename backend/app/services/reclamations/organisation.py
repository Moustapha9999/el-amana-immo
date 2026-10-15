"""Référentiels (types, motifs, sous-motifs, canaux) et unités organisationnelles du module.

Référentiel : une valeur désactivée ou supprimée n'est plus proposée à la saisie. La suppression
est physique si la valeur n'a jamais servi, logique sinon (les dossiers gardent leur libellé) ;
supprimer un type supprime ses motifs et sous-motifs. Une unité utilisée se désactive seulement.
Toute écriture est auditée (avant / après).
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agence, OrgEntite, ReclamationReferentiel, ReclamationUnite, ReclamationUniteMembre, User
from app.services import org_referentiel as org
from app.services.permission_service import load_user_permission_codes
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope, permissions_effectives
from app.services.reclamations.outils import (
    auditer,
    cle,
    code_propre,
    conflit,
    erreur,
    iso,
    maintenant,
    propre,
    texte_long,
)


# ------------------------------------------------------------------ référentiels
# Nomenclature soumise à validation de la banque (les canaux sont des listes techniques).
DOMAINES_A_VALIDER = frozenset({"TYPE", "MOTIF", "SOUS_MOTIF"})


def referentiel_dict(r: ReclamationReferentiel, usage: int = 0) -> dict:
    a_valider = r.domaine in DOMAINES_A_VALIDER
    statut = r.statut_validation or "PROPOSEE"
    return {
        "id": str(r.id), "domaine": r.domaine, "code": r.code, "libelle": r.libelle,
        "parent_id": str(r.parent_id) if r.parent_id else None, "description": r.description,
        "ordre": r.ordre, "actif": r.actif, "usage": usage,
        "a_valider": a_valider,
        "statut_validation": statut if a_valider else None,
        "statut_validation_libelle": C.VALIDATION_REFERENTIEL_LIBELLES.get(statut) if a_valider else None,
        "valide_le": iso(r.valide_le) if a_valider else None,
    }


_USAGES_DOSSIERS = """
          SELECT type_id AS id, count(*) n FROM reclamations WHERE type_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT motif_id, count(*) FROM reclamations WHERE motif_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT sous_motif_id, count(*) FROM reclamations WHERE sous_motif_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT canal_id, count(*) FROM reclamations GROUP BY 1
          UNION ALL SELECT canal_envoi_id, count(*) FROM reclamation_reponses WHERE canal_envoi_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT type_id, count(*) FROM reclamation_regles_delai WHERE type_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT motif_id, count(*) FROM reclamation_regles_delai WHERE motif_id IS NOT NULL GROUP BY 1
          UNION ALL SELECT sous_motif_id, count(*) FROM reclamation_regles_delai WHERE sous_motif_id IS NOT NULL GROUP BY 1"""


async def _usages_referentiels(db: AsyncSession, *, avec_enfants: bool = True) -> dict[uuid.UUID, int]:
    """Utilisations par dossiers, réponses et règles ; ``avec_enfants`` ajoute les valeurs rattachées visibles."""
    enfants = ("\n          UNION ALL SELECT parent_id, count(*) FROM reclamation_referentiels "
               "WHERE parent_id IS NOT NULL AND supprime_le IS NULL GROUP BY 1") if avec_enfants else ""
    sql = text(f"SELECT id, sum(n)::int FROM ({_USAGES_DOSSIERS}{enfants}\n        ) u GROUP BY id")
    return {row[0]: row[1] for row in (await db.execute(sql)).all()}


async def lister_referentiels(db: AsyncSession, domaine: str | None = None) -> list[dict]:
    q = select(ReclamationReferentiel).where(ReclamationReferentiel.supprime_le.is_(None)).order_by(
        ReclamationReferentiel.domaine, ReclamationReferentiel.ordre, ReclamationReferentiel.libelle)
    if domaine:
        q = q.where(ReclamationReferentiel.domaine == domaine)
    usages = await _usages_referentiels(db)
    return [referentiel_dict(r, usages.get(r.id, 0)) for r in (await db.scalars(q)).all()]


async def _referentiel(db: AsyncSession, rid: uuid.UUID) -> ReclamationReferentiel:
    r = await db.get(ReclamationReferentiel, rid)
    if r is None or r.supprime_le is not None:
        raise erreur("Valeur de référentiel introuvable", "NOT_FOUND", 404)
    return r


async def _verifier_unicite(db: AsyncSession, domaine: str, parent_id: uuid.UUID | None, libelle: str,
                            code: str | None, exclure: uuid.UUID | None = None
                            ) -> ReclamationReferentiel | None:
    """Refuse un doublon visible ; renvoie la valeur supprimée de même libellé (à restaurer), s'il y en a une."""
    q = select(ReclamationReferentiel).where(
        ReclamationReferentiel.domaine == domaine, ReclamationReferentiel.cle == cle(libelle),
        ReclamationReferentiel.parent_id.is_(None) if parent_id is None
        else ReclamationReferentiel.parent_id == parent_id)
    if exclure:
        q = q.where(ReclamationReferentiel.id != exclure)
    existant = await db.scalar(q)
    supprime = existant if existant is not None and existant.supprime_le is not None else None
    if existant is not None and supprime is None:
        etat = "" if existant.actif else " (désactivée — réactivez-la)"
        raise conflit(f"« {existant.libelle} » existe déjà{etat}", "REFERENTIEL_EXISTANT",
                      existant=referentiel_dict(existant))
    if supprime is not None and exclure:
        raise conflit(f"« {supprime.libelle} » a été supprimé : recréez-le pour le restaurer",
                      "REFERENTIEL_SUPPRIME")
    if code:
        q = select(ReclamationReferentiel.id).where(
            ReclamationReferentiel.domaine == domaine, ReclamationReferentiel.code == code)
        for autre in (exclure, supprime.id if supprime else None):
            if autre:
                q = q.where(ReclamationReferentiel.id != autre)
        if await db.scalar(q):
            raise conflit(f"Le code {code} est déjà utilisé dans ce référentiel", "CODE_EXISTANT")
    return supprime


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
    supprime = await _verifier_unicite(db, domaine, parent_id, libelle, code)
    if supprime is not None:
        # Recréer une valeur supprimée la restaure : les dossiers qui la portent la retrouvent.
        supprime.supprime_le, supprime.supprime_par_id, supprime.actif = None, None, True
        supprime.libelle, supprime.code = libelle, code or supprime.code
        if data.get("description") is not None:
            supprime.description = texte_long(data["description"])
        supprime.updated_by_id = s.user_id
        await db.flush()
        apres = referentiel_dict(supprime)
        await auditer(db, s, "reclamations.referentiel.restore", "reclamation_referentiel", supprime.id, after=apres)
        return apres
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
    if libelle != r.libelle and r.statut_validation == "VALIDEE":
        # Un libellé validé qui change redevient une proposition : la banque n'a pas validé le nouveau.
        r.statut_validation, r.valide_par_id, r.valide_le = "PROPOSEE", None, None
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


async def valider_referentiel(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    """Validation (ou retour en proposition) d'un type, motif ou sous-motif par la banque."""
    s.exiger("reclamations.references.validate")
    r = await _referentiel(db, rid)
    if r.domaine not in DOMAINES_A_VALIDER:
        raise erreur("Ce référentiel n'est pas soumis à validation", "VALIDATION_NON_APPLICABLE")
    statut = data["statut_validation"]
    avant = referentiel_dict(r)
    if statut == "VALIDEE":
        if r.parent_id:
            parent = await _referentiel(db, r.parent_id)
            if parent.statut_validation != "VALIDEE":
                raise conflit(f"Validez d'abord « {parent.libelle} » ({C.DOMAINE_LIBELLES[parent.domaine].lower()})",
                              "PARENT_NON_VALIDE")
        r.valide_par_id, r.valide_le = s.user_id, maintenant()
    else:
        enfants = await db.scalar(select(func.count()).where(
            ReclamationReferentiel.parent_id == r.id, ReclamationReferentiel.statut_validation == "VALIDEE"))
        if enfants:
            raise conflit("Des valeurs rattachées sont validées : repassez-les d'abord en proposition",
                          "ENFANTS_VALIDES")
        r.valide_par_id, r.valide_le = None, None
    r.statut_validation = statut
    r.updated_by_id = s.user_id
    await db.flush()
    apres = referentiel_dict(r)
    await auditer(db, s, "reclamations.referentiel.validate", "reclamation_referentiel", r.id,
                  before=avant, after={**apres, "commentaire": texte_long(data.get("commentaire"))})
    return apres


async def supprimer_referentiel(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID) -> dict:
    """Supprime la valeur et ses descendants (motifs, sous-motifs).

    Physique pour ce qui n'a jamais servi ; logique (``supprime_le``) pour une valeur portée par un
    dossier, une réponse ou une règle — ou parent d'une telle valeur — afin de conserver l'historique."""
    s.exiger("reclamations.references.manage")
    r = await _referentiel(db, rid)
    tous = list((await db.scalars(select(ReclamationReferentiel))).all())
    enfants: dict[uuid.UUID, list[ReclamationReferentiel]] = defaultdict(list)
    for x in tous:
        if x.parent_id:
            enfants[x.parent_id].append(x)
    usages = await _usages_referentiels(db, avec_enfants=False)
    physiques: list[ReclamationReferentiel] = []
    logiques: list[ReclamationReferentiel] = []

    def parcourir(x: ReclamationReferentiel) -> bool:
        effacables = [parcourir(e) for e in enfants[x.id]]
        if all(effacables) and not usages.get(x.id):
            physiques.append(x)
            return True
        logiques.append(x)
        return False

    parcourir(r)
    avant = referentiel_dict(r)
    now = maintenant()
    for x in logiques:
        if x.supprime_le is None:
            x.supprime_le, x.supprime_par_id = now, s.user_id
        x.actif, x.updated_by_id = False, s.user_id
    for x in physiques:
        await db.delete(x)
        await db.flush()
    await db.flush()
    resultat = {"id": str(rid), "libelle": r.libelle, "supprimes": len(physiques), "conserves": len(logiques)}
    await auditer(db, s, "reclamations.referentiel.delete", "reclamation_referentiel", rid, before=avant,
                  after={"supprimes_definitivement": [x.libelle for x in physiques],
                         "masques_historique_conserve": [x.libelle for x in logiques]})
    return resultat


# ---------------------------------------------------------------------- unités
def unite_dict(u: ReclamationUnite, *, agences: dict[uuid.UUID, str] | None = None,
               membres: int = 0, dossiers: int = 0, arbre: org.Arbre | None = None) -> dict:
    return {
        "id": str(u.id), "type_unite": u.type_unite, "type_libelle": C.TYPE_UNITE_LIBELLES.get(u.type_unite),
        "code": u.code, "libelle": u.libelle, "parent_id": str(u.parent_id) if u.parent_id else None,
        "agence_id": str(u.agence_id) if u.agence_id else None,
        "agence": (agences or {}).get(u.agence_id) if u.agence_id else None,
        "org_entite_id": str(u.org_entite_id) if u.org_entite_id else None,
        "org_entite": arbre.libelle_chemin(u.org_entite_id) if arbre and u.org_entite_id else None,
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
    arbre = await org.charger_arbre(db)
    return [unite_dict(u, agences=agences, membres=membres.get(u.id, 0), dossiers=dossiers.get(u.id, 0),
                       arbre=arbre) for u in unites]


async def unites_de_entite(db: AsyncSession, entite_id: uuid.UUID) -> tuple[list[uuid.UUID], str | None]:
    """Unités Réclamations rattachées à une entité de l'organigramme ou à l'une de ses sous-entités."""
    arbre = await org.charger_arbre(db)
    if entite_id not in arbre.entites:
        raise erreur("Entité de l'organigramme introuvable", "ENTITE_INCONNUE", 404)
    ids = arbre.descendants(entite_id)
    unites = list((await db.scalars(select(ReclamationUnite.id).where(
        ReclamationUnite.org_entite_id.in_(ids)))).all())
    return unites, arbre.libelle_chemin(entite_id)


async def _verifier_entite_org(db: AsyncSession, entite_id: uuid.UUID) -> None:
    e = await db.get(OrgEntite, entite_id)
    if e is None or e.deleted_at is not None:
        raise erreur("Entité de l'organigramme introuvable", "ENTITE_INCONNUE")
    if not e.is_active:
        raise erreur(f"L'entité « {e.libelle} » est désactivée dans l'organigramme", "ENTITE_INACTIVE")


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
    if data.get("org_entite_id"):
        await _verifier_entite_org(db, data["org_entite_id"])
    ordre = await db.scalar(select(func.coalesce(func.max(ReclamationUnite.ordre), 0)))
    u = ReclamationUnite(
        type_unite=data["type_unite"], code=code_propre(data.get("code")), libelle=libelle, cle=cle(libelle),
        parent_id=data.get("parent_id"), agence_id=data.get("agence_id"),
        org_entite_id=data.get("org_entite_id"), est_service_reclamations=False,
        email=propre(data.get("email")) or None, description=texte_long(data.get("description")),
        ordre=(ordre or 0) + 1, actif=True, created_by_id=s.user_id, updated_by_id=s.user_id)
    db.add(u)
    await db.flush()
    apres = unite_dict(u, agences=await _agences(db), arbre=await org.charger_arbre(db))
    await auditer(db, s, "reclamations.unite.create", "reclamation_unite", u.id, after=apres)
    return apres


async def modifier_unite(db: AsyncSession, s: ReclamationsScope, uid: uuid.UUID, data: dict) -> dict:
    s.exiger("reclamations.services.manage")
    u = await _unite(db, uid)
    agences = await _agences(db)
    arbre = await org.charger_arbre(db)
    avant = unite_dict(u, agences=agences, arbre=arbre)
    if data.get("detacher_org_entite"):
        u.org_entite_id = None
    elif data.get("org_entite_id"):
        await _verifier_entite_org(db, data["org_entite_id"])
        u.org_entite_id = data["org_entite_id"]
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
    apres = unite_dict(u, agences=agences, arbre=arbre)
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
