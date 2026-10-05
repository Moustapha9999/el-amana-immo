import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { of } from 'rxjs';
import { catchError, debounceTime, map, switchMap } from 'rxjs/operators';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackMessage, FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { MontantPipe, TauxPipe } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { UiDialogAction } from '../shared/ui-dialog/ui-dialog.types';
import { ContratsDocumentsComponent } from './contrats-documents.component';
import { fxStatut, fxTone } from './facturation/facturation.models';
import {
  ACTION_LABELS,
  Contrat,
  ContratsConfig,
  Echeance,
  FacturesContrat,
  PERIODICITE_LABELS,
  Paiement,
  RECONDUCTION_LABELS,
  RefItem,
  TYPES_ECHEANCE,
  TYPE_AVENANT_LABELS,
  aujourdhui,
  dateFr,
  dateHeureFr,
  joursLabel,
  num,
  statutLabel,
  telechargerBlob,
  typeEcheanceLabel,
} from './contrats.models';

type TransitionAction = 'soumettre' | 'valider' | 'suspendre' | 'reprendre' | 'expirer' | 'archiver';
type Onglet = 'echeances' | 'paiements' | 'avenants' | 'factures' | 'documents' | 'historique';

const TRANSITIONS: Record<TransitionAction, { preset: UiDialogAction; question: string; hint: string; loading: string; success: string; errorTitle: string }> = {
  soumettre: {
    preset: 'soumission',
    question: 'Soumettre pour validation le contrat',
    hint: 'Les valideurs sont notifiés ; la fiche n’est plus modifiable librement pendant la validation.',
    loading: 'Soumission…',
    success: 'Contrat soumis pour validation',
    errorTitle: 'Échec de la soumission',
  },
  valider: {
    preset: 'validation',
    question: 'Valider le contrat',
    hint: 'Le contrat devient actif et son échéancier de paiement est généré automatiquement.',
    loading: 'Validation…',
    success: 'Contrat validé',
    errorTitle: 'Échec de la validation',
  },
  suspendre: {
    preset: 'suspension',
    question: 'Suspendre le contrat',
    hint: 'Le contrat reste consultable et pourra être repris à tout moment.',
    loading: 'Suspension…',
    success: 'Contrat suspendu',
    errorTitle: 'Échec de la suspension',
  },
  reprendre: {
    preset: 'reprise',
    question: 'Reprendre le contrat',
    hint: 'Le contrat redevient actif.',
    loading: 'Reprise…',
    success: 'Contrat repris',
    errorTitle: 'Échec de la reprise',
  },
  expirer: {
    preset: 'expiration',
    question: 'Clôturer (marquer expiré) le contrat',
    hint: 'Vous pourrez ensuite le reconduire, le renouveler ou l’archiver.',
    loading: 'Mise à jour du statut…',
    success: 'Contrat marqué expiré',
    errorTitle: 'Échec de la mise à jour',
  },
  archiver: {
    preset: 'archivage',
    question: 'Archiver le contrat',
    hint: 'Le contrat passera en lecture seule.',
    loading: 'Archivage…',
    success: 'Contrat archivé',
    errorTitle: 'Échec de l’archivage',
  },
};

const STATUT_AIDE: Record<string, string> = {
  BROUILLON: 'Complétez la fiche (fournisseur, montant, dates) puis soumettez-la pour validation.',
  EN_PREPARATION: 'Complétez la fiche puis soumettez-la pour validation.',
  EN_VALIDATION: 'En attente d’un valideur : validation (activation + échéancier) ou rejet motivé.',
  ACTIF: 'Contrat en vigueur. Montants et dates se modifient par avenant ; les échéances déclenchent des alertes.',
  SUSPENDU: 'Contrat temporairement suspendu. Reprenez-le pour le réactiver.',
  EXPIRE: 'Contrat arrivé à terme. Reconduisez-le, renouvelez-le ou archivez-le.',
  ARCHIVE: 'Contrat archivé : consultation uniquement.',
  REJETE: 'Contrat rejeté : corrigez la fiche puis soumettez-la à nouveau.',
  ANNULE: 'Contrat annulé : consultation uniquement.',
};

const EDITION_LIBRE = new Set(['BROUILLON', 'EN_PREPARATION', 'REJETE']);
const VERROUILLE = new Set(['ARCHIVE', 'ANNULE']);
const MODES_AVEC_REF = new Set(['Virement', 'Amanty']);
const CHAMPS_FINANCIERS = ['date_debut', 'date_fin', 'montant_ht', 'taux_tva', 'periodicite', 'devise'] as const;

interface Simulation {
  montant_ttc: string | null;
  echeances: { date: string; montant: string }[];
  erreur: string | null;
}

