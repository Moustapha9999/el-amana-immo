"""Base clientèle — CLIENT (racine ORION) / COMPTE / RIB (docs/conformite/clientele-phase1.md).

Une ligne de l'État Compte ORION représente un compte ; le client est consolidé sur
``racine_client`` (6 chiffres, chaîne, zéros initiaux conservés). Client 1 ── N comptes.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class _Provenance:
    source: Mapped[str] = mapped_column(String(30), default="ORION_ETAT_COMPTE", server_default="ORION_ETAT_COMPTE")
    premiere_extraction: Mapped[date] = mapped_column(Date)
    date_extraction: Mapped[date] = mapped_column(Date)


class ClienteleClient(UUIDPrimaryKeyMixin, TimestampMixin, _Provenance, Base):
    __tablename__ = "clientele_clients"
    __table_args__ = (
        UniqueConstraint("racine_client", name="uq_clientele_clients_racine"),
        CheckConstraint("racine_client ~ '^[0-9]{6}$'", name="ck_clientele_clients_racine"),
        CheckConstraint("statut_resident IS NULL OR statut_resident IN ('R','N')",
                        name="ck_clientele_clients_resident"),
        CheckConstraint("type_identifiant IS NULL OR type_identifiant IN ('NNI','NIF')",
                        name="ck_clientele_clients_type_identifiant"),
        CheckConstraint("type_client IS NULL OR type_client IN ('PP','PM_PRIVEE','PM_PUBLIQUE','ASSOCIATION')",
                        name="ck_clientele_clients_type_client"),
        CheckConstraint("date_extraction >= premiere_extraction", name="ck_clientele_clients_extraction"),
        Index("ix_clientele_clients_raison_sociale", "raison_sociale"),
        Index("ix_clientele_clients_nni", "nni"),
        Index("ix_clientele_clients_nif", "nif"),
        Index("ix_clientele_clients_type_client", "type_client"),
    )

    racine_client: Mapped[str] = mapped_column(String(6))
    raison_sociale: Mapped[str] = mapped_column(String(255))
    prenoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_naissance: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Valeur brute : ORION concatène plusieurs dates pour les comptes à plusieurs titulaires.
    date_naissance_orion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nationalite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    statut_resident: Mapped[str | None] = mapped_column(String(1), nullable=True)
    agent_economique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    situation_juridique: Mapped[str | None] = mapped_column(String(120), nullable=True)
    categorie_juridique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secteur_activite: Mapped[str | None] = mapped_column(String(160), nullable=True)
    famille_secteur_activite: Mapped[str | None] = mapped_column(String(120), nullable=True)
    type_identifiant: Mapped[str | None] = mapped_column(String(3), nullable=True)
    identifiant_orion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nni: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nif: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rcs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Renseigné par la classification (phase 3), jamais déduit à l'import.
    type_client: Mapped[str | None] = mapped_column(String(20), nullable=True)

    comptes: Mapped[list[ClienteleCompte]] = relationship(back_populates="client", order_by="ClienteleCompte.compte")


class ClienteleCompte(UUIDPrimaryKeyMixin, TimestampMixin, _Provenance, Base):
    __tablename__ = "clientele_comptes"
    __table_args__ = (
        UniqueConstraint("compte", name="uq_clientele_comptes_compte"),
        UniqueConstraint("rib", name="uq_clientele_comptes_rib"),
        CheckConstraint("compte ~ '^[0-9]{11}$'", name="ck_clientele_comptes_compte"),
        CheckConstraint("rib ~ '^[0-9]{23}$'", name="ck_clientele_comptes_rib"),
        CheckConstraint("substr(rib, 11, 11) = compte", name="ck_clientele_comptes_rib_compte"),
        CheckConstraint("etat_compte IN ('OUVERT','FERME')", name="ck_clientele_comptes_etat"),
        CheckConstraint("devise ~ '^[A-Z]{3}$'", name="ck_clientele_comptes_devise"),
        CheckConstraint("conformite_compte IS NULL OR conformite_compte IN ('CONFORME','NON_CONFORME')",
                        name="ck_clientele_comptes_conformite"),
        CheckConstraint("date_extraction >= premiere_extraction", name="ck_clientele_comptes_extraction"),
        Index("ix_clientele_comptes_racine", "racine_client"),
        Index("ix_clientele_comptes_agence_etat", "agence_id", "etat_compte"),
    )

    compte: Mapped[str] = mapped_column(String(11))
    rib: Mapped[str] = mapped_column(String(23))
    racine_client: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT", onupdate="RESTRICT",
                   name="fk_clientele_comptes_racine"),
    )
    agence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id", ondelete="RESTRICT", name="fk_clientele_comptes_agence"))
    ncg: Mapped[str | None] = mapped_column(String(6), nullable=True)
    rubrique_comptable: Mapped[str | None] = mapped_column(String(80), nullable=True)
    etat_compte: Mapped[str] = mapped_column(String(10))
    date_ouverture: Mapped[date | None] = mapped_column(Date, nullable=True)
    ddc: Mapped[date | None] = mapped_column(Date, nullable=True)
    ddd: Mapped[date | None] = mapped_column(Date, nullable=True)
    devise: Mapped[str] = mapped_column(String(3))
    conformite_compte: Mapped[str | None] = mapped_column(String(15), nullable=True)
    liste_interdiction: Mapped[str | None] = mapped_column(Text, nullable=True)

    client: Mapped[ClienteleClient] = relationship(back_populates="comptes")


def _user_fk() -> Mapped:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ClienteleImport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_imports"
    __table_args__ = (
        CheckConstraint("statut IN ('ANALYSE','IMPORTE','ABANDONNE')", name="ck_clientele_imports_statut"),
    )

    fichier_nom: Mapped[str] = mapped_column(String(255))
    fichier_sha256: Mapped[str] = mapped_column(String(64), index=True)
    statut: Mapped[str] = mapped_column(String(20), default="ANALYSE")
    date_extraction: Mapped[date | None] = mapped_column(Date, nullable=True)
    nb_lignes: Mapped[int] = mapped_column(Integer, default=0)
    nb_clients: Mapped[int] = mapped_column(Integer, default=0)
    nb_comptes: Mapped[int] = mapped_column(Integer, default=0)
    nb_rejets: Mapped[int] = mapped_column(Integer, default=0)
    nb_anomalies: Mapped[int] = mapped_column(Integer, default=0)
    clients_crees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clients_maj: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comptes_crees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comptes_maj: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analyse: Mapped[dict] = mapped_column(JSONB, default=dict)
    resultat: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    importe_par_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    importe_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClienteleImportLigne(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_import_lignes"
    __table_args__ = (
        UniqueConstraint("import_id", "numero_ligne", name="uq_clientele_import_lignes_num"),
        CheckConstraint("statut_ligne IN ('VALIDE','REJETEE')", name="ck_clientele_import_lignes_statut"),
        Index("ix_clientele_import_lignes_import", "import_id"),
        Index("ix_clientele_import_lignes_racine", "import_id", "racine_client"),
        Index("ix_clientele_import_lignes_compte", "import_id", "compte"),
    )

    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_imports.id", ondelete="CASCADE"))
    numero_ligne: Mapped[int] = mapped_column(Integer)
    statut_ligne: Mapped[str] = mapped_column(String(10))
    motifs: Mapped[str | None] = mapped_column(Text, nullable=True)
    racine_client: Mapped[str | None] = mapped_column(String(6), nullable=True)
    raison_sociale: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prenoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_naissance: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_naissance_orion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nationalite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    statut_resident: Mapped[str | None] = mapped_column(String(1), nullable=True)
    agent_economique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    situation_juridique: Mapped[str | None] = mapped_column(String(120), nullable=True)
    categorie_juridique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secteur_activite: Mapped[str | None] = mapped_column(String(160), nullable=True)
    famille_secteur_activite: Mapped[str | None] = mapped_column(String(120), nullable=True)
    type_identifiant: Mapped[str | None] = mapped_column(String(3), nullable=True)
    identifiant_orion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nni: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nif: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rcs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    compte: Mapped[str | None] = mapped_column(String(11), nullable=True)
    rib: Mapped[str | None] = mapped_column(String(23), nullable=True)
    code_agence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    etat_compte: Mapped[str | None] = mapped_column(String(10), nullable=True)
    devise: Mapped[str | None] = mapped_column(String(3), nullable=True)
    ncg: Mapped[str | None] = mapped_column(String(6), nullable=True)
    rubrique_comptable: Mapped[str | None] = mapped_column(String(80), nullable=True)
    date_ouverture: Mapped[date | None] = mapped_column(Date, nullable=True)
    ddc: Mapped[date | None] = mapped_column(Date, nullable=True)
    ddd: Mapped[date | None] = mapped_column(Date, nullable=True)
    conformite_compte: Mapped[str | None] = mapped_column(String(15), nullable=True)
    liste_interdiction: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClienteleImportAnomalie(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_import_anomalies"
    __table_args__ = (
        Index("ix_clientele_import_anomalies_import", "import_id"),
        Index("ix_clientele_import_anomalies_code", "import_id", "code"),
    )

    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_imports.id", ondelete="CASCADE"))
    numero: Mapped[int] = mapped_column(Integer)
    racine_client: Mapped[str | None] = mapped_column(String(6), nullable=True)
    code: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    bloquante: Mapped[bool] = mapped_column(Boolean, default=False)


class ClienteleSituation(Base):
    """Vue PostgreSQL — une ligne par racine, jamais une table copiée."""

    __tablename__ = "clientele_situation"
    __table_args__ = {"info": {"is_view": True}}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    racine_client: Mapped[str] = mapped_column(String(6), primary_key=True)
    nom_client: Mapped[str] = mapped_column(String(255))
    prenoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    nationalite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    statut_resident: Mapped[str | None] = mapped_column(String(1), nullable=True)
    nni: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nif: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rcs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type_identifiant: Mapped[str | None] = mapped_column(String(3), nullable=True)
    identifiant_orion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    categorie_juridique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    situation_juridique: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_economique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secteur_activite: Mapped[str | None] = mapped_column(String(160), nullable=True)
    famille_secteur_activite: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_naissance: Mapped[date | None] = mapped_column(Date, nullable=True)
    type_client: Mapped[str | None] = mapped_column(String(20), nullable=True)
    profil_derive: Mapped[str] = mapped_column(String(20))
    etat_client: Mapped[str] = mapped_column(String(10))
    date_ouverture: Mapped[date | None] = mapped_column(Date, nullable=True)
    code_agence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    agence: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nb_comptes: Mapped[int] = mapped_column(Integer)
    nb_comptes_ouverts: Mapped[int] = mapped_column(Integer)
    nb_agences: Mapped[int] = mapped_column(Integer)
    date_extraction: Mapped[date] = mapped_column(Date)
    premiere_extraction: Mapped[date] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClienteleImportClient(UUIDPrimaryKeyMixin, Base):
    """Photographie client d'un import confirmé (extraction, pas le stock vivant)."""

    __tablename__ = "clientele_import_clients"
    __table_args__ = (UniqueConstraint("import_id", "racine_client", name="uq_clientele_import_clients"),)

    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_imports.id", ondelete="CASCADE"))
    racine_client: Mapped[str] = mapped_column(String(6))
    raison_sociale: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prenoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    nationalite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    statut_resident: Mapped[str | None] = mapped_column(String(1), nullable=True)
    agent_economique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    situation_juridique: Mapped[str | None] = mapped_column(String(120), nullable=True)
    categorie_juridique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secteur_activite: Mapped[str | None] = mapped_column(String(160), nullable=True)
    famille_secteur_activite: Mapped[str | None] = mapped_column(String(120), nullable=True)
    type_identifiant: Mapped[str | None] = mapped_column(String(3), nullable=True)
    nni: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nif: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rcs: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ClienteleImportCompte(UUIDPrimaryKeyMixin, Base):
    """Photographie compte d'un import confirmé. Clé de rapprochement = RIB."""

    __tablename__ = "clientele_import_comptes"
    __table_args__ = (UniqueConstraint("import_id", "rib", name="uq_clientele_import_comptes_rib"),)

    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_imports.id", ondelete="CASCADE"))
    rib: Mapped[str] = mapped_column(String(23))
    compte: Mapped[str | None] = mapped_column(String(11), nullable=True)
    racine_client: Mapped[str] = mapped_column(String(6))
    code_agence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    etat_compte: Mapped[str | None] = mapped_column(String(10), nullable=True)
    devise: Mapped[str | None] = mapped_column(String(3), nullable=True)
    ncg: Mapped[str | None] = mapped_column(String(6), nullable=True)
    conformite_compte: Mapped[str | None] = mapped_column(String(15), nullable=True)
    liste_interdiction: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_ouverture: Mapped[date | None] = mapped_column(Date, nullable=True)


