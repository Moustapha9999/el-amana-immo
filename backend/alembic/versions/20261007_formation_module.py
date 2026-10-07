"""Formation & Sensibilisation (Conformité) — tables formation_*, module ``formation``, référentiels.

Additif : aucune table existante modifiée. Module rattaché au domaine
« Conformité & sécurité financière » du département Audit, Contrôle & Conformité.
Référentiels initiaux repris du fichier « Suivi des formations conformité » (feuille
« List entité » nettoyée) : insérés si absents, jamais réécrits — l'écran Référentiels
reste ensuite la source de vérité.

Revision ID: 20261007_formation_module
Revises: 20261007_fournisseurs_code_seq
"""

import re
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261007_formation_module"
down_revision: Union[str, None] = "20261007_fournisseurs_code_seq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESPACE_CODE = "audit-controle-conformite"
DOMAINE_CODE = "conformite-securite-financiere"
MODULE_CODE = "formation"

THEMES = [
    "LBC FT", "Procédure EER", "Fiabilisation", "Remédiation", "FATCA",
    "Gestion Archivage des EER", "Procédure ouverture de compte", "Projet fiabilisation",
]
LIEUX = ["Nouakchott", "Nouadhibou", "Rosso", "Mberra", "Tintane", "Zouerate", "Chami", "Kiffa", "Guerou"]
FORMATEURS = [
    "Abass Ngam", "Fatimata Thiam", "Mohamed Lemrabott", "Fatimata Diallo", "Yero Dieng",
    "Bah Med Salem", "Sidi Mohamed", "Cheikh Nanni", "Sidi Med El Hadramy", "Mohamedou Chewaf",
]
FONCTIONS = [
    "Agent d'accueil", "Chargée d'accueil", "Hôtesse d'accueil", "Secrétaire", "Agent de saisie",
    "Agent de guichet", "Chargé de clientèle", "Chargée de clientèle", "Conseiller clientèle",
    "Chargé d'affaires", "Chargée d'affaires", "Caissier", "Caissière", "Caissier principal",
    "Caissière principale", "Caissier secondaire", "Caissière secondaire", "Chef d'agence",
    "Chef de département", "Chef de service", "Contrôleur", "Responsable", "Directeur",
    "Assistante Trade", "Middle office", "Stagiaire",
]
NKC = "Nouakchott"
# (entité, périmètre, lieu par défaut)
ENTITES = [
    ("AGENCE CENTRALE PARTICULIERS", "DIRECTION COMMERCIALE", NKC),
    ("AGENCE CENTRALE ENTREPRISES", "DIRECTION COMMERCIALE", NKC),
    ("AGENCE ROUTE NDB", "DIRECTION COMMERCIALE", NKC),
    ("AGENCE TEVRAGH ZEINA", "DIRECTION COMMERCIALE", NKC),
    ("AGENCE MARCHE ETHMAN IBN AFFAN", "DIRECTION COMMERCIALE", NKC),
    ("AGENCE KSAR", "DIRECTION COMMERCIALE", NKC),
    ("AGENCE MOCTAR DADDAH", "DIRECTION COMMERCIALE", NKC),
    ("AGENCE SEBKHA", "DIRECTION COMMERCIALE", NKC),
    ("AGENCE NOUADHIBOU", "DIRECTION COMMERCIALE", "Nouadhibou"),
    ("AGENCE CHAMI", "DIRECTION COMMERCIALE", "Chami"),
    ("AGENCE ROSSO", "DIRECTION COMMERCIALE", "Rosso"),
    ("AGENCE MBERRA", "DIRECTION COMMERCIALE", "Mberra"),
    ("AGENCE TINTANE", "DIRECTION COMMERCIALE", "Tintane"),
    ("AGENCE KIFFA", "DIRECTION COMMERCIALE", "Kiffa"),
    ("AGENCE GUEROU", "DIRECTION COMMERCIALE", "Guerou"),
    ("AGENCE ZOUERATE", "DIRECTION COMMERCIALE", "Zouerate"),
    ("DIRECTION COMMERCIALE", "DIRECTION COMMERCIALE", NKC),
    ("VIREMENTS", "Département Domestique", NKC),
    ("COMPENSES", "Département Domestique", NKC),
    ("CREDITS", "BO ENGAGEMENT", NKC),
    ("MONETIQUES", "BO PRODUITS & SERVICES", NKC),
    ("CHEQUIERS", "BO PRODUITS & SERVICES", NKC),
    ("OPERATIONS INTERNATIONALES", "Département International", NKC),
    ("SALLE DE MARCHE", "SALLE DE MARCHE", NKC),
    ("MARKETING ET COMMUNICATION", "MARKETING & COMMUNICATION", NKC),
    ("COMPTABILITE", "COMPTABILITE", NKC),
    ("AMANTY", "AMANTY", NKC),
    ("DSI", "DSI", NKC),
    ("RESSOURCES HUMAINES", "RESSOURCES HUMAINES", NKC),
    ("ARCHIVES", "MOYENS GENERAUX", NKC),
    ("CASH PAYMENT", "CASH PAYMENT", NKC),
    ("RISQUES", "RISQUES", NKC),
    ("GARANTIES", "RISQUES", NKC),
    ("CONFORMITE", "CONFORMITE", NKC),
    ("CONTRÔLE PERMANENT", "CONTRÔLE PERMANENT", NKC),
    ("ORGANISATION", "ORGANISATION", NKC),
    ("CONTRÔLE PERIODIQUE", "AUDIT INTERNE", NKC),
    ("CONTRÔLE DE GESTION", "CONTRÔLE DE GESTION", NKC),
]


