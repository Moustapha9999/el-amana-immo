import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable } from 'rxjs';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { QuantitePipe } from '../shared/montant.pipe';
import { PaginationComponent } from '../shared/pagination.component';
import { aPermission, downloadBlob } from './inventaire/inventaire.model';
import { StockAlertesWatcherService } from './stock-alertes-watcher.service';

export type AlerteStatut = 'NOUVELLE' | 'EN_COURS' | 'RESOLUE' | 'CLOTUREE';
export type AlerteType = 'STOCK_FAIBLE' | 'RUPTURE';

export interface AlerteSuivi {
  id: string;
  reference: string;
  article_id: string;
  article_code: string | null;
  article_reference: string | null;
  article_designation: string | null;
  famille_libelle: string | null;
  agence_libelle: string | null;
  emplacement: string | null;
  uom: string | null;
  type_alerte: AlerteType;
  type_libelle: string;
  statut: AlerteStatut;
  statut_libelle: string;
  origine: string;
  seuil: number;
  quantite_detection: number;
  quantite_actuelle: number;
  stock_actuel: number | null;
  detectee_at: string;
  rupture_at: string | null;
  retour_normal_at: string | null;
  quantite_retour: number | null;
  episode_ouvert: boolean;
  mouvement_reference: string | null;
  responsable_id: string | null;
  responsable_nom: string | null;
  commentaire: string | null;
  traite_par_nom: string | null;
  traite_at: string | null;
  deleted_at: string | null;
  deleted_by_nom: string | null;
  motif_suppression: string | null;
}

interface AlerteHistorique {
  action: string;
  user_nom: string | null;
  created_at: string;
}

interface AlerteDetail extends AlerteSuivi {
  historique: AlerteHistorique[];
}

interface Kpis {
  seuil: number;
  alertes_actives: boolean;
  articles_stock_faible: number;
  articles_rupture: number;
  alertes_non_traitees: number;
  alertes_en_cours: number;
  alertes_resolues: number;
  alertes_cloturees: number;
}

interface SuiviList {
  items: AlerteSuivi[];
  total: number;
  page: number;
  size: number;
  kpis: Kpis;
}

interface Option {
  id: string;
  libelle: string;
}

interface Responsable {
  id: string;
  nom: string;
}

interface Controle {
  articles: number;
  ouvertes: number;
  ruptures: number;
  retours: number;
}

export const STATUTS: { code: AlerteStatut; libelle: string }[] = [
  { code: 'NOUVELLE', libelle: 'Nouvelle' },
  { code: 'EN_COURS', libelle: 'En cours' },
  { code: 'RESOLUE', libelle: 'Résolue' },
  { code: 'CLOTUREE', libelle: 'Clôturée' },
];

/** Transitions proposées (le backend reste seul juge, y compris « Résolue » tant que le stock est bas). */
export const TRANSITIONS: Record<AlerteStatut, AlerteStatut[]> = {
  NOUVELLE: ['EN_COURS', 'RESOLUE', 'CLOTUREE'],
  EN_COURS: ['RESOLUE', 'CLOTUREE'],
  RESOLUE: ['EN_COURS', 'CLOTUREE'],
  CLOTUREE: ['EN_COURS'],
};

const ACTIONS: Record<string, string> = {
  alerte_detectee: 'Alerte détectée',
  alerte_retour_normal: 'Retour au-dessus du seuil',
  update: 'Suivi modifié',
  delete: 'Alerte supprimée',
};

export function statutsPossibles(a: Pick<AlerteSuivi, 'statut' | 'episode_ouvert'>): AlerteStatut[] {
  return TRANSITIONS[a.statut].filter((s) => !(s === 'RESOLUE' && a.episode_ouvert));
}

