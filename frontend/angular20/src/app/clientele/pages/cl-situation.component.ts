import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { PaginationComponent } from '../../shared/pagination.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, PageSituation, dateFr, n } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

@Component({
  selector: 'bea-cl-situation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, PaginationComponent, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Référentiel clients</p>
          <h1>Situation {{ profil() === 'PM' ? 'PM' : 'PP' }}</h1>
          <p class="bea-cl-head__sub">Vue sur la base clientèle (pas une copie). Profil dérivé d’ORION (agent puis catégorie) — ce n’est pas le champ Excel « Profil ORION retraité ».</p>
        </div>
      </header>
      <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); page.set(1); charger()">
        <label>Recherche<input [(ngModel)]="q" name="q" placeholder="Racine, nom, NNI, NIF…" /></label>
        <label>Racine<input [(ngModel)]="racine" name="racine" maxlength="6" /></label>
        <label>Compte<input [(ngModel)]="compte" name="compte" maxlength="11" /></label>
        <label>RIB<input [(ngModel)]="rib" name="rib" maxlength="23" /></label>
        <label>Agence
          <select [(ngModel)]="agence" name="agence">
            <option value="">Toutes</option>
            @for (a of store.agences(); track a.code) {
              <option [value]="a.code">{{ a.code }} — {{ a.libelle }}</option>
            }
          </select>
        </label>
        <label>État
          <select [(ngModel)]="etat" name="etat">
            <option value="">Tous</option>
            <option value="OUVERT">Ouvert</option>
            <option value="CLOTURE">Clôturé</option>
          </select>
        </label>
        <div style="display:flex;align-items:end">
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary"><mat-icon>search</mat-icon> Filtrer</button>
        </div>
      </form>
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Clients</h2><span class="bea-mg__count">{{ n(data()?.total) }} distincts</span></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Racine</th><th>Nom</th><th>Agence</th><th>Date ouv.</th><th>État</th><th>Profil</th><th class="is-num">Comptes</th><th>NNI / NIF</th></tr></thead>
            <tbody>
              @for (r of data()?.items ?? []; track r.racine_client) {
                <tr class="is-click" [routerLink]="['/clientele/clients', r.racine_client]" style="cursor:pointer">
                  <td><code>{{ r.racine_client }}</code></td>
                  <td>{{ r.nom_client }}</td>
                  <td>{{ agenceLib(r.code_agence, r.agence) }}</td>
                  <td>{{ dateFr(r.date_ouverture) }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="r.etat_client">{{ r.etat_client }}</span></td>
                  <td><span class="bea-cl-badge" [attr.data-s]="r.profil_derive">{{ r.profil_derive }}</span></td>
                  <td>{{ r.nb_comptes_ouverts }} / {{ r.nb_comptes }}</td>
                  <td>{{ r.nni || r.nif || '—' }}</td>
                </tr>
              } @empty {
                <tr><td colspan="8"><div class="bea-cl-empty"><mat-icon>group_off</mat-icon>Aucun client.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
        @if ((data()?.total ?? 0) > taille) {
          <app-pagination [page]="page()" [total]="data()!.total" [pageSize]="taille" label="clients" (pageChange)="page.set($event); charger()" />
        }
      </section>
    </div>
  `,
})
export class ClSituationComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly store = inject(ClienteleStore);
  readonly dateFr = dateFr;
  readonly n = n;

  agenceLib(code: string | null | undefined, libelle: string | null | undefined): string {
    if (!code) return '—';
    return libelle ? `${code} — ${libelle}` : code;
  }
  readonly profil = signal('PP');
  readonly data = signal<PageSituation | null>(null);
  readonly page = signal(1);
  readonly taille = 50;
  q = '';
  racine = '';
  compte = '';
  rib = '';
  agence = '';
  etat = '';

  ngOnInit(): void {
    this.store.charger();
    this.profil.set(this.route.snapshot.data['profil'] ?? 'PP');
    this.charger();
  }

  charger(): void {
    const params: Record<string, string | number | boolean> = {
      profil: this.profil(), page: this.page(), taille: this.taille,
    };
    if (this.q.trim()) params['q'] = this.q.trim();
    if (this.racine.trim()) params['racine'] = this.racine.trim();
    if (this.compte.trim()) params['compte'] = this.compte.trim();
    if (this.rib.trim()) params['rib'] = this.rib.trim();
    if (this.agence.trim()) params['agence'] = this.agence.trim();
    if (this.etat) params['etat'] = this.etat;
    this.api.get<PageSituation>(`${CL_BASE}/situation`, params).subscribe({
      next: (p) => this.data.set(p),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Situation indisponible')),
    });
  }
}
