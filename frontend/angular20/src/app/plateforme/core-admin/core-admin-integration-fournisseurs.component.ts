import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  AUCUN_APPEL,
  FournisseurFiltres,
  FournisseurResume,
  fournisseurStatutLabel,
  fournisseurStatutTone,
  integrationFournisseursPermissions,
  PERMISSIONS_FOURNISSEURS,
} from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import {
  ariaSort,
  basculerTri,
  IntegrationSuppressionService,
  IntegrationTriComponent,
  OrdreTri,
  squelette,
} from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

export const ACCES_REFUSE_FOURNISSEURS = `
  <div class="bea-admin-panel" role="alert">
    <h2>Accès refusé</h2>
    <p class="bea-admin-panel__hint">
      Les API externes exigent une session BEA DIGITAL (Login 1) et la permission
      <code>${PERMISSIONS_FOURNISSEURS.view}</code>. Un jeton de module (Login 2) n'est pas accepté.
    </p>
  </div>
`;

export const BANDEAU_AUCUN_APPEL = `
  <div class="bea-integ-notice" role="note">
    <bea-admin-icon name="info" />
    <p><strong>${AUCUN_APPEL}</strong> Les fournisseurs, spécifications et opérations sont de la documentation :
      aucune URL n'est contactée, aucune spécification n'est téléchargée, aucune opération n'est exécutée.</p>
  </div>
`;

const FILTRES_VIDES = { q: '', statut: '', environnement: '', inclure_archives: false, tri: 'updated_at', ordre: 'desc' };

