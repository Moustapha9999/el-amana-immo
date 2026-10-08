import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateHeureFr, n, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface ImportOpt {
  id: string; fichier_nom: string; date_extraction: string | null; importe_le: string | null;
  nb_clients: number; nb_comptes: number; snapshot: boolean;
}
interface Synthese {
  clients_nouveaux: number; clients_absents: number; clients_modifies: number; clients_inchanges: number;
  comptes_nouveaux: number; comptes_absents: number; comptes_modifies: number; comptes_inchanges: number;
  comptes_fermes: number; anomalies: number; regle?: string;
}
interface Rapprochement {
  id: string; import_a: ImportOpt; import_b: ImportOpt; synthese: Synthese; created_at: string | null;
}
interface Ecart {
  objet: string; categorie: string; racine_client: string | null; rib: string | null;
  libelle_champ: string | null; valeur_a: string | null; valeur_b: string | null; code: string | null;
}

@Component({
  selector: 'bea-cl-rapprochements',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Imports ORION</p>
          <h1>Rapprochement d’extractions</h1>
          <p class="bea-cl-head__sub">Import A vs import B. L’absence d’une ligne n’est pas une suppression : le client reste en base.</p>
        </div>
      </header>

      @if (store.cap().rapprochement_executer) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Comparer</h2></div>
          <div class="bea-cl-filters">
            <label>Import A (avant)
              <select [(ngModel)]="importA">
                <option value="">—</option>
                @for (i of imports(); track i.id) {
                  <option [value]="i.id" [disabled]="!i.snapshot">{{ i.fichier_nom }} ({{ i.date_extraction || 'sans date' }})</option>
                }
              </select>
            </label>
            <label>Import B (après)
              <select [(ngModel)]="importB">
                <option value="">—</option>
                @for (i of imports(); track i.id) {
                  <option [value]="i.id" [disabled]="!i.snapshot">{{ i.fichier_nom }} ({{ i.date_extraction || 'sans date' }})</option>
                }
              </select>
            </label>
          </div>
          <div style="padding:0 1rem 1rem">
            <button type="button" class="bea-mg__btn" [disabled]="!importA || !importB || importA===importB || busy()" (click)="calculer()">
              <mat-icon>compare_arrows</mat-icon> Calculer
            </button>
          </div>
        </section>
      }

      @if (courant(); as r) {
        <div class="bea-cl-kpis">
          <div class="bea-cl-kpi"><span>Nouveaux clients</span><strong>{{ n(r.synthese.clients_nouveaux) }}</strong></div>
          <div class="bea-cl-kpi"><span>Clients modifiés</span><strong>{{ n(r.synthese.clients_modifies) }}</strong></div>
          <div class="bea-cl-kpi"><span>Absents extraction</span><strong>{{ n(r.synthese.clients_absents) }}</strong></div>
          <div class="bea-cl-kpi"><span>Inchangés</span><strong>{{ n(r.synthese.clients_inchanges) }}</strong></div>
          <div class="bea-cl-kpi"><span>Comptes ajoutés</span><strong>{{ n(r.synthese.comptes_nouveaux) }}</strong></div>
          <div class="bea-cl-kpi"><span>Comptes fermés</span><strong>{{ n(r.synthese.comptes_fermes) }}</strong></div>
          <div class="bea-cl-kpi"><span>Anomalies</span><strong>{{ n(r.synthese.anomalies) }}</strong></div>
        </div>
        <p class="bea-cl-note bea-cl-note--info"><mat-icon>info</mat-icon>{{ r.synthese.regle }}</p>
        @if (store.cap().exporter) {
          <div class="bea-mg__actions" style="margin-bottom:0.8rem">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
          </div>
        }
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Écarts</h2>
            <div class="bea-mg__actions">
              @for (c of cats; track c.id) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [class.is-on]="cat()===c.id" (click)="filtrer(c.id)">{{ c.label }}</button>
              }
            </div>
          </div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th>Objet</th><th>Racine</th><th>RIB</th><th>Champ</th><th>A</th><th>B</th></tr></thead>
              <tbody>
                @for (e of ecarts(); track $index) {
                  <tr>
                    <td><span class="bea-cl-badge" [attr.data-s]="e.categorie">{{ e.categorie }}</span></td>
                    <td><a [routerLink]="['/clientele/clients', e.racine_client]"><code>{{ e.racine_client }}</code></a></td>
                    <td><code>{{ e.rib || '—' }}</code></td>
                    <td>{{ e.libelle_champ || '—' }}</td>
                    <td>{{ e.valeur_a || '—' }}</td>
                    <td>{{ e.valeur_b || '—' }}</td>
                  </tr>
                } @empty {
                  <tr><td colspan="6"><div class="bea-cl-empty">Inchangés : non listés (voir synthèse).</div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </section>
      }

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Historique</h2></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>A</th><th>B</th><th>Nouveaux</th><th>Absents</th><th>Le</th></tr></thead>
            <tbody>
              @for (h of histo(); track h.id) {
                <tr style="cursor:pointer" (click)="ouvrir(h)">
                  <td>{{ h.import_a.fichier_nom }}</td>
                  <td>{{ h.import_b.fichier_nom }}</td>
                  <td>{{ n(h.synthese.clients_nouveaux) }}</td>
                  <td>{{ n(h.synthese.clients_absents) }}</td>
                  <td>{{ dh(h.created_at) }}</td>
                </tr>
              } @empty {
                <tr><td colspan="5"><div class="bea-cl-empty">Aucun rapprochement.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `,
})
export class ClRapprochementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly imports = signal<ImportOpt[]>([]);
  readonly histo = signal<Rapprochement[]>([]);
  readonly courant = signal<Rapprochement | null>(null);
  readonly ecarts = signal<Ecart[]>([]);
  readonly cat = signal('NOUVEAU');
  readonly busy = signal(false);
  readonly cats = [
    { id: 'NOUVEAU', label: 'Nouveaux' },
    { id: 'MODIFIE', label: 'Modifiés' },
    { id: 'ABSENT_EXTRACTION', label: 'Absents extraction' },
    { id: 'ANOMALIE', label: 'Anomalies' },
  ];
  importA = '';
  importB = '';
  readonly n = n;
  readonly dh = dateHeureFr;

  ngOnInit(): void {
    this.store.charger();
    this.api.get<ImportOpt[]>(`${CL_BASE}/rapprochements/imports`).subscribe({
      next: (r) => this.imports.set(r),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Imports indisponibles')),
    });
    this.api.get<Rapprochement[]>(`${CL_BASE}/rapprochements`).subscribe({
      next: (r) => this.histo.set(r),
      error: () => this.histo.set([]),
    });
  }

  calculer(): void {
    this.feedback.run(
      () => this.api.post<Rapprochement>(`${CL_BASE}/rapprochements`, {
        import_a_id: this.importA, import_b_id: this.importB,
      }),
      { busy: this.busy, loading: 'Calcul…', success: { title: 'Rapprochement calculé' }, errorTitle: 'Calcul impossible' },
    ).subscribe((r) => this.ouvrir(r));
  }

  ouvrir(r: Rapprochement): void {
    this.courant.set(r);
    this.filtrer(this.cat());
  }

  filtrer(cat: string): void {
    this.cat.set(cat);
    const r = this.courant();
    if (!r) return;
    this.api.get<{ items: Ecart[] }>(`${CL_BASE}/rapprochements/${r.id}/ecarts`, { categorie: cat, taille: 200 }).subscribe({
      next: (p) => this.ecarts.set(p.items),
      error: () => this.ecarts.set([]),
    });
  }

  exporter(fmt: 'xlsx' | 'pdf'): void {
    const r = this.courant();
    if (!r) return;
    this.api.download(`${CL_BASE}/rapprochements/${r.id}/export.${fmt}`).subscribe({
      next: (b) => telecharger(b, `rapprochement.${fmt}`),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export impossible')),
    });
  }
}