class ClienteleRapprochement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_rapprochements"
    __table_args__ = (
        UniqueConstraint("import_a_id", "import_b_id", name="uq_clientele_rapprochements_paire"),
    )

    import_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_imports.id", ondelete="CASCADE"))
    import_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_imports.id", ondelete="CASCADE"))
    synthese: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClienteleRapprochementEcart(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_rapprochement_ecarts"

    rapprochement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_rapprochements.id", ondelete="CASCADE"))
    objet: Mapped[str] = mapped_column(String(10))
    categorie: Mapped[str] = mapped_column(String(24))
    racine_client: Mapped[str | None] = mapped_column(String(6), nullable=True)
    rib: Mapped[str | None] = mapped_column(String(23), nullable=True)
    champ: Mapped[str | None] = mapped_column(String(40), nullable=True)
    libelle_champ: Mapped[str | None] = mapped_column(String(80), nullable=True)
    valeur_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    valeur_b: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ClienteleClassifNiveau(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_niveaux"

    code: Mapped[str] = mapped_column(String(12), unique=True)
    libelle: Mapped[str] = mapped_column(String(40))
    rang: Mapped[int] = mapped_column(Integer)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class ClienteleClassifCritere(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_criteres"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    libelle: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    champ_defaut: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class ClienteleClassifVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_versions"

    numero: Mapped[int] = mapped_column(Integer, unique=True)
    libelle: Mapped[str] = mapped_column(String(160))
    mode: Mapped[str] = mapped_column(String(16), default="MAX_NIVEAU")
    seuils: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    date_effet: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    statut: Mapped[str] = mapped_column(String(16), default="BROUILLON")
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    regles: Mapped[list[ClienteleClassifRegle]] = relationship(back_populates="version")


class ClienteleClassifRegle(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_regles"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_classif_versions.id", ondelete="CASCADE"))
    critere_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_classif_criteres.id", ondelete="RESTRICT"))
    priorite: Mapped[int] = mapped_column(Integer, default=100)
    poids: Mapped[int] = mapped_column(Integer, default=0)
    niveau_cible: Mapped[str] = mapped_column(String(12))
    operateur: Mapped[str] = mapped_column(String(24))
    champ_source: Mapped[str] = mapped_column(String(40))
    portee: Mapped[str] = mapped_column(String(10), default="CLIENT")
    valeur: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    motif: Mapped[str] = mapped_column(Text)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[ClienteleClassifVersion] = relationship(back_populates="regles")
    critere: Mapped[ClienteleClassifCritere] = relationship()


class ClienteleClassification(Base):
    """Classification courante du CLIENT (racine). Jamais du RIB, sauf règle métier future."""

    __tablename__ = "clientele_classifications"

    racine_client: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT", onupdate="RESTRICT"),
        primary_key=True,
    )
    niveau: Mapped[str] = mapped_column(String(12))
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_classif_versions.id", ondelete="SET NULL"), nullable=True)
    motifs: Mapped[list] = mapped_column(JSONB, default=list)
    source: Mapped[str] = mapped_column(String(32))
    motif_risque: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif_classement: Mapped[str | None] = mapped_column(Text, nullable=True)
    classifie_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    classifie_par_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClienteleClassifHistorique(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_historique"

    racine_client: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT", onupdate="RESTRICT"))
    ancienne_classe: Mapped[str | None] = mapped_column(String(12), nullable=True)
    nouvelle_classe: Mapped[str] = mapped_column(String(12))
    motif_risque: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif_classement: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_classif_versions.id", ondelete="SET NULL"), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClienteleClassifDimension(UUIDPrimaryKeyMixin, Base):
    """Famille de risque (CLIENT, GEOGRAPHIE, PRODUIT_SERVICE_OPERATION, CANAL)."""

    __tablename__ = "clientele_classif_dimensions"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    libelle: Mapped[str] = mapped_column(String(120))
    ordre: Mapped[int] = mapped_column(Integer, default=0)


class ClienteleClassifValeur(UUIDPrimaryKeyMixin, Base):
    """Référentiel maître LOT 1 : Dimension → Critère → Valeur → Score → Niveau → Source.

    ``actif`` reste False tant que la Conformité n'a pas validé la ligne.
    """

    __tablename__ = "clientele_classif_valeurs"
    __table_args__ = (
        UniqueConstraint("dimension", "critere", "code", "version_regles",
                         name="uq_clientele_classif_valeurs"),
        Index("ix_clientele_classif_valeurs_dim", "dimension", "statut"),
    )

    dimension: Mapped[str] = mapped_column(String(40))
    critere: Mapped[str] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(String(80))
    libelle: Mapped[str] = mapped_column(String(255))
    score_v1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    niveau_v1: Mapped[str | None] = mapped_column(String(12), nullable=True)
    score_v4: Mapped[int | None] = mapped_column(Integer, nullable=True)
    niveau_v4: Mapped[str | None] = mapped_column(String(12), nullable=True)
    score_retenu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    niveau_retenu: Mapped[str | None] = mapped_column(String(12), nullable=True)
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(80))
    version_regles: Mapped[str] = mapped_column(String(40))
    conflit: Mapped[bool] = mapped_column(Boolean, default=False)
    statut: Mapped[str] = mapped_column(String(24), default="A_ARBITRER")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=False)


