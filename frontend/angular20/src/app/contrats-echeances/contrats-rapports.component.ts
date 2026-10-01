import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { ContratsConfig, telechargerBlob } from './contrats.models';

interface ReportJson {
  key: string;
  title: string;
  headers: string[];
  rows: (string | number)[][];
  count: number;
}

interface RapportDef {
  key: string;
  label: string;
  groupe: 'Registre' | 'Financier' | 'Renouvellements';
  icon: string;
  annee?: boolean;
  periode?: boolean;
  description: string;
}

const RAPPORTS: RapportDef[] = [
  { key: 'liste', label: 'Liste des contrats', groupe: 'Registre', icon: 'list_alt', description: 'Registre complet (hors supprimés).' },
  { key: 'actifs', label: 'Contrats actifs', groupe: 'Registre', icon: 'verified', description: 'Contrats en vigueur.' },
  { key: 'expires', label: 'Contrats expirés', groupe: 'Registre', icon: 'event_busy', description: 'Contrats arrivés à terme.' },
  { key: 'echeances', label: 'Échéances à 90 jours', groupe: 'Registre', icon: 'schedule', description: 'Échéancier consolidé à venir.' },
  { key: 'paiements', label: 'Rapprochement des paiements', groupe: 'Financier', icon: 'payments', annee: true, description: 'Prévu / payé / écart par règlement.' },
  { key: 'financier_fournisseur', label: 'Engagements par fournisseur', groupe: 'Financier', icon: 'storefront', annee: true, description: 'Montants engagés, payés et restant dus.' },
  { key: 'financier_agence', label: 'Engagements par agence', groupe: 'Financier', icon: 'apartment', annee: true, description: 'Répartition par agence / entité.' },
  { key: 'financier_periode', label: 'Engagements mensuels', groupe: 'Financier', icon: 'calendar_month', annee: true, description: 'Prévisions budgétaires mois par mois.' },
  { key: 'renouvellements', label: 'Contrats à renégocier', groupe: 'Renouvellements', icon: 'autorenew', periode: true, description: 'Fins de contrat du trimestre ou de l’année.' },
];

@Component({
  selector: 'bea-contrats-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting</p>
          <h1>Rapports contrats</h1>
          <p class="bea-ct-head__sub">Rapports financiers, registre et renouvellements — exports Excel et PDF.</p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/contrats-echeances/dashboard"><mat-icon>dashboard</mat-icon> Tableau de bord</a>
      </header>

      <div class="bea-ct-reports">
        @for (g of groupes; track g) {
          <div class="bea-ct-reports__group">
            <h2>{{ g }}</h2>
            @for (r of parGroupe(g); track r.key) {
              <button type="button" class="bea-ct-reports__item" [class.is-on]="courant().key === r.key" (click)="choisir(r.key)">
                <mat-icon>{{ r.icon }}</mat-icon>
                <span><strong>{{ r.label }}</strong><small>{{ r.description }}</small></span>
              </button>
            }
          </div>
        }
      </div>

      <form class="bea-mg__search" [formGroup]="filters">
        @if (courant().annee) {
          <label class="bea-mg__field">Année
            <select formControlName="annee" (change)="load()">
              @for (a of annees; track a) { <option [value]="a">{{ a }}</option> }
            </select>
          </label>
        }
        @if (courant().periode) {
          <label class="bea-mg__field">Période
            <select formControlName="periode" (change)="load()">
              <option value="trimestre">Trimestre à venir</option>
              <option value="annee">Année à venir</option>
            </select>
          </label>
        }
        <div class="bea-ct-filters__btns">
          @if (peutExporter()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!report()?.count || busy()" (click)="download('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!report()?.count || busy()" (click)="download('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
          }
        </div>
      </form>

      @if (report(); as r) {
        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-mg__panel-top"><h2>{{ r.title }} <small>{{ r.count }}</small></h2></div>
          @if (r.count === 0) {
            <div class="bea-ct-empty"><mat-icon>assessment</mat-icon><p>Aucune donnée pour ce rapport.</p></div>
          } @else {
            <div class="bea-mg__table-scroll bea-ct-table-wrap">
              <table class="bea-mg__table bea-ct-table">
                <thead><tr>@for (h of r.headers; track $index) { <th>{{ h }}</th> }</tr></thead>
                <tbody>
                  @for (row of r.rows; track $index; let i = $index) {
                    <tr class="bea-ct-row" [class.bea-ct-row--total]="row[0] === 'TOTAL'" [style.animation-delay.ms]="i < 20 ? i * 25 : 0">
                      @for (cell of row; track $index) { <td [class.is-num]="isNum(cell)">{{ format(cell) }}</td> }
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </div>
      } @else {
        <div class="bea-ct-view__loading"><span class="bea-ct-view__spinner"></span> Chargement du rapport…</div>
      }
    </section>
  `,
})
export class ContratsRapportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly feedback = inject(FeedbackService);

  readonly groupes = ['Registre', 'Financier', 'Renouvellements'] as const;
  readonly annees = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() + 1 - i);
  readonly filters = this.fb.nonNullable.group({ key: ['liste'], annee: [String(new Date().getFullYear())], periode: ['trimestre'] });
  readonly report = signal<ReportJson | null>(null);
  readonly config = signal<ContratsConfig | null>(null);
  readonly busy = signal(false);
  readonly cle = signal('liste');
  readonly courant = computed(() => RAPPORTS.find((r) => r.key === this.cle()) ?? RAPPORTS[0]);
  readonly peutExporter = computed(() => !!this.config()?.capacites.export);

  ngOnInit(): void {
    this.api.get<ContratsConfig>('/mg/contrats/config').subscribe({ next: (c) => this.config.set(c), error: () => undefined });
    this.load();
  }

  parGroupe(g: string): RapportDef[] {
    return RAPPORTS.filter((r) => r.groupe === g);
  }

  choisir(key: string): void {
    this.cle.set(key);
    this.filters.controls.key.setValue(key);
    this.load();
  }

  private params(fmt: string): Record<string, string> {
    const raw = this.filters.getRawValue();
    const p: Record<string, string> = { fmt };
    if (this.courant().annee) p['annee'] = raw.annee;
    if (this.courant().periode) p['periode'] = raw.periode;
    return p;
  }

  load(): void {
    this.report.set(null);
    const key = this.cle();
    this.api.get<ReportJson>(`/mg/contrats/rapports/${key}`, this.params('json')).subscribe({
      next: (r) => this.report.set(r),
      error: (e) => void describeApiErrorAsync(e).then((info) => this.feedback.apiError(info, 'Rapport indisponible')),
    });
  }

  download(fmt: 'xlsx' | 'pdf'): void {
    const key = this.cle();
    const nom = `contrats-${key}.${fmt}`;
    this.feedback
      .run(() => this.api.download(`/mg/contrats/rapports/${key}`, this.params(fmt)), {
        loading: 'Génération de l’export…',
        busy: this.busy,
        errorTitle: 'Export impossible',
        success: (blob) => {
          telechargerBlob(blob, nom);
          return { title: 'Export prêt', details: [{ label: 'Fichier', value: nom }] };
        },
      })
      .subscribe();
  }

  isNum(cell: string | number): boolean {
    return typeof cell === 'number';
  }

  format(cell: string | number): string {
    if (typeof cell === 'number') return cell.toLocaleString('fr-FR', { minimumFractionDigits: Number.isInteger(cell) ? 0 : 2, maximumFractionDigits: 2 });
    return cell ?? '';
  }
}
