import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, MODES_DECISION, TraceClassification, dateHeureFr, n, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

type Entree = {
  id: string; racine_client: string; raison_sociale: string | null; profil: string | null;
  ancienne_classe: string | null; nouvelle_classe: string | null; motif_classement: string | null;
  source: string | null; utilisateur: string | null; date: string | null;
} & Partial<TraceClassification>;

@Component({
  selector: 'bea-cl-classif-historique',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top">
        <h2>Historique des classifications</h2>
        @if (store.cap().exporter) {
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter()" [disabled]="busy()"><mat-icon>download</mat-icon> Export Excel</button>
        }
      </div>
      <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">Historique en ajout seul : chaque changement de classe est conservé (ancienne et nouvelle classe, classe moteur, mode, motif, analyste, auteur, date, lot et ligne du fichier).</p>
      <div class="bea-cl-filters">
        <label>Source
          <select [(ngModel)]="source" (ngModelChange)="charger(1)">
            <option value="">Toutes</option><option value="MANUELLES">Décisions manuelles</option>
          </select>
        </label>
        <label>Analyste KYC <input [(ngModel)]="analyste" (keyup.enter)="charger(1)" placeholder="Nom de l’analyste" /></label>
        <label>Du <input type="date" [(ngModel)]="du" (change)="charger(1)" /></label>
        <label>Au <input type="date" [(ngModel)]="au" (change)="charger(1)" /></label>
        <label>Recherche <input [(ngModel)]="q" (keyup.enter)="charger(1)" placeholder="Racine ou nom" /></label>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger(1)"><mat-icon>search</mat-icon> Rechercher</button>
      </div>
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table">
          <thead><tr><th>Date</th><th>Racine</th><th>Identité</th><th>Ancienne</th><th>Nouvelle</th><th>Classe moteur</th><th>Mode</th><th>Motif</th><th>Analyste KYC</th><th>Auteur</th><th>Lot / ligne</th></tr></thead>
          <tbody>
            @for (h of items(); track h.id) {
              <tr>
                <td>{{ dh(h.date) }}</td>
                <td><a [routerLink]="['/clientele/clients', h.racine_client]"><code>{{ h.racine_client }}</code></a></td>
                <td>{{ h.raison_sociale || '—' }} @if (h.profil) { <small class="bea-cl-hint">{{ h.profil }}</small> }</td>
                <td>@if (h.ancienne_classe) { <span class="bea-cl-badge" [attr.data-s]="h.ancienne_classe">{{ h.ancienne_classe }}</span> } @else { — }</td>
                <td>@if (h.nouvelle_classe) { <span class="bea-cl-badge" [attr.data-s]="h.nouvelle_classe">{{ h.nouvelle_classe }}</span> } @else { — }</td>
                <td>{{ h.niveau_propose || '—' }} @if (h.score_calcule !== null && h.score_calcule !== undefined) { <small class="bea-cl-hint">score {{ h.score_calcule }}</small> }</td>
                <td>{{ modes[h.mode_decision || ''] || h.source || '—' }}</td>
                <td>{{ h.motif_decision_manuelle || h.motif_classement || '—' }}</td>
                <td>{{ h.analyste_kyc || '—' }}</td>
                <td>{{ h.utilisateur || '—' }}</td>
                <td>@if (h.lot_id) { <a [routerLink]="['/clientele/classification-lot']" [queryParams]="{ lot: h.lot_id }">lot</a> · {{ h.ligne_source ?? '—' }} } @else { — }</td>
              </tr>
            } @empty {
              <tr><td colspan="11"><div class="bea-cl-empty">Aucune entrée pour ces filtres.</div></td></tr>
            }
          </tbody>
        </table>
      </div>
      @if (total() > taille) {
        <div class="bea-cl-pager">
          <span>{{ n(total()) }} entrée(s) · page {{ page() }} / {{ n(nbPages()) }}</span>
          <span class="bea-cl-pager__btns">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="charger(page() - 1)"><mat-icon>chevron_left</mat-icon> Précédent</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= nbPages()" (click)="charger(page() + 1)">Suivant <mat-icon>chevron_right</mat-icon></button>
          </span>
        </div>
      }
    </section>
  `,
})
export class ClClassifHistoriqueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly items = signal<Entree[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly busy = signal(false);
  readonly taille = 50;
  readonly nbPages = computed(() => Math.max(1, Math.ceil(this.total() / this.taille)));
  readonly modes = MODES_DECISION;
  readonly n = n;
  readonly dh = dateHeureFr;
  source = '';
  analyste = '';
  du = '';
  au = '';
  q = '';

  ngOnInit(): void {
    this.charger(1);
  }

  private filtres(): Record<string, string> {
    const f: Record<string, string> = {};
    if (this.source) f['source'] = this.source;
    if (this.analyste.trim()) f['analyste'] = this.analyste.trim();
    if (this.du) f['du'] = this.du;
    if (this.au) f['au'] = this.au;
    if (this.q.trim()) f['q'] = this.q.trim();
    return f;
  }

  charger(page: number): void {
    this.api.get<{ total: number; items: Entree[] }>(`${CL_BASE}/classification/historique`, { ...this.filtres(), page, taille: this.taille }).subscribe({
      next: (r) => { this.items.set(r.items || []); this.total.set(r.total || 0); this.page.set(page); },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Historique indisponible')),
    });
  }

  exporter(): void {
    this.busy.set(true);
    this.api.download(`${CL_BASE}/classification/historique.xlsx`, this.filtres()).subscribe({
      next: (b) => { this.busy.set(false); telecharger(b, `historique-classifications-${new Date().toISOString().slice(0, 10)}.xlsx`); },
      error: (e) => { this.busy.set(false); void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible')); },
    });
  }
}
