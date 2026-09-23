import { DecimalPipe } from '@angular/common';
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
import { SupplierSelectComponent } from './supplier-select.component';

interface Dash {
  demandes_ouvertes: number;
  consultations_ouvertes: number;
  devis_ouverts: number;
  comparaisons_ouvertes: number;
  bons_en_cours: number;
  bons_partiels: number;
  receptions_mois: number;
  factures_ouvertes: number;
  paiements_a_payer: number;
  montant_bc_mois: number;
  montant_factures_mois: number;
  alertes: number;
}

interface Alerte {
  type: string;
  reference: string;
  entity_id: string;
  message: string;
  priorite: string;
  date_echeance?: string | null;
}

interface Agence {
  id: string;
  libelle: string;
}

interface Fournisseur {
  id: string;
  raison_sociale: string;
  telephone?: string | null;
  email?: string | null;
  nb_bons?: number;
  nb_devis?: number;
  nb_factures?: number;
}

interface Demande {
  id: string;
  reference: string;
  date_demande: string;
  statut: string;
  type_achat: string;
  priorite: string;
  motif: string | null;
  demandeur_nom: string | null;
  agence_id: string;
}

interface Parametre {
  cle: string;
  valeur: string;
  description: string | null;
}

@Component({
  selector: 'bea-achats-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DecimalPipe, MatIconModule],
  template: `
    <section class="bea-ach">
      <header class="bea-ach__hero">
        <p>Achats &amp; Approvisionnements</p>
        <h1>Tableau de bord</h1>
        <div class="bea-ach__hero-glow" aria-hidden="true"></div>
      </header>

      @if (erreur()) {
        <p class="bea-ach__error">{{ erreur() }}</p>
      } @else if (loading()) {
        <div class="bea-ach__skeleton" aria-busy="true">
          @for (_ of [1, 2, 3, 4, 5, 6, 7, 8]; track _) {
            <div class="bea-ach__skel"></div>
          }
        </div>
      } @else if (d(); as dash) {
        <div class="bea-ach__kpis">
          <a class="bea-ach__kpi" routerLink="/achats-appro/demandes" style="--i:0">
            <span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>assignment</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Demandes ouvertes</span>
              <strong>{{ dash.demandes_ouvertes | number: '1.0-0' }}</strong>
              <em>À traiter</em>
            </span>
          </a>
          <a class="bea-ach__kpi" routerLink="/achats-appro/consultations" style="--i:1">
            <span class="bea-ach__kpi-icon" data-tone="blue"><mat-icon>forum</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Consultations</span>
              <strong>{{ dash.consultations_ouvertes | number: '1.0-0' }}</strong>
              <em>En cours</em>
            </span>
          </a>
          <a class="bea-ach__kpi" routerLink="/achats-appro/devis" style="--i:2">
            <span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>request_quote</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Devis</span>
              <strong>{{ dash.devis_ouverts | number: '1.0-0' }}</strong>
              <em>À analyser</em>
            </span>
          </a>
          <a class="bea-ach__kpi" routerLink="/achats-appro/comparaisons" style="--i:3">
            <span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>compare_arrows</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Comparaisons</span>
              <strong>{{ dash.comparaisons_ouvertes | number: '1.0-0' }}</strong>
              <em>En cours</em>
            </span>
          </a>
        </div>

        <div class="bea-ach__kpis">
          <a class="bea-ach__kpi" routerLink="/achats-appro/bons" style="--i:0">
            <span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>receipt_long</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>BC en cours</span>
              <strong>{{ dash.bons_en_cours | number: '1.0-0' }}</strong>
              <em>Pipeline commande</em>
            </span>
          </a>
          <a
            class="bea-ach__kpi"
            routerLink="/achats-appro/bons"
            style="--i:1"
            [attr.data-active]="dash.bons_partiels > 0 ? 'warn' : null"
          >
            <span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending_actions</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>BC partiels</span>
              <strong>{{ dash.bons_partiels | number: '1.0-0' }}</strong>
              <em>Réception incomplète</em>
            </span>
          </a>
          <a class="bea-ach__kpi" routerLink="/achats-appro/receptions" style="--i:2">
            <span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>local_shipping</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Réceptions</span>
              <strong>{{ dash.receptions_mois | number: '1.0-0' }}</strong>
              <em>Ce mois</em>
            </span>
          </a>
          <a class="bea-ach__kpi" routerLink="/achats-appro/factures" style="--i:3">
            <span class="bea-ach__kpi-icon" data-tone="blue"><mat-icon>receipt</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Factures ouvertes</span>
              <strong>{{ dash.factures_ouvertes | number: '1.0-0' }}</strong>
              <em>Contrôle 3 voies</em>
            </span>
          </a>
        </div>

        <div class="bea-ach__kpis bea-ach__kpis--3">
          <a class="bea-ach__kpi" routerLink="/achats-appro/paiements" style="--i:0">
            <span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>payments</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>À payer</span>
              <strong>{{ dash.paiements_a_payer | number: '1.0-0' }}</strong>
              <em>Suivi interne</em>
            </span>
          </a>
          <a
            class="bea-ach__kpi"
            routerLink="/achats-appro/alertes"
            style="--i:1"
            [attr.data-active]="dash.alertes > 0 ? 'danger' : null"
          >
            <span class="bea-ach__kpi-icon" data-tone="danger"><mat-icon>notifications_active</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Alertes</span>
              <strong>{{ dash.alertes | number: '1.0-0' }}</strong>
              <em>Échéances / retards</em>
            </span>
          </a>
          <a class="bea-ach__kpi" routerLink="/achats-appro/rapports" style="--i:2">
            <span class="bea-ach__kpi-icon" data-tone="blue"><mat-icon>analytics</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Rapports</span>
              <strong>{{ dash.montant_bc_mois | number: '1.0-0' }}</strong>
              <em>BC du mois (MRU)</em>
            </span>
          </a>
        </div>

        <div class="bea-ach__money">
          <div class="bea-ach__money-card">
            <span>Montant BC du mois</span>
            <strong>{{ dash.montant_bc_mois | number: '1.2-2' }} MRU</strong>
          </div>
          <div class="bea-ach__money-card">
            <span>Montant factures du mois</span>
            <strong>{{ dash.montant_factures_mois | number: '1.2-2' }} MRU</strong>
          </div>
        </div>

        <nav class="bea-ach__shortcuts" aria-label="Raccourcis">
          <a routerLink="/achats-appro/demandes/nouvelle"><mat-icon>add</mat-icon> Nouvelle demande</a>
          <a routerLink="/achats-appro/nouveau"><mat-icon>post_add</mat-icon> Nouveau BC</a>
          <a routerLink="/achats-appro/receptions/nouvelle"><mat-icon>inventory</mat-icon> Réception</a>
          <a routerLink="/achats-appro/rapports"><mat-icon>analytics</mat-icon> Rapports</a>
        </nav>
      }
    </section>
  `,
})
export class AchatsDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly d = signal<Dash | null>(null);
  readonly loading = signal(true);
  readonly erreur = signal('');

  ngOnInit(): void {
    this.api.get<Dash>('/mg/achats/dashboard').subscribe({
      next: (row) => {
        this.d.set(row);
        this.loading.set(false);
      },
      error: () => {
        this.erreur.set('Tableau de bord indisponible.');
        this.loading.set(false);
      },
    });
  }
}

