import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import {
  Dossier,
  Evenement,
  OperationSaisie,
  TotalDevise,
  dateFr,
  totauxParDevise,
  depuisSaisieLocale,
  maintenantLocal,
  montantFr,
  toneStatut,
  tonePriorite,
  versSaisieLocale,
} from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcPiecesComponent } from '../shared/rc-pieces.component';
import { RcActionsComponent } from '../shared/rc-actions.component';
import { CLASSEMENT_VIDE, Classement, RcClassementComponent, classementCorps, classementDe, classementErreur } from '../shared/rc-classement.component';
import { RcImportComponent } from '../shared/rc-import.component';
import { RcOperationsComponent, clientsSaisis, operationsCorps, operationsErreur, versSaisie } from '../shared/rc-operations.component';
import { RcOperationsVueComponent } from '../shared/rc-operations-vue.component';
import { optionsRestauration, optionsSuppression } from '../shared/rc-suppression';

type Onglet = 'general' | 'traitement' | 'documents' | 'chronologie';

const ONGLETS: ReadonlyArray<{ code: Onglet; libelle: string; icone: string }> = [
  { code: 'general', libelle: 'Général', icone: 'info' },
  { code: 'traitement', libelle: 'Traitement & clôture', icone: 'engineering' },
  { code: 'documents', libelle: 'Notes & pièces jointes', icone: 'attach_file' },
  { code: 'chronologie', libelle: 'Historique', icone: 'timeline' },
];

const ETAPES: ReadonlyArray<{ code: string; libelle: string; icone: string }> = [
  { code: 'RECEPTION', libelle: 'Réception', icone: 'move_to_inbox' },
  { code: 'AFFECTATION', libelle: 'Affectation', icone: 'send' },
  { code: 'TRAITEMENT', libelle: 'Traitement', icone: 'engineering' },
  { code: 'CLOTURE', libelle: 'Clôture', icone: 'task_alt' },
];

const ICONES_EVENEMENT: Record<string, string> = {
  CREATION: 'add_circle', RECEPTION_SR: 'move_to_inbox', MODIFICATION: 'edit', APPEL: 'call', OPERATIONS: 'receipt_long',
  IMPORT_ANALYSE: 'fact_check', IMPORT_CONFIRME: 'upload_file', IMPORT_ABANDONNE: 'cancel',
  DOCUMENT_AJOUT: 'attach_file', DOCUMENT_RETRAIT: 'delete', QUALIFICATION: 'rule',
  AFFECTATION: 'send', PRISE_EN_CHARGE: 'play_arrow', RETOUR_SERVICE: 'assignment_return',
  EVALUATION: 'fact_check', RENVOI: 'replay', TRAITEMENT_INTERNE: 'home_repair_service',
  DEMANDE_INFO: 'help', REPRISE: 'replay', SUSPENSION: 'pause', REFUS: 'block',
  ANNULATION: 'content_copy', REPONSE_BROUILLON: 'edit_note', REPONSE_SOUMISE: 'forward_to_inbox',
  REPONSE_VALIDEE: 'verified', REPONSE_RENVOYEE: 'undo', REPONSE_ENVOYEE: 'outgoing_mail',
  CLOTURE: 'task_alt', REOUVERTURE: 'lock_open', ARCHIVAGE: 'inventory_2', MIGRATION_CIRCUIT: 'sync_alt',
  SUPPRESSION: 'delete', RESTAURATION: 'restore_from_trash',
  REGULARISATION_A_EFFECTUER: 'pending_actions', REGULARISATION_CONFIRMEE: 'verified',
};

/** Champs facultatifs vidés à la correction : envoyés dans `effacer` (le PATCH ignore les valeurs nulles). */
const EFFACABLES = [
  'client_racine', 'client_categorie', 'client_telephone', 'client_email', 'client_adresse', 'client_agence_id',
  'agence_reception_id', 'org_departement_id', 'org_service_id',
] as const;
const NIVEAUX_CLASSEMENT = ['type_id', 'motif_id', 'motif_autre', 'sous_motif_id', 'sous_motif_autre'] as const;

