import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  authLabel,
  disponibiliteLabel,
  disponibiliteTone,
  IntegrationErreur,
  integrationErreur,
  IntegrationExemple,
  IntegrationExemples,
  IntegrationOperationFiche,
  moduleEtatLabel,
  PERMISSION_STUDIO,
  permissionStatutLabel,
  schemaStatutLabel,
} from './core-admin-integrations.models';
import { CoreAdminIntegrationsService } from './core-admin-integrations.service';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

/** Valeur par défaut renvoyée par le backend dans les exemples ; remplacée à l'affichage. */
export const BASE_URL_EXEMPLE = 'https://bea-digital.exemple.invalid';

export function appliquerBaseUrl(code: string, baseUrl: string): string {
  const base = baseUrl.trim().replace(/\/+$/, '');
  if (!/^https?:\/\/[A-Za-z0-9.\-]+(:\d{1,5})?(\/[A-Za-z0-9._~\-/]*)?$/.test(base)) {
    return code;
  }
  return code.split(BASE_URL_EXEMPLE).join(base);
}

@Component({
  selector: 'bea-core-admin-integration-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <a class="bea-admin-table__link" routerLink="/admin/integrations/catalogue">← Catalogue API</a>
          <h1>Détail de l'opération</h1>
          <p><code>{{ operationId() }}</code></p>
        </div>
      </header>

      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement de l'opération…</p>
      } @else if (erreur(); as e) {
        @if (e.accesRefuse) {
          <div class="bea-admin-panel">
            <h2>Accès refusé</h2>
            <p class="bea-admin-panel__hint">
              Session BEA DIGITAL (Login 1) et permission <code>{{ permissionStudio }}</code> requises.
            </p>
          </div>
        } @else if (e.statut === 404) {
          <div class="bea-admin-panel">
            <h2>Opération introuvable</h2>
            <p class="bea-admin-panel__hint">
              Cet identifiant n'existe pas dans le catalogue de cette version de l'application.
            </p>
          </div>
        } @else {
          <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e.message }}</p></div>
          <button type="button" class="bea-admin-btn" (click)="charger()">Réessayer</button>
        }
      } @else if (fiche(); as f) {
        <div class="bea-integ-notice" role="note">
          <bea-admin-icon name="info" />
          <p>{{ f.avertissement }}</p>
        </div>

        <div class="bea-admin-panel bea-integ-section">
          <p>
            <span class="bea-integ-method" [attr.data-m]="f.methode">{{ f.methode }}</span>
            <span class="bea-integ-path">{{ f.chemin }}</span>
          </p>
          @if (f.resume) {
            <h2>{{ f.resume }}</h2>
          }
          @if (f.description) {
            <p class="bea-admin-panel__hint">{{ f.description }}</p>
          } @else if (f.disponibilite !== 'exclue') {
            <p class="bea-integ-muted">Aucune description dans le code source.</p>
          }
          <dl class="bea-admin-dl">
            <div><dt>Module</dt><dd>{{ f.module }} — {{ moduleEtatLabel(f.module_etat) }}</dd></div>
            <div><dt>Authentification</dt><dd>{{ authLabel(f.authentification) }}</dd></div>
            <div>
              <dt>Permissions</dt>
              <dd>
                @for (p of f.permissions; track p) {
                  <code>{{ p }}</code>&nbsp;
                } @empty {
                  <span class="bea-integ-muted">Aucune permission lue dans les dépendances.</span>
                }
                @if (f.exigence_permissions) {
                  <div>Exigence : <code>{{ f.exigence_permissions }}</code></div>
                }
                <div class="bea-integ-muted">
                  {{ permissionStatutLabel(f.permission_statut) }} — condition nécessaire, pas forcément suffisante.
                </div>
              </dd>
            </div>
            @if (f.dependances_non_analysees.length) {
              <div>
                <dt>Contrôles non analysés</dt>
                <dd>
                  @for (d of f.dependances_non_analysees; track d) {
                    <code>{{ d }}</code>&nbsp;
                  }
                </dd>
              </div>
            }
            <div><dt>Schéma de réponse</dt><dd>{{ schemaStatutLabel(f.schema_reponse_statut) }}</dd></div>
            <div>
              <dt>Disponibilité</dt>
              <dd><span [class]="'bea-badge ' + disponibiliteTone(f.disponibilite)">{{ disponibiliteLabel(f.disponibilite) }}</span></dd>
            </div>
            <div>
              <dt>Console</dt>
              <dd>
                @if (f.console) {
                  <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/console" [queryParams]="{ operation: f.operation_id }">
                    <bea-admin-icon name="terminal" /> Préparer dans la console
                  </a>
                } @else {
                  <span class="bea-integ-muted">{{ f.console_motif || 'Non admissible.' }}</span>
                }
              </dd>
            </div>
          </dl>
        </div>

        @if (f.motifs.length) {
          <div class="bea-integ-notice" role="note">
            <bea-admin-icon name="help" />
            <div>
              <p><strong>Pourquoi cette opération est {{ disponibiliteLabel(f.disponibilite).toLowerCase() }}</strong></p>
              <ul>
                @for (m of f.motifs; track m) {
                  <li>{{ m }}</li>
                }
              </ul>
            </div>
          </div>
        }

        @if (f.disponibilite !== 'exclue') {
          <div class="bea-admin-panel bea-integ-section">
            <h2>Paramètres</h2>
            @if (f.parametres.length === 0) {
              <p class="bea-admin-panel__empty">Aucun paramètre déclaré.</p>
            } @else {
              <div class="bea-admin-table-wrap">
                <table class="bea-admin-table">
                  <thead>
                    <tr><th>Nom</th><th>Emplacement</th><th>Type</th><th>Requis</th><th>Défaut / valeurs</th><th>Description</th></tr>
                  </thead>
                  <tbody>
                    @for (p of f.parametres; track p.emplacement + p.nom) {
                      <tr>
                        <td><code>{{ p.nom }}</code></td>
                        <td>{{ p.emplacement }}</td>
                        <td>{{ p.type }}</td>
                        <td>{{ p.requis ? 'Oui' : 'Non' }}</td>
                        <td>
                          @if (p.defaut !== null && p.defaut !== undefined) {
                            <code>{{ p.defaut }}</code>
                          }
                          @if (p.valeurs.length) {
                            <div class="bea-integ-muted">{{ p.valeurs.join(', ') }}</div>
                          }
                        </td>
                        <td>{{ p.description || '—' }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </div>

          @if (f.corps; as c) {
            <div class="bea-admin-panel bea-integ-section">
              <h2>Corps de requête</h2>
              <p class="bea-integ-muted">
                {{ c.type_contenu }} — {{ c.requis ? 'obligatoire' : 'facultatif' }}
                @if (c.schema_nom) { — schéma <code>{{ c.schema_nom }}</code> }
              </p>
              @if (c.champs.length) {
                <div class="bea-admin-table-wrap">
                  <table class="bea-admin-table">
                    <thead><tr><th>Champ</th><th>Type</th><th>Requis</th><th>Description</th></tr></thead>
                    <tbody>
                      @for (ch of c.champs; track ch.nom) {
                        <tr><td><code>{{ ch.nom }}</code></td><td>{{ ch.type }}</td><td>{{ ch.requis ? 'Oui' : 'Non' }}</td><td>{{ ch.description || '—' }}</td></tr>
                      }
                    </tbody>
                  </table>
                </div>
              }
            </div>
          }

          <div class="bea-admin-panel bea-integ-section">
            <h2>Réponses documentées</h2>
            @for (r of f.reponses; track r.code) {
              <div class="bea-integ-section">
                <p>
                  <strong>{{ r.code }}</strong> — {{ r.description || 'Sans description' }}
                  @if (r.schema_nom) { — <code>{{ r.schema_nom }}</code> }
                </p>
                @if (r.champs.length) {
                  <p class="bea-integ-muted">
                    @for (ch of r.champs; track ch.nom; let last = $last) {
                      <code>{{ ch.nom }}</code> ({{ ch.type }}){{ last ? '' : ', ' }}
                    }
                  </p>
                }
              </div>
            } @empty {
              <p class="bea-admin-panel__empty">Aucune réponse documentée.</p>
            }
          </div>

          <div class="bea-admin-panel bea-integ-section">
            <h2>Exemples d'appel</h2>
            @if (exemplesErreur()) {
              <p class="bea-admin-panel__empty">{{ exemplesErreur() }}</p>
            } @else if (exemples(); as ex) {
              @if (!ex.disponible) {
                <div class="bea-integ-notice" role="note">
                  <p>Aucun exemple exécutable n'est proposé : {{ ex.motif }}</p>
                </div>
              } @else {
                <div class="bea-integ-notice bea-integ-notice--info" role="note">
                  <div>
                    <p><strong>À exécuter uniquement avec un compte autorisé.</strong> Les valeurs entre chevrons sont des emplacements à remplacer ; aucun secret n'est fourni.</p>
                    <ul>
                      @for (p of ex.prerequis; track p) {
                        <li>{{ p }}</li>
                      }
                    </ul>
                  </div>
                </div>
                <label class="bea-admin-field bea-integ-section">
                  <span>URL de base</span>
                  <input type="url" [value]="baseUrl()" (input)="baseUrl.set($any($event.target).value)" maxlength="200" />
                </label>
                <div class="bea-integ-tabs" role="tablist">
                  @for (e of ex.exemples; track e.langage) {
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" role="tab" [attr.aria-selected]="onglet() === e.langage" (click)="onglet.set(e.langage)">
                      {{ e.libelle }}
                    </button>
                  }
                </div>
                @if (exempleCourant(); as e) {
                  <pre class="bea-integ-pre">{{ codeAffiche() }}</pre>
                  <p>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="copier()">
                      <bea-admin-icon name="content_copy" /> Copier
                    </button>
                  </p>
                }
              }
            } @else {
              <p class="bea-admin-dash__loading">Chargement des exemples…</p>
            }
          </div>
        }
      }
    </section>
  `,
})
export class CoreAdminIntegrationFicheComponent implements OnInit {
  private readonly studio = inject(CoreAdminIntegrationsService);
  private readonly route = inject(ActivatedRoute);
  private readonly feedback = inject(FeedbackService);

  readonly permissionStudio = PERMISSION_STUDIO;
  readonly operationId = signal('');
  readonly loading = signal(true);
  readonly erreur = signal<IntegrationErreur | null>(null);
  readonly fiche = signal<IntegrationOperationFiche | null>(null);
  readonly exemples = signal<IntegrationExemples | null>(null);
  readonly exemplesErreur = signal('');
  readonly onglet = signal<IntegrationExemple['langage']>('curl');
  readonly baseUrl = signal(typeof window !== 'undefined' ? window.location.origin : BASE_URL_EXEMPLE);

  readonly exempleCourant = computed(() => this.exemples()?.exemples.find((e) => e.langage === this.onglet()) ?? null);
  readonly codeAffiche = computed(() => {
    const e = this.exempleCourant();
    return e ? appliquerBaseUrl(e.code, this.baseUrl()) : '';
  });

  readonly authLabel = authLabel;
  readonly permissionStatutLabel = permissionStatutLabel;
  readonly schemaStatutLabel = schemaStatutLabel;
  readonly disponibiliteLabel = disponibiliteLabel;
  readonly disponibiliteTone = disponibiliteTone;
  readonly moduleEtatLabel = moduleEtatLabel;

  ngOnInit(): void {
    this.route.paramMap.subscribe((params) => {
      this.operationId.set(params.get('operationId') ?? '');
      this.charger();
    });
  }

  charger(): void {
    const id = this.operationId();
    this.loading.set(true);
    this.erreur.set(null);
    this.fiche.set(null);
    this.exemples.set(null);
    this.exemplesErreur.set('');
    this.studio.fiche(id).subscribe({
      next: (fiche) => {
        this.fiche.set(fiche);
        this.loading.set(false);
        if (fiche.disponibilite !== 'exclue') {
          this.chargerExemples(id);
        }
      },
      error: (err) => {
        this.erreur.set(integrationErreur(err, "Impossible de charger l'opération."));
        this.loading.set(false);
      },
    });
  }

  copier(): void {
    const code = this.codeAffiche();
    if (!code || typeof navigator === 'undefined' || !navigator.clipboard) {
      this.feedback.warning({ title: 'Copie indisponible dans ce navigateur.' });
      return;
    }
    navigator.clipboard.writeText(code).then(
      () => this.feedback.success({ title: 'Exemple copié.' }),
      () => this.feedback.warning({ title: "Le navigateur a refusé l'accès au presse-papiers." }),
    );
  }

  private chargerExemples(id: string): void {
    this.studio.exemples(id).subscribe({
      next: (ex) => {
        this.exemples.set(ex);
        if (ex.exemples.length) this.onglet.set(ex.exemples[0].langage);
      },
      error: (err) => this.exemplesErreur.set(integrationErreur(err, 'Impossible de charger les exemples.').message),
    });
  }
}
