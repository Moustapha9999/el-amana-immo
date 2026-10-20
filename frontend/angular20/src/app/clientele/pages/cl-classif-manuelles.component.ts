import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, TraceClassification, dateHeureFr, n, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

type Manuelle = {
  racine_client: string; raison_sociale: string; niveau: string; source: string;
  motif_classement: string | null; classifie_le: string | null;
} & Partial<TraceClassification>;

@Component({
  selector: 'bea-cl-classif-manuelles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top">
        <h2>Décisions manuelles</h2>
        @if (store.cap().exporter) {
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter()" [disabled]="busy()"><mat-icon>download</mat-icon> Export de l’historique manuel</button>
        }
      </div>
      <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">Clients dont la classe retenue résulte d’une décision manuelle motivée. Ni l’import ni le moteur ne la remplacent ; la classe moteur reste affichée pour comparaison.</p>
      <div class="bea-cl-filters">
        <label>Classe retenue
          <select [(ngModel)]="niveau" (ngModelChange)="charger(1)">
            <option value="">Toutes</option>
            @for (nv of niveaux; track nv) { <option>{{ nv }}</option> }
          </select>
        </label>
        <label>Analyste KYC <input [(ngModel)]="analyste" (keyup.enter)="charger(1)" placeholder="Nom de l’analyste" /></label>
        <label>Recherche <input [(ngModel)]="q" (keyup.enter)="charger(1)" placeholder="Racine ou nom" /></label>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger(1)"><mat-icon>search</mat-icon> Rechercher</button>
      </div>
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table">
          <thead><tr><th class="c-sm">Racine</th><th class="c-lg">Identité</th><th class="c-sm">Classe retenue</th><th class="c-md">Classe moteur (au moment de la décision)</th><th class="c-md">Analyste KYC</th><th class="c-xl">Motif</th><th class="c-date">Date</th></tr></thead>
          <tbody>
            @for (i of items(); track i.racine_client) {
              <tr>
                <td><a [routerLink]="['/clientele/clients', i.racine_client]"><code>{{ i.racine_client }}</code></a></td>
                <td>{{ i.raison_sociale }}</td>
                <td><span class="bea-cl-badge" [attr.data-s]="i.niveau">{{ i.niveau }}</span> <small class="bea-cl-hint">{{ i.source }}</small></td>
                <td>@if (i.niveau_propose) { <span class="bea-cl-badge" [attr.data-s]="i.niveau_propose">{{ i.niveau_propose }}</span> <small class="bea-cl-hint">score {{ i.score_calcule ?? '—' }}</small> } @else { — }</td>
                <td>{{ i.analyste_kyc || '—' }}</td>
                <td>{{ i.motif_decision_manuelle || i.motif_classement || '—' }}</td>
                <td>{{ dh(i.classifie_le) }}</td>
              </tr>
            } @empty {
              <tr><td colspan="7"><div class="bea-cl-empty">Aucune décision manuelle pour ces filtres.</div></td></tr>
            }
          </tbody>
        </table>
      </div>
      @if (total() > taille) {
        <div class="bea-cl-pager">
          <span>{{ n(total()) }} décision(s) · page {{ page() }} / {{ n(nbPages()) }}</span>
          <span class="bea-cl-pager__btns">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="charger(page() - 1)"><mat-icon>chevron_left</mat-icon> Précédent</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= nbPages()" (click)="charger(page() + 1)">Suivant <mat-icon>chevron_right</mat-icon></button>
          </span>
        </div>
      }
    </section>
  `,
})
export class ClClassifManuellesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly items = signal<Manuelle[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly busy = signal(false);
  readonly taille = 50;
  readonly nbPages = computed(() => Math.max(1, Math.ceil(this.total() / this.taille)));
  readonly niveaux = ['FAIBLE', 'MOYEN', 'ELEVE', 'INTERDIT'];
  readonly n = n;
  readonly dh = dateHeureFr;
  niveau = '';
  analyste = '';
  q = '';

  ngOnInit(): void {
    this.charger(1);
  }

  charger(page: number): void {
    const params: Record<string, string | number> = { source: 'MANUELLES', page, taille: this.taille };
    if (this.niveau) params['niveau'] = this.niveau;
    if (this.analyste.trim()) params['analyste'] = this.analyste.trim();
    if (this.q.trim()) params['q'] = this.q.trim();
    this.api.get<{ total: number; items: Manuelle[] }>(`${CL_BASE}/classification`, params).subscribe({
      next: (r) => { this.items.set(r.items || []); this.total.set(r.total || 0); this.page.set(page); },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Décisions indisponibles')),
    });
  }

  exporter(): void {
    const params: Record<string, string> = { source: 'MANUELLES' };
    if (this.analyste.trim()) params['analyste'] = this.analyste.trim();
    if (this.q.trim()) params['q'] = this.q.trim();
    this.busy.set(true);
    this.api.download(`${CL_BASE}/classification/historique.xlsx`, params).subscribe({
      next: (b) => { this.busy.set(false); telecharger(b, `decisions-manuelles-${new Date().toISOString().slice(0, 10)}.xlsx`); },
      error: (e) => { this.busy.set(false); void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible')); },
    });
  }
}
