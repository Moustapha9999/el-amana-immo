import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { DemandesContext } from '../demandes/demandes-context';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { DocumentViewerComponent } from '../archives-generales/document-viewer.component';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import {
  ACTION_TONE,
  CANCELLABLE,
  EDITABLE,
  HistoryEvent,
  MineDashboard,
  MineDocument,
  RefRow,
  ReqCategory,
  ReqItem,
  RequestNotif,
  RequestRow,
  barWidth,
  canDeleteRequest,
  downloadBlob,
  emptyItem,
  fileSizeLabel,
  formatQty,
  priorityLabel,
  statusLabel,
  VISA_OPTIONS,
} from './demandes-employe.models';

@Component({
  selector: 'bea-emp-accueil',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-emp">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">{{ ctx.kicker() }}</p>
          <h1>Tableau de bord</h1>
          <p class="bea-mg__lead">
            @if (prenom) { {{ prenom }}, voici } @else { Voici } l’état réel de vos demandes internes —
            du brouillon jusqu’à la réception aux Moyens Généraux.
          </p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--primary" [routerLink]="ctx.base() + '/nouvelle'">
          <mat-icon>add</mat-icon> Nouvelle demande
        </a>
      </header>

      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }

      @if (dash(); as d) {
        <div class="bea-emp-kpi">
          <button type="button" class="bea-emp-kpi__card" (click)="goList()">
            <span>Mes demandes</span>
            <strong>{{ d.total }}</strong>
            <small>Toutes vos fiches</small>
          </button>
          <button type="button" class="bea-emp-kpi__card" (click)="goList('BROUILLON')">
            <span>Brouillons</span>
            <strong>{{ d.brouillons }}</strong>
            <small>À finaliser ou soumettre</small>
          </button>
          <button type="button" class="bea-emp-kpi__card bea-emp-kpi__card--warn" (click)="goList('A_COMPLETER')">
            <span>À compléter</span>
            <strong>{{ d.a_completer }}</strong>
            <small>Les MG ont demandé un complément</small>
          </button>
          <button type="button" class="bea-emp-kpi__card bea-emp-kpi__card--info" (click)="goList('SOUMISE')">
            <span>En cours</span>
            <strong>{{ d.en_cours }}</strong>
            <small>Chez le destinataire</small>
          </button>
          <button type="button" class="bea-emp-kpi__card bea-emp-kpi__card--ok" (click)="goList('SERVIE')">
            <span>Servies</span>
            <strong>{{ d.servies }}</strong>
            <small>Clôturées côté stock / achat</small>
          </button>
          <a class="bea-emp-kpi__card" [routerLink]="ctx.base() + '/notifications'">
            <span>Notifications</span>
            <strong>{{ d.notifications_non_lues }}</strong>
            <small>Circuit de vos demandes uniquement</small>
          </a>
        </div>

        <div class="bea-emp-dash">
          <article class="bea-mg__panel bea-emp-dash__chart">
            <div class="bea-mg__panel-top">
              <h2>Où en sont vos demandes</h2>
              <span class="bea-mg__count">{{ d.total }}</span>
            </div>
            <div class="bea-emp-bars">
              @for (s of d.par_statut; track s.code) {
                <button type="button" class="bea-emp-bar" (click)="goList(s.code)">
                  <span class="bea-emp-bar__meta">
                    <strong>{{ s.name }}</strong>
                    <em>{{ s.count }}</em>
                  </span>
                  <span class="bea-emp-bar__track">
                    <span class="bea-emp-bar__fill" [attr.data-status]="s.code" [style.width]="width(s.count, statutMax())"></span>
                  </span>
                </button>
              } @empty {
                <p class="bea-mg__empty">Aucune répartition pour le moment.</p>
              }
            </div>
          </article>

          <article class="bea-mg__panel bea-emp-dash__chart">
            <div class="bea-mg__panel-top"><h2>Par catégorie</h2></div>
            <div class="bea-emp-bars">
              @for (c of d.par_categorie; track c.code) {
                <div class="bea-emp-bar">
                  <span class="bea-emp-bar__meta">
                    <strong>{{ c.name }}</strong>
                    <em>{{ c.count }}</em>
                  </span>
                  <span class="bea-emp-bar__track">
                    <span class="bea-emp-bar__fill bea-emp-bar__fill--cat" [style.width]="width(c.count, catMax())"></span>
                  </span>
                </div>
              } @empty {
                <p class="bea-mg__empty">Aucune catégorie utilisée.</p>
              }
            </div>
          </article>
        </div>

        <div class="bea-emp-dash">
          <article class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Ce que cela signifie</h2></div>
            <ul class="bea-emp-insights">
              @for (i of d.insights; track i.title) {
                <li [attr.data-tone]="i.tone">
                  <strong>{{ i.title }}</strong>
                  <p>{{ i.text }}</p>
                  @if (i.statut) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="goList(i.statut)">Voir</button>
                  }
                </li>
              }
            </ul>
          </article>

          <article class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Dernières fiches</h2>
              <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="ctx.base() + '/demandes'">Liste</a>
            </div>
            <div class="bea-emp-scroll">
              <ul class="bea-emp-recent">
                @for (r of d.recentes; track r.id) {
                  <li>
                    <div>
                      <code class="bea-mg__code">{{ r.request_number }}</code>
                      <strong>{{ r.title }}</strong>
                      <span>{{ r.category_name }} · {{ r.created_at | date: 'dd/MM/yyyy' }}</span>
                    </div>
                    <span class="bea-emp-badge" [attr.data-status]="r.status">{{ label(r.status) }}</span>
                  </li>
                } @empty {
                  <li class="bea-mg__empty">Aucune demande récente.</li>
                }
              </ul>
            </div>
          </article>
        </div>

        <ol class="bea-emp-legend">
          <li><span>1</span> Brouillon — vous rédigez</li>
          <li><span>2</span> Soumise — part vers les MG</li>
          <li><span>3</span> Reçue — ouverte par les MG</li>
          <li><span>4</span> Validée, refusée ou à compléter</li>
          <li><span>5</span> Servie — stock ou achat terminé</li>
        </ol>
      }
    </section>
  `,
})
export class EmpAccueilComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly ctx = inject(DemandesContext);
  readonly dash = signal<MineDashboard | null>(null);
  readonly erreur = signal('');

  get prenom(): string {
    return (this.auth.user()?.full_name || '').trim().split(/\s+/)[0] || '';
  }

  ngOnInit(): void {
    this.api.get<MineDashboard>('/me/requests/dashboard').subscribe({
      next: (d) => this.dash.set(d),
      error: () => this.erreur.set('Dashboard indisponible.'),
    });
  }

  label(s: string): string { return statusLabel(s); }
  width(n: number, max: number): string { return barWidth(n, max); }
  statutMax(): number {
    return Math.max(1, ...(this.dash()?.par_statut || []).map((s) => s.count));
  }
  catMax(): number {
    return Math.max(1, ...(this.dash()?.par_categorie || []).map((s) => s.count));
  }
  goList(statut?: string): void {
    void this.router.navigate([this.ctx.base() + '/demandes'], {
      queryParams: statut ? { statut } : {},
    });
  }
}

@Component({
  selector: 'bea-emp-nouvelle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, RouterLink],
  template: `
    <section class="bea-mg bea-emp">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">{{ ctx.kicker() }}</p>
          <h1>Nouvelle demande</h1>
          <p class="bea-mg__lead">Formulaire d’expression de besoin. L’aperçu ci-contre est le document imprimé, visas compris.</p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="ctx.base() + '/demandes'">Mes demandes</a>
      </header>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (ok()) { <p class="bea-stock-page__ok">{{ ok() }}</p> }

      @if (!category()) {
        <h2 class="bea-emp__ask">Quelle demande souhaitez-vous adresser ?</h2>
        <div class="bea-emp__cats">
          @for (c of categories(); track c.id) {
            <button type="button" class="bea-emp__cat" (click)="pick(c)">
              <mat-icon>{{ c.icon || 'assignment' }}</mat-icon>
              <strong>{{ c.name }}</strong>
              <span>{{ c.description || 'Demande interne routée vers le destinataire.' }}</span>
            </button>
          }
        </div>
      } @else {
        <div class="bea-emp-formwrap">
          <form class="bea-mg__panel bea-emp__form" (ngSubmit)="save(false)">
            <div class="bea-mg__panel-top">
              <div>
                <p class="bea-stock-page__kicker">Type</p>
                <h2>{{ category()!.name }}</h2>
              </div>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="resetType()">Changer</button>
            </div>
            <div class="bea-mg__modal-body">
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">
                  <span>Objet de la demande</span>
                  <input [(ngModel)]="title" name="title" required placeholder="Ex. Fournitures de bureau" />
                </label>
                <label>
                  <span>Département</span>
                  @if (departements().length) {
                    <select [(ngModel)]="departmentId" name="department">
                      <option value="">{{ ctx.kicker() }}</option>
                      @for (d of departements(); track d.id) {
                        <option [value]="d.id">{{ d.label }}</option>
                      }
                    </select>
                  } @else {
                    <input [value]="ctx.kicker()" readonly />
                  }
                </label>
                <label>
                  <span>Priorité</span>
                  <select [(ngModel)]="priority" name="priority">
                    <option value="NORMALE">Normale</option>
                    <option value="HAUTE">Haute</option>
                    <option value="URGENTE">Urgente</option>
                  </select>
                </label>
                <label>
                  <span>Période</span>
                  <input [(ngModel)]="period" name="period" placeholder="Septembre 2026" />
                </label>
                <label class="bea-mg__span2">
                  <span>Motif</span>
                  <textarea [(ngModel)]="description" name="description" rows="3" placeholder="Précisez le besoin, le service et l’usage."></textarea>
                </label>
              </div>
            </div>
            <div class="bea-mg__modal-body bea-emp-articles">
              <div class="bea-emp-articles__intro">
                <h3>Articles demandés</h3>
                <p>La quantité accordée reste vide : elle est portée à la main par les Moyens Généraux.</p>
              </div>
              <div class="bea-emp-articles__head">
                <span>Désignation</span>
                <span>Quantité demandée</span>
                <span>Unité</span>
                <span>Article stock</span>
                <span></span>
              </div>
              @for (it of items(); track $index; let i = $index) {
                <div class="bea-emp-articles__row">
                  <input [(ngModel)]="it.description" [name]="'d'+i" placeholder="Désignation" required />
                  <input type="number" min="0.001" step="0.001" [(ngModel)]="it.quantity" [name]="'q'+i" />
                  <input [(ngModel)]="it.unit" [name]="'u'+i" />
                  <select [(ngModel)]="it.article_id" [name]="'a'+i">
                    <option [ngValue]="null">Optionnel</option>
                    @for (art of articles(); track art.id) {
                      <option [ngValue]="art.id">{{ art.label }}</option>
                    }
                  </select>
                  <button type="button" class="bea-mg__icon-btn" title="Retirer la ligne" (click)="removeLine(i)">
                    <mat-icon>close</mat-icon>
                  </button>
                </div>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="addLine()">+ Article</button>
            </div>
            <fieldset class="bea-emp-signpick">
              <legend>Qui doit signer</legend>
              @for (v of visaOptions; track v.id) {
                <label>
                  <input type="checkbox" [checked]="visas().includes(v.id)" (change)="toggleVisa(v.id)" />
                  {{ v.label }}
                </label>
              }
            </fieldset>
            <div class="bea-mg__modal-foot">
              <button type="submit" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="saving()">Enregistrer brouillon</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="saving()" (click)="save(true)">Soumettre</button>
              @if (savedId()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="pdf()">
                  <mat-icon>picture_as_pdf</mat-icon> Télécharger le PDF
                </button>
              }
            </div>
          </form>

          <div class="bea-emp-preview">
            <p class="bea-stock-page__kicker">Rendu du formulaire</p>
            <aside class="bea-emp-paper" aria-label="Aperçu du formulaire d’expression de besoin">
              <header class="bea-emp-paper__head">
                <img src="/brand/logo-bea.png" alt="Banque El Amana" />
                <div>
                  <strong>Banque El Amana</strong>
                  <span>Département Ressources Humaines et Moyens Généraux</span>
                  <em>Service Moyens Généraux</em>
                </div>
              </header>
              <p class="bea-emp-paper__date">Nouakchott le {{ today | date: 'dd/MM/yyyy' }}</p>
              <div class="bea-emp-paper__body">
              <h3>Formulaire d’expression de besoin</h3>
              <div class="bea-emp-paper__id">
                <dl class="bea-emp-paper__id-main">
                  <div><dt>Demandeur</dt><dd>{{ demandeur }}</dd></div>
                  <div><dt>Département</dt><dd>{{ departmentLabel() }}</dd></div>
                  <div><dt>Objet</dt><dd>{{ title || '—' }}</dd></div>
                  <div><dt>Motif</dt><dd>{{ description || '—' }}</dd></div>
                </dl>
                <div class="bea-emp-paper__id-side">
                  <span>{{ category()!.name }}</span>
                  <span>{{ savedNumber() || 'N° à l’enregistrement' }}</span>
                  <span>Priorité {{ prioLabel(priority) }}</span>
                  <span>{{ period || '—' }}</span>
                </div>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Désignation</th>
                    <th>Quantité demandée</th>
                    <th>Quantité accordée</th>
                  </tr>
                </thead>
                <tbody>
                  @for (line of paperLines(); track $index) {
                    <tr>
                      <td>{{ line.label }}</td>
                      <td>{{ line.qty }}</td>
                      <td></td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
              <div class="bea-emp-paper__foot">
                <div class="bea-emp-visas" [class.bea-emp-visas--one]="selectedVisas().length < 2">
                  @for (v of selectedVisas(); track v.id) {
                    <div>
                      <span>{{ v.label }}</span>
                      <i></i>
                    </div>
                  }
                </div>
              </div>
            </aside>
          </div>
        </div>
      }
    </section>
  `,
})
export class EmpNouvelleComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  readonly ctx = inject(DemandesContext);
  readonly today = new Date();
  readonly categories = signal<ReqCategory[]>([]);
  readonly category = signal<ReqCategory | null>(null);
  readonly agences = signal<RefRow[]>([]);
  readonly departements = signal<RefRow[]>([]);
  readonly articles = signal<RefRow[]>([]);
  readonly visaOptions = VISA_OPTIONS;
  readonly visas = signal<string[]>(['agence', 'mg']);
  readonly items = signal<ReqItem[]>([emptyItem()]);
  readonly erreur = signal('');
  readonly ok = signal('');
  readonly saving = signal(false);
  readonly savedId = signal<string | null>(null);
  readonly savedNumber = signal('');
  title = '';
  description = '';
  agencyId = '';
  departmentId = '';
  priority = 'NORMALE';
  period = '';

  ngOnInit(): void {
    this.api.get<ReqCategory[]>('/me/requests/categories').subscribe({ next: (r) => this.categories.set(r) });
    this.api.get<{ agences: RefRow[]; articles: RefRow[]; departements: RefRow[] }>('/me/requests/refs').subscribe({
      next: (r) => {
        this.agences.set(r.agences || []);
        this.departements.set(r.departements || []);
        this.articles.set(r.articles || []);
        if (!this.agencyId && r.agences[0]) this.agencyId = r.agences[0].id;
      },
    });
  }
  get demandeur(): string {
    return (this.auth.user()?.full_name || '').trim() || '—';
  }
  prioLabel(p: string): string { return priorityLabel(p); }
  departmentLabel(): string {
    const picked = this.departements().find((d) => d.id === this.departmentId)?.label;
    return picked || this.ctx.kicker();
  }
  toggleVisa(id: string): void {
    this.visas.update((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }
  selectedVisas(): { id: string; label: string }[] {
    return this.visaOptions.filter((v) => this.visas().includes(v.id));
  }
  paperLines(): { label: string; qty: string }[] {
    return this.items()
      .filter((it) => (it.description || '').trim())
      .map((it) => ({
        label: it.description.trim(),
        qty: `${this.fmtQty(it.quantity)}${it.unit ? ' ' + it.unit : ''}`.trim(),
      }));
  }
  private fmtQty(n: number): string {
    const v = Number(n);
    if (!Number.isFinite(v)) return '';
    return Number.isInteger(v) ? String(v) : String(v);
  }
  pick(c: ReqCategory): void { this.category.set(c); }
  resetType(): void { this.category.set(null); this.savedId.set(null); }
  addLine(): void { this.items.update((cur) => [...cur, emptyItem()]); }
  removeLine(i: number): void { this.items.update((cur) => cur.filter((_, idx) => idx !== i)); }

  save(submit = false): void {
    const cat = this.category();
    if (!cat) return;
    const items = this.items().filter((i) => i.description.trim());
    if (!items.length) { this.erreur.set('Ajoutez au moins un article.'); return; }
    if (!this.title.trim()) { this.erreur.set('Indiquez l’objet de la demande.'); return; }
    this.saving.set(true);
    this.erreur.set('');
    const body = {
      category_id: cat.id,
      agency_id: this.agencyId || null,
      department_id: this.departmentId || null,
      title: this.title || null,
      description: this.description || null,
      priority: this.priority,
      period: this.period || null,
      items,
    };
    const req$ = this.savedId()
      ? this.api.patch<RequestRow>(`/me/requests/${this.savedId()}`, body)
      : this.api.post<RequestRow>('/me/requests', body);
    req$.subscribe({
      next: (row) => {
        this.savedId.set(row.id);
        this.savedNumber.set(row.request_number);
        if (!submit) {
          this.ok.set(`Brouillon ${row.request_number} enregistré. Vous pouvez télécharger le PDF à visas.`);
          this.saving.set(false);
          return;
        }
        this.api.post<RequestRow>(`/me/requests/${row.id}/submit`, {}).subscribe({
          next: (s) => {
            this.ok.set(`Demande ${s.request_number} soumise aux Moyens Généraux.`);
            this.saving.set(false);
          },
          error: (e) => { this.erreur.set(e?.error?.detail || 'Soumission impossible'); this.saving.set(false); },
        });
      },
      error: (e) => { this.erreur.set(e?.error?.detail || 'Enregistrement impossible'); this.saving.set(false); },
    });
  }

  pdf(): void {
    const id = this.savedId();
    if (!id) return;
    if (!this.visas().length) {
      this.erreur.set('Choisissez au moins un signataire.');
      return;
    }
    this.api.download(`/me/requests/${id}/pdf`, {
      visas: this.visas().join(','),
      department: this.departmentLabel(),
    }).subscribe({
      next: (blob) => downloadBlob(blob, `${this.savedNumber() || 'demande'}.pdf`),
      error: () => this.erreur.set('PDF indisponible.'),
    });
  }
}

@Component({
  selector: 'bea-emp-liste',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, RouterLink, MgGedPanelComponent],
  template: `
    <section class="bea-mg bea-emp">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">{{ ctx.kicker() }}</p>
          <h1>Mes demandes</h1>
          <p class="bea-mg__lead">Liste complète : créer, voir, modifier, compléter, désactiver ou supprimer.</p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--primary" [routerLink]="ctx.base() + '/nouvelle'">
          <mat-icon>add</mat-icon> Nouvelle demande
        </a>
      </header>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (ok()) { <p class="bea-stock-page__ok">{{ ok() }}</p> }

      <form class="bea-mg__search bea-emp-search" (ngSubmit)="$event.preventDefault(); load()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input [(ngModel)]="q" name="q" placeholder="Rechercher un n°, un titre…" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>flag</mat-icon>
          <select [(ngModel)]="statut" name="statut" (change)="load()">
            <option value="">Tous les statuts</option>
            @for (s of statuts; track s) {
              <option [value]="s">{{ label(s) }}</option>
            }
          </select>
        </label>
        <button type="submit" class="bea-mg__icon-btn" title="Filtrer">
          <mat-icon>filter_list</mat-icon>
        </button>
      </form>

      <div class="bea-mg__panel">
        <div class="bea-mg__table-scroll bea-emp-listscroll">
          <table class="bea-mg__table bea-emp-table">
            <thead>
              <tr>
                <th>N°</th>
                <th>Catégorie</th>
                <th>Titre</th>
                <th>Priorité</th>
                <th>Statut</th>
                <th>Date</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (r of rows(); track r.id; let i = $index) {
                <tr class="bea-emp-row" [style.animation-delay.ms]="i * 35">
                  <td class="bea-mg__code">{{ r.request_number }}</td>
                  <td>{{ r.category_name }}</td>
                  <td class="bea-emp-table__title">{{ r.title }}</td>
                  <td>{{ prio(r.priority) }}</td>
                  <td><span class="bea-emp-badge" [attr.data-status]="r.status">{{ label(r.status) }}</span></td>
                  <td>{{ r.created_at | date: 'dd/MM/yyyy' }}</td>
                  <td class="bea-mg__actions-cell">
                    <div class="bea-emp-actions">
                      <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="open(r.id, 'view')">
                        <mat-icon>visibility</mat-icon>
                      </button>
                      @if (canEdit(r.status)) {
                        <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="open(r.id, 'edit')">
                          <mat-icon>edit</mat-icon>
                        </button>
                        <button
                          type="button"
                          class="bea-mg__icon-btn bea-emp-icon--primary"
                          [title]="r.status === 'A_COMPLETER' ? 'Compléter' : 'Soumettre'"
                          (click)="submit(r.id)"
                        >
                          <mat-icon>{{ r.status === 'A_COMPLETER' ? 'playlist_add_check' : 'send' }}</mat-icon>
                        </button>
                      }
                      <button type="button" class="bea-mg__icon-btn" title="Télécharger le PDF" (click)="pdf(r)">
                        <mat-icon>picture_as_pdf</mat-icon>
                      </button>
                      @if (canCancel(r.status)) {
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
        @if (loading()) { <p class="bea-mg__empty">Chargement des demandes…</p> }
        @else if (!rows().length) { <p class="bea-mg__empty">Aucune demande pour ce filtre.</p> }
      </div>

      @if (detail(); as d) {
        <div class="bea-mg__backdrop bea-emp-fiche-backdrop" (click)="close()"></div>
        <aside class="bea-mg__modal bea-emp-fiche" role="dialog" aria-label="Fiche demande">
          <div class="bea-emp-fiche__head">
            <div>
              <p class="bea-emp-fiche__num">{{ d.request_number }}</p>
              <h2>{{ mode() === 'edit' ? 'Modifier la demande' : d.title }}</h2>
            </div>
            <div class="bea-emp-fiche__head-right">
              <span class="bea-emp-badge" [attr.data-status]="d.status">{{ label(d.status) }}</span>
              <button type="button" class="bea-mg__icon-btn" title="Fermer" (click)="close()">
                <mat-icon>close</mat-icon>
              </button>
            </div>
          </div>
          <div class="bea-emp-fiche__body">
            @if (mode() === 'edit') {
              <div class="bea-emp__grid">
                <label class="bea-mg__field bea-mg__field--grow">
                  <span>Objet</span>
                  <input [(ngModel)]="editTitle" name="etitle" />
                </label>
                <label class="bea-mg__field">
                  <span>Priorité</span>
                  <select [(ngModel)]="editPriority" name="eprio">
                    <option value="NORMALE">Normale</option>
                    <option value="HAUTE">Haute</option>
                    <option value="URGENTE">Urgente</option>
                  </select>
                </label>
                <label class="bea-mg__field">
                  <span>Période</span>
                  <input [(ngModel)]="editPeriod" name="eperiod" />
                </label>
                <label class="bea-mg__field bea-mg__field--grow">
                  <span>Motif</span>
                  <textarea [(ngModel)]="editDesc" name="edesc" rows="3"></textarea>
                </label>
              </div>
              @for (it of editItems(); track $index; let i = $index) {
                <div class="bea-emp__ligne">
                  <input [(ngModel)]="it.description" [name]="'ed'+i" />
                  <input type="number" min="0.001" step="0.001" [(ngModel)]="it.quantity" [name]="'eq'+i" />
                  <input [(ngModel)]="it.unit" [name]="'eu'+i" />
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="removeEdit(i)">Retirer</button>
                </div>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="addEdit()">+ Article</button>
            } @else {
              <div class="bea-emp-fiche__meta">
                <div><span>Catégorie</span><strong>{{ d.category_name || '—' }}</strong></div>
                <div><span>Agence</span><strong>{{ d.agency_label || '—' }}</strong></div>
                <div><span>Priorité</span><strong>{{ prio(d.priority) }}</strong></div>
                <div><span>Destinataire</span><strong>{{ d.target_espace_label || 'Moyens Généraux' }}</strong></div>
                <div><span>Période</span><strong>{{ d.period || '—' }}</strong></div>
                <div><span>Créée le</span><strong>{{ d.created_at | date: 'dd/MM/yyyy HH:mm' }}</strong></div>
              </div>
              @if (d.complement_comment) {
                <p class="bea-emp-fiche__alert bea-emp-fiche__alert--warn">Complément demandé : {{ d.complement_comment }}</p>
              }
              @if (d.rejection_reason) {
                <p class="bea-emp-fiche__alert bea-emp-fiche__alert--danger">Refus : {{ d.rejection_reason }}</p>
              }
              @if (d.validation_comment) {
                <p class="bea-emp-fiche__alert">{{ d.validation_comment }}</p>
              }
              @if (d.batch_number) {
                <p class="bea-emp-fiche__alert">Regroupée dans {{ d.batch_number }}</p>
              }
              <section class="bea-emp-fiche__block">
                <h3>Motif</h3>
                <p>{{ d.description || 'Aucun motif renseigné.' }}</p>
              </section>
              <section class="bea-emp-fiche__block">
                <h3>Articles</h3>
                <table class="bea-emp-fiche__table">
                  <thead>
                    <tr><th>Désignation</th><th>Quantité</th><th>Unité</th></tr>
                  </thead>
                  <tbody>
                    @for (it of d.items; track it.id || (it.description + it.quantity)) {
                      <tr>
                        <td>{{ it.description }}</td>
                        <td>{{ qty(it.quantity) }}</td>
                        <td>{{ it.unit }}</td>
                      </tr>
                    } @empty {
                      <tr><td colspan="3">Aucun article.</td></tr>
                    }
                  </tbody>
                </table>
              </section>
              @if (d.approvals?.length) {
                <section class="bea-emp-fiche__block">
                  <h3>Circuit</h3>
                  <ol class="bea-emp-mini-tl">
                    @for (a of d.approvals; track a.id) {
                      <li [attr.data-tone]="tone(a.action)">
                        <strong>{{ actionLabel(a.action) }}</strong>
                        <span>{{ a.acted_at | date: 'dd/MM/yyyy HH:mm' }}</span>
                        @if (a.comment) { <em>{{ a.comment }}</em> }
                      </li>
                    }
                  </ol>
                </section>
              }
              @if (d.comments?.length) {
                <section class="bea-emp-fiche__block">
                  <h3>Conversation</h3>
                  <ul class="bea-emp-fiche__comments">
                    @for (c of d.comments; track c.id) {
                      <li><strong>{{ c.author_name || 'Utilisateur' }}</strong> {{ c.body }}</li>
                    }
                  </ul>
                </section>
              }
              <section class="bea-emp-fiche__block">
                <bea-mg-ged [moduleCode]="ctx.moduleCode()" entity="MG_EMPLOYEE_REQUEST" [entityId]="d.id" [reference]="d.request_number" [espaceCode]="ctx.espaceCode()" />
              </section>
            }
          </div>
          <div class="bea-emp-fiche__foot">
            @if (mode() === 'edit') {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="mode.set('view')">Annuler</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="saveEdit()">Enregistrer</button>
            } @else {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="pdf(d)">
                <mat-icon>picture_as_pdf</mat-icon> PDF
              </button>
              @if (canEdit(d.status)) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="mode.set('edit')">
                  <mat-icon>edit</mat-icon> Modifier
                </button>
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="submit(d.id)">
                  {{ d.status === 'A_COMPLETER' ? 'Compléter' : 'Soumettre' }}
                </button>
              }
              @if (canCancel(d.status)) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ask('cancel', d)">Désactiver</button>
              }
              @if (canDelete(d)) {
                <button type="button" class="bea-mg__btn bea-mg__btn--danger" (click)="ask('delete', d)">
                  <mat-icon>delete</mat-icon> Supprimer
                </button>
              }
            }
          </div>
        </aside>
      }

      @if (pdfPick(); as row) {
        <div class="bea-mg__backdrop bea-emp-confirm-backdrop" (click)="pdfPick.set(null)"></div>
        <aside class="bea-mg__modal bea-mg__modal--sm bea-emp-confirm" role="dialog" aria-label="Signataires du PDF">
          <div class="bea-mg__modal-head">
            <h2>Qui doit signer</h2>
          </div>
          <div class="bea-mg__modal-body">
            <p>Choix des visas sur {{ row.request_number }} avant le téléchargement.</p>
            <fieldset class="bea-emp-signpick bea-emp-signpick--dialog">
              @for (v of visaOptions; track v.id) {
                <label>
                  <input type="checkbox" [checked]="pdfVisas().includes(v.id)" (change)="togglePdfVisa(v.id)" />
                  {{ v.label }}
                </label>
              }
            </fieldset>
          </div>
          <div class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="pdfPick.set(null)">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="confirmPdf()">Télécharger</button>
          </div>
        </aside>
      }

      @if (confirm(); as c) {
        <div class="bea-mg__backdrop bea-emp-confirm-backdrop" (click)="confirm.set(null)"></div>
        <aside class="bea-mg__modal bea-mg__modal--sm bea-emp-confirm" role="dialog">
          <div class="bea-mg__modal-head">
            <h2>{{ c.kind === 'delete' ? 'Supprimer la demande' : 'Désactiver la demande' }}</h2>
          </div>
          <div class="bea-mg__modal-body">
            <p>{{ c.kind === 'delete'
              ? 'La demande ' + c.row.request_number + ' sera définitivement supprimée.'
              : 'La demande ' + c.row.request_number + ' sera désactivée. L’historique est conservé.' }}</p>
          </div>
          <div class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="confirm.set(null)">Annuler</button>
            <button
              type="button"
              class="bea-mg__btn"
              [class.bea-mg__btn--danger]="c.kind === 'delete'"
              [class.bea-mg__btn--primary]="c.kind !== 'delete'"
              (click)="confirmDo()"
            >Confirmer</button>
          </div>
        </aside>
      }
    </section>
  `,
})
export class EmpListeComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  readonly ctx = inject(DemandesContext);
  readonly rows = signal<RequestRow[]>([]);
  readonly detail = signal<RequestRow | null>(null);
  readonly mode = signal<'view' | 'edit'>('view');
  readonly confirm = signal<{ kind: 'delete' | 'cancel'; row: RequestRow } | null>(null);
  readonly pdfPick = signal<RequestRow | null>(null);
  readonly pdfVisas = signal<string[]>(['agence', 'mg']);
  readonly visaOptions = VISA_OPTIONS;
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly ok = signal('');
  readonly editItems = signal<ReqItem[]>([]);
  readonly statuts = ['BROUILLON', 'SOUMISE', 'RECUE', 'A_COMPLETER', 'A_REGROUPER', 'REFUSEE', 'SERVIE', 'ANNULEE'];
  q = '';
  statut = '';
  editTitle = '';
  editDesc = '';
  editPriority = 'NORMALE';
  editPeriod = '';

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((p) => {
      this.statut = p.get('statut') || '';
      this.load();
    });
  }
  label(s: string): string { return statusLabel(s); }
  prio(s: string): string { return priorityLabel(s); }
  tone(a: string): string { return ACTION_TONE[a] || 'info'; }
  actionLabel(a: string): string {
    const map: Record<string, string> = {
      CREATED: 'Brouillon créé',
      SUBMITTED: 'Soumise',
      RECEIVED: 'Reçue par les MG',
      REQUESTED_INFO: 'Complément demandé',
      VALIDATED: 'Validée',
      REJECTED: 'Refusée',
      CANCELLED: 'Désactivée',
      SERVED: 'Servie',
    };
    return map[a] || a;
  }
  canEdit(s: string): boolean { return EDITABLE.has(s); }
  canCancel(s: string): boolean { return CANCELLABLE.has(s); }
  canDelete(row: RequestRow): boolean { return canDeleteRequest(row); }
  qty(n: number): string { return formatQty(n); }

  load(): void {
    const params: Record<string, string | number> = { page: 1, size: 80 };
    const q = this.q.trim();
    if (q) params['q'] = q;
    if (this.statut) params['statut'] = this.statut;
    this.loading.set(true);
    this.api.get<{ items: RequestRow[] }>('/me/requests', params).subscribe({
      next: (r) => { this.rows.set(r.items ?? []); this.loading.set(false); },
      error: () => { this.erreur.set('Liste indisponible.'); this.loading.set(false); },
    });
  }
  open(id: string, mode: 'view' | 'edit'): void {
    this.api.get<RequestRow>(`/me/requests/${id}`).subscribe({
      next: (r) => {
        this.detail.set(r);
        this.mode.set(mode);
        this.editTitle = r.title;
        this.editDesc = r.description || '';
        this.editPriority = r.priority;
        this.editPeriod = r.period || '';
        this.editItems.set(r.items.map((it) => ({ ...it })));
      },
    });
  }
  close(): void { this.detail.set(null); }
  addEdit(): void { this.editItems.update((c) => [...c, emptyItem()]); }
  removeEdit(i: number): void { this.editItems.update((c) => c.filter((_, idx) => idx !== i)); }
  saveEdit(): void {
    const d = this.detail();
    if (!d) return;
    const items = this.editItems().filter((i) => i.description.trim());
    this.api.patch<RequestRow>(`/me/requests/${d.id}`, {
      title: this.editTitle,
      description: this.editDesc,
      priority: this.editPriority,
      period: this.editPeriod || null,
      items,
    }).subscribe({
      next: (r) => { this.detail.set(r); this.mode.set('view'); this.ok.set('Demande mise à jour.'); this.load(); },
      error: (e) => this.erreur.set(e?.error?.detail || 'Modification impossible'),
    });
  }
  submit(id: string): void {
    this.api.post<RequestRow>(`/me/requests/${id}/submit`, {}).subscribe({
      next: (r) => { this.ok.set(`Demande ${r.request_number} soumise.`); this.detail.set(null); this.load(); },
      error: (e) => this.erreur.set(e?.error?.detail || 'Soumission impossible'),
    });
  }
  pdf(row: RequestRow): void {
    this.pdfVisas.set(['agence', 'mg']);
    this.pdfPick.set(row);
  }
  togglePdfVisa(id: string): void {
    this.pdfVisas.update((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }
  confirmPdf(): void {
    const row = this.pdfPick();
    if (!row) return;
    const visas = this.pdfVisas();
    if (!visas.length) {
      this.erreur.set('Choisissez au moins un signataire.');
      return;
    }
    this.api.download(`/me/requests/${row.id}/pdf`, { visas: visas.join(',') }).subscribe({
      next: (blob) => {
        downloadBlob(blob, `${row.request_number}.pdf`);
        this.pdfPick.set(null);
      },
      error: () => this.erreur.set('PDF indisponible.'),
    });
  }
  ask(kind: 'delete' | 'cancel', row: RequestRow): void { this.confirm.set({ kind, row }); }
  confirmDo(): void {
    const c = this.confirm();
    if (!c) return;
    if (c.kind === 'delete') {
      this.api.delete(`/me/requests/${c.row.id}`).subscribe({
        next: () => { this.ok.set('Demande supprimée.'); this.confirm.set(null); this.detail.set(null); this.load(); },
        error: (e) => this.erreur.set(e?.error?.detail || 'Suppression impossible'),
      });
      return;
    }
    this.api.post<RequestRow>(`/me/requests/${c.row.id}/cancel`, { comment: 'Désactivée par le demandeur' }).subscribe({
      next: () => { this.ok.set('Demande désactivée.'); this.confirm.set(null); this.detail.set(null); this.load(); },
      error: (e) => this.erreur.set(e?.error?.detail || 'Désactivation impossible'),
    });
  }
}

@Component({
  selector: 'bea-emp-notifs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatIconModule],
  template: `
    <section class="bea-mg bea-emp">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">{{ ctx.kicker() }}</p>
          <h1>Notifications</h1>
          <p class="bea-mg__lead">Uniquement le circuit de vos demandes : soumission, réception, complément, validation, refus, service.</p>
        </div>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="readAll()">Tout marquer lu</button>
      </header>
      <div class="bea-emp-scroll bea-emp-notifscroll">
        <ul class="bea-emp-notifs">
          @for (n of items(); track n.id; let i = $index) {
            <li [class.is-unread]="!n.lu" [style.animation-delay.ms]="i * 40" (click)="open(n)">
              <span class="bea-emp-notifs__dot" [class.is-on]="!n.lu"></span>
              <div>
                <strong>{{ n.titre }}</strong>
                <p>{{ n.message }}</p>
                <time>{{ n.created_at | date: 'dd/MM/yyyy HH:mm' }}</time>
              </div>
            </li>
          }
        </ul>
        @if (!items().length) { <p class="bea-mg__empty">Aucune notification de demande.</p> }
      </div>
    </section>
  `,
})
export class EmpNotifsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly ctx = inject(DemandesContext);
  readonly items = signal<RequestNotif[]>([]);

  ngOnInit(): void { this.load(); }
  load(): void {
    this.api.get<{ items: RequestNotif[] }>('/notifications', {
      page: 1, size: 80, entity: 'mg_employee_request',
    }).subscribe({ next: (r) => this.items.set(r.items || []) });
  }
  open(n: RequestNotif): void {
    if (!n.lu) {
      this.api.patch(`/notifications/${n.id}/read`, {}).subscribe({ next: () => this.load() });
    }
    void this.router.navigate([this.ctx.base() + '/demandes']);
  }
  readAll(): void {
    this.api.post('/notifications/read-all?entity=mg_employee_request', {}).subscribe({ next: () => this.load() });
  }
}

@Component({
  selector: 'bea-emp-docs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, DocumentViewerComponent],
  template: `
    <section class="bea-mg bea-emp">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">{{ ctx.kicker() }}</p>
          <h1>Mes documents</h1>
          <p class="bea-mg__lead">Pièces GED liées à vos demandes : voir, modifier, désactiver ou supprimer.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (ok()) { <p class="bea-stock-page__ok">{{ ok() }}</p> }

      <div class="bea-mg__panel bea-emp-upload">
        <label class="bea-mg__field">
          <span>Joindre à une demande</span>
          <select [(ngModel)]="uploadRequestId" name="ureq">
            <option value="">Choisir une demande</option>
            @for (r of requests(); track r.id) {
              <option [value]="r.id">{{ r.request_number }} — {{ r.title }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__btn bea-mg__btn--primary">
          <mat-icon>upload_file</mat-icon> Ajouter un fichier
          <input type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.gif,.webp" (change)="onFile($event)" />
        </label>
      </div>

      <div class="bea-emp-docgrid">
        @for (d of docs(); track d.id; let i = $index) {
          <article class="bea-emp-doc" [class.is-off]="!!d.archived_at" [style.animation-delay.ms]="i * 40">
            <header>
              <mat-icon>{{ isPdf(d) ? 'picture_as_pdf' : 'image' }}</mat-icon>
              <div>
                <strong>{{ d.title || d.filename }}</strong>
                <code>{{ d.request_number }}</code>
              </div>
            </header>
            <p>{{ d.description || 'Aucune description. Ouvrez Modifier pour en ajouter une.' }}</p>
            <footer>
              <small>{{ size(d.size_bytes) }} · {{ d.created_at | date: 'dd/MM/yyyy' }}</small>
              @if (d.archived_at) { <span class="bea-emp-badge" data-status="ANNULEE">Désactivé</span> }
            </footer>
            <div class="bea-emp-actions">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="preview.set(d)">Voir</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="startEdit(d)">Modifier</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="toggleArchive(d)">
                {{ d.archived_at ? 'Réactiver' : 'Désactiver' }}
              </button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="askDelete(d)">Supprimer</button>
            </div>
          </article>
        }
      </div>
      @if (!docs().length) { <p class="bea-mg__empty">Aucun document attaché à vos demandes.</p> }

      @if (preview(); as p) {
        <div class="bea-mg__backdrop" (click)="preview.set(null)"></div>
        <aside class="bea-mg__modal bea-mg__modal--lg bea-emp-minipage" role="dialog">
          <div class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Fiche document</p>
              <h2>{{ p.title || p.filename }}</h2>
            </div>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="preview.set(null)">Fermer</button>
          </div>
          <div class="bea-mg__modal-body">
            <dl class="bea-emp-mini-meta">
              <div><dt>Demande</dt><dd>{{ p.request_number }} — {{ p.request_title }}</dd></div>
              <div><dt>Type</dt><dd>{{ p.doc_type || 'Pièce jointe' }}</dd></div>
              <div><dt>Fichier</dt><dd>{{ p.filename }} · {{ size(p.size_bytes) }}</dd></div>
              <div><dt>Description</dt><dd>{{ p.description || '—' }}</dd></div>
            </dl>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="viewerId.set(p.id)">
              Ouvrir la mini-page fichier
            </button>
          </div>
        </aside>
      }

      @if (editDoc(); as e) {
        <div class="bea-mg__backdrop" (click)="editDoc.set(null)"></div>
        <aside class="bea-mg__modal bea-mg__modal--sm" role="dialog">
          <div class="bea-mg__modal-head"><h2>Modifier le document</h2></div>
          <div class="bea-mg__modal-body">
            <label class="bea-mg__field"><span>Titre</span><input [(ngModel)]="editTitle" name="dtitle" /></label>
            <label class="bea-mg__field"><span>Description</span><textarea [(ngModel)]="editDesc" name="ddesc" rows="4"></textarea></label>
          </div>
          <div class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="editDoc.set(null)">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="saveDoc()">Enregistrer</button>
          </div>
        </aside>
      }

      <bea-document-viewer [documentId]="viewerId()" (closed)="viewerId.set(null)" />
    </section>
  `,
})
export class EmpDocsComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly ctx = inject(DemandesContext);
  readonly docs = signal<MineDocument[]>([]);
  readonly requests = signal<RequestRow[]>([]);
  readonly preview = signal<MineDocument | null>(null);
  readonly editDoc = signal<MineDocument | null>(null);
  readonly viewerId = signal<string | null>(null);
  readonly erreur = signal('');
  readonly ok = signal('');
  uploadRequestId = '';
  editTitle = '';
  editDesc = '';

  ngOnInit(): void {
    this.api.get<{ items: RequestRow[] }>('/me/requests', { page: 1, size: 80 }).subscribe({
      next: (r) => this.requests.set(r.items),
    });
    this.reload();
  }
  reload(): void {
    this.api.get<{ items: MineDocument[] }>('/me/requests/documents').subscribe({
      next: (r) => this.docs.set(r.items),
      error: () => this.erreur.set('Documents indisponibles.'),
    });
  }
  size(n: number): string { return fileSizeLabel(n); }
  isPdf(d: MineDocument): boolean {
    return (d.mime_type || '').includes('pdf') || (d.filename || '').toLowerCase().endsWith('.pdf');
  }
  onFile(ev: Event): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    (ev.target as HTMLInputElement).value = '';
    if (!file || !this.uploadRequestId) {
      this.erreur.set('Choisissez d’abord une demande, puis un fichier.');
      return;
    }
    const req = this.requests().find((r) => r.id === this.uploadRequestId);
    this.api.upload('/documents/from-operation', file, {
      espace_code: this.ctx.espaceCode(),
      module_code: this.ctx.moduleCode(),
      source_type: 'MG_EMPLOYEE_REQUEST',
      source_id: this.uploadRequestId,
      doc_type: 'JUSTIFICATIF',
      title: file.name,
      reference: req?.request_number || '',
    }).subscribe({
      next: () => { this.ok.set('Document ajouté.'); this.reload(); },
      error: () => this.erreur.set('Archivage refusé (permission ged.write ?).'),
    });
  }
  startEdit(d: MineDocument): void {
    this.editDoc.set(d);
    this.editTitle = d.title || d.filename;
    this.editDesc = d.description || '';
  }
  saveDoc(): void {
    const d = this.editDoc();
    if (!d) return;
    this.api.patch(`/documents/${d.id}`, { title: this.editTitle, description: this.editDesc }).subscribe({
      next: () => { this.ok.set('Document mis à jour.'); this.editDoc.set(null); this.reload(); },
      error: () => this.erreur.set('Modification refusée (permission ged.write ?).'),
    });
  }
  toggleArchive(d: MineDocument): void {
    this.api.patch(`/documents/${d.id}`, { archive: !d.archived_at }).subscribe({
      next: () => { this.ok.set(d.archived_at ? 'Document réactivé.' : 'Document désactivé.'); this.reload(); },
      error: () => this.erreur.set('Action refusée.'),
    });
  }
  askDelete(d: MineDocument): void {
    this.api.delete(`/ged/documents/${d.id}`).subscribe({
      next: () => { this.ok.set('Document supprimé.'); this.reload(); },
      error: () => this.erreur.set('Suppression refusée.'),
    });
  }
}

@Component({
  selector: 'bea-emp-historique',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, RouterLink],
  template: `
    <section class="bea-mg bea-emp">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">{{ ctx.kicker() }}</p>
          <h1>Historique</h1>
          <p class="bea-mg__lead">Chaque événement de vos demandes, dans l’ordre : création, soumission, réception, décision, service.</p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--primary" [routerLink]="ctx.base() + '/nouvelle'">Nouvelle demande</a>
      </header>
      <form class="bea-mg__search bea-emp-search" (ngSubmit)="$event.preventDefault()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input [(ngModel)]="q" name="hq" placeholder="Filtrer par n° ou titre…" />
        </label>
      </form>
      <div class="bea-emp-scroll bea-emp-histscroll">
        <ol class="bea-emp-tl">
          @for (e of filtered(); track e.id; let i = $index) {
            <li [attr.data-tone]="tone(e.action)" [style.animation-delay.ms]="i * 30">
              <span class="bea-emp-tl__dot"></span>
              <div>
                <strong>{{ e.action_label }}</strong>
                <p>
                  <code class="bea-mg__code">{{ e.request_number }}</code>
                  {{ e.title }}
                </p>
                @if (e.comment) { <em>{{ e.comment }}</em> }
                <small>
                  {{ e.actor_name || 'Système' }} · {{ e.acted_at | date: 'dd/MM/yyyy HH:mm' }}
                  · {{ label(e.status) }}
                </small>
              </div>
            </li>
          }
        </ol>
        @if (!filtered().length) { <p class="bea-mg__empty">Aucun événement pour le moment.</p> }
      </div>
    </section>
  `,
})
export class EmpHistoriqueComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly ctx = inject(DemandesContext);
  readonly events = signal<HistoryEvent[]>([]);
  q = '';

  ngOnInit(): void {
    this.api.get<{ items: HistoryEvent[] }>('/me/requests/history').subscribe({
      next: (r) => this.events.set(r.items),
    });
  }
  label(s: string): string { return statusLabel(s); }
  tone(a: string): string { return ACTION_TONE[a] || 'info'; }
  filtered(): HistoryEvent[] {
    const q = this.q.trim().toLowerCase();
    if (!q) return this.events();
    return this.events().filter((e) =>
      `${e.request_number} ${e.title} ${e.action_label}`.toLowerCase().includes(q)
    );
  }
}

