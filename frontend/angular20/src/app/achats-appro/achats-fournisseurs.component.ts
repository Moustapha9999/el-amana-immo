import { MontantPipe, QuantitePipe } from '../shared/montant.pipe';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';

export interface FournisseurRow {
  id: string;
  code: string;
  raison_sociale: string;
  nom_commercial?: string | null;
  type_fournisseur?: string;
  contact?: string | null;
  contact_fonction?: string | null;
  telephone?: string | null;
  telephone_secondaire?: string | null;
  email?: string | null;
  site_web?: string | null;
  adresse?: string | null;
  ville?: string | null;
  pays?: string | null;
  nif?: string | null;
  rc?: string | null;
  devise_defaut?: string | null;
  mode_paiement_defaut?: string | null;
  delai_paiement_jours?: number | null;
  conditions_commerciales?: string | null;
  is_active?: boolean;
  nb_consultations?: number;
  nb_devis?: number;
  nb_bons?: number;
  nb_receptions?: number;
  nb_factures?: number;
  nb_paiements?: number;
  montant_bons?: number;
  montant_factures?: number;
}

interface PageOut {
  items: FournisseurRow[];
  total: number;
  page: number;
  size: number;
}

type Mode = 'list' | 'form' | 'fiche';
type FicheTab = 'infos' | 'contacts' | 'adresse' | 'conditions' | 'documents' | 'historique';

