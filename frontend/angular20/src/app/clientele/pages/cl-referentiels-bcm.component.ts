import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateHeureFr, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface Version {
  id: string; libelle: string; fichier_nom: string; sha256: string; statut: 'BROUILLON' | 'ACTIVE' | 'ARCHIVEE';
  nb_codes: number; nb_pp: number; nb_pm: number; anomalies: { ligne: number; code: string | null; motif: string }[];
  observations: string | null; importe_par: string | null; importe_le: string | null;
  activee_le: string | null; archivee_le: string | null; nb_declarations: number; doublons: number;
}
interface Code { ligne: number; code: string; libelle: string; categorie: string | null; usage: string; }
interface Codes { version: Version | null; total: number; items: Code[]; }
interface Comparaison {
  a: Version; b: Version;
  ajoutes: (Code & { code: string })[]; retires: (Code & { code: string })[];
  modifies: { code: string; ecarts: Record<string, { avant: string | null; apres: string | null }> }[];
}
interface AgenceSic {
  agence_id: string; code: string; libelle: string; ville: string | null; valeur: string | null;
  observation: string | null; maj_par: string | null; maj_le: string | null; nb_clients: number;
}
interface SecteurSic {
  libelle_orion: string; cle: string; nb_clients_pm: number; generique: boolean; code_bcm: string | null;
  statut: string | null; observation: string | null; maj_par: string | null; maj_le: string | null; code_valide: boolean | null;
}
interface Complement {
  racine: string; genre: string | null; telephone: string | null; code_csp_bcm: string | null;
  code_secteur_bcm: string | null; sic_source: string | null; sic_maj_le: string | null;
}
interface ImportComplements {
  fichier: string; lignes: number; retenues: number; nb_rejets: number; applique: boolean;
  rejets: { ligne: number; racine: string; motif: string }[];
}
type Onglet = 'versions' | 'codes' | 'agences' | 'secteurs' | 'complements';

const BADGE_VERSION: Record<string, string> = { BROUILLON: 'BROUILLON', ACTIVE: 'VALIDEE', ARCHIVEE: 'ARCHIVEE' };

