import { MontantPipe } from '../shared/montant.pipe';
import { ChangeDetectionStrategy, Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackMessage, FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { UiDialogAction } from '../shared/ui-dialog/ui-dialog.types';

type TransitionAction = 'soumettre' | 'valider' | 'suspendre' | 'reprendre' | 'expirer' | 'archiver';

const TRANSITIONS: Record<
  TransitionAction,
  { preset: UiDialogAction; question: string; hint: string; loading: string; success: string; errorTitle: string }
> = {
  soumettre: {
    preset: 'soumission',
    question: 'Soumettre pour validation le contrat',
    hint: 'Après soumission, le contrat est envoyé au processus de validation.',
    loading: 'Soumission…',
    success: 'Contrat soumis avec succès',
    errorTitle: 'Échec de la soumission',
  },
  valider: {
    preset: 'validation',
    question: 'Valider le contrat',
    hint: 'Après validation, le contrat devient actif et ses échéances déclenchent des alertes.',
    loading: 'Validation…',
    success: 'Validation effectuée',
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
    question: 'Marquer comme expiré le contrat',
    hint: 'Vous pourrez ensuite préparer un renouvellement ou l’archiver.',
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

interface Contrat {
  id: string;
  reference: string;
  titre: string;
  numero_contrat: string | null;
  description: string | null;
  type_contrat: string;
  fournisseur_id: string | null;
  fournisseur_snapshot: string | null;
  agence_id: string | null;
  agence_libelle_snapshot: string | null;
  responsable_id: string | null;
  responsable_nom: string | null;
  date_signature: string | null;
  date_debut: string;
  date_fin: string | null;
  prochain_echeance: string | null;
  montant: number | null;
  montant_ht: number | null;
  taux_tva: number | null;
  devise: string;
  periodicite: string;
  mode_paiement: string | null;
  ref_paiement: string | null;
  alerte_jours: number;
  observation: string | null;
  statut: string;
  contrat_precedent_id: string | null;
  echeances?: Echeance[];
  paiements?: Paiement[];
  historique?: Hist[];
}

interface Echeance {
  id: string;
  type_echeance: string;
  date_prevue: string;
  montant: number | null;
  statut: string;
  commentaire: string | null;
}

interface Paiement {
  id: string;
  reference: string | null;
  date_prevue: string;
  date_reelle: string | null;
  montant_prevu: number;
  montant_paye: number;
  statut: string;
  mode: string | null;
}

interface Hist {
  id: string;
  action: string;
  from_statut: string | null;
  to_statut: string | null;
  user_nom: string | null;
  commentaire: string | null;
  created_at: string;
}

const STATUT_LABELS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  EN_PREPARATION: 'En préparation',
  EN_VALIDATION: 'En validation',
  ACTIF: 'Actif',
  SUSPENDU: 'Suspendu',
  EXPIRE: 'Expiré',
  ARCHIVE: 'Archivé',
  REJETE: 'Rejeté',
  ANNULE: 'Annulé',
  A_VENIR: 'À venir',
  FAITE: 'Faite',
  ANNULEE: 'Annulée',
  EN_RETARD: 'En retard',
  PAYE: 'Payé',
  PARTIELLEMENT_PAYE: 'Partiellement payé',
};

const STATUT_AIDE: Record<string, string> = {
  BROUILLON: 'Complétez la fiche puis soumettez-la pour validation.',
  EN_PREPARATION: 'Complétez la fiche puis soumettez-la pour validation.',
  EN_VALIDATION: 'En attente de validation : validez pour activer le contrat, ou rejetez-le avec un motif.',
  ACTIF: 'Contrat en vigueur. Les échéances déclenchent des alertes ; à l’approche de la fin, préparez le renouvellement.',
  SUSPENDU: 'Contrat temporairement suspendu. Reprenez-le pour le réactiver.',
  EXPIRE: 'La date de fin est passée. Préparez un renouvellement ou archivez le contrat.',
  ARCHIVE: 'Contrat archivé : consultation uniquement.',
  REJETE: 'Contrat rejeté lors de la validation. Archivez-le ou annulez-le.',
  ANNULE: 'Contrat annulé : consultation uniquement.',
};

const ETAPES = [
  { code: 'BROUILLON', label: 'Brouillon' },
  { code: 'EN_VALIDATION', label: 'Validation' },
  { code: 'ACTIF', label: 'En vigueur' },
  { code: 'FIN', label: 'Expiré / archivé' },
] as const;

const TYPES_ECHEANCE = [
  { code: 'PAIEMENT', label: 'Paiement' },
  { code: 'REVISION', label: 'Révision de prix' },
  { code: 'PREAVIS', label: 'Préavis de résiliation' },
  { code: 'RENOUVELLEMENT', label: 'Renouvellement' },
  { code: 'FIN_CONTRAT', label: 'Fin de contrat' },
  { code: 'AUTRE', label: 'Autre' },
] as const;

const PERIODICITE_LABELS: Record<string, string> = {
  MENSUEL: 'Mensuel',
  TRIMESTRIEL: 'Trimestriel',
  SEMESTRIEL: 'Semestriel',
  ANNUEL: 'Annuel',
  UNIQUE: 'Paiement unique',
};

const ACTION_LABELS: Record<string, string> = {
  creer: 'Création',
  modifier: 'Modification',
  supprimer: 'Suppression',
  soumettre: 'Soumis pour validation',
  valider: 'Validé',
  rejeter: 'Rejeté',
  suspendre: 'Suspendu',
  reprendre: 'Repris',
  expirer: 'Marqué expiré',
  annuler: 'Annulé',
  archiver: 'Archivé',
  renouveler: 'Renouvellement',
  echeance: 'Échéance ajoutée',
  echeance_modifier: 'Échéance modifiée',
  echeance_supprimer: 'Échéance supprimée',
  paiement: 'Paiement enregistré',
};

const MODES_PAIEMENT = ['Espèces', 'Virement', 'Amanty', 'Chèque', 'Carte', 'Prélèvement'] as const;
const MODES_AVEC_REF = new Set<string>(['Virement', 'Amanty']);

interface RefItem {
  id: string;
  libelle?: string;
  raison_sociale?: string;
  code?: string;
  full_name?: string;
}

interface Alerte {
  type: string;
  contrat_id: string;
  reference: string;
  titre: string;
  fournisseur: string | null;
  agence: string | null;
  echeance: string | null;
  jours: number | null;
  niveau: string;
  statut: string;
}

@Component({
  selector: 'bea-contrats-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MgGedPanelComponent, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances</p>
          <h1>{{ titre() }}</h1>
        </div>
        <div class="bea-mg__actions">
          @if (mode() === 'fiche' || mode() === 'nouveau') {
            @if (fiche(); as c) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="telechargement()" (click)="telechargerPdf(c)">
                <mat-icon>download</mat-icon> {{ telechargement() ? 'Préparation…' : 'Télécharger le contrat (PDF)' }}
              </button>
            }
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/contrats-echeances/liste">Retour liste</a>
          } @else if (mode() === 'echeances') {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirEcheance()">Nouvelle échéance</button>
          } @else if (mode() === 'liste') {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/contrats-echeances/nouveau">Nouveau contrat</a>
          }
        </div>
      </header>

      @if (mode() === 'liste' || mode() === 'renouvellements') {
        <form class="bea-mg__search" [formGroup]="filtres" (ngSubmit)="loadListe()">
          <label class="bea-mg__field">Recherche
            <input formControlName="q" placeholder="Référence, objet, fournisseur, agence, responsable" />
          </label>
          <label class="bea-mg__field">Statut
            <select formControlName="statut" (change)="loadListe()">
              <option value="">Tous</option>
              @for (s of statuts; track s) { <option [value]="s">{{ s }}</option> }
            </select>
          </label>
          <label class="bea-mg__field">Échéance
            <select formControlName="horizon" (change)="loadListe()">
              <option value="">Toutes</option>
              <option value="retard">En retard</option>
              <option value="7">≤ 7 jours</option>
              <option value="30">≤ 30 jours</option>
              <option value="60">≤ 60 jours</option>
              <option value="90">≤ 90 jours</option>
            </select>
          </label>
          <button type="submit" class="bea-mg__btn bea-mg__btn--ghost">Filtrer</button>
        </form>
        <div class="bea-mg__table-scroll bea-ct-table-wrap">
          <table class="bea-mg__table bea-ct-table">
            <thead>
              <tr>
                <th>Référence</th><th>Objet</th><th>Fournisseur</th><th>Agence</th>
                <th>Responsable</th><th>Période</th><th class="is-num">Montant TTC</th><th>Statut</th><th class="is-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (c of contrats(); track c.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 35 : 0">
                  <td class="is-nowrap">
                    <code class="bea-mg__code">{{ c.reference }}</code>
                    <small class="bea-ct-sub">{{ typeLabel(c.type_contrat) }}</small>
                  </td>
                  <td class="is-wide"><strong class="bea-ct-strong">{{ c.titre }}</strong></td>
                  <td class="is-wide">{{ c.fournisseur_snapshot || '—' }}</td>
                  <td class="is-wide">{{ c.agence_libelle_snapshot || '—' }}</td>
                  <td class="is-wide">{{ c.responsable_nom || '—' }}</td>
                  <td class="is-nowrap">
                    {{ dateFr(c.date_debut) }}
                    <small class="bea-ct-sub">au {{ dateFr(c.date_fin) }}</small>
                  </td>
                  <td class="is-nowrap is-num">{{ c.montant | montant }} {{ c.devise }}</td>
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="c.statut">{{ statutLabel(c.statut) }}</span></td>
                  <td class="bea-mg__actions-cell is-nowrap">
                    <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="voir(c)"><mat-icon>visibility</mat-icon></button>
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', c.id]" title="Modifier"><mat-icon>edit</mat-icon></a>
                    <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerContrat(c)">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="9">
                    <div class="bea-ct-empty"><mat-icon>description</mat-icon><p>Aucun contrat enregistré.</p></div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (contrats().length) {
          <p class="bea-ct-count">{{ contrats().length }} contrat{{ contrats().length > 1 ? 's' : '' }}</p>
        }
      }

      @if (apercuOuvert()) {
        <div class="bea-mg__backdrop" (click)="fermerApercu()"></div>
        <div class="bea-mg__modal bea-mg__modal--lg bea-ct-view" role="dialog" aria-modal="true" aria-labelledby="bea-ct-view-title">
          @if (apercu(); as v) {
            <header class="bea-ct-view__head">
              <div>
                <p class="bea-ct-view__kicker">
                  <code class="bea-mg__code">{{ v.reference }}</code>
                  <span class="bea-ct-badge" [attr.data-tone]="v.statut">{{ statutLabel(v.statut) }}</span>
                </p>
                <h2 id="bea-ct-view-title">{{ v.titre }}</h2>
                <p class="bea-ct-view__sub">{{ typeLabel(v.type_contrat) }}{{ v.numero_contrat ? ' · N° ' + v.numero_contrat : '' }}</p>
              </div>
              <button type="button" class="bea-ct-view__close" title="Fermer" aria-label="Fermer" (click)="fermerApercu()">
                <mat-icon>close</mat-icon>
              </button>
            </header>

            <div class="bea-ct-view__body">
              <div class="bea-ct-view__kpis">
                <div>
                  <span>Montant TTC</span>
                  <strong>{{ v.montant | montant }} {{ v.devise }}</strong>
                  @if (v.montant_ht !== null) { <small>HT {{ v.montant_ht | montant }} · TVA {{ v.taux_tva ?? 0 }} %</small> }
                </div>
                <div>
                  <span>Période</span>
                  <strong>{{ dateFr(v.date_debut) }} → {{ dateFr(v.date_fin) }}</strong>
                  <small>{{ periodiciteLabel(v.periodicite) }}</small>
                </div>
                <div>
                  <span>Prochaine échéance</span>
                  <strong>{{ dateFr(v.prochain_echeance) }}</strong>
                  @if (joursRestants(v.prochain_echeance); as j) { <small>{{ j }}</small> }
                </div>
              </div>

              <section class="bea-ct-view__section">
                <h3><mat-icon>groups</mat-icon> Parties</h3>
                <dl class="bea-ct-view__dl">
                  <div><dt>Fournisseur</dt><dd>{{ v.fournisseur_snapshot || '—' }}</dd></div>
                  <div><dt>Agence</dt><dd>{{ v.agence_libelle_snapshot || '—' }}</dd></div>
                  <div><dt>Responsable</dt><dd>{{ v.responsable_nom || '—' }}</dd></div>
                </dl>
              </section>

              <section class="bea-ct-view__section">
                <h3><mat-icon>event</mat-icon> Dates et paiement</h3>
                <dl class="bea-ct-view__dl">
                  <div><dt>Signature</dt><dd>{{ dateFr(v.date_signature) }}</dd></div>
                  <div><dt>Mode de paiement</dt><dd>{{ v.mode_paiement || '—' }}</dd></div>
                  @if (v.ref_paiement) {
                    <div><dt>{{ v.mode_paiement === 'Amanty' ? 'Numéro Amanty' : 'Compte' }}</dt><dd>{{ v.ref_paiement }}</dd></div>
                  }
                  <div><dt>Alerte</dt><dd>{{ v.alerte_jours }} jours avant échéance</dd></div>
                </dl>
              </section>

              @if (v.description || v.observation) {
                <section class="bea-ct-view__section">
                  <h3><mat-icon>notes</mat-icon> Description</h3>
                  @if (v.description) { <p class="bea-ct-view__text">{{ v.description }}</p> }
                  @if (v.observation) { <p class="bea-ct-view__text bea-ct-view__text--muted">{{ v.observation }}</p> }
                </section>
              }

              <section class="bea-ct-view__section">
                <h3><mat-icon>schedule</mat-icon> Échéances <small>{{ (v.echeances || []).length }}</small></h3>
                @if ((v.echeances || []).length) {
                  <ul class="bea-ct-view__rows">
                    @for (e of v.echeances; track e.id) {
                      <li>
                        <strong>{{ dateFr(e.date_prevue) }}</strong>
                        <span>{{ typeEcheanceLabel(e.type_echeance) }}</span>
                        <span class="is-num">{{ e.montant | montant }}</span>
                        <span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statutLabel(e.statut) }}</span>
                      </li>
                    }
                  </ul>
                } @else { <p class="bea-ct-view__none">Aucune échéance planifiée.</p> }
              </section>

              <section class="bea-ct-view__section">
                <h3><mat-icon>payments</mat-icon> Paiements <small>{{ (v.paiements || []).length }}</small></h3>
                @if ((v.paiements || []).length) {
                  <ul class="bea-ct-view__rows">
                    @for (p of v.paiements; track p.id) {
                      <li>
                        <strong>{{ dateFr(p.date_prevue) }}</strong>
                        <span>{{ p.reference || '—' }}</span>
                        <span class="is-num">{{ p.montant_paye | montant }} / {{ p.montant_prevu | montant }}</span>
                        <span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statutLabel(p.statut) }}</span>
                      </li>
                    }
                  </ul>
                } @else { <p class="bea-ct-view__none">Aucun paiement suivi.</p> }
              </section>
            </div>

            <footer class="bea-ct-view__foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerApercu()">Fermer</button>
              <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/contrats-echeances', v.id]">
                <mat-icon>edit</mat-icon> Ouvrir la fiche
              </a>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="telechargement()" (click)="telechargerPdf(v)">
                <mat-icon>download</mat-icon> {{ telechargement() ? 'Préparation…' : 'Télécharger PDF' }}
              </button>
            </footer>
          } @else {
            <div class="bea-ct-view__loading">
              <span class="bea-ct-view__spinner"></span> Chargement du contrat…
            </div>
          }
        </div>
      }

      @if (mode() === 'alertes') {
        <div class="bea-mg__table-scroll bea-ct-table-wrap">
          <table class="bea-mg__table bea-ct-table">
            <thead>
              <tr>
                <th>Contrat</th><th>Alerte</th><th>Fournisseur</th><th>Agence</th>
                <th>Échéance</th><th>Niveau</th><th>Statut</th><th class="is-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (a of alertes(); track $index; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 35 : 0">
                  <td class="is-wide">
                    <code class="bea-mg__code">{{ a.reference }}</code>
                    <small class="bea-ct-sub">{{ a.titre }}</small>
                  </td>
                  <td class="is-wide">{{ a.type }}</td>
                  <td class="is-wide">{{ a.fournisseur || '—' }}</td>
                  <td class="is-wide">{{ a.agence || '—' }}</td>
                  <td class="is-nowrap">
                    {{ dateFr(a.echeance) }}
                    @if (a.jours !== null) { <small class="bea-ct-sub">{{ joursLabel(a.jours) }}</small> }
                  </td>
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="a.niveau">{{ a.niveau }}</span></td>
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="a.statut">{{ statutLabel(a.statut) }}</span></td>
                  <td class="bea-mg__actions-cell">
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', a.contrat_id]" title="Consulter"><mat-icon>visibility</mat-icon></a>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8">
                    <div class="bea-ct-empty"><mat-icon>notifications_none</mat-icon><p>Aucune alerte.</p></div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'echeances') {
        @if (echeanceOuverte()) {
          <form class="bea-mg__panel bea-ct-panel bea-ct-section" [formGroup]="echeanceForm" (ngSubmit)="sauverEcheance()">
            <div class="bea-mg__panel-top"><h2>{{ echeanceEditId() ? 'Modifier l’échéance' : 'Nouvelle échéance' }}</h2></div>
            <div class="bea-mg__modal-body bea-ct-grid">
              <label>Contrat
                <select formControlName="contrat_id">
                  <option value="">—</option>
                  @for (c of contrats(); track c.id) { <option [value]="c.id">{{ c.reference }} — {{ c.titre }}</option> }
                </select>
              </label>
              <label>Type <input formControlName="type_echeance" /></label>
              <label>Date prévue <input type="date" formControlName="date_prevue" /></label>
              <label>Date réelle <input type="date" formControlName="date_reelle" /></label>
              <label>Montant <input type="number" formControlName="montant" /></label>
              <label>Statut
                <select formControlName="statut">
                  <option value="A_VENIR">À venir</option>
                  <option value="FAITE">Faite</option>
                  <option value="ANNULEE">Annulée</option>
                </select>
              </label>
              <label>Commentaire <input formControlName="commentaire" /></label>
            </div>
            <div class="bea-mg__actions" style="padding: 0 1rem 1rem">
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="echeanceForm.invalid || echeanceBusy()">{{ echeanceBusy() ? 'Enregistrement…' : 'Enregistrer' }}</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerEcheance()">Fermer</button>
            </div>
          </form>
        }
        <div class="bea-mg__table-scroll bea-ct-table-wrap">
          <table class="bea-mg__table bea-ct-table">
            <thead><tr><th>Contrat</th><th>Type</th><th>Date prévue</th><th class="is-num">Montant</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
            <tbody>
              @for (e of echeances(); track e.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 35 : 0">
                  <td class="is-wide">
                    <code class="bea-mg__code">{{ e.reference }}</code>
                    <small class="bea-ct-sub">{{ e.titre }}</small>
                  </td>
                  <td class="is-wide">{{ typeEcheanceLabel(e.type_echeance) }}</td>
                  <td class="is-nowrap">
                    {{ dateFr(e.date_prevue) }}
                    <small class="bea-ct-sub">{{ joursLabel(e.jours) }}</small>
                  </td>
                  <td class="is-nowrap is-num">{{ e.montant | montant }}</td>
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statutLabel(e.statut) }}</span></td>
                  <td class="bea-mg__actions-cell">
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', e.contrat_id]" title="Consulter"><mat-icon>visibility</mat-icon></a>
                    <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="modifierEcheance(e)"><mat-icon>edit</mat-icon></button>
                    <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerEcheance(e)">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6">
                    <div class="bea-ct-empty"><mat-icon>event</mat-icon><p>Aucune échéance.</p></div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'paiements') {
        <div class="bea-nf-kpi">
          <article class="bea-nf-kpi__card"><p>Montant prévu</p><strong>{{ paiementsTotaux().prevu | montant }}</strong></article>
          <article class="bea-nf-kpi__card"><p>Déjà payé</p><strong>{{ paiementsTotaux().paye | montant }}</strong></article>
          <article class="bea-nf-kpi__card"><p>Reste à payer</p><strong>{{ paiementsTotaux().reste | montant }}</strong></article>
          <article class="bea-nf-kpi__card"><p>Paiements en retard</p><strong>{{ paiementsTotaux().retard }}</strong></article>
        </div>
        <div class="bea-mg__search">
          <label class="bea-mg__field">Statut
            <select [value]="paiementStatut()" (change)="filtrerPaiements($any($event.target).value)">
              <option value="">Tous</option>
              <option value="A_VENIR">À venir</option>
              <option value="EN_RETARD">En retard</option>
              <option value="PARTIELLEMENT_PAYE">Partiellement payé</option>
              <option value="PAYE">Payé</option>
            </select>
          </label>
        </div>
        <div class="bea-mg__table-scroll bea-ct-table-wrap">
          <table class="bea-mg__table bea-ct-table">
            <thead>
              <tr><th>Contrat</th><th>Réf. paiement</th><th>Date prévue</th><th class="is-num">Prévu</th><th class="is-num">Payé</th><th class="is-num">Reste</th><th>Statut</th><th class="is-actions">Actions</th></tr>
            </thead>
            <tbody>
              @for (p of paiements(); track p.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 35 : 0">
                  <td class="is-wide">
                    <code class="bea-mg__code">{{ p.reference }}</code>
                    <small class="bea-ct-sub">{{ p.titre }}</small>
                  </td>
                  <td class="is-wide">{{ p.paiement_ref || '—' }}</td>
                  <td class="is-nowrap">{{ dateFr(p.date_prevue) }}</td>
                  <td class="is-nowrap is-num">{{ p.montant_prevu | montant }}</td>
                  <td class="is-nowrap is-num">{{ p.montant_paye | montant }}</td>
                  <td class="is-nowrap is-num"><strong class="bea-ct-strong">{{ p.reste | montant }}</strong></td>
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statutLabel(p.statut) }}</span></td>
                  <td class="bea-mg__actions-cell">
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', p.contrat_id]" title="Consulter"><mat-icon>visibility</mat-icon></a>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8">
                    <div class="bea-ct-empty">
                      <mat-icon>payments</mat-icon>
                      <p>Aucun paiement{{ paiementStatut() ? ' pour ce statut' : '' }}.</p>
                      <small>
                        Les paiements se planifient et s’enregistrent depuis la fiche d’un contrat, onglet « Paiements ».
                        <a routerLink="/contrats-echeances/liste">Ouvrir la liste des contrats</a>
                      </small>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'nouveau' || mode() === 'fiche') {
        <form [formGroup]="form" (ngSubmit)="save()">
          <div class="bea-mg__panel bea-ct-panel bea-ct-section">
          <div class="bea-mg__panel-top"><h2>Informations</h2></div>
          <div class="bea-mg__modal-body bea-ct-grid">
            <label>Objet <input formControlName="titre" [attr.aria-invalid]="!!fieldError('titre')" />
              @if (fieldError('titre'); as m) { <small class="bea-ct-field-error" role="alert">{{ m }}</small> }
            </label>
            <label>N° contrat <input formControlName="numero_contrat" /></label>
            <label>Type
              <select formControlName="type_contrat">
                @for (t of types(); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            <label>Devise <input formControlName="devise" /></label>
            <label>Description <input formControlName="description" /></label>
            <label>Observation <input formControlName="observation" /></label>
          </div>
          </div>
          <div class="bea-mg__panel bea-ct-panel bea-ct-section">
          <div class="bea-mg__panel-top"><h2>Fournisseur, agence, responsable</h2></div>
          <div class="bea-mg__modal-body bea-ct-grid">
            <label>Fournisseur
              <select formControlName="fournisseur_id">
                <option value="">—</option>
                @for (f of fournisseurs(); track f.id) { <option [value]="f.id">{{ f.raison_sociale }}</option> }
              </select>
            </label>
            <label>Agence
              <select formControlName="agence_id">
                <option value="">—</option>
                @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
              </select>
            </label>
            <label>Responsable
              <select formControlName="responsable_id">
                <option value="">—</option>
                @for (u of responsables(); track u.id) { <option [value]="u.id">{{ u.full_name }}</option> }
              </select>
            </label>
          </div>
          </div>
          <div class="bea-mg__panel bea-ct-panel bea-ct-section">
          <div class="bea-mg__panel-top"><h2>Dates et montants</h2></div>
          <div class="bea-mg__modal-body bea-ct-grid">
            <label>Signature <input type="date" formControlName="date_signature" /></label>
            <label>Début <input type="date" formControlName="date_debut" [attr.aria-invalid]="!!fieldError('date_debut')" />
              @if (fieldError('date_debut'); as m) { <small class="bea-ct-field-error" role="alert">{{ m }}</small> }
            </label>
            <label>Fin <input type="date" formControlName="date_fin" [attr.aria-invalid]="!!fieldError('date_fin')" />
              @if (fieldError('date_fin'); as m) { <small class="bea-ct-field-error" role="alert">{{ m }}</small> }
            </label>
            <label>Montant HT <input type="number" formControlName="montant_ht" [attr.aria-invalid]="!!fieldError('montant_ht')" />
              @if (fieldError('montant_ht'); as m) { <small class="bea-ct-field-error" role="alert">{{ m }}</small> }
            </label>
            <label>TVA % <input type="number" formControlName="taux_tva" /></label>
            <label>Périodicité
              <select formControlName="periodicite">
                <option value="MENSUEL">Mensuel</option>
                <option value="TRIMESTRIEL">Trimestriel</option>
                <option value="SEMESTRIEL">Semestriel</option>
                <option value="ANNUEL">Annuel</option>
                <option value="UNIQUE">Unique</option>
              </select>
            </label>
            <label>Mode de paiement
              <select formControlName="mode_paiement" (change)="onModePaiementChange()">
                <option value="">—</option>
                @for (m of modesPaiement(); track m) { <option [value]="m">{{ m }}</option> }
              </select>
            </label>
            @if (form.controls.mode_paiement.value === 'Virement') {
              <label>Compte bénéficiaire (optionnel)
                <input formControlName="ref_paiement" maxlength="120" placeholder="Ex. RIB / IBAN, banque" />
              </label>
            } @else if (form.controls.mode_paiement.value === 'Amanty') {
              <label>Numéro / compte Amanty (optionnel)
                <input formControlName="ref_paiement" maxlength="120" placeholder="Ex. 31004531" />
              </label>
            }
            <label>Alerte (jours) <input type="number" formControlName="alerte_jours" /></label>
          </div>
          <p class="bea-ct-note">TTC recalculé par le serveur à l’enregistrement. Montant actuel : {{ fiche()?.montant | montant }} {{ fiche()?.devise || form.controls.devise.value }}</p>
          <div class="bea-mg__actions" style="padding: 0 1rem 1rem">
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || saving()" [attr.aria-busy]="saving()">
              {{ saving() ? 'Enregistrement…' : contratId() ? 'Enregistrer' : 'Enregistrer brouillon' }}
            </button>
          </div>
          </div>
        </form>

        @if (fiche(); as c) {
          <div class="bea-mg__panel bea-ct-panel bea-ct-life">
            <div class="bea-ct-life__head">
              <div>
                <h2>Statut du contrat</h2>
                <p class="bea-ct-life__hint">
                  <span class="bea-ct-badge" [attr.data-tone]="c.statut">{{ statutLabel(c.statut) }}</span>
                  {{ statutAide(c.statut) }}
                </p>
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
                @if (c.statut === 'BROUILLON' || c.statut === 'EN_PREPARATION') {
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('soumettre')"><mat-icon>send</mat-icon> Soumettre pour validation</button>
                }
                @if (c.statut === 'EN_VALIDATION') {
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('valider')"><mat-icon>check_circle</mat-icon> Valider</button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="demanderMotif('rejeter')"><mat-icon>block</mat-icon> Rejeter</button>
                }
                @if (c.statut === 'ACTIF') {
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="renouveler()"><mat-icon>autorenew</mat-icon> Préparer le renouvellement</button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('suspendre')"><mat-icon>pause_circle</mat-icon> Suspendre</button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('expirer')"><mat-icon>event_busy</mat-icon> Marquer expiré</button>
                }
                @if (c.statut === 'SUSPENDU') {
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('reprendre')"><mat-icon>play_circle</mat-icon> Reprendre</button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('expirer')"><mat-icon>event_busy</mat-icon> Marquer expiré</button>
                }
                @if (c.statut === 'EXPIRE') {
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="renouveler()"><mat-icon>autorenew</mat-icon> Préparer le renouvellement</button>
                }
              </div>
              <div class="bea-ct-life__group">
                @if (c.statut === 'ACTIF' || c.statut === 'EXPIRE' || c.statut === 'SUSPENDU' || c.statut === 'REJETE') {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('archiver')"><mat-icon>inventory_2</mat-icon> Archiver</button>
                }
                @if (c.statut !== 'ARCHIVE' && c.statut !== 'ANNULE' && c.statut !== 'EXPIRE' && c.statut !== 'BROUILLON') {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-ct-danger" (click)="demanderMotif('annuler')"><mat-icon>cancel</mat-icon> Annuler le contrat</button>
                }
                @if (c.statut === 'BROUILLON') {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-ct-danger" (click)="supprimer()"><mat-icon>delete</mat-icon> Supprimer le brouillon</button>
                }
              </div>
            </fieldset>

            @if (c.contrat_precedent_id) {
              <p class="bea-ct-note">Renouvellement d’un contrat précédent — <a class="bea-ct-link" [routerLink]="['/contrats-echeances', c.contrat_precedent_id]">ouvrir le contrat d’origine</a></p>
            }
          </div>

          <div class="bea-mg__panel bea-ct-panel bea-ct-suivi">
            <div class="bea-ct-suivi__head">
              <h2>Suivi du contrat</h2>
              <div class="bea-ct-tabs">
                <button type="button" [class.is-on]="onglet() === 'echeances'" (click)="onglet.set('echeances')">
                  <mat-icon>schedule</mat-icon> Échéances <small>{{ (c.echeances || []).length }}</small>
                </button>
                <button type="button" [class.is-on]="onglet() === 'paiements'" (click)="onglet.set('paiements')">
                  <mat-icon>payments</mat-icon> Paiements <small>{{ (c.paiements || []).length }}</small>
                </button>
                <button type="button" [class.is-on]="onglet() === 'documents'" (click)="onglet.set('documents')">
                  <mat-icon>folder</mat-icon> Documents
                </button>
                <button type="button" [class.is-on]="onglet() === 'historique'" (click)="onglet.set('historique')">
                  <mat-icon>history</mat-icon> Historique
                </button>
              </div>
            </div>

            @if (onglet() === 'echeances') {
              <div class="bea-ct-pane">
                <p class="bea-ct-help"><mat-icon>info</mat-icon>
                  Planifiez les dates clés du contrat (paiement, révision de prix, préavis, renouvellement…).
                  Une alerte est envoyée {{ c.alerte_jours }} jours avant chaque échéance.
                </p>
                <form class="bea-ct-grid bea-ct-inline" [formGroup]="echeanceForm" (ngSubmit)="addEcheance()">
                  <label>Type d’échéance
                    <select formControlName="type_echeance">
                      @for (t of typesEcheance; track t.code) { <option [value]="t.code">{{ t.label }}</option> }
                    </select>
                  </label>
                  <label>Date prévue <input type="date" formControlName="date_prevue" /></label>
                  <label>Montant (optionnel) <input type="number" formControlName="montant" /></label>
                  <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="echeanceForm.invalid || echeanceBusy()">
                    <mat-icon>{{ echeanceEditId() ? 'save' : 'add' }}</mat-icon>
                    {{ echeanceBusy() ? 'Enregistrement…' : echeanceEditId() ? 'Enregistrer' : 'Ajouter' }}
                  </button>
                </form>
                <ul class="bea-ct-list">
                  @for (e of c.echeances || []; track e.id) {
                    <li>
                      <strong>{{ dateFr(e.date_prevue) }}</strong>
                      <span>{{ typeEcheanceLabel(e.type_echeance) }}</span>
                      <span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statutLabel(e.statut) }}</span>
                      <span class="bea-ct-list__amount">{{ e.montant | montant }} {{ c.devise }}</span>
                      <span class="bea-ct-list__tools">
                        <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editerEcheanceFiche(e)"><mat-icon>edit</mat-icon></button>
                        <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerEcheance(e)"><mat-icon>delete</mat-icon></button>
                      </span>
                    </li>
                  } @empty { <li class="bea-ct-list__empty">Aucune échéance planifiée pour ce contrat.</li> }
                </ul>
              </div>
            }
            @if (onglet() === 'paiements') {
              <div class="bea-ct-pane">
                <p class="bea-ct-help"><mat-icon>info</mat-icon>
                  Enregistrez ici les règlements prévus et effectués pour ce contrat afin de suivre ce qui reste à payer.
                  C’est un suivi interne : aucun virement n’est exécuté depuis BEA DIGITAL.
                </p>
                <form class="bea-ct-grid bea-ct-inline" [formGroup]="paiementForm" (ngSubmit)="addPaiement()">
                  <label>Référence (facture, OV…) <input formControlName="reference" /></label>
                  <label>Date prévue <input type="date" formControlName="date_prevue" /></label>
                  <label>Date de paiement <input type="date" formControlName="date_reelle" /></label>
                  <label>Montant prévu <input type="number" formControlName="montant_prevu" /></label>
                  <label>Montant payé <input type="number" formControlName="montant_paye" /></label>
                  <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="paiementForm.invalid || paiementBusy()"><mat-icon>add</mat-icon> {{ paiementBusy() ? 'Enregistrement…' : 'Ajouter' }}</button>
                </form>
                <ul class="bea-ct-list">
                  @for (p of c.paiements || []; track p.id) {
                    <li>
                      <strong>{{ dateFr(p.date_prevue) }}</strong>
                      <span>{{ p.reference || 'Sans référence' }}</span>
                      <span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statutLabel(p.statut) }}</span>
                      <span class="bea-ct-list__amount">{{ p.montant_paye | montant }} / {{ p.montant_prevu | montant }} {{ c.devise }}</span>
                    </li>
                  } @empty { <li class="bea-ct-list__empty">Aucun paiement enregistré.</li> }
                </ul>
              </div>
            }
            @if (onglet() === 'documents') {
              <div class="bea-ct-pane">
                <p class="bea-ct-help"><mat-icon>info</mat-icon>
                  Déposez le contrat signé (scan PDF), les avenants et les factures. Utilisez « Télécharger le contrat (PDF) » en haut de page pour obtenir la fiche générée.
                </p>
                <bea-mg-ged moduleCode="contrats-echeances" entity="contrat" docType="CONTRAT" [entityId]="c.id" [reference]="c.reference" />
              </div>
            }
            @if (onglet() === 'historique') {
              <div class="bea-ct-pane">
                <ul class="bea-ct-list">
                  @for (h of c.historique || []; track h.id) {
                    <li>
                      <strong>{{ dateHeureFr(h.created_at) }}</strong>
                      <span>{{ actionLabel(h.action) }}</span>
                      <span>{{ h.user_nom || '—' }}</span>
                      @if (h.to_statut) { <span class="bea-ct-badge" [attr.data-tone]="h.to_statut">{{ statutLabel(h.to_statut) }}</span> }
                      @if (h.commentaire) { <em class="bea-ct-list__comment">{{ h.commentaire }}</em> }
                    </li>
                  } @empty { <li class="bea-ct-list__empty">Aucun historique.</li> }
                </ul>
              </div>
            }
          </div>
        }
      }
    </section>
  `,
})
export class ContratsListComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(
    () => (this.mode() === 'nouveau' || this.mode() === 'fiche') && this.form.dirty && !this.saving(),
    () => this.form,
  );
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly dialogs = inject(UiDialogService);

  readonly statuts = ['BROUILLON', 'EN_PREPARATION', 'EN_VALIDATION', 'ACTIF', 'SUSPENDU', 'EXPIRE', 'ARCHIVE', 'REJETE', 'ANNULE'];
  readonly mode = signal<'liste' | 'alertes' | 'echeances' | 'paiements' | 'renouvellements' | 'nouveau' | 'fiche'>('liste');
  readonly titre = signal('Contrats');
  readonly contrats = signal<Contrat[]>([]);
  readonly alertes = signal<Alerte[]>([]);
  readonly echeances = signal<Array<Echeance & { reference: string; titre: string; contrat_id: string; jours: number }>>([]);
  readonly paiements = signal<Array<Paiement & { reference: string; titre: string; contrat_id: string; paiement_ref: string | null; reste: number }>>([]);
  readonly paiementStatut = signal('');
  readonly paiementsTotaux = computed(() =>
    this.paiements().reduce(
      (t, p) => ({
        prevu: t.prevu + (p.montant_prevu || 0),
        paye: t.paye + (p.montant_paye || 0),
        reste: t.reste + (p.reste || 0),
        retard: t.retard + (p.statut === 'EN_RETARD' ? 1 : 0),
      }),
      { prevu: 0, paye: 0, reste: 0, retard: 0 },
    ),
  );
  readonly fiche = signal<Contrat | null>(null);
  readonly contratId = signal<string | null>(null);
  readonly saving = signal(false);
  readonly actionEnCours = signal(false);
  readonly echeanceBusy = signal(false);
  readonly paiementBusy = signal(false);
  readonly fieldErrors = signal<Record<string, string>>({});
  readonly onglet = signal<'echeances' | 'paiements' | 'documents' | 'historique'>('echeances');
  readonly apercuOuvert = signal(false);
  readonly apercu = signal<Contrat | null>(null);
  readonly telechargement = signal(false);
  readonly etapes = ETAPES;
  readonly typesEcheance = TYPES_ECHEANCE;
  readonly types = signal<Array<{ code: string; libelle: string }>>([]);
  readonly fournisseurs = signal<RefItem[]>([]);
  readonly agences = signal<RefItem[]>([]);
  readonly responsables = signal<RefItem[]>([]);

  readonly filtres = this.fb.nonNullable.group({ q: [''], statut: [''], horizon: [''] });
  readonly form = this.fb.nonNullable.group({
    titre: ['', Validators.required],
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
    montant_ht: [null as number | null],
    taux_tva: [0],
    periodicite: ['ANNUEL'],
    mode_paiement: [''],
    ref_paiement: [''],
    alerte_jours: [30],
    observation: [''],
  });
  readonly modesPaiement = signal<string[]>([...MODES_PAIEMENT]);
  readonly echeanceOuverte = signal(false);
  readonly echeanceEditId = signal<string | null>(null);
  readonly echeanceForm = this.fb.nonNullable.group({
    contrat_id: [''],
    type_echeance: ['PAIEMENT'],
    date_prevue: ['', Validators.required],
    date_reelle: [''],
    montant: [null as number | null],
    statut: ['A_VENIR'],
    commentaire: [''],
  });
  readonly paiementForm = this.fb.nonNullable.group({
    reference: [''],
    date_prevue: ['', Validators.required],
    date_reelle: [''],
    montant_prevu: [0],
    montant_paye: [0],
  });

  ngOnInit(): void {
    this.route.url.subscribe(() => this.sync());
    this.route.queryParamMap.subscribe(() => this.sync());
  }

  private sync(): void {
    const path = this.route.snapshot.routeConfig?.path ?? '';
    const id = this.route.snapshot.paramMap.get('id');
    this.fermerApercu();
    this.fieldErrors.set({});
    if (path === 'nouveau') {
      this.mode.set('nouveau');
      this.titre.set('Nouveau contrat');
      this.contratId.set(null);
      this.fiche.set(null);
      this.form.reset({
        titre: '', numero_contrat: '', description: '', type_contrat: 'AUTRE', devise: 'MRU',
        fournisseur_id: '', agence_id: '', responsable_id: '', date_signature: '',
        date_debut: new Date().toISOString().slice(0, 10), date_fin: '', montant_ht: null,
        taux_tva: 0, periodicite: 'ANNUEL', mode_paiement: '', ref_paiement: '', alerte_jours: 30, observation: '',
      });
      this.modesPaiement.set([...MODES_PAIEMENT]);
      this.loadRefs();
      return;
    }
    if (id && path === ':id') {
      this.mode.set('fiche');
      this.contratId.set(id);
      this.loadRefs();
      this.loadOne(id);
      return;
    }
    if (path === 'alertes') {
      this.mode.set('alertes');
      this.titre.set('Alertes');
      this.api.get<Alerte[]>('/mg/contrats/alertes').subscribe({
        next: (rows) => this.alertes.set(rows),
        error: (e) => this.fail(e),
      });
      return;
    }
    if (path === 'echeances') {
      this.mode.set('echeances');
      this.titre.set('Échéances');
      this.api.get<Array<Echeance & { reference: string; titre: string; contrat_id: string; jours: number }>>('/mg/contrats/echeances').subscribe({
        next: (rows) => this.echeances.set(rows),
        error: (e) => this.fail(e),
      });
      return;
    }
    if (path === 'paiements') {
      this.mode.set('paiements');
      this.titre.set('Paiements');
      const statut = this.route.snapshot.queryParamMap.get('statut') || '';
      this.paiementStatut.set(statut);
      const params: Record<string, string> = {};
      if (statut) params['statut'] = statut;
      this.api.get<Array<Paiement & { reference: string; titre: string; contrat_id: string; paiement_ref: string | null; reste: number }>>('/mg/contrats/paiements', params).subscribe({
        next: (rows) => this.paiements.set(rows),
        error: (e) => this.fail(e),
      });
      return;
    }
    this.mode.set(path === 'renouvellements' ? 'renouvellements' : 'liste');
    this.titre.set(path === 'renouvellements' ? 'Renouvellements' : 'Contrats');
    const qp = this.route.snapshot.queryParamMap;
    this.filtres.patchValue({
      statut: qp.get('statut') || '',
      horizon: qp.get('horizon') || '',
    });
    if (!this.types().length) {
      this.api.get<Array<{ code: string; libelle: string }>>('/mg/contrats/types').subscribe({
        next: (rows) => this.types.set(rows),
        error: () => undefined,
      });
    }
    this.loadListe();
  }

  filtrerPaiements(statut: string): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { statut: statut || null } });
  }

  loadListe(): void {
    const raw = this.filtres.getRawValue();
    const params: Record<string, string> = {};
    if (raw.q.trim()) params['q'] = raw.q.trim();
    if (raw.statut) params['statut'] = raw.statut;
    if (raw.horizon) params['horizon'] = raw.horizon;
    if (this.mode() === 'renouvellements') params['renouveles'] = 'true';
    this.api.get<Contrat[]>('/mg/contrats', params).subscribe({
      next: (rows) => this.contrats.set(rows),
      error: (e) => this.fail(e),
    });
  }

  loadRefs(): void {
    this.api.get<Array<{ code: string; libelle: string }>>('/mg/contrats/types').subscribe({
      next: (rows) => this.types.set(rows),
      error: () => undefined,
    });
    this.api.get<RefItem[]>('/mg/contrats/fournisseurs').subscribe({
      next: (rows) => this.fournisseurs.set(rows),
      error: () => undefined,
    });
    this.api.get<RefItem[]>('/mg/contrats/agences').subscribe({
      next: (rows) => this.agences.set(rows),
      error: () => undefined,
    });
    this.api.get<RefItem[]>('/mg/contrats/responsables').subscribe({
      next: (rows) => this.responsables.set(rows),
      error: () => undefined,
    });
  }

  loadOne(id: string): void {
    this.api.get<Contrat>(`/mg/contrats/${id}`).subscribe({
      next: (c) => {
        this.fiche.set(c);
        this.titre.set(c.reference);
        const mode = c.mode_paiement ?? '';
        this.modesPaiement.set(
          mode && !(MODES_PAIEMENT as readonly string[]).includes(mode) ? [...MODES_PAIEMENT, mode] : [...MODES_PAIEMENT],
        );
        this.form.patchValue({
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
          montant_ht: c.montant_ht,
          taux_tva: c.taux_tva ?? 0,
          periodicite: c.periodicite || 'ANNUEL',
          mode_paiement: mode,
          ref_paiement: c.ref_paiement ?? '',
          alerte_jours: c.alerte_jours ?? 30,
          observation: c.observation ?? '',
        });
        this.form.markAsPristine();
      },
      error: (e) => this.fail(e, 'Contrat introuvable'),
    });
  }

  onModePaiementChange(): void {
    if (!MODES_AVEC_REF.has(this.form.controls.mode_paiement.value)) {
      this.form.controls.ref_paiement.setValue('');
    }
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.feedback.warning({ title: 'Formulaire incomplet', message: 'Renseignez au minimum l’objet et la date de début.' });
      return;
    }
    this.fieldErrors.set({});
    const raw = this.form.getRawValue();
    const body = {
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
      montant_ht: raw.montant_ht,
    };
    const id = this.contratId();
    this.feedback
      .run(
        () => (id ? this.api.patch<Contrat>(`/mg/contrats/${id}`, body) : this.api.post<Contrat>('/mg/contrats', body)),
        {
          loading: 'Enregistrement du contrat…',
          busy: this.saving,
          idempotent: !id,
          errorTitle: 'Échec de l’enregistrement',
          errorHint: 'Vos données saisies ont été conservées.',
          onError: (e) => this.fieldErrors.set(e.fieldErrors),
          success: (c) => ({
            title: id ? 'Contrat mis à jour' : 'Contrat créé avec succès',
            details: [
              { label: 'Référence', value: c.reference },
              { label: 'Objet', value: c.titre },
              { label: 'Statut', value: this.statutLabel(c.statut) },
            ],
          }),
        },
      )
      .subscribe((c) => {
        this.form.markAsPristine();
        if (id) {
          this.fiche.set(c);
        } else {
          void this.router.navigateByUrl(`/contrats-echeances/${c.id}`);
        }
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
        success: (res) => this.transitionSucces(res, cfg.success),
      })
      .subscribe((res) => this.fiche.set(res));
  }

  demanderMotif(action: 'annuler' | 'rejeter'): void {
    const c = this.fiche();
    if (!c) return;
    const rejet = action === 'rejeter';
    this.feedback
      .runWithReason(
        (motif) => this.api.post<Contrat>(`/mg/contrats/${c.id}/transition`, { action, commentaire: motif }),
        {
          reason: {
            ...this.dialogs.preset(
              rejet ? 'rejet' : 'annulation',
              rejet
                ? `Rejeter le contrat ${c.reference} « ${c.titre} » ?`
                : `Annuler le contrat ${c.reference} « ${c.titre} » ?`,
              rejet ? 'Rejeter le contrat' : 'Annuler le contrat',
              rejet
                ? 'Le responsable sera notifié du rejet et de son motif.'
                : 'Le contrat passera en lecture seule. Cette action ne peut pas être annulée.',
            ),
            confirmLabel: rejet ? 'Rejeter' : 'Annuler le contrat',
            cancelLabel: 'Retour',
            reasonLabel: rejet ? 'Motif du rejet' : 'Motif de l’annulation',
          },
          loading: rejet ? 'Rejet en cours…' : 'Annulation en cours…',
          busy: this.actionEnCours,
          errorTitle: rejet ? 'Échec du rejet' : 'Échec de l’annulation',
          success: (res) => this.transitionSucces(res, rejet ? 'Contrat rejeté' : 'Contrat annulé'),
        },
      )
      .subscribe((res) => this.fiche.set(res));
  }

  renouveler(): void {
    const c = this.fiche();
    if (!c) return;
    this.feedback
      .run(() => this.api.post<Contrat>(`/mg/contrats/${c.id}/renouveler`, {}), {
        confirm: {
          action: 'renouvellement',
          message: `Préparer le renouvellement du contrat ${c.reference} ?`,
          hint: 'Un nouveau contrat en brouillon sera créé à partir de celui-ci, avec une période qui démarre le lendemain de la fin actuelle.',
        },
        loading: 'Préparation du renouvellement…',
        busy: this.actionEnCours,
        idempotent: true,
        errorTitle: 'Échec du renouvellement',
        success: (n) => ({
          title: 'Renouvellement préparé',
          message: 'Le nouveau contrat est en brouillon : vérifiez-le puis soumettez-le.',
          details: [
            { label: 'Nouvelle référence', value: n.reference },
            { label: 'Issu de', value: c.reference },
          ],
        }),
      })
      .subscribe((n) => void this.router.navigateByUrl(`/contrats-echeances/${n.id}`));
  }

  supprimer(): void {
    const c = this.fiche();
    if (!c) return;
    this.feedback
      .run(() => this.api.delete(`/mg/contrats/${c.id}`), {
        confirm: {
          action: 'suppression',
          message: `Supprimer le brouillon ${c.reference} ?`,
          hint: 'Le contrat sera retiré du registre ; son historique reste conservé.',
        },
        loading: 'Suppression…',
        busy: this.actionEnCours,
        errorTitle: 'Échec de la suppression',
        success: { title: 'Brouillon supprimé', details: [{ label: 'Référence', value: c.reference }] },
      })
      .subscribe(() => {
        this.form.markAsPristine();
        void this.router.navigateByUrl('/contrats-echeances/liste');
      });
  }

  supprimerContrat(c: Contrat): void {
    this.feedback
      .run(() => this.api.delete(`/mg/contrats/${c.id}`), {
        confirm: {
          action: 'suppression',
          message: `Retirer le contrat ${c.reference} « ${c.titre} » du registre ?`,
          hint: 'L’historique reste conservé en base.',
        },
        loading: 'Suppression…',
        errorTitle: 'Échec de la suppression',
        success: { title: 'Contrat retiré du registre', details: [{ label: 'Référence', value: c.reference }] },
      })
      .subscribe(() => this.loadListe());
  }

  private transitionSucces(c: Contrat, title: string): FeedbackMessage {
    return {
      title,
      message: this.statutAide(c.statut),
      details: [
        { label: 'Contrat', value: c.reference },
        { label: 'Statut', value: this.statutLabel(c.statut) },
      ],
    };
  }

  ouvrirEcheance(): void {
    this.echeanceEditId.set(null);
    this.echeanceForm.reset({
      contrat_id: '', type_echeance: 'PAIEMENT', date_prevue: '', date_reelle: '',
      montant: null, statut: 'A_VENIR', commentaire: '',
    });
    this.echeanceOuverte.set(true);
    if (!this.contrats().length) this.loadListe();
  }

  modifierEcheance(e: Echeance & { contrat_id: string; date_reelle?: string | null; commentaire?: string | null }): void {
    this.echeanceEditId.set(e.id);
    this.echeanceForm.patchValue({
      contrat_id: e.contrat_id,
      type_echeance: e.type_echeance,
      date_prevue: e.date_prevue,
      date_reelle: e.date_reelle ?? '',
      montant: e.montant,
      statut: e.statut,
      commentaire: e.commentaire ?? '',
    });
    this.echeanceOuverte.set(true);
    if (!this.contrats().length) this.loadListe();
  }

  fermerEcheance(): void {
    this.echeanceOuverte.set(false);
    this.echeanceEditId.set(null);
  }

  sauverEcheance(): void {
    if (this.echeanceForm.invalid) return;
    const raw = this.echeanceForm.getRawValue();
    const body = {
      type_echeance: raw.type_echeance,
      date_prevue: raw.date_prevue,
      date_reelle: raw.date_reelle || null,
      montant: raw.montant,
      statut: raw.statut,
      commentaire: raw.commentaire || null,
    };
    const editId = this.echeanceEditId();
    if (!editId && !raw.contrat_id) {
      this.feedback.warning({ title: 'Contrat manquant', message: 'Choisissez le contrat concerné par cette échéance.' });
      return;
    }
    this.feedback
      .run(
        () =>
          editId
            ? this.api.patch(`/mg/contrats/echeances/${editId}`, body)
            : this.api.post(`/mg/contrats/${raw.contrat_id}/echeances`, body),
        {
          loading: 'Enregistrement de l’échéance…',
          busy: this.echeanceBusy,
          idempotent: !editId,
          errorTitle: 'Échec de l’enregistrement',
          errorHint: 'Vos données saisies ont été conservées.',
          success: {
            title: editId ? 'Échéance mise à jour' : 'Échéance ajoutée',
            details: [
              { label: 'Type', value: this.typeEcheanceLabel(raw.type_echeance) },
              { label: 'Date', value: this.dateFr(raw.date_prevue) },
            ],
          },
        },
      )
      .subscribe(() => {
        this.fermerEcheance();
        this.sync();
      });
  }

  editerEcheanceFiche(e: Echeance): void {
    this.echeanceEditId.set(e.id);
    this.echeanceForm.patchValue({
      type_echeance: e.type_echeance,
      date_prevue: e.date_prevue,
      montant: e.montant,
      statut: e.statut,
      commentaire: e.commentaire ?? '',
    });
  }

  supprimerEcheance(e: { id: string; type_echeance: string; date_prevue: string }): void {
    this.feedback
      .run(() => this.api.delete(`/mg/contrats/echeances/${e.id}`), {
        confirm: {
          action: 'suppression',
          message: `Supprimer l’échéance « ${this.typeEcheanceLabel(e.type_echeance)} » du ${this.dateFr(e.date_prevue)} ?`,
          hint: 'Les alertes liées à cette échéance ne seront plus envoyées.',
        },
        loading: 'Suppression…',
        busy: this.echeanceBusy,
        errorTitle: 'Échec de la suppression',
        success: { title: 'Échéance supprimée' },
      })
      .subscribe(() => this.sync());
  }

  addEcheance(): void {
    const id = this.contratId();
    if (!id || this.echeanceForm.invalid) return;
    const raw = this.echeanceForm.getRawValue();
    const body = {
      type_echeance: raw.type_echeance,
      date_prevue: raw.date_prevue,
      date_reelle: raw.date_reelle || null,
      montant: raw.montant,
      statut: raw.statut,
      commentaire: raw.commentaire || null,
    };
    const editId = this.echeanceEditId();
    this.feedback
      .run(
        () =>
          editId
            ? this.api.patch<Contrat>(`/mg/contrats/echeances/${editId}`, body)
            : this.api.post<Contrat>(`/mg/contrats/${id}/echeances`, body),
        {
          loading: 'Enregistrement de l’échéance…',
          busy: this.echeanceBusy,
          idempotent: !editId,
          errorTitle: 'Échec de l’enregistrement',
          errorHint: 'Vos données saisies ont été conservées.',
          success: {
            title: editId ? 'Échéance mise à jour' : 'Échéance ajoutée',
            details: [
              { label: 'Type', value: this.typeEcheanceLabel(raw.type_echeance) },
              { label: 'Date', value: this.dateFr(raw.date_prevue) },
            ],
          },
        },
      )
      .subscribe((c) => {
        if (editId) this.loadOne(id);
        else this.fiche.set(c);
        this.echeanceEditId.set(null);
        this.echeanceForm.reset({
          contrat_id: '', type_echeance: 'PAIEMENT', date_prevue: '', date_reelle: '',
          montant: null, statut: 'A_VENIR', commentaire: '',
        });
      });
  }

  addPaiement(): void {
    const id = this.contratId();
    if (!id || this.paiementForm.invalid) return;
    const raw = this.paiementForm.getRawValue();
    this.feedback
      .run(
        () =>
          this.api.post<Contrat>(`/mg/contrats/${id}/paiements`, {
            reference: raw.reference || null,
            date_prevue: raw.date_prevue,
            date_reelle: raw.date_reelle || null,
            montant_prevu: raw.montant_prevu,
            montant_paye: raw.montant_paye,
          }),
        {
          loading: 'Enregistrement du paiement…',
          busy: this.paiementBusy,
          idempotent: true,
          errorTitle: 'Échec de l’enregistrement',
          errorHint: 'Vos données saisies ont été conservées.',
          success: (c) => ({
            title: 'Paiement enregistré',
            details: [
              { label: 'Date prévue', value: this.dateFr(raw.date_prevue) },
              { label: 'Payé / prévu', value: `${raw.montant_paye} / ${raw.montant_prevu} ${c.devise}` },
            ],
          }),
        },
      )
      .subscribe((c) => {
        this.fiche.set(c);
        this.paiementForm.reset({ reference: '', date_prevue: '', date_reelle: '', montant_prevu: 0, montant_paye: 0 });
      });
  }

  voir(c: Contrat): void {
    this.apercu.set(null);
    this.apercuOuvert.set(true);
    this.api.get<Contrat>(`/mg/contrats/${c.id}`).subscribe({
      next: (detail) => this.apercu.set(detail),
      error: (e) => {
        this.apercuOuvert.set(false);
        this.fail(e, 'Ouverture du contrat impossible');
      },
    });
  }

  @HostListener('document:keydown.escape')
  fermerApercu(): void {
    this.apercuOuvert.set(false);
    this.apercu.set(null);
  }

  telechargerPdf(c: Contrat): void {
    this.feedback
      .run(() => this.api.download(`/mg/contrats/${c.id}/pdf`), {
        loading: 'Préparation du PDF…',
        busy: this.telechargement,
        errorTitle: 'Téléchargement impossible',
        success: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `Contrat-${c.reference}.pdf`;
          a.click();
          URL.revokeObjectURL(url);
          return { title: 'Téléchargement prêt', details: [{ label: 'Fichier', value: `Contrat-${c.reference}.pdf` }] };
        },
      })
      .subscribe();
  }

  fieldError(name: string): string | null {
    return this.fieldErrors()[name] ?? null;
  }

  statutLabel(code: string | null | undefined): string {
    return (code && STATUT_LABELS[code]) || code || '—';
  }

  statutAide(code: string): string {
    return STATUT_AIDE[code] ?? '';
  }

  etapeIndex(statut: string): number {
    switch (statut) {
      case 'BROUILLON':
      case 'EN_PREPARATION':
        return 0;
      case 'EN_VALIDATION':
      case 'REJETE':
        return 1;
      case 'ACTIF':
      case 'SUSPENDU':
        return 2;
      default:
        return 3;
    }
  }

  typeLabel(code: string | null | undefined): string {
    return this.types().find((t) => t.code === code)?.libelle ?? code ?? '—';
  }

  typeEcheanceLabel(code: string): string {
    return TYPES_ECHEANCE.find((t) => t.code === code)?.label ?? code;
  }

  periodiciteLabel(code: string): string {
    return PERIODICITE_LABELS[code] ?? code;
  }

  actionLabel(code: string): string {
    return ACTION_LABELS[code] ?? code;
  }

  dateFr(iso: string | null | undefined): string {
    if (!iso) return '—';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return d && m && y ? `${d}/${m}/${y}` : iso;
  }

  dateHeureFr(iso: string): string {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
  }

  joursLabel(jours: number | null | undefined): string {
    if (jours === null || jours === undefined) return '';
    if (jours === 0) return 'Aujourd’hui';
    return jours > 0 ? `Dans ${jours} j` : `Retard ${-jours} j`;
  }

  joursRestants(iso: string | null | undefined): string | null {
    if (!iso) return null;
    const cible = new Date(`${iso.slice(0, 10)}T00:00:00`);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const jours = Math.round((cible.getTime() - today.getTime()) / 86_400_000);
    if (jours === 0) return 'Aujourd’hui';
    return jours > 0 ? `Dans ${jours} jour${jours > 1 ? 's' : ''}` : `En retard de ${-jours} jour${jours < -1 ? 's' : ''}`;
  }

  private fail(err: unknown, title = 'Chargement impossible'): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, title));
  }
}