class ClienteleClassifPays(UUIDPrimaryKeyMixin, Base):
    """Référentiel pays versionné (Matrice Zone + V4 Pays Eng-FR). ISO non inventé."""

    __tablename__ = "clientele_classif_pays"
    __table_args__ = (UniqueConstraint("code", "version_regles", name="uq_clientele_classif_pays"),)

    code: Mapped[str] = mapped_column(String(48))
    nom_fr: Mapped[str] = mapped_column(String(160))
    nom_en: Mapped[str | None] = mapped_column(String(160), nullable=True)
    nationalite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    niveau_matrice: Mapped[str | None] = mapped_column(String(12), nullable=True)
    poids_pays_v4: Mapped[int | None] = mapped_column(Integer, nullable=True)
    niveau_pays_v4: Mapped[str | None] = mapped_column(String(12), nullable=True)
    poids_nationalite_v4: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label_v4: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    version_regles: Mapped[str] = mapped_column(String(40))


class ClienteleClassifSecteur(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_secteurs"
    __table_args__ = (UniqueConstraint("code", "version_regles", "origine", name="uq_clientele_classif_secteurs"),)

    code: Mapped[str] = mapped_column(String(80))
    libelle: Mapped[str] = mapped_column(String(255))
    famille: Mapped[str | None] = mapped_column(String(120), nullable=True)
    niveau_matrice: Mapped[str | None] = mapped_column(String(12), nullable=True)
    poids_v4: Mapped[int | None] = mapped_column(Integer, nullable=True)
    niveau_v4: Mapped[str | None] = mapped_column(String(12), nullable=True)
    origine: Mapped[str] = mapped_column(String(16))
    version_regles: Mapped[str] = mapped_column(String(40))


class ClienteleClassifForme(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_formes"
    __table_args__ = (UniqueConstraint("code", "version_regles", "origine", name="uq_clientele_classif_formes"),)

    code: Mapped[str] = mapped_column(String(80))
    libelle: Mapped[str] = mapped_column(String(160))
    profil: Mapped[str | None] = mapped_column(String(40), nullable=True)
    niveau_matrice: Mapped[str | None] = mapped_column(String(12), nullable=True)
    poids_v4: Mapped[int | None] = mapped_column(Integer, nullable=True)
    niveau_v4: Mapped[str | None] = mapped_column(String(12), nullable=True)
    origine: Mapped[str] = mapped_column(String(16))
    version_regles: Mapped[str] = mapped_column(String(40))


class ClienteleClassifDivergence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_divergences"
    __table_args__ = (
        Index("ix_clientele_classif_div_domaine", "domaine", "statut"),
    )

    domaine: Mapped[str] = mapped_column(String(40))
    cle: Mapped[str] = mapped_column(String(255))
    source_a: Mapped[str] = mapped_column(String(40))
    valeur_a: Mapped[str] = mapped_column(Text)
    source_b: Mapped[str] = mapped_column(String(40))
    valeur_b: Mapped[str] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(24), default="A_ARBITRER")
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_regles: Mapped[str] = mapped_column(String(40))
    validee_par_id: Mapped[uuid.UUID | None] = _user_fk()
    validee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClienteleClassifEvaluation(UUIDPrimaryKeyMixin, Base):
    """Photographie d'une évaluation. N'écrase pas la classification retenue."""

    __tablename__ = "clientele_classif_evaluations"
    __table_args__ = (
        Index("ix_clientele_classif_eval_racine", "racine_client", "created_at"),
    )

    racine_client: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT", onupdate="RESTRICT"))
    version_moteur: Mapped[str] = mapped_column(String(40))
    version_regles: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(16), default="SCORE")
    score_total: Mapped[int] = mapped_column(Integer, default=0)
    nb_evalues: Mapped[int] = mapped_column(Integer, default=0)
    niveau_score: Mapped[str | None] = mapped_column(String(12), nullable=True)
    niveau_score_v4: Mapped[str | None] = mapped_column(String(12), nullable=True)
    niveau_max: Mapped[str | None] = mapped_column(String(12), nullable=True)
    niveau_final: Mapped[str | None] = mapped_column(String(12), nullable=True)
    statut: Mapped[str] = mapped_column(String(24))
    coherence: Mapped[str] = mapped_column(String(24))
    motif_principal: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lignes: Mapped[list[ClienteleClassifEvaluationLigne]] = relationship(
        "ClienteleClassifEvaluationLigne", back_populates="evaluation", cascade="all, delete-orphan")


