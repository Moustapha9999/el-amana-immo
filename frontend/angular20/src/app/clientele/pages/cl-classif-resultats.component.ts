import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, CalculMoteur, TraceClassification, dateHeureFr, n, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface Resultat {
  racine_client: string; raison_sociale: string | null; profil: string | null; ecart: boolean;
  calcul: CalculMoteur | null;
  retenue: ({ niveau: string; source: string; classifie_le: string | null } & Partial<TraceClassification>) | null;
}

@Component({
  selector: 'bea-cl-classif-resultats',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top">
        <h2>Résultats du moteur</h2>
        @if (store.cap().exporter) {
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter()" [disabled]="busy()"><mat-icon>download</mat-icon> Export Excel</button>
        }
      </div>
      <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">Dernier calcul du moteur par client, affiché à côté de la classe retenue. Le moteur ne remplace jamais une classe retenue : un écart est signalé pour décision.</p>
      <div class="bea-cl-filters">
        <label>Écart
          <select [(ngModel)]="ecart" (ngModelChange)="charger(1)">
            <option value="">Tous</option><option value="true">Avec écart</option><option value="false">Sans écart</option>
          </select>
        </label>
        <label>Classe moteur
          <select [(ngModel)]="niveau" (ngModelChange)="charger(1)">
            <option value="">Toutes</option>
            @for (nv of niveaux; track nv) { <option>{{ nv }}</option> }
          </select>
        </label>
        <label>Classe retenue
          <select [(ngModel)]="source" (ngModelChange)="charger(1)">
            <option value="">Toutes sources</option><option value="MANUELLES">Décisions manuelles</option>
          </select>
        </label>
        <label>Recherche <input [(ngModel)]="q" (keyup.enter)="charger(1)" placeholder="Racine ou nom" /></label>
      </div>
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table">
          <thead><tr><th class="c-sm">Racine</th><th class="c-sm">PP/PM</th><th class="c-lg">Identité</th><th class="c-md">Classe moteur</th><th class="c-date">Calculé le</th><th class="c-md">Classe retenue</th><th class="c-md">Analyste</th><th class="c-sm">Écart</th></tr></thead>
          <tbody>
            @for (r of items(); track r.racine_client) {
              <tr>
                <td><a [routerLink]="['/clientele/clients', r.racine_client]"><code>{{ r.racine_client }}</code></a></td>
                <td>{{ r.profil || '—' }}</td>
                <td>{{ r.raison_sociale || '—' }}</td>
                <td>
                  @if (r.calcul; as c) {
                    @if (c.niveau) { <span class="bea-cl-badge" [attr.data-s]="c.niveau">{{ c.niveau }}</span> } @else { NON CLASSÉ }
                    <small class="bea-cl-hint"> score {{ c.score ?? '—' }} · {{ c.statut }}</small>
                  } @else { — }
                </td>
                <td>{{ dh(r.calcul?.date_calcul) }} <small class="bea-cl-hint">{{ r.calcul?.version_moteur }}</small></td>
                <td>@if (r.retenue; as k) { <span class="bea-cl-badge" [attr.data-s]="k.niveau">{{ k.niveau }}</span> <small class="bea-cl-hint">{{ k.source }}</small> } @else { <small class="bea-cl-hint">non classé</small> }</td>
                <td>{{ r.retenue?.analyste_kyc || '—' }}</td>
                <td>@if (r.ecart) { <span class="bea-cl-badge" data-s="A_VERIFIER">Écart</span> } @else { — }</td>
              </tr>
            } @empty {
              <tr><td colspan="8"><div class="bea-cl-empty">Aucun calcul du moteur pour ces filtres.</div></td></tr>
            }
          </tbody>
        </table>
      </div>
      @if (total() > taille) {
        <div class="bea-cl-pager">
          <span>{{ n(total()) }} client(s) · page {{ page() }} / {{ n(nbPages()) }}</span>
          <span class="bea-cl-pager__btns">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="charger(page() - 1)"><mat-icon>chevron_left</mat-icon> Précédent</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= nbPages()" (click)="charger(page() + 1)">Suivant <mat-icon>chevron_right</mat-icon></button>
          </span>
        </div>
      }
    </section>
  `,
})
export class ClClassifResultatsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly items = signal<Resultat[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly busy = signal(false);
  readonly taille = 50;
  readonly nbPages = computed(() => Math.max(1, Math.ceil(this.total() / this.taille)));
  readonly niveaux = ['FAIBLE', 'MOYEN', 'ELEVE', 'INTERDIT'];
  readonly n = n;
  readonly dh = dateHeureFr;
  ecart = '';
  niveau = '';
  source = '';
  q = '';

  ngOnInit(): void {
    this.charger(1);
  }

  private filtres(): Record<string, string> {
    const f: Record<string, string> = {};
    if (this.ecart) f['ecart'] = this.ecart;
    if (this.niveau) f['niveau'] = this.niveau;
    if (this.source) f['source'] = this.source;
    if (this.q.trim()) f['q'] = this.q.trim();
    return f;
  }

  charger(page: number): void {
    this.api.get<{ total: number; items: Resultat[] }>(`${CL_BASE}/classification/resultats`, { ...this.filtres(), page, taille: this.taille }).subscribe({
      next: (r) => { this.items.set(r.items || []); this.total.set(r.total || 0); this.page.set(page); },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Résultats indisponibles')),
    });
  }

  exporter(): void {
    this.busy.set(true);
    this.api.download(`${CL_BASE}/classification/resultats.xlsx`, this.filtres()).subscribe({
      next: (b) => { this.busy.set(false); telecharger(b, `resultats-moteur-${new Date().toISOString().slice(0, 10)}.xlsx`); },
      error: (e) => { this.busy.set(false); void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible')); },
    });
  }
}
