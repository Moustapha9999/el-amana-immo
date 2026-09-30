--
-- PostgreSQL database dump
--

\restrict cyg22m2Pw1PR9VH9kgeivZKDtXfRlrVXwGsI64D7RAiIhdbYWPECHZWLMJcsCzj

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'BEA DIGITAL — schéma unique (plateforme interne + module Immobilisations). ORION reste le core banking.';


--
-- Name: modeamortissement; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.modeamortissement AS ENUM (
    'LINEAIRE',
    'DEGRESSIF'
);


--
-- Name: statutimmobilisation; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.statutimmobilisation AS ENUM (
    'EN_SERVICE',
    'CESSION',
    'REBUT',
    'EN_COURS',
    'SORTIE',
    'BROUILLON',
    'EN_COURS_ACQUISITION',
    'SUSPENDUE',
    'CEDEE',
    'MISE_AU_REBUT',
    'TRANSFEREE',
    'RECLASSEE',
    'ARCHIVEE'
);


--
-- Name: typeajustement; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.typeajustement AS ENUM (
    'CORRECTION',
    'REPRISE'
);


--
-- Name: typecompteplan; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.typecompteplan AS ENUM (
    'IMMOBILISATION',
    'AMORTISSEMENT',
    'DOTATION',
    'REPRISE',
    'CESSION',
    'REBUT'
);


--
-- Name: typeimmobilisation; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.typeimmobilisation AS ENUM (
    'TERRAIN',
    'CONSTRUCTION',
    'AAI',
    'MATERIEL_INFORMATIQUE',
    'MATERIEL_BUREAU',
    'TRANSPORT',
    'LOGICIEL',
    'LICENCE',
    'FRAIS_IMMOBILISES',
    'TITRES',
    'EN_COURS',
    'AUTRES',
    'COFFRES',
    'AUTRES_CORPORELLES',
    'FRAIS_EMRT'
);


--
-- Name: typenotification; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.typenotification AS ENUM (
    'FIN_AMORTISSEMENT',
    'MAINTENANCE',
    'ASSURANCE',
    'INVENTAIRE',
    'SYSTEME'
);


