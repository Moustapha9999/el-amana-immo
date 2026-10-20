import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClExportComponent } from '../cl-export.component';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { BlocProgression, CL_BASE, ProgressionClassification, dateHeureFr, n, pourcentageFr } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

const LIBELLES: Record<string, { titre: string; sous: string }> = {
  PP: { titre: 'Personnes physiques', sous: 'Clients PP' },
  PM: { titre: 'Personnes morales', sous: 'Clients PM' },
  GLOBAL: { titre: 'Global PP + PM', sous: 'Ensemble des clients PP et PM' },
};
const NIVEAUX_LIB: Record<string, string> = { FAIBLE: 'Faible', MOYEN: 'Moyen', ELEVE: 'Élevé', INTERDIT: 'Interdit' };

@Component({
  selector: 'bea-cl-classif-suivi',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent, ClExportComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl bea-cl--large">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Classification</p>
          <h1>Tableau de bord de classification</h1>
          <p class="bea-cl-head__sub">Avancement réel du classement de la clientèle, calculé à chaque ouverture depuis la base. PP et PM sont suivis séparément.</p>
        </div>
        <div class="bea-cl-actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()" [disabled]="chargement()"><mat-icon>refresh</mat-icon> Actualiser</button>
          <bea-cl-export [chemin]="base + '/suivi/progression'" [params]="{ perimetre }" libelle="Progression de la classification" nomFichier="progression-classification" />
        </div>
      </header>

      <div class="bea-cl-prog__meta">
        <label>Périmètre des statistiques
          <select [(ngModel)]="perimetre" (ngModelChange)="charger()" aria-label="Périmètre des statistiques">
            <option value="TOUS">Tous les clients</option>
            <option value="OUVERTS">Clients ouverts (au moins un compte ouvert)</option>
          </select>
        </label>
      </div>

      @if (data(); as d) {
        <div class="bea-cl-prog">
          @for (b of [d.pp, d.pm, d.global]; track b.profil) {
            @let lib = libelles[b.profil];
            @let lien = b.profil !== 'GLOBAL' && store.cap().classif_voir;
            <section class="bea-cl-prog__card" [class.is-global]="b.profil === 'GLOBAL'" [attr.aria-label]="lib.titre">
              <div class="bea-cl-prog__top">
                <div>
                  <h2>{{ lib.titre }}</h2>
                  <p>{{ n(b.total) }} client(s) · {{ d.perimetre_libelle }}</p>
                </div>
                <span class="bea-cl-prog__pct" [class.is-na]="b.pourcentage === null">{{ pct(b.pourcentage) }}</span>
              </div>
              <div class="bea-cl-progress" role="progressbar" [attr.aria-valuenow]="b.pourcentage ?? 0" aria-valuemin="0" aria-valuemax="100" [attr.aria-label]="lib.titre + ' : part classée'">
                <span [style.width.%]="b.pourcentage ?? 0"></span>
              </div>
              <div class="bea-cl-prog__nums">
                <button type="button" class="is-ok" [disabled]="!lien" (click)="ouvrir(b, 'CLASSE')"><strong>{{ n(b.classes) }}</strong><span>Classés</span></button>
                <button type="button" class="is-warn" [disabled]="!lien" (click)="ouvrir(b, 'NON_CLASSE')"><strong>{{ n(b.non_classes) }}</strong><span>Non classés</span></button>
                <button type="button" [disabled]="!lien" (click)="ouvrir(b, 'A_VALIDER')"><strong>{{ n(b.a_valider) }}</strong><span>En attente de validation</span></button>
                <button type="button" [disabled]="!lien" (click)="ouvrir(b, 'NON_CLASSABLE')"><strong>{{ n(b.non_classables) }}</strong><span>Moteur sans résultat</span></button>
                <button type="button" [disabled]="!lien" (click)="ouvrir(b, 'NON_CALCULE')"><strong>{{ n(b.sans_calcul) }}</strong><span>Non calculés</span></button>
                <button type="button" [disabled]="!lien" (click)="ouvrir(b, 'ECART')"><strong>{{ n(b.ecarts_moteur) }}</strong><span>Écarts moteur / retenue</span></button>
              </div>
              <div class="bea-cl-prog__niv" aria-label="Répartition des classes retenues">
                @for (x of b.par_niveau; track x.niveau) {
                  <span class="bea-cl-badge" [attr.data-s]="x.niveau">{{ niveaux[x.niveau] || x.niveau }} · {{ n(x.clients) }}</span>
                }
                <span class="bea-cl-badge" data-s="MANUEL">Manuelles · {{ n(b.manuels) }}</span>
              </div>
              @if (lien) {
                <div class="bea-cl-prog__cta">
                  <a class="bea-mg__btn bea-mg__btn--primary" [routerLink]="'/clientele/classification-' + b.profil.toLowerCase()"
                    [queryParams]="{ statut: b.non_classes ? 'NON_CLASSE' : null, perimetre: perimetre === 'OUVERTS' ? 'OUVERTS' : null }">
                    <mat-icon>gavel</mat-icon> Classer les {{ b.profil }}
                  </a>
                </div>
              }
            </section>
          }
        </div>

        @if (alertes(d).length) {
          <h2 class="bea-cl-prog__titre">Points d’attention</h2>
          <ul class="bea-cl-prog__alertes">
            @for (a of alertes(d); track a.texte) {
              <li [class.is-info]="a.info">
                <span><mat-icon>{{ a.info ? 'info' : 'warning' }}</mat-icon>{{ a.texte }}</span>
                @if (a.lien) { <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="a.lien" [queryParams]="a.query">{{ a.action }}</a> }
              </li>
            }
          </ul>
        }
        <p class="bea-cl-prog__meta">Calculé le {{ dh(d.calcule_le) }} · {{ d.definition_classe }}</p>
      } @else if (chargement()) {
        <div class="bea-mg__panel"><div class="bea-cl-empty"><mat-icon class="bea-cl-spin">progress_activity</mat-icon>Calcul des statistiques…</div></div>
      } @else {
        <div class="bea-mg__panel"><div class="bea-cl-empty"><mat-icon>cloud_off</mat-icon>Statistiques indisponibles.</div></div>
      }
    </div>
  `,
})
export class ClClassifSuiviComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  readonly base = CL_BASE;
  readonly libelles = LIBELLES;
  readonly niveaux = NIVEAUX_LIB;
  readonly n = n;
  readonly dh = dateHeureFr;
  readonly pct = pourcentageFr;
  readonly data = signal<ProgressionClassification | null>(null);
  readonly chargement = signal(false);
  perimetre: 'TOUS' | 'OUVERTS' = 'TOUS';

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    this.chargement.set(true);
    this.api.get<ProgressionClassification>(`${CL_BASE}/suivi/progression`, { perimetre: this.perimetre }).subscribe({
      next: (d) => { this.data.set(d); this.chargement.set(false); },
      error: (e) => {
        this.chargement.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Statistiques indisponibles'));
      },
    });
  }

  ouvrir(b: BlocProgression, statut: string): void {
    if (b.profil === 'GLOBAL') return;
    void this.router.navigate([`/clientele/classification-${b.profil.toLowerCase()}`], {
      queryParams: { statut, perimetre: this.perimetre },
    });
  }

  alertes(d: ProgressionClassification): { texte: string; info?: boolean; lien?: string; query?: Record<string, string>; action?: string }[] {
    const out: { texte: string; info?: boolean; lien?: string; query?: Record<string, string>; action?: string }[] = [];
    const voir = this.store.cap().classif_voir;
    for (const b of [d.pp, d.pm]) {
      if (b.non_classes > 0) {
        out.push({
          texte: `${n(b.non_classes)} client(s) ${b.profil} sans classification retenue, dont ${n(b.a_valider)} avec une proposition du moteur à valider.`,
          lien: voir ? `/clientele/classification-${b.profil.toLowerCase()}` : undefined,
          query: { statut: 'NON_CLASSE', perimetre: this.perimetre }, action: 'Voir la liste',
        });
      }
      if (b.non_classables > 0) {
        out.push({
          texte: `${n(b.non_classables)} client(s) ${b.profil} : le moteur n’a pas produit de niveau exploitable (données manquantes ou à arbitrer).`,
          lien: voir ? `/clientele/classification-${b.profil.toLowerCase()}` : undefined,
          query: { statut: 'NON_CLASSABLE', perimetre: this.perimetre }, action: 'Analyser',
        });
      }
    }
    if (d.hors_perimetre.non_identifies > 0) {
      out.push({ info: true, texte: `${n(d.hors_perimetre.non_identifies)} client(s) au profil non identifié (ni PP ni PM) : hors des pourcentages ci-dessous.` });
    }
    if (d.lots_ouverts > 0) {
      out.push({ info: true, texte: `${n(d.lots_ouverts)} lot(s) de classification en cours de traitement.`, lien: '/clientele/classification-lot', action: 'Ouvrir les lots' });
    }
    return out;
  }
}
