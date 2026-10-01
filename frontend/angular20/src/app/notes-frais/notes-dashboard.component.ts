import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { NoteApercuComponent } from './note-apercu.component';
import { Note, noteStatutLabel, noteStatutTone } from './notes-frais.shared';

interface Dashboard {
  total: number;
  brouillons: number;
  soumises: number;
  en_controle: number;
  en_visa: number;
  validees: number;
  a_payer: number;
  partiellement_payees: number;
  payees: number;
  rejetees: number;
  montant_total: number;
  montant_a_payer: number;
  montant_paye: number;
}

interface AnnuelReport {
  rows: (string | number)[][];
}

interface Mois {
  label: string;
  nb: number;
  montant: number;
  paye: number;
}

interface Etape {
  label: string;
  value: number;
  tone: string;
}

@Component({
  selector: 'bea-notes-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, MontantPipe, DatePipe, NoteApercuComponent],
  template: `
    <section class="bea-mg bea-nf">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>Notes de frais</h1>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/notes-frais/rapports">
            <mat-icon>insights</mat-icon> Rapports
          </a>
          <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/notes-frais/notes">
            <mat-icon>list_alt</mat-icon> Registre
          </a>
        </div>
      </header>

      @if (dash(); as d) {
        <div class="bea-nfd-kpi">
          <article class="bea-nfd-kpi__card" data-tone="blue">
            <span class="bea-nfd-kpi__icon"><mat-icon>receipt_long</mat-icon></span>
            <div>
              <p>Notes</p>
              <strong>{{ d.total }}</strong>
              <small>{{ enCours() }} en cours de traitement</small>
            </div>
          </article>
          <article class="bea-nfd-kpi__card" data-tone="indigo">
            <span class="bea-nfd-kpi__icon"><mat-icon>account_balance_wallet</mat-icon></span>
            <div>
              <p>Montant total</p>
              <strong>{{ d.montant_total | montant }} <em>MRU</em></strong>
              <small>Moyenne {{ moyenne() | montant }} MRU / note</small>
            </div>
          </article>
          <article class="bea-nfd-kpi__card" data-tone="orange">
            <span class="bea-nfd-kpi__icon"><mat-icon>schedule</mat-icon></span>
            <div>
              <p>Reste à payer</p>
              <strong>{{ d.montant_a_payer | montant }} <em>MRU</em></strong>
              <small>{{ d.a_payer + d.partiellement_payees }} note(s) en attente de règlement</small>
            </div>
          </article>
          <article class="bea-nfd-kpi__card" data-tone="green">
            <span class="bea-nfd-kpi__icon"><mat-icon>task_alt</mat-icon></span>
            <div>
              <p>Payé</p>
              <strong>{{ d.montant_paye | montant }} <em>MRU</em></strong>
              <small>{{ tauxPaye() }} % du montant total réglé</small>
            </div>
            <div class="bea-nfd-kpi__bar" aria-hidden="true"><i [style.width.%]="tauxPaye()"></i></div>
          </article>
        </div>

        <div class="bea-nfd-grid">
          <div class="bea-mg__panel bea-nfd-panel">
            <div class="bea-mg__panel-top">
              <h2>Évolution mensuelle {{ annee }}</h2>
              <span class="bea-mg__count">{{ montantAnnee() | montant }} MRU</span>
            </div>
            @if (mois().length) {
              <div class="bea-nfd-chart">
                @for (m of mois(); track m.label; let i = $index) {
                  <div
                    class="bea-nfd-chart__col"
                    [class.is-current]="i === moisCourant"
                    [title]="m.label + ' : ' + m.nb + ' note(s) · ' + (m.montant | montant) + ' MRU'"
                  >
                    <span class="bea-nfd-chart__val">{{ m.nb || '' }}</span>
                    <div class="bea-nfd-chart__track">
                      <i class="bea-nfd-chart__bar" [style.height.%]="barHeight(m.montant)" [style.animation-delay.ms]="i * 40"></i>
                      <i class="bea-nfd-chart__bar bea-nfd-chart__bar--paid" [style.height.%]="barHeight(m.paye)" [style.animation-delay.ms]="i * 40 + 120"></i>
                    </div>
                    <span class="bea-nfd-chart__label">{{ m.label.slice(0, 3) }}</span>
                  </div>
                }
              </div>
              <div class="bea-nfd-legend">
                <span><i></i> Montant demandé</span>
                <span><i class="is-paid"></i> Montant payé</span>
              </div>
            } @else {
              <div class="bea-mg__empty"><mat-icon>bar_chart</mat-icon><p>Pas encore de données pour {{ annee }}.</p></div>
            }
          </div>

          <div class="bea-mg__panel bea-nfd-panel">
            <div class="bea-mg__panel-top">
              <h2>Répartition du workflow</h2>
              <span class="bea-mg__count">{{ d.total }} note(s)</span>
            </div>
            <ul class="bea-nfd-flow">
              @for (e of etapes(); track e.label; let i = $index) {
                <li [style.animation-delay.ms]="i * 45">
                  <span class="bea-nfd-flow__label"><i class="bea-nf-view__dot" [attr.data-tone]="e.tone"></i>{{ e.label }}</span>
                  <span class="bea-nfd-flow__track"><i [attr.data-tone]="e.tone" [style.width.%]="part(e.value)"></i></span>
                  <strong>{{ e.value }}</strong>
                </li>
              }
            </ul>
          </div>
        </div>
      }

      <div class="bea-mg__panel bea-nfd-panel">
        <div class="bea-mg__panel-top">
          <h2>Dernières notes</h2>
          <a class="bea-mg__btn bea-mg__btn--ghost bea-nfd-more" routerLink="/notes-frais/notes">
            Voir le registre <mat-icon>arrow_forward</mat-icon>
          </a>
        </div>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table bea-nf-table">
            <thead>
              <tr>
                <th>Référence</th><th>Date</th><th>Demandeur</th><th>Intitulé</th>
                <th class="is-num">Montant</th><th>Statut</th><th class="bea-mg__th-actions"></th>
              </tr>
            </thead>
            <tbody>
              @for (n of recentes(); track n.id; let i = $index) {
                <tr class="bea-nf-row" [style.animation-delay.ms]="i * 40" (dblclick)="apercuId.set(n.id)">
                  <td class="is-nowrap"><code class="bea-mg__code">{{ n.reference }}</code></td>
                  <td class="is-nowrap">{{ n.date_demande | date: 'dd/MM/yyyy' }}</td>
                  <td><strong class="bea-nf-cell__main">{{ n.demandeur_nom || '—' }}</strong></td>
                  <td>{{ n.agence_libelle_snapshot || '—' }}</td>
                  <td class="is-num is-nowrap"><strong>{{ n.total_mru | montant }}</strong></td>
                  <td class="is-nowrap"><span class="bea-nf-badge" [attr.data-tone]="tone(n.statut)">{{ label(n.statut) }}</span></td>
                  <td class="bea-mg__actions-cell">
                    <button type="button" class="bea-mg__icon-btn" title="Voir le détail" (click)="apercuId.set(n.id)">
                      <mat-icon>visibility</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7">
                    <div class="bea-mg__empty">
                      <mat-icon>receipt_long</mat-icon>
                      <p>Aucune note de frais pour le moment.</p>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      @if (apercuId(); as id) {
        <bea-note-apercu [noteId]="id" (closed)="apercuId.set(null)" (deleted)="onDeleted()" />
      }
    </section>
  `,
})
export class NotesDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly dash = signal<Dashboard | null>(null);
  readonly mois = signal<Mois[]>([]);
  readonly recentes = signal<Note[]>([]);
  readonly apercuId = signal<string | null>(null);
  readonly erreur = feedbackSignal('error', '');

  readonly annee = new Date().getFullYear();
  readonly moisCourant = new Date().getMonth();
  readonly label = noteStatutLabel;
  readonly tone = noteStatutTone;
  readonly enCours = computed(() => {
    const d = this.dash();
    return d ? d.soumises + d.en_controle + d.en_visa + d.validees + d.a_payer + d.partiellement_payees : 0;
  });
  readonly moyenne = computed(() => {
    const d = this.dash();
    return d && d.total ? Number(d.montant_total) / d.total : 0;
  });
  readonly tauxPaye = computed(() => {
    const d = this.dash();
    if (!d || !Number(d.montant_total)) return 0;
    return Math.min(100, Math.round((Number(d.montant_paye) / Number(d.montant_total)) * 100));
  });
  readonly etapes = computed<Etape[]>(() => {
    const d = this.dash();
    if (!d) return [];
    return [
      { label: 'Brouillons', value: d.brouillons, tone: 'draft' },
      { label: 'Soumises', value: d.soumises, tone: 'progress' },
      { label: 'En contrôle', value: d.en_controle, tone: 'progress' },
      { label: 'Visas', value: d.en_visa, tone: 'progress' },
      { label: 'Validées', value: d.validees, tone: 'ok' },
      { label: 'À payer', value: d.a_payer + d.partiellement_payees, tone: 'warn' },
      { label: 'Payées', value: d.payees, tone: 'ok' },
      { label: 'Rejetées', value: d.rejetees, tone: 'danger' },
    ];
  });
  readonly montantAnnee = computed(() => this.mois().reduce((acc, m) => acc + m.montant, 0));
  private readonly maxMois = computed(() => Math.max(0, ...this.mois().map((m) => m.montant)));

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.get<Dashboard>('/mg/notes-frais/dashboard').subscribe({
      next: (d) => this.dash.set(d),
      error: () => this.erreur.set('Dashboard indisponible'),
    });
    this.api.get<{ items: Note[] }>('/mg/notes-frais/notes', { page: 1, size: 6 }).subscribe({
      next: (r) => this.recentes.set(r.items),
      error: () => this.recentes.set([]),
    });
    this.api
      .get<AnnuelReport>('/mg/notes-frais/rapports/annuel', { format: 'json', annee: this.annee })
      .subscribe({
        next: (r) => {
          const rows = r.rows.map((row) => ({
            label: String(row[0]),
            nb: Number(row[1]) || 0,
            montant: Number(row[2]) || 0,
            paye: Number(row[3]) || 0,
          }));
          this.mois.set(rows.some((m) => m.nb > 0) ? rows : []);
        },
        error: () => this.mois.set([]),
      });
  }

  barHeight(value: number): number {
    const max = this.maxMois();
    return max ? Math.max(value > 0 ? 3 : 0, (value / max) * 100) : 0;
  }

  part(value: number): number {
    const total = this.dash()?.total || 0;
    return total ? Math.round((value / total) * 100) : 0;
  }

  onDeleted(): void {
    this.apercuId.set(null);
    this.load();
  }
}