class ClienteleClassifEvaluationLigne(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_classif_evaluation_lignes"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_classif_evaluations.id", ondelete="CASCADE"))
    critere: Mapped[str] = mapped_column(String(40))
    libelle: Mapped[str] = mapped_column(String(160))
    etat: Mapped[str] = mapped_column(String(24))
    valeur: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_donnee: Mapped[str | None] = mapped_column(String(40), nullable=True)
    poids: Mapped[int | None] = mapped_column(Integer, nullable=True)
    niveau_matrice: Mapped[str | None] = mapped_column(String(12), nullable=True)
    niveau_v4: Mapped[str | None] = mapped_column(String(12), nullable=True)
    niveau_retenu: Mapped[str | None] = mapped_column(String(12), nullable=True)
    type_decision: Mapped[str] = mapped_column(String(16), default="SCORE")
    motif: Mapped[str] = mapped_column(Text)
    divergence: Mapped[bool] = mapped_column(Boolean, default=False)
    blocking_propose: Mapped[bool] = mapped_column(Boolean, default=False)
    statut_regle: Mapped[str] = mapped_column(String(24), default="A_ARBITRER")
    famille: Mapped[str] = mapped_column(String(40), default="CLIENT")
    contribue_au_score: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluation: Mapped[ClienteleClassifEvaluation] = relationship(back_populates="lignes")


