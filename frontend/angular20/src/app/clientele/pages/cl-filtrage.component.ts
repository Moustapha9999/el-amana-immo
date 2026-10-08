import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateHeureFr, n } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface Alerte {
  id: string; racine_client: string; raison_sociale: string; statut: string; motif: string;
  score: number; precedent_faux_positif: boolean; created_at: string | null;
}
interface Liste { id: string; code: string; libelle: string; nb_entrees: number; actif: boolean; }

@Component({
  selector: 'bea-cl-filtrage',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Risque</p>
          <h1>Filtrage &amp; alertes</h1>
          <p class="bea-cl-head__sub">Une correspondance potentielle n’est pas une correspondance réelle. Workflow : nouvelle → à analyser → investigation → confirmée / faux positif / rejetée → clôturée.</p>
        </div>
        @if (store.cap().filtrage_executer) {
          <button type="button" class="bea-mg__btn" (click)="scanner()" [disabled]="busy()"><mat-icon>search</mat-icon> Lancer le filtrage</button>
        }
      </header>
      <p class="bea-cl-note bea-cl-note--info"><mat-icon>info</mat-icon>Les faux positifs sont conservés et signalés à une nouvelle occurrence.</p>
      <div class="bea-cl-kpis">
        @for (s of statuts; track s) {
          <button type="button" class="bea-cl-kpi" (click)="statut = statut===s ? '' : s; charger()">
            <span>{{ s.replaceAll('_', ' ') }}</span><strong>{{ n(par()[s]) }}</strong>
          </button>
        }
      </div>
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Alertes</h2><span class="bea-mg__count">{{ total() }}</span></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Racine</th><th>Nom</th><th>Motif</th><th>Score</th><th>Statut</th><th>Le</th></tr></thead>
            <tbody>
              @for (a of items(); track a.id) {
                <tr class="is-click" [routerLink]="['/clientele/filtrage', a.id]" style="cursor:pointer">
                  <td><code>{{ a.racine_client }}</code>@if (a.precedent_faux_positif) { <span class="bea-cl-badge" data-s="ANALYSE">FP antérieur</span> }</td>
                  <td>{{ a.raison_sociale }}</td>
                  <td>{{ a.motif }}</td>
                  <td>{{ a.score }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="a.statut">{{ a.statut }}</span></td>
                  <td>{{ dh(a.created_at) }}</td>
                </tr>
              } @empty {
                <tr><td colspan="6"><div class="bea-cl-empty">Aucune alerte.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Listes internes</h2></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Code</th><th>Libellé</th><th>Entrées</th></tr></thead>
            <tbody>
              @for (l of listes(); track l.id) {
                <tr>
                  <td><code>{{ l.code }}</code></td>
                  <td>{{ l.libelle }}</td>
                  <td>{{ l.nb_entrees }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (store.cap().filtrage_executer && listes()[0]) {
          <div class="bea-cl-filters">
            <label>Raison sociale / nom<input [(ngModel)]="entree.raison_sociale" /></label>
            <label>Identifiant<input [(ngModel)]="entree.identifiant" /></label>
            <label>&nbsp;<button type="button" class="bea-mg__btn" (click)="ajouter()">Ajouter une entrée</button></label>
          </div>
        }
      </section>
    </div>
  `,
})
export class ClFiltrageComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly items = signal<Alerte[]>([]);
  readonly total = signal(0);
  readonly par = signal<Record<string, number>>({});
  readonly listes = signal<Liste[]>([]);
  readonly busy = signal(false);
  readonly statuts = ['NOUVELLE', 'A_ANALYSER', 'EN_INVESTIGATION', 'CONFIRMEE', 'FAUX_POSITIF', 'REJETEE', 'CLOTUREE'];
  statut = '';
  entree = { raison_sociale: '', identifiant: '' };
  readonly n = n;
  readonly dh = dateHeureFr;

  ngOnInit(): void {
    this.store.charger();
    this.api.get<Liste[]>(`${CL_BASE}/filtrage/listes`).subscribe({ next: (r) => this.listes.set(r) });
    this.charger();
  }

  charger(): void {
    const params: Record<string, string | number> = { taille: 80 };
    if (this.statut) params['statut'] = this.statut;
    this.api.get<{ total: number; items: Alerte[]; par_statut: Record<string, number> }>(`${CL_BASE}/filtrage/alertes`, params).subscribe({
      next: (p) => { this.items.set(p.items); this.total.set(p.total); this.par.set(p.par_statut); },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Alertes indisponibles')),
    });
  }

  scanner(): void {
    this.feedback.run(() => this.api.post<{ alertes_crees: number }>(`${CL_BASE}/filtrage/scan`, {}), {
      confirm: { action: 'validation', title: 'Lancer le filtrage', message: 'Scanner le référentiel (listes + INTERDICTION ORION) ?', hint: 'Les correspondances restent à analyser.' },
      busy: this.busy, success: (r) => ({ title: 'Filtrage terminé', message: `${r.alertes_crees} alerte(s) potentielle(s)` }),
      errorTitle: 'Filtrage impossible',
    }).subscribe(() => this.charger());
  }

  ajouter(): void {
    const liste = this.listes()[0];
    if (!liste || (!this.entree.raison_sociale && !this.entree.identifiant)) return;
    this.feedback.run(() => this.api.post(`${CL_BASE}/filtrage/listes/${liste.id}/entrees`, this.entree), {
      busy: this.busy, success: { title: 'Entrée ajoutée' }, errorTitle: 'Ajout refusé',
    }).subscribe(() => {
      this.entree = { raison_sociale: '', identifiant: '' };
      this.api.get<Liste[]>(`${CL_BASE}/filtrage/listes`).subscribe({ next: (r) => this.listes.set(r) });
    });
  }
}
