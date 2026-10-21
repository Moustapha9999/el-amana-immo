import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CoreAdminIntegrationAccesComponent } from './core-admin-integration-acces.component';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import { integrationStudioPermissions, PERMISSIONS_STUDIO } from './core-admin-integration-execution.models';
import { CoreAdminIntegrationTestComponent } from './core-admin-integration-test.component';
import { FournisseurResume } from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

@Component({
  selector: 'bea-core-admin-integration-tests-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, CoreAdminIntegrationAccesComponent, CoreAdminIntegrationTestComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations">Studio d'intégration API</a></p>
          <h1>Tests d’intégration</h1>
          <p>
            Test manuel d’une opération GET ou HEAD d’un fournisseur validé, vers une destination TEST approuvée.
            Rien n’est envoyé sans aperçu puis confirmation explicite ; aucun test n’est lancé automatiquement.
          </p>
        </div>
      </header>

      @if (!d.testsExecute() && !d.testsView()) {
        <bea-integ-acces-refuse section="Les tests d’intégration" [permissions]="[P.testsExecute, P.testsView]" />
      } @else if (prerequisManquants().length) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert">
          <p>Préparer un test exige aussi de consulter les fournisseurs et les destinations. Permissions manquantes :</p>
          <ul>
            @for (p of prerequisManquants(); track p) { <li><code>{{ p }}</code></li> }
          </ul>
        </div>
        @if (d.testsView()) {
          <p><a class="bea-admin-table__link" routerLink="/admin/integrations/executions">Consulter l’historique des exécutions</a></p>
        }
      } @else {
        <div class="bea-integ-notice bea-integ-notice--info" role="note">
          <ul>
            <li>Environnement TEST uniquement, HTTPS sur le port 443, hôtes figés par la destination approuvée.</li>
            <li>Adresses internes, privées ou de métadonnées refusées après résolution DNS ; connexion épinglée sur l’adresse vérifiée.</li>
            <li>Aucune redirection suivie ; réponse limitée à 64 Kio ; délai de 3 s (connexion) et 8 s (lecture).</li>
            <li>Quotas : 10 tests par utilisateur et 20 par fournisseur sur 10 minutes, 3 simultanés. Sans service de quota, aucun test n’est envoyé.</li>
            <li>Opérations authentifiées bloquées : aucun coffre de secrets n’est approuvé.</li>
          </ul>
        </div>
        <section class="bea-admin-panel">
          <label class="bea-admin-field">
            <span>Fournisseur validé (TEST)</span>
            <select [formControl]="choix">
              <option value="">Choisir…</option>
              @for (f of fournisseurs(); track f.id) {
                <option [value]="f.id">{{ f.nom }} ({{ f.code }}) — {{ f.nb_operations }} opération(s)</option>
              }
            </select>
          </label>
          @if (chargement()) {
            <p class="bea-admin-dash__loading">Chargement des fournisseurs validés…</p>
          } @else if (erreur(); as e) {
            <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
          } @else if (fournisseurs().length === 0) {
            <p class="bea-admin-panel__empty">
              Aucun fournisseur validé en TEST. Un fournisseur doit être configuré puis validé avant tout test.
              <a class="bea-admin-table__link" routerLink="/admin/integrations/fournisseurs">Fournisseurs externes</a>
            </p>
          }
        </section>
        @for (id of selection(); track id) {
          <bea-core-admin-integration-test [fournisseurId]="id" [destinationInitiale]="destinationInitiale" />
        }
      }
    </section>
  `,
})
export class CoreAdminIntegrationTestsPageComponent implements OnInit {
  private readonly fourn = inject(CoreAdminIntegrationFournisseursService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly d = integrationStudioPermissions();
  readonly P = PERMISSIONS_STUDIO;
  readonly choix = new FormControl('', { nonNullable: true });
  readonly fournisseurs = signal<FournisseurResume[]>([]);
  readonly chargement = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly fournisseurId = signal('');
  readonly selection = computed(() => (this.fournisseurId() ? [this.fournisseurId()] : []));
  readonly prerequisManquants = computed(() => {
    const manquants: string[] = [];
    if (!this.d.fournisseurs()) manquants.push(PERMISSIONS_STUDIO.fournisseurs);
    if (!this.d.destinations()) manquants.push(PERMISSIONS_STUDIO.destinations);
    return manquants;
  });
  destinationInitiale = '';

  ngOnInit(): void {
    if ((!this.d.testsExecute() && !this.d.testsView()) || this.prerequisManquants().length) return;
    const qp = this.route.snapshot.queryParamMap;
    const initial = qp.get('fournisseur') ?? '';
    this.destinationInitiale = qp.get('destination') ?? '';
    this.chargement.set(true);
    this.fourn.lister({ statut: 'valide', environnement: 'TEST' }, 1, 100).subscribe({
      next: (page) => {
        this.fournisseurs.set(page.items);
        this.chargement.set(false);
        if (initial && page.items.some((f) => f.id === initial)) {
          this.choix.setValue(initial);
          this.fournisseurId.set(initial);
        }
      },
      error: (err) => {
        this.erreur.set(estAccesRefuse(err) ? 'Accès refusé par le serveur.' : messageErreur(err, 'Fournisseurs indisponibles.'));
        this.chargement.set(false);
      },
    });
    this.choix.valueChanges.subscribe((id) => {
      this.fournisseurId.set(id);
      this.destinationInitiale = '';
      void this.router.navigate([], { relativeTo: this.route, queryParams: id ? { fournisseur: id } : {}, replaceUrl: true });
    });
  }
}