@Component({
  selector: 'bea-contrats-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, TauxPipe, MatIconModule, ContratsDocumentsComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances</p>
          <h1>{{ fiche()?.reference || 'Nouveau contrat' }}</h1>
          @if (fiche(); as c) {
            <p class="bea-ct-head__meta">
              <span class="bea-ct-badge" [attr.data-tone]="c.etat">{{ statut(c.etat) }}</span>
              <span>{{ c.titre }}</span>
              <span class="bea-ct-head__version">Version {{ c.version }}</span>
            </p>
          }
        </div>
        <div class="bea-mg__actions">
          @if (fiche(); as c) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="telechargement()" (click)="telechargerPdf(c)">
              <mat-icon>picture_as_pdf</mat-icon> {{ telechargement() ? 'Préparation…' : 'Fiche PDF' }}
            </button>
          }
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/contrats-echeances/liste"><mat-icon>arrow_back</mat-icon> Liste</a>
        </div>
      </header>

      @if (fiche(); as c) {
        <div class="bea-mg__panel bea-ct-panel bea-ct-life">
          <div class="bea-ct-life__head">
            <div>
              <h2>Cycle de vie</h2>
              <p class="bea-ct-life__hint">{{ aide(c.statut) }}</p>
            </div>
            <div class="bea-ct-life__kpis">
              <div><span>Montant TTC</span><strong>{{ c.montant | montant }} {{ c.devise }}</strong>@if (c.montant_ht !== null) { <small>HT {{ c.montant_ht | montant }} · TVA {{ c.taux_tva | taux }}</small> }</div>
              <div><span>Fin</span><strong>{{ date(c.date_fin) }}</strong>@if (c.jours_restants !== null) { <small>{{ jours(c.jours_restants) }}</small> }</div>
              <div><span>Payé / échéancier</span><strong>{{ totaux().paye | montant }} / {{ totaux().prevu | montant }}</strong></div>
            </div>
          </div>
          <ol class="bea-ct-steps" aria-label="Cycle de vie">
            @for (s of etapes; track s.code; let i = $index) {
              <li [class.is-done]="etapeIndex(c.statut) > i" [class.is-on]="etapeIndex(c.statut) === i">
                <span class="bea-ct-steps__dot">{{ i + 1 }}</span>{{ s.label }}
              </li>
            }
          </ol>
          <fieldset class="bea-ct-life__actions" [disabled]="actionEnCours()" [attr.aria-busy]="actionEnCours()">
            <legend class="bea-ct-sr-only">Actions sur le contrat</legend>
            <div class="bea-ct-life__group">
              @if (cap().manage && edition(c.statut)) {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('soumettre')"><mat-icon>send</mat-icon> Soumettre pour validation</button>
              }
              @if (cap().validate && c.statut === 'EN_VALIDATION') {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('valider')"><mat-icon>verified</mat-icon> Valider</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="demanderMotif('rejeter')"><mat-icon>block</mat-icon> Rejeter</button>
              }
              @if (cap().manage && (c.statut === 'ACTIF' || c.statut === 'EXPIRE')) {
                @if (c.date_fin) {
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="reconduire()"><mat-icon>update</mat-icon> Reconduire (tacite)</button>
                }
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="renouveler()"><mat-icon>autorenew</mat-icon> Renouveler (expresse)</button>
              }
              @if (cap().manage && (c.statut === 'ACTIF' || c.statut === 'SUSPENDU' || c.statut === 'EXPIRE')) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirAvenant()"><mat-icon>post_add</mat-icon> Avenant</button>
              }
              @if (cap().manage && c.statut === 'ACTIF') {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('suspendre')"><mat-icon>pause_circle</mat-icon> Suspendre</button>
              }
              @if (cap().manage && c.statut === 'SUSPENDU') {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('reprendre')"><mat-icon>play_circle</mat-icon> Reprendre</button>
              }
              @if (cap().manage && (c.statut === 'ACTIF' || c.statut === 'SUSPENDU')) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('expirer')"><mat-icon>event_busy</mat-icon> Clôturer (expiré)</button>
              }
            </div>
            <div class="bea-ct-life__group">
              @if (cap().manage && (c.statut === 'ACTIF' || c.statut === 'EXPIRE' || c.statut === 'SUSPENDU' || c.statut === 'REJETE')) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('archiver')"><mat-icon>inventory_2</mat-icon> Archiver</button>
              }
              @if (cap().validate && c.statut !== 'ARCHIVE' && c.statut !== 'ANNULE' && c.statut !== 'EXPIRE') {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-ct-danger" (click)="demanderMotif('annuler')"><mat-icon>cancel</mat-icon> Annuler / résilier</button>
              }
              @if (cap().manage && (edition(c.statut) || c.statut === 'ANNULE')) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-ct-danger" (click)="supprimer(c)"><mat-icon>delete</mat-icon> Retirer du registre</button>
              }
            </div>
          </fieldset>
          @if (c.contrat_precedent_id) {
            <p class="bea-ct-note">Renouvellement d’un contrat précédent — <a class="bea-ct-link" [routerLink]="['/contrats-echeances', c.contrat_precedent_id]">ouvrir le contrat d’origine</a></p>
          }
        </div>
      }

      <form [formGroup]="form" (ngSubmit)="save()" class="bea-ct-form">
        @if (fiche() && !financierModifiable()) {
          <p class="bea-ct-help bea-ct-help--warn"><mat-icon>lock</mat-icon>
            Contrat {{ statut(fiche()!.statut).toLowerCase() }} : montants, dates, périodicité et devise se modifient par <button type="button" class="bea-ct-linkbtn" (click)="ouvrirAvenant()">avenant</button> (historique des versions conservé).
          </p>
        }
        <div class="bea-ct-form__grid">
          <div class="bea-mg__panel bea-ct-card">
            <h2 class="bea-ct-card__title"><span>A</span> Informations générales</h2>
            <div class="bea-ct-grid">
              <label class="bea-ct-span2">Objet du contrat *
                <input formControlName="titre" maxlength="255" placeholder="Ex. : Maintenance des climatiseurs — siège" [attr.aria-invalid]="!!erreurChamp('titre')" />
                @if (erreurChamp('titre'); as m) { <small class="bea-ct-field-error" role="alert">{{ m }}</small> }
              </label>
              <label>N° contrat <input formControlName="numero_contrat" maxlength="80" placeholder="Réf. interne ou fournisseur" /></label>
              <label>Type de contrat
                <select formControlName="type_contrat">
                  @for (t of typesActifs(); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
                </select>
              </label>
              <label>Devise
                <select formControlName="devise">
                  @for (d of config()?.devises ?? ['MRU']; track d) { <option [value]="d">{{ d }}</option> }
                </select>
              </label>
              <label class="bea-ct-span2">Description <textarea formControlName="description" rows="3" placeholder="Détail de la prestation"></textarea></label>
              <label class="bea-ct-span2">Observation <textarea formControlName="observation" rows="2" placeholder="Remarques, notes particulières"></textarea></label>
            </div>
          </div>

          <div class="bea-mg__panel bea-ct-card">
            <h2 class="bea-ct-card__title"><span>B</span> Intervenants &amp; affectation</h2>
            <div class="bea-ct-grid">
              <label class="bea-ct-span2">Fournisseur
                <select formControlName="fournisseur_id">
                  <option value="">— Sélectionner —</option>
                  @for (f of fournisseurs(); track f.id) { <option [value]="f.id">{{ f.raison_sociale }}</option> }
                </select>
              </label>
              <label class="bea-ct-span2">Agence / entité bénéficiaire
                <select formControlName="agence_id">
                  <option value="">— Sélectionner —</option>
                  @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
                </select>
              </label>
              <label class="bea-ct-span2">Responsable interne
                <select formControlName="responsable_id">
                  <option value="">— Sélectionner —</option>
                  @for (u of responsables(); track u.id) { <option [value]="u.id">{{ u.full_name }}</option> }
                </select>
                <small class="bea-ct-hint">Reçoit les rappels (notification et e-mail).</small>
              </label>
            </div>
          </div>

          <div class="bea-mg__panel bea-ct-card bea-ct-card--wide">
            <h2 class="bea-ct-card__title"><span>C</span> Dates, montants &amp; périodicité</h2>
            <div class="bea-ct-grid">
              <label>Date de signature <input type="date" formControlName="date_signature" /></label>
              <label>Date de début *
                <input type="date" formControlName="date_debut" [attr.aria-invalid]="!!erreurChamp('date_debut')" />
                @if (erreurChamp('date_debut'); as m) { <small class="bea-ct-field-error" role="alert">{{ m }}</small> }
              </label>
              <label>Date de fin
                <input type="date" formControlName="date_fin" [attr.aria-invalid]="!!erreurChamp('date_fin')" />
                @if (erreurChamp('date_fin'); as m) { <small class="bea-ct-field-error" role="alert">{{ m }}</small> }
              </label>
              <label>Montant HT (durée du contrat)
                <input type="number" min="0" step="0.01" formControlName="montant_ht" [attr.aria-invalid]="!!erreurChamp('montant_ht')" />
                @if (erreurChamp('montant_ht'); as m) { <small class="bea-ct-field-error" role="alert">{{ m }}</small> }
              </label>
              <label>TVA (%) <input type="number" min="0" max="100" step="0.01" formControlName="taux_tva" /></label>
              <div class="bea-ct-ttc" aria-live="polite">
                <span>Montant TTC (calcul serveur)</span>
                <strong>{{ simulation()?.montant_ttc | montant }} {{ form.controls.devise.value }}</strong>
              </div>
              <label>Périodicité de paiement
                <select formControlName="periodicite">
                  @for (p of periodicites; track p) { <option [value]="p">{{ periodicite(p) }}</option> }
                </select>
              </label>
              <label>Mode de paiement
                <select formControlName="mode_paiement" (change)="onModePaiement()">
                  <option value="">—</option>
                  @for (m of modesPaiement(); track m) { <option [value]="m">{{ m }}</option> }
                </select>
              </label>
              @if (refPaiementVisible()) {
                <label>{{ form.controls.mode_paiement.value === 'Amanty' ? 'Numéro / compte Amanty' : 'Compte bénéficiaire (RIB)' }}
                  <input formControlName="ref_paiement" maxlength="120" />
                </label>
              }
              <label>Alerte (jours avant échéance)
                <input type="number" min="0" max="730" formControlName="alerte_jours" list="bea-ct-alertes" />
                <datalist id="bea-ct-alertes">
                  @for (a of config()?.alerte_jours ?? [30, 60, 90]; track a) { <option [value]="a"></option> }
                </datalist>
              </label>
              <label>Reconduction
                <select formControlName="reconduction">
                  @for (r of reconductions; track r) { <option [value]="r">{{ reconduction(r) }}</option> }
                </select>
              </label>
              <label>Préavis de résiliation (jours)
                <input type="number" min="0" max="3650" formControlName="preavis_jours" placeholder="Ex. 90" />
              </label>
            </div>

            @if (simulation(); as s) {
              <div class="bea-ct-simu">
                <h3><mat-icon>event_note</mat-icon> Échéancier prévisionnel</h3>
                @if (s.erreur) {
                  <p class="bea-ct-simu__warn">{{ s.erreur }}</p>
                } @else if (s.echeances.length) {
                  <p>
                    {{ s.echeances.length }} échéance{{ s.echeances.length > 1 ? 's' : '' }}
                    de {{ s.echeances[0].montant | montant }} {{ form.controls.devise.value }}
                    · du {{ date(s.echeances[0].date) }} au {{ date(s.echeances[s.echeances.length - 1].date) }}
                  </p>
                  <div class="bea-ct-simu__chips">
                    @for (e of s.echeances.slice(0, 12); track e.date) { <span>{{ date(e.date) }}</span> }
                    @if (s.echeances.length > 12) { <span>+{{ s.echeances.length - 12 }}</span> }
                  </div>
                  <small>Généré automatiquement à la validation du contrat.</small>
                } @else {
                  <p class="bea-ct-simu__warn">Renseignez le montant HT pour calculer l’échéancier.</p>
                }
              </div>
            }
          </div>
        </div>

        @if (!fiche()) {
          <p class="bea-ct-help"><mat-icon>folder</mat-icon> <span><strong>D — Documents associés :</strong> enregistrez le brouillon pour déposer le contrat signé, les avenants, bons de commande, factures ou CCTP.</span></p>
        }

        @if (peutEnregistrer()) {
          <div class="bea-ct-savebar">
            <span>{{ form.dirty ? 'Modifications non enregistrées' : 'Fiche à jour' }}</span>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || saving() || (!form.dirty && !!fiche())" [attr.aria-busy]="saving()">
              <mat-icon>save</mat-icon> {{ saving() ? 'Enregistrement…' : fiche() ? 'Enregistrer les modifications' : 'Enregistrer le brouillon' }}
            </button>
          </div>
        }
      </form>

      @if (fiche(); as c) {
        <div class="bea-mg__panel bea-ct-panel bea-ct-suivi">
          <div class="bea-ct-suivi__head">
            <h2>Suivi du contrat</h2>
            <div class="bea-ct-tabs" role="tablist">
              <button type="button" role="tab" [class.is-on]="onglet() === 'echeances'" (click)="onglet.set('echeances')"><mat-icon>schedule</mat-icon> Échéancier <small>{{ (c.echeances || []).length }}</small></button>
              <button type="button" role="tab" [class.is-on]="onglet() === 'paiements'" (click)="onglet.set('paiements')"><mat-icon>payments</mat-icon> Paiements <small>{{ (c.paiements || []).length }}</small></button>
              <button type="button" role="tab" [class.is-on]="onglet() === 'avenants'" (click)="onglet.set('avenants')"><mat-icon>post_add</mat-icon> Avenants <small>{{ (c.avenants || []).length }}</small></button>
              <button type="button" role="tab" [class.is-on]="onglet() === 'factures'" (click)="ouvrirFactures(c.id)"><mat-icon>receipt_long</mat-icon> Factures @if (factures(); as fx) { <small>{{ fx.items.length }}</small> }</button>
              <button type="button" role="tab" [class.is-on]="onglet() === 'documents'" (click)="onglet.set('documents')"><mat-icon>folder</mat-icon> Documents</button>
              <button type="button" role="tab" [class.is-on]="onglet() === 'historique'" (click)="onglet.set('historique')"><mat-icon>history</mat-icon> Historique</button>
            </div>
          </div>

          @if (onglet() === 'echeances') {
            <div class="bea-ct-pane">
              <div class="bea-ct-pane__bar">
                <p class="bea-ct-help"><mat-icon>info</mat-icon>
                  Statuts calculés par le serveur : À venir → Due (≤ {{ config()?.echeance_due_jours ?? 7 }} j) → En retard ; « Payée » dès que les règlements couvrent le montant.
                </p>
                @if (modifiable()) {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="actionEnCours()" (click)="genererEcheancier(c)">
                    <mat-icon>auto_mode</mat-icon> {{ aEcheancier() ? 'Régénérer l’échéancier' : 'Générer l’échéancier' }}
                  </button>
                }
              </div>
              @if (modifiable()) {
                <form class="bea-ct-grid bea-ct-inline" [formGroup]="echeanceForm" (ngSubmit)="sauverEcheance()">
                  <label>Type
                    <select formControlName="type_echeance">
                      @for (t of typesEcheance; track t.code) { <option [value]="t.code">{{ t.label }}</option> }
                    </select>
                  </label>
                  <label>Date prévue <input type="date" formControlName="date_prevue" /></label>
                  <label>Montant <input type="number" min="0" step="0.01" formControlName="montant" /></label>
                  <label>Statut
                    <select formControlName="statut">
                      <option value="">Automatique</option>
                      <option value="FAITE">Réalisée (sans montant)</option>
                      <option value="ANNULEE">Annulée</option>
                    </select>
                  </label>
                  <label>Commentaire <input formControlName="commentaire" /></label>
                  <div class="bea-ct-inline__btns">
                    <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="echeanceForm.invalid || echeanceBusy()">
                      <mat-icon>{{ echeanceEditId() ? 'save' : 'add' }}</mat-icon> {{ echeanceEditId() ? 'Enregistrer' : 'Ajouter' }}
                    </button>
                    @if (echeanceEditId()) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="resetEcheance()">Annuler</button>
                    }
                  </div>
                </form>
              }
              <div class="bea-mg__table-scroll bea-ct-table-wrap">
                <table class="bea-mg__table bea-ct-table">
                  <thead><tr><th>Date</th><th>Type</th><th class="is-num">Montant</th><th class="is-num">Payé</th><th class="is-num">Reste</th><th>Statut</th><th>Commentaire</th><th class="is-actions">Actions</th></tr></thead>
                  <tbody>
                    @for (e of c.echeances || []; track e.id) {
                      <tr class="bea-ct-row">
                        <td class="is-nowrap"><strong>{{ date(e.date_prevue) }}</strong></td>
                        <td>{{ typeEcheance(e.type_echeance) }}</td>
                        <td class="is-num is-nowrap">{{ e.montant === null ? '—' : (e.montant | montant) }}</td>
                        <td class="is-num is-nowrap">{{ e.montant_paye | montant }}</td>
                        <td class="is-num is-nowrap"><strong>{{ resteEcheance(e) | montant }}</strong></td>
                        <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statut(e.statut) }}</span></td>
                        <td class="is-wide"><small>{{ e.commentaire || '' }}</small></td>
                        <td class="bea-mg__actions-cell">
                          @if (modifiable()) {
                            @if (e.type_echeance === 'PAIEMENT' && resteEcheance(e) > 0) {
                              <button type="button" class="bea-mg__icon-btn" title="Régler cette échéance" (click)="regler(e)"><mat-icon>price_check</mat-icon></button>
                            }
                            <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editerEcheance(e)"><mat-icon>edit</mat-icon></button>
                            <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerEcheance(e)"><mat-icon>delete</mat-icon></button>
                          }
                        </td>
                      </tr>
                    } @empty {
                      <tr><td colspan="8"><div class="bea-ct-empty"><mat-icon>event</mat-icon><p>Aucune échéance. L’échéancier est généré à la validation ou via « Générer l’échéancier ».</p></div></td></tr>
                    }
                  </tbody>
                  @if ((c.echeances || []).length) {
                    <tfoot>
                      <tr>
                        <th colspan="2">Rapprochement (TTC {{ c.montant | montant }})</th>
                        <th class="is-num">{{ totaux().prevu | montant }}</th>
                        <th class="is-num">{{ totaux().paye | montant }}</th>
                        <th class="is-num">{{ totaux().reste | montant }}</th>
                        <th colspan="3">
                          @if (ecartEcheancier() !== 0) { <span class="bea-ct-badge" data-tone="ATTENTION">Écart échéancier / TTC : {{ ecartEcheancier() | montant }}</span> }
                        </th>
                      </tr>
                    </tfoot>
                  }
                </table>
              </div>
            </div>
          }

          @if (onglet() === 'paiements') {
            <div class="bea-ct-pane">
              <p class="bea-ct-help"><mat-icon>info</mat-icon>
                Enregistrez les règlements (n° de pièce, date, montant versé) en les rattachant à une échéance. Joignez la preuve de paiement dans
                <button type="button" class="bea-ct-linkbtn" (click)="onglet.set('documents')">Documents</button> (typologie « Preuve de paiement »).
                Suivi interne : aucun virement n’est exécuté depuis BEA DIGITAL.
              </p>
              @if (modifiable()) {
                <form class="bea-ct-grid bea-ct-inline" [formGroup]="paiementForm" (ngSubmit)="sauverPaiement()">
                  <label>Échéance
                    <select formControlName="echeance_id" (change)="onEcheancePaiement()">
                      <option value="">— Hors échéancier —</option>
                      @for (e of echeancesPaiement(); track e.id) {
                        <option [value]="e.id">{{ date(e.date_prevue) }} — reste {{ resteEcheance(e) | montant }}</option>
                      }
                    </select>
                  </label>
                  <label>N° de pièce <input formControlName="reference" maxlength="40" placeholder="Facture, OV, chèque…" /></label>
                  <label>Date prévue <input type="date" formControlName="date_prevue" /></label>
                  <label>Date de paiement <input type="date" formControlName="date_reelle" /></label>
                  <label>Montant prévu <input type="number" min="0" step="0.01" formControlName="montant_prevu" /></label>
                  <label>Montant versé <input type="number" min="0" step="0.01" formControlName="montant_paye" /></label>
                  <label>Mode
                    <select formControlName="mode">
                      <option value="">—</option>
                      @for (m of modesPaiement(); track m) { <option [value]="m">{{ m }}</option> }
                    </select>
                  </label>
                  <label>Commentaire <input formControlName="commentaire" /></label>
                  <div class="bea-ct-inline__btns">
                    <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="paiementForm.invalid || paiementBusy()">
                      <mat-icon>{{ paiementEditId() ? 'save' : 'add' }}</mat-icon> {{ paiementBusy() ? 'Enregistrement…' : paiementEditId() ? 'Enregistrer' : 'Enregistrer le paiement' }}
                    </button>
                    @if (paiementEditId()) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="resetPaiement()">Annuler</button>
                    }
                  </div>
                </form>
              }
              <div class="bea-mg__table-scroll bea-ct-table-wrap">
                <table class="bea-mg__table bea-ct-table">
                  <thead><tr><th>N° pièce</th><th>Prévu le</th><th>Payé le</th><th class="is-num">Prévu</th><th class="is-num">Versé</th><th class="is-num">Écart</th><th>Mode</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
                  <tbody>
                    @for (p of c.paiements || []; track p.id) {
                      <tr class="bea-ct-row">
                        <td><code class="bea-mg__code">{{ p.reference || '—' }}</code></td>
                        <td class="is-nowrap">{{ date(p.date_prevue) }}</td>
                        <td class="is-nowrap">{{ date(p.date_reelle) }}</td>
                        <td class="is-num is-nowrap">{{ p.montant_prevu | montant }}</td>
                        <td class="is-num is-nowrap"><strong>{{ p.montant_paye | montant }}</strong></td>
                        <td class="is-num is-nowrap" [class.bea-ct-neg]="ecart(p) < 0">{{ ecart(p) | montant }}</td>
                        <td>{{ p.mode || '—' }}</td>
                        <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statut(p.statut) }}</span></td>
                        <td class="bea-mg__actions-cell">
                          @if (modifiable()) {
                            <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editerPaiement(p)"><mat-icon>edit</mat-icon></button>
                            <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerPaiement(p)"><mat-icon>delete</mat-icon></button>
                          }
                        </td>
                      </tr>
                    } @empty {
                      <tr><td colspan="9"><div class="bea-ct-empty"><mat-icon>payments</mat-icon><p>Aucun paiement enregistré.</p></div></td></tr>
                    }
                  </tbody>
                </table>
              </div>
            </div>
          }

          @if (onglet() === 'avenants') {
            <div class="bea-ct-pane">
              @if (avenantOuvert()) {
                <form class="bea-ct-avenant" [formGroup]="avenantForm" (ngSubmit)="sauverAvenant(c)">
                  <h3><mat-icon>post_add</mat-icon> Avenant n°{{ (c.avenants || []).length + 1 }}</h3>
                  <div class="bea-ct-grid">
                    <label class="bea-ct-span2">Objet de l’avenant * <input formControlName="objet" maxlength="255" placeholder="Ex. : révision tarifaire 2027" /></label>
                    <label>Date d’effet * <input type="date" formControlName="date_effet" /></label>
                    <label>Nouveau montant HT <input type="number" min="0" step="0.01" formControlName="nouveau_montant_ht" [placeholder]="'Actuel : ' + (c.montant_ht ?? '—')" /></label>
                    <label>Nouvelle TVA (%) <input type="number" min="0" max="100" step="0.01" formControlName="nouveau_taux_tva" [placeholder]="'Actuelle : ' + (c.taux_tva ?? '—')" /></label>
                    <label>Nouvelle date de fin <input type="date" formControlName="nouvelle_date_fin" /></label>
                    <label class="bea-ct-span2">Clauses modifiées <textarea formControlName="clauses" rows="3" placeholder="Texte des clauses ajoutées ou modifiées"></textarea></label>
                    <label class="bea-ct-check bea-ct-span2"><input type="checkbox" formControlName="regenerer_echeancier" /> Régénérer les échéances non réglées selon les nouvelles conditions</label>
                  </div>
                  <div class="bea-ct-inline__btns">
                    <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="avenantForm.invalid || actionEnCours()"><mat-icon>save</mat-icon> Enregistrer l’avenant</button>
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="avenantOuvert.set(false)">Fermer</button>
                  </div>
                </form>
              } @else if (cap().manage && (c.statut === 'ACTIF' || c.statut === 'SUSPENDU' || c.statut === 'EXPIRE')) {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirAvenant()"><mat-icon>post_add</mat-icon> Nouvel avenant</button>
              }
              <ol class="bea-ct-timeline">
                @for (a of (c.avenants || []).slice().reverse(); track a.id) {
                  <li>
                    <div class="bea-ct-timeline__dot">{{ a.numero }}</div>
                    <div class="bea-ct-timeline__body">
                      <p><strong>{{ a.objet }}</strong> <span class="bea-ct-badge" data-tone="INFO">{{ typeAvenant(a.type_avenant) }}</span> <small>v{{ a.version_contrat }}</small></p>
                      <p class="bea-ct-timeline__meta">Effet le {{ date(a.date_effet) }} · {{ a.user_nom || '—' }} · {{ dateHeure(a.created_at) }}</p>
                      <ul class="bea-ct-diff">
                        @if (num(a.montant_ttc_avant) !== num(a.montant_ttc_apres)) {
                          <li>Montant TTC : <s>{{ a.montant_ttc_avant | montant }}</s> → <strong>{{ a.montant_ttc_apres | montant }}</strong></li>
                        }
                        @if (a.date_fin_avant !== a.date_fin_apres) {
                          <li>Date de fin : <s>{{ date(a.date_fin_avant) }}</s> → <strong>{{ date(a.date_fin_apres) }}</strong></li>
                        }
                        @if (a.clauses) { <li class="bea-ct-diff__clauses">{{ a.clauses }}</li> }
                      </ul>
                    </div>
                  </li>
                } @empty {
                  <li class="bea-ct-timeline__empty">Aucun avenant : le contrat est dans sa version initiale.</li>
                }
              </ol>
            </div>
          }

          @if (onglet() === 'factures') {
            <div class="bea-ct-pane">
              @if (facturesErreur(); as err) {
                <p class="bea-ct-help"><mat-icon>lock</mat-icon> {{ err }}</p>
              } @else if (factures(); as fx) {
                <p class="bea-ct-note">{{ fx.nb }} facture(s) comptabilisée(s) · total {{ fx.total | montant }} · reste à payer {{ fx.reste | montant }}</p>
                <ul class="bea-ct-dash__list">
                  @for (r of fx.items; track r.id) {
                    <li>
                      <a [routerLink]="'/contrats-echeances/factures/liste'" [queryParams]="{ facture: r.id }">
                        <span class="bea-ct-dash__date"><strong>{{ r.periode_label || date(r.date_facture) }}</strong><small>{{ r.reference }}</small></span>
                        <span class="bea-ct-dash__main">{{ r.point_nom || r.numero_fournisseur || '—' }}</span>
                        <span class="bea-ct-dash__amount">{{ r.montant_a_payer === null ? '—' : (r.montant_a_payer | montant) }}</span>
                        <span class="bea-ct-badge" [attr.data-tone]="factureTone(r.statut_affiche)">{{ factureStatut(r.statut_affiche) }}</span>
                      </a>
                    </li>
                  } @empty { <li class="bea-ct-dash__none">Aucune facture rattachée à ce contrat.</li> }
                </ul>
              } @else {
                <p class="bea-ct-note">Chargement des factures…</p>
              }
            </div>
          }

          @if (onglet() === 'documents') {
            <div class="bea-ct-pane">
              <bea-contrats-documents
                [contratId]="c.id"
                [reference]="c.reference"
                [lectureSeule]="!cap().ged_write || verrouille(c.statut)"
                [typesDocument]="config()?.types_document ?? []"
                [tailleMaxMo]="config()?.ged_taille_max_mo ?? 15"
              />
            </div>
          }

          @if (onglet() === 'historique') {
            <div class="bea-ct-pane">
              <ol class="bea-ct-timeline">
                @for (h of c.historique || []; track h.id) {
                  <li>
                    <div class="bea-ct-timeline__dot bea-ct-timeline__dot--sm"><mat-icon>bolt</mat-icon></div>
                    <div class="bea-ct-timeline__body">
                      <p>
                        <strong>{{ actionLabel(h.action) }}</strong>
                        @if (h.to_statut && h.from_statut !== h.to_statut) { <span class="bea-ct-badge" [attr.data-tone]="h.to_statut">{{ statut(h.to_statut) }}</span> }
                      </p>
                      <p class="bea-ct-timeline__meta">{{ h.user_nom || 'Système' }} · {{ dateHeure(h.created_at) }}</p>
                      @if (h.commentaire) { <p class="bea-ct-timeline__comment">{{ h.commentaire }}</p> }
                    </div>
                  </li>
                } @empty {
                  <li class="bea-ct-timeline__empty">Aucun historique.</li>
                }
              </ol>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class ContratsFicheComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(() => this.form.dirty && !this.saving(), () => this.form);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly dialogs = inject(UiDialogService);
  private readonly destroyRef = inject(DestroyRef);

  readonly etapes = [
    { code: 'BROUILLON', label: 'Brouillon' },
    { code: 'EN_VALIDATION', label: 'Validation' },
    { code: 'ACTIF', label: 'En vigueur' },
    { code: 'FIN', label: 'Terme / archive' },
  ];
  readonly typesEcheance = TYPES_ECHEANCE;
  readonly periodicites = ['MENSUEL', 'TRIMESTRIEL', 'SEMESTRIEL', 'ANNUEL', 'UNIQUE'];
  readonly reconductions = ['AUCUNE', 'TACITE', 'EXPRESSE'];
  readonly num = num;

  readonly config = signal<ContratsConfig | null>(null);
  readonly fiche = signal<Contrat | null>(null);
  readonly types = signal<Array<{ code: string; libelle: string; actif: boolean }>>([]);
  readonly fournisseurs = signal<RefItem[]>([]);
  readonly agences = signal<RefItem[]>([]);
  readonly responsables = signal<RefItem[]>([]);
  readonly modesPaiement = signal<string[]>(['Espèces', 'Virement', 'Amanty', 'Chèque', 'Carte', 'Prélèvement']);
  readonly simulation = signal<Simulation | null>(null);
  readonly saving = signal(false);
  readonly actionEnCours = signal(false);
  readonly telechargement = signal(false);
  readonly echeanceBusy = signal(false);
  readonly paiementBusy = signal(false);
  readonly fieldErrors = signal<Record<string, string>>({});
  readonly onglet = signal<Onglet>('echeances');
  readonly factures = signal<FacturesContrat | null>(null);
  readonly facturesErreur = signal<string | null>(null);
  private facturesContrat: string | null = null;
  readonly echeanceEditId = signal<string | null>(null);
  readonly paiementEditId = signal<string | null>(null);
  readonly avenantOuvert = signal(false);

  readonly cap = computed(
    () => this.config()?.capacites ?? { create: false, manage: false, validate: false, settings: false, export: false, ged_write: false },
  );
  readonly typesActifs = computed(() => {
    const courant = this.form.controls.type_contrat.value;
    return this.types().filter((t) => t.actif || t.code === courant);
  });
  readonly modifiable = computed(() => {
    const c = this.fiche();
    return !!c && this.cap().manage && !VERROUILLE.has(c.statut);
  });
  readonly financierModifiable = computed(() => {
    const c = this.fiche();
    return !c || EDITION_LIBRE.has(c.statut);
  });
  readonly peutEnregistrer = computed(() => {
    const c = this.fiche();
    return c ? this.cap().manage && !VERROUILLE.has(c.statut) : this.cap().create;
  });
  readonly totaux = computed(() => {
    const ech = (this.fiche()?.echeances ?? []).filter((e) => e.type_echeance === 'PAIEMENT' && e.statut !== 'ANNULEE');
    const prevu = ech.reduce((s, e) => s + num(e.montant), 0);
    const paye = ech.reduce((s, e) => s + num(e.montant_paye), 0);
    return { prevu, paye, reste: Math.max(prevu - paye, 0) };
  });
  readonly ecartEcheancier = computed(() => {
    const c = this.fiche();
    if (!c || !this.totaux().prevu) return 0;
    return Math.round((this.totaux().prevu - num(c.montant)) * 100) / 100;
  });
  readonly aEcheancier = computed(() => (this.fiche()?.echeances ?? []).some((e) => e.type_echeance === 'PAIEMENT' && e.statut !== 'ANNULEE'));
  readonly echeancesPaiement = computed(() =>
    (this.fiche()?.echeances ?? []).filter(
      (e) => e.type_echeance === 'PAIEMENT' && e.statut !== 'ANNULEE' && (this.resteEcheance(e) > 0 || this.paiementForm.controls.echeance_id.value === e.id),
    ),
  );
  readonly refPaiementVisible = signal(false);

  readonly form = this.fb.nonNullable.group({
    titre: ['', [Validators.required, Validators.maxLength(255)]],
    numero_contrat: [''],
    description: [''],
    type_contrat: ['AUTRE'],
    devise: ['MRU'],
    fournisseur_id: [''],
    agence_id: [''],
    responsable_id: [''],
    date_signature: [''],
    date_debut: ['', Validators.required],
    date_fin: [''],
    montant_ht: [null as number | null, Validators.min(0)],
    taux_tva: [0, [Validators.min(0), Validators.max(100)]],
    periodicite: ['ANNUEL'],
    mode_paiement: [''],
    ref_paiement: [''],
    alerte_jours: [30, [Validators.min(0), Validators.max(730)]],
    reconduction: ['AUCUNE'],
    preavis_jours: [null as number | null, Validators.min(0)],
    observation: [''],
  });
  readonly echeanceForm = this.fb.nonNullable.group({
    type_echeance: ['PAIEMENT'],
    date_prevue: ['', Validators.required],
    montant: [null as number | null, Validators.min(0)],
    statut: [''],
    commentaire: [''],
  });
  readonly paiementForm = this.fb.nonNullable.group({
    echeance_id: [''],
    reference: [''],
    date_prevue: [''],
    date_reelle: [aujourdhui()],
    montant_prevu: [null as number | null, Validators.min(0)],
    montant_paye: [0, [Validators.required, Validators.min(0)]],
    mode: [''],
    commentaire: [''],
  });
  readonly avenantForm = this.fb.nonNullable.group({
    objet: ['', Validators.required],
    date_effet: [aujourdhui(), Validators.required],
    nouveau_montant_ht: [null as number | null, Validators.min(0)],
    nouveau_taux_tva: [null as number | null, [Validators.min(0), Validators.max(100)]],
    nouvelle_date_fin: [''],
    clauses: [''],
    regenerer_echeancier: [true],
  });

  ngOnInit(): void {
    this.loadRefs();
    this.form.valueChanges
      .pipe(
        map(() => this.form.getRawValue()),
        debounceTime(400),
        switchMap((v) =>
          v.date_debut
            ? this.api
                .post<Simulation>('/mg/contrats/echeancier/simuler', {
                  date_debut: v.date_debut,
                  date_fin: v.date_fin || null,
                  periodicite: v.periodicite,
                  montant_ht: v.montant_ht,
                  taux_tva: v.taux_tva,
                })
                .pipe(catchError(() => of(null)))
            : of(null),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((s) => this.simulation.set(s));
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((pm) => {
      const id = pm.get('id');
      this.fieldErrors.set({});
      this.resetEcheance();
      this.resetPaiement();
      this.avenantOuvert.set(false);
      if (id) {
        this.loadOne(id);
      } else {
        this.fiche.set(null);
        this.form.enable({ emitEvent: false });
        this.form.reset({
          titre: '', numero_contrat: '', description: '', type_contrat: 'AUTRE', devise: 'MRU',
          fournisseur_id: '', agence_id: '', responsable_id: '', date_signature: '',
          date_debut: aujourdhui(), date_fin: '', montant_ht: null, taux_tva: this.config()?.taux_tva ?? 16,
          periodicite: 'ANNUEL', mode_paiement: '', ref_paiement: '', alerte_jours: 30,
          reconduction: 'AUCUNE', preavis_jours: null, observation: '',
        });
        this.refPaiementVisible.set(false);
      }
    });
  }

  private loadRefs(): void {
    this.api.get<ContratsConfig>('/mg/contrats/config').subscribe({
      next: (cfg) => {
        this.config.set(cfg);
        this.modesPaiement.set(cfg.modes_paiement);
        if (!this.fiche() && !this.form.controls.taux_tva.dirty) {
          this.form.controls.taux_tva.setValue(cfg.taux_tva);
          this.form.markAsPristine();
        }
        this.appliquerVerrous();
      },
      error: (e) => this.fail(e, 'Configuration indisponible'),
    });
    this.api.get<Array<{ code: string; libelle: string; actif: boolean }>>('/mg/contrats/types').subscribe({ next: (r) => this.types.set(r), error: () => undefined });
    this.api.get<RefItem[]>('/mg/contrats/fournisseurs').subscribe({ next: (r) => this.fournisseurs.set(r), error: () => undefined });
    this.api.get<RefItem[]>('/mg/contrats/agences').subscribe({ next: (r) => this.agences.set(r), error: () => undefined });
    this.api.get<RefItem[]>('/mg/contrats/responsables').subscribe({ next: (r) => this.responsables.set(r), error: () => undefined });
  }

  private loadOne(id: string): void {
    this.api.get<Contrat>(`/mg/contrats/${id}`).subscribe({
      next: (c) => this.appliquer(c),
      error: (e) => this.fail(e, 'Contrat introuvable'),
    });
  }

  private appliquer(c: Contrat): void {
    this.fiche.set(c);
    const mode = c.mode_paiement ?? '';
    const modes = this.config()?.modes_paiement ?? this.modesPaiement();
    this.modesPaiement.set(mode && !modes.includes(mode) ? [...modes, mode] : modes);
    this.form.reset(
      {
        titre: c.titre,
        numero_contrat: c.numero_contrat ?? '',
        description: c.description ?? '',
        type_contrat: c.type_contrat || 'AUTRE',
        devise: c.devise || 'MRU',
        fournisseur_id: c.fournisseur_id ?? '',
        agence_id: c.agence_id ?? '',
        responsable_id: c.responsable_id ?? '',
        date_signature: c.date_signature ?? '',
        date_debut: c.date_debut,
        date_fin: c.date_fin ?? '',
        montant_ht: c.montant_ht === null ? null : num(c.montant_ht),
        taux_tva: num(c.taux_tva),
        periodicite: c.periodicite || 'ANNUEL',
        mode_paiement: mode,
        ref_paiement: c.ref_paiement ?? '',
        alerte_jours: c.alerte_jours ?? 30,
        reconduction: c.reconduction || 'AUCUNE',
        preavis_jours: c.preavis_jours,
        observation: c.observation ?? '',
      },
      { emitEvent: true },
    );
    this.refPaiementVisible.set(MODES_AVEC_REF.has(mode));
    this.appliquerVerrous();
  }

  private appliquerVerrous(): void {
    const c = this.fiche();
    if (!this.config()) return;
    if (!this.peutEnregistrer()) {
      this.form.disable({ emitEvent: false });
      return;
    }
    this.form.enable({ emitEvent: false });
    if (c && !EDITION_LIBRE.has(c.statut)) {
      for (const f of CHAMPS_FINANCIERS) this.form.controls[f].disable({ emitEvent: false });
    }
  }

  onModePaiement(): void {
    const visible = MODES_AVEC_REF.has(this.form.controls.mode_paiement.value);
    this.refPaiementVisible.set(visible);
    if (!visible) this.form.controls.ref_paiement.setValue('');
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.feedback.warning({ title: 'Formulaire incomplet', message: 'Renseignez au minimum l’objet et la date de début.' });
      return;
    }
    this.fieldErrors.set({});
    const raw = this.form.getRawValue();
    const c = this.fiche();
    const body: Record<string, unknown> = {
      ...raw,
      fournisseur_id: raw.fournisseur_id || null,
      agence_id: raw.agence_id || null,
      responsable_id: raw.responsable_id || null,
      date_signature: raw.date_signature || null,
      date_fin: raw.date_fin || null,
      numero_contrat: raw.numero_contrat || null,
      description: raw.description || null,
      mode_paiement: raw.mode_paiement || null,
      ref_paiement: MODES_AVEC_REF.has(raw.mode_paiement) ? raw.ref_paiement.trim() || null : null,
      observation: raw.observation || null,
    };
    if (c && !EDITION_LIBRE.has(c.statut)) {
      for (const f of CHAMPS_FINANCIERS) delete body[f];
    }
    this.feedback
      .run(() => (c ? this.api.patch<Contrat>(`/mg/contrats/${c.id}`, body) : this.api.post<Contrat>('/mg/contrats', body)), {
        loading: 'Enregistrement du contrat…',
        busy: this.saving,
        idempotent: !c,
        errorTitle: 'Échec de l’enregistrement',
        errorHint: 'Vos données saisies ont été conservées.',
        onError: (e) => this.fieldErrors.set(e.fieldErrors),
        success: (r) => ({
          title: c ? 'Contrat mis à jour' : 'Contrat créé en brouillon',
          details: [
            { label: 'Référence', value: r.reference },
            { label: 'Montant TTC', value: `${num(r.montant).toLocaleString('fr-FR', { minimumFractionDigits: 2 })} ${r.devise}` },
            { label: 'Statut', value: statutLabel(r.statut) },
          ],
        }),
      })
      .subscribe((r) => {
        this.form.markAsPristine();
        if (c) this.appliquer(r);
        else void this.router.navigateByUrl(`/contrats-echeances/${r.id}`);
      });
  }

  transition(action: TransitionAction): void {
    const c = this.fiche();
    if (!c) return;
    const cfg = TRANSITIONS[action];
    this.feedback
      .run(() => this.api.post<Contrat>(`/mg/contrats/${c.id}/transition`, { action, commentaire: null }), {
        confirm: { action: cfg.preset, message: `${cfg.question} ${c.reference} « ${c.titre} » ?`, hint: cfg.hint },
        loading: cfg.loading,
        busy: this.actionEnCours,
        errorTitle: cfg.errorTitle,
        success: (res) => this.succesStatut(res, cfg.success),
      })
      .subscribe((res) => this.appliquer(res));
  }

  demanderMotif(action: 'annuler' | 'rejeter'): void {
    const c = this.fiche();
    if (!c) return;
    const rejet = action === 'rejeter';
    this.feedback
      .runWithReason((motif) => this.api.post<Contrat>(`/mg/contrats/${c.id}/transition`, { action, commentaire: motif }), {
        reason: {
          ...this.dialogs.preset(
            rejet ? 'rejet' : 'annulation',
            rejet ? `Rejeter le contrat ${c.reference} « ${c.titre} » ?` : `Annuler / résilier le contrat ${c.reference} « ${c.titre} » ?`,
            rejet ? 'Rejeter le contrat' : 'Annuler le contrat',
            rejet ? 'Le responsable est notifié du rejet et de son motif.' : 'Le contrat passera en lecture seule. Action définitive.',
          ),
          confirmLabel: rejet ? 'Rejeter' : 'Annuler le contrat',
          cancelLabel: 'Retour',
          reasonLabel: rejet ? 'Motif du rejet' : 'Motif de l’annulation / résiliation',
        },
        loading: rejet ? 'Rejet en cours…' : 'Annulation en cours…',
        busy: this.actionEnCours,
        errorTitle: rejet ? 'Échec du rejet' : 'Échec de l’annulation',
        success: (res) => this.succesStatut(res, rejet ? 'Contrat rejeté' : 'Contrat annulé'),
      })
      .subscribe((res) => this.appliquer(res));
  }

  reconduire(): void {
    const c = this.fiche();
    if (!c) return;
    this.feedback
      .run(() => this.api.post<Contrat>(`/mg/contrats/${c.id}/reconduire`, {}), {
        confirm: {
          action: 'renouvellement',
          title: 'Reconduction tacite',
          message: `Reconduire ${c.reference} pour une période identique à compter du lendemain du ${dateFr(c.date_fin)} ?`,
          hint: 'Le même contrat est prolongé (avenant de reconduction tracé) et son échéancier complété pour la nouvelle période.',
        },
        loading: 'Reconduction…',
        busy: this.actionEnCours,
        idempotent: true,
        errorTitle: 'Échec de la reconduction',
        success: (r) => ({
          title: 'Contrat reconduit',
          details: [
            { label: 'Nouvelle fin', value: dateFr(r.date_fin) },
            { label: 'Version', value: String(r.version) },
          ],
        }),
      })
      .subscribe((r) => this.appliquer(r));
  }

  renouveler(): void {
    const c = this.fiche();
    if (!c) return;
    this.feedback
      .run(() => this.api.post<Contrat>(`/mg/contrats/${c.id}/renouveler`, {}), {
        confirm: {
          action: 'renouvellement',
          title: 'Reconduction expresse',
          message: `Préparer un nouveau contrat à partir de ${c.reference} ?`,
          hint: 'Un nouveau contrat en brouillon est créé (période suivante) ; il suit le circuit de validation.',
        },
        loading: 'Préparation du renouvellement…',
        busy: this.actionEnCours,
        idempotent: true,
        errorTitle: 'Échec du renouvellement',
        success: (n) => ({
          title: 'Renouvellement préparé',
          message: 'Vérifiez le nouveau contrat puis soumettez-le.',
          details: [
            { label: 'Nouvelle référence', value: n.reference },
            { label: 'Issu de', value: c.reference },
          ],
        }),
      })
      .subscribe((n) => void this.router.navigateByUrl(`/contrats-echeances/${n.id}`));
  }

  supprimer(c: Contrat): void {
    this.feedback
      .run(() => this.api.delete(`/mg/contrats/${c.id}`), {
        confirm: { action: 'suppression', message: `Retirer ${c.reference} « ${c.titre} » du registre ?`, hint: 'L’historique reste conservé en base (audit).' },
        loading: 'Suppression…',
        busy: this.actionEnCours,
        errorTitle: 'Échec de la suppression',
        success: { title: 'Contrat retiré du registre', details: [{ label: 'Référence', value: c.reference }] },
      })
      .subscribe(() => {
        this.form.markAsPristine();
        void this.router.navigateByUrl('/contrats-echeances/liste');
      });
  }

  genererEcheancier(c: Contrat): void {
    const remplacer = this.aEcheancier();
    this.feedback
      .run(() => this.api.post<Contrat>(`/mg/contrats/${c.id}/echeancier`, { remplacer }), {
        confirm: {
          action: remplacer ? 'modification' : 'ajout',
          title: remplacer ? 'Régénérer l’échéancier' : 'Générer l’échéancier',
          message: remplacer
            ? 'Remplacer les échéances de paiement non réglées par un nouveau calcul ?'
            : `Calculer les échéances ${this.periodicite(c.periodicite).toLowerCase()}s sur ${num(c.montant).toLocaleString('fr-FR')} ${c.devise} TTC ?`,
          hint: remplacer ? 'Les échéances déjà réglées (même partiellement) sont conservées ; le reste à payer est réparti.' : 'Calcul effectué par le serveur.',
        },
        loading: 'Calcul de l’échéancier…',
        busy: this.actionEnCours,
        errorTitle: 'Échéancier non généré',
        success: (r) => ({
          title: remplacer ? 'Échéancier régénéré' : 'Échéancier généré',
          details: [{ label: 'Échéances de paiement', value: String((r.echeances ?? []).filter((e) => e.type_echeance === 'PAIEMENT').length) }],
        }),
      })
      .subscribe((r) => this.appliquer(r));
  }

  sauverEcheance(): void {
    const c = this.fiche();
    if (!c || this.echeanceForm.invalid) return;
    const raw = this.echeanceForm.getRawValue();
    const body = { ...raw, montant: raw.montant, commentaire: raw.commentaire || null };
    const editId = this.echeanceEditId();
    this.feedback
      .run(
        () => (editId ? this.api.patch(`/mg/contrats/echeances/${editId}`, body) : this.api.post<Contrat>(`/mg/contrats/${c.id}/echeances`, body)),
        {
          loading: 'Enregistrement de l’échéance…',
          busy: this.echeanceBusy,
          idempotent: !editId,
          errorTitle: 'Échec de l’enregistrement',
          errorHint: 'Vos données saisies ont été conservées.',
          success: {
            title: editId ? 'Échéance mise à jour' : 'Échéance ajoutée',
            details: [
              { label: 'Type', value: typeEcheanceLabel(raw.type_echeance) },
              { label: 'Date', value: dateFr(raw.date_prevue) },
            ],
          },
        },
      )
      .subscribe(() => {
        this.resetEcheance();
        this.loadOne(c.id);
      });
  }

  editerEcheance(e: Echeance): void {
    this.echeanceEditId.set(e.id);
    this.echeanceForm.reset({
      type_echeance: e.type_echeance,
      date_prevue: e.date_prevue,
      montant: e.montant === null ? null : num(e.montant),
      statut: e.statut === 'FAITE' || e.statut === 'ANNULEE' ? e.statut : '',
      commentaire: e.commentaire ?? '',
    });
  }

  resetEcheance(): void {
    this.echeanceEditId.set(null);
    this.echeanceForm.reset({ type_echeance: 'PAIEMENT', date_prevue: '', montant: null, statut: '', commentaire: '' });
  }

  supprimerEcheance(e: Echeance): void {
    const c = this.fiche();
    if (!c) return;
    this.feedback
      .run(() => this.api.delete(`/mg/contrats/echeances/${e.id}`), {
        confirm: {
          action: 'suppression',
          message: `Supprimer l’échéance « ${typeEcheanceLabel(e.type_echeance)} » du ${dateFr(e.date_prevue)} ?`,
          hint: 'Impossible si des paiements y sont rattachés.',
        },
        loading: 'Suppression…',
        busy: this.echeanceBusy,
        errorTitle: 'Échec de la suppression',
        success: { title: 'Échéance supprimée' },
      })
      .subscribe(() => this.loadOne(c.id));
  }

  regler(e: Echeance): void {
    this.onglet.set('paiements');
    this.paiementEditId.set(null);
    const reste = this.resteEcheance(e);
    this.paiementForm.reset({
      echeance_id: e.id,
      reference: '',
      date_prevue: e.date_prevue,
      date_reelle: aujourdhui(),
      montant_prevu: reste,
      montant_paye: reste,
      mode: this.fiche()?.mode_paiement ?? '',
      commentaire: '',
    });
  }

  onEcheancePaiement(): void {
    const id = this.paiementForm.controls.echeance_id.value;
    const e = (this.fiche()?.echeances ?? []).find((x) => x.id === id);
    if (!e) return;
    const reste = this.resteEcheance(e);
    this.paiementForm.patchValue({ date_prevue: e.date_prevue, montant_prevu: reste, montant_paye: reste });
  }

  sauverPaiement(): void {
    const c = this.fiche();
    if (!c || this.paiementForm.invalid) return;
    const raw = this.paiementForm.getRawValue();
    const body = {
      echeance_id: raw.echeance_id || null,
      reference: raw.reference.trim() || null,
      date_prevue: raw.date_prevue || null,
      date_reelle: raw.date_reelle || null,
      montant_prevu: raw.montant_prevu,
      montant_paye: raw.montant_paye ?? 0,
      mode: raw.mode || null,
      commentaire: raw.commentaire || null,
    };
    const editId = this.paiementEditId();
    this.feedback
      .run(
        () => (editId ? this.api.patch<Contrat>(`/mg/contrats/paiements/${editId}`, body) : this.api.post<Contrat>(`/mg/contrats/${c.id}/paiements`, body)),
        {
          loading: 'Enregistrement du paiement…',
          busy: this.paiementBusy,
          idempotent: !editId,
          errorTitle: 'Paiement refusé',
          errorHint: 'Vos données saisies ont été conservées.',
          success: (r) => ({
            title: editId ? 'Paiement mis à jour' : 'Paiement enregistré',
            details: [
              { label: 'N° pièce', value: body.reference ?? '—' },
              { label: 'Montant versé', value: `${num(body.montant_paye).toLocaleString('fr-FR', { minimumFractionDigits: 2 })} ${r.devise}` },
            ],
          }),
        },
      )
      .subscribe((r) => {
        this.resetPaiement();
        this.appliquer(r);
      });
  }

  editerPaiement(p: Paiement): void {
    this.paiementEditId.set(p.id);
    this.paiementForm.reset({
      echeance_id: p.echeance_id ?? '',
      reference: p.reference ?? '',
      date_prevue: p.date_prevue,
      date_reelle: p.date_reelle ?? '',
      montant_prevu: num(p.montant_prevu),
      montant_paye: num(p.montant_paye),
      mode: p.mode ?? '',
      commentaire: p.commentaire ?? '',
    });
  }

  resetPaiement(): void {
    this.paiementEditId.set(null);
    this.paiementForm.reset({
      echeance_id: '', reference: '', date_prevue: '', date_reelle: aujourdhui(),
      montant_prevu: null, montant_paye: 0, mode: '', commentaire: '',
    });
  }

  supprimerPaiement(p: Paiement): void {
    this.feedback
      .run(() => this.api.delete<Contrat>(`/mg/contrats/paiements/${p.id}`), {
        confirm: {
          action: 'suppression',
          message: `Supprimer le paiement ${p.reference || 'sans référence'} du ${dateFr(p.date_reelle || p.date_prevue)} ?`,
          hint: 'L’échéance rattachée repasse en « à payer » ; l’opération est tracée.',
        },
        loading: 'Suppression…',
        busy: this.paiementBusy,
        errorTitle: 'Échec de la suppression',
        success: { title: 'Paiement supprimé' },
      })
      .subscribe((r) => this.appliquer(r));
  }

  ouvrirAvenant(): void {
    const c = this.fiche();
    this.onglet.set('avenants');
    this.avenantForm.reset({
      objet: '',
      date_effet: aujourdhui(),
      nouveau_montant_ht: null,
      nouveau_taux_tva: null,
      nouvelle_date_fin: c?.date_fin ?? '',
      clauses: '',
      regenerer_echeancier: true,
    });
    this.avenantOuvert.set(true);
  }

  sauverAvenant(c: Contrat): void {
    if (this.avenantForm.invalid) return;
    const raw = this.avenantForm.getRawValue();
    const body = {
      objet: raw.objet.trim(),
      date_effet: raw.date_effet,
      nouveau_montant_ht: raw.nouveau_montant_ht,
      nouveau_taux_tva: raw.nouveau_taux_tva,
      nouvelle_date_fin: raw.nouvelle_date_fin && raw.nouvelle_date_fin !== c.date_fin ? raw.nouvelle_date_fin : null,
      clauses: raw.clauses.trim() || null,
      regenerer_echeancier: raw.regenerer_echeancier,
    };
    this.feedback
      .run(() => this.api.post<Contrat>(`/mg/contrats/${c.id}/avenants`, body), {
        confirm: {
          action: 'modification',
          title: 'Enregistrer l’avenant',
          message: `Appliquer l’avenant « ${body.objet} » au contrat ${c.reference} ?`,
          hint: 'Le contrat passe en version ' + (c.version + 1) + ' ; les valeurs précédentes restent dans l’historique.',
        },
        loading: 'Enregistrement de l’avenant…',
        busy: this.actionEnCours,
        idempotent: true,
        errorTitle: 'Avenant refusé',
        errorHint: 'Vos données saisies ont été conservées.',
        success: (r) => ({
          title: 'Avenant enregistré',
          details: [
            { label: 'Version', value: String(r.version) },
            { label: 'Montant TTC', value: `${num(r.montant).toLocaleString('fr-FR', { minimumFractionDigits: 2 })} ${r.devise}` },
            { label: 'Fin', value: dateFr(r.date_fin) },
          ],
        }),
      })
      .subscribe((r) => {
        this.avenantOuvert.set(false);
        this.appliquer(r);
      });
  }

  telechargerPdf(c: Contrat): void {
    this.feedback
      .run(() => this.api.download(`/mg/contrats/${c.id}/pdf`), {
        loading: 'Préparation du PDF…',
        busy: this.telechargement,
        errorTitle: 'Téléchargement impossible',
        success: (blob) => {
          telechargerBlob(blob, `Contrat-${c.reference}.pdf`);
          return { title: 'Téléchargement prêt', details: [{ label: 'Fichier', value: `Contrat-${c.reference}.pdf` }] };
        },
      })
      .subscribe();
  }

  private succesStatut(c: Contrat, title: string): FeedbackMessage {
    const details = [
      { label: 'Contrat', value: c.reference },
      { label: 'Statut', value: statutLabel(c.statut) },
    ];
    const n = (c.echeances ?? []).filter((e) => e.type_echeance === 'PAIEMENT').length;
    if (c.statut === 'ACTIF' && n) details.push({ label: 'Échéances', value: String(n) });
    return { title, message: this.aide(c.statut), details };
  }

  resteEcheance(e: Echeance): number {
    if (e.statut === 'PAYEE' || e.statut === 'FAITE' || e.statut === 'ANNULEE' || e.montant === null) return 0;
    return Math.max(Math.round((num(e.montant) - num(e.montant_paye)) * 100) / 100, 0);
  }

  ecart(p: Paiement): number {
    return Math.round((num(p.montant_paye) - num(p.montant_prevu)) * 100) / 100;
  }

  erreurChamp(name: string): string | null {
    return this.fieldErrors()[name] ?? null;
  }

  edition(statut: string): boolean {
    return EDITION_LIBRE.has(statut);
  }

  verrouille(statut: string): boolean {
    return VERROUILLE.has(statut);
  }

  etapeIndex(statut: string): number {
    if (EDITION_LIBRE.has(statut)) return statut === 'REJETE' ? 1 : 0;
    if (statut === 'EN_VALIDATION') return 1;
    if (statut === 'ACTIF' || statut === 'SUSPENDU') return 2;
    return 3;
  }

  aide(statut: string): string {
    return STATUT_AIDE[statut] ?? '';
  }

  ouvrirFactures(contratId: string): void {
    this.onglet.set('factures');
    if (this.facturesContrat === contratId && (this.factures() || this.facturesErreur())) return;
    this.facturesContrat = contratId;
    this.factures.set(null);
    this.facturesErreur.set(null);
    this.api.get<FacturesContrat>(`/mg/factures/contrats/${contratId}`).subscribe({
      next: (r) => this.factures.set(r),
      error: (e: { status?: number }) =>
        this.facturesErreur.set(e?.status === 403 ? 'Vous n’avez pas accès à la gestion des factures.' : 'Factures indisponibles pour le moment.'),
    });
  }

  factureStatut(code: string): string {
    return fxStatut(code);
  }

  factureTone(code: string): string {
    return fxTone(code);
  }

  statut(code: string | null | undefined): string {
    return statutLabel(code);
  }

  typeEcheance(code: string): string {
    return typeEcheanceLabel(code);
  }

  typeAvenant(code: string): string {
    return TYPE_AVENANT_LABELS[code] ?? code;
  }

  periodicite(code: string): string {
    return PERIODICITE_LABELS[code] ?? code;
  }

  reconduction(code: string): string {
    return RECONDUCTION_LABELS[code] ?? code;
  }

  actionLabel(code: string): string {
    return ACTION_LABELS[code] ?? code;
  }

  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }

  dateHeure(iso: string): string {
    return dateHeureFr(iso);
  }

  jours(n: number | null | undefined): string {
    return joursLabel(n);
  }

  private fail(err: unknown, title: string): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, title));
  }
}