@Component({
  selector: 'bea-achats-alertes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, ReactiveFormsModule],
  template: `
    <section class="bea-ach">
      <header class="bea-ach__hero">
        <p>Pilotage</p>
        <h1>Alertes</h1>
        <div class="bea-ach__hero-glow" aria-hidden="true"></div>
      </header>

      <div class="bea-ach__kpis bea-ach__kpis--3">
        <div class="bea-ach__kpi" style="--i:0" [attr.data-active]="urgentes() > 0 ? 'danger' : null">
          <span class="bea-ach__kpi-icon" data-tone="danger"><mat-icon>priority_high</mat-icon></span>
          <span class="bea-ach__kpi-meta">
            <span>Urgentes</span>
            <strong>{{ urgentes() }}</strong>
            <em>Échéance dépassée</em>
          </span>
        </div>
        <div class="bea-ach__kpi" style="--i:1" [attr.data-active]="normales() > 0 ? 'warn' : null">
          <span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>schedule</mat-icon></span>
          <span class="bea-ach__kpi-meta">
            <span>À surveiller</span>
            <strong>{{ normales() }}</strong>
            <em>Dans la fenêtre</em>
          </span>
        </div>
        <div class="bea-ach__kpi" style="--i:2">
          <span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>notifications</mat-icon></span>
          <span class="bea-ach__kpi-meta">
            <span>Total</span>
            <strong>{{ rows().length }}</strong>
            <em>Alertes actives</em>
          </span>
        </div>
      </div>

      <form class="bea-ach__search" [formGroup]="filters" (ngSubmit)="$event.preventDefault()">
        <label class="bea-ach__field bea-ach__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Filtrer par réf. ou message…" (input)="onSearch()" />
        </label>
        <label class="bea-ach__field">
          <mat-icon>filter_list</mat-icon>
          <select formControlName="priorite" (change)="onSearch()">
            <option value="">Toutes priorités</option>
            <option value="URGENT">Urgent</option>
            <option value="NORMAL">Normal</option>
          </select>
        </label>
      </form>

      @if (erreur()) {
        <p class="bea-ach__error">{{ erreur() }}</p>
      }

      <div class="bea-ach__panel">
        <div class="bea-ach__panel-top">
          <h2>Échéances et livraisons</h2>
          <span class="bea-ach__count">{{ filtered().length }} alerte(s)</span>
        </div>
        <div style="overflow-x:auto">
          <table class="bea-ach__table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Réf.</th>
                <th>Message</th>
                <th>Priorité</th>
                <th class="bea-ach__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (a of filtered(); track a.entity_id + a.type; let i = $index) {
                <tr [style.--i]="i">
                  <td>{{ typeLabel(a.type) }}</td>
                  <td><code class="bea-ach__code">{{ a.reference }}</code></td>
                  <td>{{ a.message }}</td>
                  <td>
                    <span class="bea-ach__badge" [attr.data-prio]="a.priorite">{{ a.priorite }}</span>
                  </td>
                  <td class="bea-ach__actions">
                    <button type="button" class="bea-ach__icon-btn" title="Voir" (click)="openDetail(a)">
                      <mat-icon>visibility</mat-icon>
                    </button>
                    <button type="button" class="bea-ach__icon-btn" title="Ouvrir la fiche" (click)="goEntity(a)">
                      <mat-icon>edit</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr class="bea-ach__empty">
                  <td colspan="5">
                    <mat-icon>check_circle</mat-icon>
                    <p>Aucune alerte pour ces critères.</p>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      @if (detail(); as d) {
        <div class="bea-ach__backdrop" (click)="closeDetail()" role="presentation"></div>
        <div class="bea-ach__modal" role="dialog" aria-modal="true" aria-label="Détail alerte">
          <header class="bea-ach__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Alerte</p>
              <h2>{{ d.reference }}</h2>
            </div>
            <button type="button" class="bea-ach__icon-btn" (click)="closeDetail()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <p><strong>{{ typeLabel(d.type) }}</strong></p>
          <p>{{ d.message }}</p>
          <p>
            Priorité :
            <span class="bea-ach__badge" [attr.data-prio]="d.priorite">{{ d.priorite }}</span>
          </p>
          <footer class="bea-ach__modal-foot">
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closeDetail()">Fermer</button>
            <button type="button" class="bea-ach__btn" (click)="goEntity(d)">Ouvrir la fiche</button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class AchatsAlertesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  readonly rows = signal<Alerte[]>([]);
  readonly detail = signal<Alerte | null>(null);
  readonly erreur = signal('');
  readonly q = signal('');
  readonly priorite = signal('');
  readonly filters = this.fb.nonNullable.group({ q: '', priorite: '' });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    const prio = this.priorite();
    return this.rows().filter((a) => {
      if (prio && a.priorite !== prio) return false;
      if (!term) return true;
      return (
        a.reference.toLowerCase().includes(term) ||
        a.message.toLowerCase().includes(term) ||
        a.type.toLowerCase().includes(term)
      );
    });
  });

  readonly urgentes = computed(() => this.rows().filter((a) => a.priorite === 'URGENT').length);
  readonly normales = computed(() => this.rows().filter((a) => a.priorite !== 'URGENT').length);

  ngOnInit(): void {
    this.api.get<Alerte[]>('/mg/achats/alertes').subscribe({
      next: (rows) => this.rows.set(rows),
      error: () => this.erreur.set('Alertes indisponibles.'),
    });
  }

  onSearch(): void {
    const v = this.filters.getRawValue();
    this.q.set(v.q);
    this.priorite.set(v.priorite);
  }

  typeLabel(type: string): string {
    const map: Record<string, string> = {
      FACTURE_ECHEANCE: 'Facture',
      PAIEMENT_ECHEANCE: 'Paiement',
      LIVRAISON_PREVUE: 'Livraison BC',
      DEVIS_VALIDITE: 'Devis',
      CONSULTATION_LIMITE: 'Consultation',
      FACTURE_3WM: 'Contrôle 3 voies',
    };
    return map[type] ?? type;
  }

  entityHref(a: Alerte): string {
    if (a.type === 'FACTURE_ECHEANCE' || a.type === 'FACTURE_3WM') {
      return `/achats-appro/factures/${a.entity_id}`;
    }
    if (a.type === 'PAIEMENT_ECHEANCE') return `/achats-appro/paiements/${a.entity_id}`;
    if (a.type === 'LIVRAISON_PREVUE') return `/achats-appro/bons/${a.entity_id}`;
    if (a.type === 'DEVIS_VALIDITE') return `/achats-appro/devis/${a.entity_id}`;
    if (a.type === 'CONSULTATION_LIMITE') return `/achats-appro/consultations/${a.entity_id}`;
    return '/achats-appro/alertes';
  }

  goEntity(a: Alerte): void {
    void this.router.navigateByUrl(this.entityHref(a));
  }

  openDetail(a: Alerte): void {
    this.detail.set(a);
  }

  closeDetail(): void {
    this.detail.set(null);
  }
}

@Component({
  selector: 'bea-achats-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, ReactiveFormsModule],
  template: `
    <section class="bea-ach">
      <header class="bea-ach__hero">
        <p>Configuration</p>
        <h1>Paramètres achats</h1>
        <div class="bea-ach__hero-glow"></div>
      </header>
      <div class="bea-ach__head">
        <div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0">
          <div class="bea-ach__kpi" style="--i:0">
            <span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>settings</mat-icon></span>
            <span class="bea-ach__kpi-meta"><span>Paramètres</span><strong>{{ rows().length }}</strong><em>Clés configurées</em></span>
          </div>
          <div class="bea-ach__kpi" style="--i:1">
            <span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>check_circle</mat-icon></span>
            <span class="bea-ach__kpi-meta"><span>Renseignés</span><strong>{{ filled() }}</strong><em>Valeurs actives</em></span>
          </div>
          <div class="bea-ach__kpi" style="--i:2">
            <span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>percent</mat-icon></span>
            <span class="bea-ach__kpi-meta"><span>TVA défaut</span><strong>{{ tvaDefaut() }}%</strong><em>Appliquée aux BC</em></span>
          </div>
        </div>
        <button type="button" class="bea-ach__btn" (click)="openCreate()"><mat-icon>add</mat-icon>Nouveau</button>
      </div>
      @if (erreur()) { <p class="bea-ach__error">{{ erreur() }}</p> }
      @if (msg()) { <p class="bea-ach__ok">{{ msg() }}</p> }
      <div class="bea-ach__panel">
        <div class="bea-ach__panel-top">
          <h2>Référentiel de configuration</h2>
          <span class="bea-ach__count">{{ rows().length }} paramètre(s)</span>
        </div>
        <div style="overflow-x:auto">
          <table class="bea-ach__table">
            <thead>
              <tr>
                <th>Clé</th>
                <th>Valeur</th>
                <th>Description</th>
                <th class="bea-ach__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (p of rows(); track p.cle; let i = $index) {
                <tr [style.--i]="i">
                  <td><code class="bea-ach__code">{{ p.cle }}</code></td>
                  <td>{{ p.valeur }}</td>
                  <td>{{ p.description || '—' }}</td>
                  <td class="bea-ach__actions">
                    <button type="button" class="bea-ach__icon-btn" title="Éditer" (click)="openEdit(p)"><mat-icon>edit</mat-icon></button>
                    <button type="button" class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Supprimer" (click)="askDelete(p)"><mat-icon>delete</mat-icon></button>
                  </td>
                </tr>
              } @empty {
                <tr class="bea-ach__empty"><td colspan="4"><mat-icon>settings</mat-icon><p>Aucun paramètre.</p></td></tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      @if (modal(); as mode) {
        <div class="bea-ach__backdrop" (click)="closeModal()"></div>
        <div class="bea-ach__modal" role="dialog" aria-modal="true">
          <header class="bea-ach__modal-head">
            <div>
              <p class="bea-ach__kicker">Paramètre</p>
              <h2>{{ mode === 'create' ? 'Nouveau paramètre' : 'Modifier le paramètre' }}</h2>
            </div>
            <button type="button" class="bea-ach__icon-btn" title="Fermer" (click)="closeModal()"><mat-icon>close</mat-icon></button>
          </header>
          <form class="bea-ach__form" style="box-shadow:none;border:0;padding:0;margin:0" [formGroup]="form" (ngSubmit)="save()">
            <div class="bea-ach__grid" style="grid-template-columns:1fr">
              <label>Clé
                <input formControlName="cle" placeholder="Ex. tva_defaut" [readonly]="mode === 'edit'" />
              </label>
              <label>Valeur
                <input formControlName="valeur" placeholder="Ex. 14" />
              </label>
              <label>Description
                <input formControlName="description" placeholder="Ex. Taux TVA par défaut (%)" />
              </label>
            </div>
            @if (modalErreur()) { <p class="bea-ach__error" style="margin-top:0.75rem">{{ modalErreur() }}</p> }
            <footer class="bea-ach__modal-foot" style="margin-top:1.25rem;padding:0;border:0">
              <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closeModal()">Annuler</button>
              <button type="submit" class="bea-ach__btn" [disabled]="saving()"><mat-icon>save</mat-icon>{{ saving() ? 'Enregistrement…' : 'Enregistrer' }}</button>
            </footer>
          </form>
        </div>
      }

      @if (deleteTarget(); as p) {
        <div class="bea-ach__backdrop" (click)="deleteTarget.set(null)"></div>
        <div class="bea-ach__modal" role="dialog" aria-modal="true">
          <header class="bea-ach__modal-head">
            <div>
              <p class="bea-ach__kicker">Confirmation</p>
              <h2>Supprimer le paramètre ?</h2>
            </div>
            <button type="button" class="bea-ach__icon-btn" title="Fermer" (click)="deleteTarget.set(null)"><mat-icon>close</mat-icon></button>
          </header>
          <p>La clé <code class="bea-ach__code">{{ p.cle }}</code> sera définitivement retirée.</p>
          <footer class="bea-ach__modal-foot">
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="deleteTarget.set(null)">Retour</button>
            <button type="button" class="bea-ach__btn" (click)="confirmDelete()">Supprimer</button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class AchatsParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<Parametre[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly modalErreur = signal('');
  readonly saving = signal(false);
  readonly modal = signal<'create' | 'edit' | null>(null);
  readonly deleteTarget = signal<Parametre | null>(null);
  readonly filled = computed(() => this.rows().filter((p) => !!p.valeur).length);
  readonly tvaDefaut = computed(() => {
    const row = this.rows().find((p) => p.cle === 'tva_defaut');
    return row?.valeur ?? '0';
  });

  readonly form = this.fb.nonNullable.group({
    cle: ['', Validators.required],
    valeur: ['', Validators.required],
    description: [''],
  });

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.api.get<Parametre[]>('/mg/achats/parametres').subscribe({
      next: (r) => this.rows.set(r),
      error: () => this.erreur.set('Paramètres indisponibles.'),
    });
  }

  openCreate(): void {
    this.modalErreur.set('');
    this.form.reset({ cle: '', valeur: '', description: '' });
    this.form.controls.cle.enable();
    this.modal.set('create');
  }

  openEdit(p: Parametre): void {
    this.modalErreur.set('');
    this.form.reset({ cle: p.cle, valeur: p.valeur, description: p.description ?? '' });
    this.form.controls.cle.disable();
    this.modal.set('edit');
  }

  closeModal(): void {
    this.modal.set(null);
    this.form.controls.cle.enable();
    this.modalErreur.set('');
  }

  save(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.modalErreur.set('');
    const raw = this.form.getRawValue();
    const mode = this.modal();
    const req =
      mode === 'edit'
        ? this.api.patch<Parametre>(`/mg/achats/parametres/${raw.cle}`, {
            valeur: raw.valeur,
            description: raw.description || null,
          })
        : this.api.post<Parametre>('/mg/achats/parametres', {
            cle: raw.cle.trim(),
            valeur: raw.valeur,
            description: raw.description || null,
          });
    req.subscribe({
      next: () => {
        this.saving.set(false);
        this.closeModal();
        this.msg.set(mode === 'edit' ? 'Paramètre mis à jour.' : 'Paramètre créé.');
        this.reload();
      },
      error: (err) => {
        this.saving.set(false);
        const detail = (err as { error?: { detail?: string } })?.error?.detail;
        this.modalErreur.set(typeof detail === 'string' && detail ? detail : 'Enregistrement impossible.');
      },
    });
  }

  askDelete(p: Parametre): void {
    this.deleteTarget.set(p);
  }

  confirmDelete(): void {
    const p = this.deleteTarget();
    if (!p) return;
    this.api.delete(`/mg/achats/parametres/${p.cle}`).subscribe({
      next: () => {
        this.deleteTarget.set(null);
        this.msg.set(`Paramètre ${p.cle} supprimé.`);
        this.reload();
      },
      error: (err) => {
        this.deleteTarget.set(null);
        const detail = (err as { error?: { detail?: string } })?.error?.detail;
        this.erreur.set(typeof detail === 'string' && detail ? detail : 'Suppression refusée.');
      },
    });
  }
}