/** Fiche dossier. Le statut n'évolue que par les actions du circuit ; la correction de données est motivée et tracée. */
@Component({
  selector: 'bea-rc-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, FormsModule, RouterLink, MatIconModule, ReclamationsUiComponent, RcPiecesComponent, RcActionsComponent, RcClassementComponent, RcOperationsComponent,
    RcOperationsVueComponent, RcImportComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      @if (dossier(); as d) {
        <header class="bea-mg__head bea-rc-fiche__head">
          <div>
            <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
            <h1>{{ d.reference }}</h1>
            <p class="bea-ct-head__sub">{{ d.objet }}{{ d.client_nom ? ' — ' + d.client_nom : '' }}</p>
            <div class="bea-rc-fiche__badges">
              <span class="bea-ct-badge" [attr.data-tone]="toneStatut(d.statut)">{{ d.statut_libelle }}</span>
              <span class="bea-ct-badge" [attr.data-tone]="tonePriorite(d.priorite)">{{ d.priorite_libelle }}</span>
              @if (d.nb_operations) { <span class="bea-ct-badge" data-tone="INFO">{{ d.nb_operations }} opération{{ d.nb_operations > 1 ? 's' : '' }} · {{ parDevise(d) }}</span> }
              @if (d.regularisation; as rg) {
                <span class="bea-ct-badge" [attr.data-tone]="rg.statut === 'A_EFFECTUER' ? 'ATTENTION' : 'ACTIF'">{{ rg.statut_libelle }}</span>
              }
              @if (d.archivee_le) { <span class="bea-ct-badge" data-tone="ANNULEE">Archivée</span> }
              @if (d.supprimee_le) { <span class="bea-ct-badge" data-tone="URGENT">Supprimée</span> }
            </div>
          </div>
          <div class="bea-mg__actions">
            <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="'/reclamations/dossiers'" [queryParams]="d.supprimee_le ? { corbeille: 'true' } : {}"><mat-icon>arrow_back</mat-icon> Réclamations</a>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="chargement()" (click)="recharger()"><mat-icon>refresh</mat-icon> Actualiser</button>
            @if (d.actions['modifier'] && !edition()) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirEdition()"><mat-icon>edit</mat-icon> Corriger les données</button>
            }
            @if (d.actions['restaurer']) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="restaurer()"><mat-icon>restore_from_trash</mat-icon> Restaurer</button>
            }
            @if (d.actions['supprimer']) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-rc-danger" [disabled]="busy() || edition()" (click)="supprimer()"><mat-icon>delete_forever</mat-icon> Supprimer</button>
            }
          </div>
        </header>

        @if (d.supprimee_le) {
          <div class="bea-rc-note bea-rc-note--warn bea-rc-fiche__alerte"><mat-icon>delete</mat-icon>
            <span>
              <strong>Dossier supprimé</strong> le {{ date(d.suppression.supprimee_le, true) }}{{ d.suppression.supprimee_par ? ' par ' + d.suppression.supprimee_par : '' }}
              — motif : {{ d.suppression.motif }}. Il n’apparaît plus dans les listes, indicateurs ni exports : restaurez-le ou supprimez-le définitivement.
            </span>
          </div>
        }

        <ol class="bea-rc-pipe" aria-label="Avancement du dossier">
          @for (e of etapes; track e.code; let i = $index) {
            <li [class.is-done]="i < etapeIndex() || (i === etapeIndex() && d.statut === 'CLOTUREE')"
                [class.is-on]="i === etapeIndex() && d.statut !== 'CLOTUREE'"
                [class.is-stop]="interrompu() && i > etapeIndex()"
                [attr.aria-current]="i === etapeIndex() ? 'step' : null">
              <mat-icon>{{ i < etapeIndex() || d.statut === 'CLOTUREE' ? 'check_circle' : e.icone }}</mat-icon> {{ e.libelle }}
            </li>
          }
        </ol>

        @if (!edition()) { <bea-rc-actions [dossier]="d" (modifie)="applique($event)" /> }

        <nav class="bea-ct-tabs" aria-label="Sections du dossier">
          @for (o of onglets; track o.code) {
            <button type="button" [class.is-on]="onglet() === o.code" (click)="choisir(o.code)">
              <mat-icon>{{ o.icone }}</mat-icon> {{ o.libelle }}
              @if (o.code === 'documents') { <small>{{ nbDocuments() }}</small> }
            </button>
          }
        </nav>

        @switch (onglet()) {
          @case ('general') {
            @if (edition()) {
              <form [formGroup]="form" (ngSubmit)="enregistrer()">
                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top"><h2>Correction des données</h2></div>
                  <div class="bea-rc-form">
                    <div class="bea-rc-note"><mat-icon>info</mat-icon>
                      <span>Chaque correction est tracée (valeurs avant / après, auteur, date). La correction d’une date de réception exige un motif.</span>
                    </div>
                    <div class="bea-rc-row">
                      <label>Date de la réclamation <em>*</em><input type="date" formControlName="date_reclamation" [max]="aujourdhui" [class.is-invalid]="invalide('date_reclamation')" /></label>
                      <label>Réception par la banque <em>*</em><input type="datetime-local" formControlName="date_premiere_reception" [max]="maintenant" /></label>
                      @if (d.date_reception_sr) {
                        <label>Réception par le Service Réclamations<input type="datetime-local" formControlName="date_reception_sr" [max]="maintenant" /></label>
                      }
                    </div>
                    <div class="bea-rc-row">
                      <label>Agence de réception
                        <select formControlName="agence_reception_id">
                          <option value="">—</option>
                          @for (a of store.config()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
                        </select>
                      </label>
                      <label>Réception
                        <select formControlName="niveau_concerne">
                          <option value="SERVICE">Service</option>
                          <option value="DEPARTEMENT">Département</option>
                        </select>
                      </label>
                      @if (form.controls.niveau_concerne.value === 'DEPARTEMENT') {
                        <label>Département concerné
                          <select formControlName="org_departement_id">
                            <option value="">— À déterminer —</option>
                            @for (x of store.departements(); track x.id) { <option [value]="x.id" [title]="x.chemin ?? ''">{{ x.libelle }}{{ x.sigle ? ' (' + x.sigle + ')' : '' }}</option> }
                          </select>
                        </label>
                      } @else {
                        <label>Service concerné
                          <select formControlName="org_service_id">
                            <option value="">— À déterminer —</option>
                            @for (x of store.services(); track x.id) { <option [value]="x.id" [title]="x.chemin ?? ''">{{ x.libelle }}{{ x.sigle ? ' (' + x.sigle + ')' : '' }}</option> }
                          </select>
                        </label>
                      }
                      <label>Priorité
                        <select formControlName="priorite">
                          @for (p of store.libelles('priorites'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
                        </select>
                      </label>
                    </div>
                    <bea-rc-classement [(valeur)]="classement" [tente]="tente()" />
                    <label>Objet <em>*</em><input formControlName="objet" maxlength="255" [class.is-invalid]="invalide('objet')" /></label>
                    <label>Description <em>*</em><textarea formControlName="description" rows="5" maxlength="20000" [class.is-invalid]="invalide('description')"></textarea></label>
                    <div class="bea-rc-row">
                      <label>Racine client <input formControlName="client_racine" maxlength="6" inputmode="numeric" [class.is-invalid]="invalide('client_racine')" /></label>
                      <label>Catégorie
                        <select formControlName="client_categorie">
                          <option value="">—</option>
                          @for (c of store.libelles('categories_client'); track c.code) { <option [value]="c.code">{{ c.libelle }}</option> }
                        </select>
                      </label>
                      <label>Nom / raison sociale <em>*</em><input formControlName="client_nom" maxlength="255" [class.is-invalid]="invalide('client_nom')" /></label>
                    </div>
                    <div class="bea-rc-row">
                      <label>Téléphone <input formControlName="client_telephone" maxlength="40" /></label>
                      <label>E-mail <input type="email" formControlName="client_email" maxlength="255" /></label>
                    </div>
                    <label>Adresse <textarea formControlName="client_adresse" rows="2" maxlength="2000"></textarea></label>
                    <label>Motif de la correction @if (dateModifiee()) { <em>*</em> }
                      <textarea formControlName="motif" rows="2" maxlength="4000" [class.is-invalid]="dateModifiee() && tente() && !form.controls.motif.value.trim()"
                                placeholder="Obligatoire si une date de réception est corrigée"></textarea>
                    </label>
                  </div>
                </section>
                <div class="bea-rc-savebar">
                  <span>Révision {{ d.revision }} — si un autre utilisateur modifie le dossier entre-temps, l’enregistrement sera refusé.</span>
                  <span class="bea-mg__actions">
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="annulerEdition()">Annuler</button>
                    <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer</button>
                  </span>
                </div>
              </form>
            } @else {
              <div class="bea-rc-grid">
                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top"><h2>Réclamation</h2></div>
                  <dl class="bea-rc-dl">
                    <dt>Objet</dt><dd>{{ d.objet }}</dd>
                    <dt>Type</dt><dd>{{ d.type_ref?.libelle ?? 'À qualifier' }}</dd>
                    <dt>Motif</dt><dd>{{ d.motif ?? '—' }}</dd>
                    <dt>Sous-motif</dt><dd>{{ d.sous_motif ?? '—' }}</dd>
                    @if (d.service_ref) {
                      <dt>Service concerné</dt><dd [title]="d.service_ref.chemin ?? ''">{{ d.service_ref.libelle }}</dd>
                    } @else {
                      <dt>Département concerné</dt><dd [title]="d.departement_ref?.chemin ?? ''">{{ d.departement_ref?.libelle ?? 'À déterminer' }}</dd>
                    }
                    @if (d.reclamation_liee) {
                      <dt>Réclamation liée</dt><dd><a [routerLink]="['/reclamations/dossiers', d.reclamation_liee.id]">{{ d.reclamation_liee.reference }}</a></dd>
                    }
                    @if (d.doublon_de) {
                      <dt>Doublon de</dt><dd><a [routerLink]="['/reclamations/dossiers', d.doublon_de.id]">{{ d.doublon_de.reference }}</a></dd>
                    }
                  </dl>
                </section>
                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top"><h2>Réception</h2></div>
                  <dl class="bea-rc-dl">
                    <dt>Date de la réclamation</dt><dd>{{ date(d.date_reclamation) }}</dd>
                    <dt>Reçue par la banque</dt><dd>{{ date(d.date_premiere_reception, true) }}</dd>
                    <dt>Reçue par le SR</dt><dd>{{ d.date_reception_sr ? date(d.date_reception_sr, true) : '—' }}</dd>
                    <dt>Canal</dt><dd>{{ d.canal_ref?.libelle ?? '—' }}</dd>
                    <dt>Agence de réception</dt><dd>{{ d.agence_reception_ref ? d.agence_reception_ref.code + ' — ' + d.agence_reception_ref.libelle : '—' }}</dd>
                  </dl>
                </section>
                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top"><h2>Client</h2></div>
                  <dl class="bea-rc-dl">
                    <dt>Nom</dt><dd>{{ d.client.nom ?? '—' }}</dd>
                    <dt>Racine ORION</dt><dd>{{ d.client.racine ?? 'Non-client / non renseignée' }}</dd>
                    <dt>Catégorie</dt><dd>{{ d.client.categorie_libelle ?? '—' }}</dd>
                    @if (d.client.agence) { <dt>Agence</dt><dd>{{ d.client.agence.code }} — {{ d.client.agence.libelle }}</dd> }
                    <dt>Téléphone</dt><dd>{{ d.client.telephone ?? '—' }}</dd>
                    <dt>E-mail</dt><dd>{{ d.client.email ?? '—' }}</dd>
                    <dt>Adresse</dt><dd>{{ d.client.adresse ?? '—' }}</dd>
                    @if (d.compte_reference) { <dt>Compte</dt><dd>{{ d.compte_reference }}</dd> }
                    @if (d.carte_masquee) { <dt>Carte</dt><dd>{{ d.carte_masquee }}</dd> }
                  </dl>
                </section>
              </div>
              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top"><h2>Description</h2></div>
                <p class="bea-rc-text">{{ d.description }}</p>
              </section>

              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top">
                  <h2>Opérations concernées</h2>
                  @if (d.actions['modifier_operations'] && !editionOps()) {
                    <span class="bea-mg__actions">
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [class.is-on]="importOuvert()" (click)="importOuvert.set(!importOuvert())"><mat-icon>upload_file</mat-icon> Importer (Excel)</button>
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirOperations()"><mat-icon>edit</mat-icon> Modifier les opérations</button>
                    </span>
                  }
                </div>
                @if (d.a_completer_avant_transmission.length && d.etape === 'RECEPTION' && !d.termine) {
                  <div class="bea-rc-note bea-rc-note--warn"><mat-icon>rule</mat-icon>
                    <span><strong>À compléter avant transmission au service :</strong> {{ d.a_completer_avant_transmission.join(' ; ') }}</span>
                  </div>
                }
                @if (d.actions['modifier_operations'] && !editionOps() && (importOuvert() || importEnAttente())) {
                  <bea-rc-import [dossier]="d" (modifie)="apresImport($event)" />
                }
                @if (editionOps()) {
                  <div class="bea-rc-form">
                    <bea-rc-operations [(lignes)]="operations" [tente]="tenteOps()" [principal]="d.client.racine"
                                       [regle]="d.regle" [devises]="store.devises()" [reclamationId]="d.id" [motifId]="d.motif_ref?.id ?? null" />
                    @if (regroupementOps()) {
                      <label>Justification du regroupement multi-clients
                        <textarea [(ngModel)]="justificationOps" name="justification_ops" rows="2" maxlength="4000"
                                  [placeholder]="d.justification_regroupement ?? 'Obligatoire si les opérations concernent plusieurs clients'"></textarea>
                      </label>
                    }
                    <label>Motif de la modification
                      <textarea [(ngModel)]="motifOps" name="motif_ops" rows="2" maxlength="4000" placeholder="Facultatif — conservé dans l’historique"></textarea>
                    </label>
                    <span class="bea-mg__actions">
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="editionOps.set(false)">Annuler</button>
                      <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="enregistrerOperations()"><mat-icon>save</mat-icon> Enregistrer les opérations</button>
                    </span>
                  </div>
                } @else if (d.operations.length) {
                  <bea-rc-operations-vue [dossier]="d" />
                } @else {
                  <p class="bea-rc-pad bea-rc-muted">Aucune opération rattachée.</p>
                }
              </section>

              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top">
                  <h2>Appels téléphoniques</h2>
                  @if (d.actions['ajouter_appel']) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirAppel()"><mat-icon>add_call</mat-icon> Ajouter un appel</button>
                  }
                </div>
                @if (d.appels.length) {
                  <div class="bea-mg__table-wrap">
                    <table class="bea-mg__table">
                      <thead><tr><th>Date</th><th>Numéro</th><th>Agent</th><th>Identité</th><th>Référence</th><th>Rappel</th><th>Notes</th></tr></thead>
                      <tbody>
                        @for (a of d.appels; track a.id) {
                          <tr>
                            <td>{{ date(a.appel_le, true) }}</td>
                            <td>{{ a.numero_appelant ?? '—' }}</td>
                            <td>{{ a.agent ?? '—' }}</td>
                            <td>{{ a.identite_verifiee ? 'Vérifiée' + (a.mode_verification ? ' (' + a.mode_verification + ')' : '') : 'Non vérifiée' }}</td>
                            <td>{{ a.reference_appel ?? '—' }}{{ a.reference_enregistrement ? ' · enr. ' + a.reference_enregistrement : '' }}</td>
                            <td>{{ a.rappel_statut_libelle }}{{ a.rappel_prevu_le ? ' — ' + date(a.rappel_prevu_le, true) : '' }}</td>
                            <td>{{ a.commentaire ?? '' }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                } @else {
                  <p class="bea-rc-pad bea-rc-muted">Aucun appel enregistré.</p>
                }
              </section>
              <p class="bea-rc-hint">Créée le {{ date(d.created_at, true) }}{{ d.cree_par ? ' par ' + d.cree_par : '' }}{{ d.modifie_par ? ' · dernière modification par ' + d.modifie_par : '' }} · révision {{ d.revision }}</p>
            }
          }

          @case ('traitement') {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Pilotage</h2></div>
              <dl class="bea-rc-dl">
                <dt>Gestionnaire SR</dt><dd>{{ d.gestionnaire ?? 'Non désigné' }}</dd>
                <dt>Service de traitement</dt><dd>{{ d.unite_traitement_ref?.libelle ?? 'Non affectée' }}</dd>
                <dt>Responsable du traitement</dt><dd>{{ d.responsable_traitement ?? '—' }}</dd>
                <dt>Renvois au service</dt><dd>{{ d.nb_renvois }}</dd>
                @if (d.nb_reouvertures) { <dt>Réouvertures</dt><dd>{{ d.nb_reouvertures }}</dd> }
              </dl>
            </section>
            @for (a of d.affectations; track a.id) {
              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top"><h2>Fiche {{ a.numero }} — {{ a.unite }}</h2>
                  <span class="bea-ct-badge" data-tone="INFO">{{ a.statut_libelle }}</span>
                </div>
                <dl class="bea-rc-dl">
                  <dt>Transmise</dt><dd>{{ date(a.transmis_le, true) }}{{ a.transmis_par ? ' par ' + a.transmis_par : '' }}</dd>
                  <dt>Instructions</dt><dd>{{ a.instructions ?? '—' }}</dd>
                  <dt>Analyse</dt><dd>{{ a.analyse ?? '—' }}</dd>
                  <dt>Actions menées</dt><dd>{{ a.actions_menees ?? '—' }}</dd>
                  <dt>Conclusion</dt><dd>{{ a.conclusion ?? '—' }}</dd>
                  <dt>Décision proposée</dt><dd>{{ a.decision_proposee_libelle ?? '—' }}</dd>
                  <dt>Retour</dt><dd>{{ date(a.retour_le, true) }}{{ a.retour_par ? ' par ' + a.retour_par : '' }}</dd>
                  <dt>Évaluation SR</dt><dd>{{ a.evaluation_libelle ?? '—' }} {{ a.evaluation_commentaire ?? '' }}</dd>
                </dl>
              </section>
            } @empty {
              <p class="bea-rc-pad bea-rc-muted">Aucune transmission à un service pour l’instant.</p>
            }
            @if (d.reponse_courante; as p) {
              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top"><h2>Réponse envoyée au client</h2>
                  <span class="bea-ct-badge" data-tone="INFO">{{ p.statut_libelle }}</span>
                </div>
                <dl class="bea-rc-dl">
                  <dt>Envoyée le</dt><dd>{{ date(p.envoye_le, true) }}{{ p.envoye_par ? ' par ' + p.envoye_par : '' }}</dd>
                  <dt>Canal</dt><dd>{{ p.canal_envoi ?? '—' }}</dd>
                  <dt>Destinataire</dt><dd>{{ p.destinataire ?? '—' }}</dd>
                  <dt>Référence d’envoi</dt><dd>{{ p.reference_envoi ?? '—' }}</dd>
                  <dt>Objet</dt><dd>{{ p.objet ?? '—' }}</dd>
                  <dt>Résultat</dt><dd>{{ p.resultat_libelle ?? '—' }}</dd>
                  <dt>Preuve d’envoi</dt><dd>{{ d.preuve_envoi ? 'Jointe (onglet Notes & pièces jointes)' : 'Non jointe' }}</dd>
                </dl>
                <p class="bea-rc-text">{{ p.contenu }}</p>
              </section>
            }
            @if (d.regularisation; as rg) {
              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top"><h2>Régularisation</h2>
                  <span class="bea-ct-badge" [attr.data-tone]="rg.statut === 'A_EFFECTUER' ? 'ATTENTION' : 'ACTIF'">{{ rg.statut_libelle }}</span>
                </div>
                @if (rg.statut === 'A_EFFECTUER') {
                  <div class="bea-rc-note bea-rc-note--warn"><mat-icon>info</mat-icon>
                    <span>Décision favorable : la régularisation (extourne, correction) s’exécute dans ORION, hors BEA DIGITAL.
                      Une fois passée, confirmez-la ici avec sa preuve (catégorie « Preuve de régularisation » dans l’onglet Notes & pièces jointes).
                      Le dossier ne peut pas être archivé avant cette confirmation.</span>
                  </div>
                  @if (d.actions['confirmer_regularisation']) {
                    <span class="bea-mg__actions bea-rc-pad">
                      <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirRegularisation()"><mat-icon>verified</mat-icon> Confirmer la régularisation</button>
                    </span>
                  }
                } @else {
                  <dl class="bea-rc-dl">
                    <dt>Effectuée le</dt><dd>{{ date(rg.effectuee_le) }}</dd>
                    <dt>Par</dt><dd>{{ rg.agent ?? '—' }}</dd>
                    <dt>Référence de la preuve</dt><dd>{{ rg.reference ?? '—' }}</dd>
                    <dt>Confirmée</dt><dd>{{ date(rg.confirme_le, true) }}{{ rg.confirme_par ? ' par ' + rg.confirme_par : '' }}</dd>
                    @if (rg.commentaire) { <dt>Commentaire</dt><dd>{{ rg.commentaire }}</dd> }
                  </dl>
                }
              </section>
            }
            @if (d.date_cloture || d.motif_refus || d.motif_annulation) {
              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top"><h2>Issue du dossier</h2></div>
                <dl class="bea-rc-dl">
                  @if (d.date_cloture) {
                    <dt>Clôturée le</dt><dd>{{ date(d.date_cloture, true) }}{{ d.cloture_par ? ' par ' + d.cloture_par : '' }}</dd>
                    <dt>Résultat</dt><dd>{{ d.resultat_libelle ?? '—' }}</dd>
                    <dt>Motif de résolution</dt><dd>{{ d.motif_resolution ?? '—' }}</dd>
                  }
                  @if (d.motif_refus) { <dt>Motif du rejet</dt><dd>{{ d.motif_refus }}</dd> }
                  @if (d.motif_annulation) { <dt>Motif d’annulation</dt><dd>{{ d.motif_annulation }}</dd> }
                </dl>
              </section>
            }
          }

          @case ('chronologie') {
            <section class="bea-mg__panel bea-rc-pad">
              @if (evenements(); as ev) {
                <ol class="bea-ct-timeline">
                  @for (e of ev; track e.id) {
                    <li>
                      <span class="bea-ct-timeline__dot" [class.bea-ct-timeline__dot--sm]="e.type !== 'CREATION'"><mat-icon>{{ icone(e.type) }}</mat-icon></span>
                      <div class="bea-ct-timeline__body">
                        <p><strong>{{ e.libelle }}</strong>
                          @if (e.statut_apres && e.statut_apres !== e.statut_avant) { <span class="bea-ct-badge" [attr.data-tone]="toneStatut(e.code_statut_apres ?? '')">{{ e.statut_apres }}</span> }
                        </p>
                        <p class="bea-ct-timeline__meta">
                          {{ date(e.date_effet, true) }}{{ e.auteur ? ' · ' + e.auteur : '' }}{{ e.unite ? ' · ' + e.unite : '' }}
                          @if (e.enregistre_le !== e.date_effet) { · saisi le {{ date(e.enregistre_le, true) }} }
                        </p>
                        @if (detailEvenement(e); as det) { <p class="bea-ct-timeline__meta">{{ det }}</p> }
                        @if (e.commentaire) { <p class="bea-ct-timeline__comment">{{ e.commentaire }}</p> }
                      </div>
                    </li>
                  } @empty {
                    <li class="bea-ct-timeline__empty">Aucun événement.</li>
                  }
                </ol>
              } @else {
                <p class="bea-rc-muted">Chargement de l’historique…</p>
              }
            </section>
          }

          @case ('documents') {
            <section class="bea-mg__panel bea-rc-pad bea-rc-pj">
              @if (d.actions['documents_voir']) {
                <bea-rc-pieces [dossierId]="d.id" [reference]="d.reference" [operations]="referencesOperations()" (modifie)="piecesModifiees($event)" />
              } @else {
                <p class="bea-rc-muted">Vous n’avez pas accès aux notes et pièces jointes de ce dossier.</p>
              }
            </section>
          }
        }

        @if (regularisationOuverte()) {
          <div class="bea-mg__backdrop" (click)="regularisationOuverte.set(false)"></div>
          <form class="bea-mg__modal" role="dialog" aria-modal="true" [formGroup]="regul" (ngSubmit)="confirmerRegularisation()">
            <div class="bea-mg__modal-head">
              <h2>Confirmer la régularisation — {{ d.reference }}</h2>
              <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="regularisationOuverte.set(false)"><mat-icon>close</mat-icon></button>
            </div>
            <div class="bea-rc-form">
              <div class="bea-rc-note"><mat-icon>info</mat-icon>
                <span>Constat d’une régularisation déjà passée dans ORION : BEA DIGITAL n’exécute aucune écriture. La preuve doit être jointe au dossier.</span>
              </div>
              <div class="bea-rc-row">
                <label>Date de la régularisation <em>*</em><input type="date" formControlName="effectuee_le" [max]="aujourdhui" /></label>
                <label>Référence de la preuve <em>*</em><input formControlName="reference" maxlength="120" placeholder="N° d’écriture, d’extourne…" /></label>
              </div>
              <label>Commentaire <textarea formControlName="commentaire" rows="3" maxlength="4000"></textarea></label>
              <span class="bea-rc-hint">Agent ayant effectué la régularisation : vous-même ({{ store.config()?.utilisateur }}).</span>
            </div>
            <div class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="regularisationOuverte.set(false)">Annuler</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>verified</mat-icon> Confirmer</button>
            </div>
          </form>
        }

        @if (appelOuvert()) {
          <div class="bea-mg__backdrop" (click)="fermerAppel()"></div>
          <form class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" [formGroup]="appel" (ngSubmit)="enregistrerAppel()">
            <div class="bea-mg__modal-head">
              <h2>Ajouter un appel — {{ d.reference }}</h2>
              <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerAppel()"><mat-icon>close</mat-icon></button>
            </div>
            <div class="bea-rc-form">
              <div class="bea-rc-row">
                <label>Date et heure <em>*</em><input type="datetime-local" formControlName="appel_le" [max]="maintenant" /></label>
                <label>Numéro de l’appelant <em>*</em><input formControlName="numero_appelant" maxlength="40" /></label>
                <label>Référence de l’appel <input formControlName="reference_appel" maxlength="120" /></label>
              </div>
              <div class="bea-rc-row">
                <label class="bea-rc-check"><input type="checkbox" formControlName="identite_verifiee" /> Identité vérifiée</label>
                <label>Mode de vérification <input formControlName="mode_verification" maxlength="200" /></label>
              </div>
              <div class="bea-rc-row">
                <label>Rappel
                  <select formControlName="rappel_statut">
                    @for (r of store.libelles('statuts_rappel'); track r.code) { <option [value]="r.code">{{ r.libelle }}</option> }
                  </select>
                </label>
                @if (appel.controls.rappel_statut.value === 'A_RAPPELER') {
                  <label>Rappel prévu le <em>*</em><input type="datetime-local" formControlName="rappel_prevu_le" /></label>
                }
                @if (store.config()?.parametres?.enregistrement_appels_autorise) {
                  <label>Référence de l’enregistrement <input formControlName="reference_enregistrement" maxlength="200" /></label>
                }
              </div>
              <label>Notes <textarea formControlName="commentaire" rows="3" maxlength="4000"></textarea></label>
            </div>
            <div class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerAppel()">Annuler</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer l’appel</button>
            </div>
          </form>
        }
      } @else if (introuvable()) {
        <section class="bea-mg__panel">
          <div class="bea-ct-empty"><mat-icon>search_off</mat-icon>
            <p>Réclamation introuvable ou hors de votre périmètre.</p>
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reclamations/dossiers"><mat-icon>arrow_back</mat-icon> Retour à la liste</a>
          </div>
        </section>
      } @else {
        <section class="bea-mg__panel bea-rc-pad"><p class="bea-rc-muted">Chargement du dossier…</p></section>
      }
    </section>
  `,
})
export class RcFicheComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  readonly store = inject(ReclamationsStore);

  readonly toneStatut = toneStatut;
  readonly tonePriorite = tonePriorite;
  readonly onglets = ONGLETS;
  readonly etapes = ETAPES;
  readonly maintenant = maintenantLocal();
  readonly aujourdhui = maintenantLocal().slice(0, 10);

  readonly dossier = signal<Dossier | null>(null);
  readonly introuvable = signal(false);
  readonly chargement = signal(false);
  readonly onglet = signal<Onglet>('general');
  readonly evenements = signal<Evenement[] | null>(null);
  readonly nbDocuments = signal(0);
  readonly edition = signal(false);
  readonly editionOps = signal(false);
  readonly appelOuvert = signal(false);
  readonly busy = signal(false);
  readonly tente = signal(false);
  readonly tenteOps = signal(false);
  readonly classement = signal<Classement>({ ...CLASSEMENT_VIDE });
  readonly operations = signal<OperationSaisie[]>([]);
  readonly importOuvert = signal(false);
  readonly importEnAttente = computed(() => !!this.dossier()?.imports.some((i) => i.statut === 'ANALYSE'));
  readonly referencesOperations = computed(() => [...new Set((this.dossier()?.operations ?? []).map((o) => o.reference))]);
  readonly regroupementOps = computed(() =>
    (this.dossier()?.nb_clients ?? 0) > 1 || this.operations().some((l) => l.client_racine.trim() || l.compte_reference.trim()));
  motifOps = '';
  justificationOps = '';
  private readonly premiere = signal('');
  private readonly receptionSr = signal('');
  private id = '';
  private initial = '';
  private initialOps = '';

  readonly etapeIndex = computed(() => ETAPES.findIndex((e) => e.code === this.dossier()?.etape));
  readonly interrompu = computed(() => ['REJETEE', 'ANNULEE'].includes(this.dossier()?.statut ?? ''));
  readonly dateModifiee = computed(() => {
    const d = this.dossier();
    if (!d) return false;
    return this.premiere() !== versSaisieLocale(d.date_premiere_reception)
      || (!!d.date_reception_sr && this.receptionSr() !== versSaisieLocale(d.date_reception_sr));
  });

  readonly form = this.fb.nonNullable.group({
    objet: ['', Validators.required],
    description: ['', Validators.required],
    priorite: ['NORMALE'],
    date_reclamation: ['', Validators.required],
    agence_reception_id: [''],
    niveau_concerne: ['SERVICE' as 'SERVICE' | 'DEPARTEMENT'],
    org_departement_id: [''],
    org_service_id: [''],
    client_racine: ['', Validators.pattern(/^[0-9]{6}$/)],
    client_categorie: [''],
    client_nom: ['', Validators.required],
    client_telephone: [''],
    client_email: [''],
    client_agence_id: [''],
    client_adresse: [''],
    date_premiere_reception: ['', Validators.required],
    date_reception_sr: [''],
    motif: [''],
  });

  readonly appel = this.fb.nonNullable.group({
    appel_le: [maintenantLocal()],
    numero_appelant: [''],
    reference_appel: [''],
    identite_verifiee: [false],
    mode_verification: [''],
    rappel_statut: ['AUCUN'],
    rappel_prevu_le: [''],
    reference_enregistrement: [''],
    commentaire: [''],
  });

  readonly regul = this.fb.nonNullable.group({
    effectuee_le: [maintenantLocal().slice(0, 10), Validators.required],
    reference: ['', Validators.required],
    commentaire: [''],
  });
  readonly regularisationOuverte = signal(false);

  readonly hasUnsavedChanges = unsavedChanges(() => !this.busy() && (
    (this.edition() && this.instantane() !== this.initial)
    || (this.editionOps() && JSON.stringify(this.operations()) !== this.initialOps)
    || (this.appelOuvert() && this.appel.dirty)
    || (this.regularisationOuverte() && this.regul.dirty)));

  private instantane(): string {
    return JSON.stringify([this.form.getRawValue(), this.classement()]);
  }

  ngOnInit(): void {
    this.store.charger();
    const c = this.form.controls;
    c.date_premiere_reception.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.premiere.set(v));
    c.date_reception_sr.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.receptionSr.set(v));
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((q) => {
      const o = q.get('onglet');
      this.onglet.set(ONGLETS.find((x) => x.code === o)?.code ?? 'general');
      this.chargerOnglet();
    });
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((p) => {
      this.id = p.get('id') ?? '';
      this.dossier.set(null);
      this.introuvable.set(false);
      this.edition.set(false);
      this.editionOps.set(false);
      this.evenements.set(null);
      this.recharger();
    });
  }

  date(iso: string | null | undefined, heure = false): string {
    return dateFr(iso, heure);
  }

  montant(v: string | null | undefined, devise = 'MRU'): string {
    return montantFr(v, devise);
  }

  parDevise(d: Dossier): string {
    return totauxParDevise(d.par_devise);
  }

  icone(type: string): string {
    return ICONES_EVENEMENT[type] ?? 'radio_button_checked';
  }

  detailEvenement(e: Evenement): string | null {
    const d = e.donnees ?? {};
    if (e.type === 'OPERATIONS') {
      type Etat = { nb: number; total?: string; par_devise?: TotalDevise[] };
      const av = d['avant'] as Etat | undefined;
      const ap = d['apres'] as Etat | undefined;
      const lib = (x: Etat) => (x.par_devise ? totauxParDevise(x.par_devise) : montantFr(x.total ?? null));
      if (av && ap) return `Opérations : ${av.nb} (${lib(av)}) → ${ap.nb} (${lib(ap)})`;
    }
    if (e.type === 'REGULARISATION_CONFIRMEE') {
      return `Le ${dateFr(String(d['regularisation_le'] ?? ''))} par ${d['agent'] ?? '—'} · référence ${d['reference'] ?? '—'}`;
    }
    if (typeof d['operation'] === 'string' && typeof d['fichier'] === 'string') {
      return `${d['fichier']} (${d['categorie'] ?? ''}) — opération ${d['operation']}`;
    }
    if (Array.isArray(d['champs'])) return `Champs : ${(d['champs'] as string[]).join(', ')}`;
    if (Array.isArray(d['operations'])) return `${(d['operations'] as unknown[]).length} opération(s) saisie(s)`;
    if (typeof d['fichier'] === 'string') {
      return `${d['titre'] ? d['titre'] + ' — ' : ''}${d['fichier']}${d['categorie'] ? ' (' + d['categorie'] + ')' : ''}`;
    }
    if (e.type === 'SUPPRESSION') return `Conservés : ${d['operations'] ?? 0} opération(s), ${d['documents'] ?? 0} pièce(s)`;
    if (typeof d['numero'] === 'string') return `Numéro : ${d['numero']}`;
    if (typeof d['canal'] === 'string') return `Canal : ${d['canal']}`;
    return null;
  }

  recharger(): void {
    if (!this.id) return;
    this.chargement.set(true);
    this.rc.lire(this.id).subscribe({
      next: (d) => {
        this.chargement.set(false);
        this.applique(d);
        if (this.route.snapshot.queryParamMap.get('edition') && d.actions['modifier'] && !this.edition()) this.ouvrirEdition();
      },
      error: (e) => {
        this.chargement.set(false);
        void describeApiErrorAsync(e).then((i) => {
          if (i.status === 404 || i.status === 422) this.introuvable.set(true);
          else this.feedback.apiError(i, 'Dossier indisponible');
        });
      },
    });
  }

  choisir(o: Onglet): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { onglet: o === 'general' ? null : o, edition: null }, queryParamsHandling: 'merge', replaceUrl: true });
  }

  private chargerOnglet(): void {
    const d = this.dossier();
    if (!d || this.onglet() !== 'chronologie' || this.evenements()) return;
    this.rc.chronologie(d.id).subscribe({
      next: (ev) => this.evenements.set(ev),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Historique indisponible')),
    });
  }

  applique(d: Dossier): void {
    this.dossier.set(d);
    this.nbDocuments.set(d.nb_documents);
    this.evenements.set(null);
    this.chargerOnglet();
  }

  piecesModifiees(n: number): void {
    this.nbDocuments.set(n);
    this.evenements.set(null);
  }

  invalide(nom: 'objet' | 'description' | 'client_nom' | 'client_racine' | 'date_reclamation'): boolean {
    const ctl = this.form.controls[nom];
    return ctl.invalid && (ctl.touched || this.tente());
  }

  apresImport(d: Dossier): void {
    this.importOuvert.set(false);
    this.applique(d);
  }

  ouvrirOperations(): void {
    const d = this.dossier();
    if (!d) return;
    this.operations.set(d.operations.map(versSaisie));
    this.initialOps = JSON.stringify(this.operations());
    this.motifOps = '';
    this.justificationOps = '';
    this.importOuvert.set(false);
    this.tenteOps.set(false);
    this.editionOps.set(true);
  }

  enregistrerOperations(): void {
    const d = this.dossier();
    if (!d) return;
    this.tenteOps.set(true);
    const multi = clientsSaisis(this.operations(), d.client.racine) > 1;
    const erreur = operationsErreur(this.operations(), d.regle)
      ?? (multi && !this.justificationOps.trim() && !d.justification_regroupement
        ? 'Les opérations concernent plusieurs clients : justifiez le regroupement dans un même dossier.' : null);
    if (erreur) {
      this.feedback.warning({ title: 'Opérations à corriger', message: erreur });
      return;
    }
    const corps = {
      revision: d.revision, operations: operationsCorps(this.operations()), motif: this.motifOps.trim() || null,
      justification_regroupement: this.justificationOps.trim() || null,
    };
    this.feedback
      .run(() => this.rc.remplacerOperations(d.id, corps), {
        busy: this.busy,
        loading: 'Enregistrement des opérations…',
        success: (r) => r.revision === d.revision
          ? { title: 'Aucune modification', message: 'La liste des opérations était déjà à jour.' }
          : { title: 'Opérations enregistrées', details: [
            { label: 'Opérations', value: String(r.nb_operations) },
            { label: 'Montants', value: totauxParDevise(r.par_devise) },
          ] },
        errorTitle: 'Enregistrement refusé',
        errorHint: 'Vos saisies ont été conservées.',
        retry: false,
      })
      .subscribe((r) => {
        this.editionOps.set(false);
        this.applique(r);
      });
  }

  ouvrirEdition(): void {
    const d = this.dossier();
    if (!d) return;
    this.tente.set(false);
    this.form.reset({
      objet: d.objet, description: d.description, priorite: d.priorite,
      date_reclamation: d.date_reclamation ?? d.date_premiere_reception.slice(0, 10),
      agence_reception_id: d.agence_reception_ref?.id ?? '',
      niveau_concerne: !d.service_ref && d.departement_ref ? 'DEPARTEMENT' : 'SERVICE',
      org_departement_id: d.departement_ref?.id ?? '', org_service_id: d.service_ref?.id ?? '',
      client_racine: d.client.racine ?? '', client_categorie: d.client.categorie ?? '', client_nom: d.client.nom ?? '',
      client_telephone: d.client.telephone ?? '', client_email: d.client.email ?? '',
      client_agence_id: d.client.agence?.id ?? '', client_adresse: d.client.adresse ?? '',
      date_premiere_reception: versSaisieLocale(d.date_premiere_reception),
      date_reception_sr: versSaisieLocale(d.date_reception_sr), motif: '',
    });
    this.classement.set(classementDe(d));
    this.premiere.set(this.form.controls.date_premiere_reception.value);
    this.receptionSr.set(this.form.controls.date_reception_sr.value);
    this.initial = this.instantane();
    this.editionOps.set(false);
    this.edition.set(true);
    this.choisir('general');
  }

  annulerEdition(): void {
    this.edition.set(false);
  }

  enregistrer(): void {
    const d = this.dossier();
    if (!d) return;
    this.tente.set(true);
    this.form.markAllAsTouched();
    const v = this.form.getRawValue();
    const erreur = this.form.invalid ? 'Vérifiez les champs signalés en rouge.' : classementErreur(this.classement());
    if (erreur) {
      this.feedback.warning({ title: 'Champs à corriger', message: erreur });
      return;
    }
    if (this.dateModifiee() && !v.motif.trim()) {
      this.feedback.warning({ title: 'Motif obligatoire', message: 'Indiquez pourquoi la date de réception est corrigée.' });
      return;
    }
    const premiere = depuisSaisieLocale(v.date_premiere_reception);
    if (!premiere) {
      this.feedback.warning({ title: 'Date invalide', message: 'Renseignez la date de réception par la banque.' });
      return;
    }
    const corps: Record<string, unknown> = {
      revision: d.revision, objet: v.objet.trim(), description: v.description.trim(), priorite: v.priorite,
      client_nom: v.client_nom.trim(), date_reclamation: v.date_reclamation, date_premiere_reception: premiere,
      motif: v.motif.trim() || null,
    };
    if (d.date_reception_sr && v.date_reception_sr) corps['date_reception_sr'] = depuisSaisieLocale(v.date_reception_sr);
    if (v.niveau_concerne === 'SERVICE') v.org_departement_id = '';
    else v.org_service_id = '';
    const effacer: string[] = [];
    for (const champ of EFFACABLES) {
      const valeur = v[champ].trim();
      if (valeur) corps[champ] = valeur;
      else effacer.push(champ);
    }
    const cl = classementCorps(this.classement());
    for (const champ of NIVEAUX_CLASSEMENT) {
      if (cl[champ]) corps[champ] = cl[champ];
      else effacer.push(champ);
    }
    if (v.niveau_concerne === 'DEPARTEMENT' && d.point_reception_ref) effacer.push('point_reception_id');
    corps['effacer'] = effacer;
    this.feedback
      .run(() => this.rc.modifier(d.id, corps), {
        busy: this.busy,
        loading: 'Enregistrement…',
        success: (r) => r.revision === d.revision
          ? { title: 'Aucune modification', message: 'Les données étaient déjà à jour.' }
          : { title: 'Dossier mis à jour', details: [{ label: 'Référence', value: r.reference }, { label: 'Révision', value: String(r.revision) }] },
        errorTitle: 'Correction refusée',
        errorHint: 'Vos saisies ont été conservées.',
        retry: false,
      })
      .subscribe((r) => {
        this.edition.set(false);
        this.applique(r);
      });
  }

  supprimer(): void {
    const d = this.dossier();
    if (!d) return;
    this.feedback
      .run(() => this.rc.supprimer(d.id, { revision: d.revision }), optionsSuppression(d.reference, this.busy))
      .subscribe(() => void this.router.navigate(['/reclamations/dossiers']));
  }

  restaurer(): void {
    const d = this.dossier();
    if (!d) return;
    this.feedback
      .runWithReason((motif) => this.rc.restaurer(d.id, { revision: d.revision, motif }), optionsRestauration(d.reference, this.busy))
      .subscribe((r) => this.applique(r));
  }

  ouvrirRegularisation(): void {
    this.regul.reset({ effectuee_le: maintenantLocal().slice(0, 10), reference: '', commentaire: '' });
    this.regularisationOuverte.set(true);
  }

  confirmerRegularisation(): void {
    const d = this.dossier();
    if (!d) return;
    const v = this.regul.getRawValue();
    if (!v.effectuee_le || !v.reference.trim()) {
      this.feedback.warning({ title: 'Confirmation incomplète', message: 'La date et la référence de la preuve sont obligatoires.' });
      return;
    }
    if (v.effectuee_le > this.aujourdhui) {
      this.feedback.warning({ title: 'Date invalide', message: 'La date de la régularisation ne peut pas être dans le futur.' });
      return;
    }
    this.feedback
      .run(() => this.rc.confirmerRegularisation(d.id, {
        revision: d.revision, effectuee_le: v.effectuee_le, reference: v.reference.trim(),
        commentaire: v.commentaire.trim() || null,
      }), {
        busy: this.busy,
        loading: 'Confirmation de la régularisation…',
        success: (r) => ({ title: 'Régularisation confirmée', details: [
          { label: 'Dossier', value: r.reference }, { label: 'Référence', value: r.regularisation?.reference ?? '' },
        ] }),
        errorTitle: 'Confirmation refusée',
        errorHint: 'Vos saisies ont été conservées.',
        retry: false,
      })
      .subscribe((r) => {
        this.regularisationOuverte.set(false);
        this.applique(r);
      });
  }

  ouvrirAppel(): void {
    this.appel.reset({ appel_le: maintenantLocal(), rappel_statut: 'AUCUN', identite_verifiee: false });
    this.appelOuvert.set(true);
  }

  fermerAppel(): void {
    this.appelOuvert.set(false);
  }

  enregistrerAppel(): void {
    const d = this.dossier();
    if (!d) return;
    const a = this.appel.getRawValue();
    const appelLe = depuisSaisieLocale(a.appel_le);
    if (!appelLe || !a.numero_appelant.trim() || (a.rappel_statut === 'A_RAPPELER' && !a.rappel_prevu_le)) {
      this.feedback.warning({ title: 'Appel incomplet', message: 'Date, numéro de l’appelant et, le cas échéant, date de rappel sont obligatoires.' });
      return;
    }
    const corps = {
      appel_le: appelLe, numero_appelant: a.numero_appelant.trim(), reference_appel: a.reference_appel.trim() || null,
      identite_verifiee: a.identite_verifiee, mode_verification: a.mode_verification.trim() || null,
      rappel_statut: a.rappel_statut,
      rappel_prevu_le: a.rappel_statut === 'A_RAPPELER' ? depuisSaisieLocale(a.rappel_prevu_le) : null,
      reference_enregistrement: a.reference_enregistrement.trim() || null, commentaire: a.commentaire.trim() || null,
    };
    this.feedback
      .run(() => this.rc.ajouterAppel(d.id, corps), {
        busy: this.busy,
        loading: 'Enregistrement de l’appel…',
        success: () => ({ title: 'Appel enregistré', details: [{ label: 'Dossier', value: d.reference }] }),
        errorTitle: 'Appel refusé',
        errorHint: 'Vos saisies ont été conservées.',
        retry: false,
      })
      .subscribe((r) => {
        this.appelOuvert.set(false);
        this.applique(r);
      });
  }
}
