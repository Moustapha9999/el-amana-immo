import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { PaginationComponent } from '../../shared/pagination.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClExportComponent } from '../cl-export.component';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, PageSituation, dateFr, n } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

@Component({
  selector: 'bea-cl-situation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, PaginationComponent, ClienteleUiComponent, ClExportComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Base Clientèle</p>
          <h1>Clients {{ profil() === 'PM' ? 'PM' : 'PP' }}</h1>
          <p class="bea-cl-head__sub">Vue sur la base clientèle (pas une copie). Profil dérivé d’ORION (agent puis catégorie) — ce n’est pas le champ Excel « Profil ORION retraité ».</p>
        </div>
        <bea-cl-export [chemin]="base + '/situation/export'" [apercu]="base + '/situation/export/apercu'"
          [params]="paramsExport()" [filtresActifs]="filtresActifs()" [libelle]="'Clients ' + profil()"
          [nomFichier]="'clients-' + profil().toLowerCase()" [perimetre]="'Tous les clients ' + profil() + ' de la base.'" />
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
            <thead><tr><th class="c-sm">Racine</th><th class="c-lg">Nom</th><th class="c-md">Agence</th><th class="c-sm">Date ouv.</th><th class="c-sm">État</th><th class="c-sm">Profil</th><th class="is-num c-xs">Comptes</th><th class="c-md">NNI / NIF</th><th class="c-md">Classe retenue</th><th class="c-md">Classe moteur</th><th class="c-md">Analyste KYC</th></tr></thead>
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
                  <td>@if (r.classe_retenue) { <span class="bea-cl-badge" [attr.data-s]="r.classe_retenue">{{ r.classe_retenue }}</span> <small class="bea-cl-hint">{{ r.source_classe }}</small> } @else { <small class="bea-cl-hint">non classé</small> }</td>
                  <td>@if (r.classe_moteur) { <span class="bea-cl-badge" [attr.data-s]="r.classe_moteur">{{ r.classe_moteur }}</span> } @else { — }
                    @if (r.ecart_moteur) { <span class="bea-cl-badge" data-s="A_VERIFIER" title="La classe moteur diffère de la classe retenue">Écart</span> }
                  </td>
                  <td>{{ r.analyste_kyc || '—' }}</td>
                </tr>
              } @empty {
                <tr><td colspan="11"><div class="bea-cl-empty"><mat-icon>group_off</mat-icon>Aucun client.</div></td></tr>
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
  readonly base = CL_BASE;
  readonly filtres = signal<Record<string, string>>({});
  readonly filtresActifs = computed(() => Object.keys(this.filtres()).length > 0);
  readonly paramsExport = computed(() => ({ ...this.filtres(), profil: this.profil() }));

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
    const f: Record<string, string> = {};
    if (this.q.trim()) f['q'] = this.q.trim();
    if (this.racine.trim()) f['racine'] = this.racine.trim();
    if (this.compte.trim()) f['compte'] = this.compte.trim();
    if (this.rib.trim()) f['rib'] = this.rib.trim();
    if (this.agence.trim()) f['agence'] = this.agence.trim();
    if (this.etat) f['etat'] = this.etat;
    this.filtres.set(f);
    const params = { ...f, profil: this.profil(), page: this.page(), taille: this.taille };
    this.api.get<PageSituation>(`${CL_BASE}/situation`, params).subscribe({
      next: (p) => this.data.set(p),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Situation indisponible')),
    });
  }
}
