import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateFr } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface Resume {
  id: string; annee: number; mois: number; libelle: string;
  date_debut: string; date_fin: string; statut: string;
  moteur_version: string | null; calculee_le: string | null; validee_le: string | null;
}

const MOIS = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
];

@Component({
  selector: 'bea-cl-declarations',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Conformité</p>
          <h1>Déclaration mensuelle BCM</h1>
          <p class="bea-cl-head__sub">Une déclaration par mois calendaire. Les chiffres viennent du moteur d’indicateurs. Une déclaration validée ne se recalcule plus (snapshot).</p>
        </div>
      </header>
      <p class="bea-cl-note bea-cl-note--info"><mat-icon>info</mat-icon>Officiel = mois clos uniquement. Les cellules « À CONFIGURER » n’affichent aucun chiffre tant que la Conformité n’a pas tranché (Actif, construction juridique, UMEF, Tableau 3…).</p>
      @if (store.cap().bcm_preparer) {
        <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); creer()">
          <label>Année<input type="number" [(ngModel)]="annee" name="annee" min="2000" max="2100" /></label>
          <label>Mois
            <select [(ngModel)]="mois" name="mois">
              @for (m of moisLib; track $index) {
                <option [ngValue]="$index + 1">{{ m }}</option>
              }
            </select>
          </label>
          <div style="display:flex;align-items:end">
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>add</mat-icon> Préparer</button>
          </div>
        </form>
      }
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Déclarations</h2></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Période</th><th>Du</th><th>Au</th><th>Statut</th><th>Moteur</th><th>Validée</th></tr></thead>
            <tbody>
              @for (r of liste(); track r.id) {
                <tr>
                  <td><a [routerLink]="['/clientele/declarations', r.id]"><strong>{{ r.libelle }}</strong></a></td>
                  <td>{{ dateFr(r.date_debut) }}</td>
                  <td>{{ dateFr(r.date_fin) }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="r.statut">{{ r.statut.replaceAll('_', ' ') }}</span></td>
                  <td>{{ r.moteur_version ?? '—' }}</td>
                  <td>{{ dateFr(r.validee_le) }}</td>
                </tr>
              } @empty {
                <tr><td colspan="6"><div class="bea-cl-empty">Aucune déclaration.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `,
})
export class ClDeclarationsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  private readonly router = inject(Router);
  readonly liste = signal<Resume[]>([]);
  readonly busy = signal(false);
  readonly dateFr = dateFr;
  readonly moisLib = MOIS;
  annee = new Date().getMonth() === 0 ? new Date().getFullYear() - 1 : new Date().getFullYear();
  mois = new Date().getMonth() === 0 ? 12 : new Date().getMonth();

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    this.api.get<Resume[]>(`${CL_BASE}/declarations`).subscribe({
      next: (d) => this.liste.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Déclarations indisponibles')),
    });
  }

  creer(): void {
    this.feedback.run(() => this.api.post<Resume>(`${CL_BASE}/declarations`, { annee: this.annee, mois: this.mois }), {
      busy: this.busy,
      loading: 'Création…',
      success: (r) => ({ title: 'Déclaration créée', details: [{ label: 'Période', value: r.libelle }] }),
      errorTitle: 'Création impossible',
    }).subscribe((r) => void this.router.navigate(['/clientele/declarations', r.id]));
  }
}