def _cle(texte: str) -> str:
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def _user(nom: str) -> sa.Column:
    return sa.Column(nom, sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    has = inspector.has_table

    if not has("formation_referentiels"):
        op.create_table(
            "formation_referentiels",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("domaine", sa.String(20), nullable=False),
            sa.Column("libelle", sa.String(200), nullable=False),
            sa.Column("cle", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
            sa.UniqueConstraint("domaine", "cle", name="uq_formation_referentiels_domaine_cle"),
            sa.CheckConstraint(
                "domaine IN ('THEME','FORMATEUR','LIEU','FONCTION','PERIMETRE')",
                name="ck_formation_referentiels_domaine",
            ),
        )
        op.create_index("ix_formation_referentiels_domaine", "formation_referentiels", ["domaine"])

    if not has("formation_entites"):
        op.create_table(
            "formation_entites",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("libelle", sa.String(200), nullable=False),
            sa.Column("cle", sa.String(200), nullable=False, unique=True),
            sa.Column("perimetre_id", sa.UUID(),
                      sa.ForeignKey("formation_referentiels.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("lieu_id", sa.UUID(),
                      sa.ForeignKey("formation_referentiels.id", ondelete="SET NULL"), nullable=True),
            sa.Column("agence_id", sa.UUID(), sa.ForeignKey("agences.id", ondelete="SET NULL"), nullable=True),
            sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
        )
        op.create_index("ix_formation_entites_perimetre_id", "formation_entites", ["perimetre_id"])

    if not has("formation_imports"):
        op.create_table(
            "formation_imports",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("fichier_nom", sa.String(255), nullable=False),
            sa.Column("fichier_sha256", sa.String(64), nullable=False),
            sa.Column("statut", sa.String(20), nullable=False, server_default="ANALYSE"),
            sa.Column("nb_lignes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("analyse", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("resultat", postgresql.JSONB(), nullable=True),
            _user("created_by_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("importe_le", sa.DateTime(timezone=True), nullable=True),
            _user("importe_par_id"),
            sa.CheckConstraint("statut IN ('ANALYSE','IMPORTE','ABANDONNE')", name="ck_formation_imports_statut"),
        )
        op.create_index("ix_formation_imports_fichier_sha256", "formation_imports", ["fichier_sha256"])

    if not has("formation_employes"):
        op.create_table(
            "formation_employes",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("nom", sa.String(120), nullable=False),
            sa.Column("prenom", sa.String(120), nullable=True),
            sa.Column("cle_identite", sa.String(260), nullable=False),
            sa.Column("fonction_id", sa.UUID(),
                      sa.ForeignKey("formation_referentiels.id", ondelete="SET NULL"), nullable=True),
            sa.Column("entite_id", sa.UUID(),
                      sa.ForeignKey("formation_entites.id", ondelete="SET NULL"), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("telephone", sa.String(40), nullable=True),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("motif_desactivation", sa.Text(), nullable=True),
            sa.Column("source", sa.String(20), nullable=False, server_default="MANUEL"),
            sa.Column("import_id", sa.UUID(),
                      sa.ForeignKey("formation_imports.id", ondelete="SET NULL"), nullable=True),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
        )
        op.create_index("ix_formation_employes_cle_identite", "formation_employes", ["cle_identite"])
        op.create_index("ix_formation_employes_fonction_id", "formation_employes", ["fonction_id"])
        op.create_index("ix_formation_employes_entite_id", "formation_employes", ["entite_id"])
        op.create_index("ix_formation_employes_actif", "formation_employes", ["actif"])

    if not has("formation_sessions"):
        op.create_table(
            "formation_sessions",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("reference", sa.String(20), nullable=False, unique=True),
            sa.Column("intitule", sa.String(255), nullable=True),
            sa.Column("date_session", sa.Date(), nullable=False),
            sa.Column("lieu_id", sa.UUID(),
                      sa.ForeignKey("formation_referentiels.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("statut", sa.String(20), nullable=False, server_default="PLANIFIEE"),
            sa.Column("statut_precedent", sa.String(20), nullable=True),
            sa.Column("observations", sa.Text(), nullable=True),
            sa.Column("motif_annulation", sa.Text(), nullable=True),
            sa.Column("presences_saisies_le", sa.DateTime(timezone=True), nullable=True),
            _user("presences_saisies_par_id"),
            sa.Column("cloturee_le", sa.DateTime(timezone=True), nullable=True),
            _user("cloturee_par_id"),
            sa.Column("source", sa.String(20), nullable=False, server_default="MANUEL"),
            sa.Column("import_id", sa.UUID(),
                      sa.ForeignKey("formation_imports.id", ondelete="SET NULL"), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
            sa.CheckConstraint(
                "statut IN ('PLANIFIEE','REALISEE','CLOTUREE','ANNULEE','ARCHIVEE')",
                name="ck_formation_sessions_statut",
            ),
        )
        op.create_index("ix_formation_sessions_date_session", "formation_sessions", ["date_session"])
        op.create_index("ix_formation_sessions_statut", "formation_sessions", ["statut"])
        op.create_index("ix_formation_sessions_lieu_id", "formation_sessions", ["lieu_id"])

    for table, col in (("formation_session_themes", "theme_id"), ("formation_session_formateurs", "formateur_id")):
        if not has(table):
            op.create_table(
                table,
                sa.Column("session_id", sa.UUID(),
                          sa.ForeignKey("formation_sessions.id", ondelete="CASCADE"), primary_key=True),
                sa.Column(col, sa.UUID(),
                          sa.ForeignKey("formation_referentiels.id", ondelete="RESTRICT"), primary_key=True),
                sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
            )
            op.create_index(f"ix_{table}_{col}", table, [col])

    if not has("formation_participants"):
        op.create_table(
            "formation_participants",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("session_id", sa.UUID(),
                      sa.ForeignKey("formation_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("employe_id", sa.UUID(),
                      sa.ForeignKey("formation_employes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("presence", sa.String(10), nullable=True),
            sa.Column("fonction_id", sa.UUID(),
                      sa.ForeignKey("formation_referentiels.id", ondelete="SET NULL"), nullable=True),
            sa.Column("entite_id", sa.UUID(),
                      sa.ForeignKey("formation_entites.id", ondelete="SET NULL"), nullable=True),
            sa.Column("perimetre_id", sa.UUID(),
                      sa.ForeignKey("formation_referentiels.id", ondelete="SET NULL"), nullable=True),
            sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("presence_saisie_le", sa.DateTime(timezone=True), nullable=True),
            _user("presence_saisie_par_id"),
            *_ts(),
            sa.UniqueConstraint("session_id", "employe_id", name="uq_formation_participants_session_employe"),
            sa.CheckConstraint(
                "presence IS NULL OR presence IN ('PRESENT','ABSENT')", name="ck_formation_participants_presence"),
        )
        for col in ("session_id", "employe_id", "presence", "entite_id", "perimetre_id"):
            op.create_index(f"ix_formation_participants_{col}", "formation_participants", [col])

    if not has("formation_compteurs"):
        op.create_table(
            "formation_compteurs",
            sa.Column("annee", sa.Integer(), primary_key=True),
            sa.Column("dernier", sa.Integer(), nullable=False, server_default="0"),
        )

    _seed(bind)


def _seed(bind) -> None:
    ins_ref = sa.text(
        """
        INSERT INTO formation_referentiels (id, domaine, libelle, cle, ordre, actif)
        VALUES (gen_random_uuid(), :domaine, :libelle, :cle, :ordre, true)
        ON CONFLICT (domaine, cle) DO NOTHING
        """
    )
    perimetres = sorted({p for _e, p, _l in ENTITES})
    for domaine, valeurs in (
        ("THEME", THEMES), ("LIEU", LIEUX), ("FORMATEUR", FORMATEURS),
        ("FONCTION", FONCTIONS), ("PERIMETRE", perimetres),
    ):
        for i, libelle in enumerate(valeurs, start=1):
            bind.execute(ins_ref, {"domaine": domaine, "libelle": libelle, "cle": _cle(libelle), "ordre": i})

    for i, (entite, perimetre, lieu) in enumerate(ENTITES, start=1):
        bind.execute(
            sa.text(
                """
                INSERT INTO formation_entites (id, libelle, cle, perimetre_id, lieu_id, agence_id, ordre, actif)
                SELECT gen_random_uuid(), :libelle, :cle, p.id,
                       (SELECT l.id FROM formation_referentiels l WHERE l.domaine = 'LIEU' AND l.cle = :lieu),
                       (SELECT a.id FROM agences a WHERE upper(a.libelle) = upper(:libelle)
                          AND a.deleted_at IS NULL LIMIT 1),
                       :ordre, true
                FROM formation_referentiels p
                WHERE p.domaine = 'PERIMETRE' AND p.cle = :perimetre
                ON CONFLICT (cle) DO NOTHING
                """
            ),
            {"libelle": entite, "cle": _cle(entite), "perimetre": _cle(perimetre), "lieu": _cle(lieu), "ordre": i},
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO plateforme_modules
                (id, espace_id, domaine_id, code, label, description, entry_path, statut,
                 status_message, sort_order, is_active, icon)
            SELECT gen_random_uuid(), e.id,
                   (SELECT d.id FROM plateforme_domaines d WHERE d.code = :domaine_code),
                   :code, :label, :description, '/formation/dashboard', 'actif', '', 2, true, 'school'
            FROM plateforme_espaces e
            WHERE e.code = :espace_code
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "espace_code": ESPACE_CODE,
            "domaine_code": DOMAINE_CODE,
            "code": MODULE_CODE,
            "label": "Formation & Sensibilisation",
            "description": (
                "Sessions de formation Conformité (LBC-FT, EER, FATCA…) : employés attendus, "
                "feuille de présence PDF, présents / absents, historique, statistiques et rapports."
            ),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM plateforme_modules WHERE code = :c"), {"c": MODULE_CODE})
    for table in (
        "formation_participants", "formation_session_formateurs", "formation_session_themes",
        "formation_sessions", "formation_employes", "formation_imports", "formation_entites",
        "formation_referentiels", "formation_compteurs",
    ):
        op.drop_table(table)