@Component({
  selector: 'bea-core-admin-integration-fournisseurs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DatePipe, CoreAdminIconComponent, IntegrationTriComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations">Studio d'intégration API</a></p>
          <h1>Fournisseurs externes</h1>
          <p>Fournisseurs d'API tiers que BEA DIGITAL pourrait consommer : fiches, spécifications OpenAPI, opérations.</p>
        </div>
        <div class="bea-integ-head-actions">
          <button type="button" class="bea-admin-btn bea-admin-btn--refresh" [disabled]="loading()" (click)="charger()">
            <bea-admin-icon name="refresh" /> Actualiser
          </button>
          @if (droits.manage()) {
            <a class="bea-admin-btn" routerLink="/admin/integrations/fournisseurs/nouveau"><bea-admin-icon name="add" /> Nouveau fournisseur</a>
          }
        </div>
      </header>

      ${BANDEAU_AUCUN_APPEL}

      <form class="bea-admin-toolbar" [formGroup]="filtres" (ngSubmit)="rechercher()" role="search" aria-label="Filtrer les fournisseurs">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input type="search" formControlName="q" placeholder="Nom, identifiant interne, description…" maxlength="120" />
        </label>
        <label class="bea-admin-field">
          <span>Statut</span>
          <select formControlName="statut">
            <option value="">Tous (hors archivés)</option>
            <option value="brouillon">Brouillon</option>
            <option value="a_valider">À valider</option>
            <option value="valide">Validé (configuration)</option>
            <option value="suspendu">Suspendu</option>
            <option value="archive">Archivé</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Environnement</span>
          <select formControlName="environnement">
            <option value="">Tous</option>
            <option value="DEV">DEV</option>
            <option value="TEST">TEST</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Archivés</span>
          <span><input type="checkbox" formControlName="inclure_archives" /> Inclure</span>
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="submit" class="bea-admin-btn" [disabled]="loading()">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
        </div>
      </form>

      @if (loading() && items().length === 0) {
        ${squelette('Chargement des fournisseurs…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_FOURNISSEURS}
      } @else if (erreur(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        <button type="button" class="bea-admin-btn" (click)="charger()">Réessayer</button>
      } @else {
        <div class="bea-admin-panel" [attr.aria-busy]="loading()">
          <div class="bea-integ-list-head">
            <h2>Fournisseurs</h2>
            <span class="bea-integ-count" aria-live="polite">{{ total() }} résultat(s)</span>
          </div>
          @if (items().length === 0) {
            <div class="bea-integ-empty">
              <bea-admin-icon name="cloud_off" />
              @if (filtresActifs()) {
                <strong>Aucun fournisseur d'API ne correspond à ces critères.</strong>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reinitialiser()">Réinitialiser les filtres</button>
              } @else {
                <strong>Aucun fournisseur d'API enregistré.</strong>
                <p>Un fournisseur regroupe la documentation d'une API tierce (spécification OpenAPI ou opérations manuelles).</p>
                @if (droits.manage()) {
                  <a class="bea-admin-btn" routerLink="/admin/integrations/fournisseurs/nouveau">Déclarer un fournisseur</a>
                }
              }
            </div>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table bea-integ-cards">
                <thead>
                  <tr>
                    <th scope="col" [attr.aria-sort]="sort('nom')"><bea-integ-tri colonne="nom" libelle="Fournisseur" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                    <th scope="col">Service responsable</th>
                    <th scope="col" [attr.aria-sort]="sort('environnement')"><bea-integ-tri colonne="environnement" libelle="Env." [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                    <th scope="col" [attr.aria-sort]="sort('statut')"><bea-integ-tri colonne="statut" libelle="Statut" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                    <th scope="col">URL de base déclarée</th>
                    <th scope="col">Spéc. / opérations</th>
                    <th scope="col" [attr.aria-sort]="sort('updated_at')"><bea-integ-tri colonne="updated_at" libelle="Modification" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                    <th scope="col"><span class="bea-integ-muted">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  @for (f of items(); track f.id) {
                    <tr>
                      <td data-label="Fournisseur">
                        <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/fournisseurs', f.id]">{{ f.nom }}</a>
                        <div class="bea-integ-muted"><code>{{ f.code }}</code></div>
                      </td>
                      <td data-label="Service">{{ f.entite?.libelle ?? '—' }}</td>
                      <td data-label="Env."><span class="bea-integ-pill">{{ f.environnement }}</span></td>
                      <td data-label="Statut"><span [class]="statutTone(f.statut)">{{ statutLabel(f.statut) }}</span></td>
                      <td data-label="URL"><span class="bea-integ-path bea-integ-truncate" [title]="f.url_base ?? ''">{{ f.url_base ?? '—' }}</span></td>
                      <td data-label="Spéc. / op.">{{ f.version_courante ? 'v' + f.version_courante : '—' }} · {{ f.nb_operations }} op.</td>
                      <td data-label="Modification">
                        {{ f.updated_at | date: 'dd/MM/yyyy HH:mm' }}
                        <div class="bea-integ-muted">{{ f.modifie_par?.nom ?? '—' }}</div>
                      </td>
                      <td data-label="">
                        <div class="bea-integ-row-actions">
                          <a class="bea-integ-icon-btn" [routerLink]="['/admin/integrations/fournisseurs', f.id]" [attr.aria-label]="'Consulter ' + f.nom" title="Consulter">
                            <bea-admin-icon name="visibility" />
                          </a>
                          @if (droits.manage() && modifiable(f.statut)) {
                            <a class="bea-integ-icon-btn" [routerLink]="['/admin/integrations/fournisseurs', f.id, 'modifier']" [attr.aria-label]="'Modifier ' + f.nom" title="Modifier">
                              <bea-admin-icon name="edit" />
                            </a>
                          }
                          @if (droits.manage() && f.statut !== 'archive') {
                            <button type="button" class="bea-integ-icon-btn" data-tone="danger" [disabled]="suppression() === f.id"
                                    [attr.aria-label]="'Supprimer ' + f.nom" title="Supprimer (si aucune dépendance)" (click)="supprimer(f)">
                              <bea-admin-icon name="delete" />
                            </button>
                          }
                        </div>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <nav class="bea-admin-pager" aria-label="Pagination">
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} fournisseur(s)</span>
              <div>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1 || loading()" (click)="aller(page() - 1)">Précédent</button>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages() || loading()" (click)="aller(page() + 1)">Suivant</button>
              </div>
            </nav>
          }
        </div>
      }
    </section>
  `,
})
export class CoreAdminIntegrationFournisseursComponent implements OnInit {
  private readonly service = inject(CoreAdminIntegrationFournisseursService);
  private readonly suppressions = inject(IntegrationSuppressionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  readonly droits = integrationFournisseursPermissions();

  readonly loading = signal(true);
  readonly erreur = signal<string | null>(null);
  readonly accesRefuse = signal(false);
  readonly items = signal<FournisseurResume[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly suppression = signal<string | null>(null);
  readonly triActuel = signal<{ tri: string; ordre: OrdreTri }>({ tri: FILTRES_VIDES.tri, ordre: 'desc' });
  readonly size = 25;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  readonly filtres = this.fb.nonNullable.group({ ...FILTRES_VIDES });
  readonly statutLabel = fournisseurStatutLabel;
  readonly statutTone = fournisseurStatutTone;

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    this.filtres.patchValue({
      q: qp.get('q') ?? '',
      statut: qp.get('statut') ?? '',
      environnement: qp.get('environnement') ?? '',
      inclure_archives: qp.get('inclure_archives') === 'true',
      tri: qp.get('tri') ?? FILTRES_VIDES.tri,
      ordre: qp.get('ordre') ?? FILTRES_VIDES.ordre,
    });
    this.majTri();
    this.charger();
  }

  sort(colonne: string) {
    return ariaSort(this.triActuel(), colonne);
  }

  modifiable(statut: string): boolean {
    return statut === 'brouillon' || statut === 'a_valider';
  }

  filtresActifs(): boolean {
    const v = this.filtres.getRawValue();
    return !!(v.q.trim() || v.statut || v.environnement || v.inclure_archives);
  }

  trier(colonne: string): void {
    this.filtres.patchValue(basculerTri(this.triActuel(), colonne, colonne === 'updated_at' ? 'desc' : 'asc'));
    this.rechercher();
  }

  rechercher(): void {
    this.page.set(1);
    this.majTri();
    this.synchroniserUrl();
    this.charger();
  }

  async supprimer(f: FournisseurResume): Promise<void> {
    if (this.suppression()) return;
    this.suppression.set(f.id);
    const ok = await this.suppressions.supprimer({
      objet: 'le fournisseur',
      nom: f.nom,
      dependances: () => this.service.dependances(f.id),
      supprimer: (revision) => this.service.supprimer(f.id, revision),
    });
    this.suppression.set(null);
    if (ok) {
      if (this.items().length === 1 && this.page() > 1) this.page.update((p) => p - 1);
      this.charger();
    }
  }

  private majTri(): void {
    const v = this.filtres.getRawValue();
    this.triActuel.set({ tri: v.tri, ordre: v.ordre === 'asc' ? 'asc' : 'desc' });
  }

  reinitialiser(): void {
    this.filtres.reset({ ...FILTRES_VIDES });
    this.rechercher();
  }

  aller(page: number): void {
    this.page.set(page);
    this.charger();
  }

  valeurs(): FournisseurFiltres {
    return this.filtres.getRawValue();
  }

  charger(): void {
    this.loading.set(true);
    this.erreur.set(null);
    this.accesRefuse.set(false);
    this.service.lister(this.valeurs(), this.page(), this.size).subscribe({
      next: (data) => {
        this.items.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.page.set(data.page ?? 1);
        this.loading.set(false);
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Impossible de charger les fournisseurs d’API.'));
        this.loading.set(false);
      },
    });
  }

  private synchroniserUrl(): void {
    const v = this.filtres.getRawValue();
    const queryParams: Record<string, string> = {};
    if (v.q.trim()) queryParams['q'] = v.q.trim();
    if (v.statut) queryParams['statut'] = v.statut;
    if (v.environnement) queryParams['environnement'] = v.environnement;
    if (v.inclure_archives) queryParams['inclure_archives'] = 'true';
    if (v.tri !== FILTRES_VIDES.tri) queryParams['tri'] = v.tri;
    if (v.ordre !== FILTRES_VIDES.ordre) queryParams['ordre'] = v.ordre;
    void this.router.navigate([], { relativeTo: this.route, queryParams, replaceUrl: true });
  }
}