@Component({
  selector: 'bea-achats-fournisseurs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, ReactiveFormsModule, MatIconModule, MontantPipe, QuantitePipe, MgGedPanelComponent],
  templateUrl: './achats-fournisseurs.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsFournisseursComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly mode = signal<Mode>('list');
  readonly rows = signal<FournisseurRow[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly fiche = signal<FournisseurRow | null>(null);
  readonly editingId = signal<string | null>(null);
  readonly ficheTab = signal<FicheTab>('infos');
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly saving = signal(false);
  readonly confirm = signal<{ row: FournisseurRow; action: 'desactiver' | 'activer' | 'supprimer' } | null>(
    null,
  );

  readonly filters = this.fb.nonNullable.group({
    q: '',
    statut: '',
    type_fournisseur: '',
    ville: '',
    pays: '',
  });

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.maxLength(30)]],
    raison_sociale: ['', [Validators.required, Validators.maxLength(255)]],
    nom_commercial: [''],
    type_fournisseur: ['FOURNITURE', Validators.required],
    contact: [''],
    contact_fonction: [''],
    telephone: [''],
    telephone_secondaire: [''],
    email: [''],
    site_web: [''],
    adresse: [''],
    ville: [''],
    pays: ['Mauritanie'],
    nif: [''],
    rc: [''],
    devise_defaut: ['MRU'],
    mode_paiement_defaut: [''],
    delai_paiement_jours: [null as number | null],
    conditions_commerciales: [''],
  });

  readonly actifs = computed(() => this.rows().filter((r) => r.is_active !== false).length);
  readonly inactifs = computed(() => this.rows().filter((r) => r.is_active === false).length);
  readonly totalBons = computed(() => this.rows().reduce((n, r) => n + (r.nb_bons ?? 0), 0));

  readonly types = [
    { value: 'FOURNITURE', label: 'Fourniture' },
    { value: 'SERVICE', label: 'Service' },
    { value: 'MIXTE', label: 'Mixte' },
    { value: 'TRAVAUX', label: 'Travaux' },
  ];

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const url = this.router.url;
    if (url.includes('/fournisseurs/nouveau')) {
      this.mode.set('form');
      this.editingId.set(null);
      this.form.reset({
        code: '',
        raison_sociale: '',
        nom_commercial: '',
        type_fournisseur: 'FOURNITURE',
        contact: '',
        contact_fonction: '',
        telephone: '',
        telephone_secondaire: '',
        email: '',
        site_web: '',
        adresse: '',
        ville: '',
        pays: 'Mauritanie',
        nif: '',
        rc: '',
        devise_defaut: 'MRU',
        mode_paiement_defaut: '',
        delai_paiement_jours: null,
        conditions_commerciales: '',
      });
      return;
    }
    if (id) {
      this.openFiche(id);
      return;
    }
    this.mode.set('list');
    this.load();
  }

  load(page = 1): void {
    this.erreur.set('');
    const f = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      page,
      size: 50,
      actifs_seulement: 'false',
    };
    if (f.q.trim()) params['q'] = f.q.trim();
    if (f.statut) params['statut'] = f.statut;
    if (f.type_fournisseur) params['type_fournisseur'] = f.type_fournisseur;
    if (f.ville.trim()) params['ville'] = f.ville.trim();
    if (f.pays.trim()) params['pays'] = f.pays.trim();
    this.api.get<PageOut>('/mg/achats/fournisseurs', params).subscribe({
      next: (res) => {
        this.rows.set(res.items ?? []);
        this.total.set(res.total ?? 0);
        this.page.set(res.page ?? page);
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Liste fournisseurs indisponible.')),
    });
  }

  search(): void {
    this.load(1);
  }

  openCreate(): void {
    void this.router.navigateByUrl('/achats-appro/fournisseurs/nouveau');
  }

  openFiche(id: string): void {
    this.mode.set('fiche');
    this.ficheTab.set('infos');
    this.api.get<FournisseurRow>(`/mg/achats/fournisseurs/${id}`).subscribe({
      next: (f) => this.fiche.set(f),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Fournisseur introuvable.')),
    });
  }

  openEdit(row: FournisseurRow): void {
    this.mode.set('form');
    this.editingId.set(row.id);
    this.form.reset({
      code: row.code ?? '',
      raison_sociale: row.raison_sociale ?? '',
      nom_commercial: row.nom_commercial ?? '',
      type_fournisseur: row.type_fournisseur ?? 'FOURNITURE',
      contact: row.contact ?? '',
      contact_fonction: row.contact_fonction ?? '',
      telephone: row.telephone ?? '',
      telephone_secondaire: row.telephone_secondaire ?? '',
      email: row.email ?? '',
      site_web: row.site_web ?? '',
      adresse: row.adresse ?? '',
      ville: row.ville ?? '',
      pays: row.pays ?? 'Mauritanie',
      nif: row.nif ?? '',
      rc: row.rc ?? '',
      devise_defaut: row.devise_defaut ?? 'MRU',
      mode_paiement_defaut: row.mode_paiement_defaut ?? '',
      delai_paiement_jours: row.delai_paiement_jours ?? null,
      conditions_commerciales: row.conditions_commerciales ?? '',
    });
  }

  editFromFiche(): void {
    const f = this.fiche();
    if (f) this.openEdit(f);
  }

  cancelForm(): void {
    const id = this.editingId();
    if (id) void this.router.navigateByUrl(`/achats-appro/fournisseurs/${id}`);
    else void this.router.navigateByUrl('/achats-appro/fournisseurs');
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.erreur.set('Complétez les champs obligatoires (code, raison sociale).');
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    const raw = this.form.getRawValue();
    const body = {
      code: raw.code.trim(),
      raison_sociale: raw.raison_sociale.trim(),
      nom_commercial: raw.nom_commercial.trim() || null,
      type_fournisseur: raw.type_fournisseur,
      contact: raw.contact.trim() || null,
      contact_fonction: raw.contact_fonction.trim() || null,
      telephone: raw.telephone.trim() || null,
      telephone_secondaire: raw.telephone_secondaire.trim() || null,
      email: raw.email.trim() || null,
      site_web: raw.site_web.trim() || null,
      adresse: raw.adresse.trim() || null,
      ville: raw.ville.trim() || null,
      pays: raw.pays.trim() || 'Mauritanie',
      nif: raw.nif.trim() || null,
      rc: raw.rc.trim() || null,
      devise_defaut: raw.devise_defaut.trim() || 'MRU',
      mode_paiement_defaut: raw.mode_paiement_defaut.trim() || null,
      delai_paiement_jours: raw.delai_paiement_jours,
      conditions_commerciales: raw.conditions_commerciales.trim() || null,
    };
    const id = this.editingId();
    const req = id
      ? this.api.patch<FournisseurRow>(`/mg/achats/fournisseurs/${id}`, body)
      : this.api.post<FournisseurRow>('/mg/achats/fournisseurs', body);
    req.subscribe({
      next: (created) => {
        this.saving.set(false);
        this.msg.set(id ? 'Fournisseur mis à jour.' : 'Fournisseur créé.');
        void this.router.navigateByUrl(`/achats-appro/fournisseurs/${created.id}`);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.'));
      },
    });
  }

  askAction(row: FournisseurRow, action: 'desactiver' | 'activer' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const id = c.row.id;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/fournisseurs/${id}`)
        : c.action === 'activer'
          ? this.api.post(`/mg/achats/fournisseurs/${id}/activer`, {})
          : this.api.post(`/mg/achats/fournisseurs/${id}/desactiver`, {});
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? 'Fournisseur supprimé.'
            : c.action === 'activer'
              ? 'Fournisseur réactivé.'
              : 'Fournisseur désactivé.',
        );
        if (this.mode() === 'fiche') this.openFiche(id);
        else this.load(this.page());
      },
      error: (err) => {
        this.confirm.set(null);
        this.erreur.set(this.apiDetail(err, 'Action refusée.'));
      },
    });
  }

  backToList(): void {
    void this.router.navigateByUrl('/achats-appro/fournisseurs');
  }

  private apiDetail(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((x) => (typeof x === 'string' ? x : (x as { msg?: string })?.msg))
        .filter((x): x is string => !!x);
      if (msgs.length) return msgs.join(' · ');
    }
    return fallback;
  }
}
