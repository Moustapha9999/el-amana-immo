import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  DestinationResume,
  destinationStatutLabel,
  destinationStatutTone,
  integrationDestinationsPermissions,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionService } from './core-admin-integration-execution.service';
import {
  ariaSort,
  basculerTri,
  IntegrationSuppressionService,
  IntegrationTriComponent,
  OrdreTri,
  squelette,
} from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

export const ACCES_REFUSE_DEST = `
  <div class="bea-integ-notice bea-integ-notice--danger" role="alert">
    <p>Accès refusé. Cette section exige une permission CORE ADMIN dédiée. Le serveur a refusé la requête.</p>
  </div>`;

const FILTRES_VIDES = { q: '', statut: '', inclure_archivees: false, tri: 'updated_at', ordre: 'desc' };

@Component({
  selector: 'bea-core-admin-integration-destinations',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DatePipe, CoreAdminIconComponent, IntegrationTriComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations">Studio d'intégration API</a></p>
          <h1>Destinations TEST</h1>
          <p>Hôtes HTTPS TEST explicitement approuvés. L’URL d’appel n’est jamais saisie à l’exécution.</p>
        </div>
        <div class="bea-integ-head-actions">
          <button type="button" class="bea-admin-btn bea-admin-btn--refresh" [disabled]="chargement()" (click)="charger()">
            <bea-admin-icon name="refresh" /> Actualiser
          </button>
          @if (droits.manage()) {
            <a class="bea-admin-btn" routerLink="/admin/integrations/destinations/nouvelle" [queryParams]="lienNouveau()">
              <bea-admin-icon name="add" /> Nouvelle destination
            </a>
          }
        </div>
      </header>
      <div class="bea-integ-notice" role="note">
        <bea-admin-icon name="info" />
        <p>Seul l’environnement TEST, le protocole HTTPS et le port 443 sont autorisés. Aucun appel n’est déclenché à l’ouverture de cette page.</p>
      </div>

      <form class="bea-admin-toolbar" [formGroup]="filtres" (ngSubmit)="rechercher()" role="search" aria-label="Filtrer les destinations">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input type="search" formControlName="q" maxlength="120" placeholder="Nom, code, hôte…" />
        </label>
        <label class="bea-admin-field">
          <span>Statut</span>
          <select formControlName="statut">
            <option value="">Tous (hors archivées)</option>
            <option value="brouillon">Brouillon</option>
            <option value="a_valider">À approuver</option>
            <option value="active">Active</option>
            <option value="suspendue">Suspendue</option>
            <option value="archivee">Archivée</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Archivées</span>
          <span><input type="checkbox" formControlName="inclure_archivees" /> Inclure</span>
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="submit" class="bea-admin-btn" [disabled]="chargement()">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
        </div>
      </form>
      @if (fournisseurId) {
        <p class="bea-integ-muted">
          Filtré sur un fournisseur. <a routerLink="/admin/integrations/destinations">Voir toutes les destinations</a>
        </p>
      }

      @if (chargement() && items().length === 0) {
        ${squelette('Chargement des destinations…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_DEST}
      } @else if (erreur(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        <button type="button" class="bea-admin-btn" (click)="charger()">Réessayer</button>
      } @else {
        <div class="bea-admin-panel" [attr.aria-busy]="chargement()">
          <div class="bea-integ-list-head">
            <h2>Destinations</h2>
            <span class="bea-integ-count" aria-live="polite">{{ total() }} résultat(s)</span>
          </div>
          @if (items().length === 0) {
            <div class="bea-integ-empty">
              <bea-admin-icon name="dns" />
              @if (filtresActifs()) {
                <strong>Aucune destination ne correspond à ces critères.</strong>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reinitialiser()">Réinitialiser les filtres</button>
              } @else {
                <strong>Aucune destination.</strong>
                <p>Créez-en une à partir d’un fournisseur validé ; elle devra être approuvée avant tout test.</p>
              }
            </div>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table bea-integ-cards">
                <thead>
                  <tr>
                    <th scope="col" [attr.aria-sort]="sort('nom')"><bea-integ-tri colonne="nom" libelle="Destination" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                    <th scope="col">Fournisseur</th>
                    <th scope="col">Hôtes</th>
                    <th scope="col">Opérations</th>
                    <th scope="col" [attr.aria-sort]="sort('statut')"><bea-integ-tri colonne="statut" libelle="Statut" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                    <th scope="col" [attr.aria-sort]="sort('valide_le')"><bea-integ-tri colonne="valide_le" libelle="Approbation" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                    <th scope="col" [attr.aria-sort]="sort('updated_at')"><bea-integ-tri colonne="updated_at" libelle="Mise à jour" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                    <th scope="col"><span class="bea-integ-muted">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  @for (d of items(); track d.id) {
                    <tr>
                      <td data-label="Destination">
                        <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/destinations', d.id]">{{ d.nom }}</a>
                        <div class="bea-integ-muted"><code>{{ d.code }}</code> — {{ d.environnement }}</div>
                      </td>
                      <td data-label="Fournisseur">
                        <a [routerLink]="['/admin/integrations/fournisseurs', d.fournisseur_id]">{{ d.fournisseur_nom ?? 'Fournisseur' }}</a>
                      </td>
                      <td data-label="Hôtes" class="bea-integ-path">{{ d.hotes.join(', ') }}</td>
                      <td data-label="Opérations">{{ d.nb_operations ?? '—' }}</td>
                      <td data-label="Statut"><span [class]="tone(d.statut)">{{ label(d.statut) }}</span></td>
                      <td data-label="Approbation">{{ d.valide_le ? (d.valide_le | date: 'dd/MM/yyyy') : '—' }}</td>
                      <td data-label="Mise à jour">{{ d.updated_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td data-label="">
                        <div class="bea-integ-row-actions">
                          <a class="bea-integ-icon-btn" [routerLink]="['/admin/integrations/destinations', d.id]" [attr.aria-label]="'Consulter ' + d.nom" title="Consulter">
                            <bea-admin-icon name="visibility" />
                          </a>
                          @if (droits.manage() && modifiable(d)) {
                            <a class="bea-integ-icon-btn" [routerLink]="['/admin/integrations/destinations', d.id, 'modifier']" [attr.aria-label]="'Modifier ' + d.nom" title="Modifier">
                              <bea-admin-icon name="edit" />
                            </a>
                          }
                          @if (droits.manage() && d.statut !== 'archivee') {
                            <button type="button" class="bea-integ-icon-btn" data-tone="danger" [disabled]="suppression() === d.id"
                                    [attr.aria-label]="'Supprimer ' + d.nom" title="Supprimer (si jamais approuvée ni utilisée)" (click)="supprimer(d)">
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
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} destination(s)</span>
              <div>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1 || chargement()" (click)="aller(page() - 1)">Précédent</button>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages() || chargement()" (click)="aller(page() + 1)">Suivant</button>
              </div>
            </nav>
          }
        </div>
      }
    </section>
  `,
})
export class CoreAdminIntegrationDestinationsComponent implements OnInit {
  private readonly service = inject(CoreAdminIntegrationExecutionService);
  private readonly suppressions = inject(IntegrationSuppressionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  readonly droits = integrationDestinationsPermissions();
  readonly filtres = this.fb.nonNullable.group({ ...FILTRES_VIDES });
  readonly items = signal<DestinationResume[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 25;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly chargement = signal(true);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly suppression = signal<string | null>(null);
  readonly triActuel = signal<{ tri: string; ordre: OrdreTri }>({ tri: FILTRES_VIDES.tri, ordre: 'desc' });
  readonly label = destinationStatutLabel;
  readonly tone = destinationStatutTone;
  fournisseurId = '';

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    this.fournisseurId = qp.get('fournisseur') ?? '';
    this.filtres.patchValue({
      q: qp.get('q') ?? '',
      statut: qp.get('statut') ?? '',
      inclure_archivees: qp.get('inclure_archivees') === 'true',
      tri: qp.get('tri') ?? FILTRES_VIDES.tri,
      ordre: qp.get('ordre') ?? FILTRES_VIDES.ordre,
    });
    this.majTri();
    this.charger();
  }

  lienNouveau(): Record<string, string> {
    return this.fournisseurId ? { fournisseur: this.fournisseurId } : {};
  }

  modifiable(d: DestinationResume): boolean {
    return d.statut === 'brouillon' || d.statut === 'a_valider';
  }

  sort(colonne: string) {
    return ariaSort(this.triActuel(), colonne);
  }

  filtresActifs(): boolean {
    const v = this.filtres.getRawValue();
    return !!(v.q.trim() || v.statut || v.inclure_archivees);
  }

  trier(colonne: string): void {
    const ordreInitial: OrdreTri = colonne === 'updated_at' || colonne === 'valide_le' ? 'desc' : 'asc';
    this.filtres.patchValue(basculerTri(this.triActuel(), colonne, ordreInitial));
    this.rechercher();
  }

  rechercher(): void {
    this.page.set(1);
    this.majTri();
    this.synchroniserUrl();
    this.charger();
  }

  reinitialiser(): void {
    this.filtres.reset({ ...FILTRES_VIDES });
    this.rechercher();
  }

  aller(page: number): void {
    this.page.set(page);
    this.charger();
  }

  charger(): void {
    this.chargement.set(true);
    this.erreur.set(null);
    this.accesRefuse.set(false);
    const v = this.filtres.getRawValue();
    this.service
      .listerDestinations({ ...v, q: v.q.trim(), fournisseur_id: this.fournisseurId || undefined }, this.page(), this.size)
      .subscribe({
        next: (r) => {
          this.items.set(r.items ?? []);
          this.total.set(r.total ?? 0);
          this.page.set(r.page ?? 1);
          this.chargement.set(false);
        },
        error: (err) => {
          this.accesRefuse.set(estAccesRefuse(err));
          this.erreur.set(messageErreur(err, 'Impossible de charger les destinations.'));
          this.chargement.set(false);
        },
      });
  }

  async supprimer(d: DestinationResume): Promise<void> {
    if (this.suppression()) return;
    this.suppression.set(d.id);
    const ok = await this.suppressions.supprimer({
      objet: 'la destination',
      nom: d.nom,
      dependances: () => this.service.dependancesDestination(d.id),
      supprimer: (revision) => this.service.supprimerDestination(d.id, revision),
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

  private synchroniserUrl(): void {
    const v = this.filtres.getRawValue();
    const queryParams: Record<string, string> = {};
    if (this.fournisseurId) queryParams['fournisseur'] = this.fournisseurId;
    if (v.q.trim()) queryParams['q'] = v.q.trim();
    if (v.statut) queryParams['statut'] = v.statut;
    if (v.inclure_archivees) queryParams['inclure_archivees'] = 'true';
    if (v.tri !== FILTRES_VIDES.tri) queryParams['tri'] = v.tri;
    if (v.ordre !== FILTRES_VIDES.ordre) queryParams['ordre'] = v.ordre;
    void this.router.navigate([], { relativeTo: this.route, queryParams, replaceUrl: true });
  }
}
