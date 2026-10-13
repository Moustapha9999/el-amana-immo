import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import {
  Dossier,
  Evenement,
  LigneAudit,
  dateFr,
  depuisSaisieLocale,
  maintenantLocal,
  toneStatut,
  tonePriorite,
  versSaisieLocale,
} from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcPiecesComponent } from '../shared/rc-pieces.component';

type Onglet = 'general' | 'reception' | 'traitement' | 'chronologie' | 'documents' | 'reponse' | 'delais' | 'audit';

const ONGLETS: ReadonlyArray<{ code: Onglet; libelle: string; icone: string }> = [
  { code: 'general', libelle: 'Général', icone: 'info' },
  { code: 'reception', libelle: 'Réception', icone: 'move_to_inbox' },
  { code: 'traitement', libelle: 'Traitement', icone: 'engineering' },
  { code: 'chronologie', libelle: 'Chronologie', icone: 'timeline' },
  { code: 'documents', libelle: 'Documents', icone: 'folder' },
  { code: 'reponse', libelle: 'Réponse client', icone: 'outgoing_mail' },
  { code: 'delais', libelle: 'Délais', icone: 'schedule' },
  { code: 'audit', libelle: 'Audit', icone: 'policy' },
];

const ICONES_EVENEMENT: Record<string, string> = {
  CREATION: 'add_circle', RECEPTION_SR: 'move_to_inbox', MODIFICATION: 'edit', APPEL: 'call',
  DOCUMENT_AJOUT: 'attach_file', DOCUMENT_RETRAIT: 'delete',
};

const CARTE_MASQUEE = /^[0-9]{0,6}[\s*Xx•-]+[0-9]{0,4}$/;

/** Champs facultatifs vidés à la correction : envoyés dans `effacer` (le PATCH ignore les valeurs nulles). */
const EFFACABLES = [
  'type_id', 'motif_id', 'sous_motif_id', 'client_racine', 'client_categorie', 'client_telephone', 'client_email',
  'client_adresse', 'client_agence_id', 'compte_reference', 'carte_masquee', 'operation_reference', 'operation_date',
  'montant_conteste', 'devise',
] as const;

