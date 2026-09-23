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

interface Dash {
  demandes_ouvertes: number;
  consultations_ouvertes: number;
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

interface Consultation {
  id: string;
  reference: string;
  objet: string;
  statut: string;
  date_consultation: string;
}

interface Devis {
  id: string;
  reference: string;
  fournisseur_id: string;
  montant_ttc: number;
  statut: string;
  date_devis: string;
}

interface Comparaison {
  id: string;
  reference: string;
  statut: string;
  motif_choix: string | null;
}

interface Bl {
  id: string;
  reference: string;
  bon_id: string;
  date_bl: string;
  statut: string;
}

interface Reception {
  id: string;
  reference: string;
  bon_id: string;
  date_reception: string;
  statut: string;
}

interface Facture {
  id: string;
  reference: string;
  bon_id: string;
  date_facture: string;
  montant_ttc: number;
  statut: string;
  ecart_quantite: boolean;
  ecart_montant: boolean;
}

interface Paiement {
  id: string;
  reference: string;
  facture_id: string;
  montant: number;
  statut: string;
  date_echeance: string | null;
}

interface Parametre {
  cle: string;
  valeur: string;
  description: string | null;
}

interface Rapport {
  nb_demandes: number;
  nb_bons: number;
  nb_receptions: number;
  nb_factures: number;
  montant_bons: number;
  montant_factures: number;
  montant_paiements: number;
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
          <a class="bea-ach__kpi" routerLink="/achats-appro/bons" style="--i:2">
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
            style="--i:3"
            [attr.data-active]="dash.bons_partiels > 0 ? 'warn' : null"
          >
            <span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending_actions</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>BC partiels</span>
              <strong>{{ dash.bons_partiels | number: '1.0-0' }}</strong>
              <em>Réception incomplète</em>
            </span>
          </a>
        </div>

