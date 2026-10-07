import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FoDonutComponent, FoHBarsComponent } from '../formation-charts';
import { FormationUiComponent } from '../formation-ui.component';
import { Employe, FO_BASE, FicheEmploye, dateFr, dateHeureFr, initiales, taux } from '../formation.models';
import { FormationStore } from '../formation.store';
import { FoEmployeFormComponent } from '../shared/fo-employe-form.component';

@Component({
  selector: 'bea-fo-employe-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, FormationUiComponent, FoDonutComponent, FoHBarsComponent, FoEmployeFormComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <button type="button" class="bea-fo-back" (click)="router.navigate(['/formation/employes'])"><mat-icon>arrow_back</mat-icon> Employés</button>
      @if (!e()) {
        <div class="bea-fo-hero"><span class="bea-fx-skel" style="width:3.4rem;height:3.4rem;border-radius:50%"></span>
          <div style="flex:1"><span class="bea-fx-skel bea-fx-skel--title"></span><span class="bea-fx-skel bea-fx-skel--line"></span></div></div>
        <div class="bea-fx-kpis">@for (i of [1, 2, 3, 4]; track i) { <span class="bea-fx-skel bea-fx-skel--kpi"></span> }</div>
      } @else {
        @let x = e()!;
        <section class="bea-fo-hero">
          <span class="bea-fo-avatar bea-fo-avatar--lg">{{ ini(x.nom_complet) }}</span>
          <div class="bea-fo-hero__main">
            <div style="display:flex;gap:0.4rem;align-items:center;flex-wrap:wrap">
              <span class="bea-fo-badge" [attr.data-s]="x.actif ? 'ACTIF' : 'INACTIF'">{{ x.actif ? 'Actif' : 'Désactivé' }}</span>
              @if (x.source === 'IMPORT') { <span class="bea-fo-tag bea-fo-tag--muted">Créé par import Excel</span> }
            </div>
            <h1>{{ x.nom }} {{ x.prenom }}</h1>
            <div class="bea-fo-hero__meta">
              <span><mat-icon>work_outline</mat-icon>{{ x.fonction || 'Fonction non renseignée' }}</span>
              <span><mat-icon>account_tree</mat-icon>{{ x.entite || 'Entité non renseignée' }}</span>
              <span><mat-icon>hub</mat-icon>{{ x.perimetre || '—' }}</span>
            </div>
          </div>
          <div class="bea-fo-hero__actions">
            @if (store.cap().employes_gerer) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="edition.set(true)"><mat-icon>edit</mat-icon> Modifier</button>
              @if (x.actif) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" style="color:#b91c1c" (click)="activer(false)" [disabled]="busy()"><mat-icon>person_off</mat-icon> Désactiver</button>
              } @else {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="activer(true)" [disabled]="busy()"><mat-icon>person</mat-icon> Réactiver</button>
              }
            }
            @if (store.cap().reporting_voir) {
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/formation/reporting" [queryParams]="{ employe_id: x.id }"><mat-icon>assessment</mat-icon> Reporting</a>
            }
          </div>
        </section>
        @if (!x.actif && x.motif_desactivation) {
          <div class="bea-fo-note"><mat-icon>person_off</mat-icon><span><strong>Désactivé.</strong> Motif : {{ x.motif_desactivation }}</span></div>
        }

        <div class="bea-fx-kpis">
          <div class="bea-fx-kpi"><mat-icon>event_note</mat-icon><p>Convocations</p><strong>{{ x.stats.participations }}</strong><small>hors formations annulées</small></div>
          <div class="bea-fx-kpi" data-tone="ok"><mat-icon>verified_user</mat-icon><p>Formations suivies</p><strong>{{ x.stats.presents }}</strong><small>dernière : {{ dateFr(x.stats.derniere_formation) }}</small></div>
          <div class="bea-fx-kpi" data-tone="danger"><mat-icon>person_off</mat-icon><p>Absences</p><strong>{{ x.stats.absents }}</strong><small>{{ x.stats.non_saisis }} non saisie(s)</small></div>
          <div class="bea-fx-kpi" data-tone="brand"><mat-icon>percent</mat-icon><p>Taux de présence</p><strong>{{ taux(x.stats.taux_presence) }}</strong><small>&nbsp;</small></div>
        </div>

        <div class="bea-fo-grid">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Coordonnées</h2></div>
            <dl class="bea-fo-dl">
              <dt>Nom</dt><dd>{{ x.nom }}</dd>
              <dt>Prénom</dt><dd>{{ x.prenom || '—' }}</dd>
              <dt>Fonction</dt><dd>{{ x.fonction || '—' }}</dd>
              <dt>Entité</dt><dd>{{ x.entite || '—' }}</dd>
              <dt>Périmètre</dt><dd>{{ x.perimetre || '—' }}</dd>
              <dt>Email</dt><dd>@if (x.email) {<a class="bea-ct-link" [href]="'mailto:' + x.email">{{ x.email }}</a>} @else {—}</dd>
              <dt>Téléphone</dt><dd>{{ x.telephone || '—' }}</dd>
              <dt>Mis à jour</dt><dd>{{ dh(x.updated_at) }}</dd>
            </dl>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Présence</h2></div>
            <bea-fo-donut [parts]="parts()" [centre]="taux(x.stats.taux_presence)" unite="présence" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Thèmes suivis</h2></div>
            <bea-fo-hbars mode="valeur" [valeursSimples]="x.par_theme" unite="fois" />
          </section>
        </div>

        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Historique des formations</h2><span class="bea-mg__count">{{ x.historique.length }}</span></div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-fo-table">
              <thead><tr><th>Date</th><th>Thème</th><th>Lieu</th><th>Formateur</th><th>Entité (à la date)</th><th>Présence</th><th>Statut</th></tr></thead>
              <tbody>
                @for (h of x.historique; track h.participant_id; let i = $index) {
                  <tr class="is-click bea-fx-row-in" [style.--i]="i" [class.is-muted]="h.statut === 'ANNULEE'" (click)="router.navigate(['/formation/sessions', h.session_id])">
                    <td><strong>{{ dateFr(h.date) }}</strong><small>{{ h.reference }}</small></td>
                    <td>{{ h.theme }}</td>
                    <td>{{ h.lieu }}</td>
                    <td>{{ h.formateurs.join(' / ') }}</td>
                    <td>{{ h.entite || '—' }}</td>
                    <td><span class="bea-fo-badge" [attr.data-s]="h.presence ?? 'NON_SAISI'">{{ h.presence === 'PRESENT' ? 'PRÉSENT' : h.presence === 'ABSENT' ? 'ABSENT' : 'Non saisi' }}</span></td>
                    <td><span class="bea-fo-badge bea-fo-badge--plain" [attr.data-s]="h.statut">{{ h.statut_libelle }}</span></td>
                  </tr>
                } @empty {
                  <tr><td colspan="7"><div class="bea-fo-empty"><mat-icon>school</mat-icon><strong>Aucune formation</strong>Cet employé n’a encore été convoqué à aucune formation.</div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </section>
      }
    </div>
    @if (edition() && e()) {
      <bea-fo-employe-form [employe]="e()" (fermer)="edition.set(false)" (enregistre)="modifie($event)" (choisirExistant)="aller($event)" />
    }
  `,
})
export class FoEmployeFicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly router = inject(Router);
  readonly store = inject(FormationStore);

  readonly dateFr = dateFr;
  readonly dh = dateHeureFr;
  readonly taux = taux;
  readonly ini = initiales;
  readonly e = signal<FicheEmploye | null>(null);
  readonly edition = signal(false);
  readonly busy = signal(false);

  readonly parts = computed(() => {
    const s = this.e()?.stats;
    if (!s) return [];
    return [
      { label: 'Présent', value: s.presents, color: '#15803d' },
      { label: 'Absent', value: s.absents, color: '#dc2626' },
      { label: 'Non saisi', value: s.non_saisis, color: '#cbd5e1' },
    ];
  });

  ngOnInit(): void {
    this.store.charger();
    this.route.paramMap.subscribe((pm) => {
      const id = pm.get('id');
      if (id) this.charger(id);
    });
  }

  private charger(id: string): void {
    this.e.set(null);
    this.api.get<FicheEmploye>(`${FO_BASE}/employes/${id}`).subscribe({
      next: (f) => this.e.set(f),
      error: (err) => {
        void describeApiErrorAsync(err).then((i) => this.feedback.apiError(i, 'Employé introuvable'));
        void this.router.navigate(['/formation/employes']);
      },
    });
  }

  modifie(x: Employe): void {
    this.edition.set(false);
    this.charger(x.id);
  }

  aller(x: Employe): void {
    this.edition.set(false);
    void this.router.navigate(['/formation/employes', x.id]);
  }

  activer(actif: boolean): void {
    const x = this.e()!;
    const appel = (motif: string | null) => this.api.post<Employe>(`${FO_BASE}/employes/${x.id}/activation`, { actif, motif });
    const base = {
      busy: this.busy,
      loading: 'Mise à jour…',
      success: { title: actif ? 'Employé réactivé' : 'Employé désactivé', message: x.nom_complet },
      errorTitle: 'Action impossible',
    };
    const flux = actif
      ? this.feedback.run(() => appel(null), { ...base, confirm: { action: 'reprise', title: 'Réactiver l’employé', message: `Réactiver ${x.nom_complet} ?` } })
      : this.feedback.runWithReason((m) => appel(m), {
          ...base,
          reason: {
            title: 'Désactiver l’employé', message: x.nom_complet,
            hint: 'L’historique est conservé. Un employé désactivé ne peut plus être convoqué.',
            reasonLabel: 'Motif (départ, mutation, doublon…)', required: true, maxLength: 1000, tone: 'warn', confirmLabel: 'Désactiver',
          },
        });
    flux.subscribe(() => this.charger(x.id));
  }
}
