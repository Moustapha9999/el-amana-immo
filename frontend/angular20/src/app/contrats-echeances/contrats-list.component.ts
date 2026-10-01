import { ChangeDetectionStrategy, Component, DestroyRef, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import {
  ALERTE_TYPE_LABELS,
  ARenouveler,
  Alerte,
  Contrat,
  ContratsConfig,
  ETATS_FILTRE,
  EcheanceRow,
  PaiementRow,
  RECONDUCTION_LABELS,
  RefItem,
  STATUTS_CONTRAT,
  TYPES_ECHEANCE,
  aujourdhui,
  dateFr,
  joursLabel,
  num,
  statutLabel,
  typeEcheanceLabel,
} from './contrats.models';

type Mode = 'liste' | 'alertes' | 'echeances' | 'paiements' | 'renouvellements';

const TITRES: Record<Mode, { titre: string; sous: string }> = {
  liste: { titre: 'Registre des contrats', sous: 'Recherche, filtres par statut, état, type et agence.' },
  alertes: { titre: 'Alertes', sous: 'Fins de contrat, préavis, paiements dus ou en retard, fiches incomplètes.' },
  echeances: { titre: 'Échéances', sous: 'Échéancier consolidé de tous les contrats : à venir, dues, en retard, payées.' },
  paiements: { titre: 'Paiements', sous: 'Règlements enregistrés et rapprochement prévu / payé.' },
  renouvellements: { titre: 'Renouvellements', sous: 'Contrats arrivant à terme : reconduction tacite ou expresse.' },
};

const SUPPRIMABLES = new Set(['BROUILLON', 'EN_PREPARATION', 'REJETE', 'ANNULE']);

@Component({
  selector: 'bea-contrats-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances</p>
          <h1>{{ entete().titre }}</h1>
          <p class="bea-ct-head__sub">
            {{ entete().sous }}
            @if (config()?.agence_scope; as s) { <span class="bea-ct-badge" data-tone="INFO">Périmètre : {{ s.libelle || 'votre agence' }}</span> }
          </p>
        </div>
        <div class="bea-mg__actions">
          @if (mode() === 'liste' && cap().create) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/contrats-echeances/nouveau"><mat-icon>add</mat-icon> Nouveau contrat</a>
          }
          @if (mode() === 'paiements' && cap().manage) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirPaiement()"><mat-icon>add</mat-icon> Nouveau paiement</button>
          }
          @if (mode() === 'alertes' && cap().manage) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="envoyerRappels()"><mat-icon>notifications_active</mat-icon> Envoyer les rappels</button>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Actualiser" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      @if (mode() === 'liste') {
        <form class="bea-mg__search bea-ct-filters" [formGroup]="filtres" (ngSubmit)="appliquerFiltres()">
          <label class="bea-mg__field bea-ct-filters__q">Recherche
            <input formControlName="q" placeholder="Référence, objet, n° contrat, fournisseur, agence, responsable" />
          </label>
          <label class="bea-mg__field">Statut
            <select formControlName="statut" (change)="appliquerFiltres()">
              <option value="">Tous</option>
              @for (s of statuts; track s) { <option [value]="s">{{ statut(s) }}</option> }
            </select>
          </label>
          <label class="bea-mg__field">État
            <select formControlName="etat" (change)="appliquerFiltres()">
              <option value="">Tous</option>
              @for (e of etats; track e.code) { <option [value]="e.code">{{ e.label }}</option> }
            </select>
          </label>
          <label class="bea-mg__field">Type
            <select formControlName="type_contrat" (change)="appliquerFiltres()">
              <option value="">Tous</option>
              @for (t of types(); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
            </select>
          </label>
          @if (!config()?.agence_scope) {
            <label class="bea-mg__field">Agence
              <select formControlName="agence_id" (change)="appliquerFiltres()">
                <option value="">Toutes</option>
                @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
              </select>
            </label>
          }
          <label class="bea-mg__field">Fin de contrat
            <select formControlName="horizon" (change)="appliquerFiltres()">
              <option value="">Toutes</option>
              <option value="retard">Date dépassée</option>
              <option value="30">≤ 30 jours</option>
              <option value="60">≤ 60 jours</option>
              <option value="90">≤ 90 jours</option>
            </select>
          </label>
          <div class="bea-ct-filters__btns">
            <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Filtrer</button>
            @if (filtresActifs()) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
            }
          </div>
        </form>
        <div class="bea-mg__table-scroll bea-ct-table-wrap">
          <table class="bea-mg__table bea-ct-table">
            <thead>
              <tr>
                <th>Référence</th><th>Objet</th><th>Fournisseur</th><th>Agence</th><th>Responsable</th>
                <th>Fin</th><th class="is-num">Montant TTC</th><th>Statut</th><th class="is-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (c of contrats(); track c.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 30 : 0">
                  <td class="is-nowrap">
                    <a class="bea-ct-link" [routerLink]="['/contrats-echeances', c.id]"><code class="bea-mg__code">{{ c.reference }}</code></a>
                    <small class="bea-ct-sub">{{ typeLabel(c.type_contrat) }}{{ c.version > 1 ? ' · v' + c.version : '' }}</small>
                  </td>
                  <td class="is-wide">
                    <strong class="bea-ct-strong">{{ c.titre }}</strong>
                    @if (c.numero_contrat) { <small class="bea-ct-sub">N° {{ c.numero_contrat }}</small> }
                  </td>
                  <td class="is-wide">{{ c.fournisseur_snapshot || '—' }}</td>
                  <td class="is-wide">{{ c.agence_libelle_snapshot || '—' }}</td>
                  <td class="is-wide">{{ c.responsable_nom || '—' }}</td>
                  <td class="is-nowrap">
                    {{ date(c.date_fin) }}
                    @if (c.jours_restants !== null && enVigueur(c.statut)) { <small class="bea-ct-sub" [class.bea-ct-neg]="c.jours_restants < 0">{{ jours(c.jours_restants) }}</small> }
                  </td>
                  <td class="is-nowrap is-num">{{ c.montant | montant }} {{ c.devise }}</td>
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="c.etat">{{ statut(c.etat) }}</span></td>
                  <td class="bea-mg__actions-cell is-nowrap">
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', c.id]" title="Ouvrir la fiche"><mat-icon>{{ cap().manage ? 'edit' : 'visibility' }}</mat-icon></a>
                    @if (cap().manage && supprimable(c.statut)) {
                      <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Retirer du registre" [disabled]="busy()" (click)="supprimerContrat(c)"><mat-icon>delete</mat-icon></button>
                    }
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="9"><div class="bea-ct-empty"><mat-icon>description</mat-icon><p>{{ filtresActifs() ? 'Aucun contrat ne correspond aux filtres.' : 'Aucun contrat enregistré.' }}</p></div></td></tr>
              }
            </tbody>
          </table>
        </div>
        @if (contrats().length) {
          <p class="bea-ct-count">{{ contrats().length }} contrat{{ contrats().length > 1 ? 's' : '' }} · {{ totalListe() | montant }} TTC</p>
        }
      }

      @if (mode() === 'alertes') {
        <div class="bea-nf-kpi">
          @for (n of niveaux; track n) {
            <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" [class.is-on]="filtreNiveau() === n" [attr.data-tone]="n" (click)="filtreNiveau.set(filtreNiveau() === n ? '' : n)">
              <p>{{ statut(n) }}</p><strong>{{ compteNiveau(n) }}</strong>
            </button>
          }
        </div>
        <div class="bea-mg__search">
          <label class="bea-mg__field">Type d’alerte
            <select [value]="filtreType()" (change)="filtreType.set($any($event.target).value)">
              <option value="">Tous</option>
              @for (t of typesAlerte; track t[0]) { <option [value]="t[0]">{{ t[1] }}</option> }
            </select>
          </label>
        </div>
        <div class="bea-mg__table-scroll bea-ct-table-wrap">
          <table class="bea-mg__table bea-ct-table">
            <thead><tr><th>Niveau</th><th>Type</th><th>Contrat</th><th>Alerte</th><th>Responsable</th><th>Date</th><th class="is-actions">Actions</th></tr></thead>
            <tbody>
              @for (a of alertesFiltrees(); track $index; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 30 : 0">
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="a.niveau">{{ statut(a.niveau) }}</span></td>
                  <td class="is-nowrap">{{ typeAlerte(a.type) }}</td>
                  <td class="is-wide"><code class="bea-mg__code">{{ a.reference }}</code><small class="bea-ct-sub">{{ a.titre }}{{ a.fournisseur ? ' · ' + a.fournisseur : '' }}</small></td>
                  <td class="is-wide"><strong class="bea-ct-strong">{{ a.message }}</strong></td>
                  <td class="is-wide">{{ a.responsable || '—' }}</td>
                  <td class="is-nowrap">{{ date(a.echeance) }}@if (a.jours !== null) { <small class="bea-ct-sub" [class.bea-ct-neg]="a.jours < 0">{{ jours(a.jours) }}</small> }</td>
                  <td class="bea-mg__actions-cell"><a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', a.contrat_id]" title="Ouvrir le contrat"><mat-icon>open_in_new</mat-icon></a></td>
                </tr>
              } @empty {
                <tr><td colspan="7"><div class="bea-ct-empty"><mat-icon>notifications_none</mat-icon><p>Aucune alerte en cours.</p></div></td></tr>
              }
            </tbody>
          </table>
        </div>
        <p class="bea-ct-help"><mat-icon>schedule_send</mat-icon> Rappels automatiques quotidiens (7 h 30) aux responsables : au délai d’alerte du contrat, J-30, J-15, J-7, J-1, jour J, puis chaque semaine en cas de retard (notification + e-mail si configuré).</p>
      }

      @if (mode() === 'echeances') {
        <div class="bea-nf-kpi">
          <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" data-tone="A_VENIR" [class.is-on]="filtreEcheance.value.statut === 'A_VENIR'" (click)="filtrerEcheancesStatut('A_VENIR')"><p>À venir</p><strong>{{ kpiEcheances().aVenir }}</strong></button>
          <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" data-tone="DUE" [class.is-on]="filtreEcheance.value.statut === 'DUE'" (click)="filtrerEcheancesStatut('DUE')"><p>Dues</p><strong>{{ kpiEcheances().dues }}</strong></button>
          <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" data-tone="EN_RETARD" [class.is-on]="filtreEcheance.value.statut === 'EN_RETARD'" (click)="filtrerEcheancesStatut('EN_RETARD')"><p>En retard</p><strong>{{ kpiEcheances().retard }}</strong><small>{{ kpiEcheances().resteRetard | montant }}</small></button>
          <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" data-tone="PAYEE" [class.is-on]="filtreEcheance.value.statut === 'PAYEE'" (click)="filtrerEcheancesStatut('PAYEE')"><p>Payées</p><strong>{{ kpiEcheances().payees }}</strong></button>
        </div>
        <form class="bea-mg__search" [formGroup]="filtreEcheance">
          <label class="bea-mg__field">Horizon
            <select formControlName="horizon" (change)="chargerEcheances()">
              <option value="">Toutes</option>
              <option value="retard">Passées</option>
              <option value="7">≤ 7 jours</option>
              <option value="30">≤ 30 jours</option>
              <option value="60">≤ 60 jours</option>
              <option value="90">≤ 90 jours</option>
            </select>
          </label>
          <label class="bea-mg__field">Statut
            <select formControlName="statut" (change)="chargerEcheances()">
              <option value="">Tous</option>
              <option value="A_VENIR">À venir</option>
              <option value="DUE">Due</option>
              <option value="EN_RETARD">En retard</option>
              <option value="PAYEE">Payée</option>
              <option value="FAITE">Réalisée</option>
              <option value="ANNULEE">Annulée</option>
            </select>
          </label>
          <label class="bea-mg__field">Type
            <select formControlName="type_echeance" (change)="chargerEcheances()">
              <option value="">Tous</option>
              @for (t of typesEcheance; track t.code) { <option [value]="t.code">{{ t.label }}</option> }
            </select>
          </label>
        </form>
        <div class="bea-mg__table-scroll bea-ct-table-wrap">
          <table class="bea-mg__table bea-ct-table">
            <thead><tr><th>Date</th><th>Contrat</th><th>Type</th><th>Agence</th><th class="is-num">Montant</th><th class="is-num">Payé</th><th class="is-num">Reste</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
            <tbody>
              @for (e of echeances(); track e.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 30 : 0">
                  <td class="is-nowrap"><strong>{{ date(e.date_prevue) }}</strong><small class="bea-ct-sub" [class.bea-ct-neg]="e.jours < 0 && e.statut === 'EN_RETARD'">{{ jours(e.jours) }}</small></td>
                  <td class="is-wide"><code class="bea-mg__code">{{ e.reference }}</code><small class="bea-ct-sub">{{ e.titre }}{{ e.fournisseur ? ' · ' + e.fournisseur : '' }}</small></td>
                  <td class="is-nowrap">{{ typeEcheance(e.type_echeance) }}</td>
                  <td class="is-wide">{{ e.agence || '—' }}</td>
                  <td class="is-nowrap is-num">{{ e.montant === null ? '—' : (e.montant | montant) }}</td>
                  <td class="is-nowrap is-num">{{ e.montant_paye | montant }}</td>
                  <td class="is-nowrap is-num"><strong class="bea-ct-strong">{{ e.reste | montant }}</strong></td>
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statut(e.statut) }}</span></td>
                  <td class="bea-mg__actions-cell is-nowrap">
                    @if (cap().manage && e.type_echeance === 'PAIEMENT' && e.reste > 0 && regleable(e.contrat_statut)) {
                      <button type="button" class="bea-mg__icon-btn" title="Régler cette échéance" (click)="regler(e)"><mat-icon>price_check</mat-icon></button>
                    }
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', e.contrat_id]" title="Ouvrir le contrat"><mat-icon>open_in_new</mat-icon></a>
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="9"><div class="bea-ct-empty"><mat-icon>event</mat-icon><p>Aucune échéance pour ces critères.</p><small>Les échéanciers sont générés automatiquement à la validation des contrats.</small></div></td></tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'paiements') {
        <div class="bea-nf-kpi">
          <article class="bea-nf-kpi__card"><p>Montant prévu</p><strong>{{ paiementsTotaux().prevu | montant }}</strong></article>
          <article class="bea-nf-kpi__card"><p>Montant versé</p><strong>{{ paiementsTotaux().paye | montant }}</strong></article>
          <article class="bea-nf-kpi__card"><p>Écart (versé − prévu)</p><strong [class.bea-ct-neg]="paiementsTotaux().ecart < 0">{{ paiementsTotaux().ecart | montant }}</strong></article>
          <article class="bea-nf-kpi__card" data-tone="EN_RETARD"><p>En retard</p><strong>{{ paiementsTotaux().retard }}</strong></article>
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
            <thead><tr><th>N° pièce</th><th>Contrat</th><th>Échéance</th><th>Payé le</th><th class="is-num">Prévu</th><th class="is-num">Versé</th><th class="is-num">Écart</th><th>Mode</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
            <tbody>
              @for (p of paiements(); track p.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 30 : 0">
                  <td class="is-nowrap"><code class="bea-mg__code">{{ p.paiement_ref || '—' }}</code></td>
                  <td class="is-wide"><code class="bea-mg__code">{{ p.reference }}</code><small class="bea-ct-sub">{{ p.titre }}{{ p.fournisseur ? ' · ' + p.fournisseur : '' }}</small></td>
                  <td class="is-nowrap">{{ date(p.echeance_date || p.date_prevue) }}</td>
                  <td class="is-nowrap">{{ date(p.date_reelle) }}</td>
                  <td class="is-nowrap is-num">{{ p.montant_prevu | montant }}</td>
                  <td class="is-nowrap is-num"><strong class="bea-ct-strong">{{ p.montant_paye | montant }}</strong></td>
                  <td class="is-nowrap is-num" [class.bea-ct-neg]="p.ecart < 0">{{ p.ecart | montant }}</td>
                  <td class="is-nowrap">{{ p.mode || '—' }}</td>
                  <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statut(p.statut) }}</span></td>
                  <td class="bea-mg__actions-cell is-nowrap">
                    @if (cap().manage && regleable(p.contrat_statut)) {
                      <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editerPaiement(p)"><mat-icon>edit</mat-icon></button>
                      <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" [disabled]="busy()" (click)="supprimerPaiement(p)"><mat-icon>delete</mat-icon></button>
                    }
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', p.contrat_id]" title="Ouvrir le contrat"><mat-icon>open_in_new</mat-icon></a>
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="10"><div class="bea-ct-empty"><mat-icon>payments</mat-icon><p>Aucun paiement{{ paiementStatut() ? ' pour ce statut' : '' }}.</p><small>Réglez une échéance depuis l’onglet « Échéances » ou la fiche d’un contrat.</small></div></td></tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'renouvellements') {
        <div class="bea-mg__search">
          <label class="bea-mg__field">Contrats arrivant à terme sous
            <select [value]="horizonRenouv()" (change)="changerHorizon($any($event.target).value)">
              <option value="30">30 jours</option>
              <option value="60">60 jours</option>
              <option value="90">90 jours</option>
              <option value="180">6 mois</option>
              <option value="365">1 an</option>
            </select>
          </label>
        </div>
        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-mg__panel-top"><h2>À traiter <small>{{ aRenouveler().length }}</small></h2></div>
          <div class="bea-mg__table-scroll bea-ct-table-wrap">
            <table class="bea-mg__table bea-ct-table">
              <thead><tr><th>Contrat</th><th>Fournisseur</th><th>Fin</th><th>Préavis</th><th>Reconduction</th><th class="is-num">Montant TTC</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
              <tbody>
                @for (r of aRenouveler(); track r.id) {
                  <tr class="bea-ct-row">
                    <td class="is-wide"><code class="bea-mg__code">{{ r.reference }}</code><small class="bea-ct-sub">{{ r.titre }}</small></td>
                    <td class="is-wide">{{ r.fournisseur || '—' }}</td>
                    <td class="is-nowrap"><strong>{{ date(r.date_fin) }}</strong><small class="bea-ct-sub" [class.bea-ct-neg]="r.jours < 0">{{ jours(r.jours) }}</small></td>
                    <td class="is-nowrap">{{ date(r.date_preavis) }}</td>
                    <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="r.reconduction === 'TACITE' ? 'INFO' : 'ATTENTION'">{{ reconduction(r.reconduction) }}</span></td>
                    <td class="is-nowrap is-num">{{ r.montant | montant }} {{ r.devise }}</td>
                    <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="r.etat">{{ statut(r.etat) }}</span></td>
                    <td class="bea-mg__actions-cell is-nowrap">
                      @if (cap().manage) {
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-ct-btn-sm" [disabled]="busy()" (click)="reconduire(r)" title="Prolonge le même contrat d’une période identique"><mat-icon>update</mat-icon> Reconduire</button>
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-ct-btn-sm" [disabled]="busy()" (click)="renouveler(r)" title="Crée un nouveau contrat en brouillon"><mat-icon>autorenew</mat-icon> Renouveler</button>
                      }
                      <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', r.id]" title="Ouvrir"><mat-icon>open_in_new</mat-icon></a>
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="8"><div class="bea-ct-empty"><mat-icon>event_available</mat-icon><p>Aucun contrat n’arrive à terme sur cette période.</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>
        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-mg__panel-top"><h2>Contrats issus d’un renouvellement <small>{{ contrats().length }}</small></h2></div>
          <div class="bea-mg__table-scroll bea-ct-table-wrap">
            <table class="bea-mg__table bea-ct-table">
              <thead><tr><th>Référence</th><th>Objet</th><th>Fournisseur</th><th>Période</th><th class="is-num">Montant TTC</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
              <tbody>
                @for (c of contrats(); track c.id) {
                  <tr class="bea-ct-row">
                    <td class="is-nowrap"><code class="bea-mg__code">{{ c.reference }}</code></td>
                    <td class="is-wide"><strong class="bea-ct-strong">{{ c.titre }}</strong></td>
                    <td class="is-wide">{{ c.fournisseur_snapshot || '—' }}</td>
                    <td class="is-nowrap">{{ date(c.date_debut) }}<small class="bea-ct-sub">au {{ date(c.date_fin) }}</small></td>
                    <td class="is-nowrap is-num">{{ c.montant | montant }} {{ c.devise }}</td>
                    <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="c.etat">{{ statut(c.etat) }}</span></td>
                    <td class="bea-mg__actions-cell is-nowrap">
                      <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', c.id]" title="Ouvrir"><mat-icon>open_in_new</mat-icon></a>
                      @if (c.contrat_precedent_id) {
                        <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', c.contrat_precedent_id]" title="Contrat d’origine"><mat-icon>history</mat-icon></a>
                      }
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="7"><div class="bea-ct-empty"><mat-icon>autorenew</mat-icon><p>Aucun renouvellement (reconduction expresse) enregistré.</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }

      @if (paiementOuvert()) {
        <div class="bea-mg__backdrop" (click)="fermerPaiement()"></div>
        <form class="bea-mg__modal bea-mg__modal--lg bea-ct-modal" role="dialog" aria-modal="true" aria-labelledby="bea-ct-pay-title" [formGroup]="paiementForm" (ngSubmit)="sauverPaiement()">
          <header class="bea-ct-modal__head">
            <h2 id="bea-ct-pay-title"><mat-icon>payments</mat-icon> {{ paiementEditId() ? 'Modifier le paiement' : 'Enregistrer un paiement' }}</h2>
            <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerPaiement()"><mat-icon>close</mat-icon></button>
          </header>
          <div class="bea-ct-grid bea-ct-modal__body">
            <label class="bea-ct-span2">Contrat *
              <select formControlName="contrat_id" (change)="onContratPaiement()">
                <option value="">— Sélectionner —</option>
                @for (c of contratsPayables(); track c.id) { <option [value]="c.id">{{ c.reference }} — {{ c.titre }}</option> }
              </select>
            </label>
            <label class="bea-ct-span2">Échéance réglée
              <select formControlName="echeance_id" (change)="onEcheancePaiement()">
                <option value="">— Hors échéancier —</option>
                @for (e of echeancesContrat(); track e.id) { <option [value]="e.id">{{ date(e.date_prevue) }} — reste {{ e.reste | montant }} {{ e.devise }}</option> }
              </select>
            </label>
            <label>N° de pièce <input formControlName="reference" maxlength="40" placeholder="Facture, OV, chèque…" /></label>
            <label>Mode
              <select formControlName="mode">
                <option value="">—</option>
                @for (m of config()?.modes_paiement ?? []; track m) { <option [value]="m">{{ m }}</option> }
              </select>
            </label>
            <label>Date prévue <input type="date" formControlName="date_prevue" /></label>
            <label>Date de paiement <input type="date" formControlName="date_reelle" /></label>
            <label>Montant prévu <input type="number" min="0" step="0.01" formControlName="montant_prevu" /></label>
            <label>Montant versé * <input type="number" min="0" step="0.01" formControlName="montant_paye" /></label>
            <label class="bea-ct-span2">Commentaire <input formControlName="commentaire" /></label>
          </div>
          <p class="bea-ct-help bea-ct-modal__help"><mat-icon>info</mat-icon> Joignez la preuve de paiement dans la fiche du contrat, onglet Documents (typologie « Preuve de paiement »).</p>
          <footer class="bea-ct-modal__foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerPaiement()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="paiementForm.invalid || busy()"><mat-icon>save</mat-icon> {{ busy() ? 'Enregistrement…' : 'Enregistrer' }}</button>
          </footer>
        </form>
      }
    </section>
  `,
})
export class ContratsListComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(() => this.paiementOuvert() && this.paiementForm.dirty && !this.busy(), () => this.paiementForm);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly statuts = STATUTS_CONTRAT;
  readonly etats = ETATS_FILTRE;
  readonly typesEcheance = TYPES_ECHEANCE;
  readonly niveaux = ['CRITIQUE', 'URGENT', 'ATTENTION', 'INFO'];
  readonly typesAlerte = Object.entries(ALERTE_TYPE_LABELS);

  readonly mode = signal<Mode>('liste');
  readonly config = signal<ContratsConfig | null>(null);
  readonly contrats = signal<Contrat[]>([]);
  readonly alertes = signal<Alerte[]>([]);
  readonly echeances = signal<EcheanceRow[]>([]);
  readonly paiements = signal<PaiementRow[]>([]);
  readonly aRenouveler = signal<ARenouveler[]>([]);
  readonly types = signal<Array<{ code: string; libelle: string }>>([]);
  readonly agences = signal<RefItem[]>([]);
  readonly contratsPayables = signal<Contrat[]>([]);
  readonly echeancesContrat = signal<EcheanceRow[]>([]);
  readonly paiementStatut = signal('');
  readonly horizonRenouv = signal('90');
  readonly filtreNiveau = signal('');
  readonly filtreType = signal('');
  readonly busy = signal(false);
  readonly paiementOuvert = signal(false);
  readonly paiementEditId = signal<string | null>(null);

  readonly entete = computed(() => TITRES[this.mode()]);
  readonly cap = computed(
    () => this.config()?.capacites ?? { create: false, manage: false, validate: false, settings: false, export: false, ged_write: false },
  );
  readonly totalListe = computed(() => this.contrats().reduce((s, c) => s + num(c.montant), 0));
  readonly alertesFiltrees = computed(() =>
    this.alertes().filter((a) => (!this.filtreNiveau() || a.niveau === this.filtreNiveau()) && (!this.filtreType() || a.type === this.filtreType())),
  );
  readonly kpiEcheances = signal({ aVenir: 0, dues: 0, retard: 0, payees: 0, resteRetard: 0 });
  readonly paiementsTotaux = computed(() => {
    const rows = this.paiements();
    const prevu = rows.reduce((s, p) => s + num(p.montant_prevu), 0);
    const paye = rows.reduce((s, p) => s + num(p.montant_paye), 0);
    return { prevu, paye, ecart: Math.round((paye - prevu) * 100) / 100, retard: rows.filter((p) => p.statut === 'EN_RETARD').length };
  });

  readonly filtres = this.fb.nonNullable.group({ q: [''], statut: [''], etat: [''], type_contrat: [''], agence_id: [''], horizon: [''] });
  readonly filtreEcheance = this.fb.nonNullable.group({ horizon: [''], statut: [''], type_echeance: [''] });
  readonly paiementForm = this.fb.nonNullable.group({
    contrat_id: ['', Validators.required],
    echeance_id: [''],
    reference: [''],
    date_prevue: [''],
    date_reelle: [aujourdhui()],
    montant_prevu: [null as number | null, Validators.min(0)],
    montant_paye: [0, [Validators.required, Validators.min(0)]],
    mode: [''],
    commentaire: [''],
  });

  ngOnInit(): void {
    this.api.get<ContratsConfig>('/mg/contrats/config').subscribe({ next: (c) => this.config.set(c), error: (e) => this.fail(e) });
    this.api.get<Array<{ code: string; libelle: string }>>('/mg/contrats/types').subscribe({ next: (r) => this.types.set(r), error: () => undefined });
    this.api.get<RefItem[]>('/mg/contrats/agences').subscribe({ next: (r) => this.agences.set(r), error: () => undefined });
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.sync());
  }

  private sync(): void {
    const path = (this.route.snapshot.routeConfig?.path ?? 'liste') as Mode;
    this.mode.set(path in TITRES ? path : 'liste');
    this.fermerPaiement(true);
    const qp = this.route.snapshot.queryParamMap;
    if (this.mode() === 'liste') {
      this.filtres.patchValue({
        q: qp.get('q') || '',
        statut: qp.get('statut') || '',
        etat: qp.get('etat') || '',
        type_contrat: qp.get('type') || '',
        agence_id: qp.get('agence') || '',
        horizon: qp.get('horizon') || '',
      });
    }
    if (this.mode() === 'paiements') this.paiementStatut.set(qp.get('statut') || '');
    if (this.mode() === 'echeances') {
      this.filtreEcheance.patchValue({ statut: qp.get('statut') || '', horizon: qp.get('horizon') || '' });
    }
    if (this.mode() === 'alertes') this.filtreNiveau.set(qp.get('niveau') || '');
    this.charger();
  }

  charger(): void {
    switch (this.mode()) {
      case 'liste':
        this.chargerListe();
        break;
      case 'alertes':
        this.api.get<Alerte[]>('/mg/contrats/alertes').subscribe({ next: (r) => this.alertes.set(r), error: (e) => this.fail(e) });
        break;
      case 'echeances':
        this.chargerEcheances();
        break;
      case 'paiements':
        this.chargerPaiements();
        break;
      case 'renouvellements':
        this.api
          .get<ARenouveler[]>('/mg/contrats/renouvellements/a-traiter', { horizon: this.horizonRenouv() })
          .subscribe({ next: (r) => this.aRenouveler.set(r), error: (e) => this.fail(e) });
        this.api.get<Contrat[]>('/mg/contrats', { renouveles: 'true' }).subscribe({ next: (r) => this.contrats.set(r), error: (e) => this.fail(e) });
        break;
    }
  }

  private chargerListe(): void {
    const raw = this.filtres.getRawValue();
    const params: Record<string, string> = {};
    if (raw.q.trim()) params['q'] = raw.q.trim();
    if (raw.statut) params['statut'] = raw.statut;
    if (raw.etat) params['etat'] = raw.etat;
    if (raw.type_contrat) params['type_contrat'] = raw.type_contrat;
    if (raw.agence_id) params['agence_id'] = raw.agence_id;
    if (raw.horizon) params['horizon'] = raw.horizon;
    this.api.get<Contrat[]>('/mg/contrats', params).subscribe({ next: (r) => this.contrats.set(r), error: (e) => this.fail(e) });
  }

  appliquerFiltres(): void {
    const raw = this.filtres.getRawValue();
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        q: raw.q.trim() || null,
        statut: raw.statut || null,
        etat: raw.etat || null,
        type: raw.type_contrat || null,
        agence: raw.agence_id || null,
        horizon: raw.horizon || null,
      },
    });
  }

  filtresActifs(): boolean {
    return Object.values(this.filtres.getRawValue()).some((v) => !!String(v).trim());
  }

  reinitialiser(): void {
    this.filtres.reset({ q: '', statut: '', etat: '', type_contrat: '', agence_id: '', horizon: '' });
    this.appliquerFiltres();
  }

  chargerEcheances(): void {
    const raw = this.filtreEcheance.getRawValue();
    const params: Record<string, string> = {};
    if (raw.horizon) params['horizon'] = raw.horizon;
    if (raw.statut) params['statut'] = raw.statut;
    if (raw.type_echeance) params['type_echeance'] = raw.type_echeance;
    this.api.get<EcheanceRow[]>('/mg/contrats/echeances', params).subscribe({ next: (r) => this.echeances.set(r), error: (e) => this.fail(e) });
    this.api.get<EcheanceRow[]>('/mg/contrats/echeances').subscribe({
      next: (all) =>
        this.kpiEcheances.set({
          aVenir: all.filter((e) => e.statut === 'A_VENIR').length,
          dues: all.filter((e) => e.statut === 'DUE').length,
          retard: all.filter((e) => e.statut === 'EN_RETARD').length,
          payees: all.filter((e) => e.statut === 'PAYEE').length,
          resteRetard: all.filter((e) => e.statut === 'EN_RETARD').reduce((s, e) => s + num(e.reste), 0),
        }),
      error: () => undefined,
    });
  }

  filtrerEcheancesStatut(statut: string): void {
    const courant = this.filtreEcheance.controls.statut.value;
    this.filtreEcheance.controls.statut.setValue(courant === statut ? '' : statut);
    this.chargerEcheances();
  }

  private chargerPaiements(): void {
    const params: Record<string, string> = {};
    if (this.paiementStatut()) params['statut'] = this.paiementStatut();
    this.api.get<PaiementRow[]>('/mg/contrats/paiements', params).subscribe({ next: (r) => this.paiements.set(r), error: (e) => this.fail(e) });
  }

  filtrerPaiements(statut: string): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { statut: statut || null } });
  }

  changerHorizon(h: string): void {
    this.horizonRenouv.set(h);
    this.charger();
  }

  supprimerContrat(c: Contrat): void {
    this.feedback
      .run(() => this.api.delete(`/mg/contrats/${c.id}`), {
        confirm: { action: 'suppression', message: `Retirer ${c.reference} « ${c.titre} » du registre ?`, hint: 'L’historique reste conservé (audit).' },
        loading: 'Suppression…',
        busy: this.busy,
        errorTitle: 'Échec de la suppression',
        success: { title: 'Contrat retiré du registre', details: [{ label: 'Référence', value: c.reference }] },
      })
      .subscribe(() => this.chargerListe());
  }

  envoyerRappels(): void {
    this.feedback
      .run(() => this.api.post<{ notifications: number; emails: number }>('/mg/contrats/alertes/envoyer', {}), {
        confirm: {
          action: 'enregistrement',
          title: 'Envoyer les rappels',
          message: 'Notifier maintenant les responsables des contrats en alerte ?',
          hint: 'Un seul rappel par contrat, type d’alerte et responsable et par jour (pas de doublon).',
        },
        loading: 'Envoi des rappels…',
        busy: this.busy,
        errorTitle: 'Échec de l’envoi',
        success: (r) => ({
          title: 'Rappels envoyés',
          details: [
            { label: 'Notifications', value: String(r.notifications) },
            { label: 'E-mails', value: String(r.emails) },
          ],
        }),
      })
      .subscribe();
  }

  reconduire(r: ARenouveler): void {
    this.feedback
      .run(() => this.api.post<Contrat>(`/mg/contrats/${r.id}/reconduire`, {}), {
        confirm: {
          action: 'renouvellement',
          title: 'Reconduction tacite',
          message: `Reconduire ${r.reference} « ${r.titre} » pour une période identique ?`,
          hint: 'Le même contrat est prolongé ; un avenant de reconduction est tracé et l’échéancier complété.',
        },
        loading: 'Reconduction…',
        busy: this.busy,
        idempotent: true,
        errorTitle: 'Échec de la reconduction',
        success: (c) => ({ title: 'Contrat reconduit', details: [{ label: 'Contrat', value: c.reference }, { label: 'Nouvelle fin', value: dateFr(c.date_fin) }] }),
      })
      .subscribe(() => this.charger());
  }

  renouveler(r: ARenouveler): void {
    this.feedback
      .run(() => this.api.post<Contrat>(`/mg/contrats/${r.id}/renouveler`, {}), {
        confirm: {
          action: 'renouvellement',
          title: 'Reconduction expresse',
          message: `Préparer un nouveau contrat à partir de ${r.reference} ?`,
          hint: 'Un nouveau contrat en brouillon est créé pour la période suivante ; il suivra le circuit de validation.',
        },
        loading: 'Préparation…',
        busy: this.busy,
        idempotent: true,
        errorTitle: 'Échec du renouvellement',
        success: (n) => ({ title: 'Renouvellement préparé', details: [{ label: 'Nouvelle référence', value: n.reference }, { label: 'Issu de', value: r.reference }] }),
      })
      .subscribe((n) => void this.router.navigateByUrl(`/contrats-echeances/${n.id}`));
  }

  private chargerPayables(): void {
    if (this.contratsPayables().length) return;
    this.api.get<Contrat[]>('/mg/contrats').subscribe({
      next: (rows) => this.contratsPayables.set(rows.filter((c) => this.regleable(c.statut))),
      error: () => undefined,
    });
  }

  private chargerEcheancesContrat(contratId: string, selection?: string): void {
    this.echeancesContrat.set([]);
    if (!contratId) return;
    this.api.get<EcheanceRow[]>('/mg/contrats/echeances', { contrat_id: contratId, type_echeance: 'PAIEMENT' }).subscribe({
      next: (rows) => this.echeancesContrat.set(rows.filter((e) => e.reste > 0 || e.id === selection)),
      error: () => undefined,
    });
  }

  ouvrirPaiement(): void {
    this.chargerPayables();
    this.paiementEditId.set(null);
    this.echeancesContrat.set([]);
    this.paiementForm.reset({
      contrat_id: '', echeance_id: '', reference: '', date_prevue: '', date_reelle: aujourdhui(),
      montant_prevu: null, montant_paye: 0, mode: '', commentaire: '',
    });
    this.paiementForm.controls.contrat_id.enable();
    this.paiementOuvert.set(true);
  }

  regler(e: EcheanceRow): void {
    this.chargerPayables();
    this.paiementEditId.set(null);
    this.paiementForm.reset({
      contrat_id: e.contrat_id, echeance_id: e.id, reference: '', date_prevue: e.date_prevue, date_reelle: aujourdhui(),
      montant_prevu: e.reste, montant_paye: e.reste, mode: '', commentaire: '',
    });
    this.paiementForm.controls.contrat_id.disable();
    this.chargerEcheancesContrat(e.contrat_id, e.id);
    this.paiementOuvert.set(true);
  }

  editerPaiement(p: PaiementRow): void {
    this.chargerPayables();
    this.paiementEditId.set(p.id);
    this.paiementForm.reset({
      contrat_id: p.contrat_id, echeance_id: p.echeance_id ?? '', reference: p.paiement_ref ?? '', date_prevue: p.date_prevue,
      date_reelle: p.date_reelle ?? '', montant_prevu: p.montant_prevu, montant_paye: p.montant_paye, mode: p.mode ?? '', commentaire: p.commentaire ?? '',
    });
    this.paiementForm.controls.contrat_id.disable();
    this.chargerEcheancesContrat(p.contrat_id, p.echeance_id ?? undefined);
    this.paiementOuvert.set(true);
  }

  onContratPaiement(): void {
    this.paiementForm.patchValue({ echeance_id: '' });
    this.chargerEcheancesContrat(this.paiementForm.controls.contrat_id.value);
  }

  onEcheancePaiement(): void {
    const e = this.echeancesContrat().find((x) => x.id === this.paiementForm.controls.echeance_id.value);
    if (e) this.paiementForm.patchValue({ date_prevue: e.date_prevue, montant_prevu: e.reste, montant_paye: e.reste });
  }

  fermerPaiement(force = false): void {
    if (!this.paiementOuvert()) return;
    if (!force && this.busy()) return;
    this.paiementOuvert.set(false);
    this.paiementForm.markAsPristine();
  }

  sauverPaiement(): void {
    if (this.paiementForm.invalid) return;
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
        () => (editId ? this.api.patch<Contrat>(`/mg/contrats/paiements/${editId}`, body) : this.api.post<Contrat>(`/mg/contrats/${raw.contrat_id}/paiements`, body)),
        {
          loading: 'Enregistrement du paiement…',
          busy: this.busy,
          idempotent: !editId,
          errorTitle: 'Paiement refusé',
          errorHint: 'Vos données saisies ont été conservées.',
          success: (c) => ({
            title: editId ? 'Paiement mis à jour' : 'Paiement enregistré',
            details: [
              { label: 'Contrat', value: c.reference },
              { label: 'Montant versé', value: `${num(body.montant_paye).toLocaleString('fr-FR', { minimumFractionDigits: 2 })} ${c.devise}` },
            ],
          }),
        },
      )
      .subscribe(() => {
        this.fermerPaiement(true);
        this.charger();
      });
  }

  supprimerPaiement(p: PaiementRow): void {
    this.feedback
      .run(() => this.api.delete(`/mg/contrats/paiements/${p.id}`), {
        confirm: {
          action: 'suppression',
          message: `Supprimer le paiement ${p.paiement_ref || 'sans référence'} du contrat ${p.reference} ?`,
          hint: 'L’échéance rattachée repasse en « à payer » ; l’opération est tracée.',
        },
        loading: 'Suppression…',
        busy: this.busy,
        errorTitle: 'Échec de la suppression',
        success: { title: 'Paiement supprimé' },
      })
      .subscribe(() => this.chargerPaiements());
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.fermerPaiement();
  }

  compteNiveau(n: string): number {
    return this.alertes().filter((a) => a.niveau === n).length;
  }

  supprimable(statut: string): boolean {
    return SUPPRIMABLES.has(statut);
  }

  enVigueur(statut: string): boolean {
    return statut === 'ACTIF' || statut === 'SUSPENDU';
  }

  regleable(statut: string): boolean {
    return statut === 'ACTIF' || statut === 'SUSPENDU' || statut === 'EXPIRE';
  }

  typeLabel(code: string): string {
    return this.types().find((t) => t.code === code)?.libelle ?? code;
  }

  typeAlerte(code: string): string {
    return ALERTE_TYPE_LABELS[code] ?? code;
  }

  typeEcheance(code: string): string {
    return typeEcheanceLabel(code);
  }

  reconduction(code: string): string {
    return RECONDUCTION_LABELS[code] ?? code;
  }

  statut(code: string | null | undefined): string {
    return statutLabel(code);
  }

  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }

  jours(n: number | null | undefined): string {
    return joursLabel(n);
  }

  private fail(err: unknown): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, 'Chargement impossible'));
  }
}
