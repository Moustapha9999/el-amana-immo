import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { estAccesRefuse, messageErreur, texteOuNull } from './core-admin-integration-clients.models';
import {
  AnalyseSpec,
  AUCUN_APPEL,
  EvenementFournisseur,
  extensionAcceptee,
  FournisseurFiche,
  FournisseurStatut,
  fournisseurStatutLabel,
  fournisseurStatutTone,
  integrationFournisseursPermissions,
  mecanismeLabel,
  OperationResume,
  SpecDetail,
  SpecResume,
  TAILLE_MAX_SPEC,
  TRANSITIONS_FOURNISSEUR,
  TransitionFournisseur,
} from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { ACCES_REFUSE_FOURNISSEURS, BANDEAU_AUCUN_APPEL } from './core-admin-integration-fournisseurs.component';
import { formatOctets } from './core-admin-integrations.models';
import { IntegrationSuppressionService, squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';
import { CoreAdminIntegrationTestComponent } from './core-admin-integration-test.component';
import { integrationTestsPermissions } from './core-admin-integration-execution.models';

export type OngletFournisseur = 'fiche' | 'operations' | 'import' | 'versions' | 'test' | 'historique';

const ONGLETS: readonly OngletFournisseur[] = ['fiche', 'operations', 'import', 'versions', 'test', 'historique'];

@Component({
  selector: 'bea-core-admin-integration-fournisseur-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DatePipe, CoreAdminIconComponent, CoreAdminIntegrationTestComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      @if (chargement()) {
        ${squelette('Chargement du fournisseur…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_FOURNISSEURS}
      } @else if (erreur(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/fournisseurs">Retour à la liste</a>
      } @else if (fiche(); as f) {
        <header class="bea-admin-dash__head bea-admin-users__head">
          <div>
            <p class="bea-admin-kicker"><a routerLink="/admin/integrations/fournisseurs">Fournisseurs externes</a></p>
            <h1>{{ f.nom }}</h1>
            <p><code>{{ f.code }}</code> — identifiant interne de la fiche.</p>
          </div>
          <div class="bea-admin-users__head-actions">
            <span class="bea-badge">{{ f.environnement }}</span>
            <span [class]="statutTone(f.statut)">{{ statutLabel(f.statut) }}</span>
          </div>
        </header>

        ${BANDEAU_AUCUN_APPEL}

        <div class="bea-integ-tabs" role="tablist" aria-label="Sections du fournisseur">
          @for (o of ongletsVisibles(); track o.id) {
            <button type="button" role="tab" class="bea-admin-btn bea-admin-btn--ghost" [attr.aria-selected]="onglet() === o.id" (click)="choisir(o.id)">
              {{ o.libelle }}
            </button>
          }
        </div>

        @switch (onglet()) {
          @case ('fiche') {
            <section class="bea-admin-panel">
              <h2>Fiche</h2>
              <p class="bea-admin-panel__hint">{{ f.avertissement }}</p>
              <dl class="bea-admin-dl">
                <div><dt>Identifiant interne</dt><dd><code>{{ f.code }}</code></dd></div>
                <div><dt>Environnement</dt><dd>{{ f.environnement }}</dd></div>
                <div><dt>Statut</dt><dd>{{ statutLabel(f.statut) }} @if (f.motif_statut) { — {{ f.motif_statut }} }</dd></div>
                <div>
                  <dt>Service responsable</dt>
                  <dd>{{ f.entite?.libelle ?? '—' }} @if (f.entite && !f.entite.actif) { <span class="bea-badge bea-badge--inactif">désactivé</span> }</dd>
                </div>
                <div><dt>Responsable interne</dt><dd>{{ f.responsable_interne ?? '—' }}</dd></div>
                <div><dt>Contact technique</dt><dd>{{ f.contact_technique ?? '—' }}</dd></div>
                <div><dt>URL de base déclarée</dt><dd><span class="bea-integ-path">{{ f.url_base ?? '—' }}</span> <span class="bea-integ-muted">(jamais contactée)</span></dd></div>
                <div><dt>Description</dt><dd>{{ f.description ?? '—' }}</dd></div>
                <div><dt>Documentation</dt><dd>{{ f.documentation ?? '—' }}</dd></div>
                <div><dt>Notes d'administration</dt><dd>{{ f.notes ?? '—' }}</dd></div>
                <div><dt>Spécification courante</dt><dd>{{ f.version_courante ? 'v' + f.version_courante : 'Aucune' }}</dd></div>
                <div><dt>Opérations</dt><dd>{{ f.nb_operations }}</dd></div>
                @if (f.valide_par) {
                  <div><dt>Validée</dt><dd>{{ f.valide_le | date: 'dd/MM/yyyy HH:mm' }} — {{ f.valide_par.nom ?? '—' }}</dd></div>
                }
                <div><dt>Créée</dt><dd>{{ f.created_at | date: 'dd/MM/yyyy HH:mm' }} — {{ f.cree_par?.nom ?? '—' }}</dd></div>
                <div><dt>Modifiée</dt><dd>{{ f.updated_at | date: 'dd/MM/yyyy HH:mm' }} — {{ f.modifie_par?.nom ?? '—' }}</dd></div>
                @if (f.statut === 'archive') {
                  <div><dt>Archivée</dt><dd>{{ f.archived_at | date: 'dd/MM/yyyy HH:mm' }} — {{ f.archive_par?.nom ?? '—' }} : {{ f.motif_archivage }}</dd></div>
                }
              </dl>
            </section>
            @if (f.statut !== 'archive' && (droits.manage() || droits.validate())) {
              <div class="bea-admin-actions">
                @if (droits.manage() && f.modifiable) {
                  <a class="bea-admin-btn" [routerLink]="['/admin/integrations/fournisseurs', f.id, 'modifier']">Modifier</a>
                }
                @for (t of transitionsVisibles(); track t.cible) {
                  <button type="button" class="bea-admin-btn" [class.bea-admin-btn--danger]="t.tone === 'danger'" [class.bea-admin-btn--ghost]="t.tone !== 'danger'" [disabled]="action()" (click)="changerStatut(t.cible, t)">
                    {{ t.libelle }}
                  </button>
                }
                @if (droits.manage()) {
                  <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="action()" (click)="archiver()">Archiver</button>
                  <button type="button" class="bea-admin-btn bea-integ-btn-danger-ghost" [disabled]="action()" (click)="supprimer()"
                          title="Possible seulement sans version, opération, destination, test ni alerte">
                    <bea-admin-icon name="delete" /> Supprimer
                  </button>
                }
              </div>
            }
          }

          @case ('operations') {
            <section class="bea-admin-panel">
              <div class="bea-admin-users__list-head">
                <h2>Opérations</h2>
                @if (droits.manage() && f.modifiable) {
                  <a class="bea-admin-btn" [routerLink]="['/admin/integrations/fournisseurs', f.id, 'operations', 'nouvelle']">Opération manuelle</a>
                }
              </div>
              <p class="bea-admin-panel__hint">
                Opérations de la spécification courante et opérations saisies à la main. Tout est déclaratif : rien n'est vérifié auprès du fournisseur.
              </p>
              <form class="bea-admin-toolbar" [formGroup]="opsFiltres" (ngSubmit)="chargerOperations(1)">
                <label class="bea-admin-field bea-admin-toolbar__search">
                  <span>Recherche</span>
                  <input type="search" formControlName="q" maxlength="120" placeholder="Nom, chemin, operationId, tag…" />
                </label>
                <label class="bea-admin-field">
                  <span>Méthode</span>
                  <select formControlName="methode">
                    <option value="">Toutes</option>
                    @for (m of methodes; track m) { <option [value]="m">{{ m }}</option> }
                  </select>
                </label>
                <label class="bea-admin-field">
                  <span>Origine</span>
                  <select formControlName="origine">
                    <option value="">Toutes</option>
                    <option value="openapi">Spécification importée</option>
                    <option value="manuelle">Configuration manuelle</option>
                  </select>
                </label>
                <div class="bea-admin-toolbar__actions">
                  <button type="submit" class="bea-admin-btn" [disabled]="opsChargement()">Filtrer</button>
                </div>
              </form>
              @if (opsChargement()) {
                <p class="bea-admin-dash__loading">Chargement des opérations…</p>
              } @else if (opsErreur(); as e) {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
                <button type="button" class="bea-admin-btn" (click)="chargerOperations(opsPage())">Réessayer</button>
              } @else if (operations().length === 0) {
                <p class="bea-admin-panel__empty">Aucune opération : importez une spécification OpenAPI ou saisissez une opération manuelle.</p>
              } @else {
                <div class="bea-admin-table-wrap">
                  <table class="bea-admin-table bea-integ-cards">
                    <thead><tr><th scope="col">Opération</th><th scope="col">Origine</th><th scope="col">Tags</th><th scope="col">Modification</th><th scope="col"><span class="bea-integ-muted">Actions</span></th></tr></thead>
                    <tbody>
                      @for (op of operations(); track op.id) {
                        <tr>
                          <td data-label="Opération">
                            <span class="bea-integ-method" [attr.data-m]="op.methode">{{ op.methode }}</span>
                            <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/fournisseurs', f.id, 'operations', op.id]">
                              <span class="bea-integ-path">{{ op.chemin }}</span>
                            </a>
                            <div class="bea-integ-muted">{{ op.nom ?? op.operation_id ?? '—' }}</div>
                            @if (op.deprecie) { <span class="bea-badge bea-badge--inactif">Dépréciée</span> }
                            @if (op.conflit) {
                              <div class="bea-admin-note" role="note">Conflit : même méthode et chemin dans la spécification et en saisie manuelle.</div>
                            }
                          </td>
                          <td data-label="Origine">
                            <span class="bea-integ-pill" [attr.data-tone]="op.origine === 'openapi' ? 'info' : null">
                              {{ op.origine === 'openapi' ? 'Importée · v' + op.spec_numero : 'Manuelle' }}
                            </span>
                          </td>
                          <td data-label="Tags">{{ op.tags.join(', ') || '—' }}</td>
                          <td data-label="Modification">{{ op.updated_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                          <td data-label="">
                            <div class="bea-integ-row-actions">
                              <a class="bea-integ-icon-btn" [routerLink]="['/admin/integrations/fournisseurs', f.id, 'operations', op.id]" [attr.aria-label]="'Consulter ' + op.chemin" title="Consulter">
                                <bea-admin-icon name="visibility" />
                              </a>
                              @if (droits.manage() && f.modifiable && op.origine === 'manuelle') {
                                <a class="bea-integ-icon-btn" [routerLink]="['/admin/integrations/fournisseurs', f.id, 'operations', op.id, 'modifier']" [attr.aria-label]="'Modifier ' + op.chemin" title="Modifier">
                                  <bea-admin-icon name="edit" />
                                </a>
                                <button type="button" class="bea-integ-icon-btn" data-tone="danger" [disabled]="action()"
                                        [attr.aria-label]="'Supprimer ' + op.chemin" title="Supprimer (si aucune dépendance)" (click)="supprimerOperation(op)">
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
                <div class="bea-admin-pager">
                  <span>Page {{ opsPage() }} / {{ opsPages() }} — {{ opsTotal() }} opération(s)</span>
                  <div>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="opsPage() <= 1" (click)="chargerOperations(opsPage() - 1)">Précédent</button>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="opsPage() >= opsPages()" (click)="chargerOperations(opsPage() + 1)">Suivant</button>
                  </div>
                </div>
              }
            </section>
          }

          @case ('test') {
            <bea-core-admin-integration-test [fournisseurId]="f.id" />
          }

          @case ('import') {
            <section class="bea-admin-panel">
              <h2>Importer une spécification OpenAPI</h2>
              <p class="bea-admin-panel__hint">
                Fichier JSON ou YAML (OpenAPI 3.0 ou 3.1), {{ tailleMax }} maximum. Le fichier est analysé sur le serveur sans
                aucun accès réseau : les références externes (<code>$ref</code> vers une URL ou un autre fichier) sont signalées,
                jamais chargées. Rien n'est enregistré avant votre confirmation.
              </p>
              @if (!f.modifiable) {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>Import impossible au statut « {{ statutLabel(f.statut) }} ».</p></div>
              } @else {
                <label class="bea-admin-field">
                  <span>Fichier de spécification</span>
                  <input type="file" accept=".json,.yaml,.yml,application/json,application/yaml" (change)="choisirFichier($event)" [disabled]="analyseEnCours() || importEnCours()" />
                </label>
                @if (fichierErreur(); as e) { <p class="bea-admin-note" role="alert">{{ e }}</p> }
                @if (fichier(); as fi) {
                  <div class="bea-admin-form__actions">
                    <button type="button" class="bea-admin-btn" [disabled]="analyseEnCours()" (click)="analyser()">
                      {{ analyseEnCours() ? 'Analyse…' : 'Analyser ' + fi.name }}
                    </button>
                  </div>
                }
                @if (analyseErreur(); as e) {
                  <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
                }
                @if (analyse(); as a) {
                  <div class="bea-integ-section">
                    <h3>Aperçu — {{ a.nom_fichier }}</h3>
                    <p class="bea-integ-muted">{{ a.avertissement }}</p>
                    <dl class="bea-admin-dl">
                      <div><dt>Résultat</dt><dd>
                        @if (a.valide) { <span class="bea-badge bea-badge--actif">Spécification valide</span> }
                        @else { <span class="bea-badge bea-badge--inactif">Spécification refusée</span> }
                      </dd></div>
                      <div><dt>Format</dt><dd>{{ a.format ?? '—' }} — OpenAPI {{ a.openapi_version ?? '?' }}</dd></div>
                      <div><dt>Titre / version déclarée</dt><dd>{{ a.titre ?? '—' }} — {{ a.version_api ?? '—' }}</dd></div>
                      <div><dt>Taille</dt><dd>{{ octets(a.taille) }}</dd></div>
                      <div><dt>Empreinte SHA-256</dt><dd><code>{{ a.empreinte }}</code></dd></div>
                      <div><dt>Opérations</dt><dd>{{ a.nb_operations }}</dd></div>
                      <div><dt>Serveurs déclarés</dt><dd>
                        @for (s of a.serveurs; track s.url) { <div><span class="bea-integ-path">{{ s.url }}</span> <span class="bea-integ-muted">(non contacté)</span></div> }
                        @empty { — }
                      </dd></div>
                      <div><dt>Authentification déclarée</dt><dd>
                        @for (m of a.securite; track m.nom) { <div>{{ m.nom }} : {{ mecanisme(m) }}</div> } @empty { — }
                      </dd></div>
                      @if (a.version_courante) {
                        <div><dt>Version courante</dt><dd>v{{ a.version_courante }}</dd></div>
                      }
                    </dl>

                    @if (a.erreurs.length) {
                      <div class="bea-integ-notice bea-integ-notice--danger" role="alert">
                        <ul>
                          @for (m of a.erreurs; track $index) {
                            <li><code>{{ m.code }}</code> {{ m.message }} @if (m.emplacement) { <span class="bea-integ-muted">({{ m.emplacement }})</span> }</li>
                          }
                        </ul>
                      </div>
                    }
                    @if (a.avertissements.length) {
                      <div class="bea-integ-notice" role="note">
                        <bea-admin-icon name="warning" />
                        <ul>
                          @for (m of a.avertissements; track $index) {
                            <li><code>{{ m.code }}</code> {{ m.message }} @if (m.emplacement) { <span class="bea-integ-muted">({{ m.emplacement }})</span> }</li>
                          }
                        </ul>
                      </div>
                    }
                    @if (a.deja_importee) {
                      <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>Ce fichier est déjà importé (version v{{ a.deja_importee }}).</p></div>
                    }
                    @if (a.diff; as d) {
                      <h3>Différences avec la version courante</h3>
                      <p class="bea-integ-muted">
                        {{ d.ajoutees.length }} ajoutée(s), {{ d.supprimees.length }} supprimée(s), {{ d.modifiees.length }} modifiée(s), {{ d.inchangees }} inchangée(s).
                      </p>
                      @if (d.ajoutees.length) { <p><strong>Ajoutées :</strong> <span class="bea-integ-path">{{ d.ajoutees.join(' · ') }}</span></p> }
                      @if (d.supprimees.length) { <p><strong>Supprimées :</strong> <span class="bea-integ-path">{{ d.supprimees.join(' · ') }}</span></p> }
                      @if (d.modifiees.length) { <p><strong>Modifiées :</strong> <span class="bea-integ-path">{{ d.modifiees.join(' · ') }}</span></p> }
                    }
                    @if (a.conflits.length) {
                      <div class="bea-integ-notice bea-integ-notice--danger" role="alert">
                        <p>
                          Conflit avec des opérations manuelles : {{ a.conflits.join(' · ') }}. Les deux seront conservées et signalées ;
                          cochez la case pour confirmer en connaissance de cause.
                        </p>
                      </div>
                      <label><input type="checkbox" [checked]="accepterConflits()" (change)="accepterConflits.set(!accepterConflits())" /> J'accepte ces conflits</label>
                    }
                    @if (a.operations.length) {
                      <details>
                        <summary>Opérations détectées ({{ a.operations.length }})</summary>
                        <ul>
                          @for (op of a.operations; track op.cle) {
                            <li>
                              <span class="bea-integ-method" [attr.data-m]="op.methode">{{ op.methode }}</span>
                              <span class="bea-integ-path">{{ op.chemin }}</span>
                              <span class="bea-integ-muted">{{ op.nom ?? op.operation_id ?? '' }}</span>
                              @if (op.deprecie) { <span class="bea-badge bea-badge--inactif">Dépréciée</span> }
                            </li>
                          }
                        </ul>
                      </details>
                    }
                    <div class="bea-admin-form__actions">
                      <button type="button" class="bea-admin-btn" [disabled]="!importable() || importEnCours()" (click)="importer()">
                        {{ importEnCours() ? 'Import…' : 'Confirmer l’import' }}
                      </button>
                      <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="importEnCours()" (click)="annulerImport()">Annuler</button>
                    </div>
                  </div>
                }
              }
            </section>
          }

          @case ('versions') {
            <section class="bea-admin-panel">
              <h2>Versions de la spécification</h2>
              @if (specsChargement()) {
                <p class="bea-admin-dash__loading">Chargement des versions…</p>
              } @else if (specsErreur(); as e) {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
              } @else if (specs().length === 0) {
                <p class="bea-admin-panel__empty">Aucune spécification importée.</p>
              } @else {
                <div class="bea-admin-table-wrap">
                  <table class="bea-admin-table">
                    <thead><tr><th>Version</th><th>Fichier</th><th>OpenAPI</th><th>Opérations</th><th>Avertissements</th><th>Import</th><th></th></tr></thead>
                    <tbody>
                      @for (s of specs(); track s.id) {
                        <tr>
                          <td>v{{ s.numero }} @if (s.courante) { <span class="bea-badge bea-badge--actif">Courante</span> }</td>
                          <td>{{ s.nom_fichier }} <div class="bea-integ-muted">{{ octets(s.taille) }} — <code>{{ s.empreinte.slice(0, 12) }}…</code></div></td>
                          <td>{{ s.openapi_version }} <div class="bea-integ-muted">{{ s.titre }} {{ s.version_api }}</div></td>
                          <td>{{ s.nb_operations }}</td>
                          <td>{{ s.nb_avertissements }}</td>
                          <td>{{ s.created_at | date: 'dd/MM/yyyy HH:mm' }} <div class="bea-integ-muted">{{ s.importe_par?.nom ?? '—' }}</div></td>
                          <td><button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="voirSpec(s)">Détail</button></td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              }
              @if (specDetail(); as sd) {
                <div class="bea-integ-section">
                  <h3>Version v{{ sd.numero }} — {{ sd.titre }} {{ sd.version_api }}</h3>
                  @if (sd.description) { <p>{{ sd.description }}</p> }
                  <p><strong>Serveurs déclarés (non contactés) :</strong>
                    @for (s of sd.serveurs; track s.url) { <span class="bea-integ-path">{{ s.url }}</span>&nbsp; } @empty { — }
                  </p>
                  <p><strong>Authentification déclarée :</strong>
                    @for (m of sd.securite; track m.nom) { {{ m.nom }} ({{ mecanisme(m) }})&nbsp; } @empty { — }
                  </p>
                  @if (sd.avertissements.length) {
                    <ul>@for (m of sd.avertissements; track $index) { <li><code>{{ m.code }}</code> {{ m.message }}</li> }</ul>
                  }
                </div>
              }
            </section>
          }

          @case ('historique') {
            <section class="bea-admin-panel">
              <h2>Historique</h2>
              @if (histChargement()) {
                <p class="bea-admin-dash__loading">Chargement de l'historique…</p>
              } @else if (histErreur(); as e) {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
              } @else if (historique().length === 0) {
                <p class="bea-admin-panel__empty">Aucun évènement.</p>
              } @else {
                <div class="bea-admin-table-wrap">
                  <table class="bea-admin-table">
                    <thead><tr><th>Date</th><th>Évènement</th><th>Par</th><th>Détails</th></tr></thead>
                    <tbody>
                      @for (e of historique(); track e.id) {
                        <tr>
                          <td>{{ e.created_at | date: 'dd/MM/yyyy HH:mm:ss' }}</td>
                          <td>{{ e.libelle }}</td>
                          <td>{{ e.acteur?.nom ?? '—' }}</td>
                          <td><span class="bea-integ-muted">{{ details(e) }}</span></td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
                <div class="bea-admin-pager">
                  <span>Page {{ histPage() }} / {{ histPages() }} — {{ histTotal() }} évènement(s)</span>
                  <div>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="histPage() <= 1" (click)="chargerHistorique(histPage() - 1)">Précédent</button>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="histPage() >= histPages()" (click)="chargerHistorique(histPage() + 1)">Suivant</button>
                  </div>
                </div>
              }
            </section>
          }
        }
      }
    </section>
  `,
})
export class CoreAdminIntegrationFournisseurFicheComponent implements OnInit {
  private readonly service = inject(CoreAdminIntegrationFournisseursService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly suppressions = inject(IntegrationSuppressionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  readonly droits = integrationFournisseursPermissions();
  readonly droitsTests = integrationTestsPermissions();

  readonly chargement = signal(true);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly fiche = signal<FournisseurFiche | null>(null);
  readonly onglet = signal<OngletFournisseur>('fiche');
  readonly action = signal(false);

  readonly methodes = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
  readonly opsFiltres = this.fb.nonNullable.group({ q: '', methode: '', origine: '' });
  readonly operations = signal<OperationResume[]>([]);
  readonly opsTotal = signal(0);
  readonly opsPage = signal(1);
  readonly opsChargement = signal(false);
  readonly opsErreur = signal<string | null>(null);
  readonly opsPages = computed(() => Math.max(1, Math.ceil(this.opsTotal() / 50)));

  readonly tailleMax = formatOctets(TAILLE_MAX_SPEC);
  readonly fichier = signal<File | null>(null);
  readonly fichierErreur = signal<string | null>(null);
  readonly analyse = signal<AnalyseSpec | null>(null);
  readonly analyseEnCours = signal(false);
  readonly analyseErreur = signal<string | null>(null);
  readonly accepterConflits = signal(false);
  readonly importEnCours = signal(false);
  readonly importable = computed(() => {
    const a = this.analyse();
    return !!a && a.valide && !a.deja_importee && (a.conflits.length === 0 || this.accepterConflits());
  });

  readonly specs = signal<SpecResume[]>([]);
  readonly specsChargement = signal(false);
  readonly specsErreur = signal<string | null>(null);
  readonly specDetail = signal<SpecDetail | null>(null);

  readonly historique = signal<EvenementFournisseur[]>([]);
  readonly histTotal = signal(0);
  readonly histPage = signal(1);
  readonly histChargement = signal(false);
  readonly histErreur = signal<string | null>(null);
  readonly histPages = computed(() => Math.max(1, Math.ceil(this.histTotal() / 50)));

  readonly statutLabel = fournisseurStatutLabel;
  readonly statutTone = fournisseurStatutTone;
  readonly mecanisme = mecanismeLabel;
  readonly octets = formatOctets;

  readonly ongletsVisibles = computed(() => {
    const tous: { id: OngletFournisseur; libelle: string; visible: boolean }[] = [
      { id: 'fiche', libelle: 'Fiche', visible: true },
      { id: 'operations', libelle: 'Opérations', visible: true },
      { id: 'import', libelle: 'Import OpenAPI', visible: this.droits.manage() },
      { id: 'versions', libelle: 'Versions', visible: true },
      { id: 'test', libelle: 'Test contrôlé', visible: this.droitsTests.view() || this.droitsTests.execute() },
      { id: 'historique', libelle: 'Historique', visible: true },
    ];
    return tous.filter((o) => o.visible);
  });

  readonly transitionsVisibles = computed(() => {
    const f = this.fiche();
    if (!f) return [];
    return f.transitions
      .map((cible) => ({ cible, t: TRANSITIONS_FOURNISSEUR[cible] }))
      .filter((x): x is { cible: FournisseurStatut; t: TransitionFournisseur } => !!x.t && this.droits[x.t.droit]())
      .map(({ cible, t }) => ({ cible, ...t }));
  });

  private id = '';

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    const demande = this.route.snapshot.queryParamMap.get('onglet') as OngletFournisseur | null;
    this.chargerFiche(() => {
      if (demande && ONGLETS.includes(demande) && this.ongletsVisibles().some((o) => o.id === demande)) {
        this.choisir(demande);
      }
    });
  }

  chargerFiche(apres?: () => void): void {
    this.service.fiche(this.id).subscribe({
      next: (f) => {
        this.fiche.set(f);
        this.chargement.set(false);
        apres?.();
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Fournisseur introuvable.'));
        this.chargement.set(false);
      },
    });
  }

  choisir(o: OngletFournisseur): void {
    this.onglet.set(o);
    void this.router.navigate([], { relativeTo: this.route, queryParams: { onglet: o === 'fiche' ? null : o }, replaceUrl: true });
    if (o === 'operations') this.chargerOperations(1);
    if (o === 'versions') this.chargerSpecs();
    if (o === 'historique') this.chargerHistorique(1);
  }

  // ------------------------------------------------------------------ statut
  async changerStatut(cible: FournisseurStatut, t: TransitionFournisseur): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    const message =
      cible === 'valide'
        ? `Valider la configuration de « ${f.nom} » ? La validation atteste que la fiche a été examinée ; aucun appel au fournisseur n'est effectué ni autorisé.`
        : `${t.libelle} : « ${f.nom} » ?`;
    const valeurs = await this.dialogs.prompt({
      title: t.libelle,
      message,
      tone: t.tone,
      confirmLabel: t.libelle,
      fields: [{ key: 'motif', label: t.motif === 'obligatoire' ? 'Motif (obligatoire)' : 'Motif (facultatif)' }],
      validate: (v) => (t.motif === 'obligatoire' && (v['motif'] ?? '').trim().length < 3 ? 'Motif obligatoire (3 caractères minimum).' : null),
    });
    if (!valeurs) return;
    this.action.set(true);
    this.service.changerStatut(f.id, f.revision, cible, texteOuNull(valeurs['motif'])).subscribe({
      next: (r) => {
        this.fiche.set(r);
        this.action.set(false);
        void this.dialogs.success(`Statut : ${fournisseurStatutLabel(r.statut)}. ${AUCUN_APPEL}`);
      },
      error: (err) => {
        this.action.set(false);
        void this.dialogs.error(messageErreur(err, 'Changement de statut impossible.'));
      },
    });
  }

  async archiver(): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    const valeurs = await this.dialogs.prompt({
      title: 'Archiver le fournisseur',
      message: `Archiver « ${f.nom} » ? Rien n'est supprimé : la fiche, ses versions et son historique restent consultables.`,
      tone: 'danger',
      confirmLabel: 'Archiver',
      fields: [{ key: 'motif', label: 'Motif (obligatoire)' }],
      validate: (v) => ((v['motif'] ?? '').trim().length < 3 ? 'Motif obligatoire (3 caractères minimum).' : null),
    });
    if (!valeurs) return;
    this.action.set(true);
    this.service.archiver(f.id, f.revision, valeurs['motif'].trim()).subscribe({
      next: (r) => {
        this.fiche.set(r);
        this.action.set(false);
        void this.dialogs.success(`« ${r.nom} » a été archivé.`);
      },
      error: (err) => {
        this.action.set(false);
        void this.dialogs.error(messageErreur(err, 'Archivage impossible.'));
      },
    });
  }

  async supprimer(): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    this.action.set(true);
    const ok = await this.suppressions.supprimer({
      objet: 'le fournisseur',
      nom: f.nom,
      dependances: () => this.service.dependances(f.id),
      supprimer: (revision) => this.service.supprimer(f.id, revision),
    });
    this.action.set(false);
    if (ok) void this.router.navigate(['/admin/integrations/fournisseurs']);
  }

  async supprimerOperation(op: OperationResume): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    this.action.set(true);
    const ok = await this.suppressions.supprimer({
      objet: 'l’opération manuelle',
      nom: `${op.methode} ${op.chemin}`,
      dependances: () => this.service.dependancesOperation(f.id, op.id),
      supprimer: (revision) => this.service.supprimerOperation(f.id, op.id, revision),
    });
    this.action.set(false);
    if (ok) {
      this.chargerOperations(this.operations().length === 1 && this.opsPage() > 1 ? this.opsPage() - 1 : this.opsPage());
      this.service.fiche(f.id).subscribe({ next: (r) => this.fiche.set(r), error: () => undefined });
    }
  }

  // ------------------------------------------------------------------ opérations
  chargerOperations(page: number): void {
    const v = this.opsFiltres.getRawValue();
    this.opsChargement.set(true);
    this.opsErreur.set(null);
    this.service.operations(this.id, v, page, 50).subscribe({
      next: (r) => {
        this.operations.set(r.items ?? []);
        this.opsTotal.set(r.total ?? 0);
        this.opsPage.set(r.page ?? page);
        this.opsChargement.set(false);
      },
      error: (err) => {
        this.opsErreur.set(messageErreur(err, 'Impossible de charger les opérations.'));
        this.opsChargement.set(false);
      },
    });
  }

  // ------------------------------------------------------------------ import
  choisirFichier(event: Event): void {
    const input = event.target as HTMLInputElement;
    const fi = input.files?.[0] ?? null;
    this.analyse.set(null);
    this.analyseErreur.set(null);
    this.accepterConflits.set(false);
    this.fichierErreur.set(null);
    this.fichier.set(null);
    if (!fi) return;
    if (!extensionAcceptee(fi.name)) {
      this.fichierErreur.set('Extension attendue : .json, .yaml ou .yml.');
      input.value = '';
      return;
    }
    if (fi.size > TAILLE_MAX_SPEC) {
      this.fichierErreur.set(`Fichier trop volumineux (${this.tailleMax} maximum).`);
      input.value = '';
      return;
    }
    this.fichier.set(fi);
  }

  analyser(): void {
    const fi = this.fichier();
    if (!fi || this.analyseEnCours()) return;
    this.analyseEnCours.set(true);
    this.analyseErreur.set(null);
    this.analyse.set(null);
    this.accepterConflits.set(false);
    this.service.analyser(this.id, fi).subscribe({
      next: (a) => {
        this.analyse.set(a);
        this.analyseEnCours.set(false);
      },
      error: (err) => {
        this.analyseErreur.set(messageErreur(err, 'Analyse impossible.'));
        this.analyseEnCours.set(false);
      },
    });
  }

  async importer(): Promise<void> {
    const fi = this.fichier();
    const a = this.analyse();
    if (!fi || !a || !this.importable() || this.importEnCours()) return;
    const ok = await this.dialogs.confirm({
      title: 'Confirmer l’import',
      message:
        `Enregistrer « ${a.nom_fichier} » comme nouvelle version (${a.nb_operations} opération(s)) ? ` +
        'Les versions précédentes restent consultables. Aucun serveur déclaré ne sera contacté.',
      confirmLabel: 'Importer',
    });
    if (!ok) return;
    this.importEnCours.set(true);
    this.service.importer(this.id, fi, a.empreinte, a.version_courante ?? null, this.accepterConflits()).subscribe({
      next: (s) => {
        this.importEnCours.set(false);
        this.annulerImport();
        this.chargerFiche();
        void this.dialogs.success(`Version v${s.numero} importée (${s.nb_operations} opération(s)). ${AUCUN_APPEL}`);
      },
      error: (err) => {
        this.importEnCours.set(false);
        void this.dialogs.error(messageErreur(err, 'Import impossible.'));
      },
    });
  }

  annulerImport(): void {
    this.fichier.set(null);
    this.analyse.set(null);
    this.analyseErreur.set(null);
    this.accepterConflits.set(false);
  }

  // ------------------------------------------------------------------ versions & historique
  chargerSpecs(): void {
    this.specsChargement.set(true);
    this.specsErreur.set(null);
    this.service.specs(this.id).subscribe({
      next: (r) => {
        this.specs.set(r.items ?? []);
        this.specsChargement.set(false);
      },
      error: (err) => {
        this.specsErreur.set(messageErreur(err, 'Impossible de charger les versions.'));
        this.specsChargement.set(false);
      },
    });
  }

  voirSpec(s: SpecResume): void {
    this.service.spec(this.id, s.id).subscribe({
      next: (d) => this.specDetail.set(d),
      error: (err) => void this.dialogs.error(messageErreur(err, 'Version introuvable.')),
    });
  }

  chargerHistorique(page: number): void {
    this.histChargement.set(true);
    this.histErreur.set(null);
    this.service.historique(this.id, page, 50).subscribe({
      next: (r) => {
        this.historique.set(r.items ?? []);
        this.histTotal.set(r.total ?? 0);
        this.histPage.set(r.page ?? page);
        this.histChargement.set(false);
      },
      error: (err) => {
        this.histErreur.set(messageErreur(err, "Impossible de charger l'historique."));
        this.histChargement.set(false);
      },
    });
  }

  details(e: EvenementFournisseur): string {
    return detailsEvenement(e);
  }
}

const valeurTexte = (v: unknown): string =>
  v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v);

/** Champs modifiés entre les états « avant » et « après » enregistrés par l'audit. */
export function detailsEvenement(e: EvenementFournisseur): string {
  const avant = (e.details?.['avant'] ?? {}) as Record<string, unknown>;
  const apres = (e.details?.['apres'] ?? {}) as Record<string, unknown>;
  const cles = [...new Set([...Object.keys(avant), ...Object.keys(apres)])].sort();
  const lignes = cles
    .filter((k) => JSON.stringify(avant[k]) !== JSON.stringify(apres[k]))
    .map((k) => (k in avant ? `${k} : ${valeurTexte(avant[k])} → ${valeurTexte(apres[k])}` : `${k} : ${valeurTexte(apres[k])}`));
  const texte = lignes.join(' ; ');
  return texte.length > 400 ? `${texte.slice(0, 400)}…` : texte || '—';
}
