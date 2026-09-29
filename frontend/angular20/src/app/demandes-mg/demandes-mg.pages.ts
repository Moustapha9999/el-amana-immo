import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { downloadBlob } from '../demandes-employes/demandes-employe.models';
import { MontantPipe, QuantitePipe, formatQuantite, quantiteEntiere } from '../shared/montant.pipe';
import { feedbackSignal } from '../core/feedback/feedback-signal';

interface Dash {
  a_traiter: number;
  a_completer: number;
  validees: number;
  refusees: number;
  urgentes: number;
  a_regrouper: number;
  en_achat: number;
  servies: number;
  aujourd_hui: number;
  par_categorie: Array<{ code: string; name: string; count: number }>;
  par_source?: Array<{ code: string; name: string; count: number }>;
}

interface RequestRow {
  id: string;
  request_number: string;
  title: string;
  status: string;
  priority: string;
  requester_name?: string | null;
  source_espace_label?: string | null;
  category_name?: string | null;
  agency_label?: string | null;
  created_at: string;
  description?: string | null;
  complement_comment?: string | null;
  batch_id?: string | null;
  achat_demande_id?: string | null;
  items: Array<{
    id: string;
    description: string;
    quantity: number;
    quantity_granted?: number | null;
    unit: string;
    article_id?: string | null;
  }>;
  stock_hints: Array<{
    article_id: string;
    designation: string;
    stock_actuel: number;
    stock_min: number | null;
    quantity: number;
    after: number;
    available: boolean;
  }>;
}

interface GrantLine {
  id: string;
  description: string;
  quantity: number;
  unit: string;
  article_id?: string | null;
  granted: number | null;
}

interface BatchRow {
  id: string;
  batch_number: string;
  title: string;
  description?: string | null;
  period?: string | null;
  priority?: string;
  status: string;
  request_count: number;
  item_count: number;
  estimated_total: number;
  achat_demande_id?: string | null;
  items: Array<{ id: string; description: string; quantity: number; status: string }>;
  consolidated: Array<{ description: string; quantity: number; request_count: number }>;
}

const BATCH_LABEL: Record<string, string> = {
  BROUILLON: 'Brouillon',
  VALIDE: 'Validé',
  VALIDEE: 'Validé',
  EN_ACHAT: 'En achat',
};

const PRIO_LABEL: Record<string, string> = {
  NORMALE: 'Normale',
  HAUTE: 'Haute',
  URGENTE: 'Urgente',
  URGENT: 'Urgente',
};

const DELETE_LOCKED = new Set([
  'VALIDEE', 'A_REGROUPER', 'REGROUPEE', 'ACHAT_EN_COURS', 'COMMANDEE', 'SERVIE', 'CLOTUREE',
]);
const CLOSED = new Set(['REFUSEE', 'ANNULEE', 'SERVIE', 'CLOTUREE']);
const TREATABLE = new Set(['SOUMISE', 'RECUE', 'EN_ANALYSE', 'A_COMPLETER']);

const STATUS_LABEL: Record<string, string> = {
  BROUILLON: 'Brouillon',
  SOUMISE: 'Soumise',
  RECUE: 'Reçue',
  EN_ANALYSE: 'En analyse',
  A_COMPLETER: 'À compléter',
  VALIDEE: 'Validée',
  A_REGROUPER: 'À regrouper',
  REGROUPEE: 'Regroupée',
  ACHAT_EN_COURS: 'En achat',
  SERVIE: 'Servie',
  REFUSEE: 'Refusée',
  ANNULEE: 'Annulée',
};