@Component({
  selector: 'bea-stock-alertes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, QuantitePipe, DatePipe, MatIconModule, ReactiveFormsModule, PaginationComponent],
  template: `
    <section class="bea-mg bea-stock-alertes">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Alertes</p>
          <h1>Alertes stock</h1>
          <p class="bea-stock-alertes__lead">
            Une alerte est créée quand le stock disponible d’un article passe à
            <strong>{{ kpis()?.seuil ?? 5 | quantite }}</strong> unité(s) ou moins, à partir des mouvements validés.
          </p>
        </div>
        <div class="bea-mg__actions">
          @if (peutGerer()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="lancerControle()">
              <mat-icon>rule</mat-icon> Lancer le contrôle
            </button>
          }
          @if (peutExporter()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
              <mat-icon>table_view</mat-icon> Excel
            </button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" title="PDF">
              <mat-icon>picture_as_pdf</mat-icon> PDF
            </button>
          }
        </div>
      </header>

      @if (kpis(); as k) {
        @if (!k.alertes_actives) {
          <p class="bea-alert-view__msg" data-niveau="warn">
            <mat-icon>notifications_off</mat-icon>
            <span>Les alertes stock bas sont désactivées (paramètre « alerte_seuil_actif »).</span>
          </p>
        }
        <div class="bea-stock-kpis">
          <article data-tone="warn">
            <span>Articles en stock faible</span>
            <strong>{{ k.articles_stock_faible }}</strong>
          </article>
          <article data-tone="danger">
            <span>Articles en rupture</span>
            <strong>{{ k.articles_rupture }}</strong>
          </article>
          <article [attr.data-tone]="k.alertes_non_traitees ? 'danger' : null">
            <span>Alertes non traitées</span>
            <strong>{{ k.alertes_non_traitees }}</strong>
          </article>
          <article>
            <span>Alertes en cours</span>
            <strong>{{ k.alertes_en_cours }}</strong>
          </article>
        </div>
      }

      <div class="bea-alert-live">
        <span class="bea-alert-live__dot" aria-hidden="true"></span>
        <p>
          <strong>Surveillance active.</strong>
          Les nouvelles alertes s’affichent en pop-up sur tous les onglets du module.
        </p>
        @switch (watcher.notificationsNavigateur()) {
          @case ('granted') {
            <span class="bea-alert-live__state"><mat-icon>notifications_active</mat-icon> Notifications Windows activées</span>
          }
          @case ('denied') {
            <span class="bea-alert-live__state bea-alert-live__state--off">
              <mat-icon>notifications_off</mat-icon> Notifications bloquées par le navigateur
            </span>
          }
          @case ('default') {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="watcher.demanderNotificationsNavigateur()">
              <mat-icon>notifications</mat-icon> Activer les notifications Windows
            </button>
          }
        }
      </div>

      <form class="bea-mg__search bea-stock-alertes__filtres" [formGroup]="filters" (ngSubmit)="goToPage(1)">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Référence alerte, code ou désignation article…" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>flag</mat-icon>
          <select formControlName="statut" (change)="goToPage(1)" aria-label="Statut">
            <option value="">Tous statuts</option>
            @for (s of statuts; track s.code) {
              <option [value]="s.code">{{ s.libelle }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>warning</mat-icon>
          <select formControlName="type_alerte" (change)="goToPage(1)" aria-label="Type d’alerte">
            <option value="">Tous types</option>
            <option value="STOCK_FAIBLE">Stock faible</option>
            <option value="RUPTURE">Rupture de stock</option>
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>store</mat-icon>
          <select formControlName="agence_id" (change)="goToPage(1)" aria-label="Agence">
            <option value="">Toutes agences</option>
            @for (a of agences(); track a.id) {
              <option [value]="a.id">{{ a.libelle }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>category</mat-icon>
          <select formControlName="famille_id" (change)="goToPage(1)" aria-label="Famille">
            <option value="">Toutes familles</option>
            @for (f of familles(); track f.id) {
              <option [value]="f.id">{{ f.libelle }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <span class="bea-stock-alertes__lbl">Du</span>
          <input type="date" formControlName="date_debut" (change)="goToPage(1)" aria-label="Détectées à partir du" />
        </label>
        <label class="bea-mg__field">
          <span class="bea-stock-alertes__lbl">Au</span>
          <input type="date" formControlName="date_fin" (change)="goToPage(1)" aria-label="Détectées jusqu’au" />
        </label>
        @if (peutSupprimer()) {
          <label class="bea-stock-alertes__check">
            <input type="checkbox" formControlName="supprimees" (change)="goToPage(1)" />
            Alertes supprimées
          </label>
        }
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary"><mat-icon>filter_alt</mat-icon> Filtrer</button>
      </form>

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Suivi des alertes</h2>
          <span class="bea-mg__count">{{ total() }} alerte(s)</span>
          @if (peutSupprimer() && selection().size && !voirSupprimees()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--danger" [disabled]="busy()" (click)="supprimerSelection()">
              <mat-icon>delete</mat-icon> Supprimer la sélection ({{ selection().size }})
            </button>
          }
        </div>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr>
                @if (peutSupprimer() && !voirSupprimees()) {
                  <th class="bea-stock-alertes__sel">
                    <input type="checkbox" [checked]="toutSelectionne()" (change)="toutSelectionner($any($event.target).checked)" aria-label="Tout sélectionner" />
                  </th>
                }
                <th>Alerte</th>
                <th>Article</th>
                <th>Agence / emplacement</th>
                <th>Type</th>
                <th>Disponible</th>
                <th>Seuil</th>
                <th>Détectée le</th>
                <th>Statut</th>
                <th>Responsable</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @if (chargement()) {
                <tr><td colspan="11" class="bea-mg__empty"><p>Chargement…</p></td></tr>
              } @else if (erreurChargement()) {
                <tr>
                  <td colspan="11" class="bea-mg__empty">
                    <mat-icon>error_outline</mat-icon>
                    <p>{{ erreurChargement() }}</p>
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="load()">Réessayer</button>
                  </td>
                </tr>
              } @else {
                @for (a of items(); track a.id) {
                  <tr [class.bea-stock-alertes__row--sel]="selection().has(a.id)">
                    @if (peutSupprimer() && !voirSupprimees()) {
                      <td class="bea-stock-alertes__sel">
                        <input type="checkbox" [checked]="selection().has(a.id)" (change)="basculer(a.id)" [attr.aria-label]="'Sélectionner ' + a.reference" />
                      </td>
                    }
                    <td><code class="bea-mg__code">{{ a.reference }}</code></td>
                    <td>
                      <a class="app-link" [routerLink]="['/stock-fournitures/articles', a.article_id]" title="Ouvrir la fiche article">
                        <code class="bea-mg__code">{{ a.article_code }}</code> {{ a.article_designation }}
                      </a>
                    </td>
                    <td>{{ a.agence_libelle }}@if (a.emplacement) { · {{ a.emplacement }} }</td>
                    <td>
                      <span class="bea-stock-badge" [attr.data-niveau]="a.type_alerte === 'RUPTURE' ? 'epuise' : 'faible'">{{ a.type_libelle }}</span>
                    </td>
                    <td>{{ a.quantite_actuelle | quantite }} {{ a.uom }}</td>
                    <td>{{ a.seuil | quantite }}</td>
                    <td>{{ a.detectee_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    <td>
                      <span class="bea-stock-alertes__statut" [attr.data-statut]="a.statut">{{ a.statut_libelle }}</span>
                      @if (!a.episode_ouvert) {
                        <small class="bea-stock-alertes__retour">stock rétabli</small>
                      }
                    </td>
                    <td>{{ a.responsable_nom || '—' }}</td>
                    <td class="bea-mg__actions-cell">
                      <button type="button" class="bea-mg__icon-btn" title="Détail et suivi" (click)="ouvrir(a.id)">
                        <mat-icon>visibility</mat-icon>
                      </button>
                      @if (peutSupprimer() && !a.deleted_at) {
                        <button type="button" class="bea-mg__icon-btn" title="Supprimer l’alerte" [disabled]="busy()" (click)="supprimer([a])">
                          <mat-icon>delete</mat-icon>
                        </button>
                      }
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="11" class="bea-mg__empty">
                      <mat-icon>check_circle</mat-icon>
                      <p>Aucune alerte pour les critères actuels.</p>
                    </td>
                  </tr>
                }
              }
            </tbody>
          </table>
        </div>
        @if (total() > 0) {
          <app-pagination [page]="page()" [total]="total()" [pageSize]="pageSize" label="alerte(s)" (pageChange)="goToPage($event)" />
        }
      </div>

      @if (detail(); as d) {
        <div class="bea-mg__backdrop" (click)="fermer()" role="presentation"></div>
        <div class="bea-mg__modal bea-stock-view" role="dialog" aria-modal="true" [attr.aria-label]="'Alerte ' + d.reference">
          <header class="bea-mg__modal-head">
            <div class="bea-stock-view__head">
              <span class="bea-stock-view__avatar bea-alert-view__avatar" [attr.data-niveau]="d.type_alerte === 'RUPTURE' ? 'epuise' : 'faible'">
                <mat-icon>{{ d.type_alerte === 'RUPTURE' ? 'error' : 'warning' }}</mat-icon>
              </span>
              <div>
                <p class="bea-stock-page__kicker">{{ d.reference }} · {{ d.type_libelle }} · {{ d.statut_libelle }}</p>
                <h2>{{ d.article_designation }}</h2>
              </div>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="fermer()" title="Fermer"><mat-icon>close</mat-icon></button>
          </header>
          <div class="bea-mg__modal-body bea-stock-view__body">
            <div class="bea-stock-view__kpis">
              <div class="bea-stock-view__kpi bea-stock-view__kpi--main" [attr.data-niveau]="d.type_alerte === 'RUPTURE' ? 'epuise' : 'faible'">
                <span>Disponible</span>
                <strong>{{ d.quantite_actuelle | quantite }} <small>{{ d.uom }}</small></strong>
              </div>
              <div class="bea-stock-view__kpi">
                <span>Seuil</span>
                <strong>{{ d.seuil | quantite }}</strong>
              </div>
              <div class="bea-stock-view__kpi">
                <span>À la détection</span>
                <strong>{{ d.quantite_detection | quantite }}</strong>
              </div>
            </div>
            <dl class="bea-stock-alertes__dl">
              <div><dt>Article</dt><dd><a class="app-link" [routerLink]="['/stock-fournitures/articles', d.article_id]" (click)="fermer()">{{ d.article_code }}{{ d.article_reference ? ' · ' + d.article_reference : '' }}</a></dd></div>
              <div><dt>Agence / emplacement</dt><dd>{{ d.agence_libelle }}{{ d.emplacement ? ' · ' + d.emplacement : '' }}</dd></div>
              <div><dt>Famille</dt><dd>{{ d.famille_libelle || '—' }}</dd></div>
              <div><dt>Détectée le</dt><dd>{{ d.detectee_at | date: 'dd/MM/yyyy HH:mm' }} ({{ d.origine === 'CONTROLE' ? 'contrôle' : 'mouvement ' + (d.mouvement_reference || '') }})</dd></div>
              @if (d.rupture_at) {
                <div><dt>Rupture le</dt><dd>{{ d.rupture_at | date: 'dd/MM/yyyy HH:mm' }}</dd></div>
              }
              @if (d.retour_normal_at) {
                <div><dt>Retour au-dessus du seuil</dt><dd>{{ d.retour_normal_at | date: 'dd/MM/yyyy HH:mm' }} ({{ d.quantite_retour | quantite }})</dd></div>
              }
              @if (d.traite_par_nom) {
                <div><dt>Dernier traitement</dt><dd>{{ d.traite_par_nom }} · {{ d.traite_at | date: 'dd/MM/yyyy HH:mm' }}</dd></div>
              }
              @if (d.deleted_at) {
                <div><dt>Supprimée</dt><dd>{{ d.deleted_by_nom }} · {{ d.deleted_at | date: 'dd/MM/yyyy HH:mm' }} — {{ d.motif_suppression }}</dd></div>
              }
            </dl>

            @if (peutGerer() && !d.deleted_at) {
              <form class="bea-mg__grid bea-stock-alertes__suivi" [formGroup]="suivi" (ngSubmit)="enregistrer(d)">
                <label>
                  Statut
                  <select formControlName="statut">
                    <option [value]="d.statut">{{ d.statut_libelle }}</option>
                    @for (s of possibles(d); track s) {
                      <option [value]="s">{{ libelleStatut(s) }}</option>
                    }
                  </select>
                </label>
                <label>
                  Responsable
                  <select formControlName="responsable_id">
                    <option value="">— Aucun —</option>
                    @for (r of responsables(); track r.id) {
                      <option [value]="r.id">{{ r.nom }}</option>
                    }
                  </select>
                </label>
                <label class="bea-mg__span2">
                  Commentaire
                  <textarea formControlName="commentaire" rows="3" maxlength="2000" placeholder="Action prévue, commande en cours…"></textarea>
                </label>
                @if (d.episode_ouvert) {
                  <p class="bea-mg__span2 bea-stock-alertes__hint">
                    <mat-icon>info</mat-icon>
                    L’alerte passera « Résolue » automatiquement quand le stock repassera au-dessus du seuil.
                  </p>
                }
              </form>
            } @else {
              <dl class="bea-stock-alertes__dl">
                <div><dt>Responsable</dt><dd>{{ d.responsable_nom || '—' }}</dd></div>
                <div><dt>Commentaire</dt><dd>{{ d.commentaire || '—' }}</dd></div>
              </dl>
            }

            <h3 class="bea-stock-alertes__h3">Historique</h3>
            <ol class="bea-stock-alertes__histo">
              @for (h of d.historique; track $index) {
                <li>
                  <strong>{{ actionLabel(h.action) }}</strong>
                  <span>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }} · {{ h.user_nom || 'Système' }}</span>
                </li>
              } @empty {
                <li>Aucun événement.</li>
              }
            </ol>
          </div>
          <footer class="bea-mg__modal-foot bea-stock-view__foot">
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/entrees" (click)="fermer()">
              <mat-icon>south_west</mat-icon> Saisir une entrée
            </a>
            @if (peutSupprimer() && !d.deleted_at) {
              <button type="button" class="bea-mg__btn bea-mg__btn--danger" [disabled]="busy()" (click)="supprimer([d])">
                <mat-icon>delete</mat-icon> Supprimer
              </button>
            }
            @if (peutGerer() && !d.deleted_at) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || suivi.pristine" (click)="enregistrer(d)">
                <mat-icon>save</mat-icon> Enregistrer le suivi
              </button>
            } @else {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="fermer()">Fermer</button>
            }
          </footer>
        </div>
      }
    </section>
  `,
  styles: [
    `
      .bea-stock-alertes__lead { margin: 0.25rem 0 0; color: #64748b; font-size: 0.85rem; }
      .bea-stock-alertes__filtres { flex-wrap: wrap; }
      .bea-stock-alertes__lbl { font-size: 0.75rem; color: #64748b; }
      .bea-stock-alertes__check { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.85rem; }
      .bea-stock-alertes__sel { width: 2rem; text-align: center; }
      .bea-stock-alertes__row--sel { background: rgba(37, 99, 235, 0.06); }
      .bea-stock-alertes__statut { display: inline-block; padding: 0.1rem 0.55rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; background: #e2e8f0; color: #334155; }
      .bea-stock-alertes__statut[data-statut='NOUVELLE'] { background: #fee2e2; color: #b91c1c; }
      .bea-stock-alertes__statut[data-statut='EN_COURS'] { background: #fef3c7; color: #b45309; }
      .bea-stock-alertes__statut[data-statut='RESOLUE'] { background: #dcfce7; color: #166534; }
      .bea-stock-alertes__retour { display: block; color: #166534; font-size: 0.7rem; }
      .bea-stock-alertes__dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 0.6rem 1rem; margin: 1rem 0; }
      .bea-stock-alertes__dl dt { font-size: 0.72rem; color: #64748b; }
      .bea-stock-alertes__dl dd { margin: 0; }
      .bea-stock-alertes__suivi { margin-top: 0.5rem; }
      .bea-stock-alertes__suivi textarea { width: 100%; box-sizing: border-box; }
      .bea-stock-alertes__hint { display: flex; gap: 0.4rem; align-items: center; font-size: 0.8rem; color: #64748b; margin: 0; }
      .bea-stock-alertes__h3 { font-size: 0.9rem; margin: 1.1rem 0 0.4rem; }
      .bea-stock-alertes__histo { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.35rem; }
      .bea-stock-alertes__histo li { display: flex; flex-wrap: wrap; gap: 0.5rem; font-size: 0.82rem; border-left: 3px solid #cbd5e1; padding-left: 0.6rem; }
      .bea-stock-alertes__histo span { color: #64748b; }
      @media (max-width: 720px) {
        .bea-stock-alertes__filtres .bea-mg__field { flex: 1 1 100%; }
      }
    `,
  ],
})
export class StockAlertesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly watcher = inject(StockAlertesWatcherService);

  readonly statuts = STATUTS;
  readonly pageSize = 50;
  readonly page = signal(1);
  readonly total = signal(0);
  readonly items = signal<AlerteSuivi[]>([]);
  readonly kpis = signal<Kpis | null>(null);
  readonly chargement = signal(false);
  readonly erreurChargement = signal<string | null>(null);
  readonly busy = signal(false);
  readonly detail = signal<AlerteDetail | null>(null);
  readonly selection = signal<Set<string>>(new Set());
  readonly agences = signal<Option[]>([]);
  readonly familles = signal<Option[]>([]);
  readonly responsables = signal<Responsable[]>([]);

  readonly filters = this.fb.nonNullable.group({
    q: '',
    statut: '',
    type_alerte: '',
    agence_id: '',
    famille_id: '',
    date_debut: '',
    date_fin: '',
    supprimees: false,
  });
  readonly suivi = this.fb.nonNullable.group({ statut: '', responsable_id: '', commentaire: '' });

  readonly peutGerer = computed(() => aPermission(this.auth.user(), 'mg.stock.alert.manage'));
  readonly peutSupprimer = computed(() => aPermission(this.auth.user(), 'mg.stock.alert.delete'));
  readonly peutExporter = computed(() => aPermission(this.auth.user(), 'mg.stock.export'));
  readonly voirSupprimees = signal(false);
  readonly toutSelectionne = computed(() => {
    const ids = this.items().filter((a) => !a.deleted_at).map((a) => a.id);
    return ids.length > 0 && ids.every((id) => this.selection().has(id));
  });

  readonly hasUnsavedChanges = unsavedChanges(() => !!this.detail() && this.suivi.dirty);

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.detail()) this.fermer();
  }

  ngOnInit(): void {
    this.api.get<Option[]>('/mg/stock/agences').subscribe({ next: (a) => this.agences.set(a) });
    this.api.get<Option[]>('/mg/stock/familles').subscribe({ next: (f) => this.familles.set(f) });
    if (this.peutGerer()) {
      this.api.get<Responsable[]>('/mg/stock/alertes/suivi/responsables').subscribe({ next: (r) => this.responsables.set(r) });
    }
    this.load();
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((p) => {
      const id = p.get('alerte');
      if (id) this.ouvrir(id);
    });
  }

  private params(): Record<string, string> {
    const f = this.filters.getRawValue();
    const p: Record<string, string> = {};
    if (f.q.trim()) p['q'] = f.q.trim();
    for (const k of ['statut', 'type_alerte', 'agence_id', 'famille_id', 'date_debut', 'date_fin'] as const) {
      if (f[k]) p[k] = f[k];
    }
    if (f.supprimees && this.peutSupprimer()) p['supprimees'] = 'true';
    return p;
  }

  load(): void {
    this.chargement.set(true);
    this.erreurChargement.set(null);
    this.voirSupprimees.set(this.filters.getRawValue().supprimees && this.peutSupprimer());
    this.api
      .get<SuiviList>('/mg/stock/alertes/suivi', { ...this.params(), page: String(this.page()), size: String(this.pageSize) })
      .subscribe({
        next: (res) => {
          this.items.set(res.items);
          this.total.set(res.total);
          this.kpis.set(res.kpis);
          this.selection.set(new Set());
          this.chargement.set(false);
        },
        error: () => {
          this.chargement.set(false);
          this.erreurChargement.set('Impossible de charger les alertes. Vérifiez votre connexion puis réessayez.');
        },
      });
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  basculer(id: string): void {
    const s = new Set(this.selection());
    if (s.has(id)) s.delete(id);
    else s.add(id);
    this.selection.set(s);
  }

  toutSelectionner(oui: boolean): void {
    this.selection.set(oui ? new Set(this.items().filter((a) => !a.deleted_at).map((a) => a.id)) : new Set());
  }

  ouvrir(id: string): void {
    this.api.get<AlerteDetail>(`/mg/stock/alertes/suivi/${id}`).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.suivi.reset({ statut: d.statut, responsable_id: d.responsable_id ?? '', commentaire: d.commentaire ?? '' });
      },
      error: () => this.feedback.error({ title: 'Alerte introuvable', message: 'Elle a peut-être été supprimée.' }),
    });
  }

  fermer(): void {
    this.detail.set(null);
    this.suivi.reset();
    if (this.route.snapshot.queryParamMap.has('alerte')) {
      void this.router.navigate([], { relativeTo: this.route, queryParams: { alerte: null }, queryParamsHandling: 'merge' });
    }
  }

  possibles(d: AlerteSuivi): AlerteStatut[] {
    return statutsPossibles(d);
  }

  libelleStatut(s: AlerteStatut): string {
    return STATUTS.find((x) => x.code === s)?.libelle ?? s;
  }

  actionLabel(action: string): string {
    return ACTIONS[action] ?? action;
  }

  enregistrer(d: AlerteDetail): void {
    if (this.suivi.pristine) return;
    const v = this.suivi.getRawValue();
    const body: Record<string, unknown> = {};
    if (v.statut !== d.statut) body['statut'] = v.statut;
    if ((v.responsable_id || null) !== d.responsable_id) body['responsable_id'] = v.responsable_id || null;
    if ((v.commentaire.trim() || null) !== d.commentaire) body['commentaire'] = v.commentaire.trim() || null;
    this.feedback
      .run(() => this.api.patch<AlerteSuivi>(`/mg/stock/alertes/suivi/${d.id}`, body), {
        loading: 'Enregistrement…',
        busy: this.busy,
        errorTitle: 'Suivi non enregistré',
        success: (a) => ({
          title: 'Suivi de l’alerte enregistré',
          details: [
            { label: 'Alerte', value: a.reference },
            { label: 'Statut', value: a.statut_libelle },
          ],
        }),
      })
      .subscribe(() => {
        this.suivi.markAsPristine();
        this.ouvrir(d.id);
        this.load();
        this.watcher.refresh(true);
      });
  }

  supprimerSelection(): void {
    this.supprimer(this.items().filter((a) => this.selection().has(a.id)));
  }

  supprimer(alertes: AlerteSuivi[]): void {
    if (!alertes.length) return;
    const ids = alertes.map((a) => a.id);
    const une = alertes.length === 1;
    this.feedback
      .runWithReason((motif) => this.supprimerApi(ids, motif), {
        reason: {
          title: une ? `Supprimer l’alerte ${alertes[0].reference}` : `Supprimer ${alertes.length} alertes`,
          message: une
            ? `L’alerte sur ${alertes[0].article_code} sera retirée de la liste.`
            : `${alertes.length} alertes seront retirées de la liste.`,
          hint:
            'Le stock et les mouvements ne sont pas modifiés. Tant que le stock reste sous le seuil, aucune nouvelle alerte n’est recréée ; une nouvelle alerte sera émise au prochain franchissement.',
          reasonLabel: 'Motif (tracé dans l’audit)',
          reasonPlaceholder: 'Ex. : doublon, réapprovisionnement déjà commandé…',
          required: true,
          maxLength: 500,
          confirmLabel: 'Supprimer',
          tone: 'danger',
          icon: 'delete',
        },
        loading: 'Suppression…',
        busy: this.busy,
        errorTitle: 'Suppression refusée',
        success: (r) => ({ title: `${r.supprimees} alerte(s) supprimée(s)` }),
      })
      .subscribe(() => {
        if (this.detail() && ids.includes(this.detail()!.id)) this.fermer();
        this.load();
        this.watcher.refresh(true);
      });
  }

  private supprimerApi(ids: string[], motif: string): Observable<{ supprimees: number }> {
    if (ids.length === 1) {
      return this.api.delete<{ supprimees: number }>(
        `/mg/stock/alertes/suivi/${ids[0]}?motif=${encodeURIComponent(motif)}`,
      );
    }
    return this.api.post<{ supprimees: number }>('/mg/stock/alertes/suivi/suppression', { ids, motif });
  }

  lancerControle(): void {
    this.feedback
      .run(() => this.api.post<Controle>('/mg/stock/alertes/suivi/controle', {}), {
        confirm: {
          title: 'Contrôle des seuils',
          message: 'Contrôler le stock réel de tous les articles actifs ?',
          hint: 'Une alerte est créée pour chaque article sous le seuil qui n’en a pas déjà une. Aucun doublon n’est créé.',
          confirmLabel: 'Lancer le contrôle',
          icon: 'rule',
        },
        loading: 'Contrôle en cours…',
        busy: this.busy,
        errorTitle: 'Contrôle impossible',
        success: (r) => ({
          title: 'Contrôle terminé',
          details: [
            { label: 'Articles contrôlés', value: String(r.articles) },
            { label: 'Nouvelles alertes', value: String(r.ouvertes) },
            { label: 'Passages en rupture', value: String(r.ruptures) },
            { label: 'Retours à la normale', value: String(r.retours) },
          ],
        }),
      })
      .subscribe(() => {
        this.load();
        this.watcher.refresh(true);
      });
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    this.api.download('/mg/stock/alertes/export', { ...this.params(), format }).subscribe({
      next: (blob) => downloadBlob(blob, `alertes-stock.${format}`),
      error: () => this.feedback.error({ title: `Export ${format.toUpperCase()} impossible`, message: 'Vérifiez votre permission d’export.' }),
    });
  }
}