        <div class="bea-ach__kpis">
          <a class="bea-ach__kpi" routerLink="/achats-appro/receptions" style="--i:0">
            <span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>local_shipping</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Réceptions</span>
              <strong>{{ dash.receptions_mois | number: '1.0-0' }}</strong>
              <em>Ce mois</em>
            </span>
          </a>
          <a class="bea-ach__kpi" routerLink="/achats-appro/factures" style="--i:1">
            <span class="bea-ach__kpi-icon" data-tone="blue"><mat-icon>request_quote</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Factures ouvertes</span>
              <strong>{{ dash.factures_ouvertes | number: '1.0-0' }}</strong>
              <em>Contrôle 3 voies</em>
            </span>
          </a>
          <a class="bea-ach__kpi" routerLink="/achats-appro/paiements" style="--i:2">
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
            style="--i:3"
            [attr.data-active]="dash.alertes > 0 ? 'danger' : null"
          >
            <span class="bea-ach__kpi-icon" data-tone="danger"><mat-icon>notifications_active</mat-icon></span>
            <span class="bea-ach__kpi-meta">
              <span>Alertes</span>
              <strong>{{ dash.alertes | number: '1.0-0' }}</strong>
              <em>Échéances / retards</em>
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
                    <button type="button" class="bea-ach__icon-btn" title="Éditer" disabled>
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button type="button" class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactiver" disabled>
                      <mat-icon>block</mat-icon>
                    </button>
                    <button type="button" class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Supprimer" disabled>
                      <mat-icon>delete</mat-icon>
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
    };
    return map[type] ?? type;
  }

  entityHref(a: Alerte): string {
    if (a.type === 'FACTURE_ECHEANCE') return `/achats-appro/factures/${a.entity_id}`;
    if (a.type === 'PAIEMENT_ECHEANCE') return `/achats-appro/paiements/${a.entity_id}`;
    if (a.type === 'LIVRAISON_PREVUE') return `/achats-appro/bons/${a.entity_id}`;
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
  selector: 'bea-achats-demandes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MgGedPanelComponent, MatIconModule],
  template: `
    <section class="bea-ach">
      @if (mode() === 'list') {
        <header class="bea-ach__hero">
          <p>Amont</p>
          <h1>Demandes d'achat</h1>
          <div class="bea-ach__hero-glow" aria-hidden="true"></div>
        </header>

        <div class="bea-ach__head">
          <div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0">
            <div class="bea-ach__kpi" style="--i:0">
              <span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>draft</mat-icon></span>
              <span class="bea-ach__kpi-meta">
                <span>Brouillons</span>
                <strong>{{ countStatut('BROUILLON') }}</strong>
                <em>En rédaction</em>
              </span>
            </div>
            <div class="bea-ach__kpi" style="--i:1" [attr.data-active]="countStatut('SOUMISE') > 0 ? 'warn' : null">
              <span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>hourglass_top</mat-icon></span>
              <span class="bea-ach__kpi-meta">
                <span>Soumises</span>
                <strong>{{ countStatut('SOUMISE') }}</strong>
                <em>En attente visa</em>
              </span>
            </div>
            <div class="bea-ach__kpi" style="--i:2">
              <span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>verified</mat-icon></span>
              <span class="bea-ach__kpi-meta">
                <span>Validées</span>
                <strong>{{ countStatut('VALIDEE') + countStatut('CONSULTATION') + countStatut('COMMANDE') }}</strong>
                <em>Pipeline amont</em>
              </span>
            </div>
          </div>
          <a class="bea-ach__btn" routerLink="/achats-appro/demandes/nouvelle">
            <mat-icon>add</mat-icon> Nouvelle
          </a>
        </div>

        <form class="bea-ach__search" [formGroup]="filters" (ngSubmit)="$event.preventDefault()">
          <label class="bea-ach__field bea-ach__field--grow">
            <mat-icon>search</mat-icon>
            <input formControlName="q" placeholder="Réf., demandeur, motif…" (input)="onSearch()" />
          </label>
          <label class="bea-ach__field">
            <mat-icon>filter_alt</mat-icon>
            <select formControlName="statut" (change)="onSearch()">
              <option value="">Tous les statuts</option>
              <option value="BROUILLON">Brouillon</option>
              <option value="SOUMISE">Soumise</option>
              <option value="VALIDEE">Validée</option>
              <option value="CONSULTATION">Consultation</option>
              <option value="COMMANDE">Commandée</option>
              <option value="ANNULEE">Annulée</option>
            </select>
          </label>
        </form>

        @if (erreur()) {
          <p class="bea-ach__error">{{ erreur() }}</p>
        }
        @if (msg()) {
          <p class="bea-ach__ok">{{ msg() }}</p>
        }

        <div class="bea-ach__panel">
          <div class="bea-ach__panel-top">
            <h2>Liste des demandes</h2>
            <span class="bea-ach__count">{{ filtered().length }} résultat(s)</span>
          </div>
          <div style="overflow-x:auto">
            <table class="bea-ach__table">
              <thead>
                <tr>
                  <th>Réf.</th>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Priorité</th>
                  <th>Statut</th>
                  <th class="bea-ach__th-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                @for (r of filtered(); track r.id; let i = $index) {
                  <tr [style.--i]="i">
                    <td><code class="bea-ach__code">{{ r.reference }}</code></td>
                    <td>{{ r.date_demande }}</td>
                    <td>{{ r.type_achat }}</td>
                    <td>
                      <span class="bea-ach__badge" [attr.data-prio]="r.priorite">{{ r.priorite }}</span>
                    </td>
                    <td>
                      <span class="bea-ach__badge" [attr.data-statut]="r.statut">{{ r.statut }}</span>
                    </td>
                    <td class="bea-ach__actions">
                      <a
                        class="bea-ach__icon-btn"
                        title="Voir"
                        [routerLink]="['/achats-appro/demandes', r.id]"
                      >
                        <mat-icon>visibility</mat-icon>
                      </a>
                      <button
                        type="button"
                        class="bea-ach__icon-btn"
                        title="Éditer"
                        [disabled]="!canEdit(r)"
                        (click)="edit(r)"
                      >
                        <mat-icon>edit</mat-icon>
                      </button>
                      <button
                        type="button"
                        class="bea-ach__icon-btn bea-ach__icon-btn--warn"
                        title="Désactiver"
                        [disabled]="!canCancel(r)"
                        (click)="askAction(r, 'annuler')"
                      >
                        <mat-icon>block</mat-icon>
                      </button>
                      <button
                        type="button"
                        class="bea-ach__icon-btn bea-ach__icon-btn--danger"
                        title="Supprimer"
                        [disabled]="!canCancel(r)"
                        (click)="askAction(r, 'supprimer')"
                      >
                        <mat-icon>delete</mat-icon>
                      </button>
                    </td>
                  </tr>
                } @empty {
                  <tr class="bea-ach__empty">
                    <td colspan="6">
                      <mat-icon>assignment</mat-icon>
                      <p>Aucune demande pour ces critères.</p>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      } @else {
        <header class="bea-ach__head">
          <div>
            <p class="bea-stock-page__kicker">{{ id() ? 'Fiche' : 'Création' }}</p>
            <h1>{{ id() ? 'Demande ' + (current()?.reference || '') : 'Nouvelle demande' }}</h1>
          </div>
          <a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/demandes">
            <mat-icon>arrow_back</mat-icon> Retour
          </a>
        </header>

        @if (erreur()) {
          <p class="bea-ach__error">{{ erreur() }}</p>
        }
        @if (msg()) {
          <p class="bea-ach__ok">{{ msg() }}</p>
        }

        <form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()">
          <div class="bea-ach__grid">
            <label>Date <input type="date" formControlName="date_demande" /></label>
            <label>
              Agence
              <select formControlName="agence_id">
                <option value="">—</option>
                @for (a of agences(); track a.id) {
                  <option [value]="a.id">{{ a.libelle }}</option>
                }
              </select>
            </label>
            <label>Demandeur <input formControlName="demandeur_nom" /></label>
            <label>Motif <input formControlName="motif" /></label>
            <label>Désignation <input formControlName="designation" /></label>
            <label>Qté <input type="number" formControlName="quantite" /></label>
          </div>
          <div class="bea-ach__form-actions">
            <button type="submit" class="bea-ach__btn">
              <mat-icon>save</mat-icon> Enregistrer
            </button>
            @if (id()) {
              <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="go('soumettre')">
                Soumettre
              </button>
              <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="go('valider')">
                Valider
              </button>
            }
          </div>
        </form>
        @if (id()) {
          <div style="margin-top:1rem">
            <bea-mg-ged moduleCode="achats-appro" entity="achat_demande" [entityId]="id()!" />
          </div>
        }
      }

      @if (confirm(); as c) {
        <div class="bea-ach__backdrop" (click)="confirm.set(null)" role="presentation"></div>
        <div class="bea-ach__modal" role="dialog" aria-modal="true">
          <header class="bea-ach__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Confirmation</p>
              <h2>{{ c.action === 'supprimer' ? 'Supprimer' : 'Désactiver' }} la demande ?</h2>
            </div>
            <button type="button" class="bea-ach__icon-btn" (click)="confirm.set(null)" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <p>
            {{ c.action === 'supprimer' ? 'Annulation définitive' : 'Mise hors circuit' }} de
            <code class="bea-ach__code">{{ c.row.reference }}</code>.
          </p>
          <footer class="bea-ach__modal-foot">
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="confirm.set(null)">
              Annuler
            </button>
            <button type="button" class="bea-ach__btn" (click)="confirmAction()">Confirmer</button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class AchatsDemandesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  readonly rows = signal<Demande[]>([]);
  readonly current = signal<Demande | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<'list' | 'form'>('list');
  readonly id = signal<string | null>(null);
  readonly q = signal('');
  readonly statutFilter = signal('');
  readonly confirm = signal<{ row: Demande; action: 'annuler' | 'supprimer' } | null>(null);
  readonly filters = this.fb.nonNullable.group({ q: '', statut: '' });
  readonly form = this.fb.nonNullable.group({
    date_demande: [new Date().toISOString().slice(0, 10), Validators.required],
    agence_id: ['', Validators.required],
    demandeur_nom: [''],
    motif: [''],
    designation: ['', Validators.required],
    quantite: [1, Validators.required],
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    const statut = this.statutFilter();
    return this.rows().filter((r) => {
      if (statut && r.statut !== statut) return false;
      if (!term) return true;
      return (
        r.reference.toLowerCase().includes(term) ||
        (r.demandeur_nom ?? '').toLowerCase().includes(term) ||
        (r.motif ?? '').toLowerCase().includes(term)
      );
    });
  });

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/achats/agences').subscribe({ next: (rows) => this.agences.set(rows) });
    const url = this.router.url;
    const param = this.route.snapshot.paramMap.get('id');
    if (url.endsWith('/nouvelle') || param) {
      this.mode.set('form');
      if (param) {
        this.id.set(param);
        this.api.get<Demande>(`/mg/achats/demandes/${param}`).subscribe({
          next: (d) => {
            this.current.set(d);
            this.form.patchValue({
              date_demande: d.date_demande,
              agence_id: d.agence_id,
              demandeur_nom: d.demandeur_nom ?? '',
              motif: d.motif ?? '',
            });
          },
        });
      }
    } else {
      this.loadList();
    }
  }

  loadList(): void {
    this.api.get<Demande[]>('/mg/achats/demandes').subscribe({
      next: (rows) => this.rows.set(rows),
      error: () => this.erreur.set('Demandes indisponibles.'),
    });
  }

  onSearch(): void {
    const v = this.filters.getRawValue();
    this.q.set(v.q);
    this.statutFilter.set(v.statut);
  }

  countStatut(statut: string): number {
    return this.rows().filter((r) => r.statut === statut).length;
  }

  canEdit(r: Demande): boolean {
    return r.statut === 'BROUILLON' || r.statut === 'SOUMISE';
  }

  canCancel(r: Demande): boolean {
    return !['CLOTUREE', 'REJETEE', 'ANNULEE'].includes(r.statut);
  }

  edit(r: Demande): void {
    if (!this.canEdit(r)) return;
    void this.router.navigateByUrl(`/achats-appro/demandes/${r.id}`);
  }

  askAction(row: Demande, action: 'annuler' | 'supprimer'): void {
    if (!this.canCancel(row)) return;
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    this.api.post(`/mg/achats/demandes/${c.row.id}/transition`, { action: 'annuler' }).subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? `Demande ${c.row.reference} annulée.`
            : `Demande ${c.row.reference} désactivée.`,
        );
        this.loadList();
      },
      error: (err) => {
        this.confirm.set(null);
        const detail = (err as { error?: { detail?: string } })?.error?.detail;
        this.erreur.set(typeof detail === 'string' && detail ? detail : 'Action refusée.');
      },
    });
  }

  save(): void {
    if (this.form.invalid) return;
    const v = this.form.getRawValue();
    const body = {
      date_demande: v.date_demande,
      agence_id: v.agence_id,
      demandeur_nom: v.demandeur_nom || null,
      motif: v.motif || null,
      type_achat: 'FOURNITURE',
      lignes: [{ designation: v.designation, quantite: v.quantite, uom: 'U' }],
    };
    const req = this.id()
      ? this.api.patch<Demande>(`/mg/achats/demandes/${this.id()}`, body)
      : this.api.post<Demande>('/mg/achats/demandes', body);
    req.subscribe({
      next: (d) => void this.router.navigateByUrl(`/achats-appro/demandes/${d.id}`),
      error: (err) => {
        const detail = (err as { error?: { detail?: string } })?.error?.detail;
        this.erreur.set(typeof detail === 'string' && detail ? detail : 'Enregistrement impossible.');
      },
    });
  }

  go(action: string): void {
    const id = this.id();
    if (!id) return;
    this.api.post(`/mg/achats/demandes/${id}/transition`, { action }).subscribe({
      next: () => this.msg.set('Transition effectuée.'),
      error: (err) => {
        const detail = (err as { error?: { detail?: string } })?.error?.detail;
        this.erreur.set(typeof detail === 'string' && detail ? detail : 'Transition refusée.');
      },
    });
  }
}

@Component({
  selector: 'bea-achats-fournisseurs', changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MgGedPanelComponent, MatIconModule, ReactiveFormsModule],
  template: `
    <section class="bea-ach">
      @if (!id()) {
        <header class="bea-ach__hero"><p>Référentiel</p><h1>Fournisseurs</h1><div class="bea-ach__hero-glow"></div></header>
        <div class="bea-ach__kpis bea-ach__kpis--3">
          <div class="bea-ach__kpi" style="--i:0"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>storefront</mat-icon></span><span class="bea-ach__kpi-meta"><span>Fournisseurs</span><strong>{{ rows().length }}</strong><em>Partenaires référencés</em></span></div>
          <div class="bea-ach__kpi" style="--i:1"><span class="bea-ach__kpi-icon" data-tone="blue"><mat-icon>receipt_long</mat-icon></span><span class="bea-ach__kpi-meta"><span>Bons</span><strong>{{ total('nb_bons') }}</strong><em>Commandes associées</em></span></div>
          <div class="bea-ach__kpi" style="--i:2"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>request_quote</mat-icon></span><span class="bea-ach__kpi-meta"><span>Factures</span><strong>{{ total('nb_factures') }}</strong><em>Documents associés</em></span></div>
        </div>
        <form class="bea-ach__search" [formGroup]="filters"><label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Raison sociale, téléphone ou e-mail…" (input)="search()" /></label></form>
        @if (erreur()) { <p class="bea-ach__error">{{ erreur() }}</p> }
        <div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Annuaire fournisseurs</h2><span class="bea-ach__count">{{ filtered().length }} résultat(s)</span></div><div style="overflow-x:auto"><table class="bea-ach__table">
          <thead><tr><th>Raison sociale</th><th>Téléphone</th><th>E-mail</th><th>BC</th><th class="bea-ach__th-actions">Actions</th></tr></thead><tbody>
          @for (f of filtered(); track f.id; let i = $index) { <tr [style.--i]="i"><td>{{ f.raison_sociale }}</td><td>{{ f.telephone || '—' }}</td><td>{{ f.email || '—' }}</td><td>{{ f.nb_bons ?? 0 }}</td><td class="bea-ach__actions"><a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/fournisseurs', f.id]"><mat-icon>visibility</mat-icon></a><a class="bea-ach__icon-btn" title="Éditer (consultation de la fiche)" [routerLink]="['/achats-appro/fournisseurs', f.id]"><mat-icon>edit</mat-icon></a><button class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactivation non disponible" disabled><mat-icon>block</mat-icon></button><button class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Suppression non disponible" disabled><mat-icon>delete</mat-icon></button></td></tr> }
          @empty { <tr class="bea-ach__empty"><td colspan="5"><mat-icon>storefront</mat-icon><p>Aucun fournisseur.</p></td></tr> }</tbody></table></div></div>
      } @else {
        <header class="bea-ach__head"><div><p class="bea-ach__kicker">Fiche fournisseur</p><h1>{{ fiche()?.raison_sociale || 'Fournisseur' }}</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/fournisseurs"><mat-icon>arrow_back</mat-icon>Retour</a></header>
        @if (erreur()) { <p class="bea-ach__error">{{ erreur() }}</p> }
        @if (fiche(); as f) { <div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Coordonnées</h2><span class="bea-ach__count">{{ f.nb_bons ?? 0 }} BC</span></div><p>{{ f.email || 'E-mail non renseigné' }} · {{ f.telephone || 'Téléphone non renseigné' }}</p><div class="bea-ach__money"><div class="bea-ach__money-card"><span>Devis</span><strong>{{ f.nb_devis ?? 0 }}</strong></div><div class="bea-ach__money-card"><span>Factures</span><strong>{{ f.nb_factures ?? 0 }}</strong></div></div></div><bea-mg-ged moduleCode="achats-appro" entity="fournisseur" [entityId]="id()!" /> }
      }
    </section>`,
})
export class AchatsFournisseursComponent implements OnInit {
  private readonly api = inject(ApiService); private readonly route = inject(ActivatedRoute); private readonly fb = inject(FormBuilder);
  readonly rows = signal<Fournisseur[]>([]); readonly fiche = signal<Fournisseur | null>(null); readonly erreur = signal(''); readonly id = signal<string | null>(null); readonly q = signal('');
  readonly filters = this.fb.nonNullable.group({ q: '' });
  readonly filtered = computed(() => { const q = this.q().toLowerCase(); return this.rows().filter(f => !q || [f.raison_sociale, f.telephone ?? '', f.email ?? ''].some(v => v.toLowerCase().includes(q))); });
  ngOnInit(): void { const id = this.route.snapshot.paramMap.get('id'); this.id.set(id); if (id) this.api.get<Fournisseur>(`/mg/achats/fournisseurs/${id}`).subscribe({ next:f=>this.fiche.set(f), error:()=>this.erreur.set('Fournisseur introuvable.') }); else this.api.get<Fournisseur[]>('/mg/achats/fournisseurs').subscribe({ next:r=>this.rows.set(r), error:()=>this.erreur.set('Liste indisponible.') }); }
  search(): void { this.q.set(this.filters.controls.q.value.trim()); }
  total(key: 'nb_bons'|'nb_factures'): number { return this.rows().reduce((n,r)=>n+(r[key] ?? 0),0); }
}

@Component({
  selector: 'bea-achats-consultations', changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `<section class="bea-ach">
    @if (mode()==='list') {
      <header class="bea-ach__hero"><p>Mise en concurrence</p><h1>Consultations</h1><div class="bea-ach__hero-glow"></div></header>
      <div class="bea-ach__head"><div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0"><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>forum</mat-icon></span><span class="bea-ach__kpi-meta"><span>Total</span><strong>{{ rows().length }}</strong><em>Consultations</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending</mat-icon></span><span class="bea-ach__kpi-meta"><span>Ouvertes</span><strong>{{ active() }}</strong><em>En traitement</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>task_alt</mat-icon></span><span class="bea-ach__kpi-meta"><span>Clôturées</span><strong>{{ rows().length-active() }}</strong><em>Finalisées</em></span></div></div><a class="bea-ach__btn" routerLink="/achats-appro/consultations/nouvelle"><mat-icon>add</mat-icon>Nouvelle</a></div>
      <form class="bea-ach__search" [formGroup]="filters"><label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence ou objet…" (input)="search()" /></label></form>
      @if (erreur()) { <p class="bea-ach__error">{{ erreur() }}</p> } <div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Liste des consultations</h2><span class="bea-ach__count">{{ filtered().length }} résultat(s)</span></div><div style="overflow-x:auto"><table class="bea-ach__table"><thead><tr><th>Réf.</th><th>Objet</th><th>Date</th><th>Statut</th><th class="bea-ach__th-actions">Actions</th></tr></thead><tbody>
      @for(r of filtered();track r.id;let i=$index){<tr [style.--i]="i"><td><code class="bea-ach__code">{{r.reference}}</code></td><td>{{r.objet}}</td><td>{{r.date_consultation}}</td><td><span class="bea-ach__badge" [attr.data-statut]="r.statut">{{r.statut}}</span></td><td class="bea-ach__actions"><a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/consultations',r.id]"><mat-icon>visibility</mat-icon></a><a class="bea-ach__icon-btn" title="Éditer" [routerLink]="['/achats-appro/consultations',r.id]"><mat-icon>edit</mat-icon></a><button class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactivation non disponible" disabled><mat-icon>block</mat-icon></button><button class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Suppression non disponible" disabled><mat-icon>delete</mat-icon></button></td></tr>}@empty{<tr class="bea-ach__empty"><td colspan="5"><mat-icon>forum</mat-icon><p>Aucune consultation.</p></td></tr>}</tbody></table></div></div>
    } @else { <header class="bea-ach__head"><div><p class="bea-ach__kicker">Consultation</p><h1>{{ editing() ? 'Fiche consultation' : 'Nouvelle consultation' }}</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/consultations"><mat-icon>arrow_back</mat-icon>Retour</a></header><form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()"><div class="bea-ach__grid"><label>Date<input type="date" formControlName="date_consultation"/></label><label>Agence<select formControlName="agence_id">@for(a of agences();track a.id){<option [value]="a.id">{{a.libelle}}</option>}</select></label><label>Objet<input formControlName="objet"/></label></div><div class="bea-ach__form-actions"><button class="bea-ach__btn" type="submit"><mat-icon>save</mat-icon>Enregistrer</button></div></form> }
  </section>`,
})
export class AchatsConsultationsComponent implements OnInit {
  private readonly api=inject(ApiService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);private readonly fb=inject(FormBuilder);
  readonly rows=signal<Consultation[]>([]);readonly agences=signal<Agence[]>([]);readonly erreur=signal('');readonly mode=signal<'list'|'form'>('list');readonly editing=signal(false);readonly q=signal('');readonly filters=this.fb.nonNullable.group({q:''});
  readonly form=this.fb.nonNullable.group({date_consultation:[new Date().toISOString().slice(0,10),Validators.required],agence_id:['',Validators.required],objet:['',Validators.required]});
  readonly filtered=computed(()=>{const q=this.q().toLowerCase();return this.rows().filter(r=>!q||r.reference.toLowerCase().includes(q)||r.objet.toLowerCase().includes(q));});readonly active=computed(()=>this.rows().filter(r=>!['CLOTURE','CLOTUREE','ANNULEE'].includes(r.statut)).length);
  ngOnInit():void{this.api.get<Agence[]>('/mg/achats/agences').subscribe({next:r=>this.agences.set(r)});const p=this.route.snapshot.paramMap.get('id');if(this.router.url.endsWith('/nouvelle')||p){this.mode.set('form');this.editing.set(!!p);}else this.api.get<Consultation[]>('/mg/achats/consultations').subscribe({next:r=>this.rows.set(r),error:()=>this.erreur.set('Consultations indisponibles.')});}
  search():void{this.q.set(this.filters.controls.q.value.trim());} save():void{if(this.form.invalid)return;this.api.post<Consultation>('/mg/achats/consultations',this.form.getRawValue()).subscribe({next:c=>void this.router.navigateByUrl(`/achats-appro/consultations/${c.id}`),error:()=>this.erreur.set('Enregistrement impossible.')});}
}

@Component({
  selector:'bea-achats-devis',changeDetection:ChangeDetectionStrategy.OnPush,imports:[ReactiveFormsModule,RouterLink,DecimalPipe,MatIconModule],
  template:`<section class="bea-ach">@if(mode()==='list'){<header class="bea-ach__hero"><p>Offres fournisseurs</p><h1>Devis</h1><div class="bea-ach__hero-glow"></div></header>
  <div class="bea-ach__head"><div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0"><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>request_quote</mat-icon></span><span class="bea-ach__kpi-meta"><span>Total</span><strong>{{rows().length}}</strong><em>Offres reçues</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>payments</mat-icon></span><span class="bea-ach__kpi-meta"><span>Montant TTC</span><strong>{{total()|number:'1.0-0'}}</strong><em>MRU</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending</mat-icon></span><span class="bea-ach__kpi-meta"><span>En cours</span><strong>{{active()}}</strong><em>À analyser</em></span></div></div><a class="bea-ach__btn" routerLink="/achats-appro/devis/nouveau"><mat-icon>add</mat-icon>Nouveau</a></div>
  <form class="bea-ach__search" [formGroup]="filters"><label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence…" (input)="search()"/></label></form>@if(erreur()){<p class="bea-ach__error">{{erreur()}}</p>}
  <div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Liste des devis</h2><span class="bea-ach__count">{{filtered().length}} résultat(s)</span></div><div style="overflow-x:auto"><table class="bea-ach__table"><thead><tr><th>Réf.</th><th>Date</th><th>TTC</th><th>Statut</th><th class="bea-ach__th-actions">Actions</th></tr></thead><tbody>@for(r of filtered();track r.id;let i=$index){<tr [style.--i]="i"><td><code class="bea-ach__code">{{r.reference}}</code></td><td>{{r.date_devis}}</td><td>{{r.montant_ttc|number:'1.2-2'}} MRU</td><td><span class="bea-ach__badge" [attr.data-statut]="r.statut">{{r.statut}}</span></td><td class="bea-ach__actions"><a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/devis',r.id]"><mat-icon>visibility</mat-icon></a><a class="bea-ach__icon-btn" title="Éditer" [routerLink]="['/achats-appro/devis',r.id]"><mat-icon>edit</mat-icon></a><button class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactivation non disponible" disabled><mat-icon>block</mat-icon></button><button class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Suppression non disponible" disabled><mat-icon>delete</mat-icon></button></td></tr>}@empty{<tr class="bea-ach__empty"><td colspan="5"><mat-icon>request_quote</mat-icon><p>Aucun devis.</p></td></tr>}</tbody></table></div></div>
  }@else{<header class="bea-ach__head"><div><p class="bea-ach__kicker">Devis</p><h1>Nouveau devis</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/devis"><mat-icon>arrow_back</mat-icon>Retour</a></header><form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()"><div class="bea-ach__grid"><label>Fournisseur<select formControlName="fournisseur_id">@for(f of fournisseurs();track f.id){<option [value]="f.id">{{f.raison_sociale}}</option>}</select></label><label>Date<input type="date" formControlName="date_devis"/></label><label>Désignation<input formControlName="designation"/></label><label>Qté<input type="number" formControlName="quantite"/></label><label>PU<input type="number" formControlName="prix_unitaire"/></label></div><div class="bea-ach__form-actions"><button class="bea-ach__btn"><mat-icon>save</mat-icon>Enregistrer</button></div></form>}</section>`,
})
export class AchatsDevisComponent implements OnInit{
  private readonly api=inject(ApiService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);private readonly fb=inject(FormBuilder);readonly rows=signal<Devis[]>([]);readonly fournisseurs=signal<Fournisseur[]>([]);readonly erreur=signal('');readonly mode=signal<'list'|'form'>('list');readonly q=signal('');readonly filters=this.fb.nonNullable.group({q:''});
  readonly form=this.fb.nonNullable.group({fournisseur_id:['',Validators.required],date_devis:[new Date().toISOString().slice(0,10),Validators.required],designation:['',Validators.required],quantite:[1,Validators.required],prix_unitaire:[0,Validators.required]});readonly filtered=computed(()=>{const q=this.q().toLowerCase();return this.rows().filter(r=>!q||r.reference.toLowerCase().includes(q));});readonly total=computed(()=>this.rows().reduce((n,r)=>n+r.montant_ttc,0));readonly active=computed(()=>this.rows().filter(r=>!['RETENU','REJETE','ANNULE'].includes(r.statut)).length);
  ngOnInit():void{this.api.get<Fournisseur[]>('/mg/achats/fournisseurs').subscribe({next:r=>this.fournisseurs.set(r)});const p=this.route.snapshot.paramMap.get('id');if(this.router.url.endsWith('/nouveau')||p)this.mode.set('form');else this.api.get<Devis[]>('/mg/achats/devis').subscribe({next:r=>this.rows.set(r),error:()=>this.erreur.set('Devis indisponibles.')});}search():void{this.q.set(this.filters.controls.q.value.trim());}save():void{if(this.form.invalid)return;const v=this.form.getRawValue();this.api.post<Devis>('/mg/achats/devis',{fournisseur_id:v.fournisseur_id,date_devis:v.date_devis,lignes:[{designation:v.designation,quantite:v.quantite,prix_unitaire:v.prix_unitaire}]}).subscribe({next:d=>void this.router.navigateByUrl(`/achats-appro/devis/${d.id}`),error:()=>this.erreur.set('Enregistrement impossible.')});}
}

@Component({
  selector:'bea-achats-comparaisons',changeDetection:ChangeDetectionStrategy.OnPush,imports:[ReactiveFormsModule,RouterLink,MatIconModule],
  template:`<section class="bea-ach">@if(mode()==='list'){<header class="bea-ach__hero"><p>Aide à la décision</p><h1>Comparaisons</h1><div class="bea-ach__hero-glow"></div></header><div class="bea-ach__head"><div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0"><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>compare_arrows</mat-icon></span><span class="bea-ach__kpi-meta"><span>Total</span><strong>{{rows().length}}</strong><em>Analyses</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending</mat-icon></span><span class="bea-ach__kpi-meta"><span>En cours</span><strong>{{active()}}</strong><em>À décider</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>task_alt</mat-icon></span><span class="bea-ach__kpi-meta"><span>Finalisées</span><strong>{{rows().length-active()}}</strong><em>Choix actés</em></span></div></div><a class="bea-ach__btn" routerLink="/achats-appro/comparaisons/nouvelle"><mat-icon>add</mat-icon>Nouvelle</a></div><form class="bea-ach__search" [formGroup]="filters"><label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence ou motif…" (input)="search()"/></label></form>@if(erreur()){<p class="bea-ach__error">{{erreur()}}</p>}<div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Analyses comparatives</h2><span class="bea-ach__count">{{filtered().length}} résultat(s)</span></div><div style="overflow-x:auto"><table class="bea-ach__table"><thead><tr><th>Réf.</th><th>Statut</th><th>Motif</th><th class="bea-ach__th-actions">Actions</th></tr></thead><tbody>@for(r of filtered();track r.id;let i=$index){<tr [style.--i]="i"><td><code class="bea-ach__code">{{r.reference}}</code></td><td><span class="bea-ach__badge" [attr.data-statut]="r.statut">{{r.statut}}</span></td><td>{{r.motif_choix||'—'}}</td><td class="bea-ach__actions"><a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/comparaisons',r.id]"><mat-icon>visibility</mat-icon></a><a class="bea-ach__icon-btn" title="Éditer" [routerLink]="['/achats-appro/comparaisons',r.id]"><mat-icon>edit</mat-icon></a><button class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactivation non disponible" disabled><mat-icon>block</mat-icon></button><button class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Suppression non disponible" disabled><mat-icon>delete</mat-icon></button></td></tr>}@empty{<tr class="bea-ach__empty"><td colspan="4"><mat-icon>compare_arrows</mat-icon><p>Aucune comparaison.</p></td></tr>}</tbody></table></div></div>}@else{<header class="bea-ach__head"><div><p class="bea-ach__kicker">Comparaison</p><h1>Nouvelle comparaison</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/comparaisons"><mat-icon>arrow_back</mat-icon>Retour</a></header><form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()"><div class="bea-ach__grid"><label>Consultation<select formControlName="consultation_id">@for(c of consultations();track c.id){<option [value]="c.id">{{c.reference}} — {{c.objet}}</option>}</select></label><label>Motif du choix<input formControlName="motif_choix"/></label></div><div class="bea-ach__form-actions"><button class="bea-ach__btn"><mat-icon>save</mat-icon>Enregistrer</button></div></form>}</section>`,
})
export class AchatsComparaisonsComponent implements OnInit{
  private readonly api=inject(ApiService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);private readonly fb=inject(FormBuilder);readonly rows=signal<Comparaison[]>([]);readonly consultations=signal<Consultation[]>([]);readonly erreur=signal('');readonly mode=signal<'list'|'form'>('list');readonly q=signal('');readonly filters=this.fb.nonNullable.group({q:''});readonly form=this.fb.nonNullable.group({consultation_id:['',Validators.required],motif_choix:['']});readonly filtered=computed(()=>{const q=this.q().toLowerCase();return this.rows().filter(r=>!q||r.reference.toLowerCase().includes(q)||(r.motif_choix??'').toLowerCase().includes(q));});readonly active=computed(()=>this.rows().filter(r=>!['VALIDEE','CLOTUREE','ANNULEE'].includes(r.statut)).length);
  ngOnInit():void{this.api.get<Consultation[]>('/mg/achats/consultations').subscribe({next:r=>this.consultations.set(r)});const p=this.route.snapshot.paramMap.get('id');if(this.router.url.endsWith('/nouvelle')||p)this.mode.set('form');else this.api.get<Comparaison[]>('/mg/achats/comparaisons').subscribe({next:r=>this.rows.set(r),error:()=>this.erreur.set('Comparaisons indisponibles.')});}search():void{this.q.set(this.filters.controls.q.value.trim());}save():void{if(this.form.invalid)return;const v=this.form.getRawValue();this.api.post<Comparaison>('/mg/achats/comparaisons',{consultation_id:v.consultation_id,motif_choix:v.motif_choix||null}).subscribe({next:c=>void this.router.navigateByUrl(`/achats-appro/comparaisons/${c.id}`),error:()=>this.erreur.set('Enregistrement impossible.')});}
}

@Component({
 selector:'bea-achats-livraisons',changeDetection:ChangeDetectionStrategy.OnPush,imports:[ReactiveFormsModule,RouterLink,MatIconModule],
 template:`<section class="bea-ach">@if(mode()==='list'){<header class="bea-ach__hero"><p>Logistique</p><h1>Bons de livraison</h1><div class="bea-ach__hero-glow"></div></header><div class="bea-ach__head"><div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0"><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>local_shipping</mat-icon></span><span class="bea-ach__kpi-meta"><span>Total</span><strong>{{rows().length}}</strong><em>Bons de livraison</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending</mat-icon></span><span class="bea-ach__kpi-meta"><span>En cours</span><strong>{{active()}}</strong><em>À réceptionner</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>inventory</mat-icon></span><span class="bea-ach__kpi-meta"><span>Reçus</span><strong>{{rows().length-active()}}</strong><em>Livrés</em></span></div></div><a class="bea-ach__btn" routerLink="/achats-appro/livraisons/nouvelle"><mat-icon>add</mat-icon>Nouveau BL</a></div><form class="bea-ach__search" [formGroup]="filters"><label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence ou BC…" (input)="search()"/></label></form>@if(erreur()){<p class="bea-ach__error">{{erreur()}}</p>}<div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Livraisons</h2><span class="bea-ach__count">{{filtered().length}} résultat(s)</span></div><div style="overflow-x:auto"><table class="bea-ach__table"><thead><tr><th>Réf.</th><th>BC</th><th>Date</th><th>Statut</th><th class="bea-ach__th-actions">Actions</th></tr></thead><tbody>@for(r of filtered();track r.id;let i=$index){<tr [style.--i]="i"><td><code class="bea-ach__code">{{r.reference}}</code></td><td><code class="bea-ach__code">{{r.bon_id}}</code></td><td>{{r.date_bl}}</td><td><span class="bea-ach__badge" [attr.data-statut]="r.statut">{{r.statut}}</span></td><td class="bea-ach__actions"><a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/livraisons',r.id]"><mat-icon>visibility</mat-icon></a><a class="bea-ach__icon-btn" title="Éditer" [routerLink]="['/achats-appro/livraisons',r.id]"><mat-icon>edit</mat-icon></a><button class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactivation non disponible" disabled><mat-icon>block</mat-icon></button><button class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Suppression non disponible" disabled><mat-icon>delete</mat-icon></button></td></tr>}@empty{<tr class="bea-ach__empty"><td colspan="5"><mat-icon>local_shipping</mat-icon><p>Aucun bon de livraison.</p></td></tr>}</tbody></table></div></div>}@else{<header class="bea-ach__head"><div><p class="bea-ach__kicker">Livraison</p><h1>Nouveau bon de livraison</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/livraisons"><mat-icon>arrow_back</mat-icon>Retour</a></header><form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()"><div class="bea-ach__grid"><label>Bon de commande<input formControlName="bon_id" placeholder="UUID du BC"/></label><label>Date BL<input type="date" formControlName="date_bl"/></label></div><div class="bea-ach__form-actions"><button class="bea-ach__btn"><mat-icon>save</mat-icon>Enregistrer</button></div></form>}</section>`,
})
export class AchatsLivraisonsComponent implements OnInit{
 private readonly api=inject(ApiService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);private readonly fb=inject(FormBuilder);readonly rows=signal<Bl[]>([]);readonly erreur=signal('');readonly mode=signal<'list'|'form'>('list');readonly q=signal('');readonly filters=this.fb.nonNullable.group({q:''});readonly form=this.fb.nonNullable.group({bon_id:['',Validators.required],date_bl:[new Date().toISOString().slice(0,10),Validators.required]});readonly filtered=computed(()=>{const q=this.q().toLowerCase();return this.rows().filter(r=>!q||r.reference.toLowerCase().includes(q)||r.bon_id.toLowerCase().includes(q));});readonly active=computed(()=>this.rows().filter(r=>!['RECU','COMPLETE','CLOTURE'].includes(r.statut)).length);
 ngOnInit():void{const p=this.route.snapshot.paramMap.get('id');if(this.router.url.endsWith('/nouvelle')||p)this.mode.set('form');else this.api.get<Bl[]>('/mg/achats/livraisons').subscribe({next:r=>this.rows.set(r),error:()=>this.erreur.set('Livraisons indisponibles.')});}search():void{this.q.set(this.filters.controls.q.value.trim());}save():void{if(this.form.invalid)return;this.api.post<Bl>('/mg/achats/livraisons',this.form.getRawValue()).subscribe({next:b=>void this.router.navigateByUrl(`/achats-appro/livraisons/${b.id}`),error:()=>this.erreur.set('Enregistrement impossible.')});}
}

@Component({
 selector:'bea-achats-receptions',changeDetection:ChangeDetectionStrategy.OnPush,imports:[ReactiveFormsModule,RouterLink,MatIconModule],
 template:`<section class="bea-ach">@if(mode()==='list'){<header class="bea-ach__hero"><p>Contrôle physique</p><h1>Réceptions</h1><div class="bea-ach__hero-glow"></div></header><div class="bea-ach__head"><div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0"><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>inventory_2</mat-icon></span><span class="bea-ach__kpi-meta"><span>Total</span><strong>{{rows().length}}</strong><em>Réceptions</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending</mat-icon></span><span class="bea-ach__kpi-meta"><span>Partielles</span><strong>{{partial()}}</strong><em>À compléter</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>task_alt</mat-icon></span><span class="bea-ach__kpi-meta"><span>Complètes</span><strong>{{rows().length-partial()}}</strong><em>Contrôlées</em></span></div></div><a class="bea-ach__btn" routerLink="/achats-appro/receptions/nouvelle"><mat-icon>add</mat-icon>Nouvelle</a></div><form class="bea-ach__search" [formGroup]="filters"><label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence ou BC…" (input)="search()"/></label></form>@if(erreur()){<p class="bea-ach__error">{{erreur()}}</p>}<div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Réceptions enregistrées</h2><span class="bea-ach__count">{{filtered().length}} résultat(s)</span></div><div style="overflow-x:auto"><table class="bea-ach__table"><thead><tr><th>Réf.</th><th>BC</th><th>Date</th><th>Statut</th><th class="bea-ach__th-actions">Actions</th></tr></thead><tbody>@for(r of filtered();track r.id;let i=$index){<tr [style.--i]="i"><td><code class="bea-ach__code">{{r.reference}}</code></td><td><code class="bea-ach__code">{{r.bon_id}}</code></td><td>{{r.date_reception}}</td><td><span class="bea-ach__badge" [attr.data-statut]="r.statut">{{r.statut}}</span></td><td class="bea-ach__actions"><a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/receptions',r.id]"><mat-icon>visibility</mat-icon></a><a class="bea-ach__icon-btn" title="Éditer" [routerLink]="['/achats-appro/receptions',r.id]"><mat-icon>edit</mat-icon></a><button class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactivation non disponible" disabled><mat-icon>block</mat-icon></button><button class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Suppression non disponible" disabled><mat-icon>delete</mat-icon></button></td></tr>}@empty{<tr class="bea-ach__empty"><td colspan="5"><mat-icon>inventory_2</mat-icon><p>Aucune réception.</p></td></tr>}</tbody></table></div></div>}@else{<header class="bea-ach__head"><div><p class="bea-ach__kicker">Réception</p><h1>Nouvelle réception</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/receptions"><mat-icon>arrow_back</mat-icon>Retour</a></header><form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()"><div class="bea-ach__grid"><label>BC<input formControlName="bon_id"/></label><label>Ligne BC<input formControlName="bc_ligne_id"/></label><label>Qté reçue<input type="number" formControlName="quantite_recue"/></label><label>Date<input type="date" formControlName="date_reception"/></label></div><div class="bea-ach__form-actions"><button class="bea-ach__btn"><mat-icon>inventory</mat-icon>Réceptionner</button></div></form>}</section>`,
})
export class AchatsReceptionsComponent implements OnInit{
 private readonly api=inject(ApiService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);private readonly fb=inject(FormBuilder);readonly rows=signal<Reception[]>([]);readonly erreur=signal('');readonly mode=signal<'list'|'form'>('list');readonly q=signal('');readonly filters=this.fb.nonNullable.group({q:''});readonly form=this.fb.nonNullable.group({bon_id:['',Validators.required],bc_ligne_id:['',Validators.required],quantite_recue:[1,Validators.required],date_reception:[new Date().toISOString().slice(0,10),Validators.required]});readonly filtered=computed(()=>{const q=this.q().toLowerCase();return this.rows().filter(r=>!q||r.reference.toLowerCase().includes(q)||r.bon_id.toLowerCase().includes(q));});readonly partial=computed(()=>this.rows().filter(r=>r.statut==='PARTIEL').length);
 ngOnInit():void{const p=this.route.snapshot.paramMap.get('id');if(this.router.url.endsWith('/nouvelle')||p)this.mode.set('form');else this.api.get<Reception[]>('/mg/achats/receptions').subscribe({next:r=>this.rows.set(r),error:()=>this.erreur.set('Réceptions indisponibles.')});}search():void{this.q.set(this.filters.controls.q.value.trim());}save():void{if(this.form.invalid)return;const v=this.form.getRawValue();this.api.post<Reception>('/mg/achats/receptions',{bon_id:v.bon_id,date_reception:v.date_reception,lignes:[{bc_ligne_id:v.bc_ligne_id,quantite_recue:v.quantite_recue}]}).subscribe({next:r=>void this.router.navigateByUrl(`/achats-appro/receptions/${r.id}`),error:()=>this.erreur.set('Réception refusée.')});}
}

@Component({
 selector:'bea-achats-factures',changeDetection:ChangeDetectionStrategy.OnPush,imports:[ReactiveFormsModule,RouterLink,DecimalPipe,MgGedPanelComponent,MatIconModule],
 template:`<section class="bea-ach">@if(mode()==='list'){<header class="bea-ach__hero"><p>Contrôle fournisseur</p><h1>Factures</h1><div class="bea-ach__hero-glow"></div></header><div class="bea-ach__head"><div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0"><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>request_quote</mat-icon></span><span class="bea-ach__kpi-meta"><span>Total</span><strong>{{rows().length}}</strong><em>Factures</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>payments</mat-icon></span><span class="bea-ach__kpi-meta"><span>Montant TTC</span><strong>{{total()|number:'1.0-0'}}</strong><em>MRU</em></span></div><div class="bea-ach__kpi" [attr.data-active]="ecarts()>0?'danger':null"><span class="bea-ach__kpi-icon" data-tone="danger"><mat-icon>warning</mat-icon></span><span class="bea-ach__kpi-meta"><span>Écarts 3WM</span><strong>{{ecarts()}}</strong><em>À régulariser</em></span></div></div><a class="bea-ach__btn" routerLink="/achats-appro/factures/nouvelle"><mat-icon>add</mat-icon>Nouvelle</a></div><form class="bea-ach__search" [formGroup]="filters"><label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence ou BC…" (input)="search()"/></label></form>@if(erreur()){<p class="bea-ach__error">{{erreur()}}</p>}<div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Factures fournisseurs</h2><span class="bea-ach__count">{{filtered().length}} résultat(s)</span></div><div style="overflow-x:auto"><table class="bea-ach__table"><thead><tr><th>Réf.</th><th>Date</th><th>TTC</th><th>Statut</th><th>3WM</th><th class="bea-ach__th-actions">Actions</th></tr></thead><tbody>@for(r of filtered();track r.id;let i=$index){<tr [style.--i]="i"><td><code class="bea-ach__code">{{r.reference}}</code></td><td>{{r.date_facture}}</td><td>{{r.montant_ttc|number:'1.2-2'}} MRU</td><td><span class="bea-ach__badge" [attr.data-statut]="r.statut">{{r.statut}}</span></td><td><span class="bea-ach__badge" [attr.data-statut]="r.ecart_quantite||r.ecart_montant?'ANOMALIE':'VALIDE'">{{r.ecart_quantite||r.ecart_montant?'Écart':'Conforme'}}</span></td><td class="bea-ach__actions"><a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/factures',r.id]"><mat-icon>visibility</mat-icon></a><a class="bea-ach__icon-btn" title="Éditer" [routerLink]="['/achats-appro/factures',r.id]"><mat-icon>edit</mat-icon></a><button class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactivation non disponible" disabled><mat-icon>block</mat-icon></button><button class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Suppression non disponible" disabled><mat-icon>delete</mat-icon></button></td></tr>}@empty{<tr class="bea-ach__empty"><td colspan="6"><mat-icon>request_quote</mat-icon><p>Aucune facture.</p></td></tr>}</tbody></table></div></div>}@else{<header class="bea-ach__head"><div><p class="bea-ach__kicker">Facture</p><h1>{{id()?'Fiche facture':'Nouvelle facture'}}</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/factures"><mat-icon>arrow_back</mat-icon>Retour</a></header>@if(erreur()){<p class="bea-ach__error">{{erreur()}}</p>}<form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()"><div class="bea-ach__grid"><label>Fournisseur<select formControlName="fournisseur_id">@for(f of fournisseurs();track f.id){<option [value]="f.id">{{f.raison_sociale}}</option>}</select></label><label>BC<input formControlName="bon_id"/></label><label>Date<input type="date" formControlName="date_facture"/></label><label>Désignation<input formControlName="designation"/></label><label>Qté<input type="number" formControlName="quantite"/></label><label>PU<input type="number" formControlName="prix_unitaire"/></label></div><div class="bea-ach__form-actions"><button class="bea-ach__btn"><mat-icon>save</mat-icon>Enregistrer</button>@if(id()){<button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="match()"><mat-icon>fact_check</mat-icon>Contrôle 3 voies</button>}</div>@if(matchResult()){<p class="bea-ach__ok">{{matchResult()}}</p>}</form>@if(id()){<bea-mg-ged moduleCode="achats-appro" entity="achat_facture" [entityId]="id()!"/>}}</section>`,
})
export class AchatsFacturesComponent implements OnInit{
 private readonly api=inject(ApiService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);private readonly fb=inject(FormBuilder);readonly rows=signal<Facture[]>([]);readonly fournisseurs=signal<Fournisseur[]>([]);readonly erreur=signal('');readonly mode=signal<'list'|'form'>('list');readonly id=signal<string|null>(null);readonly matchResult=signal('');readonly q=signal('');readonly filters=this.fb.nonNullable.group({q:''});readonly form=this.fb.nonNullable.group({fournisseur_id:['',Validators.required],bon_id:['',Validators.required],date_facture:[new Date().toISOString().slice(0,10),Validators.required],designation:['',Validators.required],quantite:[1,Validators.required],prix_unitaire:[0,Validators.required]});readonly filtered=computed(()=>{const q=this.q().toLowerCase();return this.rows().filter(r=>!q||r.reference.toLowerCase().includes(q)||r.bon_id.toLowerCase().includes(q));});readonly total=computed(()=>this.rows().reduce((n,r)=>n+r.montant_ttc,0));readonly ecarts=computed(()=>this.rows().filter(r=>r.ecart_quantite||r.ecart_montant).length);
 ngOnInit():void{this.api.get<Fournisseur[]>('/mg/achats/fournisseurs').subscribe({next:r=>this.fournisseurs.set(r)});const p=this.route.snapshot.paramMap.get('id');if(this.router.url.endsWith('/nouvelle')||p){this.mode.set('form');this.id.set(p);}else this.api.get<Facture[]>('/mg/achats/factures').subscribe({next:r=>this.rows.set(r),error:()=>this.erreur.set('Factures indisponibles.')});}search():void{this.q.set(this.filters.controls.q.value.trim());}save():void{if(this.form.invalid)return;const v=this.form.getRawValue();this.api.post<Facture>('/mg/achats/factures',{fournisseur_id:v.fournisseur_id,bon_id:v.bon_id,date_facture:v.date_facture,lignes:[{designation:v.designation,quantite:v.quantite,prix_unitaire:v.prix_unitaire}]}).subscribe({next:f=>void this.router.navigateByUrl(`/achats-appro/factures/${f.id}`),error:()=>this.erreur.set('Enregistrement impossible.')});}match():void{const id=this.id();if(!id)return;this.api.post<{resultat:string;detail:string|null}>(`/mg/achats/factures/${id}/match`,{}).subscribe({next:r=>this.matchResult.set(`${r.resultat}${r.detail?' — '+r.detail:''}`),error:()=>this.erreur.set('Contrôle impossible.')});}
}

@Component({
 selector:'bea-achats-paiements',changeDetection:ChangeDetectionStrategy.OnPush,imports:[ReactiveFormsModule,RouterLink,DecimalPipe,MatIconModule],
 template:`<section class="bea-ach">@if(mode()==='list'){<header class="bea-ach__hero"><p>Trésorerie</p><h1>Suivi des paiements</h1><div class="bea-ach__hero-glow"></div></header><p class="bea-ach__note">Suivi interne uniquement. Aucun virement ni écriture comptable n'est émis.</p><div class="bea-ach__head"><div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0"><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>payments</mat-icon></span><span class="bea-ach__kpi-meta"><span>Total suivi</span><strong>{{total()|number:'1.0-0'}}</strong><em>MRU</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>schedule</mat-icon></span><span class="bea-ach__kpi-meta"><span>À payer</span><strong>{{pending()}}</strong><em>Échéances ouvertes</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>task_alt</mat-icon></span><span class="bea-ach__kpi-meta"><span>Payés</span><strong>{{rows().length-pending()}}</strong><em>Soldés</em></span></div></div><a class="bea-ach__btn" routerLink="/achats-appro/paiements/nouveau"><mat-icon>add</mat-icon>Nouveau suivi</a></div><form class="bea-ach__search" [formGroup]="filters"><label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence ou facture…" (input)="search()"/></label></form>@if(erreur()){<p class="bea-ach__error">{{erreur()}}</p>}<div class="bea-ach__panel"><div class="bea-ach__panel-top"><h2>Échéancier interne</h2><span class="bea-ach__count">{{filtered().length}} résultat(s)</span></div><div style="overflow-x:auto"><table class="bea-ach__table"><thead><tr><th>Réf.</th><th>Montant</th><th>Échéance</th><th>Statut</th><th class="bea-ach__th-actions">Actions</th></tr></thead><tbody>@for(r of filtered();track r.id;let i=$index){<tr [style.--i]="i"><td><code class="bea-ach__code">{{r.reference}}</code></td><td>{{r.montant|number:'1.2-2'}} MRU</td><td>{{r.date_echeance||'—'}}</td><td><span class="bea-ach__badge" [attr.data-statut]="r.statut">{{r.statut}}</span></td><td class="bea-ach__actions"><a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/paiements',r.id]"><mat-icon>visibility</mat-icon></a><a class="bea-ach__icon-btn" title="Éditer" [routerLink]="['/achats-appro/paiements',r.id]"><mat-icon>edit</mat-icon></a><button class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactivation non disponible" disabled><mat-icon>block</mat-icon></button><button class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Suppression non disponible" disabled><mat-icon>delete</mat-icon></button></td></tr>}@empty{<tr class="bea-ach__empty"><td colspan="5"><mat-icon>payments</mat-icon><p>Aucun paiement.</p></td></tr>}</tbody></table></div></div>}@else{<header class="bea-ach__head"><div><p class="bea-ach__kicker">Paiement</p><h1>Nouveau suivi</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/paiements"><mat-icon>arrow_back</mat-icon>Retour</a></header><p class="bea-ach__note">Ce formulaire alimente uniquement le suivi interne.</p><form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()"><div class="bea-ach__grid"><label>Facture<input formControlName="facture_id"/></label><label>Montant<input type="number" formControlName="montant"/></label><label>Échéance<input type="date" formControlName="date_echeance"/></label></div><div class="bea-ach__form-actions"><button class="bea-ach__btn"><mat-icon>save</mat-icon>Enregistrer</button></div></form>}</section>`,
})
export class AchatsPaiementsComponent implements OnInit{
 private readonly api=inject(ApiService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);private readonly fb=inject(FormBuilder);readonly rows=signal<Paiement[]>([]);readonly erreur=signal('');readonly mode=signal<'list'|'form'>('list');readonly q=signal('');readonly filters=this.fb.nonNullable.group({q:''});readonly form=this.fb.nonNullable.group({facture_id:['',Validators.required],montant:[0,Validators.required],date_echeance:['']});readonly filtered=computed(()=>{const q=this.q().toLowerCase();return this.rows().filter(r=>!q||r.reference.toLowerCase().includes(q)||r.facture_id.toLowerCase().includes(q));});readonly total=computed(()=>this.rows().reduce((n,r)=>n+r.montant,0));readonly pending=computed(()=>this.rows().filter(r=>r.statut!=='PAYE').length);
 ngOnInit():void{const p=this.route.snapshot.paramMap.get('id');if(this.router.url.endsWith('/nouveau')||p)this.mode.set('form');else this.api.get<Paiement[]>('/mg/achats/paiements').subscribe({next:r=>this.rows.set(r),error:()=>this.erreur.set('Paiements indisponibles.')});}search():void{this.q.set(this.filters.controls.q.value.trim());}save():void{if(this.form.invalid)return;const v=this.form.getRawValue();this.api.post<Paiement>('/mg/achats/paiements',{facture_id:v.facture_id,montant:v.montant,date_echeance:v.date_echeance||null}).subscribe({next:p=>void this.router.navigateByUrl(`/achats-appro/paiements/${p.id}`),error:()=>this.erreur.set('Enregistrement impossible.')});}
}

@Component({
 selector:'bea-achats-rapports',changeDetection:ChangeDetectionStrategy.OnPush,imports:[DecimalPipe,MatIconModule],
 template:`<section class="bea-ach"><header class="bea-ach__hero"><p>Pilotage</p><h1>Rapports achats</h1><div class="bea-ach__hero-glow"></div></header>@if(erreur()){<p class="bea-ach__error">{{erreur()}}</p>}<div class="bea-ach__head"><div class="bea-ach__kpis bea-ach__kpis--3" style="flex:1;margin:0"><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>assignment</mat-icon></span><span class="bea-ach__kpi-meta"><span>Demandes</span><strong>{{r()?.nb_demandes??0}}</strong><em>Enregistrées</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="blue"><mat-icon>receipt_long</mat-icon></span><span class="bea-ach__kpi-meta"><span>Bons</span><strong>{{r()?.nb_bons??0}}</strong><em>{{r()?.montant_bons??0|number:'1.0-0'}} MRU</em></span></div><div class="bea-ach__kpi"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>inventory</mat-icon></span><span class="bea-ach__kpi-meta"><span>Réceptions</span><strong>{{r()?.nb_receptions??0}}</strong><em>Enregistrées</em></span></div></div><button class="bea-ach__btn" type="button" (click)="exportBons()"><mat-icon>download</mat-icon>Exporter les BC</button></div><div class="bea-ach__money"><div class="bea-ach__money-card"><span>Factures ({{r()?.nb_factures??0}})</span><strong>{{r()?.montant_factures??0|number:'1.2-2'}} MRU</strong></div><div class="bea-ach__money-card"><span>Paiements suivis</span><strong>{{r()?.montant_paiements??0|number:'1.2-2'}} MRU</strong></div></div></section>`,
})
export class AchatsRapportsComponent implements OnInit{
 private readonly api=inject(ApiService);readonly r=signal<Rapport|null>(null);readonly erreur=signal('');ngOnInit():void{this.api.get<Rapport>('/mg/achats/rapports/summary').subscribe({next:r=>this.r.set(r),error:()=>this.erreur.set('Rapport indisponible.')});}exportBons():void{this.api.download('/mg/achats/bons/export').subscribe({next:blob=>{const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='bons-commande.csv';a.click();URL.revokeObjectURL(url);},error:()=>this.erreur.set('Export impossible.')});}
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