@Component({
  selector: 'bea-cl-referentiels-bcm',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Déclarations BCM</p>
          <h1>Gestion des référentiels BCM</h1>
          <p class="bea-cl-head__sub">Référentiel officiel versionné (feuille « ref »), correspondances agences et secteurs, compléments KYC nécessaires au fichier SIC. Toute modification est tracée.</p>
        </div>
      </header>
      @if (!peutGerer()) {
        <p class="bea-cl-note bea-cl-note--info"><mat-icon>visibility</mat-icon>Consultation seule : la gestion requiert la permission « Gestion des référentiels BCM ».</p>
      }
      <nav class="bea-cl-filters" style="gap:0.4rem">
        @for (o of onglets; track o[0]) {
          <button type="button" class="bea-mg__btn" [class.bea-mg__btn--primary]="onglet() === o[0]" [class.bea-mg__btn--ghost]="onglet() !== o[0]" (click)="ouvrir(o[0])">{{ o[1] }}</button>
        }
      </nav>

      @switch (onglet()) {
        @case ('versions') {
          @if (peutGerer()) {
            <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); importer(fichierRef)">
              <label style="flex:1 1 16rem">Fichier Excel (feuille « ref »)<input #fichierRef type="file" accept=".xlsx,.xlsm" /></label>
              <label style="flex:1 1 14rem">Libellé de la version<input [(ngModel)]="libelleVersion" name="libelle" maxlength="120" /></label>
              <label style="flex:1 1 18rem">Observations<input [(ngModel)]="observationsVersion" name="observations" maxlength="2000" /></label>
              <div style="display:flex;align-items:end">
                <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>upload_file</mat-icon> Importer une version</button>
              </div>
            </form>
          }
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Versions</h2></div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Version</th><th>Statut</th><th style="text-align:right">Codes</th><th style="text-align:right">PP / PM</th><th>Anomalies</th><th>Importée</th><th>Activée</th><th style="text-align:right">Déclarations</th><th style="text-align:right">Actions</th></tr></thead>
                <tbody>
                  @for (v of versions(); track v.id) {
                    <tr [class.is-off]="v.statut === 'ARCHIVEE'">
                      <td><strong>{{ v.libelle }}</strong><br /><span class="bea-cl-hint">{{ v.fichier_nom }} · {{ v.sha256.slice(0, 12) }}…</span>
                        @if (v.observations) { <br /><span class="bea-cl-hint">{{ v.observations }}</span> }</td>
                      <td><span class="bea-cl-badge" [attr.data-s]="badgeVersion[v.statut]">{{ v.statut }}</span></td>
                      <td style="text-align:right">{{ v.nb_codes }}</td>
                      <td style="text-align:right">{{ v.nb_pp }} / {{ v.nb_pm }}</td>
                      <td>
                        @if (v.anomalies.length) {
                          <button type="button" class="bea-cl-chip" [class.bea-cl-chip--n]="v.doublons > 0" (click)="versionAnomalies.set(versionAnomalies() === v.id ? null : v.id)">{{ v.anomalies.length }} anomalie(s){{ v.doublons ? ' dont ' + v.doublons + ' doublon(s)' : '' }}</button>
                        } @else { — }
                      </td>
                      <td>{{ dateHeureFr(v.importe_le) }}<br /><span class="bea-cl-hint">{{ v.importe_par ?? '—' }}</span></td>
                      <td>{{ dateHeureFr(v.activee_le) }}</td>
                      <td style="text-align:right">{{ v.nb_declarations }}</td>
                      <td>
                        <div class="bea-cl-row-actions">
                          <button type="button" (click)="voirCodes(v)" title="Voir les codes" aria-label="Voir les codes"><mat-icon>list</mat-icon></button>
                          <button type="button" (click)="choisirComparaison(v)" [title]="comparerA() ? 'Comparer avec la version choisie' : 'Choisir pour comparer'" aria-label="Comparer"><mat-icon>{{ comparerA() === v.id ? 'radio_button_checked' : 'compare' }}</mat-icon></button>
                          @if (peutGerer() && v.statut === 'BROUILLON') {
                            <button type="button" (click)="activer(v)" [disabled]="busy() || v.doublons > 0" title="Activer" aria-label="Activer"><mat-icon>task_alt</mat-icon></button>
                            @if (!v.nb_declarations) {
                              <button type="button" class="is-danger" (click)="supprimerVersion(v)" [disabled]="busy()" title="Supprimer le brouillon" aria-label="Supprimer"><mat-icon>delete</mat-icon></button>
                            }
                          }
                        </div>
                      </td>
                    </tr>
                    @if (versionAnomalies() === v.id) {
                      <tr><td colspan="9">
                        <ul class="bea-cl-anoms">
                          @for (a of v.anomalies; track $index) {
                            <li [attr.data-n]="a.motif.includes('dupliqué') ? 'bloquant' : 'alerte'">Ligne {{ a.ligne }}{{ a.code ? ' · code ' + a.code : '' }} : {{ a.motif }}</li>
                          }
                        </ul>
                      </td></tr>
                    }
                  } @empty {
                    <tr><td colspan="9"><div class="bea-cl-empty">Aucune version importée : la génération SIC est bloquée tant qu’aucune version n’est active.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
            <p class="bea-cl-hint" style="padding:0.6rem 1.1rem 0.9rem">Une version importée n’est jamais modifiée. L’activation archive la version précédente ; une version utilisée par une déclaration reste consultable et n’est jamais supprimée. Un fichier comportant des codes dupliqués ne peut pas être activé.</p>
          </section>
          @if (comparaison(); as c) {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Comparaison « {{ c.a.libelle }} » → « {{ c.b.libelle }} »</h2>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="comparaison.set(null)"><mat-icon>close</mat-icon></button></div>
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead><tr><th>Écart</th><th>Code</th><th>Détail</th></tr></thead>
                  <tbody>
                    @for (x of c.ajoutes; track x.code) { <tr><td>Ajouté</td><td>{{ x.code }}</td><td>{{ x.libelle }} · {{ x.categorie }} ({{ x.usage }})</td></tr> }
                    @for (x of c.retires; track x.code) { <tr><td>Retiré</td><td>{{ x.code }}</td><td>{{ x.libelle }} · {{ x.categorie }} ({{ x.usage }})</td></tr> }
                    @for (x of c.modifies; track x.code) { <tr><td>Modifié</td><td>{{ x.code }}</td><td>{{ ecarts(x.ecarts) }}</td></tr> }
                    @if (!c.ajoutes.length && !c.retires.length && !c.modifies.length) { <tr><td colspan="3"><div class="bea-cl-empty">Versions identiques.</div></td></tr> }
                  </tbody>
                </table>
              </div>
            </section>
          }
        }

        @case ('codes') {
          <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); pageCodes.set(1); chargerCodes()">
            <label>Version
              <select [(ngModel)]="versionCodes" name="version">
                <option value="">Version active</option>
                @for (v of versions(); track v.id) { <option [value]="v.id">{{ v.libelle }} ({{ v.statut }})</option> }
              </select>
            </label>
            <label>Usage
              <select [(ngModel)]="usageCodes" name="usage">
                <option value="">PP et PM</option><option value="PP">PP — catégories socioprofessionnelles</option><option value="PM">PM — secteurs d’activité</option>
              </select>
            </label>
            <label style="flex:1 1 16rem">Recherche<input [(ngModel)]="qCodes" name="q" placeholder="Code, libellé, catégorie" /></label>
            <div style="display:flex;align-items:end"><button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Rechercher</button></div>
          </form>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>{{ codes()?.version?.libelle ?? 'Aucune version active' }}</h2><span class="bea-cl-hint">{{ codes()?.total ?? 0 }} code(s)</span></div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Ligne</th><th>Code</th><th>Libellé</th><th>Catégorie</th><th>Usage</th></tr></thead>
                <tbody>
                  @for (c of codes()?.items ?? []; track c.ligne) {
                    <tr><td>{{ c.ligne }}</td><td><strong>{{ c.code }}</strong></td><td>{{ c.libelle }}</td><td>{{ c.categorie ?? '—' }}</td><td>{{ c.usage }}</td></tr>
                  } @empty { <tr><td colspan="5"><div class="bea-cl-empty">Aucun code.</div></td></tr> }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('agences') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Agence → MoughataaAgence</h2><span class="bea-cl-hint">{{ agencesManquantes() }} agence(s) avec clients sans valeur</span></div>
            <p class="bea-cl-hint" style="padding:0 1.1rem">Valeur attendue par SIC pour la colonne « MoughataaAgence » (consigne du modèle : « Les agences »). Format exact à confirmer avec la BCM ; aucune valeur n’est déduite automatiquement.</p>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Code</th><th>Agence</th><th>Ville</th><th style="text-align:right">Clients</th><th>Valeur SIC</th><th>Observation</th><th>Mise à jour</th>@if (peutGerer()) { <th></th> }</tr></thead>
                <tbody>
                  @for (a of agences(); track a.agence_id) {
                    <tr>
                      <td>{{ a.code }}</td><td>{{ a.libelle }}</td><td>{{ a.ville ?? '—' }}</td>
                      <td style="text-align:right">{{ a.nb_clients }}</td>
                      @if (peutGerer() && edition() === a.agence_id) {
                        <td><input [(ngModel)]="editValeur" name="valeur_{{ a.agence_id }}" maxlength="120" /></td>
                        <td><input [(ngModel)]="editObservation" name="obs_{{ a.agence_id }}" maxlength="2000" /></td>
                        <td></td>
                        <td><div class="bea-cl-row-actions">
                          <button type="button" (click)="enregistrerAgence(a)" [disabled]="busy()" title="Enregistrer" aria-label="Enregistrer"><mat-icon>check</mat-icon></button>
                          <button type="button" (click)="edition.set(null)" title="Annuler" aria-label="Annuler"><mat-icon>close</mat-icon></button>
                        </div></td>
                      } @else {
                        <td>@if (a.valeur) { <strong>{{ a.valeur }}</strong> } @else { <span class="bea-cl-chip bea-cl-chip--n">Non paramétrée</span> }</td>
                        <td>{{ a.observation ?? '' }}</td>
                        <td>{{ dateHeureFr(a.maj_le) }}<br /><span class="bea-cl-hint">{{ a.maj_par ?? '' }}</span></td>
                        @if (peutGerer()) {
                          <td><div class="bea-cl-row-actions">
                            <button type="button" (click)="editerAgence(a)" title="Modifier" aria-label="Modifier"><mat-icon>edit</mat-icon></button>
                            @if (a.valeur) { <button type="button" class="is-danger" (click)="retirerAgence(a)" [disabled]="busy()" title="Retirer" aria-label="Retirer"><mat-icon>link_off</mat-icon></button> }
                          </div></td>
                        }
                      }
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('secteurs') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Secteur ORION → code secteur BCM (PM)</h2></div>
            <p class="bea-cl-hint" style="padding:0 1.1rem">Utilisée seulement si le KYC ne fournit pas de code. « SANS », « DIVERS », « INCONNU » et les secteurs vides ne sont jamais rattachés : le code doit être saisi client par client. Une correspondance « à valider » exporte le client avec une anomalie à corriger.</p>
            @if (!secteurs()?.version_active) {
              <p class="bea-cl-note bea-cl-note--warn"><mat-icon>warning</mat-icon>Aucune version active du référentiel : correspondances non modifiables.</p>
            }
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Libellé ORION</th><th style="text-align:right">Clients PM</th><th>Code BCM</th><th>Statut</th><th>Observation</th><th>Mise à jour</th>@if (peutGerer()) { <th></th> }</tr></thead>
                <tbody>
                  @for (s of secteurs()?.items ?? []; track s.cle) {
                    <tr [class.is-off]="s.generique">
                      <td>{{ s.libelle_orion }}@if (s.generique) { <br /><span class="bea-cl-hint">Générique : jamais rattaché</span> }</td>
                      <td style="text-align:right">{{ s.nb_clients_pm }}</td>
                      @if (peutGerer() && edition() === s.cle) {
                        <td><input [(ngModel)]="editValeur" name="code_{{ s.cle }}" maxlength="10" style="width:6rem" /></td>
                        <td><select [(ngModel)]="editStatut" name="statut_{{ s.cle }}"><option value="A_VALIDER">À valider</option><option value="CONFIRMEE">Confirmée</option></select></td>
                        <td><input [(ngModel)]="editObservation" name="sobs_{{ s.cle }}" maxlength="2000" /></td>
                        <td></td>
                        <td><div class="bea-cl-row-actions">
                          <button type="button" (click)="enregistrerSecteur(s)" [disabled]="busy()" title="Enregistrer" aria-label="Enregistrer"><mat-icon>check</mat-icon></button>
                          <button type="button" (click)="edition.set(null)" title="Annuler" aria-label="Annuler"><mat-icon>close</mat-icon></button>
                        </div></td>
                      } @else {
                        <td>{{ s.code_bcm ?? '—' }}@if (s.code_valide === false) { <span class="bea-cl-chip bea-cl-chip--n">Absent du référentiel actif</span> }</td>
                        <td>@if (s.statut) { <span class="bea-cl-badge" [attr.data-s]="s.statut === 'CONFIRMEE' ? 'VALIDEE' : 'A_CONTROLER'">{{ s.statut === 'CONFIRMEE' ? 'Confirmée' : 'À valider' }}</span> }</td>
                        <td>{{ s.observation ?? '' }}</td>
                        <td>{{ dateHeureFr(s.maj_le) }}<br /><span class="bea-cl-hint">{{ s.maj_par ?? '' }}</span></td>
                        @if (peutGerer()) {
                          <td><div class="bea-cl-row-actions">
                            @if (!s.generique && secteurs()?.version_active) {
                              <button type="button" (click)="editerSecteur(s)" title="Modifier" aria-label="Modifier"><mat-icon>edit</mat-icon></button>
                            }
                            @if (s.code_bcm) { <button type="button" class="is-danger" (click)="retirerSecteur(s)" [disabled]="busy()" title="Retirer" aria-label="Retirer"><mat-icon>link_off</mat-icon></button> }
                          </div></td>
                        }
                      }
                    </tr>
                  } @empty { <tr><td colspan="7"><div class="bea-cl-empty">Aucun secteur observé.</div></td></tr> }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('complements') {
          <p class="bea-cl-note bea-cl-note--info"><mat-icon>info</mat-icon>Genre, téléphone, catégorie socioprofessionnelle (PP) et code secteur (PM) n’existent pas dans ORION. Ordre de lecture : dossier EER validé, puis ces compléments KYC. Ils ne modifient ni la classification, ni les comptes, ni les données ORION.</p>
          @if (peutGerer()) {
            <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); analyserComplements(fichierComp)">
              <label style="flex:1 1 18rem">Fichier complément SIC (.xlsx)<input #fichierComp type="file" accept=".xlsx,.xlsm" /></label>
              <div style="display:flex;align-items:end;gap:0.45rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="modele()"><mat-icon>download</mat-icon> Modèle</button>
                <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>fact_check</mat-icon> Analyser</button>
              </div>
              @if (analyse(); as r) {
                <div style="flex-basis:100%">
                  <p><strong>{{ r.fichier }}</strong> : {{ r.lignes }} ligne(s), {{ r.retenues }} retenue(s), {{ r.nb_rejets }} rejet(s){{ r.applique ? ' — appliqué' : '' }}.</p>
                  @if (r.rejets.length) {
                    <ul class="bea-cl-anoms">
                      @for (x of r.rejets; track x.ligne) { <li data-n="alerte">Ligne {{ x.ligne }} · {{ x.racine || '—' }} : {{ x.motif }}</li> }
                    </ul>
                  }
                  @if (!r.applique && r.retenues) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="appliquerComplements()" [disabled]="busy()"><mat-icon>done_all</mat-icon> Appliquer les {{ r.retenues }} ligne(s) retenue(s)</button>
                  }
                </div>
              }
            </form>
            <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); saisirComplement()">
              <strong style="flex-basis:100%">Saisie unitaire</strong>
              <label>Racine<input [(ngModel)]="cRacine" name="c_racine" maxlength="6" required /></label>
              <label>Genre<select [(ngModel)]="cGenre" name="c_genre"><option value="">—</option><option value="H">H</option><option value="F">F</option></select></label>
              <label>Téléphone<input [(ngModel)]="cTel" name="c_tel" maxlength="40" /></label>
              <label>Code CSP (PP)<input [(ngModel)]="cCsp" name="c_csp" maxlength="10" style="width:6rem" /></label>
              <label>Code secteur (PM)<input [(ngModel)]="cSecteur" name="c_secteur" maxlength="10" style="width:6rem" /></label>
              <div style="display:flex;align-items:end"><button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !cRacine"><mat-icon>save</mat-icon> Enregistrer</button></div>
            </form>
          }
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Compléments enregistrés</h2>
              <form class="bea-cl-filters" style="padding:0" (submit)="$event.preventDefault(); pageComp.set(1); chargerComplements()">
                <input [(ngModel)]="qComp" name="q_comp" placeholder="Racine" maxlength="6" />
                <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon></button>
              </form>
            </div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Racine</th><th>Genre</th><th>Téléphone</th><th>CSP</th><th>Secteur</th><th>Source</th><th>Mise à jour</th></tr></thead>
                <tbody>
                  @for (c of complements()?.items ?? []; track c.racine) {
                    <tr><td>{{ c.racine }}</td><td>{{ c.genre ?? '—' }}</td><td>{{ c.telephone ?? '—' }}</td><td>{{ c.code_csp_bcm ?? '—' }}</td><td>{{ c.code_secteur_bcm ?? '—' }}</td><td>{{ c.sic_source ?? '—' }}</td><td>{{ dateHeureFr(c.sic_maj_le) }}</td></tr>
                  } @empty { <tr><td colspan="7"><div class="bea-cl-empty">Aucun complément.</div></td></tr> }
                </tbody>
              </table>
            </div>
            <div class="bea-cl-filters" style="justify-content:flex-end">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="pageComp() <= 1" (click)="pageComp.set(pageComp() - 1); chargerComplements()"><mat-icon>chevron_left</mat-icon></button>
              <span class="bea-cl-hint" style="align-self:center">Page {{ pageComp() }} · {{ complements()?.total ?? 0 }} client(s)</span>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="pageComp() * 50 >= (complements()?.total ?? 0)" (click)="pageComp.set(pageComp() + 1); chargerComplements()"><mat-icon>chevron_right</mat-icon></button>
            </div>
          </section>
        }
      }
    </div>
  `,
})
export class ClReferentielsBcmComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly onglets: [Onglet, string][] = [
    ['versions', 'Versions du référentiel'], ['codes', 'Codes officiels'], ['agences', 'Agences'],
    ['secteurs', 'Secteurs ORION'], ['complements', 'Compléments KYC SIC'],
  ];
  readonly onglet = signal<Onglet>('versions');
  readonly versions = signal<Version[]>([]);
  readonly codes = signal<Codes | null>(null);
  readonly comparaison = signal<Comparaison | null>(null);
  readonly comparerA = signal<string | null>(null);
  readonly versionAnomalies = signal<string | null>(null);
  readonly agences = signal<AgenceSic[]>([]);
  readonly secteurs = signal<{ items: SecteurSic[]; version_active: Version | null } | null>(null);
  readonly complements = signal<{ total: number; items: Complement[] } | null>(null);
  readonly analyse = signal<ImportComplements | null>(null);
  readonly edition = signal<string | null>(null);
  readonly pageCodes = signal(1);
  readonly pageComp = signal(1);
  readonly busy = signal(false);
  readonly peutGerer = computed(() => this.store.cap().bcm_referentiel);
  readonly agencesManquantes = computed(() => this.agences().filter((a) => !a.valeur && a.nb_clients > 0).length);
  readonly dateHeureFr = dateHeureFr;
  readonly badgeVersion = BADGE_VERSION;
  libelleVersion = '';
  observationsVersion = '';
  versionCodes = '';
  usageCodes = '';
  qCodes = '';
  qComp = '';
  editValeur = '';
  editObservation = '';
  editStatut = 'A_VALIDER';
  cRacine = '';
  cGenre = '';
  cTel = '';
  cCsp = '';
  cSecteur = '';
  private fichierComplements: File | null = null;

  ngOnInit(): void {
    this.store.charger();
    this.chargerVersions();
  }

  private erreur(titre: string) {
    return (e: unknown) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, titre));
  }

  ouvrir(o: Onglet): void {
    this.onglet.set(o);
    this.edition.set(null);
    if (o === 'versions') this.chargerVersions();
    if (o === 'codes') this.chargerCodes();
    if (o === 'agences') this.chargerAgences();
    if (o === 'secteurs') this.chargerSecteurs();
    if (o === 'complements') this.chargerComplements();
  }

  chargerVersions(): void {
    this.api.get<Version[]>(`${CL_BASE}/bcm/referentiel/versions`).subscribe({
      next: (v) => this.versions.set(v), error: this.erreur('Versions indisponibles'),
    });
  }

  importer(input: HTMLInputElement): void {
    const f = input.files?.[0];
    if (!f) {
      this.feedback.warning({ title: 'Fichier manquant', message: 'Choisissez le fichier Excel du référentiel BCM.' });
      return;
    }
    const fd = new FormData();
    fd.append('fichier', f);
    if (this.libelleVersion.trim()) fd.append('libelle', this.libelleVersion.trim());
    if (this.observationsVersion.trim()) fd.append('observations', this.observationsVersion.trim());
    this.feedback.run(() => this.api.post<Version>(`${CL_BASE}/bcm/referentiel/versions`, fd), {
      busy: this.busy,
      loading: 'Import du référentiel…',
      success: (v) => ({
        title: 'Version importée (brouillon)',
        message: v.anomalies.length ? `${v.anomalies.length} anomalie(s) à examiner avant activation.` : 'Aucune anomalie de structure.',
        details: [{ label: 'Codes', value: `${v.nb_codes} (PP ${v.nb_pp} / PM ${v.nb_pm})` }],
      }),
      errorTitle: 'Import refusé',
    }).subscribe(() => {
      input.value = '';
      this.libelleVersion = '';
      this.observationsVersion = '';
      this.chargerVersions();
    });
  }

  activer(v: Version): void {
    this.feedback.runWithReason((motif) => this.api.post<Version>(`${CL_BASE}/bcm/referentiel/versions/${v.id}/activer`, { motif }), {
      reason: {
        title: 'Activer la version du référentiel',
        message: `« ${v.libelle} » (${v.nb_codes} codes) deviendra la version utilisée par les prochaines déclarations SIC.`,
        hint: 'La version active actuelle sera archivée. Les déclarations existantes gardent leur version.',
        reasonLabel: 'Motif (référence de la publication BCM)',
      },
      busy: this.busy,
      loading: 'Activation…',
      success: { title: 'Version activée' },
      errorTitle: 'Activation refusée',
    }).subscribe(() => this.chargerVersions());
  }

  supprimerVersion(v: Version): void {
    this.feedback.run(() => this.api.delete<void>(`${CL_BASE}/bcm/referentiel/versions/${v.id}`), {
      confirm: { action: 'suppression', title: 'Supprimer le brouillon', message: `« ${v.libelle} » n’a jamais été activée ni utilisée.` },
      busy: this.busy,
      success: { title: 'Brouillon supprimé' },
      errorTitle: 'Suppression refusée',
    }).subscribe(() => this.chargerVersions());
  }

  voirCodes(v: Version): void {
    this.versionCodes = v.id;
    this.onglet.set('codes');
    this.chargerCodes();
  }

  chargerCodes(): void {
    const params: Record<string, string | number> = { page: this.pageCodes(), taille: 200 };
    if (this.versionCodes) params['version'] = this.versionCodes;
    if (this.usageCodes) params['usage'] = this.usageCodes;
    if (this.qCodes.trim()) params['q'] = this.qCodes.trim();
    this.api.get<Codes>(`${CL_BASE}/bcm/referentiel/codes`, params).subscribe({
      next: (c) => this.codes.set(c), error: this.erreur('Codes indisponibles'),
    });
  }

  choisirComparaison(v: Version): void {
    const a = this.comparerA();
    if (!a || a === v.id) {
      this.comparerA.set(a === v.id ? null : v.id);
      return;
    }
    this.comparerA.set(null);
    this.api.get<Comparaison>(`${CL_BASE}/bcm/referentiel/comparer`, { a, b: v.id }).subscribe({
      next: (c) => this.comparaison.set(c), error: this.erreur('Comparaison impossible'),
    });
  }

  ecarts(e: Record<string, { avant: string | null; apres: string | null }>): string {
    return Object.entries(e).map(([k, x]) => `${k} : ${x.avant ?? '—'} → ${x.apres ?? '—'}`).join(' · ');
  }

  chargerAgences(): void {
    this.api.get<AgenceSic[]>(`${CL_BASE}/bcm/referentiel/agences`).subscribe({
      next: (a) => this.agences.set(a), error: this.erreur('Agences indisponibles'),
    });
  }

  editerAgence(a: AgenceSic): void {
    this.editValeur = a.valeur ?? '';
    this.editObservation = a.observation ?? '';
    this.edition.set(a.agence_id);
  }

  enregistrerAgence(a: AgenceSic): void {
    const body = { valeur: this.editValeur, observation: this.editObservation || null };
    this.feedback.run(() => this.api.put<AgenceSic[]>(`${CL_BASE}/bcm/referentiel/agences/${a.agence_id}`, body), {
      busy: this.busy,
      success: { title: 'Correspondance enregistrée', message: `${a.code} → ${this.editValeur}` },
      errorTitle: 'Enregistrement refusé',
    }).subscribe((l) => {
      this.agences.set(l);
      this.edition.set(null);
    });
  }

  retirerAgence(a: AgenceSic): void {
    this.feedback.run(() => this.api.delete<AgenceSic[]>(`${CL_BASE}/bcm/referentiel/agences/${a.agence_id}`), {
      confirm: { action: 'suppression', title: 'Retirer la correspondance', message: `Les clients de l’agence ${a.code} seront bloqués dans les prochains fichiers SIC.` },
      busy: this.busy,
      success: { title: 'Correspondance retirée' },
      errorTitle: 'Retrait refusé',
    }).subscribe((l) => this.agences.set(l));
  }

  chargerSecteurs(): void {
    this.api.get<{ items: SecteurSic[]; version_active: Version | null }>(`${CL_BASE}/bcm/referentiel/secteurs`).subscribe({
      next: (s) => this.secteurs.set(s), error: this.erreur('Secteurs indisponibles'),
    });
  }

  editerSecteur(s: SecteurSic): void {
    this.editValeur = s.code_bcm ?? '';
    this.editObservation = s.observation ?? '';
    this.editStatut = s.statut ?? 'A_VALIDER';
    this.edition.set(s.cle);
  }

  enregistrerSecteur(s: SecteurSic): void {
    const body = { libelle_orion: s.libelle_orion, code_bcm: this.editValeur, statut: this.editStatut, observation: this.editObservation || null };
    this.feedback.run(() => this.api.put<{ items: SecteurSic[]; version_active: Version | null }>(`${CL_BASE}/bcm/referentiel/secteurs`, body), {
      busy: this.busy,
      success: { title: 'Correspondance enregistrée', message: `${s.libelle_orion} → ${this.editValeur}` },
      errorTitle: 'Enregistrement refusé',
    }).subscribe((r) => {
      this.secteurs.set(r);
      this.edition.set(null);
    });
  }

  retirerSecteur(s: SecteurSic): void {
    this.feedback.run(() => this.api.delete<{ items: SecteurSic[]; version_active: Version | null }>(
      `${CL_BASE}/bcm/referentiel/secteurs?libelle=${encodeURIComponent(s.cle)}`), {
      confirm: { action: 'suppression', title: 'Retirer la correspondance', message: `${s.libelle_orion} ne sera plus rattaché à un code BCM.` },
      busy: this.busy,
      success: { title: 'Correspondance retirée' },
      errorTitle: 'Retrait refusé',
    }).subscribe((r) => this.secteurs.set(r));
  }

  chargerComplements(): void {
    const params: Record<string, string | number> = { page: this.pageComp(), taille: 50 };
    if (this.qComp.trim()) params['racine'] = this.qComp.trim();
    this.api.get<{ total: number; items: Complement[] }>(`${CL_BASE}/bcm/referentiel/complements`, params).subscribe({
      next: (c) => this.complements.set(c), error: this.erreur('Compléments indisponibles'),
    });
  }

  modele(): void {
    this.api.download(`${CL_BASE}/bcm/referentiel/complements/modele.xlsx`).subscribe({
      next: (b) => telecharger(b, 'modele-complements-sic.xlsx'), error: this.erreur('Modèle indisponible'),
    });
  }

  private envoyerComplements(appliquer: boolean) {
    const fd = new FormData();
    fd.append('fichier', this.fichierComplements!);
    return this.api.post<ImportComplements>(`${CL_BASE}/bcm/referentiel/complements/import?appliquer=${appliquer}`, fd);
  }

  analyserComplements(input: HTMLInputElement): void {
    const f = input.files?.[0];
    if (!f) {
      this.feedback.warning({ title: 'Fichier manquant', message: 'Choisissez le fichier complément SIC.' });
      return;
    }
    this.fichierComplements = f;
    this.feedback.run(() => this.envoyerComplements(false), {
      busy: this.busy,
      loading: 'Analyse du fichier…',
      success: (r) => ({ title: 'Analyse terminée', message: `${r.retenues} ligne(s) retenue(s), ${r.nb_rejets} rejet(s). Rien n’est encore enregistré.` }),
      errorTitle: 'Analyse impossible',
    }).subscribe((r) => this.analyse.set(r));
  }

  appliquerComplements(): void {
    const r = this.analyse();
    if (!r || !this.fichierComplements) return;
    this.feedback.run(() => this.envoyerComplements(true), {
      confirm: { action: 'enregistrement', title: 'Appliquer les compléments', message: `${r.retenues} client(s) seront complétés. Les cellules vides ne remplacent aucune valeur existante.` },
      busy: this.busy,
      loading: 'Enregistrement des compléments…',
      success: (x) => ({ title: 'Compléments enregistrés', message: `${x.retenues} client(s) complété(s).` }),
      errorTitle: 'Enregistrement refusé',
    }).subscribe((x) => {
      this.analyse.set(x);
      this.chargerComplements();
    });
  }

  saisirComplement(): void {
    const racine = this.cRacine.trim();
    const valeurs = { genre: this.cGenre || null, telephone: this.cTel || null, code_csp_bcm: this.cCsp || null, code_secteur_bcm: this.cSecteur || null };
    this.feedback.runWithReason((motif) => this.api.put<Complement>(`${CL_BASE}/bcm/referentiel/complements/${racine}`, { ...valeurs, motif }), {
      reason: {
        title: 'Complément SIC',
        message: `Client ${racine} : données utilisées par les prochaines déclarations SIC (sans modifier ORION ni la classification).`,
        reasonLabel: 'Motif / pièce justificative',
      },
      busy: this.busy,
      success: { title: 'Complément enregistré' },
      errorTitle: 'Enregistrement refusé',
    }).subscribe(() => {
      this.cRacine = this.cGenre = this.cTel = this.cCsp = this.cSecteur = '';
      this.chargerComplements();
    });
  }
}