@Component({
  selector: 'bea-dmg-dash',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-dmg-dash">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>Centre des demandes</h1>
          <p class="bea-mg__lead">Suivi des demandes employés : traitement, regroupement et achats.</p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/demandes-mg/demandes">
          <mat-icon>inbox</mat-icon> Demandes reçues
        </a>
      </header>
      @if (d(); as x) {
        <div class="bea-dmg-kpis">
          @for (card of cards(x); track card.label; let i = $index) {
            <a
              class="bea-dmg-kpi"
              [routerLink]="card.link"
              [style.--i]="i"
              [attr.data-tone]="card.tone"
              [attr.data-live]="card.live ? '' : null"
            >
              <span class="bea-dmg-kpi__icon" [attr.data-tone]="card.tone">
                <mat-icon>{{ card.icon }}</mat-icon>
              </span>
              <span class="bea-dmg-kpi__meta">
                <span>{{ card.label }}</span>
                <strong>{{ card.value }}</strong>
                <em>{{ card.hint }}</em>
              </span>
            </a>
          }
        </div>
        <div class="bea-dmg-dash__grid">
          <div class="bea-mg__panel bea-dmg-panel">
            <div class="bea-mg__panel-top">
              <h2><mat-icon>category</mat-icon> Par catégorie</h2>
            </div>
            <div class="bea-dmg-bars">
              @for (c of x.par_categorie; track c.code; let i = $index) {
                <div class="bea-dmg-bar" [style.--i]="i">
                  <div class="bea-dmg-bar__top">
                    <span>{{ c.name }}</span>
                    <strong>{{ c.count }}</strong>
                  </div>
                  <div class="bea-dmg-bar__track">
                    <i [style.width.%]="share(c.count, x.par_categorie)"></i>
                  </div>
                </div>
              } @empty {
                <p class="bea-mg__empty">Aucune catégorie.</p>
              }
            </div>
          </div>
          <div class="bea-mg__panel bea-dmg-panel">
            <div class="bea-mg__panel-top">
              <h2><mat-icon>apartment</mat-icon> Par département demandeur</h2>
            </div>
            <div class="bea-dmg-bars">
              @for (c of x.par_source || []; track c.code; let i = $index) {
                <div class="bea-dmg-bar" [style.--i]="i">
                  <div class="bea-dmg-bar__top">
                    <span>{{ c.name }}</span>
                    <strong>{{ c.count }}</strong>
                  </div>
                  <div class="bea-dmg-bar__track">
                    <i [style.width.%]="share(c.count, x.par_source || [])"></i>
                  </div>
                </div>
              } @empty {
                <p class="bea-mg__empty">Aucun département.</p>
              }
            </div>
          </div>
        </div>
      }
    </section>
  `,
})
export class DmgDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly d = signal<Dash | null>(null);
  ngOnInit(): void {
    this.api.get<Dash>('/mg/requests/dashboard').subscribe({ next: (r) => this.d.set(r) });
  }
  cards(x: Dash): Array<{ label: string; value: number; icon: string; tone: string; link: string; hint: string; live?: boolean }> {
    return [
      { label: 'À traiter', value: x.a_traiter, icon: 'pending_actions', tone: 'navy', link: '/demandes-mg/a-traiter', hint: 'Soumises et en analyse', live: x.a_traiter > 0 },
      { label: 'À compléter', value: x.a_completer, icon: 'edit_note', tone: 'warn', link: '/demandes-mg/a-completer', hint: 'En attente du demandeur', live: x.a_completer > 0 },
      { label: 'Urgentes', value: x.urgentes, icon: 'priority_high', tone: 'danger', link: '/demandes-mg/demandes', hint: 'Priorité haute ou urgente', live: x.urgentes > 0 },
      { label: "Aujourd'hui", value: x.aujourd_hui, icon: 'today', tone: 'blue', link: '/demandes-mg/demandes', hint: 'Demandes du jour' },
      { label: 'Validées', value: x.validees, icon: 'task_alt', tone: 'teal', link: '/demandes-mg/validees', hint: 'Prêtes à regrouper' },
      { label: 'À regrouper', value: x.a_regrouper, icon: 'inventory_2', tone: 'blue', link: '/demandes-mg/regroupements', hint: 'Vers un achat groupé' },
      { label: 'En achat', value: x.en_achat, icon: 'shopping_cart', tone: 'navy', link: '/demandes-mg/demandes', hint: 'Commande en cours' },
      { label: 'Servies', value: x.servies, icon: 'check_circle', tone: 'teal', link: '/demandes-mg/demandes', hint: 'Clôturées' },
      { label: 'Refusées', value: x.refusees, icon: 'thumb_down', tone: 'danger', link: '/demandes-mg/refusees', hint: 'Non retenues' },
    ];
  }
  share(count: number, rows: Array<{ count: number }>): number {
    const max = Math.max(1, ...rows.map((r) => r.count));
    return Math.round((count / max) * 100);
  }
}

@Component({
  selector: 'bea-dmg-inbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, MgGedPanelComponent, QuantitePipe],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>{{ title }}</h1>
          <p class="bea-mg__lead">Consulter, modifier les quantités accordées, traiter ou retirer une demande.</p>
        </div>
      </header>
      <form class="bea-mg__search" (ngSubmit)="load()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input [(ngModel)]="q" name="q" placeholder="N°, employé, titre…" />
        </label>
        <button type="submit" class="bea-mg__icon-btn" title="Filtrer">
          <mat-icon>filter_list</mat-icon>
        </button>
      </form>
      <div class="bea-mg__panel">
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table bea-emp-table">
            <thead>
              <tr>
                <th>N°</th>
                <th>Employé</th>
                <th>Département</th>
                <th>Catégorie</th>
                <th>Agence</th>
                <th>Priorité</th>
                <th>Statut</th>
                <th>Date</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (r of rows(); track r.id) {
                <tr>
                  <td class="bea-mg__code">{{ r.request_number }}</td>
                  <td>{{ r.requester_name }}</td>
                  <td>{{ r.source_espace_label || '—' }}</td>
                  <td>{{ r.category_name }}</td>
                  <td>{{ r.agency_label }}</td>
                  <td>{{ prio(r.priority) }}</td>
                  <td><span class="bea-emp-badge" [attr.data-status]="r.status">{{ label(r.status) }}</span></td>
                  <td>{{ r.created_at | date: 'dd/MM/yyyy' }}</td>
                  <td class="bea-mg__actions-cell">
                    <div class="bea-emp-actions">
                      <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="open(r.id, 'view')">
                        <mat-icon>visibility</mat-icon>
                      </button>
                      @if (canEdit(r)) {
                        <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="open(r.id, 'edit')">
                          <mat-icon>edit</mat-icon>
                        </button>
                      }
                      <button type="button" class="bea-mg__icon-btn" title="Télécharger le PDF" (click)="pdf(r)">
                        <mat-icon>picture_as_pdf</mat-icon>
                      </button>
                      @if (canValidate(r.status)) {
                        <button type="button" class="bea-mg__icon-btn bea-emp-icon--primary" title="Valider" (click)="act(r.id, 'validate')">
                          <mat-icon>check_circle</mat-icon>
                        </button>
                      }
                      @if (canComplement(r.status)) {
                        <button type="button" class="bea-mg__icon-btn" title="Demander un complément" (click)="act(r.id, 'request-info')">
                          <mat-icon>reply</mat-icon>
                        </button>
                      }
                      @if (canReject(r)) {
                        <button type="button" class="bea-mg__icon-btn" title="Refuser" (click)="ask('reject', r)">
                          <mat-icon>thumb_down</mat-icon>
                        </button>
                      }
                      @if (canServe(r.status)) {
                        <button type="button" class="bea-mg__icon-btn" title="Servir le stock" (click)="act(r.id, 'serve')">
                          <mat-icon>inventory_2</mat-icon>
                        </button>
                      }
                      @if (canCancel(r)) {
                        <button type="button" class="bea-mg__icon-btn" title="Désactiver" (click)="ask('cancel', r)">
                          <mat-icon>block</mat-icon>
                        </button>
                      }
                      @if (canDelete(r)) {
                        <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="ask('delete', r)">
                          <mat-icon>delete</mat-icon>
                        </button>
                      }
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (!rows().length) { <p class="bea-mg__empty">Aucune demande.</p> }
      </div>

      @if (detail(); as d) {
        <div class="bea-mg__backdrop" (click)="detail.set(null)"></div>
        <aside class="bea-mg__modal bea-mg__modal--lg bea-dmg-fiche" role="dialog" aria-labelledby="dmg-fiche-title">
          <div class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">{{ d.request_number }}</p>
              <div class="bea-dmg-fiche__title">
                <h2 id="dmg-fiche-title">{{ d.title }}</h2>
                <span class="bea-emp-badge" [attr.data-status]="d.status">{{ label(d.status) }}</span>
              </div>
            </div>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="detail.set(null)">Retour</button>
          </div>
          <div class="bea-mg__modal-body">
            <ul class="bea-dmg-fiche__meta">
              <li><mat-icon>person</mat-icon><span>{{ d.requester_name || '—' }}</span></li>
              <li><mat-icon>apartment</mat-icon><span>{{ d.source_espace_label || '—' }}</span></li>
              <li><mat-icon>location_on</mat-icon><span>{{ d.agency_label || '—' }}</span></li>
              <li><mat-icon>flag</mat-icon><span>{{ prio(d.priority) }}</span></li>
            </ul>
            @if (d.description) {
              <p class="bea-dmg-fiche__desc">{{ d.description }}</p>
            }
            <section class="bea-dmg-fiche__grant">
              <h3>Quantités accordées</h3>
              <p class="bea-dmg-grant__lead">Après vérification du stock, indiquez la quantité à accorder. Elle ne peut pas dépasser la quantité demandée.</p>
              @if (grantError()) { <p class="bea-dmg-fiche__alert bea-dmg-fiche__alert--err">{{ grantError() }}</p> }
              @if (grantOk()) { <p class="bea-dmg-fiche__alert bea-dmg-fiche__alert--ok">{{ grantOk() }}</p> }
              <div class="bea-dmg-fiche__table">
                <table class="bea-mg__table bea-dmg-grant">
                  <thead>
                    <tr>
                      <th>Désignation</th>
                      <th>Demandée</th>
                      <th>Stock</th>
                      <th>Accordée</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (it of grantLines; track it.id) {
                      <tr>
                        <td>{{ it.description }}</td>
                        <td>{{ it.quantity | quantite }} {{ it.unit }}</td>
                        <td [class.bea-dmg-grant__short]="stockShort(it)">{{ stockLabel(it) }}</td>
                        <td>
                          <input
                            type="number"
                            min="0"
                            [max]="it.quantity"
                            step="1"
                            [(ngModel)]="it.granted"
                            [name]="'g' + it.id"
                            [readonly]="mode() === 'view'"
                          />
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              @if (mode() === 'edit') {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="grantSaving()" (click)="saveGranted(d.id)">
                  Enregistrer les quantités
                </button>
              }
            </section>
            <label class="bea-dmg-note">
              <span><mat-icon>chat_bubble_outline</mat-icon> Commentaire</span>
              <textarea
                [(ngModel)]="comment"
                name="comment"
                rows="4"
                placeholder="Précisez le motif ou la décision transmise au demandeur."
              ></textarea>
              <small>Ce texte accompagne l’action choisie en bas de la fiche. Il est obligatoire pour un refus.</small>
            </label>
            <bea-mg-ged moduleCode="demandes-mg" entity="MG_EMPLOYEE_REQUEST" [entityId]="d.id" [reference]="d.request_number" />
          </div>
          <div class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="pdf(d)">PDF</button>
            @if (canComplement(d.status)) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="act(d.id, 'request-info')">Complément</button>
            }
            @if (canReject(d)) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ask('reject', d)">Refuser</button>
            }
            @if (canServe(d.status)) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="act(d.id, 'serve')">Servir stock</button>
            }
            @if (canCancel(d)) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ask('cancel', d)">Désactiver</button>
            }
            @if (canDelete(d)) {
              <button type="button" class="bea-mg__btn bea-mg__btn--danger" (click)="ask('delete', d)">Supprimer</button>
            }
            @if (canValidate(d.status)) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="act(d.id, 'validate')">Valider</button>
            }
          </div>
        </aside>
      }

      @if (confirm(); as c) {
        <div class="bea-mg__backdrop bea-emp-confirm-backdrop" (click)="confirm.set(null)"></div>
        <aside class="bea-mg__modal bea-mg__modal--sm bea-emp-confirm" role="dialog">
          <div class="bea-mg__modal-head">
            <h2>{{ confirmTitle(c.kind) }}</h2>
          </div>
          <div class="bea-mg__modal-body">
            <p>{{ confirmText(c) }}</p>
            @if (c.kind === 'reject') {
              <label class="bea-dmg-note bea-dmg-note--plain">
                <span>Motif de refus</span>
                <textarea [(ngModel)]="comment" name="motif" rows="4" required placeholder="Indiquez pourquoi la demande est refusée."></textarea>
              </label>
            }
          </div>
          <div class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="confirm.set(null)">Annuler</button>
            <button
              type="button"
              class="bea-mg__btn"
              [class.bea-mg__btn--danger]="c.kind !== 'cancel'"
              [class.bea-mg__btn--primary]="c.kind === 'cancel'"
              (click)="confirmDo()"
            >Confirmer</button>
          </div>
        </aside>
      }
    </section>
  `,
})
export class DmgInboxComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  readonly rows = signal<RequestRow[]>([]);
  readonly detail = signal<RequestRow | null>(null);
  readonly mode = signal<'view' | 'edit'>('view');
  readonly confirm = signal<{ kind: 'delete' | 'cancel' | 'reject'; row: RequestRow } | null>(null);
  readonly grantSaving = signal(false);
  readonly grantError = signal('');
  readonly grantOk = signal('');
  readonly erreur = feedbackSignal('error', '');
  readonly ok = feedbackSignal('success', '');
  grantLines: GrantLine[] = [];
  q = '';
  comment = '';
  title = 'Demandes reçues';
  statut: string | null = null;

  ngOnInit(): void {
    const preset = this.route.snapshot.data['statut'] as string | undefined;
    this.statut = preset || null;
    this.title =
      preset === 'a_traiter' ? 'À traiter' :
      preset === 'A_COMPLETER' ? 'À compléter' :
      preset === 'a_regrouper' ? 'Validées' :
      preset === 'REFUSEE' ? 'Refusées' : 'Demandes reçues';
    this.load();
  }
  label(s: string): string { return STATUS_LABEL[s] || s; }
  prio(s: string): string { return PRIO_LABEL[s] || s; }
  canEdit(r: RequestRow): boolean {
    if (CLOSED.has(r.status) || r.batch_id || r.achat_demande_id) return false;
    return !['REGROUPEE', 'ACHAT_EN_COURS', 'COMMANDEE'].includes(r.status);
  }
  canValidate(status: string): boolean { return ['SOUMISE', 'RECUE', 'EN_ANALYSE'].includes(status); }
  canComplement(status: string): boolean { return TREATABLE.has(status); }
  canReject(r: RequestRow): boolean { return this.canEdit(r); }
  canServe(status: string): boolean {
    return ['SOUMISE', 'RECUE', 'EN_ANALYSE', 'VALIDEE', 'A_REGROUPER'].includes(status);
  }
  canCancel(r: RequestRow): boolean { return this.canEdit(r); }
  canDelete(r: RequestRow): boolean {
    return !DELETE_LOCKED.has(r.status) && !r.batch_id && !r.achat_demande_id;
  }
  load(): void {
    this.erreur.set('');
    const params: Record<string, string | number> = { page: 1, size: 50, q: this.q };
    if (this.statut) params['statut'] = this.statut;
    this.api.get<{ items: RequestRow[] }>('/mg/requests', params).subscribe({
      next: (r) => this.rows.set(r.items),
      error: (e) => this.erreur.set(e?.error?.detail || 'Chargement impossible'),
    });
  }
  open(id: string, nextMode: 'view' | 'edit' = 'view'): void {
    this.grantError.set('');
    this.grantOk.set('');
    this.comment = '';
    this.api.get<RequestRow>(`/mg/requests/${id}`).subscribe({
      next: (r) => {
        this.mode.set(nextMode === 'edit' && this.canEdit(r) ? 'edit' : 'view');
        this.detail.set(r);
        this.grantLines = r.items.map((it) => this.grantLine(it));
      },
      error: (e) => this.erreur.set(e?.error?.detail || 'Ouverture impossible'),
    });
  }
  private grantLine(it: RequestRow['items'][number]): GrantLine {
    const granted = it.quantity_granted;
    return {
      id: it.id,
      description: it.description,
      quantity: quantiteEntiere(it.quantity),
      unit: it.unit,
      article_id: it.article_id,
      granted: granted === null || granted === undefined ? null : quantiteEntiere(granted),
    };
  }
  stockLabel(it: GrantLine): string {
    const hint = this.detail()?.stock_hints?.find((h) => h.article_id === it.article_id);
    if (!hint) return '—';
    return `${formatQuantite(hint.stock_actuel)}${hint.available ? '' : ' · insuffisant'}`;
  }
  stockShort(it: GrantLine): boolean {
    const hint = this.detail()?.stock_hints?.find((h) => h.article_id === it.article_id);
    return !!hint && !hint.available;
  }
  saveGranted(id: string): void {
    this.grantSaving.set(true);
    this.grantError.set('');
    this.grantOk.set('');
    const lines = this.grantLines.map((it) => ({
      item_id: it.id,
      quantity_granted: it.granted === null || it.granted === undefined || String(it.granted) === ''
        ? null
        : quantiteEntiere(it.granted),
    }));
    this.api.post<RequestRow>(`/mg/requests/${id}/granted`, { lines }).subscribe({
      next: (r) => {
        this.detail.set(r);
        this.grantLines = r.items.map((it) => this.grantLine(it));
        this.grantOk.set('Quantités accordées enregistrées. Elles figurent sur le PDF.');
        this.grantSaving.set(false);
      },
      error: (e) => {
        this.grantError.set(e?.error?.detail || 'Enregistrement impossible');
        this.grantSaving.set(false);
      },
    });
  }
  act(id: string, action: 'validate' | 'reject' | 'request-info' | 'serve'): void {
    if (action === 'reject' && !this.comment.trim()) {
      this.erreur.set('Le motif de refus est obligatoire.');
      return;
    }
    this.erreur.set('');
    const url = action === 'serve' ? `/mg/requests/${id}/serve` : `/mg/requests/${id}/${action}`;
    this.api.post<RequestRow>(url, { comment: this.comment.trim() || null }).subscribe({
      next: () => {
        this.ok.set(this.actLabel(action));
        this.detail.set(null);
        this.confirm.set(null);
        this.comment = '';
        this.load();
      },
      error: (e) => this.erreur.set(e?.error?.detail || 'Action impossible'),
    });
  }
  pdf(row: RequestRow): void {
    this.erreur.set('');
    this.api.download(`/mg/requests/${row.id}/pdf`, { visas: 'agence,mg' }).subscribe({
      next: (blob) => downloadBlob(blob, `${row.request_number}.pdf`),
      error: () => this.erreur.set('Téléchargement du PDF impossible'),
    });
  }
  ask(kind: 'delete' | 'cancel' | 'reject', row: RequestRow): void {
    this.confirm.set({ kind, row });
  }
  confirmTitle(kind: 'delete' | 'cancel' | 'reject'): string {
    if (kind === 'delete') return 'Supprimer la demande';
    if (kind === 'reject') return 'Refuser la demande';
    return 'Désactiver la demande';
  }
  confirmText(c: { kind: 'delete' | 'cancel' | 'reject'; row: RequestRow }): string {
    if (c.kind === 'delete') return `La demande ${c.row.request_number} sera définitivement supprimée.`;
    if (c.kind === 'reject') return `La demande ${c.row.request_number} sera refusée. Le demandeur sera notifié.`;
    return `La demande ${c.row.request_number} sera désactivée. L’historique est conservé.`;
  }
  confirmDo(): void {
    const c = this.confirm();
    if (!c) return;
    if (c.kind === 'reject') {
      this.act(c.row.id, 'reject');
      return;
    }
    if (c.kind === 'delete') {
      this.api.delete(`/mg/requests/${c.row.id}`).subscribe({
        next: () => {
          this.ok.set('Demande supprimée.');
          this.confirm.set(null);
          this.detail.set(null);
          this.load();
        },
        error: (e) => {
          this.erreur.set(e?.error?.detail || 'Suppression impossible');
          this.confirm.set(null);
        },
      });
      return;
    }
    this.api.post(`/mg/requests/${c.row.id}/cancel`, { comment: this.comment.trim() || null }).subscribe({
      next: () => {
        this.ok.set('Demande désactivée.');
        this.confirm.set(null);
        this.detail.set(null);
        this.comment = '';
        this.load();
      },
      error: (e) => {
        this.erreur.set(e?.error?.detail || 'Désactivation impossible');
        this.confirm.set(null);
      },
    });
  }
  private actLabel(action: 'validate' | 'reject' | 'request-info' | 'serve'): string {
    if (action === 'validate') return 'Demande validée.';
    if (action === 'reject') return 'Demande refusée.';
    if (action === 'serve') return 'Demande servie depuis le stock.';
    return 'Complément demandé.';
  }
}