--
-- Name: typepiececomptable; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.typepiececomptable AS ENUM (
    'facture',
    'pv',
    'bon_commande',
    'bon_livraison',
    'contrat',
    'autre',
    'protocole_accord'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agences (
    code character varying(20) NOT NULL,
    libelle character varying(255) NOT NULL,
    adresse text,
    ville character varying(120),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone,
    code_banque character varying(10),
    banque_sigle character varying(20),
    banque_raison_sociale character varying(255),
    code_swift character varying(20)
);


--
-- Name: ajustements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ajustements (
    immobilisation_id uuid NOT NULL,
    type_ajustement public.typeajustement NOT NULL,
    date_ajustement date NOT NULL,
    montant numeric(18,2) NOT NULL,
    commentaire text,
    before_json jsonb,
    after_json jsonb,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: amortissements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.amortissements (
    immobilisation_id uuid NOT NULL,
    periode character varying(7) NOT NULL,
    montant numeric(18,2) NOT NULL,
    cumul numeric(18,2) NOT NULL,
    vnc numeric(18,2) NOT NULL,
    valide boolean NOT NULL,
    annule boolean NOT NULL,
    simule boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE amortissements; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.amortissements IS 'Dotations d’amortissement. Ne pas modifier la règle VNC côté application.';


--
-- Name: api_error_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_error_events (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    request_id character varying(64),
    method character varying(10) NOT NULL,
    route character varying(255) NOT NULL,
    status_code integer NOT NULL,
    code character varying(60),
    message character varying(500),
    exception_type character varying(120),
    user_id uuid,
    module_code character varying(80),
    ip_address character varying(45),
    duration_ms double precision
);


--
-- Name: archive_dossiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_dossiers (
    id uuid NOT NULL,
    annee integer NOT NULL,
    libelle character varying(255),
    created_by_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: archive_fichiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_fichiers (
    id uuid NOT NULL,
    dossier_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    filename character varying(255) NOT NULL,
    stored_path character varying(512) NOT NULL,
    mime_type character varying(120),
    size_bytes integer DEFAULT 0 NOT NULL,
    nature_code character varying(40),
    sheet_names jsonb,
    uploaded_by_id uuid,
    parse_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    parse_error text,
    lines_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: archive_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_lignes (
    id uuid NOT NULL,
    fichier_id uuid NOT NULL,
    categorie_code character varying(40) NOT NULL,
    feuille character varying(120),
    row_number integer DEFAULT 0 NOT NULL,
    date_acquisition date,
    quantite integer DEFAULT 1 NOT NULL,
    designation character varying(512) DEFAULT ''::character varying NOT NULL,
    valeur_brute numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    taux numeric(10,4),
    amt_n1 numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    dotation numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    amt_fin numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    vnc numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    agence_label character varying(120),
    is_report boolean DEFAULT false NOT NULL,
    source_kind character varying(32) DEFAULT 'excel_banque'::character varying NOT NULL,
    raw_json jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    user_id uuid,
    action character varying(80) NOT NULL,
    entity character varying(80) NOT NULL,
    entity_id character varying(64),
    before_data jsonb,
    after_data jsonb,
    ip_address character varying(45),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    espace_code character varying(80),
    module_code character varying(80),
    session_id uuid,
    request_id character varying(64)
);


--
-- Name: COLUMN audit_logs.espace_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audit_logs.espace_code IS 'Contexte espace BEA DIGITAL (nullable, additif).';


--
-- Name: COLUMN audit_logs.module_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audit_logs.module_code IS 'Contexte module BEA DIGITAL (nullable, additif).';


--
-- Name: COLUMN audit_logs.session_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audit_logs.session_id IS 'Session auth à l’origine de l’événement (nullable).';


--
-- Name: auth_login_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_login_attempts (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    ip_address character varying(64),
    login_kind character varying(20) NOT NULL,
    module_code character varying(80),
    success boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE auth_login_attempts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.auth_login_attempts IS 'Journal des tentatives Login 1 / Login 2 (verrouillage 5 échecs / 15 min).';


--
-- Name: COLUMN auth_login_attempts.login_kind; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.auth_login_attempts.login_kind IS 'platform | module.';


--
-- Name: auth_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    refresh_jti character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    ip_address character varying(64),
    user_agent character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    kind character varying(20) DEFAULT 'platform'::character varying NOT NULL,
    module_code character varying(80),
    parent_session_id uuid
);


--
-- Name: COLUMN auth_sessions.kind; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.auth_sessions.kind IS 'platform = Login 1 BEA DIGITAL, module = Login 2.';


--
-- Name: COLUMN auth_sessions.module_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.auth_sessions.module_code IS 'Renseigné uniquement pour kind=module.';


--
-- Name: COLUMN auth_sessions.parent_session_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.auth_sessions.parent_session_id IS 'Session plateforme parente d’une session module.';


--
-- Name: categories_immobilisation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.categories_immobilisation (
    code character varying(30) NOT NULL,
    famille character varying(120) NOT NULL,
    sous_famille character varying(120),
    type_immobilisation public.typeimmobilisation NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone,
    compte_immobilisation character varying(20),
    compte_amortissement character varying(20),
    compte_dotation character varying(20),
    comptes_amortissement_alternatifs character varying(120),
    amortissable boolean DEFAULT false NOT NULL,
    duree_annees_defaut integer,
    taux_lineaire_defaut numeric(8,4),
    mode_amortissement_defaut public.modeamortissement DEFAULT 'LINEAIRE'::public.modeamortissement NOT NULL,
    periodicite_defaut character varying(20) DEFAULT 'annuel'::character varying NOT NULL,
    prorata_temporis boolean DEFAULT true NOT NULL,
    journal_code character varying(10) DEFAULT 'OD'::character varying NOT NULL
);


--
-- Name: centres_cout; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.centres_cout (
    code character varying(30) NOT NULL,
    libelle character varying(255) NOT NULL,
    departement_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: cessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cessions (
    immobilisation_id uuid NOT NULL,
    date_cession date NOT NULL,
    prix_cession numeric(18,2) NOT NULL,
    vnc numeric(18,2) NOT NULL,
    plus_value numeric(18,2) NOT NULL,
    moins_value numeric(18,2) NOT NULL,
    libelle character varying(255),
    ecriture_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    reference character varying(80),
    observations text
);


--
-- Name: departements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.departements (
    code character varying(20) NOT NULL,
    libelle character varying(255) NOT NULL,
    direction_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: TABLE departements; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.departements IS 'Organigramme banque (directions / départements). N’est PAS le catalogue des espaces plateforme.';


--
-- Name: directions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.directions (
    code character varying(20) NOT NULL,
    libelle character varying(255) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: ecritures_comptables; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ecritures_comptables (
    journal_code character varying(10) NOT NULL,
    date_ecriture date NOT NULL,
    libelle character varying(255) NOT NULL,
    compte_debit character varying(20) NOT NULL,
    compte_credit character varying(20) NOT NULL,
    montant numeric(18,2) NOT NULL,
    reference character varying(80),
    immobilisation_id uuid,
    generee_auto boolean NOT NULL,
    validee boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE ecritures_comptables; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.ecritures_comptables IS 'Écritures du module immobilisations (complément d’ORION, pas un remplacement).';


--
-- Name: exercices_comptables; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exercices_comptables (
    id uuid NOT NULL,
    annee integer NOT NULL,
    statut character varying(20) DEFAULT 'ouvert'::character varying NOT NULL,
    archive_dossier_id uuid,
    cloture_at timestamp with time zone,
    cloture_by_id uuid,
    ouverture_at timestamp with time zone,
    ouverture_by_id uuid,
    total_valeur_brute numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    total_amortissement numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    total_vnc numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    total_dotation_68 numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    nb_immobilisations integer DEFAULT 0 NOT NULL,
    snapshot_hash character varying(64),
    message character varying(512),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: fournisseurs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fournisseurs (
    code character varying(30) NOT NULL,
    raison_sociale character varying(255) NOT NULL,
    contact character varying(120),
    telephone character varying(40),
    email character varying(255),
    adresse text,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone,
    nom_commercial character varying(255),
    type_fournisseur character varying(40) DEFAULT 'FOURNITURE'::character varying NOT NULL,
    contact_fonction character varying(120),
    telephone_secondaire character varying(40),
    site_web character varying(255),
    ville character varying(120),
    pays character varying(80) DEFAULT 'Mauritanie'::character varying NOT NULL,
    nif character varying(60),
    rc character varying(60),
    devise_defaut character varying(10) DEFAULT 'MRU'::character varying NOT NULL,
    mode_paiement_defaut character varying(80),
    delai_paiement_jours integer,
    conditions_commerciales text,
    created_by uuid,
    updated_by uuid
);


--
-- Name: ged_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ged_documents (
    id uuid NOT NULL,
    espace_code character varying(80) NOT NULL,
    module_code character varying(80) NOT NULL,
    entity character varying(80) NOT NULL,
    entity_id character varying(64) NOT NULL,
    filename character varying(255) NOT NULL,
    stored_path character varying(512) NOT NULL,
    mime_type character varying(120),
    size_bytes integer DEFAULT 0 NOT NULL,
    uploaded_by_id uuid,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    title character varying(255),
    description text,
    doc_type character varying(80),
    reference character varying(120),
    date_document date,
    archived_at timestamp with time zone,
    agence_id uuid,
    department_id uuid,
    fournisseur_id uuid,
    version integer DEFAULT 1 NOT NULL,
    parent_document_id uuid,
    deleted_by_id uuid,
    delete_reason character varying(500),
    ocr_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    ocr_text text,
    ocr_text_search tsvector,
    ocr_error text,
    ocr_attempts integer DEFAULT 0 NOT NULL,
    security_level character varying(40) DEFAULT 'internal'::character varying NOT NULL,
    version_comment character varying(500)
);


--
-- Name: TABLE ged_documents; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.ged_documents IS 'GED CORE — documents transverses. Non branchée ; pieces_jointes / archive_* restent immo.';


--
-- Name: immobilisations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.immobilisations (
    code_inventaire character varying(50) NOT NULL,
    numero_serie character varying(80),
    designation character varying(255) NOT NULL,
    description text,
    categorie_id uuid,
    agence_id uuid,
    departement_id uuid,
    centre_cout_id uuid,
    responsable_id uuid,
    fournisseur_id uuid,
    date_acquisition date NOT NULL,
    date_mise_en_service date,
    date_fin date,
    valeur_brute numeric(18,2) NOT NULL,
    valeur_residuelle numeric(18,2) NOT NULL,
    duree_mois integer NOT NULL,
    mode_amortissement public.modeamortissement NOT NULL,
    taux numeric(8,4),
    devise character varying(3) NOT NULL,
    statut public.statutimmobilisation NOT NULL,
    compte_immobilisation character varying(20),
    compte_amortissement character varying(20),
    compte_dotation character varying(20),
    qr_code_data character varying(512),
    barcode_data character varying(80),
    localisation character varying(255),
    metadata_json jsonb,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone,
    numero_facture character varying(80),
    quantite integer DEFAULT 1 NOT NULL,
    observations text,
    duree_annees integer,
    periodicite character varying(20) DEFAULT 'annuel'::character varying NOT NULL,
    prorata_temporis boolean DEFAULT true NOT NULL,
    date_comptabilisation date
);


--
-- Name: TABLE immobilisations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.immobilisations IS 'Module Comptabilité / Immobilisations — logique métier inchangée (VNC, dotations, parc).';


--
-- Name: inventaire_scans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inventaire_scans (
    immobilisation_id uuid,
    code_scanne character varying(80) NOT NULL,
    valide boolean NOT NULL,
    localisation character varying(255),
    scanned_by_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: journaux; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.journaux (
    code character varying(10) NOT NULL,
    libelle character varying(120) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: mg_achat_bl; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_bl (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    bon_id uuid NOT NULL,
    fournisseur_id uuid NOT NULL,
    date_bl date NOT NULL,
    date_livraison date,
    agence_id uuid,
    transporteur character varying(255),
    observation text,
    statut character varying(30) DEFAULT 'RECU'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_comparaisons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_comparaisons (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    consultation_id uuid NOT NULL,
    demande_id uuid,
    statut character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    fournisseur_retenu_id uuid,
    motif_choix text,
    snapshot_json text,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_consultation_fournisseurs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_consultation_fournisseurs (
    id uuid NOT NULL,
    consultation_id uuid NOT NULL,
    fournisseur_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_consultations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_consultations (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    date_consultation date NOT NULL,
    demande_id uuid,
    agence_id uuid NOT NULL,
    objet character varying(255) NOT NULL,
    date_limite date,
    responsable_id uuid,
    statut character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_demande_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_demande_lignes (
    id uuid NOT NULL,
    demande_id uuid NOT NULL,
    designation character varying(255) NOT NULL,
    description text,
    quantite numeric(18,3) DEFAULT '1'::numeric NOT NULL,
    uom character varying(20) DEFAULT 'U'::character varying NOT NULL,
    prix_estime numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    montant_estime numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    article_id uuid,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_demandes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_demandes (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    date_demande date NOT NULL,
    agence_id uuid NOT NULL,
    departement_id uuid,
    demandeur_id uuid,
    demandeur_nom character varying(255),
    fonction character varying(120),
    type_achat character varying(40) DEFAULT 'FOURNITURE'::character varying NOT NULL,
    priorite character varying(20) DEFAULT 'NORMAL'::character varying NOT NULL,
    projet character varying(255),
    motif text,
    date_souhaitee date,
    budget_estime numeric(18,2),
    statut character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    source_type character varying(40),
    source_id uuid
);


--
-- Name: mg_achat_devis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_devis (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    fournisseur_id uuid NOT NULL,
    consultation_id uuid,
    date_devis date NOT NULL,
    date_validite date,
    montant_ht numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    montant_tva numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    montant_ttc numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    devise character varying(10) DEFAULT 'MRU'::character varying NOT NULL,
    conditions text,
    delai_livraison character varying(120),
    conditions_paiement character varying(120),
    statut character varying(30) DEFAULT 'RECU'::character varying NOT NULL,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_devis_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_devis_lignes (
    id uuid NOT NULL,
    devis_id uuid NOT NULL,
    designation character varying(255) NOT NULL,
    quantite numeric(18,3) DEFAULT '1'::numeric NOT NULL,
    prix_unitaire numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    remise_pct numeric(5,2) DEFAULT '0'::numeric NOT NULL,
    taux_tva numeric(5,2) DEFAULT '0'::numeric NOT NULL,
    total_ht numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_evenements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_evenements (
    id uuid NOT NULL,
    entity_type character varying(40) NOT NULL,
    entity_id uuid NOT NULL,
    action character varying(60) NOT NULL,
    message text,
    user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_facture_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_facture_lignes (
    id uuid NOT NULL,
    facture_id uuid NOT NULL,
    designation character varying(255) NOT NULL,
    quantite numeric(18,3) DEFAULT '1'::numeric NOT NULL,
    prix_unitaire numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    total_ht numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_factures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_factures (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    numero_fournisseur character varying(80),
    fournisseur_id uuid NOT NULL,
    bon_id uuid NOT NULL,
    bl_id uuid,
    reception_id uuid,
    date_facture date NOT NULL,
    date_echeance date,
    montant_ht numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    montant_tva numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    montant_ttc numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    devise character varying(10) DEFAULT 'MRU'::character varying NOT NULL,
    statut character varying(30) DEFAULT 'RECUE'::character varying NOT NULL,
    ecart_quantite boolean DEFAULT false NOT NULL,
    ecart_montant boolean DEFAULT false NOT NULL,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_paiements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_paiements (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    facture_id uuid NOT NULL,
    fournisseur_id uuid NOT NULL,
    montant numeric(18,2) NOT NULL,
    date_echeance date,
    date_paiement date,
    mode_paiement character varying(80),
    reference_paiement character varying(120),
    statut character varying(30) DEFAULT 'A_PAYER'::character varying NOT NULL,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_parametres; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_parametres (
    cle character varying(80) NOT NULL,
    valeur text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_reception_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_reception_lignes (
    id uuid NOT NULL,
    reception_id uuid NOT NULL,
    bc_ligne_id uuid NOT NULL,
    quantite_recue numeric(18,3) NOT NULL,
    article_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_achat_receptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_achat_receptions (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    bon_id uuid NOT NULL,
    bl_id uuid,
    date_reception date NOT NULL,
    agence_id uuid,
    statut character varying(30) DEFAULT 'PARTIEL'::character varying NOT NULL,
    observation text,
    created_by uuid,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_article_familles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_article_familles (
    id uuid NOT NULL,
    code character varying(40) NOT NULL,
    libelle character varying(120) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_articles (
    id uuid NOT NULL,
    code character varying(40) NOT NULL,
    designation character varying(255) NOT NULL,
    famille_id uuid NOT NULL,
    uom character varying(20) DEFAULT 'U'::character varying NOT NULL,
    stock_actuel numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    stock_min numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    stock_max numeric(18,3),
    agence_id uuid,
    emplacement character varying(120),
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    reference character varying(80),
    sous_famille character varying(120),
    stockable boolean DEFAULT true NOT NULL,
    fournisseur_habituel character varying(255)
);


--
-- Name: mg_bc_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_bc_lignes (
    id uuid NOT NULL,
    bc_id uuid NOT NULL,
    code_produit character varying(60),
    departement character varying(120),
    description character varying(255) NOT NULL,
    quantite numeric(18,3) DEFAULT '1'::numeric NOT NULL,
    uom character varying(20) DEFAULT 'U'::character varying NOT NULL,
    prix_unitaire numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    prix_total numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    article_id uuid,
    quantite_recue numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    remise_pct numeric(5,2) DEFAULT '0'::numeric NOT NULL,
    taux_tva numeric(5,2) DEFAULT '0'::numeric NOT NULL,
    total_ttc numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    stockable boolean DEFAULT false NOT NULL
);


--
-- Name: mg_bons_commande; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_bons_commande (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    date_bc date NOT NULL,
    fournisseur_id uuid,
    fournisseur_raison_sociale character varying(255),
    fournisseur_nif character varying(60),
    fournisseur_telephone character varying(40),
    fournisseur_adresse text,
    departement character varying(120),
    projet character varying(255),
    acheteur_id uuid,
    acheteur_nom character varying(255),
    acheteur_tel character varying(40),
    adresse_facturation text,
    adresse_livraison text,
    conditions text,
    incoterm character varying(60),
    conditions_paiement character varying(120),
    moyen_paiement character varying(120),
    demandeur_nom character varying(255),
    demandeur_date date,
    statut character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    visa_mg_at timestamp with time zone,
    visa_mg_by uuid,
    visa_dr_at timestamp with time zone,
    visa_dr_by uuid,
    total_ht numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    demande_id uuid,
    consultation_id uuid,
    comparaison_id uuid,
    contrat_id uuid,
    agence_facturation_id uuid,
    agence_livraison_id uuid,
    agence_facturation_snapshot text,
    agence_livraison_snapshot text,
    type_achat character varying(40) DEFAULT 'FOURNITURE'::character varying NOT NULL,
    devise character varying(10) DEFAULT 'MRU'::character varying NOT NULL,
    total_tva numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    total_ttc numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    date_livraison_prevue date,
    pdf_version integer DEFAULT 1 NOT NULL
);


--
-- Name: mg_contrat_echeances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_contrat_echeances (
    id uuid NOT NULL,
    contrat_id uuid NOT NULL,
    type_echeance character varying(40) DEFAULT 'AUTRE'::character varying NOT NULL,
    date_prevue date NOT NULL,
    date_reelle date,
    montant numeric(18,2),
    responsable_nom character varying(255),
    statut character varying(30) DEFAULT 'A_VENIR'::character varying NOT NULL,
    commentaire text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mg_contrat_historique; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_contrat_historique (
    id uuid NOT NULL,
    contrat_id uuid NOT NULL,
    action character varying(60) NOT NULL,
    from_statut character varying(30),
    to_statut character varying(30),
    user_id uuid,
    user_nom character varying(255),
    commentaire text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mg_contrat_paiements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_contrat_paiements (
    id uuid NOT NULL,
    contrat_id uuid NOT NULL,
    echeance_id uuid,
    reference character varying(40),
    date_prevue date NOT NULL,
    date_reelle date,
    montant_prevu numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    montant_paye numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    devise character varying(8) DEFAULT 'MRU'::character varying NOT NULL,
    statut character varying(30) DEFAULT 'A_VENIR'::character varying NOT NULL,
    mode character varying(40),
    commentaire text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mg_contrat_parametres; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_contrat_parametres (
    id uuid NOT NULL,
    cle character varying(80) NOT NULL,
    valeur character varying(255) DEFAULT ''::character varying NOT NULL,
    libelle character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mg_contrat_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_contrat_types (
    id uuid NOT NULL,
    code character varying(40) NOT NULL,
    libelle character varying(120) NOT NULL,
    actif boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mg_contrats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_contrats (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    titre character varying(255) NOT NULL,
    fournisseur_id uuid,
    fournisseur_snapshot character varying(255),
    date_debut date NOT NULL,
    date_fin date,
    montant numeric(18,2),
    periodicite character varying(20) DEFAULT 'ANNUEL'::character varying NOT NULL,
    prochain_echeance date,
    alerte_jours integer DEFAULT 30 NOT NULL,
    statut character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    agence_id uuid,
    agence_libelle_snapshot character varying(255),
    type_contrat character varying(40),
    numero_contrat character varying(80),
    description text,
    date_signature date,
    devise character varying(8),
    montant_ht numeric(18,2),
    taux_tva numeric(6,2),
    responsable_id uuid,
    responsable_nom character varying(255),
    mode_paiement character varying(40),
    contrat_precedent_id uuid,
    ref_paiement character varying(120)
);


--
-- Name: mg_demande_fourniture_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_demande_fourniture_lignes (
    id uuid NOT NULL,
    demande_id uuid NOT NULL,
    article_id uuid,
    designation character varying(255) NOT NULL,
    quantite_demandee numeric(18,3) NOT NULL,
    quantite_accordee numeric(18,3),
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_demandes_fourniture; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_demandes_fourniture (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    date_demande date NOT NULL,
    agence_id uuid NOT NULL,
    agence_libelle_snapshot character varying(255),
    agence_adresse_snapshot text,
    departement character varying(120),
    demandeur_id uuid,
    demandeur_nom character varying(255),
    fonction character varying(120),
    statut character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    visa_agence_at timestamp with time zone,
    visa_agence_by uuid,
    visa_mg_at timestamp with time zone,
    visa_mg_by uuid,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_employee_request_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_employee_request_items (
    id uuid NOT NULL,
    request_id uuid NOT NULL,
    article_id uuid,
    description character varying(255) NOT NULL,
    quantity numeric(18,3) DEFAULT '1'::numeric NOT NULL,
    unit character varying(20) DEFAULT 'U'::character varying NOT NULL,
    estimated_unit_price numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    estimated_total numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    stock_checked boolean DEFAULT false NOT NULL,
    stock_available boolean,
    stock_actuel numeric(18,3),
    status character varying(30) DEFAULT 'OUVERT'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    quantity_granted numeric(18,3)
);


--
-- Name: mg_employee_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_employee_requests (
    id uuid NOT NULL,
    request_number character varying(40) NOT NULL,
    requester_id uuid NOT NULL,
    department_id uuid,
    agency_id uuid NOT NULL,
    category_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    priority character varying(20) DEFAULT 'NORMALE'::character varying NOT NULL,
    status character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    period character varying(40),
    submitted_at timestamp with time zone,
    received_at timestamp with time zone,
    validated_at timestamp with time zone,
    rejected_at timestamp with time zone,
    closed_at timestamp with time zone,
    validated_by uuid,
    rejected_by uuid,
    rejection_reason text,
    validation_comment text,
    complement_comment text,
    achat_demande_id uuid,
    batch_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    source_espace_code character varying(80) DEFAULT 'employe'::character varying NOT NULL,
    target_espace_code character varying(80) DEFAULT 'moyens-generaux'::character varying NOT NULL,
    assigned_to_id uuid
);


--
-- Name: mg_inventaire_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_inventaire_lignes (
    id uuid NOT NULL,
    inventaire_id uuid NOT NULL,
    article_id uuid NOT NULL,
    stock_theorique numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    stock_physique numeric(18,3),
    ecart numeric(18,3),
    observation character varying(255),
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    nature_ecart character varying(20)
);


--
-- Name: mg_inventaires; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_inventaires (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    libelle character varying(255) NOT NULL,
    date_debut date NOT NULL,
    date_fin date,
    agence_id uuid,
    statut character varying(30) DEFAULT 'OUVERT'::character varying NOT NULL,
    observation text,
    created_by uuid,
    cloture_at timestamp with time zone,
    cloture_by uuid,
    deleted_at timestamp with time zone,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    periode_id uuid,
    valide_at timestamp with time zone,
    valide_by uuid,
    ajustements_at timestamp with time zone,
    ajustements_by uuid
);


--
-- Name: mg_note_frais_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_note_frais_categories (
    id uuid NOT NULL,
    code character varying(40) NOT NULL,
    libelle character varying(120) NOT NULL,
    actif boolean DEFAULT true NOT NULL,
    justificatif_obligatoire boolean DEFAULT false NOT NULL,
    plafond numeric(18,2),
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    deleted_at timestamp with time zone
);


--
-- Name: mg_note_frais_historique; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_note_frais_historique (
    id uuid NOT NULL,
    note_id uuid NOT NULL,
    action character varying(60) NOT NULL,
    from_statut character varying(30),
    to_statut character varying(30),
    user_id uuid,
    user_nom character varying(255),
    commentaire text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mg_note_frais_lignes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_note_frais_lignes (
    id uuid NOT NULL,
    note_id uuid NOT NULL,
    date_depense date NOT NULL,
    description character varying(255) NOT NULL,
    motif character varying(255),
    montant numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    mode_reglement character varying(80),
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    categorie_id uuid,
    categorie_libelle_snapshot character varying(120),
    devise character varying(10) DEFAULT 'MRU'::character varying NOT NULL,
    commentaire text
);


--
-- Name: mg_note_frais_parametres; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_note_frais_parametres (
    id uuid NOT NULL,
    cle character varying(60) NOT NULL,
    valeur character varying(255) NOT NULL,
    libelle character varying(120),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mg_notes_frais; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_notes_frais (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    date_demande date NOT NULL,
    agence_id uuid,
    agence_libelle_snapshot character varying(255),
    demandeur_id uuid,
    demandeur_nom character varying(255),
    departement character varying(120),
    fonction character varying(120),
    statut character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    visa_mg_at timestamp with time zone,
    visa_mg_by uuid,
    visa_dr_at timestamp with time zone,
    visa_dr_by uuid,
    total_mru numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    observation text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    objet character varying(255),
    periode_debut date,
    periode_fin date,
    devise character varying(10) DEFAULT 'MRU'::character varying NOT NULL,
    agence_code_snapshot character varying(40),
    agence_adresse_snapshot text,
    montant_paye numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    date_mise_en_paiement date,
    date_paiement date,
    mode_paiement character varying(80),
    ref_paiement character varying(120),
    commentaire_paiement text,
    motif_rejet text,
    motif_correction text,
    pdf_version integer DEFAULT 1 NOT NULL,
    document_final_ged_id uuid,
    controle_at timestamp with time zone,
    controle_by uuid
);


--
-- Name: mg_procurement_batch_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_procurement_batch_items (
    id uuid NOT NULL,
    batch_id uuid NOT NULL,
    request_id uuid NOT NULL,
    request_item_id uuid NOT NULL,
    article_id uuid,
    description character varying(255) NOT NULL,
    quantity numeric(18,3) DEFAULT '1'::numeric NOT NULL,
    supplier_id uuid,
    estimated_unit_price numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    estimated_total numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    status character varying(30) DEFAULT 'INCLUS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_procurement_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_procurement_batches (
    id uuid NOT NULL,
    batch_number character varying(40) NOT NULL,
    category_id uuid,
    department_id uuid,
    agency_id uuid,
    period character varying(40),
    title character varying(255) NOT NULL,
    description text,
    priority character varying(20) DEFAULT 'NORMALE'::character varying NOT NULL,
    status character varying(30) DEFAULT 'BROUILLON'::character varying NOT NULL,
    created_by uuid NOT NULL,
    validated_by uuid,
    achat_demande_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_request_approvals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_request_approvals (
    id uuid NOT NULL,
    request_id uuid NOT NULL,
    approver_id uuid NOT NULL,
    action character varying(40) NOT NULL,
    status character varying(30) NOT NULL,
    comment text,
    acted_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_request_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_request_categories (
    id uuid NOT NULL,
    code character varying(40) NOT NULL,
    name character varying(120) NOT NULL,
    description text,
    icon character varying(40),
    form_schema jsonb,
    requires_stock_check boolean DEFAULT false NOT NULL,
    requires_purchase boolean DEFAULT true NOT NULL,
    active boolean DEFAULT true NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    can_create_purchase boolean DEFAULT true NOT NULL,
    requires_attachment boolean DEFAULT false NOT NULL,
    owner_espace_code character varying(80) DEFAULT 'moyens-generaux'::character varying NOT NULL,
    target_espace_code character varying(80) DEFAULT 'moyens-generaux'::character varying NOT NULL,
    source_espaces jsonb
);


--
-- Name: mg_request_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_request_comments (
    id uuid NOT NULL,
    request_id uuid NOT NULL,
    author_id uuid NOT NULL,
    body text NOT NULL,
    visibility character varying(20) DEFAULT 'SHARED'::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: mg_stock_mouvements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_stock_mouvements (
    id uuid NOT NULL,
    reference character varying(40) NOT NULL,
    date_mouvement timestamp with time zone NOT NULL,
    type_mouvement character varying(20) NOT NULL,
    article_id uuid NOT NULL,
    quantite numeric(18,3) NOT NULL,
    agence_id uuid,
    departement character varying(120),
    initiateur_id uuid,
    motif character varying(255),
    observation text,
    source_type character varying(40),
    source_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    periode_id uuid
);


--
-- Name: mg_stock_parametres; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_stock_parametres (
    id uuid NOT NULL,
    cle character varying(60) NOT NULL,
    valeur character varying(255) NOT NULL,
    libelle character varying(120),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mg_stock_periodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_stock_periodes (
    id uuid NOT NULL,
    annee integer NOT NULL,
    mois integer NOT NULL,
    libelle character varying(80) NOT NULL,
    date_debut date NOT NULL,
    date_fin date NOT NULL,
    statut character varying(20) DEFAULT 'OUVERTE'::character varying NOT NULL,
    agence_id uuid,
    periode_precedente_id uuid,
    opened_at timestamp with time zone,
    opened_by uuid,
    cloture_at timestamp with time zone,
    cloture_by uuid,
    reopen_at timestamp with time zone,
    reopen_by uuid,
    reopen_motif text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mg_stock_soldes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mg_stock_soldes (
    id uuid NOT NULL,
    periode_id uuid NOT NULL,
    article_id uuid NOT NULL,
    stock_initial numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    entrees numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    sorties numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    ajustements numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    stock_theorique numeric(18,3) DEFAULT '0'::numeric NOT NULL,
    stock_physique numeric(18,3),
    ecart numeric(18,3),
    stock_final numeric(18,3),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    user_id uuid NOT NULL,
    type_notification public.typenotification NOT NULL,
    titre character varying(255) NOT NULL,
    message text NOT NULL,
    lu boolean NOT NULL,
    entity character varying(80),
    entity_id character varying(64),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    espace_code character varying(80),
    module_code character varying(80),
    categorie character varying(40) DEFAULT 'systeme'::character varying NOT NULL,
    priorite character varying(20) DEFAULT 'info'::character varying NOT NULL,
    event_type character varying(80),
    event_code character varying(40),
    emetteur_type character varying(40) DEFAULT 'systeme'::character varying NOT NULL,
    emetteur_label character varying(255) DEFAULT 'Systeme'::character varying NOT NULL,
    destinataire_type character varying(40) DEFAULT 'utilisateur'::character varying NOT NULL,
    destinataire_label character varying(255),
    actor_user_id uuid,
    archived boolean DEFAULT false NOT NULL
);


--
-- Name: COLUMN notifications.espace_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.notifications.espace_code IS 'Contexte espace BEA DIGITAL (nullable, additif).';


--
-- Name: COLUMN notifications.module_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.notifications.module_code IS 'Contexte module BEA DIGITAL (nullable, additif).';


--
-- Name: parametrage_amortissement; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parametrage_amortissement (
    periodicite character varying(20) NOT NULL,
    prorata boolean NOT NULL,
    journal_code character varying(10) NOT NULL,
    compte_dotation_defaut character varying(20) NOT NULL,
    compte_amortissement_defaut character varying(20) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: parametrage_ecritures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parametrage_ecritures (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    categorie_id uuid NOT NULL,
    journal_code character varying(10) NOT NULL,
    compte_debit character varying(20) NOT NULL,
    compte_credit character varying(20) NOT NULL,
    libelle_modele character varying(255) NOT NULL
);


--
-- Name: password_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_history (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    password_hash character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: password_reset_jtis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_jtis (
    jti character varying(64) NOT NULL,
    user_id uuid NOT NULL,
    used_at timestamp with time zone,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: periodes_amortissement; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.periodes_amortissement (
    id uuid NOT NULL,
    exercice_id uuid NOT NULL,
    annee integer NOT NULL,
    trimestre integer NOT NULL,
    code character varying(20) NOT NULL,
    date_arrete date NOT NULL,
    statut character varying(20) DEFAULT 'en_attente'::character varying NOT NULL,
    calcule_at timestamp with time zone,
    valide_at timestamp with time zone,
    valide_by_id uuid,
    total_dotation numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    nb_dotations integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_periode_amort_trimestre CHECK (((trimestre >= 1) AND (trimestre <= 4)))
);


--
-- Name: periodes_amortissement_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.periodes_amortissement_categories (
    id uuid NOT NULL,
    periode_id uuid NOT NULL,
    categorie_id uuid NOT NULL,
    statut character varying(20) DEFAULT 'en_attente'::character varying NOT NULL,
    valide_at timestamp with time zone,
    valide_by_id uuid,
    total_dotation numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    nb_dotations integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permissions (
    code character varying(100) NOT NULL,
    label character varying(255) NOT NULL,
    module character varying(80) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE permissions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.permissions IS 'Permissions fonctionnelles (ex. immobilisations.read). Module = code métier, pas plateforme_modules.id.';


--
-- Name: pieces_jointes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pieces_jointes (
    immobilisation_id uuid NOT NULL,
    filename character varying(255) NOT NULL,
    stored_path character varying(512) NOT NULL,
    mime_type character varying(120),
    size_bytes integer NOT NULL,
    is_photo boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    type_piece public.typepiececomptable NOT NULL,
    date_journee date NOT NULL,
    reference character varying(120),
    libelle character varying(255),
    uploaded_by_id uuid,
    montant numeric(18,2)
);


--
-- Name: plan_comptable; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plan_comptable (
    numero character varying(20) NOT NULL,
    libelle character varying(255) NOT NULL,
    type_compte public.typecompteplan NOT NULL,
    centre_analytique character varying(30),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: TABLE plan_comptable; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.plan_comptable IS 'Plan comptable banque (référentiel El Amana) — inchangé.';


--
-- Name: plateforme_espaces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plateforme_espaces (
    id uuid NOT NULL,
    code character varying(80) NOT NULL,
    label character varying(120) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    route character varying(160),
    statut character varying(20) DEFAULT 'bientot'::character varying NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    status_message text DEFAULT ''::text NOT NULL,
    maintenance_starts_at timestamp with time zone,
    maintenance_ends_at timestamp with time zone
);


--
-- Name: TABLE plateforme_espaces; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.plateforme_espaces IS 'Catalogue des espaces métiers BEA DIGITAL (Comptabilité, Crédit, RH, …). Distinct de org.departements.';


--
-- Name: COLUMN plateforme_espaces.code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.plateforme_espaces.code IS 'Code stable (ex. comptabilite).';


--
-- Name: COLUMN plateforme_espaces.route; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.plateforme_espaces.route IS 'Route Angular de l’espace (ex. /comptabilite).';


--
-- Name: COLUMN plateforme_espaces.statut; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.plateforme_espaces.statut IS 'actif | bientot | inactif.';


--
-- Name: plateforme_modules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plateforme_modules (
    id uuid NOT NULL,
    espace_id uuid NOT NULL,
    code character varying(80) NOT NULL,
    label character varying(160) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    entry_path character varying(160),
    statut character varying(20) DEFAULT 'bientot'::character varying NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    status_message text DEFAULT ''::text NOT NULL,
    version character varying(40) DEFAULT '1.0.0'::character varying NOT NULL,
    maintenance_starts_at timestamp with time zone,
    maintenance_ends_at timestamp with time zone,
    admins_bypass_maintenance boolean DEFAULT true NOT NULL
);


--
-- Name: TABLE plateforme_modules; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.plateforme_modules IS 'Modules d’un espace. Premier module actif : immobilisations (entry_path /dashboard).';


--
-- Name: COLUMN plateforme_modules.code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.plateforme_modules.code IS 'Code stable (ex. immobilisations).';


--
-- Name: COLUMN plateforme_modules.entry_path; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.plateforme_modules.entry_path IS 'Entrée Angular du module. Immobilisations = /dashboard (ne pas préfixer sous /comptabilite/).';


--
-- Name: COLUMN plateforme_modules.statut; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.plateforme_modules.statut IS 'actif | bientot | inactif.';


--
-- Name: platform_backups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_backups (
    id uuid NOT NULL,
    level character varying(20) NOT NULL,
    backup_type character varying(40) NOT NULL,
    espace_code character varying(80),
    module_code character varying(80),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    file_path character varying(512),
    uploads_path character varying(512),
    size_bytes bigint DEFAULT '0'::bigint NOT NULL,
    tables_included jsonb,
    shared_dependencies jsonb,
    error_message text,
    created_by_id uuid,
    finished_at timestamp with time zone,
    label character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: platform_module_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_module_versions (
    id uuid NOT NULL,
    module_id uuid NOT NULL,
    version character varying(40) NOT NULL,
    notes text DEFAULT ''::text NOT NULL,
    created_by_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: platform_ops_flags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_ops_flags (
    key character varying(80) NOT NULL,
    value jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: platform_restores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_restores (
    id uuid NOT NULL,
    backup_id uuid NOT NULL,
    safety_backup_id uuid,
    level character varying(20) NOT NULL,
    espace_code character varying(80),
    module_code character varying(80),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    dependency_warning text,
    acknowledged_dependencies boolean DEFAULT false NOT NULL,
    error_message text,
    created_by_id uuid,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: rebuts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rebuts (
    immobilisation_id uuid NOT NULL,
    date_rebut date NOT NULL,
    vnc numeric(18,2) NOT NULL,
    motif text,
    ecriture_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: reevaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reevaluations (
    immobilisation_id uuid NOT NULL,
    date_reevaluation date NOT NULL,
    ancienne_valeur numeric(18,2) NOT NULL,
    nouvelle_valeur numeric(18,2) NOT NULL,
    justificatif text,
    stored_justificatif_path character varying(512),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: role_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_permissions (
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL
);


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    code character varying(50) NOT NULL,
    label character varying(120) NOT NULL,
    description text,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: security_incidents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.security_incidents (
    id uuid NOT NULL,
    titre character varying(255) NOT NULL,
    description text,
    niveau character varying(20) DEFAULT 'info'::character varying NOT NULL,
    statut character varying(30) DEFAULT 'ouvert'::character varying NOT NULL,
    actions text,
    responsable character varying(255),
    resolution text,
    created_by_id uuid,
    closed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    type_incident character varying(40) DEFAULT 'autre'::character varying NOT NULL,
    module_code character varying(80),
    espace_code character varying(80),
    user_concerne_id uuid
);


--
-- Name: soldes_compte_orion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soldes_compte_orion (
    id uuid NOT NULL,
    annee integer NOT NULL,
    compte_immobilisation character varying(20) NOT NULL,
    valeur_brute numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    source character varying(40) DEFAULT 'orion'::character varying NOT NULL,
    libelle character varying(120),
    updated_by_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    verrouille_at timestamp with time zone
);


--
-- Name: soldes_ouverture_immobilisations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soldes_ouverture_immobilisations (
    id uuid NOT NULL,
    exercice_id uuid NOT NULL,
    immobilisation_id uuid NOT NULL,
    annee integer NOT NULL,
    annee_source integer NOT NULL,
    valeur_brute_142 numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    cumul_148 numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    vnc numeric(18,2) DEFAULT '0'::numeric NOT NULL,
    code_inventaire character varying(80),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_espace_acces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_espace_acces (
    user_id uuid NOT NULL,
    espace_id uuid NOT NULL,
    status character varying(20) DEFAULT 'actif'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by uuid
);


--
-- Name: TABLE user_espace_acces; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.user_espace_acces IS 'Habilitations utilisateur → espace BEA DIGITAL (Login 1). Pas une table d’organisation bancaire.';


--
-- Name: COLUMN user_espace_acces.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_espace_acces.status IS 'actif | revoque.';


--
-- Name: COLUMN user_espace_acces.created_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_espace_acces.created_by IS 'UUID users.id — FK en base, pas mappée ORM (évite AmbiguousForeignKeys).';


--
-- Name: user_module_acces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_module_acces (
    user_id uuid NOT NULL,
    module_id uuid NOT NULL,
    status character varying(20) DEFAULT 'actif'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by uuid
);


--
-- Name: TABLE user_module_acces; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.user_module_acces IS 'Habilitations utilisateur → module (Login 2). Indépendant des rôles métier immobilisations.*';


--
-- Name: COLUMN user_module_acces.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_module_acces.status IS 'actif | revoque.';


--
-- Name: COLUMN user_module_acces.created_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_module_acces.created_by IS 'UUID users.id — FK en base, pas mappée ORM.';


--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_roles (
    user_id uuid NOT NULL,
    role_id uuid NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    email character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    phone character varying(40),
    is_superuser boolean NOT NULL,
    totp_secret character varying(255),
    totp_enabled boolean NOT NULL,
    last_login_at timestamp with time zone,
    agence_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: TABLE users; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.users IS 'Identités BEA DIGITAL (FastAPI JWT). auth.users Supabase n’est pas utilisé par l’application.';


--
-- Name: agences agences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agences
    ADD CONSTRAINT agences_pkey PRIMARY KEY (id);


--
-- Name: ajustements ajustements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ajustements
    ADD CONSTRAINT ajustements_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: amortissements amortissements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.amortissements
    ADD CONSTRAINT amortissements_pkey PRIMARY KEY (id);


--
-- Name: api_error_events api_error_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_error_events
    ADD CONSTRAINT api_error_events_pkey PRIMARY KEY (id);


--
-- Name: archive_dossiers archive_dossiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_dossiers
    ADD CONSTRAINT archive_dossiers_pkey PRIMARY KEY (id);


--
-- Name: archive_fichiers archive_fichiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_fichiers
    ADD CONSTRAINT archive_fichiers_pkey PRIMARY KEY (id);


--
-- Name: archive_lignes archive_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_lignes
    ADD CONSTRAINT archive_lignes_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: auth_login_attempts auth_login_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_login_attempts
    ADD CONSTRAINT auth_login_attempts_pkey PRIMARY KEY (id);


--
-- Name: auth_sessions auth_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_pkey PRIMARY KEY (id);


--
-- Name: categories_immobilisation categories_immobilisation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories_immobilisation
    ADD CONSTRAINT categories_immobilisation_pkey PRIMARY KEY (id);


--
-- Name: centres_cout centres_cout_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.centres_cout
    ADD CONSTRAINT centres_cout_pkey PRIMARY KEY (id);


--
-- Name: cessions cessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cessions
    ADD CONSTRAINT cessions_pkey PRIMARY KEY (id);


--
-- Name: departements departements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departements
    ADD CONSTRAINT departements_pkey PRIMARY KEY (id);


--
-- Name: directions directions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.directions
    ADD CONSTRAINT directions_pkey PRIMARY KEY (id);


--
-- Name: ecritures_comptables ecritures_comptables_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ecritures_comptables
    ADD CONSTRAINT ecritures_comptables_pkey PRIMARY KEY (id);


--
-- Name: exercices_comptables exercices_comptables_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exercices_comptables
    ADD CONSTRAINT exercices_comptables_pkey PRIMARY KEY (id);


--
-- Name: fournisseurs fournisseurs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fournisseurs
    ADD CONSTRAINT fournisseurs_pkey PRIMARY KEY (id);


--
-- Name: ged_documents ged_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ged_documents
    ADD CONSTRAINT ged_documents_pkey PRIMARY KEY (id);


--
-- Name: immobilisations immobilisations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.immobilisations
    ADD CONSTRAINT immobilisations_pkey PRIMARY KEY (id);


--
-- Name: inventaire_scans inventaire_scans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventaire_scans
    ADD CONSTRAINT inventaire_scans_pkey PRIMARY KEY (id);


--
-- Name: journaux journaux_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.journaux
    ADD CONSTRAINT journaux_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_bl mg_achat_bl_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_bl
    ADD CONSTRAINT mg_achat_bl_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_comparaisons mg_achat_comparaisons_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_comparaisons
    ADD CONSTRAINT mg_achat_comparaisons_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_consultation_fournisseurs mg_achat_consultation_fournisseurs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultation_fournisseurs
    ADD CONSTRAINT mg_achat_consultation_fournisseurs_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_consultations mg_achat_consultations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultations
    ADD CONSTRAINT mg_achat_consultations_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_demande_lignes mg_achat_demande_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_demande_lignes
    ADD CONSTRAINT mg_achat_demande_lignes_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_demandes mg_achat_demandes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_demandes
    ADD CONSTRAINT mg_achat_demandes_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_devis_lignes mg_achat_devis_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_devis_lignes
    ADD CONSTRAINT mg_achat_devis_lignes_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_devis mg_achat_devis_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_devis
    ADD CONSTRAINT mg_achat_devis_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_evenements mg_achat_evenements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_evenements
    ADD CONSTRAINT mg_achat_evenements_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_facture_lignes mg_achat_facture_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_facture_lignes
    ADD CONSTRAINT mg_achat_facture_lignes_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_factures mg_achat_factures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_factures
    ADD CONSTRAINT mg_achat_factures_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_paiements mg_achat_paiements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_paiements
    ADD CONSTRAINT mg_achat_paiements_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_parametres mg_achat_parametres_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_parametres
    ADD CONSTRAINT mg_achat_parametres_pkey PRIMARY KEY (cle);


--
-- Name: mg_achat_reception_lignes mg_achat_reception_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_reception_lignes
    ADD CONSTRAINT mg_achat_reception_lignes_pkey PRIMARY KEY (id);


--
-- Name: mg_achat_receptions mg_achat_receptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_receptions
    ADD CONSTRAINT mg_achat_receptions_pkey PRIMARY KEY (id);


--
-- Name: mg_article_familles mg_article_familles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_article_familles
    ADD CONSTRAINT mg_article_familles_pkey PRIMARY KEY (id);


--
-- Name: mg_articles mg_articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_articles
    ADD CONSTRAINT mg_articles_pkey PRIMARY KEY (id);


--
-- Name: mg_bc_lignes mg_bc_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bc_lignes
    ADD CONSTRAINT mg_bc_lignes_pkey PRIMARY KEY (id);


--
-- Name: mg_bons_commande mg_bons_commande_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT mg_bons_commande_pkey PRIMARY KEY (id);


--
-- Name: mg_contrat_echeances mg_contrat_echeances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_echeances
    ADD CONSTRAINT mg_contrat_echeances_pkey PRIMARY KEY (id);


--
-- Name: mg_contrat_historique mg_contrat_historique_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_historique
    ADD CONSTRAINT mg_contrat_historique_pkey PRIMARY KEY (id);


--
-- Name: mg_contrat_paiements mg_contrat_paiements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_paiements
    ADD CONSTRAINT mg_contrat_paiements_pkey PRIMARY KEY (id);


--
-- Name: mg_contrat_parametres mg_contrat_parametres_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_parametres
    ADD CONSTRAINT mg_contrat_parametres_pkey PRIMARY KEY (id);


--
-- Name: mg_contrat_types mg_contrat_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_types
    ADD CONSTRAINT mg_contrat_types_pkey PRIMARY KEY (id);


--
-- Name: mg_contrats mg_contrats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrats
    ADD CONSTRAINT mg_contrats_pkey PRIMARY KEY (id);


--
-- Name: mg_demande_fourniture_lignes mg_demande_fourniture_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_demande_fourniture_lignes
    ADD CONSTRAINT mg_demande_fourniture_lignes_pkey PRIMARY KEY (id);


--
-- Name: mg_demandes_fourniture mg_demandes_fourniture_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_demandes_fourniture
    ADD CONSTRAINT mg_demandes_fourniture_pkey PRIMARY KEY (id);


--
-- Name: mg_employee_request_items mg_employee_request_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_request_items
    ADD CONSTRAINT mg_employee_request_items_pkey PRIMARY KEY (id);


--
-- Name: mg_employee_requests mg_employee_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_pkey PRIMARY KEY (id);


--
-- Name: mg_inventaire_lignes mg_inventaire_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaire_lignes
    ADD CONSTRAINT mg_inventaire_lignes_pkey PRIMARY KEY (id);


--
-- Name: mg_inventaires mg_inventaires_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaires
    ADD CONSTRAINT mg_inventaires_pkey PRIMARY KEY (id);


--
-- Name: mg_note_frais_categories mg_note_frais_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_categories
    ADD CONSTRAINT mg_note_frais_categories_pkey PRIMARY KEY (id);


--
-- Name: mg_note_frais_historique mg_note_frais_historique_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_historique
    ADD CONSTRAINT mg_note_frais_historique_pkey PRIMARY KEY (id);


--
-- Name: mg_note_frais_lignes mg_note_frais_lignes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_lignes
    ADD CONSTRAINT mg_note_frais_lignes_pkey PRIMARY KEY (id);


--
-- Name: mg_note_frais_parametres mg_note_frais_parametres_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_parametres
    ADD CONSTRAINT mg_note_frais_parametres_pkey PRIMARY KEY (id);


--
-- Name: mg_notes_frais mg_notes_frais_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_notes_frais
    ADD CONSTRAINT mg_notes_frais_pkey PRIMARY KEY (id);


--
-- Name: mg_procurement_batch_items mg_procurement_batch_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batch_items
    ADD CONSTRAINT mg_procurement_batch_items_pkey PRIMARY KEY (id);


--
-- Name: mg_procurement_batches mg_procurement_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batches
    ADD CONSTRAINT mg_procurement_batches_pkey PRIMARY KEY (id);


--
-- Name: mg_request_approvals mg_request_approvals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_request_approvals
    ADD CONSTRAINT mg_request_approvals_pkey PRIMARY KEY (id);


--
-- Name: mg_request_categories mg_request_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_request_categories
    ADD CONSTRAINT mg_request_categories_pkey PRIMARY KEY (id);


--
-- Name: mg_request_comments mg_request_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_request_comments
    ADD CONSTRAINT mg_request_comments_pkey PRIMARY KEY (id);


--
-- Name: mg_stock_mouvements mg_stock_mouvements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_mouvements
    ADD CONSTRAINT mg_stock_mouvements_pkey PRIMARY KEY (id);


--
-- Name: mg_stock_parametres mg_stock_parametres_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_parametres
    ADD CONSTRAINT mg_stock_parametres_pkey PRIMARY KEY (id);


--
-- Name: mg_stock_periodes mg_stock_periodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_periodes
    ADD CONSTRAINT mg_stock_periodes_pkey PRIMARY KEY (id);


--
-- Name: mg_stock_soldes mg_stock_soldes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_soldes
    ADD CONSTRAINT mg_stock_soldes_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: parametrage_amortissement parametrage_amortissement_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parametrage_amortissement
    ADD CONSTRAINT parametrage_amortissement_pkey PRIMARY KEY (id);


--
-- Name: parametrage_ecritures parametrage_ecritures_categorie_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parametrage_ecritures
    ADD CONSTRAINT parametrage_ecritures_categorie_id_key UNIQUE (categorie_id);


--
-- Name: parametrage_ecritures parametrage_ecritures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parametrage_ecritures
    ADD CONSTRAINT parametrage_ecritures_pkey PRIMARY KEY (id);


--
-- Name: password_history password_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_history
    ADD CONSTRAINT password_history_pkey PRIMARY KEY (id);


--
-- Name: password_reset_jtis password_reset_jtis_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_jtis
    ADD CONSTRAINT password_reset_jtis_pkey PRIMARY KEY (jti);


--
-- Name: periodes_amortissement_categories periodes_amortissement_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement_categories
    ADD CONSTRAINT periodes_amortissement_categories_pkey PRIMARY KEY (id);


--
-- Name: periodes_amortissement periodes_amortissement_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement
    ADD CONSTRAINT periodes_amortissement_pkey PRIMARY KEY (id);


--
-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);


--
-- Name: pieces_jointes pieces_jointes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pieces_jointes
    ADD CONSTRAINT pieces_jointes_pkey PRIMARY KEY (id);


--
-- Name: plan_comptable plan_comptable_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_comptable
    ADD CONSTRAINT plan_comptable_pkey PRIMARY KEY (id);


--
-- Name: plateforme_espaces plateforme_espaces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plateforme_espaces
    ADD CONSTRAINT plateforme_espaces_pkey PRIMARY KEY (id);


--
-- Name: plateforme_modules plateforme_modules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plateforme_modules
    ADD CONSTRAINT plateforme_modules_pkey PRIMARY KEY (id);


--
-- Name: platform_backups platform_backups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_backups
    ADD CONSTRAINT platform_backups_pkey PRIMARY KEY (id);


--
-- Name: platform_module_versions platform_module_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_module_versions
    ADD CONSTRAINT platform_module_versions_pkey PRIMARY KEY (id);


--
-- Name: platform_ops_flags platform_ops_flags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_ops_flags
    ADD CONSTRAINT platform_ops_flags_pkey PRIMARY KEY (key);


--
-- Name: platform_restores platform_restores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_restores
    ADD CONSTRAINT platform_restores_pkey PRIMARY KEY (id);


--
-- Name: rebuts rebuts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rebuts
    ADD CONSTRAINT rebuts_pkey PRIMARY KEY (id);


--
-- Name: reevaluations reevaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reevaluations
    ADD CONSTRAINT reevaluations_pkey PRIMARY KEY (id);


--
-- Name: role_permissions role_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (role_id, permission_id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: security_incidents security_incidents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents
    ADD CONSTRAINT security_incidents_pkey PRIMARY KEY (id);


--
-- Name: soldes_compte_orion soldes_compte_orion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soldes_compte_orion
    ADD CONSTRAINT soldes_compte_orion_pkey PRIMARY KEY (id);


--
-- Name: soldes_ouverture_immobilisations soldes_ouverture_immobilisations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soldes_ouverture_immobilisations
    ADD CONSTRAINT soldes_ouverture_immobilisations_pkey PRIMARY KEY (id);


--
-- Name: amortissements uq_amort_periode; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.amortissements
    ADD CONSTRAINT uq_amort_periode UNIQUE (immobilisation_id, periode);


--
-- Name: archive_dossiers uq_archive_dossiers_annee; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_dossiers
    ADD CONSTRAINT uq_archive_dossiers_annee UNIQUE (annee);


--
-- Name: exercices_comptables uq_exercices_comptables_annee; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exercices_comptables
    ADD CONSTRAINT uq_exercices_comptables_annee UNIQUE (annee);


--
-- Name: mg_achat_bl uq_mg_achat_bl_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_bl
    ADD CONSTRAINT uq_mg_achat_bl_reference UNIQUE (reference);


--
-- Name: mg_achat_comparaisons uq_mg_achat_comparaisons_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_comparaisons
    ADD CONSTRAINT uq_mg_achat_comparaisons_reference UNIQUE (reference);


--
-- Name: mg_achat_consultation_fournisseurs uq_mg_achat_cons_fourn; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultation_fournisseurs
    ADD CONSTRAINT uq_mg_achat_cons_fourn UNIQUE (consultation_id, fournisseur_id);


--
-- Name: mg_achat_consultations uq_mg_achat_consultations_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultations
    ADD CONSTRAINT uq_mg_achat_consultations_reference UNIQUE (reference);


--
-- Name: mg_achat_demandes uq_mg_achat_demandes_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_demandes
    ADD CONSTRAINT uq_mg_achat_demandes_reference UNIQUE (reference);


--
-- Name: mg_achat_devis uq_mg_achat_devis_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_devis
    ADD CONSTRAINT uq_mg_achat_devis_reference UNIQUE (reference);


--
-- Name: mg_achat_factures uq_mg_achat_factures_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_factures
    ADD CONSTRAINT uq_mg_achat_factures_reference UNIQUE (reference);


--
-- Name: mg_achat_paiements uq_mg_achat_paiements_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_paiements
    ADD CONSTRAINT uq_mg_achat_paiements_reference UNIQUE (reference);


--
-- Name: mg_achat_receptions uq_mg_achat_receptions_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_receptions
    ADD CONSTRAINT uq_mg_achat_receptions_reference UNIQUE (reference);


--
-- Name: mg_article_familles uq_mg_article_familles_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_article_familles
    ADD CONSTRAINT uq_mg_article_familles_code UNIQUE (code);


--
-- Name: mg_articles uq_mg_articles_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_articles
    ADD CONSTRAINT uq_mg_articles_code UNIQUE (code);


--
-- Name: mg_bons_commande uq_mg_bons_commande_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT uq_mg_bons_commande_reference UNIQUE (reference);


--
-- Name: mg_contrat_parametres uq_mg_contrat_parametres_cle; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_parametres
    ADD CONSTRAINT uq_mg_contrat_parametres_cle UNIQUE (cle);


--
-- Name: mg_contrat_types uq_mg_contrat_types_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_types
    ADD CONSTRAINT uq_mg_contrat_types_code UNIQUE (code);


--
-- Name: mg_contrats uq_mg_contrats_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrats
    ADD CONSTRAINT uq_mg_contrats_reference UNIQUE (reference);


--
-- Name: mg_demandes_fourniture uq_mg_demandes_fourniture_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_demandes_fourniture
    ADD CONSTRAINT uq_mg_demandes_fourniture_reference UNIQUE (reference);


--
-- Name: mg_inventaires uq_mg_inventaires_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaires
    ADD CONSTRAINT uq_mg_inventaires_reference UNIQUE (reference);


--
-- Name: mg_note_frais_categories uq_mg_note_frais_categories_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_categories
    ADD CONSTRAINT uq_mg_note_frais_categories_code UNIQUE (code);


--
-- Name: mg_note_frais_parametres uq_mg_note_frais_parametres_cle; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_parametres
    ADD CONSTRAINT uq_mg_note_frais_parametres_cle UNIQUE (cle);


--
-- Name: mg_notes_frais uq_mg_notes_frais_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_notes_frais
    ADD CONSTRAINT uq_mg_notes_frais_reference UNIQUE (reference);


--
-- Name: mg_procurement_batch_items uq_mg_procurement_batch_items_request_item; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batch_items
    ADD CONSTRAINT uq_mg_procurement_batch_items_request_item UNIQUE (request_item_id);


--
-- Name: mg_request_categories uq_mg_request_categories_owner_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_request_categories
    ADD CONSTRAINT uq_mg_request_categories_owner_code UNIQUE (owner_espace_code, code);


--
-- Name: mg_stock_parametres uq_mg_stock_parametres_cle; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_parametres
    ADD CONSTRAINT uq_mg_stock_parametres_cle UNIQUE (cle);


--
-- Name: mg_stock_periodes uq_mg_stock_periodes_annee_mois; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_periodes
    ADD CONSTRAINT uq_mg_stock_periodes_annee_mois UNIQUE (annee, mois);


--
-- Name: mg_stock_soldes uq_mg_stock_soldes_periode_article; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_soldes
    ADD CONSTRAINT uq_mg_stock_soldes_periode_article UNIQUE (periode_id, article_id);


--
-- Name: periodes_amortissement_categories uq_periode_amort_categorie; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement_categories
    ADD CONSTRAINT uq_periode_amort_categorie UNIQUE (periode_id, categorie_id);


--
-- Name: periodes_amortissement uq_periode_amort_exercice_trimestre; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement
    ADD CONSTRAINT uq_periode_amort_exercice_trimestre UNIQUE (exercice_id, trimestre);


--
-- Name: soldes_compte_orion uq_solde_compte_orion_annee_compte; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soldes_compte_orion
    ADD CONSTRAINT uq_solde_compte_orion_annee_compte UNIQUE (annee, compte_immobilisation);


--
-- Name: soldes_ouverture_immobilisations uq_solde_ouverture_exercice_immo; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soldes_ouverture_immobilisations
    ADD CONSTRAINT uq_solde_ouverture_exercice_immo UNIQUE (exercice_id, immobilisation_id);


--
-- Name: user_espace_acces user_espace_acces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_espace_acces
    ADD CONSTRAINT user_espace_acces_pkey PRIMARY KEY (user_id, espace_id);


--
-- Name: user_module_acces user_module_acces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_module_acces
    ADD CONSTRAINT user_module_acces_pkey PRIMARY KEY (user_id, module_id);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_agences_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_agences_code ON public.agences USING btree (code);


--
-- Name: ix_agences_code_banque; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agences_code_banque ON public.agences USING btree (code_banque);


--
-- Name: ix_ajustements_immobilisation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ajustements_immobilisation_id ON public.ajustements USING btree (immobilisation_id);


--
-- Name: ix_amortissements_immobilisation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_amortissements_immobilisation_id ON public.amortissements USING btree (immobilisation_id);


--
-- Name: ix_amortissements_periode; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_amortissements_periode ON public.amortissements USING btree (periode);


--
-- Name: ix_api_error_events_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_error_events_code ON public.api_error_events USING btree (code);


--
-- Name: ix_api_error_events_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_error_events_created_at ON public.api_error_events USING btree (created_at DESC);


--
-- Name: ix_api_error_events_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_error_events_request_id ON public.api_error_events USING btree (request_id);


--
-- Name: ix_api_error_events_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_error_events_status ON public.api_error_events USING btree (status_code);


--
-- Name: ix_archive_dossiers_annee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_dossiers_annee ON public.archive_dossiers USING btree (annee);


--
-- Name: ix_archive_fichiers_dossier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_fichiers_dossier_id ON public.archive_fichiers USING btree (dossier_id);


--
-- Name: ix_archive_fichiers_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_fichiers_kind ON public.archive_fichiers USING btree (kind);


--
-- Name: ix_archive_fichiers_nature_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_fichiers_nature_code ON public.archive_fichiers USING btree (nature_code);


--
-- Name: ix_archive_fichiers_parse_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_fichiers_parse_status ON public.archive_fichiers USING btree (parse_status);


--
-- Name: ix_archive_lignes_categorie_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_lignes_categorie_code ON public.archive_lignes USING btree (categorie_code);


--
-- Name: ix_archive_lignes_date_acquisition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_lignes_date_acquisition ON public.archive_lignes USING btree (date_acquisition);


--
-- Name: ix_archive_lignes_fichier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_lignes_fichier_id ON public.archive_lignes USING btree (fichier_id);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_audit_logs_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_entity ON public.audit_logs USING btree (entity);


--
-- Name: ix_audit_logs_espace_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_espace_code ON public.audit_logs USING btree (espace_code);


--
-- Name: ix_audit_logs_module_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_module_code ON public.audit_logs USING btree (module_code);


--
-- Name: ix_audit_logs_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_request_id ON public.audit_logs USING btree (request_id);


--
-- Name: ix_auth_login_attempts_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_login_attempts_email ON public.auth_login_attempts USING btree (email);


--
-- Name: ix_auth_login_attempts_ip_address; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_login_attempts_ip_address ON public.auth_login_attempts USING btree (ip_address);


--
-- Name: ix_auth_login_attempts_login_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_login_attempts_login_kind ON public.auth_login_attempts USING btree (login_kind);


--
-- Name: ix_auth_sessions_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_kind ON public.auth_sessions USING btree (kind);


--
-- Name: ix_auth_sessions_module_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_module_code ON public.auth_sessions USING btree (module_code);


--
-- Name: ix_auth_sessions_parent_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_parent_session_id ON public.auth_sessions USING btree (parent_session_id);


--
-- Name: ix_auth_sessions_refresh_jti; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_auth_sessions_refresh_jti ON public.auth_sessions USING btree (refresh_jti);


--
-- Name: ix_auth_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_user_id ON public.auth_sessions USING btree (user_id);


--
-- Name: ix_categories_immobilisation_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_categories_immobilisation_code ON public.categories_immobilisation USING btree (code);


--
-- Name: ix_categories_immobilisation_compte_immobilisation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_categories_immobilisation_compte_immobilisation ON public.categories_immobilisation USING btree (compte_immobilisation);


--
-- Name: ix_centres_cout_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_centres_cout_code ON public.centres_cout USING btree (code);


--
-- Name: ix_cessions_immobilisation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cessions_immobilisation_id ON public.cessions USING btree (immobilisation_id);


--
-- Name: ix_departements_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_departements_code ON public.departements USING btree (code);


--
-- Name: ix_directions_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_directions_code ON public.directions USING btree (code);


--
-- Name: ix_exercices_comptables_annee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_exercices_comptables_annee ON public.exercices_comptables USING btree (annee);


--
-- Name: ix_exercices_comptables_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_exercices_comptables_statut ON public.exercices_comptables USING btree (statut);


--
-- Name: ix_fournisseurs_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_fournisseurs_code ON public.fournisseurs USING btree (code);


--
-- Name: ix_fournisseurs_nif; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fournisseurs_nif ON public.fournisseurs USING btree (nif);


--
-- Name: ix_fournisseurs_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fournisseurs_type ON public.fournisseurs USING btree (type_fournisseur);


--
-- Name: ix_fournisseurs_ville; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fournisseurs_ville ON public.fournisseurs USING btree (ville);


--
-- Name: ix_ged_documents_agence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_agence_id ON public.ged_documents USING btree (agence_id);


--
-- Name: ix_ged_documents_archived_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_archived_at ON public.ged_documents USING btree (archived_at);


--
-- Name: ix_ged_documents_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_department_id ON public.ged_documents USING btree (department_id);


--
-- Name: ix_ged_documents_doc_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_doc_type ON public.ged_documents USING btree (doc_type);


--
-- Name: ix_ged_documents_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_entity ON public.ged_documents USING btree (entity);


--
-- Name: ix_ged_documents_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_entity_id ON public.ged_documents USING btree (entity_id);


--
-- Name: ix_ged_documents_espace_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_espace_code ON public.ged_documents USING btree (espace_code);


--
-- Name: ix_ged_documents_filename_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_filename_trgm ON public.ged_documents USING gin (filename public.gin_trgm_ops);


--
-- Name: ix_ged_documents_fournisseur_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_fournisseur_id ON public.ged_documents USING btree (fournisseur_id);


--
-- Name: ix_ged_documents_module_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_module_code ON public.ged_documents USING btree (module_code);


--
-- Name: ix_ged_documents_ocr_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_ocr_status ON public.ged_documents USING btree (ocr_status);


--
-- Name: ix_ged_documents_ocr_text_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_ocr_text_search ON public.ged_documents USING gin (ocr_text_search);


--
-- Name: ix_ged_documents_parent_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_parent_document_id ON public.ged_documents USING btree (parent_document_id);


--
-- Name: ix_ged_documents_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_reference ON public.ged_documents USING btree (reference);


--
-- Name: ix_ged_documents_reference_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_reference_trgm ON public.ged_documents USING gin (reference public.gin_trgm_ops);


--
-- Name: ix_ged_documents_security_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_security_level ON public.ged_documents USING btree (security_level);


--
-- Name: ix_ged_documents_title_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_title_trgm ON public.ged_documents USING gin (title public.gin_trgm_ops);


--
-- Name: ix_ged_documents_uploaded_by_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ged_documents_uploaded_by_id ON public.ged_documents USING btree (uploaded_by_id);


--
-- Name: ix_immobilisations_code_inventaire; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_immobilisations_code_inventaire ON public.immobilisations USING btree (code_inventaire);


--
-- Name: ix_inventaire_scans_code_scanne; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventaire_scans_code_scanne ON public.inventaire_scans USING btree (code_scanne);


--
-- Name: ix_journaux_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_journaux_code ON public.journaux USING btree (code);


--
-- Name: ix_mg_achat_bl_bon_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_bl_bon_id ON public.mg_achat_bl USING btree (bon_id);


--
-- Name: ix_mg_achat_bl_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_bl_reference ON public.mg_achat_bl USING btree (reference);


--
-- Name: ix_mg_achat_comparaisons_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_comparaisons_reference ON public.mg_achat_comparaisons USING btree (reference);


--
-- Name: ix_mg_achat_cons_fourn_consultation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_cons_fourn_consultation_id ON public.mg_achat_consultation_fournisseurs USING btree (consultation_id);


--
-- Name: ix_mg_achat_consultations_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_consultations_reference ON public.mg_achat_consultations USING btree (reference);


--
-- Name: ix_mg_achat_consultations_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_consultations_statut ON public.mg_achat_consultations USING btree (statut);


--
-- Name: ix_mg_achat_demande_lignes_demande_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_demande_lignes_demande_id ON public.mg_achat_demande_lignes USING btree (demande_id);


--
-- Name: ix_mg_achat_demandes_agence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_demandes_agence_id ON public.mg_achat_demandes USING btree (agence_id);


--
-- Name: ix_mg_achat_demandes_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_demandes_reference ON public.mg_achat_demandes USING btree (reference);


--
-- Name: ix_mg_achat_demandes_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_demandes_source ON public.mg_achat_demandes USING btree (source_type, source_id);


--
-- Name: ix_mg_achat_demandes_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_demandes_statut ON public.mg_achat_demandes USING btree (statut);


--
-- Name: ix_mg_achat_devis_fournisseur_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_devis_fournisseur_id ON public.mg_achat_devis USING btree (fournisseur_id);


--
-- Name: ix_mg_achat_devis_lignes_devis_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_devis_lignes_devis_id ON public.mg_achat_devis_lignes USING btree (devis_id);


--
-- Name: ix_mg_achat_devis_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_devis_reference ON public.mg_achat_devis USING btree (reference);


--
-- Name: ix_mg_achat_evenements_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_evenements_entity ON public.mg_achat_evenements USING btree (entity_type, entity_id);


--
-- Name: ix_mg_achat_facture_lignes_facture_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_facture_lignes_facture_id ON public.mg_achat_facture_lignes USING btree (facture_id);


--
-- Name: ix_mg_achat_factures_bon_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_factures_bon_id ON public.mg_achat_factures USING btree (bon_id);


--
-- Name: ix_mg_achat_factures_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_factures_reference ON public.mg_achat_factures USING btree (reference);


--
-- Name: ix_mg_achat_paiements_facture_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_paiements_facture_id ON public.mg_achat_paiements USING btree (facture_id);


--
-- Name: ix_mg_achat_paiements_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_paiements_reference ON public.mg_achat_paiements USING btree (reference);


--
-- Name: ix_mg_achat_reception_lignes_reception_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_reception_lignes_reception_id ON public.mg_achat_reception_lignes USING btree (reception_id);


--
-- Name: ix_mg_achat_receptions_bon_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_receptions_bon_id ON public.mg_achat_receptions USING btree (bon_id);


--
-- Name: ix_mg_achat_receptions_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_achat_receptions_reference ON public.mg_achat_receptions USING btree (reference);


--
-- Name: ix_mg_article_familles_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_article_familles_code ON public.mg_article_familles USING btree (code);


--
-- Name: ix_mg_articles_agence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_articles_agence_id ON public.mg_articles USING btree (agence_id);


--
-- Name: ix_mg_articles_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_articles_code ON public.mg_articles USING btree (code);


--
-- Name: ix_mg_articles_famille_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_articles_famille_id ON public.mg_articles USING btree (famille_id);


--
-- Name: ix_mg_bc_lignes_article_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_bc_lignes_article_id ON public.mg_bc_lignes USING btree (article_id);


--
-- Name: ix_mg_bc_lignes_bc_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_bc_lignes_bc_id ON public.mg_bc_lignes USING btree (bc_id);


--
-- Name: ix_mg_bons_commande_contrat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_bons_commande_contrat_id ON public.mg_bons_commande USING btree (contrat_id);


--
-- Name: ix_mg_bons_commande_demande_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_bons_commande_demande_id ON public.mg_bons_commande USING btree (demande_id);


--
-- Name: ix_mg_bons_commande_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_bons_commande_reference ON public.mg_bons_commande USING btree (reference);


--
-- Name: ix_mg_bons_commande_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_bons_commande_statut ON public.mg_bons_commande USING btree (statut);


--
-- Name: ix_mg_contrat_echeances_contrat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_contrat_echeances_contrat_id ON public.mg_contrat_echeances USING btree (contrat_id);


--
-- Name: ix_mg_contrat_historique_contrat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_contrat_historique_contrat_id ON public.mg_contrat_historique USING btree (contrat_id);


--
-- Name: ix_mg_contrat_paiements_contrat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_contrat_paiements_contrat_id ON public.mg_contrat_paiements USING btree (contrat_id);


--
-- Name: ix_mg_contrats_agence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_contrats_agence_id ON public.mg_contrats USING btree (agence_id);


--
-- Name: ix_mg_contrats_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_contrats_reference ON public.mg_contrats USING btree (reference);


--
-- Name: ix_mg_contrats_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_contrats_statut ON public.mg_contrats USING btree (statut);


--
-- Name: ix_mg_demande_fourniture_lignes_demande_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_demande_fourniture_lignes_demande_id ON public.mg_demande_fourniture_lignes USING btree (demande_id);


--
-- Name: ix_mg_demandes_fourniture_agence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_demandes_fourniture_agence_id ON public.mg_demandes_fourniture USING btree (agence_id);


--
-- Name: ix_mg_demandes_fourniture_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_demandes_fourniture_reference ON public.mg_demandes_fourniture USING btree (reference);


--
-- Name: ix_mg_demandes_fourniture_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_demandes_fourniture_statut ON public.mg_demandes_fourniture USING btree (statut);


--
-- Name: ix_mg_employee_request_items_request; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_employee_request_items_request ON public.mg_employee_request_items USING btree (request_id);


--
-- Name: ix_mg_employee_requests_agency; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_employee_requests_agency ON public.mg_employee_requests USING btree (agency_id);


--
-- Name: ix_mg_employee_requests_assigned; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_employee_requests_assigned ON public.mg_employee_requests USING btree (assigned_to_id);


--
-- Name: ix_mg_employee_requests_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_mg_employee_requests_number ON public.mg_employee_requests USING btree (request_number);


--
-- Name: ix_mg_employee_requests_requester; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_employee_requests_requester ON public.mg_employee_requests USING btree (requester_id);


--
-- Name: ix_mg_employee_requests_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_employee_requests_source ON public.mg_employee_requests USING btree (source_espace_code);


--
-- Name: ix_mg_employee_requests_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_employee_requests_status ON public.mg_employee_requests USING btree (status);


--
-- Name: ix_mg_employee_requests_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_employee_requests_target ON public.mg_employee_requests USING btree (target_espace_code);


--
-- Name: ix_mg_inventaire_lignes_article_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_inventaire_lignes_article_id ON public.mg_inventaire_lignes USING btree (article_id);


--
-- Name: ix_mg_inventaire_lignes_inventaire_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_inventaire_lignes_inventaire_id ON public.mg_inventaire_lignes USING btree (inventaire_id);


--
-- Name: ix_mg_inventaires_agence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_inventaires_agence_id ON public.mg_inventaires USING btree (agence_id);


--
-- Name: ix_mg_inventaires_periode_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_inventaires_periode_id ON public.mg_inventaires USING btree (periode_id);


--
-- Name: ix_mg_inventaires_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_inventaires_statut ON public.mg_inventaires USING btree (statut);


--
-- Name: ix_mg_note_frais_categories_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_note_frais_categories_code ON public.mg_note_frais_categories USING btree (code);


--
-- Name: ix_mg_note_frais_historique_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_note_frais_historique_note_id ON public.mg_note_frais_historique USING btree (note_id);


--
-- Name: ix_mg_note_frais_lignes_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_note_frais_lignes_note_id ON public.mg_note_frais_lignes USING btree (note_id);


--
-- Name: ix_mg_notes_frais_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_notes_frais_reference ON public.mg_notes_frais USING btree (reference);


--
-- Name: ix_mg_notes_frais_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_notes_frais_statut ON public.mg_notes_frais USING btree (statut);


--
-- Name: ix_mg_procurement_batch_items_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_procurement_batch_items_batch ON public.mg_procurement_batch_items USING btree (batch_id);


--
-- Name: ix_mg_procurement_batches_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_mg_procurement_batches_number ON public.mg_procurement_batches USING btree (batch_number);


--
-- Name: ix_mg_procurement_batches_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_procurement_batches_status ON public.mg_procurement_batches USING btree (status);


--
-- Name: ix_mg_request_approvals_request; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_request_approvals_request ON public.mg_request_approvals USING btree (request_id);


--
-- Name: ix_mg_request_categories_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_request_categories_code ON public.mg_request_categories USING btree (code);


--
-- Name: ix_mg_request_categories_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_request_categories_owner ON public.mg_request_categories USING btree (owner_espace_code);


--
-- Name: ix_mg_request_categories_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_request_categories_target ON public.mg_request_categories USING btree (target_espace_code);


--
-- Name: ix_mg_request_comments_request; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_request_comments_request ON public.mg_request_comments USING btree (request_id);


--
-- Name: ix_mg_stock_mouvements_agence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_mouvements_agence_id ON public.mg_stock_mouvements USING btree (agence_id);


--
-- Name: ix_mg_stock_mouvements_article_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_mouvements_article_id ON public.mg_stock_mouvements USING btree (article_id);


--
-- Name: ix_mg_stock_mouvements_periode_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_mouvements_periode_id ON public.mg_stock_mouvements USING btree (periode_id);


--
-- Name: ix_mg_stock_mouvements_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_mouvements_reference ON public.mg_stock_mouvements USING btree (reference);


--
-- Name: ix_mg_stock_mouvements_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_mouvements_type ON public.mg_stock_mouvements USING btree (type_mouvement);


--
-- Name: ix_mg_stock_periodes_agence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_periodes_agence_id ON public.mg_stock_periodes USING btree (agence_id);


--
-- Name: ix_mg_stock_periodes_annee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_periodes_annee ON public.mg_stock_periodes USING btree (annee);


--
-- Name: ix_mg_stock_periodes_mois; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_periodes_mois ON public.mg_stock_periodes USING btree (mois);


--
-- Name: ix_mg_stock_periodes_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_periodes_statut ON public.mg_stock_periodes USING btree (statut);


--
-- Name: ix_mg_stock_soldes_article_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_soldes_article_id ON public.mg_stock_soldes USING btree (article_id);


--
-- Name: ix_mg_stock_soldes_periode_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mg_stock_soldes_periode_id ON public.mg_stock_soldes USING btree (periode_id);


--
-- Name: ix_notifications_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_archived ON public.notifications USING btree (archived);


--
-- Name: ix_notifications_categorie; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_categorie ON public.notifications USING btree (categorie);


--
-- Name: ix_notifications_espace_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_espace_code ON public.notifications USING btree (espace_code);


--
-- Name: ix_notifications_event_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_event_code ON public.notifications USING btree (event_code);


--
-- Name: ix_notifications_module_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_module_code ON public.notifications USING btree (module_code);


--
-- Name: ix_notifications_priorite; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_priorite ON public.notifications USING btree (priorite);


--
-- Name: ix_notifications_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);


--
-- Name: ix_parametrage_ecritures_categorie_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_parametrage_ecritures_categorie_id ON public.parametrage_ecritures USING btree (categorie_id);


--
-- Name: ix_password_history_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_history_user_id ON public.password_history USING btree (user_id);


--
-- Name: ix_password_reset_jtis_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_reset_jtis_user_id ON public.password_reset_jtis USING btree (user_id);


--
-- Name: ix_periodes_amort_cat_categorie_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_periodes_amort_cat_categorie_id ON public.periodes_amortissement_categories USING btree (categorie_id);


--
-- Name: ix_periodes_amort_cat_periode_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_periodes_amort_cat_periode_id ON public.periodes_amortissement_categories USING btree (periode_id);


--
-- Name: ix_periodes_amort_cat_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_periodes_amort_cat_statut ON public.periodes_amortissement_categories USING btree (statut);


--
-- Name: ix_periodes_amortissement_annee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_periodes_amortissement_annee ON public.periodes_amortissement USING btree (annee);


--
-- Name: ix_periodes_amortissement_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_periodes_amortissement_code ON public.periodes_amortissement USING btree (code);


--
-- Name: ix_periodes_amortissement_exercice_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_periodes_amortissement_exercice_id ON public.periodes_amortissement USING btree (exercice_id);


--
-- Name: ix_periodes_amortissement_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_periodes_amortissement_statut ON public.periodes_amortissement USING btree (statut);


--
-- Name: ix_permissions_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_permissions_code ON public.permissions USING btree (code);


--
-- Name: ix_permissions_module; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_permissions_module ON public.permissions USING btree (module);


--
-- Name: ix_pieces_jointes_date_journee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pieces_jointes_date_journee ON public.pieces_jointes USING btree (date_journee);


--
-- Name: ix_pieces_jointes_immobilisation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pieces_jointes_immobilisation_id ON public.pieces_jointes USING btree (immobilisation_id);


--
-- Name: ix_pieces_jointes_type_piece; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pieces_jointes_type_piece ON public.pieces_jointes USING btree (type_piece);


--
-- Name: ix_plan_comptable_numero; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_plan_comptable_numero ON public.plan_comptable USING btree (numero);


--
-- Name: ix_plateforme_espaces_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_plateforme_espaces_code ON public.plateforme_espaces USING btree (code);


--
-- Name: ix_plateforme_espaces_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plateforme_espaces_statut ON public.plateforme_espaces USING btree (statut);


--
-- Name: ix_plateforme_modules_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_plateforme_modules_code ON public.plateforme_modules USING btree (code);


--
-- Name: ix_plateforme_modules_espace_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plateforme_modules_espace_id ON public.plateforme_modules USING btree (espace_id);


--
-- Name: ix_plateforme_modules_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plateforme_modules_statut ON public.plateforme_modules USING btree (statut);


--
-- Name: ix_platform_backups_backup_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_backups_backup_type ON public.platform_backups USING btree (backup_type);


--
-- Name: ix_platform_backups_espace_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_backups_espace_code ON public.platform_backups USING btree (espace_code);


--
-- Name: ix_platform_backups_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_backups_level ON public.platform_backups USING btree (level);


--
-- Name: ix_platform_backups_module_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_backups_module_code ON public.platform_backups USING btree (module_code);


--
-- Name: ix_platform_backups_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_backups_status ON public.platform_backups USING btree (status);


--
-- Name: ix_platform_module_versions_module_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_module_versions_module_id ON public.platform_module_versions USING btree (module_id);


--
-- Name: ix_platform_restores_backup_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_restores_backup_id ON public.platform_restores USING btree (backup_id);


--
-- Name: ix_platform_restores_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_restores_level ON public.platform_restores USING btree (level);


--
-- Name: ix_platform_restores_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_restores_status ON public.platform_restores USING btree (status);


--
-- Name: ix_rebuts_immobilisation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rebuts_immobilisation_id ON public.rebuts USING btree (immobilisation_id);


--
-- Name: ix_reevaluations_immobilisation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reevaluations_immobilisation_id ON public.reevaluations USING btree (immobilisation_id);


--
-- Name: ix_roles_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_roles_code ON public.roles USING btree (code);


--
-- Name: ix_security_incidents_espace_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_security_incidents_espace_code ON public.security_incidents USING btree (espace_code);


--
-- Name: ix_security_incidents_module_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_security_incidents_module_code ON public.security_incidents USING btree (module_code);


--
-- Name: ix_security_incidents_niveau; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_security_incidents_niveau ON public.security_incidents USING btree (niveau);


--
-- Name: ix_security_incidents_statut; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_security_incidents_statut ON public.security_incidents USING btree (statut);


--
-- Name: ix_security_incidents_type_incident; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_security_incidents_type_incident ON public.security_incidents USING btree (type_incident);


--
-- Name: ix_security_incidents_user_concerne_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_security_incidents_user_concerne_id ON public.security_incidents USING btree (user_concerne_id);


--
-- Name: ix_soldes_compte_orion_annee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_soldes_compte_orion_annee ON public.soldes_compte_orion USING btree (annee);


--
-- Name: ix_soldes_compte_orion_compte_immobilisation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_soldes_compte_orion_compte_immobilisation ON public.soldes_compte_orion USING btree (compte_immobilisation);


--
-- Name: ix_soldes_ouverture_immobilisations_annee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_soldes_ouverture_immobilisations_annee ON public.soldes_ouverture_immobilisations USING btree (annee);


--
-- Name: ix_soldes_ouverture_immobilisations_annee_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_soldes_ouverture_immobilisations_annee_source ON public.soldes_ouverture_immobilisations USING btree (annee_source);


--
-- Name: ix_soldes_ouverture_immobilisations_exercice_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_soldes_ouverture_immobilisations_exercice_id ON public.soldes_ouverture_immobilisations USING btree (exercice_id);


--
-- Name: ix_soldes_ouverture_immobilisations_immobilisation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_soldes_ouverture_immobilisations_immobilisation_id ON public.soldes_ouverture_immobilisations USING btree (immobilisation_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: uq_mg_contrat_paiements_ref; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_mg_contrat_paiements_ref ON public.mg_contrat_paiements USING btree (contrat_id, reference) WHERE (reference IS NOT NULL);


--
-- Name: uq_mg_contrats_renouvellement; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_mg_contrats_renouvellement ON public.mg_contrats USING btree (contrat_precedent_id) WHERE ((contrat_precedent_id IS NOT NULL) AND (deleted_at IS NULL) AND ((statut)::text <> 'ANNULE'::text));


--
-- Name: uq_mg_stock_mvt_demande_sortie; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_mg_stock_mvt_demande_sortie ON public.mg_stock_mouvements USING btree (source_id, article_id) WHERE (((source_type)::text = 'demande_fourniture'::text) AND ((type_mouvement)::text = 'SORTIE'::text));


--
-- Name: uq_mg_stock_mvt_inv_ajust; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_mg_stock_mvt_inv_ajust ON public.mg_stock_mouvements USING btree (source_id, article_id) WHERE (((source_type)::text = 'inventaire'::text) AND ((type_mouvement)::text = 'AJUSTEMENT'::text));


--
-- Name: ajustements ajustements_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ajustements
    ADD CONSTRAINT ajustements_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id);


--
-- Name: amortissements amortissements_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.amortissements
    ADD CONSTRAINT amortissements_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id) ON DELETE CASCADE;


--
-- Name: api_error_events api_error_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_error_events
    ADD CONSTRAINT api_error_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: archive_dossiers archive_dossiers_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_dossiers
    ADD CONSTRAINT archive_dossiers_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id);


--
-- Name: archive_fichiers archive_fichiers_dossier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_fichiers
    ADD CONSTRAINT archive_fichiers_dossier_id_fkey FOREIGN KEY (dossier_id) REFERENCES public.archive_dossiers(id) ON DELETE CASCADE;


--
-- Name: archive_fichiers archive_fichiers_uploaded_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_fichiers
    ADD CONSTRAINT archive_fichiers_uploaded_by_id_fkey FOREIGN KEY (uploaded_by_id) REFERENCES public.users(id);


--
-- Name: archive_lignes archive_lignes_fichier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_lignes
    ADD CONSTRAINT archive_lignes_fichier_id_fkey FOREIGN KEY (fichier_id) REFERENCES public.archive_fichiers(id) ON DELETE CASCADE;


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: auth_sessions auth_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: centres_cout centres_cout_departement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.centres_cout
    ADD CONSTRAINT centres_cout_departement_id_fkey FOREIGN KEY (departement_id) REFERENCES public.departements(id);


--
-- Name: cessions cessions_ecriture_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cessions
    ADD CONSTRAINT cessions_ecriture_id_fkey FOREIGN KEY (ecriture_id) REFERENCES public.ecritures_comptables(id);


--
-- Name: cessions cessions_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cessions
    ADD CONSTRAINT cessions_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id);


--
-- Name: departements departements_direction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departements
    ADD CONSTRAINT departements_direction_id_fkey FOREIGN KEY (direction_id) REFERENCES public.directions(id);


--
-- Name: ecritures_comptables ecritures_comptables_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ecritures_comptables
    ADD CONSTRAINT ecritures_comptables_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id);


--
-- Name: exercices_comptables exercices_comptables_archive_dossier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exercices_comptables
    ADD CONSTRAINT exercices_comptables_archive_dossier_id_fkey FOREIGN KEY (archive_dossier_id) REFERENCES public.archive_dossiers(id) ON DELETE SET NULL;


--
-- Name: exercices_comptables exercices_comptables_cloture_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exercices_comptables
    ADD CONSTRAINT exercices_comptables_cloture_by_id_fkey FOREIGN KEY (cloture_by_id) REFERENCES public.users(id);


--
-- Name: exercices_comptables exercices_comptables_ouverture_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exercices_comptables
    ADD CONSTRAINT exercices_comptables_ouverture_by_id_fkey FOREIGN KEY (ouverture_by_id) REFERENCES public.users(id);


--
-- Name: auth_sessions fk_auth_sessions_parent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT fk_auth_sessions_parent FOREIGN KEY (parent_session_id) REFERENCES public.auth_sessions(id);


--
-- Name: mg_bons_commande fk_mg_bons_comparaison_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT fk_mg_bons_comparaison_id FOREIGN KEY (comparaison_id) REFERENCES public.mg_achat_comparaisons(id);


--
-- Name: mg_bons_commande fk_mg_bons_consultation_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT fk_mg_bons_consultation_id FOREIGN KEY (consultation_id) REFERENCES public.mg_achat_consultations(id);


--
-- Name: mg_bons_commande fk_mg_bons_demande_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT fk_mg_bons_demande_id FOREIGN KEY (demande_id) REFERENCES public.mg_achat_demandes(id);


--
-- Name: mg_contrats fk_mg_contrats_agence; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrats
    ADD CONSTRAINT fk_mg_contrats_agence FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_contrats fk_mg_contrats_precedent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrats
    ADD CONSTRAINT fk_mg_contrats_precedent FOREIGN KEY (contrat_precedent_id) REFERENCES public.mg_contrats(id);


--
-- Name: mg_contrats fk_mg_contrats_responsable; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrats
    ADD CONSTRAINT fk_mg_contrats_responsable FOREIGN KEY (responsable_id) REFERENCES public.users(id);


--
-- Name: mg_employee_requests fk_mg_employee_requests_assigned; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT fk_mg_employee_requests_assigned FOREIGN KEY (assigned_to_id) REFERENCES public.users(id);


--
-- Name: notifications fk_notifications_actor_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_actor_user_id FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: pieces_jointes fk_pieces_jointes_uploaded_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pieces_jointes
    ADD CONSTRAINT fk_pieces_jointes_uploaded_by FOREIGN KEY (uploaded_by_id) REFERENCES public.users(id);


--
-- Name: security_incidents fk_security_incidents_user_concerne; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents
    ADD CONSTRAINT fk_security_incidents_user_concerne FOREIGN KEY (user_concerne_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: user_espace_acces fk_user_espace_acces_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_espace_acces
    ADD CONSTRAINT fk_user_espace_acces_created_by FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: user_module_acces fk_user_module_acces_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_module_acces
    ADD CONSTRAINT fk_user_module_acces_created_by FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: ged_documents ged_documents_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ged_documents
    ADD CONSTRAINT ged_documents_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: ged_documents ged_documents_deleted_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ged_documents
    ADD CONSTRAINT ged_documents_deleted_by_id_fkey FOREIGN KEY (deleted_by_id) REFERENCES public.users(id);


--
-- Name: ged_documents ged_documents_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ged_documents
    ADD CONSTRAINT ged_documents_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departements(id);


--
-- Name: ged_documents ged_documents_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ged_documents
    ADD CONSTRAINT ged_documents_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: ged_documents ged_documents_parent_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ged_documents
    ADD CONSTRAINT ged_documents_parent_document_id_fkey FOREIGN KEY (parent_document_id) REFERENCES public.ged_documents(id);


--
-- Name: ged_documents ged_documents_uploaded_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ged_documents
    ADD CONSTRAINT ged_documents_uploaded_by_id_fkey FOREIGN KEY (uploaded_by_id) REFERENCES public.users(id);


--
-- Name: immobilisations immobilisations_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.immobilisations
    ADD CONSTRAINT immobilisations_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: immobilisations immobilisations_categorie_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.immobilisations
    ADD CONSTRAINT immobilisations_categorie_id_fkey FOREIGN KEY (categorie_id) REFERENCES public.categories_immobilisation(id);


--
-- Name: immobilisations immobilisations_centre_cout_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.immobilisations
    ADD CONSTRAINT immobilisations_centre_cout_id_fkey FOREIGN KEY (centre_cout_id) REFERENCES public.centres_cout(id);


--
-- Name: immobilisations immobilisations_departement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.immobilisations
    ADD CONSTRAINT immobilisations_departement_id_fkey FOREIGN KEY (departement_id) REFERENCES public.departements(id);


--
-- Name: immobilisations immobilisations_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.immobilisations
    ADD CONSTRAINT immobilisations_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: immobilisations immobilisations_responsable_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.immobilisations
    ADD CONSTRAINT immobilisations_responsable_id_fkey FOREIGN KEY (responsable_id) REFERENCES public.users(id);


--
-- Name: inventaire_scans inventaire_scans_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventaire_scans
    ADD CONSTRAINT inventaire_scans_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id);


--
-- Name: inventaire_scans inventaire_scans_scanned_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventaire_scans
    ADD CONSTRAINT inventaire_scans_scanned_by_id_fkey FOREIGN KEY (scanned_by_id) REFERENCES public.users(id);


--
-- Name: mg_achat_bl mg_achat_bl_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_bl
    ADD CONSTRAINT mg_achat_bl_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_achat_bl mg_achat_bl_bon_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_bl
    ADD CONSTRAINT mg_achat_bl_bon_id_fkey FOREIGN KEY (bon_id) REFERENCES public.mg_bons_commande(id);


--
-- Name: mg_achat_bl mg_achat_bl_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_bl
    ADD CONSTRAINT mg_achat_bl_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_achat_comparaisons mg_achat_comparaisons_consultation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_comparaisons
    ADD CONSTRAINT mg_achat_comparaisons_consultation_id_fkey FOREIGN KEY (consultation_id) REFERENCES public.mg_achat_consultations(id);


--
-- Name: mg_achat_comparaisons mg_achat_comparaisons_demande_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_comparaisons
    ADD CONSTRAINT mg_achat_comparaisons_demande_id_fkey FOREIGN KEY (demande_id) REFERENCES public.mg_achat_demandes(id);


--
-- Name: mg_achat_comparaisons mg_achat_comparaisons_fournisseur_retenu_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_comparaisons
    ADD CONSTRAINT mg_achat_comparaisons_fournisseur_retenu_id_fkey FOREIGN KEY (fournisseur_retenu_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_achat_consultation_fournisseurs mg_achat_consultation_fournisseurs_consultation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultation_fournisseurs
    ADD CONSTRAINT mg_achat_consultation_fournisseurs_consultation_id_fkey FOREIGN KEY (consultation_id) REFERENCES public.mg_achat_consultations(id) ON DELETE CASCADE;


--
-- Name: mg_achat_consultation_fournisseurs mg_achat_consultation_fournisseurs_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultation_fournisseurs
    ADD CONSTRAINT mg_achat_consultation_fournisseurs_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_achat_consultations mg_achat_consultations_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultations
    ADD CONSTRAINT mg_achat_consultations_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_achat_consultations mg_achat_consultations_demande_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultations
    ADD CONSTRAINT mg_achat_consultations_demande_id_fkey FOREIGN KEY (demande_id) REFERENCES public.mg_achat_demandes(id);


--
-- Name: mg_achat_consultations mg_achat_consultations_responsable_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_consultations
    ADD CONSTRAINT mg_achat_consultations_responsable_id_fkey FOREIGN KEY (responsable_id) REFERENCES public.users(id);


--
-- Name: mg_achat_demande_lignes mg_achat_demande_lignes_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_demande_lignes
    ADD CONSTRAINT mg_achat_demande_lignes_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_achat_demande_lignes mg_achat_demande_lignes_demande_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_demande_lignes
    ADD CONSTRAINT mg_achat_demande_lignes_demande_id_fkey FOREIGN KEY (demande_id) REFERENCES public.mg_achat_demandes(id) ON DELETE CASCADE;


--
-- Name: mg_achat_demandes mg_achat_demandes_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_demandes
    ADD CONSTRAINT mg_achat_demandes_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_achat_demandes mg_achat_demandes_demandeur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_demandes
    ADD CONSTRAINT mg_achat_demandes_demandeur_id_fkey FOREIGN KEY (demandeur_id) REFERENCES public.users(id);


--
-- Name: mg_achat_demandes mg_achat_demandes_departement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_demandes
    ADD CONSTRAINT mg_achat_demandes_departement_id_fkey FOREIGN KEY (departement_id) REFERENCES public.departements(id);


--
-- Name: mg_achat_devis mg_achat_devis_consultation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_devis
    ADD CONSTRAINT mg_achat_devis_consultation_id_fkey FOREIGN KEY (consultation_id) REFERENCES public.mg_achat_consultations(id);


--
-- Name: mg_achat_devis mg_achat_devis_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_devis
    ADD CONSTRAINT mg_achat_devis_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_achat_devis_lignes mg_achat_devis_lignes_devis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_devis_lignes
    ADD CONSTRAINT mg_achat_devis_lignes_devis_id_fkey FOREIGN KEY (devis_id) REFERENCES public.mg_achat_devis(id) ON DELETE CASCADE;


--
-- Name: mg_achat_evenements mg_achat_evenements_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_evenements
    ADD CONSTRAINT mg_achat_evenements_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: mg_achat_facture_lignes mg_achat_facture_lignes_facture_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_facture_lignes
    ADD CONSTRAINT mg_achat_facture_lignes_facture_id_fkey FOREIGN KEY (facture_id) REFERENCES public.mg_achat_factures(id) ON DELETE CASCADE;


--
-- Name: mg_achat_factures mg_achat_factures_bl_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_factures
    ADD CONSTRAINT mg_achat_factures_bl_id_fkey FOREIGN KEY (bl_id) REFERENCES public.mg_achat_bl(id);


--
-- Name: mg_achat_factures mg_achat_factures_bon_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_factures
    ADD CONSTRAINT mg_achat_factures_bon_id_fkey FOREIGN KEY (bon_id) REFERENCES public.mg_bons_commande(id);


--
-- Name: mg_achat_factures mg_achat_factures_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_factures
    ADD CONSTRAINT mg_achat_factures_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_achat_factures mg_achat_factures_reception_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_factures
    ADD CONSTRAINT mg_achat_factures_reception_id_fkey FOREIGN KEY (reception_id) REFERENCES public.mg_achat_receptions(id);


--
-- Name: mg_achat_paiements mg_achat_paiements_facture_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_paiements
    ADD CONSTRAINT mg_achat_paiements_facture_id_fkey FOREIGN KEY (facture_id) REFERENCES public.mg_achat_factures(id);


--
-- Name: mg_achat_paiements mg_achat_paiements_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_paiements
    ADD CONSTRAINT mg_achat_paiements_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_achat_reception_lignes mg_achat_reception_lignes_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_reception_lignes
    ADD CONSTRAINT mg_achat_reception_lignes_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_achat_reception_lignes mg_achat_reception_lignes_bc_ligne_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_reception_lignes
    ADD CONSTRAINT mg_achat_reception_lignes_bc_ligne_id_fkey FOREIGN KEY (bc_ligne_id) REFERENCES public.mg_bc_lignes(id);


--
-- Name: mg_achat_reception_lignes mg_achat_reception_lignes_reception_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_reception_lignes
    ADD CONSTRAINT mg_achat_reception_lignes_reception_id_fkey FOREIGN KEY (reception_id) REFERENCES public.mg_achat_receptions(id) ON DELETE CASCADE;


--
-- Name: mg_achat_receptions mg_achat_receptions_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_receptions
    ADD CONSTRAINT mg_achat_receptions_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_achat_receptions mg_achat_receptions_bl_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_receptions
    ADD CONSTRAINT mg_achat_receptions_bl_id_fkey FOREIGN KEY (bl_id) REFERENCES public.mg_achat_bl(id);


--
-- Name: mg_achat_receptions mg_achat_receptions_bon_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_receptions
    ADD CONSTRAINT mg_achat_receptions_bon_id_fkey FOREIGN KEY (bon_id) REFERENCES public.mg_bons_commande(id);


--
-- Name: mg_achat_receptions mg_achat_receptions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_achat_receptions
    ADD CONSTRAINT mg_achat_receptions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: mg_articles mg_articles_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_articles
    ADD CONSTRAINT mg_articles_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_articles mg_articles_famille_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_articles
    ADD CONSTRAINT mg_articles_famille_id_fkey FOREIGN KEY (famille_id) REFERENCES public.mg_article_familles(id);


--
-- Name: mg_bc_lignes mg_bc_lignes_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bc_lignes
    ADD CONSTRAINT mg_bc_lignes_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_bc_lignes mg_bc_lignes_bc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bc_lignes
    ADD CONSTRAINT mg_bc_lignes_bc_id_fkey FOREIGN KEY (bc_id) REFERENCES public.mg_bons_commande(id) ON DELETE CASCADE;


--
-- Name: mg_bons_commande mg_bons_commande_acheteur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT mg_bons_commande_acheteur_id_fkey FOREIGN KEY (acheteur_id) REFERENCES public.users(id);


--
-- Name: mg_bons_commande mg_bons_commande_agence_facturation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT mg_bons_commande_agence_facturation_id_fkey FOREIGN KEY (agence_facturation_id) REFERENCES public.agences(id);


--
-- Name: mg_bons_commande mg_bons_commande_agence_livraison_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT mg_bons_commande_agence_livraison_id_fkey FOREIGN KEY (agence_livraison_id) REFERENCES public.agences(id);


--
-- Name: mg_bons_commande mg_bons_commande_contrat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT mg_bons_commande_contrat_id_fkey FOREIGN KEY (contrat_id) REFERENCES public.mg_contrats(id);


--
-- Name: mg_bons_commande mg_bons_commande_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_bons_commande
    ADD CONSTRAINT mg_bons_commande_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_contrat_echeances mg_contrat_echeances_contrat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_echeances
    ADD CONSTRAINT mg_contrat_echeances_contrat_id_fkey FOREIGN KEY (contrat_id) REFERENCES public.mg_contrats(id) ON DELETE CASCADE;


--
-- Name: mg_contrat_historique mg_contrat_historique_contrat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_historique
    ADD CONSTRAINT mg_contrat_historique_contrat_id_fkey FOREIGN KEY (contrat_id) REFERENCES public.mg_contrats(id) ON DELETE CASCADE;


--
-- Name: mg_contrat_historique mg_contrat_historique_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_historique
    ADD CONSTRAINT mg_contrat_historique_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: mg_contrat_paiements mg_contrat_paiements_contrat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_paiements
    ADD CONSTRAINT mg_contrat_paiements_contrat_id_fkey FOREIGN KEY (contrat_id) REFERENCES public.mg_contrats(id) ON DELETE CASCADE;


--
-- Name: mg_contrat_paiements mg_contrat_paiements_echeance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrat_paiements
    ADD CONSTRAINT mg_contrat_paiements_echeance_id_fkey FOREIGN KEY (echeance_id) REFERENCES public.mg_contrat_echeances(id) ON DELETE SET NULL;


--
-- Name: mg_contrats mg_contrats_fournisseur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_contrats
    ADD CONSTRAINT mg_contrats_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_demande_fourniture_lignes mg_demande_fourniture_lignes_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_demande_fourniture_lignes
    ADD CONSTRAINT mg_demande_fourniture_lignes_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_demande_fourniture_lignes mg_demande_fourniture_lignes_demande_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_demande_fourniture_lignes
    ADD CONSTRAINT mg_demande_fourniture_lignes_demande_id_fkey FOREIGN KEY (demande_id) REFERENCES public.mg_demandes_fourniture(id) ON DELETE CASCADE;


--
-- Name: mg_demandes_fourniture mg_demandes_fourniture_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_demandes_fourniture
    ADD CONSTRAINT mg_demandes_fourniture_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_demandes_fourniture mg_demandes_fourniture_demandeur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_demandes_fourniture
    ADD CONSTRAINT mg_demandes_fourniture_demandeur_id_fkey FOREIGN KEY (demandeur_id) REFERENCES public.users(id);


--
-- Name: mg_employee_request_items mg_employee_request_items_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_request_items
    ADD CONSTRAINT mg_employee_request_items_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_employee_request_items mg_employee_request_items_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_request_items
    ADD CONSTRAINT mg_employee_request_items_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.mg_employee_requests(id) ON DELETE CASCADE;


--
-- Name: mg_employee_requests mg_employee_requests_achat_demande_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_achat_demande_id_fkey FOREIGN KEY (achat_demande_id) REFERENCES public.mg_achat_demandes(id);


--
-- Name: mg_employee_requests mg_employee_requests_agency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_agency_id_fkey FOREIGN KEY (agency_id) REFERENCES public.agences(id);


--
-- Name: mg_employee_requests mg_employee_requests_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.mg_procurement_batches(id);


--
-- Name: mg_employee_requests mg_employee_requests_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.mg_request_categories(id);


--
-- Name: mg_employee_requests mg_employee_requests_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departements(id);


--
-- Name: mg_employee_requests mg_employee_requests_rejected_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_rejected_by_fkey FOREIGN KEY (rejected_by) REFERENCES public.users(id);


--
-- Name: mg_employee_requests mg_employee_requests_requester_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_requester_id_fkey FOREIGN KEY (requester_id) REFERENCES public.users(id);


--
-- Name: mg_employee_requests mg_employee_requests_validated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_employee_requests
    ADD CONSTRAINT mg_employee_requests_validated_by_fkey FOREIGN KEY (validated_by) REFERENCES public.users(id);


--
-- Name: mg_inventaire_lignes mg_inventaire_lignes_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaire_lignes
    ADD CONSTRAINT mg_inventaire_lignes_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_inventaire_lignes mg_inventaire_lignes_inventaire_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaire_lignes
    ADD CONSTRAINT mg_inventaire_lignes_inventaire_id_fkey FOREIGN KEY (inventaire_id) REFERENCES public.mg_inventaires(id) ON DELETE CASCADE;


--
-- Name: mg_inventaires mg_inventaires_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaires
    ADD CONSTRAINT mg_inventaires_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_inventaires mg_inventaires_ajustements_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaires
    ADD CONSTRAINT mg_inventaires_ajustements_by_fkey FOREIGN KEY (ajustements_by) REFERENCES public.users(id);


--
-- Name: mg_inventaires mg_inventaires_cloture_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaires
    ADD CONSTRAINT mg_inventaires_cloture_by_fkey FOREIGN KEY (cloture_by) REFERENCES public.users(id);


--
-- Name: mg_inventaires mg_inventaires_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaires
    ADD CONSTRAINT mg_inventaires_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: mg_inventaires mg_inventaires_periode_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaires
    ADD CONSTRAINT mg_inventaires_periode_id_fkey FOREIGN KEY (periode_id) REFERENCES public.mg_stock_periodes(id);


--
-- Name: mg_inventaires mg_inventaires_valide_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_inventaires
    ADD CONSTRAINT mg_inventaires_valide_by_fkey FOREIGN KEY (valide_by) REFERENCES public.users(id);


--
-- Name: mg_note_frais_historique mg_note_frais_historique_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_historique
    ADD CONSTRAINT mg_note_frais_historique_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.mg_notes_frais(id) ON DELETE CASCADE;


--
-- Name: mg_note_frais_historique mg_note_frais_historique_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_historique
    ADD CONSTRAINT mg_note_frais_historique_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: mg_note_frais_lignes mg_note_frais_lignes_categorie_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_lignes
    ADD CONSTRAINT mg_note_frais_lignes_categorie_id_fkey FOREIGN KEY (categorie_id) REFERENCES public.mg_note_frais_categories(id);


--
-- Name: mg_note_frais_lignes mg_note_frais_lignes_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_note_frais_lignes
    ADD CONSTRAINT mg_note_frais_lignes_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.mg_notes_frais(id) ON DELETE CASCADE;


--
-- Name: mg_notes_frais mg_notes_frais_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_notes_frais
    ADD CONSTRAINT mg_notes_frais_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_notes_frais mg_notes_frais_demandeur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_notes_frais
    ADD CONSTRAINT mg_notes_frais_demandeur_id_fkey FOREIGN KEY (demandeur_id) REFERENCES public.users(id);


--
-- Name: mg_procurement_batch_items mg_procurement_batch_items_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batch_items
    ADD CONSTRAINT mg_procurement_batch_items_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_procurement_batch_items mg_procurement_batch_items_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batch_items
    ADD CONSTRAINT mg_procurement_batch_items_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.mg_procurement_batches(id) ON DELETE CASCADE;


--
-- Name: mg_procurement_batch_items mg_procurement_batch_items_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batch_items
    ADD CONSTRAINT mg_procurement_batch_items_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.mg_employee_requests(id);


--
-- Name: mg_procurement_batch_items mg_procurement_batch_items_request_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batch_items
    ADD CONSTRAINT mg_procurement_batch_items_request_item_id_fkey FOREIGN KEY (request_item_id) REFERENCES public.mg_employee_request_items(id);


--
-- Name: mg_procurement_batch_items mg_procurement_batch_items_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batch_items
    ADD CONSTRAINT mg_procurement_batch_items_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.fournisseurs(id);


--
-- Name: mg_procurement_batches mg_procurement_batches_achat_demande_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batches
    ADD CONSTRAINT mg_procurement_batches_achat_demande_id_fkey FOREIGN KEY (achat_demande_id) REFERENCES public.mg_achat_demandes(id);


--
-- Name: mg_procurement_batches mg_procurement_batches_agency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batches
    ADD CONSTRAINT mg_procurement_batches_agency_id_fkey FOREIGN KEY (agency_id) REFERENCES public.agences(id);


--
-- Name: mg_procurement_batches mg_procurement_batches_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batches
    ADD CONSTRAINT mg_procurement_batches_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.mg_request_categories(id);


--
-- Name: mg_procurement_batches mg_procurement_batches_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batches
    ADD CONSTRAINT mg_procurement_batches_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: mg_procurement_batches mg_procurement_batches_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batches
    ADD CONSTRAINT mg_procurement_batches_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departements(id);


--
-- Name: mg_procurement_batches mg_procurement_batches_validated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_procurement_batches
    ADD CONSTRAINT mg_procurement_batches_validated_by_fkey FOREIGN KEY (validated_by) REFERENCES public.users(id);


--
-- Name: mg_request_approvals mg_request_approvals_approver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_request_approvals
    ADD CONSTRAINT mg_request_approvals_approver_id_fkey FOREIGN KEY (approver_id) REFERENCES public.users(id);


--
-- Name: mg_request_approvals mg_request_approvals_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_request_approvals
    ADD CONSTRAINT mg_request_approvals_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.mg_employee_requests(id) ON DELETE CASCADE;


--
-- Name: mg_request_comments mg_request_comments_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_request_comments
    ADD CONSTRAINT mg_request_comments_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id);


--
-- Name: mg_request_comments mg_request_comments_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_request_comments
    ADD CONSTRAINT mg_request_comments_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.mg_employee_requests(id) ON DELETE CASCADE;


--
-- Name: mg_stock_mouvements mg_stock_mouvements_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_mouvements
    ADD CONSTRAINT mg_stock_mouvements_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_stock_mouvements mg_stock_mouvements_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_mouvements
    ADD CONSTRAINT mg_stock_mouvements_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_stock_mouvements mg_stock_mouvements_initiateur_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_mouvements
    ADD CONSTRAINT mg_stock_mouvements_initiateur_id_fkey FOREIGN KEY (initiateur_id) REFERENCES public.users(id);


--
-- Name: mg_stock_mouvements mg_stock_mouvements_periode_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_mouvements
    ADD CONSTRAINT mg_stock_mouvements_periode_id_fkey FOREIGN KEY (periode_id) REFERENCES public.mg_stock_periodes(id);


--
-- Name: mg_stock_periodes mg_stock_periodes_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_periodes
    ADD CONSTRAINT mg_stock_periodes_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- Name: mg_stock_periodes mg_stock_periodes_cloture_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_periodes
    ADD CONSTRAINT mg_stock_periodes_cloture_by_fkey FOREIGN KEY (cloture_by) REFERENCES public.users(id);


--
-- Name: mg_stock_periodes mg_stock_periodes_opened_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_periodes
    ADD CONSTRAINT mg_stock_periodes_opened_by_fkey FOREIGN KEY (opened_by) REFERENCES public.users(id);


--
-- Name: mg_stock_periodes mg_stock_periodes_periode_precedente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_periodes
    ADD CONSTRAINT mg_stock_periodes_periode_precedente_id_fkey FOREIGN KEY (periode_precedente_id) REFERENCES public.mg_stock_periodes(id);


--
-- Name: mg_stock_periodes mg_stock_periodes_reopen_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_periodes
    ADD CONSTRAINT mg_stock_periodes_reopen_by_fkey FOREIGN KEY (reopen_by) REFERENCES public.users(id);


--
-- Name: mg_stock_soldes mg_stock_soldes_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_soldes
    ADD CONSTRAINT mg_stock_soldes_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.mg_articles(id);


--
-- Name: mg_stock_soldes mg_stock_soldes_periode_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mg_stock_soldes
    ADD CONSTRAINT mg_stock_soldes_periode_id_fkey FOREIGN KEY (periode_id) REFERENCES public.mg_stock_periodes(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: parametrage_ecritures parametrage_ecritures_categorie_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parametrage_ecritures
    ADD CONSTRAINT parametrage_ecritures_categorie_id_fkey FOREIGN KEY (categorie_id) REFERENCES public.categories_immobilisation(id) ON DELETE CASCADE;


--
-- Name: password_history password_history_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_history
    ADD CONSTRAINT password_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: periodes_amortissement_categories periodes_amortissement_categories_categorie_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement_categories
    ADD CONSTRAINT periodes_amortissement_categories_categorie_id_fkey FOREIGN KEY (categorie_id) REFERENCES public.categories_immobilisation(id) ON DELETE CASCADE;


--
-- Name: periodes_amortissement_categories periodes_amortissement_categories_periode_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement_categories
    ADD CONSTRAINT periodes_amortissement_categories_periode_id_fkey FOREIGN KEY (periode_id) REFERENCES public.periodes_amortissement(id) ON DELETE CASCADE;


--
-- Name: periodes_amortissement_categories periodes_amortissement_categories_valide_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement_categories
    ADD CONSTRAINT periodes_amortissement_categories_valide_by_id_fkey FOREIGN KEY (valide_by_id) REFERENCES public.users(id);


--
-- Name: periodes_amortissement periodes_amortissement_exercice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement
    ADD CONSTRAINT periodes_amortissement_exercice_id_fkey FOREIGN KEY (exercice_id) REFERENCES public.exercices_comptables(id) ON DELETE CASCADE;


--
-- Name: periodes_amortissement periodes_amortissement_valide_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.periodes_amortissement
    ADD CONSTRAINT periodes_amortissement_valide_by_id_fkey FOREIGN KEY (valide_by_id) REFERENCES public.users(id);


--
-- Name: pieces_jointes pieces_jointes_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pieces_jointes
    ADD CONSTRAINT pieces_jointes_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id) ON DELETE CASCADE;


--
-- Name: plateforme_modules plateforme_modules_espace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plateforme_modules
    ADD CONSTRAINT plateforme_modules_espace_id_fkey FOREIGN KEY (espace_id) REFERENCES public.plateforme_espaces(id) ON DELETE CASCADE;


--
-- Name: platform_backups platform_backups_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_backups
    ADD CONSTRAINT platform_backups_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: platform_module_versions platform_module_versions_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_module_versions
    ADD CONSTRAINT platform_module_versions_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: platform_module_versions platform_module_versions_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_module_versions
    ADD CONSTRAINT platform_module_versions_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.plateforme_modules(id) ON DELETE CASCADE;


--
-- Name: platform_restores platform_restores_backup_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_restores
    ADD CONSTRAINT platform_restores_backup_id_fkey FOREIGN KEY (backup_id) REFERENCES public.platform_backups(id) ON DELETE RESTRICT;


--
-- Name: platform_restores platform_restores_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_restores
    ADD CONSTRAINT platform_restores_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: platform_restores platform_restores_safety_backup_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_restores
    ADD CONSTRAINT platform_restores_safety_backup_id_fkey FOREIGN KEY (safety_backup_id) REFERENCES public.platform_backups(id) ON DELETE SET NULL;


--
-- Name: rebuts rebuts_ecriture_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rebuts
    ADD CONSTRAINT rebuts_ecriture_id_fkey FOREIGN KEY (ecriture_id) REFERENCES public.ecritures_comptables(id);


--
-- Name: rebuts rebuts_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rebuts
    ADD CONSTRAINT rebuts_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id);


--
-- Name: reevaluations reevaluations_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reevaluations
    ADD CONSTRAINT reevaluations_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id);


--
-- Name: role_permissions role_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: security_incidents security_incidents_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents
    ADD CONSTRAINT security_incidents_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: soldes_compte_orion soldes_compte_orion_updated_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soldes_compte_orion
    ADD CONSTRAINT soldes_compte_orion_updated_by_id_fkey FOREIGN KEY (updated_by_id) REFERENCES public.users(id);


--
-- Name: soldes_ouverture_immobilisations soldes_ouverture_immobilisations_exercice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soldes_ouverture_immobilisations
    ADD CONSTRAINT soldes_ouverture_immobilisations_exercice_id_fkey FOREIGN KEY (exercice_id) REFERENCES public.exercices_comptables(id) ON DELETE CASCADE;


--
-- Name: soldes_ouverture_immobilisations soldes_ouverture_immobilisations_immobilisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soldes_ouverture_immobilisations
    ADD CONSTRAINT soldes_ouverture_immobilisations_immobilisation_id_fkey FOREIGN KEY (immobilisation_id) REFERENCES public.immobilisations(id) ON DELETE CASCADE;


--
-- Name: user_espace_acces user_espace_acces_espace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_espace_acces
    ADD CONSTRAINT user_espace_acces_espace_id_fkey FOREIGN KEY (espace_id) REFERENCES public.plateforme_espaces(id) ON DELETE CASCADE;


--
-- Name: user_espace_acces user_espace_acces_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_espace_acces
    ADD CONSTRAINT user_espace_acces_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_module_acces user_module_acces_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_module_acces
    ADD CONSTRAINT user_module_acces_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.plateforme_modules(id) ON DELETE CASCADE;


--
-- Name: user_module_acces user_module_acces_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_module_acces
    ADD CONSTRAINT user_module_acces_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_roles user_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: user_roles user_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: users users_agence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES public.agences(id);


--
-- PostgreSQL database dump complete
--

\unrestrict cyg22m2Pw1PR9VH9kgeivZKDtXfRlrVXwGsI64D7RAiIhdbYWPECHZWLMJcsCzj

