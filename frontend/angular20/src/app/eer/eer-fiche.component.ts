import { ChangeDetectionStrategy, Component, DestroyRef, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { Observable } from 'rxjs';
import { AuthService } from '../core/services/auth.service';
import { ApiErrorInfo, describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { UiConfirmData, UiReasonData } from '../shared/ui-dialog/ui-dialog.types';
import { EerAnalyste, EerService } from './eer.service';
import {
  ACTIONS_WORKFLOW,
  CLASSEMENTS,
  ELEMENT_STATUTS,
  ETAPES,
  ETATS_COMPTE,
  EerAnomalie,
  EerConformite,
  EerAudit,
  EerChecklist,
  EerChecklistItem,
  EerComplement,
  EerConstat,
  EerControle,
  EerDecision,
  EerDocument,
  EerDossier,
  EerFicheChamp,
  EerHistorique,
  EerPerimetre,
  EerVersion,
  EerVersionLigne,
  EerVisa,
  ROLES_PARTIE,
  STATUTS,
  TYPES_CLIENT,
  dateFr,
  eerTone,
  libelle,
  valeurAffichee,
} from './eer.models';

type Onglet =
  | 'resume' | 'client' | 'formulaires' | 'documents' | 'checklist' | 'controles'
  | 'anomalies' | 'complements' | 'avis' | 'versions' | 'historique' | 'audit';

type Modal = null | 'assign' | 'complement' | 'avis-defavorable' | 'anomalie' | 'version';

interface ActionBouton {
  cle: string;
  label: string;
  icon: string;
  primaire?: boolean;
  danger?: boolean;
  run: () => void;
}

const ONGLETS: Array<{ code: Onglet; label: string; capacite?: string }> = [
  { code: 'resume', label: 'Résumé' },
  { code: 'client', label: 'Client' },
  { code: 'formulaires', label: 'Formulaires' },
  { code: 'documents', label: 'Documents', capacite: 'documents' },
  { code: 'checklist', label: 'Checklist' },
  { code: 'controles', label: 'Contrôles' },
  { code: 'anomalies', label: 'Anomalies' },
  { code: 'complements', label: 'Compléments' },
  { code: 'avis', label: 'Avis' },
  { code: 'versions', label: 'Versions' },
  { code: 'historique', label: 'Historique' },
  { code: 'audit', label: 'Audit', capacite: 'audit' },
];

const TITRES_FICHES: Record<string, string> = {
  FICHE_PP: 'Fiche client personne physique',
  FICHE_PM_PRIVEE: 'Fiche client personne morale privée',
  FICHE_PM_PUBLIQUE: 'Fiche client personne morale publique',
  FICHE_ASSOCIATION: 'Fiche client personne morale associations',
  FICHE_MANDATAIRE: 'Fiche client mandataire',
  SPECIMEN_SIGNATURE: 'Spécimen de signature',
};

const CHAMPS_BOOLEENS = new Set(['ppe', 'fatca_indice', 'impact_rse']);
const RISQUES: Choix[] = [
  { code: 'FAIBLE', libelle: 'Faible' },
  { code: 'MOYEN', libelle: 'Moyen' },
  { code: 'ELEVE', libelle: 'Élevé' },
];
/** Champs à liste fermée : valeurs du référentiel EER (le backend refuse tout autre code). */
const DOMAINE_PAR_CHEMIN: Record<string, string> = {
  'dossier.type_signature': 'TYPE_SIGNATURE',
  'role.forme_mandat': 'FORME_MANDAT',
  'client.piece.type': 'TYPE_PIECE',
  'partie.piece.type': 'TYPE_PIECE',
};
const DOMAINES_CHOIX = ['TYPE_SIGNATURE', 'FORME_MANDAT', 'TYPE_PIECE', 'TRANCHE_PP', 'TRANCHE_PM'];

interface Choix {
  code: string;
  libelle: string;
}
const CHAMPS_NUMERIQUES = new Set(['salaire_net', 'nombre_signataires', 'effectif']);
const ETATS_CHAMP: Record<string, string> = {
  CONNU: 'Connu',
  MANQUANT: 'Manquant',
  A_CONFIRMER: 'À confirmer',
  CONFIRME: 'Confirmé',
  NON_APPLICABLE: 'Non applicable',
};
const PRESENCES: Record<string, string> = { PRESENT: 'Présent', ABSENT: 'Absent', SANS_OBJET: 'Sans objet' };

/** Parcours affiché en tête de fiche ; l'étape « Avis KYC » n'apparaît que si l'avis est requis. */
const PARCOURS: Array<{ code: string; label: string; statuts: string[] }> = [
  { code: 'saisie', label: 'Saisie', statuts: ['BROUILLON'] },
  { code: 'affectation', label: 'Affectation', statuts: ['SOUMIS', 'A_AFFECTER'] },
  { code: 'controle', label: 'Contrôle analyste', statuts: ['AFFECTE', 'EN_CONTROLE', 'RESOUMIS'] },
  { code: 'decision', label: 'Décision', statuts: ['CONFORME', 'NON_CONFORME', 'A_COMPLETER'] },
  { code: 'avis', label: 'Avis KYC', statuts: ['AVIS_CONFORMITE'] },
  { code: 'validation', label: 'Validation', statuts: ['VALIDE'] },
  { code: 'cloture', label: 'Clôture', statuts: ['CLOTURE', 'ARCHIVE'] },
];

const SOUS_ETAPES_CONTROLE: Array<{ code: string; label: string }> = [
  { code: 'CHECKLIST', label: 'Pointer la checklist' },
  { code: 'FICHES', label: 'Vérifier les fiches' },
  { code: 'CONTROLES', label: 'Contrôler et décider' },
];

interface Consigne {
  titre: string;
  texte: string;
  onglet?: Onglet;
  lienOnglet?: string;
}

interface GroupeFiche {
  cle: string;
  titre: string;
  total: number;
  renseignes: number;
  bloquants: number;
  sections: Array<{ nom: string; champs: EerFicheChamp[] }>;
}

interface GroupeChecklist {
  categorie: string;
  items: EerChecklistItem[];
}

@Component({
  selector: 'bea-eer-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, FormsModule, RouterLink, MatIconModule],
  templateUrl: './eer-fiche.component.html',
  styleUrls: ['./eer-fiche.component.css', './eer-fiche-sections.component.css'],
})
export class EerFicheComponent implements OnInit {
  private readonly eer = inject(EerService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);

  readonly canAccessCoreAdmin = this.auth.canAccessCoreAdmin;
  readonly busy = signal(false);
  readonly masquerNA = signal(true);
  private affectationDemandee = false;
  readonly id = signal('');
  readonly dossier = signal<EerDossier | null>(null);
  readonly perimetre = signal<EerPerimetre | null>(null);
  readonly onglet = signal<Onglet>('resume');
  readonly modal = signal<Modal>(null);

  readonly checklist = signal<EerChecklist | null>(null);
  readonly fiches = signal<Record<string, EerFicheChamp[]>>({});
  readonly controles = signal<EerControle[]>([]);
  readonly decisions = signal<EerDecision[]>([]);
  readonly constats = signal<EerConstat[] | null>(null);
  readonly anomalies = signal<EerAnomalie[]>([]);
  readonly conformite = signal<EerConformite | null>(null);
  readonly complements = signal<EerComplement[]>([]);
  readonly visas = signal<EerVisa[]>([]);
  readonly versions = signal<EerVersionLigne[]>([]);
  readonly versionDetail = signal<EerVersion | null>(null);
  readonly historique = signal<EerHistorique[]>([]);
  readonly documents = signal<EerDocument[]>([]);
  readonly audit = signal<EerAudit[]>([]);
  readonly analystes = signal<EerAnalyste[]>([]);
  readonly chargementAnalystes = signal(false);
  readonly referentiels = signal<Record<string, Choix[]>>({});

  /** Saisies en cours dans l'onglet Formulaires : clé `${fiche}|${chemin}`. */
  readonly saisies = signal<Record<string, string>>({});

  readonly assignForm = this.fb.nonNullable.group({ analyste_id: ['', Validators.required] });
  readonly complementForm = this.fb.nonNullable.group({
    consigne: ['', [Validators.required, Validators.maxLength(4000)]],
    echeance: '',
  });
  readonly anomalieForm = this.fb.nonNullable.group({
    type_code: ['', [Validators.required, Validators.maxLength(60)]],
    gravite: ['MAJEURE', Validators.required],
    description: ['', [Validators.required, Validators.maxLength(4000)]],
    item_id: '',
    observation: '',
    action_attendue: '',
  });
  readonly ciblesItems = signal<Set<string>>(new Set());
  readonly ciblesAnomalies = signal<Set<string>>(new Set());

  readonly hasUnsavedChanges = unsavedChanges(
    () => !this.busy() && (Object.keys(this.saisies()).length > 0 || (this.modal() !== null && this.modal() !== 'version' && this.formModalDirty())),
  );

  readonly onglets = computed(() => {
    const cap = this.perimetre()?.capacites ?? {};
    return ONGLETS.filter((o) => !o.capacite || cap[o.capacite]);
  });
  readonly cap = computed(() => this.perimetre()?.capacites ?? {});
  readonly statut = computed(() => this.dossier()?.statut ?? '');
  readonly revision = computed(() => this.dossier()?.revision ?? 0);
  readonly enControle = computed(() => this.statut() === 'EN_CONTROLE' && !!this.cap()['controle']);
  readonly modifiable = computed(() => {
    const s = this.statut();
    const c = this.cap();
    return (s === 'BROUILLON' && !!c['modification']) || (s === 'EN_CONTROLE' && !!c['controle']) || (s === 'A_COMPLETER' && !!c['complement']);
  });
  readonly client = computed(() => this.dossier()?.parties.find((p) => p.role === 'CLIENT') ?? null);
  readonly ficheCles = computed(() => Object.keys(this.fiches()));
  readonly nbSaisies = computed(() => Object.keys(this.saisies()).length);
  readonly anomaliesOuvertes = computed(() => this.anomalies().filter((a) => a.statut === 'OUVERTE'));
  readonly itemsCiblables = computed(() =>
    (this.checklist()?.items ?? []).filter((i) => ['NON_CONFORME', 'MANQUANT', 'A_VERIFIER'].includes(i.statut)),
  );
  readonly complementOuvert = computed(() => this.complements().find((c) => c.statut === 'OUVERT') ?? null);
  readonly itemsAttendus = computed(() => {
    const c = this.complementOuvert();
    return new Set((c?.elements ?? []).filter((e) => e.item_id && !e.fourni).map((e) => e.item_id as string));
  });

  readonly estAnalyste = computed(() => {
    const d = this.dossier();
    return !!d?.analyste_id && d.analyste_id === this.perimetre()?.user_id;
  });

  readonly parcours = computed(() => {
    const d = this.dossier();
    if (!d) return [];
    const etapes = PARCOURS.filter((e) => e.code !== 'avis' || d.avis_requis || d.statut === 'AVIS_CONFORMITE');
    const courante = etapes.findIndex((e) => e.statuts.includes(d.statut));
    return etapes.map((e, i) => ({
      ...e,
      etat: d.statut === 'ABANDONNE' ? 'abandon' : i < courante ? 'fait' : i === courante ? 'courant' : 'avenir',
    }));
  });

  readonly sousEtapes = computed(() => {
    const d = this.dossier();
    if (d?.statut !== 'EN_CONTROLE') return [];
    const rang = (e: string | null) => (e === 'CHECKLIST' ? 0 : e === 'CHECKLIST_VALIDEE' || e === 'FICHES' ? 1 : e === 'CONTROLES' ? 2 : 0);
    const courante = rang(d.etape);
    return SOUS_ETAPES_CONTROLE.map((s, i) => ({ ...s, etat: i < courante ? 'fait' : i === courante ? 'courant' : 'avenir' }));
  });

  /** Qui doit agir maintenant et où — guide l'utilisateur ; les droits restent contrôlés par le backend. */
  readonly consigne = computed<Consigne | null>(() => {
    const d = this.dossier();
    if (!d) return null;
    const cap = this.cap();
    const moi = this.estAnalyste();
    switch (d.statut) {
      case 'BROUILLON':
        return {
          titre: 'Saisie du dossier',
          texte: 'Complétez les formulaires (onglet « Formulaires ») puis cliquez « Soumettre au contrôle ». La checklist se calcule toute seule à partir des données saisies : rien n’est à cocher à ce stade, elle sera pointée par l’analyste après affectation.',
          onglet: 'formulaires', lienOnglet: 'Ouvrir les formulaires',
        };
      case 'SOUMIS':
      case 'A_AFFECTER':
        return {
          titre: 'En attente d’affectation',
          texte: cap['affectation']
            ? 'Cliquez « Affecter à un analyste ». Tout agent ayant accès au module EER peut être choisi, y compris vous-même.'
            : 'Un agent du module EER doit affecter ce dossier à un analyste.',
        };
      case 'AFFECTE':
        return {
          titre: 'Affecté — contrôle à démarrer',
          texte: moi ? 'Ce dossier vous est affecté : cliquez « Démarrer le contrôle » pour commencer le pointage de la checklist.' : 'L’analyste affecté doit démarrer le contrôle.',
        };
      case 'EN_CONTROLE':
      case 'RESOUMIS':
        if (!moi) return { titre: 'Contrôle en cours', texte: 'Seul l’analyste affecté pointe la checklist, vérifie les fiches et contrôle les éléments.' };
        if (d.statut === 'RESOUMIS') return { titre: 'Dossier resoumis', texte: 'Le complément a été fourni : cliquez « Démarrer le contrôle » pour reprendre là où vous vous étiez arrêté.' };
        if (d.etape === 'CHECKLIST') {
          return {
            titre: 'Étape 1 / 3 — Pointer la checklist',
            texte: 'Pour chaque élément, indiquez si la pièce ou l’information figure dans le dossier : « Présent », « Absent » ou « Sans objet » (justification obligatoire). Quand tout est pointé, cliquez « Valider la checklist ».',
            onglet: 'checklist', lienOnglet: 'Ouvrir la checklist',
          };
        }
        if (d.etape === 'CONTROLES') {
          return {
            titre: 'Étape 3 / 3 — Contrôler et décider',
            texte: 'Dans la checklist, marquez chaque élément « Conforme » ou « Non conforme ». Vous pouvez lancer les contrôles automatiques (onglet « Contrôles »). La décision « Déclarer conforme / non conforme » apparaît quand tous les éléments obligatoires sont contrôlés.',
            onglet: 'checklist', lienOnglet: 'Ouvrir la checklist',
          };
        }
        return {
          titre: 'Étape 2 / 3 — Vérifier les fiches',
          texte: 'Confirmez les données marquées « À confirmer », complétez les manquantes, enregistrez puis cliquez « Fiches complétées ».',
          onglet: 'formulaires', lienOnglet: 'Ouvrir les formulaires',
        };
      case 'NON_CONFORME':
        return { titre: 'Non conforme', texte: 'Demandez un complément en ciblant les éléments à régulariser ; le dossier reste le même et une nouvelle version sera créée à la resoumission.' };
      case 'A_COMPLETER':
        return {
          titre: 'Complément attendu',
          texte: 'Seuls les éléments demandés sont modifiables. Marquez chaque pièce « Reçu » dans la checklist, corrigez les formulaires, puis cliquez « Resoumettre ».',
          onglet: 'complements', lienOnglet: 'Voir la demande',
        };
      case 'CONFORME':
        return {
          titre: 'Conforme',
          texte: d.avis_requis
            ? 'L’avis du Service Conformité KYC est obligatoire : cliquez « Demander l’avis KYC ».'
            : 'Cliquez « Valider le dossier ».',
        };
      case 'AVIS_CONFORMITE':
        return {
          titre: 'Avis Conformité KYC',
          texte: 'Émettez un avis favorable (validation) ou défavorable (complément ciblé, motif obligatoire).',
        };
      case 'VALIDE':
        return { titre: 'Validé', texte: 'Le dossier peut être clôturé puis archivé.' };
      case 'ABANDONNE':
        return { titre: 'Dossier abandonné', texte: `Motif : ${d.motif_abandon || '—'}. Le dossier reste consultable, il n’est plus modifiable.` };
      default:
        return null;
    }
  });

  readonly fichesGroupees = computed<GroupeFiche[]>(() =>
    Object.entries(this.fiches()).map(([cle, champs]) => {
      const sections = new Map<string, EerFicheChamp[]>();
      for (const c of champs) {
        const nom = c.section || 'Informations';
        sections.set(nom, [...(sections.get(nom) ?? []), c]);
      }
      const applicables = champs.filter((c) => c.etat !== 'NON_APPLICABLE');
      return {
        cle,
        titre: this.titreFiche(cle),
        total: applicables.length,
        renseignes: applicables.filter((c) => c.etat !== 'MANQUANT').length,
        bloquants: champs.filter((c) => c.bloquant).length,
        sections: [...sections].map(([nom, liste]) => ({ nom, champs: liste })),
      };
    }),
  );

  readonly checklistGroupee = computed<GroupeChecklist[]>(() => {
    const groupes = new Map<string, EerChecklistItem[]>();
    for (const i of this.checklist()?.items ?? []) {
      if (this.masquerNA() && i.statut === 'NON_APPLICABLE') continue;
      groupes.set(i.categorie, [...(groupes.get(i.categorie) ?? []), i]);
    }
    return [...groupes].map(([categorie, items]) => ({ categorie, items }));
  });

  readonly progression = computed(() => {
    const items = (this.checklist()?.items ?? []).filter((i) => i.statut !== 'NON_APPLICABLE');
    const etape = this.dossier()?.etape;
    const faits = etape === 'CONTROLES'
      ? items.filter((i) => !!i.controle_le || i.derogation_acceptee).length
      : items.filter((i) => !!i.pointe_le).length;
    return {
      total: items.length,
      faits,
      na: (this.checklist()?.items.length ?? 0) - items.length,
      libelle: etape === 'CONTROLES' ? 'contrôlé(s)' : 'pointé(s)',
      pct: items.length ? Math.round((faits / items.length) * 100) : 0,
    };
  });

  /** Mode d'emploi de la checklist selon l'étape et l'utilisateur. */
  readonly modeChecklist = computed<{ ton: 'info' | 'action' | 'attente'; texte: string }>(() => {
    const d = this.dossier();
    const s = d?.statut ?? '';
    if (['BROUILLON', 'SOUMIS', 'A_AFFECTER', 'AFFECTE'].includes(s)) {
      return { ton: 'info', texte: 'Lecture seule : la checklist est générée automatiquement à partir des formulaires (type de client, profil, PPE, FATCA, risque…). Elle sera pointée par l’analyste affecté, une fois le contrôle démarré.' };
    }
    if (s === 'EN_CONTROLE' && !this.enControle()) {
      return { ton: 'attente', texte: 'Contrôle en cours : seul l’analyste affecté pointe et contrôle les éléments.' };
    }
    if (s === 'EN_CONTROLE' && d?.etape === 'CHECKLIST') {
      return { ton: 'action', texte: 'À vous : pour chaque élément, la pièce ou l’information est-elle dans le dossier ? Cliquez « Présent », « Absent » ou « Sans objet » (justification demandée). Puis « Valider la checklist ».' };
    }
    if (s === 'EN_CONTROLE' && d?.etape === 'CONTROLES') {
      return { ton: 'action', texte: 'À vous : jugez chaque élément « Conforme » ou « Non conforme » (observation demandée en cas de non-conformité).' };
    }
    if (s === 'EN_CONTROLE') {
      return { ton: 'attente', texte: 'Checklist validée : poursuivez par la vérification des fiches (onglet « Formulaires »).' };
    }
    if (s === 'A_COMPLETER') {
      return { ton: 'action', texte: 'Complément : marquez « Reçu » chaque élément demandé lorsqu’il est fourni.' };
    }
    return { ton: 'info', texte: 'Checklist figée pour ce statut (consultation).' };
  });

  readonly actions = computed<ActionBouton[]>(() => {
    const d = this.dossier();
    if (!d) return [];
    const out: ActionBouton[] = [];
    for (const cible of d.transitions_possibles) {
      if (cible === 'AFFECTE') {
        out.push({ cle: cible, label: 'Affecter à un analyste', icon: 'assignment_ind', primaire: true, run: () => this.ouvrirAffectation() });
      } else if (cible === 'CONFORME') {
        out.push({ cle: cible, label: 'Déclarer conforme', icon: 'verified', primaire: true, run: () => this.decider('CONFORME') });
      } else if (cible === 'NON_CONFORME') {
        out.push({ cle: cible, label: 'Déclarer non conforme', icon: 'report', danger: true, run: () => this.decider('NON_CONFORME') });
      } else if (cible === 'A_COMPLETER' && d.statut === 'NON_CONFORME') {
        out.push({ cle: cible, label: 'Demander un complément', icon: 'playlist_add', primaire: true, run: () => this.ouvrirComplement('complement') });
      } else if (cible === 'A_COMPLETER' && d.statut === 'AVIS_CONFORMITE') {
        out.push({ cle: cible, label: 'Avis défavorable', icon: 'thumb_down', danger: true, run: () => this.ouvrirComplement('avis-defavorable') });
      } else if (cible === 'VALIDE' && d.statut === 'AVIS_CONFORMITE') {
        out.push({ cle: cible, label: 'Avis favorable', icon: 'thumb_up', primaire: true, run: () => this.avisFavorable() });
      } else if (cible === 'VALIDE') {
        out.push({ cle: cible, label: 'Valider le dossier', icon: 'check_circle', primaire: true, run: () => this.transition('validate', 'Valider le dossier', 'validation') });
      } else if (ACTIONS_WORKFLOW[cible]) {
        const a = ACTIONS_WORKFLOW[cible];
        out.push({
          cle: cible,
          label: a.label,
          icon: a.icon,
          danger: cible === 'ABANDONNE',
          primaire: cible === 'SOUMIS' || cible === 'EN_CONTROLE' || cible === 'RESOUMIS',
          run: () => (a.motif === 'requis' ? this.transitionMotivee(a.route, a.label) : this.transition(a.route, a.label)),
        });
      }
    }
    if (d.statut === 'A_COMPLETER' && this.cap()['demande_complement']) {
      out.push({ cle: 'RELANCE', label: 'Relancer', icon: 'notifications_active', run: () => this.relancer() });
    }
    if (this.cap()['administration']) {
      out.push({ cle: 'SUPPRIMER', label: 'Supprimer', icon: 'delete', danger: true, run: () => this.supprimer() });
    }
    return out;
  });

  ngOnInit(): void {
    this.eer.perimetre().subscribe({ next: (p) => this.perimetre.set(p), error: (e) => this.fail(e) });
    for (const domaine of DOMAINES_CHOIX) {
      this.eer.referentiels(domaine).subscribe({
        next: (r) => this.referentiels.update((m) => ({ ...m, [domaine]: r.map((x) => ({ code: x.code, libelle: x.libelle })) })),
        error: () => undefined,
      });
    }
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((p) => {
      this.id.set(p.get('id') ?? '');
      this.saisies.set({});
      this.recharger();
    });
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((q) => {
      const o = q.get('onglet') as Onglet | null;
      if (o && ONGLETS.some((x) => x.code === o)) this.choisir(o);
      if (q.get('action') === 'affecter') this.affectationDemandee = true;
    });
  }

  // --- Chargement ---------------------------------------------------------------------------

  recharger(): void {
    if (!this.id()) return;
    this.eer.lire(this.id()).subscribe({
      next: (d) => {
        this.dossier.set(d);
        if (this.affectationDemandee) {
          this.affectationDemandee = false;
          if (d.transitions_possibles.includes('AFFECTE')) this.ouvrirAffectation();
        }
      },
      error: (e) => this.fail(e),
    });
    this.eer.conformite(this.id()).subscribe({ next: (c) => this.conformite.set(c), error: (e) => this.fail(e) });
    this.chargerOnglet(this.onglet());
  }

  classement(code: string | null | undefined): string {
    return libelle(CLASSEMENTS, code);
  }

  etatCompte(code: string | null | undefined): string {
    return libelle(ETATS_COMPTE, code);
  }

  choisir(o: Onglet): void {
    this.onglet.set(o);
    this.chargerOnglet(o);
  }

  private chargerOnglet(o: Onglet): void {
    const id = this.id();
    if (!id) return;
    const err = (e: unknown) => this.fail(e);
    switch (o) {
      case 'resume':
        this.eer.checklist(id).subscribe({ next: (c) => this.checklist.set(c), error: err });
        this.eer.anomalies(id).subscribe({ next: (a) => this.anomalies.set(a), error: err });
        break;
      case 'formulaires':
        this.eer.fiches(id).subscribe({ next: (f) => this.fiches.set(f), error: err });
        break;
      case 'documents':
        this.eer.documents(id).subscribe({ next: (d) => this.documents.set(d), error: err });
        break;
      case 'checklist':
        this.eer.checklist(id).subscribe({ next: (c) => this.checklist.set(c), error: err });
        this.eer.complements(id).subscribe({ next: (c) => this.complements.set(c), error: err });
        break;
      case 'controles':
        this.eer.controles(id).subscribe({
          next: (r) => {
            this.controles.set(r.controles);
            this.decisions.set(r.decisions);
          },
          error: err,
        });
        break;
      case 'anomalies':
        this.eer.anomalies(id).subscribe({ next: (a) => this.anomalies.set(a), error: err });
        this.eer.checklist(id).subscribe({ next: (c) => this.checklist.set(c), error: err });
        break;
      case 'complements':
        this.eer.complements(id).subscribe({ next: (c) => this.complements.set(c), error: err });
        break;
      case 'avis':
        this.eer.avis(id).subscribe({ next: (v) => this.visas.set(v), error: err });
        break;
      case 'versions':
        this.eer.versions(id).subscribe({ next: (v) => this.versions.set(v), error: err });
        break;
      case 'historique':
        this.eer.historique(id).subscribe({ next: (h) => this.historique.set(h), error: err });
        break;
      case 'audit':
        this.eer.audit(id).subscribe({ next: (a) => this.audit.set(a), error: err });
        break;
      default:
        break;
    }
  }

  // --- Mutations (révision optimiste ; 409 → rechargement) ----------------------------------

  private muter<T>(
    action: (revision: number) => Observable<T>,
    opts: { loading: string; succes: string; errorTitle: string; confirm?: UiConfirmData | { action: 'soumission' | 'validation' | 'cloture' | 'archivage' | 'modification'; message: string } },
    apres?: (r: T) => void,
  ): void {
    this.feedback
      .run(() => action(this.revision()), {
        confirm: opts.confirm,
        loading: opts.loading,
        busy: this.busy,
        retry: false,
        errorTitle: opts.errorTitle,
        onError: (info) => this.surErreur(info),
        success: (r: T) => ({ title: opts.succes, details: this.details(r) }),
      })
      .subscribe((r) => {
        apres?.(r);
        this.recharger();
      });
  }

  private muterMotif<T>(reason: UiReasonData, action: (revision: number, motif: string) => Observable<T>, succes: string, errorTitle: string): void {
    this.feedback
      .runWithReason((motif) => action(this.revision(), motif), {
        reason,
        loading: 'Enregistrement…',
        busy: this.busy,
        retry: false,
        errorTitle,
        onError: (info) => this.surErreur(info),
        success: (r: T) => ({ title: succes, details: this.details(r) }),
      })
      .subscribe(() => this.recharger());
  }

  private details(r: unknown): Array<{ label: string; value: string }> {
    const m = r as { statut?: string; version_courante?: number } | null;
    if (!m?.statut) return [];
    return [
      { label: 'Statut', value: libelle(STATUTS, m.statut) },
      { label: 'Version', value: `v${m.version_courante}` },
    ];
  }

  private surErreur(info: ApiErrorInfo): void {
    if (info.status === 409 && info.code === 'EER_CONFLIT_REVISION') {
      this.feedback.warning({
        title: 'Dossier modifié entre-temps',
        message: 'Un autre utilisateur a modifié ce dossier. La fiche a été rechargée : vérifiez puis recommencez.',
      });
      this.recharger();
    }
  }

  transition(route: string, label: string, preset: 'soumission' | 'validation' | 'cloture' | 'archivage' | 'modification' = 'modification'): void {
    const d = this.dossier();
    if (!d) return;
    const action = route === 'submit' ? 'soumission' : route === 'close' ? 'cloture' : route === 'archive' ? 'archivage' : preset;
    this.muter((rev) => this.eer.action(d.id, route, rev), {
      loading: `${label}…`,
      succes: label,
      errorTitle: 'Action refusée',
      confirm: { action, message: `${label} — dossier ${d.reference} ?` },
    });
  }

  transitionMotivee(route: string, label: string): void {
    const d = this.dossier();
    if (!d) return;
    this.muterMotif(
      { title: label, message: `${label} — dossier ${d.reference}.`, reasonLabel: 'Motif', required: true, maxLength: 4000, tone: 'danger', confirmLabel: label },
      (rev, motif) => this.eer.action(d.id, route, rev, { motif }),
      label,
      'Action refusée',
    );
  }

  supprimer(): void {
    const d = this.dossier();
    if (!d) return;
    this.feedback
      .runWithReason((motif) => this.eer.action(d.id, 'supprimer', this.revision(), { motif }), {
        reason: {
          title: 'Supprimer le dossier',
          message: `${d.reference}. Le dossier disparaît des listes et du tableau de bord ; son historique reste tracé (audit).`,
          reasonLabel: 'Motif de suppression',
          required: true,
          maxLength: 4000,
          tone: 'danger',
          confirmLabel: 'Supprimer',
        },
        loading: 'Suppression…',
        busy: this.busy,
        retry: false,
        errorTitle: 'Suppression refusée',
        onError: (info) => this.surErreur(info),
        success: () => ({ title: 'Dossier supprimé', details: [{ label: 'Référence', value: d.reference }] }),
      })
      .subscribe(() => this.router.navigateByUrl('/eer/dossiers'));
  }

  decider(resultat: 'CONFORME' | 'NON_CONFORME'): void {
    const d = this.dossier();
    if (!d) return;
    const label = resultat === 'CONFORME' ? 'Déclarer le dossier conforme' : 'Déclarer le dossier non conforme';
    this.muter((rev) => this.eer.action(d.id, 'decision', rev, { resultat }), {
      loading: 'Enregistrement de la décision…',
      succes: resultat === 'CONFORME' ? 'Dossier déclaré conforme' : 'Dossier déclaré non conforme',
      errorTitle: 'Décision refusée',
      confirm: {
        title: label,
        message: `${label} (${d.reference}) ?`,
        hint: 'La décision doit correspondre à la décision calculée par le moteur de conformité.',
        tone: resultat === 'CONFORME' ? 'success' : 'danger',
        confirmLabel: 'Confirmer',
      },
    });
  }

  avisFavorable(): void {
    const d = this.dossier();
    if (!d) return;
    this.muterMotif(
      {
        title: 'Avis Conformité KYC favorable',
        message: `Émettre un avis favorable sur ${d.reference} (version ${d.version_courante}) ? Le dossier sera validé.`,
        reasonLabel: 'Commentaire',
        required: false,
        maxLength: 4000,
        tone: 'success',
        confirmLabel: 'Émettre l’avis',
      },
      (rev, commentaire) => this.eer.action(d.id, 'avis', rev, { favorable: true, commentaire: commentaire || null }),
      'Avis favorable enregistré',
      'Avis refusé',
    );
  }

  relancer(): void {
    const d = this.dossier();
    if (!d) return;
    this.muterMotif(
      { title: 'Relancer le complément', message: `Enregistrer une relance pour ${d.reference}.`, reasonLabel: 'Commentaire', required: false, maxLength: 4000, confirmLabel: 'Relancer' },
      (rev, motif) => this.eer.action(d.id, 'relance', rev, { motif: motif || null }),
      'Relance enregistrée',
      'Relance refusée',
    );
  }

  // Affectation
  ouvrirAffectation(): void {
    const d = this.dossier();
    if (!d) return;
    this.assignForm.reset();
    this.analystes.set([]);
    this.chargementAnalystes.set(true);
    this.eer.analystes(d.id).subscribe({
      next: (a) => {
        this.analystes.set(a);
        this.chargementAnalystes.set(false);
      },
      error: (e) => {
        this.chargementAnalystes.set(false);
        this.fail(e);
      },
    });
    this.modal.set('assign');
  }

  affecter(): void {
    const d = this.dossier();
    if (!d || this.assignForm.invalid) return;
    const { analyste_id } = this.assignForm.getRawValue();
    this.muter((rev) => this.eer.action(d.id, 'assign', rev, { analyste_id }), {
      loading: 'Affectation…',
      succes: 'Dossier affecté',
      errorTitle: 'Affectation refusée',
    }, () => this.fermer(true));
  }

  // Complément / avis défavorable : seuls les éléments ciblés seront modifiables.
  ouvrirComplement(type: 'complement' | 'avis-defavorable'): void {
    const d = this.dossier();
    if (!d) return;
    this.complementForm.reset();
    this.ciblesItems.set(new Set());
    this.ciblesAnomalies.set(new Set(this.anomaliesOuvertes().map((a) => a.id)));
    this.eer.checklist(d.id).subscribe({ next: (c) => this.checklist.set(c), error: (e) => this.fail(e) });
    this.eer.anomalies(d.id).subscribe({
      next: (a) => {
        this.anomalies.set(a);
        this.ciblesAnomalies.set(new Set(a.filter((x) => x.statut === 'OUVERTE').map((x) => x.id)));
      },
      error: (e) => this.fail(e),
    });
    this.modal.set(type);
  }

  basculer(cible: 'items' | 'anomalies', id: string): void {
    const s = cible === 'items' ? this.ciblesItems : this.ciblesAnomalies;
    const next = new Set(s());
    if (next.has(id)) next.delete(id);
    else next.add(id);
    s.set(next);
  }

  envoyerComplement(): void {
    const d = this.dossier();
    if (!d || this.complementForm.invalid) return;
    const v = this.complementForm.getRawValue();
    const cibles = { item_ids: [...this.ciblesItems()], anomalie_ids: [...this.ciblesAnomalies()], champs: [] };
    if (this.modal() === 'avis-defavorable') {
      this.muter((rev) => this.eer.action(d.id, 'avis', rev, { favorable: false, commentaire: v.consigne, cibles }), {
        loading: 'Enregistrement de l’avis…',
        succes: 'Avis défavorable enregistré',
        errorTitle: 'Avis refusé',
      }, () => this.fermer(true));
    } else {
      this.muter((rev) => this.eer.action(d.id, 'complement', rev, { consigne: v.consigne, echeance: v.echeance || null, cibles }), {
        loading: 'Demande de complément…',
        succes: 'Complément demandé',
        errorTitle: 'Demande refusée',
      }, () => this.fermer(true));
    }
  }

  // --- Formulaires ---------------------------------------------------------------------------

  cleSaisie(fiche: string, chemin: string): string {
    return `${fiche}|${chemin}`;
  }

  valeurSaisie(fiche: string, c: EerFicheChamp): string {
    const k = this.cleSaisie(fiche, c.chemin);
    const s = this.saisies();
    if (k in s) return s[k];
    if (c.valeur === null || c.valeur === undefined) return '';
    if (typeof c.valeur === 'boolean') return c.valeur ? 'true' : 'false';
    return String(c.valeur);
  }

  saisir(fiche: string, c: EerFicheChamp, valeur: string): void {
    const k = this.cleSaisie(fiche, c.chemin);
    const next = { ...this.saisies() };
    const origine = c.valeur === null || c.valeur === undefined ? '' : typeof c.valeur === 'boolean' ? String(c.valeur) : String(c.valeur);
    if (valeur === origine) delete next[k];
    else next[k] = valeur;
    this.saisies.set(next);
  }

  choix(chemin: string): Choix[] {
    if (chemin.endsWith('.risque_lbcft')) return RISQUES;
    if (chemin === 'dossier.tranche_mouvement') {
      return this.referentiels()[this.dossier()?.type_client === 'PP' ? 'TRANCHE_PP' : 'TRANCHE_PM'] ?? [];
    }
    const domaine = DOMAINE_PAR_CHEMIN[chemin];
    return domaine ? (this.referentiels()[domaine] ?? []) : [];
  }

  /** Options de la liste + valeur actuelle si elle n'y figure pas (saisie antérieure), pour ne rien masquer. */
  options(fiche: string, c: EerFicheChamp): Choix[] {
    const liste = this.choix(c.chemin);
    const v = this.valeurSaisie(fiche, c);
    return v && !liste.some((o) => o.code === v) ? [...liste, { code: v, libelle: `${v} (valeur non reconnue)` }] : liste;
  }

  affichage(c: EerFicheChamp): string {
    if (c.etat === 'NON_APPLICABLE') return 'Non applicable';
    const o = typeof c.valeur === 'string' ? this.choix(c.chemin).find((x) => x.code === c.valeur) : undefined;
    return o ? o.libelle : this.val(c.valeur);
  }

  typeChamp(chemin: string): 'date' | 'bool' | 'number' | 'text' | 'choix' {
    if (this.choix(chemin).length) return 'choix';
    const feuille = chemin.split('.').pop() ?? '';
    if (CHAMPS_BOOLEENS.has(feuille)) return 'bool';
    if (feuille.startsWith('date')) return 'date';
    if (CHAMPS_NUMERIQUES.has(feuille)) return 'number';
    return 'text';
  }

  enregistrerFiches(): void {
    const d = this.dossier();
    if (!d || !this.nbSaisies()) return;
    const champs = Object.entries(this.saisies()).map(([k, brut]) => {
      const [fiche, chemin] = k.split('|');
      const dpId = fiche.includes(':') ? fiche.split(':')[1] : null;
      const t = this.typeChamp(chemin);
      const valeur = brut === '' ? null : t === 'bool' ? brut === 'true' : t === 'number' ? Number(brut) : brut;
      return { chemin, valeur, dossier_partie_id: dpId };
    });
    this.muter((rev) => this.eer.modifier(d.id, rev, champs), {
      loading: 'Enregistrement des fiches…',
      succes: 'Fiches enregistrées',
      errorTitle: 'Enregistrement refusé',
    }, () => this.saisies.set({}));
  }

  annulerSaisies(): void {
    this.saisies.set({});
  }

  confirmerChamp(fiche: string, c: EerFicheChamp): void {
    const d = this.dossier();
    if (!d) return;
    const dpId = fiche.includes(':') ? fiche.split(':')[1] : null;
    this.muter((rev) => this.eer.action(d.id, 'fiches/confirm', rev, { chemin: c.chemin, dossier_partie_id: dpId }), {
      loading: 'Confirmation…',
      succes: `« ${c.libelle} » confirmé`,
      errorTitle: 'Confirmation refusée',
    });
  }

  terminerFiches(): void {
    const d = this.dossier();
    if (!d) return;
    this.muter((rev) => this.eer.action(d.id, 'fiches/complete', rev), {
      loading: 'Clôture de l’étape fiches…',
      succes: 'Fiches complétées',
      errorTitle: 'Fiches incomplètes',
    });
  }

  titreFiche(cle: string): string {
    const [code, dp] = cle.split(':');
    const titre = TITRES_FICHES[code] ?? code;
    if (!dp) return titre;
    const partie = this.dossier()?.parties.find((p) => p.dossier_partie_id === dp);
    return partie ? `${titre} — ${partie.nom}` : titre;
  }

  // --- Checklist / contrôles -----------------------------------------------------------------

  regenererChecklist(): void {
    const d = this.dossier();
    if (!d) return;
    this.muter((rev) => this.eer.action(d.id, 'checklist/generate', rev), {
      loading: 'Recalcul de la checklist…',
      succes: 'Checklist recalculée',
      errorTitle: 'Recalcul refusé',
    });
  }

  validerChecklist(): void {
    const d = this.dossier();
    if (!d) return;
    this.muter((rev) => this.eer.action(d.id, 'checklist/validate', rev), {
      loading: 'Validation de la checklist…',
      succes: 'Checklist validée',
      errorTitle: 'Checklist incomplète',
    });
  }

  pointer(i: EerChecklistItem, presence: 'PRESENT' | 'ABSENT' | 'SANS_OBJET'): void {
    const d = this.dossier();
    if (!d) return;
    if (presence === 'SANS_OBJET') {
      this.muterMotif(
        { title: 'Élément sans objet', message: i.libelle, reasonLabel: 'Justification', required: true, maxLength: 1000, confirmLabel: 'Enregistrer' },
        (rev, motif) => this.eer.pointer(d.id, i.id, rev, presence, motif),
        'Élément pointé',
        'Pointage refusé',
      );
      return;
    }
    this.muter((rev) => this.eer.pointer(d.id, i.id, rev, presence), {
      loading: 'Pointage…',
      succes: `${i.libelle} : ${PRESENCES[presence]}`,
      errorTitle: 'Pointage refusé',
    });
  }

  controler(i: EerChecklistItem, conforme: boolean): void {
    const d = this.dossier();
    if (!d) return;
    if (!conforme) {
      this.muterMotif(
        { title: 'Élément non conforme', message: i.libelle, reasonLabel: 'Observation', required: true, maxLength: 1000, tone: 'danger', confirmLabel: 'Enregistrer' },
        (rev, motif) => this.eer.controler(d.id, i.id, rev, false, motif),
        'Contrôle enregistré',
        'Contrôle refusé',
      );
      return;
    }
    this.muter((rev) => this.eer.controler(d.id, i.id, rev, true), {
      loading: 'Contrôle…',
      succes: `${i.libelle} : conforme`,
      errorTitle: 'Contrôle refusé',
    });
  }

  marquerFourni(i: EerChecklistItem): void {
    const d = this.dossier();
    if (!d) return;
    this.muter((rev) => this.eer.action(d.id, 'complements/fourni', rev, { item_id: i.id }), {
      loading: 'Enregistrement…',
      succes: `${i.libelle} : reçu`,
      errorTitle: 'Réception refusée',
    });
  }

  lancerControlesAuto(): void {
    const d = this.dossier();
    if (!d) return;
    this.muter((rev) => this.eer.controlesAuto(d.id, rev), {
      loading: 'Contrôles automatiques…',
      succes: 'Contrôles automatiques exécutés',
      errorTitle: 'Contrôles impossibles',
    }, (r) => this.constats.set(r.constats));
  }

  statutLigne(i: EerChecklistItem): string {
    if (i.neutralise_auto) return 'Neutralisé (auto)';
    if (i.derogation_acceptee) return 'Dérogation acceptée';
    if (i.controle_le) return 'Contrôlé';
    if (i.pointe_le) return 'Pointé';
    return 'Non pointé';
  }

  // --- Anomalies -----------------------------------------------------------------------------

  ouvrirAnomaliesAuto(): void {
    const d = this.dossier();
    if (!d) return;
    this.muter((rev) => this.eer.action(d.id, 'anomalies/open', rev), {
      loading: 'Ouverture des anomalies…',
      succes: 'Anomalies ouvertes depuis les non-conformités',
      errorTitle: 'Ouverture refusée',
    });
  }

  nouvelleAnomalie(): void {
    this.anomalieForm.reset({ gravite: 'MAJEURE' });
    this.modal.set('anomalie');
  }

  creerAnomalie(): void {
    const d = this.dossier();
    if (!d || this.anomalieForm.invalid) return;
    const v = this.anomalieForm.getRawValue();
    this.muter((rev) => this.eer.action(d.id, 'anomalies', rev, {
      type_code: v.type_code.trim(),
      gravite: v.gravite,
      description: v.description.trim(),
      item_id: v.item_id || null,
      observation: v.observation.trim() || null,
      action_attendue: v.action_attendue.trim() || null,
    }), {
      loading: 'Enregistrement de l’anomalie…',
      succes: 'Anomalie enregistrée',
      errorTitle: 'Anomalie refusée',
    }, () => this.fermer(true));
  }

  annulerAnomalie(a: EerAnomalie): void {
    const d = this.dossier();
    if (!d) return;
    this.muterMotif(
      { title: 'Annuler l’anomalie', message: a.description, reasonLabel: 'Motif d’annulation', required: true, maxLength: 1000, tone: 'danger', confirmLabel: 'Annuler l’anomalie' },
      (rev, motif) => this.eer.modifierAnomalie(d.id, a.id, rev, { annuler_motif: motif }),
      'Anomalie annulée',
      'Annulation refusée',
    );
  }

  accepterAnomalie(a: EerAnomalie): void {
    const d = this.dossier();
    if (!d) return;
    this.muterMotif(
      { title: 'Accepter avec justification', message: a.description, reasonLabel: 'Justification (dérogation)', required: true, maxLength: 1000, tone: 'warn', confirmLabel: 'Accepter' },
      (rev, justification) => this.eer.modifierAnomalie(d.id, a.id, rev, { accepter_justification: justification }),
      'Anomalie acceptée',
      'Acceptation refusée',
    );
  }

  libelleItem(id: string | null): string {
    if (!id) return '—';
    return this.checklist()?.items.find((i) => i.id === id)?.libelle ?? '—';
  }

  // --- Versions ------------------------------------------------------------------------------

  ouvrirVersion(v: EerVersionLigne): void {
    this.versionDetail.set(null);
    this.modal.set('version');
    this.eer.version(this.id(), v.id).subscribe({ next: (r) => this.versionDetail.set(r), error: (e) => this.fail(e) });
  }

  json(v: unknown): string {
    return JSON.stringify(v, null, 2);
  }

  // --- Modales -------------------------------------------------------------------------------

  private formModalDirty(): boolean {
    switch (this.modal()) {
      case 'assign':
        return this.assignForm.dirty;
      case 'complement':
      case 'avis-defavorable':
        return this.complementForm.dirty;
      case 'anomalie':
        return this.anomalieForm.dirty;
      default:
        return false;
    }
  }

  fermer(force = false): void {
    if (!force && this.busy()) return;
    this.modal.set(null);
    this.assignForm.markAsPristine();
    this.complementForm.markAsPristine();
    this.anomalieForm.markAsPristine();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.modal()) this.fermer();
  }

  // --- Affichage -----------------------------------------------------------------------------

  readonly libStatut = (c: string | null | undefined) => libelle(STATUTS, c);
  readonly libEtape = (c: string | null | undefined) => libelle(ETAPES, c);
  readonly libType = (c: string | null | undefined) => libelle(TYPES_CLIENT, c);
  readonly libRole = (c: string | null | undefined) => libelle(ROLES_PARTIE, c);
  readonly libElement = (c: string | null | undefined) => libelle(ELEMENT_STATUTS, c);
  readonly libEtatChamp = (c: string | null | undefined) => libelle(ETATS_CHAMP, c);
  readonly libPresence = (c: string | null | undefined) => libelle(PRESENCES, c);
  readonly tone = eerTone;
  readonly date = dateFr;
  readonly val = valeurAffichee;

  ouiNon(v: boolean | null | undefined): string {
    return v === null || v === undefined ? '—' : v ? 'Oui' : 'Non';
  }

  private fail(err: unknown): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, 'Chargement impossible'));
  }
}