@Component({
  selector: 'bea-dmg-batches',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, RouterLink, QuantitePipe, MontantPipe],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>Regroupements achats</h1>
          <p class="bea-mg__lead">Regrouper les demandes validées, les modifier tant qu’elles sont en brouillon, puis créer la demande d’achat.</p>
        </div>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openCreate()">
          + Nouveau regroupement
        </button>
      </header>
      <form class="bea-mg__search" (ngSubmit)="q = q">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input [(ngModel)]="q" name="q" placeholder="N°, titre…" />
        </label>
        <button type="submit" class="bea-mg__icon-btn" title="Filtrer">
          <mat-icon>filter_list</mat-icon>
        </button>
      </form>
      <div class="bea-mg__panel">
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table bea-emp-table">
            <thead>
              <tr>
                <th>N°</th>
                <th>Titre</th>
                <th>Demandes</th>
                <th>Articles</th>
                <th>Estimé</th>
                <th>Statut</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (b of filtered(); track b.id) {
                <tr>
                  <td class="bea-mg__code">{{ b.batch_number }}</td>
                  <td>{{ b.title }}</td>
                  <td>{{ b.request_count }}</td>
                  <td>{{ b.item_count }}</td>
                  <td>{{ b.estimated_total | montant }}</td>
                  <td><span class="bea-emp-badge" [attr.data-status]="b.status === 'BROUILLON' ? 'BROUILLON' : 'VALIDEE'">{{ batchLabel(b.status) }}</span></td>
                  <td class="bea-mg__actions-cell">
                    <div class="bea-emp-actions">
                      <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="open(b.id, 'view')">
                        <mat-icon>visibility</mat-icon>
                      </button>
                      @if (b.status === 'BROUILLON') {
                        <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="open(b.id, 'edit')">
                          <mat-icon>edit</mat-icon>
                        </button>
                        <button type="button" class="bea-mg__icon-btn bea-emp-icon--primary" title="Valider et créer la demande d’achat" (click)="validate(b.id)">
                          <mat-icon>shopping_cart</mat-icon>
                        </button>
                        <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="askDelete(b)">
                          <mat-icon>delete</mat-icon>
                        </button>
                      }
                      @if (b.achat_demande_id) {
                        <a class="bea-mg__icon-btn" title="Voir la demande d’achat" [routerLink]="['/achats-appro/demandes', b.achat_demande_id]">
                          <mat-icon>open_in_new</mat-icon>
                        </a>
                      }
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (!filtered().length) { <p class="bea-mg__empty">Aucun regroupement.</p> }
      </div>

      @if (creating()) {
        <div class="bea-mg__backdrop" (click)="creating.set(false)"></div>
        <aside class="bea-mg__modal" role="dialog">
          <div class="bea-mg__modal-head"><h2>Créer un regroupement</h2></div>
          <form class="bea-mg__modal-body" (ngSubmit)="create()">
            <label class="bea-mg__field"><span>Titre</span><input [(ngModel)]="title" name="title" required /></label>
            <label class="bea-mg__field"><span>Période</span><input [(ngModel)]="period" name="period" /></label>
            <label class="bea-mg__field"><span>Description</span><textarea [(ngModel)]="description" name="desc" rows="2"></textarea></label>
            <p>Demandes validées à inclure</p>
            @for (r of groupable(); track r.id) {
              <label><input type="checkbox" [checked]="selected.has(r.id)" (change)="toggle(r.id)" /> {{ r.request_number }} — {{ r.title }}</label>
            }
            @if (!groupable().length) { <p class="bea-mg__empty">Aucune demande validée à regrouper.</p> }
            <div class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="creating.set(false)">Annuler</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Créer</button>
            </div>
          </form>
        </aside>
      }

      @if (detail(); as b) {
        <div class="bea-mg__backdrop" (click)="detail.set(null)"></div>
        <aside class="bea-mg__modal bea-mg__modal--lg" role="dialog">
          <div class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">{{ b.batch_number }}</p>
              <h2>{{ mode() === 'edit' ? 'Modifier le regroupement' : b.title }}</h2>
            </div>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="detail.set(null)">Retour</button>
          </div>
          <div class="bea-mg__modal-body">
            @if (mode() === 'edit') {
              <label class="bea-mg__field"><span>Titre</span><input [(ngModel)]="editTitle" name="etitle" /></label>
              <label class="bea-mg__field"><span>Période</span><input [(ngModel)]="editPeriod" name="eperiod" /></label>
              <label class="bea-mg__field"><span>Description</span><textarea [(ngModel)]="editDescription" name="edesc" rows="2"></textarea></label>
            } @else {
              <p>{{ b.description || '—' }}</p>
              <p>{{ b.period || 'Sans période' }} · {{ batchLabel(b.status) }}</p>
            }
            <h3>Lignes</h3>
            <table class="bea-mg__table">
              <thead><tr><th>Désignation</th><th>Quantité</th><th></th></tr></thead>
              <tbody>
                @for (it of b.items; track it.id) {
                  <tr>
                    <td>{{ it.description }}</td>
                    <td>{{ it.quantity | quantite }}</td>
                    <td>
                      @if (b.status === 'BROUILLON') {
                        <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Retirer" (click)="removeItem(b.id, it.id)">
                          <mat-icon>close</mat-icon>
                        </button>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
            @if (!b.items.length) { <p class="bea-mg__empty">Aucune ligne.</p> }
          </div>
          <div class="bea-mg__modal-foot">
            @if (mode() === 'edit') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="save(b.id)">Enregistrer</button>
            }
            @if (b.status === 'BROUILLON') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="validate(b.id)">Valider → DA</button>
            }
            @if (b.achat_demande_id) {
              <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/achats-appro/demandes', b.achat_demande_id]">Voir DA</a>
            }
          </div>
        </aside>
      }

      @if (pendingDelete(); as b) {
        <div class="bea-mg__backdrop bea-emp-confirm-backdrop" (click)="pendingDelete.set(null)"></div>
        <aside class="bea-mg__modal bea-mg__modal--sm bea-emp-confirm" role="dialog">
          <div class="bea-mg__modal-head"><h2>Supprimer le regroupement</h2></div>
          <div class="bea-mg__modal-body">
            <p>Le regroupement {{ b.batch_number }} sera supprimé. Les demandes qu’il contient redeviennent disponibles.</p>
          </div>
          <div class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="pendingDelete.set(null)">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--danger" (click)="remove(b.id)">Supprimer</button>
          </div>
        </aside>
      }
    </section>
  `,
})
export class DmgBatchesComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<BatchRow[]>([]);
  readonly groupable = signal<RequestRow[]>([]);
  readonly creating = signal(false);
  readonly detail = signal<BatchRow | null>(null);
  readonly mode = signal<'view' | 'edit'>('view');
  readonly pendingDelete = signal<BatchRow | null>(null);
  readonly erreur = feedbackSignal('error', '');
  readonly ok = feedbackSignal('success', '');
  readonly selected = new Set<string>();
  title = '';
  period = '';
  description = '';
  editTitle = '';
  editPeriod = '';
  editDescription = '';
  q = '';

  ngOnInit(): void { this.load(); }
  batchLabel(s: string): string { return BATCH_LABEL[s] || s; }
  filtered(): BatchRow[] {
    const q = this.q.trim().toLowerCase();
    if (!q) return this.rows();
    return this.rows().filter((b) =>
      b.batch_number.toLowerCase().includes(q) || b.title.toLowerCase().includes(q),
    );
  }
  load(): void {
    this.api.get<{ items: BatchRow[] }>('/mg/batches', { page: 1, size: 50 }).subscribe({
      next: (r) => this.rows.set(r.items.map((b) => ({ ...b, items: b.items || [] }))),
      error: (e) => this.erreur.set(e?.error?.detail || 'Chargement impossible'),
    });
  }
  loadGroupable(): void {
    this.api.get<{ items: RequestRow[] }>('/mg/requests', { statut: 'a_regrouper', page: 1, size: 80 }).subscribe({
      next: (r) => this.groupable.set(r.items),
    });
  }
  openCreate(): void {
    this.erreur.set('');
    this.title = '';
    this.period = '';
    this.description = '';
    this.selected.clear();
    this.creating.set(true);
    this.loadGroupable();
  }
  toggle(id: string): void {
    if (this.selected.has(id)) this.selected.delete(id);
    else this.selected.add(id);
  }
  create(): void {
    this.erreur.set('');
    this.api.post<BatchRow>('/mg/batches', {
      title: this.title,
      period: this.period || null,
      description: this.description || null,
      request_ids: [...this.selected],
    }).subscribe({
      next: () => {
        this.creating.set(false);
        this.selected.clear();
        this.ok.set('Regroupement créé.');
        this.load();
      },
      error: (e) => this.erreur.set(e?.error?.detail || 'Création impossible'),
    });
  }
  open(id: string, nextMode: 'view' | 'edit'): void {
    this.erreur.set('');
    this.api.get<BatchRow>(`/mg/batches/${id}`).subscribe({
      next: (b) => {
        const row = { ...b, items: b.items || [] };
        this.mode.set(nextMode === 'edit' && row.status === 'BROUILLON' ? 'edit' : 'view');
        this.editTitle = row.title;
        this.editPeriod = row.period || '';
        this.editDescription = row.description || '';
        this.detail.set(row);
      },
      error: (e) => this.erreur.set(e?.error?.detail || 'Ouverture impossible'),
    });
  }
  save(id: string): void {
    this.api.patch<BatchRow>(`/mg/batches/${id}`, {
      title: this.editTitle,
      period: this.editPeriod || null,
      description: this.editDescription || null,
    }).subscribe({
      next: (b) => {
        this.detail.set({ ...b, items: b.items || [] });
        this.mode.set('view');
        this.ok.set('Regroupement enregistré.');
        this.load();
      },
      error: (e) => this.erreur.set(e?.error?.detail || 'Enregistrement impossible'),
    });
  }
  removeItem(batchId: string, itemId: string): void {
    this.api.delete<BatchRow>(`/mg/batches/${batchId}/items/${itemId}`).subscribe({
      next: (b) => {
        this.detail.set({ ...b, items: b.items || [] });
        this.ok.set('Ligne retirée.');
        this.load();
      },
      error: (e) => this.erreur.set(e?.error?.detail || 'Retrait impossible'),
    });
  }
  validate(id: string): void {
    this.erreur.set('');
    this.api.post<BatchRow>(`/mg/batches/${id}/validate`, {}).subscribe({
      next: () => {
        this.detail.set(null);
        this.ok.set('Regroupement validé. La demande d’achat est créée.');
        this.load();
      },
      error: (e) => this.erreur.set(e?.error?.detail || 'Validation impossible'),
    });
  }
  askDelete(row: BatchRow): void { this.pendingDelete.set(row); }
  remove(id: string): void {
    this.api.delete(`/mg/batches/${id}`).subscribe({
      next: () => {
        this.pendingDelete.set(null);
        this.detail.set(null);
        this.ok.set('Regroupement supprimé.');
        this.load();
      },
      error: (e) => {
        this.erreur.set(e?.error?.detail || 'Suppression impossible');
        this.pendingDelete.set(null);
      },
    });
  }
}