/** Fiche dossier. Le statut n'évolue que par les actions du circuit ; la correction de données est motivée et tracée. */
@Component({
  selector: 'bea-rc-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, ReclamationsUiComponent, RcPiecesComponent],
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
              <span class="bea-ct-badge" data-tone="INFO">Étape : {{ d.etape_libelle }}</span>
              <span class="bea-ct-badge" [attr.data-tone]="tonePriorite(d.priorite)">{{ d.priorite_libelle }}</span>
              @if (d.en_retard) { <span class="bea-ct-badge" data-tone="URGENT">En retard</span> }
              @if (d.archivee_le) { <span class="bea-ct-badge" data-tone="ANNULEE">Archivée</span> }
            </div>
          </div>
          <div class="bea-mg__actions">
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reclamations/dossiers"><mat-icon>arrow_back</mat-icon> Réclamations</a>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="chargement()" (click)="recharger()"><mat-icon>refresh</mat-icon> Actualiser</button>
            @if (d.actions.modifier && !edition()) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirEdition()"><mat-icon>edit</mat-icon> Corriger les données</button>
            }
          </div>
        </header>

        <nav class="bea-ct-tabs" aria-label="Sections du dossier">
          @for (o of onglets(); track o.code) {
            <button type="button" [class.is-on]="onglet() === o.code" (click)="choisir(o.code)">
              <mat-icon>{{ o.icone }}</mat-icon> {{ o.libelle }}
              @if (o.code === 'documents') { <small>{{ nbDocuments() }}</small> }
              @if (o.code === 'reception' && d.appels.length) { <small>{{ d.appels.length }}</small> }
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
                      <label>Objet <em>*</em><input formControlName="objet" maxlength="255" [class.is-invalid]="invalide('objet')" /></label>
                      <label>Priorité
                        <select formControlName="priorite">
                          @for (p of store.libelles('priorites'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
                        </select>
                      </label>
                    </div>
                    <label>Description <em>*</em><textarea formControlName="description" rows="5" maxlength="20000" [class.is-invalid]="invalide('description')"></textarea></label>
                    <div class="bea-rc-row">
                      <label>Type
                        <select formControlName="type_id">
                          <option value="">— À qualifier —</option>
                          @for (t of store.refs('TYPE'); track t.id) { <option [value]="t.id">{{ t.libelle }}</option> }
                        </select>
                      </label>
                      <label>Motif
                        <select formControlName="motif_id">
                          <option value="">—</option>
                          @for (m of motifs(); track m.id) { <option [value]="m.id">{{ m.libelle }}</option> }
                        </select>
                      </label>
                      <label>Sous-motif
                        <select formControlName="sous_motif_id">
                          <option value="">—</option>
                          @for (m of sousMotifs(); track m.id) { <option [value]="m.id">{{ m.libelle }}</option> }
                        </select>
                      </label>
                    </div>
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
                      <label>Agence du client
                        <select formControlName="client_agence_id">
                          <option value="">—</option>
                          @for (a of store.config()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
                        </select>
                      </label>
                    </div>
                    <label>Adresse <textarea formControlName="client_adresse" rows="2" maxlength="2000"></textarea></label>
                    <div class="bea-rc-row">
                      <label>Compte concerné <input formControlName="compte_reference" maxlength="60" /></label>
                      <label>Carte (masquée)
                        <input formControlName="carte_masquee" maxlength="25" [class.is-invalid]="invalide('carte_masquee')" />
                        @if (invalide('carte_masquee')) { <span class="bea-rc-err">Au plus les 6 premiers et 4 derniers chiffres</span> }
                      </label>
                      <label>Référence de l’opération <input formControlName="operation_reference" maxlength="120" /></label>
                    </div>
                    <div class="bea-rc-row">
                      <label>Date de l’opération <input type="date" formControlName="operation_date" /></label>
                      <label>Montant contesté <input type="number" min="0" step="0.01" formControlName="montant_conteste" /></label>
                      <label>Devise <input formControlName="devise" maxlength="3" /></label>
                    </div>
                    <div class="bea-rc-row">
                      <label>Première réception <em>*</em><input type="datetime-local" formControlName="date_premiere_reception" [max]="maintenant" /></label>
                      @if (d.date_reception_sr) {
                        <label>Réception par le Service Réclamations<input type="datetime-local" formControlName="date_reception_sr" [max]="maintenant" /></label>
                      }
                    </div>
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
                    <dt>Motif</dt><dd>{{ d.motif_ref?.libelle ?? '—' }}</dd>
                    <dt>Sous-motif</dt><dd>{{ d.sous_motif_ref?.libelle ?? '—' }}</dd>
                    <dt>Canal</dt><dd>{{ d.canal_ref?.libelle ?? '—' }}</dd>
                    <dt>Source</dt><dd>{{ d.source }}</dd>
                    @if (d.reclamation_liee) {
                      <dt>Réclamation liée</dt><dd><a [routerLink]="['/reclamations/dossiers', d.reclamation_liee.id]">{{ d.reclamation_liee.reference }}</a></dd>
                    }
                    @if (d.doublon_de) {
                      <dt>Doublon de</dt><dd><a [routerLink]="['/reclamations/dossiers', d.doublon_de.id]">{{ d.doublon_de.reference }}</a></dd>
                    }
                  </dl>
                </section>
                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top"><h2>Réclamant</h2></div>
                  <dl class="bea-rc-dl">
                    <dt>Nom</dt><dd>{{ d.client.nom ?? '—' }}</dd>
                    <dt>Racine ORION</dt><dd>{{ d.client.racine ?? 'Non-client / non renseignée' }}</dd>
                    <dt>Catégorie</dt><dd>{{ d.client.categorie_libelle ?? '—' }}</dd>
                    <dt>Téléphone</dt><dd>{{ d.client.telephone ?? '—' }}</dd>
                    <dt>E-mail</dt><dd>{{ d.client.email ?? '—' }}</dd>
                    <dt>Agence</dt><dd>{{ d.client.agence ? d.client.agence.code + ' — ' + d.client.agence.libelle : '—' }}</dd>
                    <dt>Adresse</dt><dd>{{ d.client.adresse ?? '—' }}</dd>
                  </dl>
                </section>
                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top"><h2>Compte et opération</h2></div>
                  <dl class="bea-rc-dl">
                    <dt>Compte</dt><dd>{{ d.operation.compte_reference ?? '—' }}</dd>
                    <dt>Carte</dt><dd>{{ d.operation.carte_masquee ?? '—' }}</dd>
                    <dt>Référence</dt><dd>{{ d.operation.reference ?? '—' }}</dd>
                    <dt>Date</dt><dd>{{ date(d.operation.date) }}</dd>
                    <dt>Montant contesté</dt><dd>{{ d.operation.montant_conteste ? d.operation.montant_conteste + ' ' + (d.operation.devise ?? '') : '—' }}</dd>
                  </dl>
                </section>
              </div>
              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top"><h2>Description</h2></div>
                <p class="bea-rc-text">{{ d.description }}</p>
              </section>
              <p class="bea-rc-hint">Créée le {{ date(d.created_at, true) }}{{ d.cree_par ? ' par ' + d.cree_par : '' }}{{ d.modifie_par ? ' · dernière modification par ' + d.modifie_par : '' }} · révision {{ d.revision }}</p>
            }
          }

          @case ('reception') {
            <div class="bea-rc-grid">
              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top"><h2>Dates de réception</h2></div>
                <dl class="bea-rc-dl">
                  <dt>Première réception</dt><dd>{{ date(d.date_premiere_reception, true) }}</dd>
                  <dt>Réception par le SR</dt><dd>{{ d.date_reception_sr ? date(d.date_reception_sr, true) : 'Pas encore reçue par le Service Réclamations' }}</dd>
                  <dt>Saisie dans BEA DIGITAL</dt><dd>{{ date(d.created_at, true) }}</dd>
                </dl>
              </section>
              <section class="bea-mg__panel">
                <div class="bea-mg__panel-top"><h2>Point de réception</h2></div>
                <dl class="bea-rc-dl">
                  <dt>Unité</dt><dd>{{ d.unite_reception_ref?.libelle ?? '—' }}</dd>
                  <dt>Canal</dt><dd>{{ d.canal_ref?.libelle ?? '—' }}</dd>
                  <dt>Enregistrée par</dt><dd>{{ d.cree_par ?? '—' }}</dd>
                </dl>
              </section>
            </div>
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top">
                <h2>Appels téléphoniques</h2>
                @if (d.actions.ajouter_appel) {
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
          }

          @case ('traitement') {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Pilotage et traitement</h2></div>
              <dl class="bea-rc-dl">
                <dt>Unité de suivi</dt><dd>{{ d.unite_suivi_ref?.libelle ?? '—' }}</dd>
                <dt>Gestionnaire SR</dt><dd>{{ d.gestionnaire ?? 'Non désigné' }}</dd>
                <dt>Service de traitement</dt><dd>{{ d.unite_traitement_ref?.libelle ?? 'Non affectée' }}</dd>
                <dt>Responsable du traitement</dt><dd>{{ d.responsable_traitement ?? '—' }}</dd>
                <dt>Transmission au service</dt><dd>{{ date(d.dates['date_transmission'], true) }}</dd>
                <dt>Retour du service</dt><dd>{{ date(d.dates['date_retour_service'], true) }}</dd>
                <dt>Renvois au service</dt><dd>{{ d.nb_renvois }}</dd>
              </dl>
            </section>
            <div class="bea-rc-note"><mat-icon>construction</mat-icon>
              <span>Les actions du circuit (qualification, affectation, retour du service, suspension, refus…) ne sont pas encore disponibles dans cette version.</span>
            </div>
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
                          @if (e.statut_apres && e.statut_apres !== e.statut_avant) { <span class="bea-ct-badge" [attr.data-tone]="toneStatut(e.statut_apres)">{{ libelleStatut(e.statut_apres) }}</span> }
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
                <p class="bea-rc-muted">Chargement de la chronologie…</p>
              }
            </section>
          }

          @case ('documents') {
            <section class="bea-mg__panel bea-rc-pad">
              @if (d.actions.documents_voir) {
                <bea-rc-pieces [dossierId]="d.id" [reference]="d.reference" (modifie)="piecesModifiees($event)" />
              } @else {
                <p class="bea-rc-muted">Vous n’avez pas accès aux pièces de ce dossier.</p>
              }
            </section>
          }

          @case ('reponse') {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Réponse au client</h2></div>
              <dl class="bea-rc-dl">
                <dt>Réponse envoyée le</dt><dd>{{ d.dates['date_reponse_client'] ? date(d.dates['date_reponse_client'], true) : 'Aucune réponse envoyée' }}</dd>
                <dt>Résultat</dt><dd>{{ d.resultat_libelle ?? '—' }}</dd>
                <dt>Motif de la décision</dt><dd>{{ d.motif_resolution ?? '—' }}</dd>
                <dt>Clôture</dt><dd>{{ date(d.date_cloture, true) }}</dd>
              </dl>
            </section>
            <div class="bea-rc-note"><mat-icon>construction</mat-icon>
              <span>La rédaction, la validation et l’envoi de la réponse ne sont pas encore disponibles dans cette version.</span>
            </div>
          }

          @case ('delais') {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Délais</h2></div>
              @if (d.echeance) {
                <dl class="bea-rc-dl">
                  <dt>Échéance</dt><dd [class.bea-rc-late]="d.en_retard">{{ date(d.echeance) }}{{ d.en_retard ? ' — dépassée' : '' }}</dd>
                  <dt>Échéance initiale</dt><dd>{{ date(d.echeance_initiale) }}</dd>
                </dl>
              } @else {
                <p class="bea-rc-pad bea-rc-muted">Aucune règle de délai n’est configurée pour ce dossier : aucune échéance n’est calculée.</p>
              }
            </section>
            <div class="bea-rc-note"><mat-icon>gavel</mat-icon>
              <span>Les délais sont des paramètres internes de la banque. Aucun délai réglementaire n’est appliqué tant que la Conformité ne l’a pas validé.</span>
            </div>
          }

          @case ('audit') {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Journal d’audit</h2></div>
              @if (audit(); as lignes) {
                <div class="bea-mg__table-wrap">
                  <table class="bea-mg__table">
                    <thead><tr><th>Date</th><th>Action</th><th>Utilisateur</th><th>Avant</th><th>Après</th><th>Requête</th></tr></thead>
                    <tbody>
                      @for (l of lignes; track l.id) {
                        <tr>
                          <td>{{ date(l.date, true) }}</td>
                          <td><code>{{ l.action }}</code></td>
                          <td>{{ l.utilisateur ?? '—' }}</td>
                          <td>@if (l.avant) { <pre class="bea-rc-json">{{ json(l.avant) }}</pre> }</td>
                          <td>@if (l.apres) { <pre class="bea-rc-json">{{ json(l.apres) }}</pre> }</td>
                          <td><small>{{ l.request_id ?? '' }}</small></td>
                        </tr>
                      } @empty {
                        <tr><td colspan="6" class="bea-rc-muted">Aucune entrée.</td></tr>
                      }
                    </tbody>
                  </table>
                </div>
              } @else {
                <p class="bea-rc-pad bea-rc-muted">Chargement du journal…</p>
              }
            </section>
          }
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
  readonly maintenant = maintenantLocal();

  readonly dossier = signal<Dossier | null>(null);
  readonly introuvable = signal(false);
  readonly chargement = signal(false);
  readonly onglet = signal<Onglet>('general');
  readonly evenements = signal<Evenement[] | null>(null);
  readonly audit = signal<LigneAudit[] | null>(null);
  readonly nbDocuments = signal(0);
  readonly edition = signal(false);
  readonly appelOuvert = signal(false);
  readonly busy = signal(false);
  readonly tente = signal(false);
  private readonly typeId = signal('');
  private readonly motifId = signal('');
  private readonly premiere = signal('');
  private readonly receptionSr = signal('');
  private id = '';
  private initial = '';

  readonly onglets = computed(() => ONGLETS.filter((o) => o.code !== 'audit' || !!this.dossier()?.actions.audit_voir));
  readonly motifs = computed(() => this.store.enfants('MOTIF', this.typeId()));
  readonly sousMotifs = computed(() => this.store.enfants('SOUS_MOTIF', this.motifId()));
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
    type_id: [''],
    motif_id: [''],
    sous_motif_id: [''],
    client_racine: ['', Validators.pattern(/^[0-9]{6}$/)],
    client_categorie: [''],
    client_nom: ['', Validators.required],
    client_telephone: [''],
    client_email: [''],
    client_agence_id: [''],
    client_adresse: [''],
    compte_reference: [''],
    carte_masquee: ['', Validators.pattern(CARTE_MASQUEE)],
    operation_reference: [''],
    operation_date: [''],
    montant_conteste: [null as number | null],
    devise: [''],
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

  readonly hasUnsavedChanges = unsavedChanges(() =>
    !this.busy() && ((this.edition() && JSON.stringify(this.form.getRawValue()) !== this.initial) || (this.appelOuvert() && this.appel.dirty)));

  ngOnInit(): void {
    this.store.charger();
    const c = this.form.controls;
    c.type_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => {
      this.typeId.set(v);
      if (!this.store.enfants('MOTIF', v).some((m) => m.id === c.motif_id.value)) c.motif_id.setValue('');
    });
    c.motif_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => {
      this.motifId.set(v);
      if (!this.store.enfants('SOUS_MOTIF', v).some((m) => m.id === c.sous_motif_id.value)) c.sous_motif_id.setValue('');
    });
    c.date_premiere_reception.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.premiere.set(v));
    c.date_reception_sr.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.receptionSr.set(v));

    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((q) => {
      const o = q.get('onglet') as Onglet | null;
      this.onglet.set(o && ONGLETS.some((x) => x.code === o) ? o : 'general');
      this.chargerOnglet();
    });
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((p) => {
      this.id = p.get('id') ?? '';
      this.dossier.set(null);
      this.introuvable.set(false);
      this.edition.set(false);
      this.evenements.set(null);
      this.audit.set(null);
      this.recharger();
    });
  }

  date(iso: string | null | undefined, heure = false): string {
    return dateFr(iso, heure);
  }

  json(v: unknown): string {
    return JSON.stringify(v, null, 1);
  }

  icone(type: string): string {
    return ICONES_EVENEMENT[type] ?? 'radio_button_checked';
  }

  libelleStatut(code: string): string {
    return this.store.libelles('statuts').find((s) => s.code === code)?.libelle ?? code;
  }

  detailEvenement(e: Evenement): string | null {
    const d = e.donnees ?? {};
    if (Array.isArray(d['champs'])) return `Champs : ${(d['champs'] as string[]).join(', ')}`;
    if (typeof d['fichier'] === 'string') return `${d['fichier']}${d['categorie'] ? ' (' + d['categorie'] + ')' : ''}`;
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
        this.dossier.set(d);
        this.nbDocuments.set(d.nb_documents);
        if (this.onglet() === 'audit' && !d.actions.audit_voir) this.choisir('general');
        this.evenements.set(null);
        this.audit.set(null);
        this.chargerOnglet();
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
    void this.router.navigate([], { relativeTo: this.route, queryParams: { onglet: o === 'general' ? null : o }, queryParamsHandling: 'merge', replaceUrl: true });
  }

  private chargerOnglet(): void {
    const d = this.dossier();
    if (!d) return;
    if (this.onglet() === 'chronologie' && !this.evenements()) {
      this.rc.chronologie(d.id).subscribe({
        next: (ev) => this.evenements.set(ev),
        error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Chronologie indisponible')),
      });
    }
    if (this.onglet() === 'audit' && !this.audit() && d.actions.audit_voir) {
      this.rc.audit(d.id).subscribe({
        next: (l) => this.audit.set(l),
        error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Journal indisponible')),
      });
    }
  }

  piecesModifiees(n: number): void {
    this.nbDocuments.set(n);
    this.evenements.set(null);
    this.audit.set(null);
  }

  invalide(nom: 'objet' | 'description' | 'client_nom' | 'client_racine' | 'carte_masquee'): boolean {
    const ctl = this.form.controls[nom];
    return ctl.invalid && (ctl.touched || this.tente());
  }

  ouvrirEdition(): void {
    const d = this.dossier();
    if (!d) return;
    this.tente.set(false);
    this.form.reset({
      objet: d.objet, description: d.description, priorite: d.priorite,
      type_id: d.type_ref?.id ?? '', motif_id: d.motif_ref?.id ?? '', sous_motif_id: d.sous_motif_ref?.id ?? '',
      client_racine: d.client.racine ?? '', client_categorie: d.client.categorie ?? '', client_nom: d.client.nom ?? '',
      client_telephone: d.client.telephone ?? '', client_email: d.client.email ?? '',
      client_agence_id: d.client.agence?.id ?? '', client_adresse: d.client.adresse ?? '',
      compte_reference: d.operation.compte_reference ?? '', carte_masquee: d.operation.carte_masquee ?? '',
      operation_reference: d.operation.reference ?? '', operation_date: d.operation.date ?? '',
      montant_conteste: d.operation.montant_conteste != null ? Number(d.operation.montant_conteste) : null,
      devise: d.operation.devise ?? '',
      date_premiere_reception: versSaisieLocale(d.date_premiere_reception),
      date_reception_sr: versSaisieLocale(d.date_reception_sr), motif: '',
    });
    this.typeId.set(this.form.controls.type_id.value);
    this.motifId.set(this.form.controls.motif_id.value);
    this.premiere.set(this.form.controls.date_premiere_reception.value);
    this.receptionSr.set(this.form.controls.date_reception_sr.value);
    this.initial = JSON.stringify(this.form.getRawValue());
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
    if (this.form.invalid) {
      this.feedback.warning({ title: 'Champs à corriger', message: 'Vérifiez les champs signalés en rouge.' });
      return;
    }
    if (this.dateModifiee() && !v.motif.trim()) {
      this.feedback.warning({ title: 'Motif obligatoire', message: 'Indiquez pourquoi la date de réception est corrigée.' });
      return;
    }
    const premiere = depuisSaisieLocale(v.date_premiere_reception);
    if (!premiere) {
      this.feedback.warning({ title: 'Date invalide', message: 'Renseignez la date de première réception.' });
      return;
    }
    const corps: Record<string, unknown> = {
      revision: d.revision, objet: v.objet.trim(), description: v.description.trim(), priorite: v.priorite,
      client_nom: v.client_nom.trim(), date_premiere_reception: premiere, motif: v.motif.trim() || null,
    };
    if (d.date_reception_sr && v.date_reception_sr) corps['date_reception_sr'] = depuisSaisieLocale(v.date_reception_sr);
    const effacer: string[] = [];
    for (const champ of EFFACABLES) {
      const brut = v[champ];
      const valeur = typeof brut === 'string' ? brut.trim() : brut;
      if (valeur === '' || valeur === null) effacer.push(champ);
      else corps[champ] = champ === 'devise' ? String(valeur).toUpperCase() : valeur;
    }
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
        this.dossier.set(r);
        this.edition.set(false);
        this.evenements.set(null);
        this.audit.set(null);
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
        this.dossier.set(r);
        this.appelOuvert.set(false);
        this.evenements.set(null);
        this.audit.set(null);
      });
  }
}