class ClienteleFiltrageListe(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_filtrage_listes"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    libelle: Mapped[str] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(40), default="INTERNE")
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    entrees: Mapped[list[ClienteleFiltrageEntree]] = relationship(back_populates="liste")


class ClienteleFiltrageEntree(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_filtrage_entrees"

    liste_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_filtrage_listes.id", ondelete="CASCADE"))
    nom: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prenom: Mapped[str | None] = mapped_column(String(160), nullable=True)
    raison_sociale: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_naissance: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationalite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    identifiant: Mapped[str | None] = mapped_column(String(80), nullable=True)
    type_identifiant: Mapped[str | None] = mapped_column(String(12), nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    liste: Mapped[ClienteleFiltrageListe] = relationship(back_populates="entrees")


class ClienteleAlerte(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_alertes"

    racine_client: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT", onupdate="RESTRICT"))
    statut: Mapped[str] = mapped_column(String(24), default="NOUVELLE")
    motif: Mapped[str] = mapped_column(String(40))
    empreinte: Mapped[str] = mapped_column(String(80))
    score: Mapped[int] = mapped_column(Integer, default=100)
    correspondance: Mapped[dict] = mapped_column(JSONB, default=dict)
    precedent_faux_positif: Mapped[bool] = mapped_column(Boolean, default=False)
    assignee_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cloturee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClienteleAlerteEvenement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_alerte_evenements"

    alerte_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_alertes.id", ondelete="CASCADE"))
    statut: Mapped[str] = mapped_column(String(24))
    decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClienteleAlerteJustificatif(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clientele_alerte_justificatifs"

    alerte_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_alertes.id", ondelete="CASCADE"))
    nom_fichier: Mapped[str] = mapped_column(String(255))
    chemin: Mapped[str] = mapped_column(String(400))
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClienteleDeclarationBcm(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Déclaration mensuelle BCM. Une VALIDEE ne se recalcule plus (snapshot JSON)."""

    __tablename__ = "clientele_declarations_bcm"
    __table_args__ = (
        UniqueConstraint("annee", "mois", name="uq_clientele_declarations_bcm_periode"),
        CheckConstraint("mois BETWEEN 1 AND 12", name="ck_clientele_declarations_bcm_mois"),
        CheckConstraint(
            "statut IN ('BROUILLON','CALCULEE','A_CONTROLER','VALIDEE','CLOTUREE','ARCHIVEE')",
            name="ck_clientele_declarations_bcm_statut",
        ),
        Index("ix_clientele_declarations_bcm_statut", "statut"),
    )

    annee: Mapped[int] = mapped_column(Integer)
    mois: Mapped[int] = mapped_column(Integer)
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date] = mapped_column(Date)
    fin_mois_precedent: Mapped[date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(20), default="BROUILLON")
    moteur_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    grille_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cellules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    controles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    populations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    calculee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calculee_par_id: Mapped[uuid.UUID | None] = _user_fk()
    controlee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    controlee_par_id: Mapped[uuid.UUID | None] = _user_fk()
    validee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validee_par_id: Mapped[uuid.UUID | None] = _user_fk()
    cloturee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cloturee_par_id: Mapped[uuid.UUID | None] = _user_fk()
    archivee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClienteleFiltrageEmpreinte(UUIDPrimaryKeyMixin, Base):
    """Décisions antérieures (faux positifs notamment) retrouvées à une nouvelle occurrence."""

    __tablename__ = "clientele_filtrage_empreintes"
    __table_args__ = (
        UniqueConstraint("racine_client", "empreinte", "decision", name="uq_clientele_filtrage_empreintes"),
    )

    racine_client: Mapped[str] = mapped_column(String(6))
    empreinte: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(24))
    alerte_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientele_alertes.id", ondelete="SET NULL"), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
