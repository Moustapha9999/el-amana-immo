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
import { ContratDrawerComponent } from './contrat-drawer.component';
import { ContratsActionsService } from './contrats-actions.service';
import { EcheanceDrawerComponent, PaiementDrawerComponent } from './contrats-mini-pages.component';
import {
  ALERTE_TYPE_LABELS,
  ARenouveler,
  Alerte,
  Contrat,
  ContratsConfig,
  DashboardContrats,
  ETATS_FILTRE,
  EcheanceRow,
  PERIODICITE_LABELS,
  PaiementRow,
  RECONDUCTION_LABELS,
  RefItem,
  STATUTS_CONTRAT,
  TYPES_ECHEANCE,
  aujourdhui,
  dateFr,
  echeanceStatutLabel,
  joursLabel,
  num,
  renouvellementStatut,
  statutLabel,
  typeEcheanceLabel,
  variation,
} from './contrats.models';
import { PagerComponent, TableState } from './shared/table-state';

type Mode = 'liste' | 'alertes' | 'echeances' | 'paiements' | 'renouvellements';

const TITRES: Record<Mode, { titre: string; sous: string }> = {
  liste: { titre: 'Registre des contrats', sous: 'Recherche, filtres, tri et mini-fiche détaillée de chaque contrat.' },
  alertes: { titre: 'Alertes', sous: 'Fins de contrat, préavis, paiements dus ou en retard, fiches incomplètes.' },
  echeances: { titre: 'Échéances', sous: 'Échéancier consolidé : à venir, bientôt, échues, payées, reportées, annulées.' },
  paiements: { titre: 'Paiements', sous: 'Règlements enregistrés, justificatifs et rapprochement prévu / versé.' },
  renouvellements: { titre: 'Renouvellements', sous: 'Contrats arrivant à terme et renouvellements en cours : périodes, montants, variation.' },
};

const SUPPRIMABLES = new Set(['BROUILLON', 'EN_PREPARATION', 'REJETE', 'ANNULE']);
const FILTRE_STOCKAGE = 'bea.contrats.filtres';

type Drawer =
  | { type: 'contrat'; contratId: string; onglet: string }
  | { type: 'echeance'; contratId: string; id: string; onglet: string; action: 'reporter' | null }
  | { type: 'paiement'; contratId: string; id: string; onglet: string };

interface Menu {
  top: number;
  left: number;
  items: Array<{ icone: string; label: string; danger?: boolean; action: () => void }>;
}

interface RenouvRow {
  c: Contrat;
  precedent: Contrat | null;
  statut: { code: string; label: string };
  ecart: number;
  pct: number | null;
  sens: string;
}

@Component({
  selector: 'bea-contrats-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MatIconModule, PagerComponent, ContratDrawerComponent, EcheanceDrawerComponent, PaiementDrawerComponent],
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

      <!-- ===================== REGISTRE ===================== -->
      @if (mode() === 'liste') {
        <div class="bea-ct-kpis8">
          @let k = dashboard();
          <button type="button" [class.is-on]="!filtresActifs()" (click)="reinitialiser()"><span>Total</span><strong>{{ k?.total ?? '—' }}</strong><small>contrats au registre</small></button>
          <button type="button" data-tone="ok" [class.is-on]="filtres.value.statut === 'ACTIF'" (click)="filtreRapide({ statut: 'ACTIF' })"><span>Actifs</span><strong>{{ k?.actifs ?? '—' }}</strong></button>
          <button type="button" data-tone="warn" [class.is-on]="filtres.value.etat === 'ECHEANCE_30'" (click)="filtreRapide({ etat: 'ECHEANCE_30' })"><span>Expirant bientôt</span><strong>{{ k?.expirant_bientot ?? '—' }}</strong><small>fin ≤ 30 jours</small></button>
          <button type="button" data-tone="danger" [class.is-on]="filtres.value.statut === 'EXPIRE'" (click)="filtreRapide({ statut: 'EXPIRE' })"><span>Expirés</span><strong>{{ k?.expires ?? '—' }}</strong></button>
          <button type="button" data-tone="warn" (click)="allerRenouvellements()"><span>À renouveler</span><strong>{{ k?.a_renouveler ?? '—' }}</strong><small>sous 90 jours</small></button>
          <button type="button" [class.is-on]="filtres.value.statut === 'SUSPENDU'" (click)="filtreRapide({ statut: 'SUSPENDU' })"><span>Suspendus</span><strong>{{ k?.suspendus ?? '—' }}</strong></button>
          <button type="button" disabled><span>Montant annuel</span><strong>{{ k ? (k.montant_annuel | montant) : '—' }}</strong><small>contrats actifs, ramené à 12 mois</small></button>
          <button type="button" disabled><span>Montant mensuel</span><strong>{{ k ? (k.montant_mensuel | montant) : '—' }}</strong><small>moyenne mensuelle</small></button>
        </div>

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
          <label class="bea-mg__field">Type
            <select formControlName="type_contrat" (change)="appliquerFiltres()">
              <option value="">Tous</option>
              @for (t of types(); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
            </select>
          </label>
          <div class="bea-ct-filters__btns">
            <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Rechercher</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [attr.aria-expanded]="avance()" (click)="avance.set(!avance())"><mat-icon>tune</mat-icon> Filtres avancés @if (nbAvances()) { <span class="bea-ct-badge" data-tone="INFO">{{ nbAvances() }}</span> }</button>
          </div>
        </form>
        @if (avance()) {
          <form class="bea-adv-filters" [formGroup]="filtres" (ngSubmit)="appliquerFiltres()">
            <label class="bea-mg__field">État
              <select formControlName="etat">
                <option value="">Tous</option>
                @for (e of etats; track e.code) { <option [value]="e.code">{{ e.label }}</option> }
              </select>
            </label>
            @if (!config()?.agence_scope) {
              <label class="bea-mg__field">Agence / point
                <select formControlName="agence_id">
                  <option value="">Toutes</option>
                  @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
                </select>
              </label>
            }
            <label class="bea-mg__field">Fournisseur
              <select formControlName="fournisseur_id">
                <option value="">Tous</option>
                @for (f of fournisseurs(); track f.id) { <option [value]="f.id">{{ f.raison_sociale || f.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Fin de contrat
              <select formControlName="horizon">
                <option value="">Toutes</option>
                <option value="retard">Date dépassée</option>
                <option value="30">≤ 30 jours</option>
                <option value="60">≤ 60 jours</option>
                <option value="90">≤ 90 jours</option>
              </select>
            </label>
            <div class="bea-adv-filters__btns">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()"><mat-icon>restart_alt</mat-icon> Réinitialiser</button>
              @if (filtreEnregistre()) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="restaurerFiltre()"><mat-icon>bookmark</mat-icon> Mon filtre</button> }
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="enregistrerFiltre()"><mat-icon>bookmark_add</mat-icon> Enregistrer filtre</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary"><mat-icon>filter_alt</mat-icon> Appliquer</button>
            </div>
          </form>
        }

        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-list-tools">
            <span class="bea-list-tools__count">{{ contrats().length }} contrat{{ contrats().length > 1 ? 's' : '' }} · {{ totalListe() | montant }} TTC @if (filtresActifs()) { · filtres appliqués }</span>
            <span class="bea-list-tools__btns">
              @if (cap().export) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!contrats().length || busy()" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!contrats().length || busy()" (click)="exporter('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
              }
            </span>
          </div>
          <div class="bea-mg__table-scroll bea-ct-table-wrap">
            <table class="bea-mg__table bea-ct-table">
              <thead>
                <tr>
                  @for (h of colsListe; track h[0]) {
                    <th [class.is-num]="h[0] === 'montant'" [attr.aria-sort]="tListe.aria(h[0])"><button type="button" class="bea-sort" (click)="tListe.trier(h[0])">{{ h[1] }} <mat-icon>{{ tListe.icone(h[0]) }}</mat-icon></button></th>
                  }
                  <th class="is-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                @if (chargement()) {
                  @for (i of [1, 2, 3, 4, 5]; track i) { <tr><td colspan="13"><span class="bea-fx-skel bea-fx-skel--line"></span></td></tr> }
                } @else {
                  @for (c of tListe.lignes(); track c.id; let i = $index) {
                    <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 20 : 0">
                      <td class="is-nowrap">
                        <button type="button" class="bea-ct-link bea-sort" (click)="voirContrat(c.id)"><code class="bea-mg__code">{{ c.reference }}</code></button>
                        @if (c.numero_contrat) { <small class="bea-ct-sub">N° {{ c.numero_contrat }}</small> }
                      </td>
                      <td class="is-wide"><strong class="bea-ct-strong">{{ c.titre }}</strong>@if (c.version > 1) { <small class="bea-ct-sub">v{{ c.version }}</small> }</td>
                      <td class="is-wide">{{ c.fournisseur_snapshot || '—' }}</td>
                      <td class="is-nowrap">{{ typeLabel(c.type_contrat) }}</td>
                      <td class="is-wide">{{ c.agence_libelle_snapshot || '—' }}</td>
                      <td class="is-nowrap">{{ date(c.date_debut) }}</td>
                      <td class="is-nowrap">{{ date(c.date_fin) }}@if (c.jours_restants !== null && enVigueur(c.statut)) { <small class="bea-ct-sub" [class.bea-ct-neg]="c.jours_restants < 0">{{ jours(c.jours_restants) }}</small> }</td>
                      <td class="is-nowrap is-num">{{ c.montant | montant }} {{ c.devise }}</td>
                      <td class="is-nowrap">{{ periodicite(c.periodicite) }}</td>
                      <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="c.etat">{{ statut(c.etat) }}</span></td>
                      <td class="is-nowrap">{{ reconductionCourt(c.reconduction) }}</td>
                      <td class="is-nowrap">{{ date(c.prochain_echeance) }}</td>
                      <td class="bea-mg__actions-cell is-nowrap">
                        <span class="bea-row-actions">
                          <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="voirContrat(c.id)"><mat-icon>visibility</mat-icon></button>
                          @if (cap().manage && !verrouille(c.statut)) { <a class="bea-mg__icon-btn" title="Modifier" [routerLink]="['/contrats-echeances', c.id]"><mat-icon>edit</mat-icon></a> }
                          <button type="button" class="bea-mg__icon-btn" title="Documents" (click)="voirContrat(c.id, 'documents')"><mat-icon>folder_open</mat-icon></button>
                          <button type="button" class="bea-mg__icon-btn" title="Plus d’actions" aria-haspopup="menu" (click)="menuContrat($event, c)"><mat-icon>more_vert</mat-icon></button>
                        </span>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="13"><div class="bea-ct-empty"><mat-icon>description</mat-icon><p>{{ filtresActifs() ? 'Aucun contrat ne correspond aux filtres.' : 'Aucun contrat enregistré.' }}</p>
                      @if (filtresActifs()) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()">Réinitialiser les filtres</button> }</div></td></tr>
                  }
                }
              </tbody>
            </table>
          </div>
          <bea-pager [etat]="tListe" />
        </div>
      }

      <!-- ===================== ALERTES ===================== -->
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
        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-mg__table-scroll bea-ct-table-wrap">
            <table class="bea-mg__table bea-ct-table">
              <thead><tr><th>Niveau</th><th>Type</th><th>Contrat</th><th>Alerte</th><th>Responsable</th><th>Date</th><th class="is-actions">Actions</th></tr></thead>
              <tbody>
                @for (a of tAlertes.lignes(); track $index; let i = $index) {
                  <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 20 : 0">
                    <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="a.niveau">{{ statut(a.niveau) }}</span></td>
                    <td class="is-nowrap">{{ typeAlerte(a.type) }}</td>
                    <td class="is-wide"><code class="bea-mg__code">{{ a.reference }}</code><small class="bea-ct-sub">{{ a.titre }}{{ a.fournisseur ? ' · ' + a.fournisseur : '' }}</small></td>
                    <td class="is-wide"><strong class="bea-ct-strong">{{ a.message }}</strong></td>
                    <td class="is-wide">{{ a.responsable || '—' }}</td>
                    <td class="is-nowrap">{{ date(a.echeance) }}@if (a.jours !== null) { <small class="bea-ct-sub" [class.bea-ct-neg]="a.jours < 0">{{ jours(a.jours) }}</small> }</td>
                    <td class="bea-mg__actions-cell"><button type="button" class="bea-mg__icon-btn" title="Voir le contrat" (click)="voirContrat(a.contrat_id)"><mat-icon>visibility</mat-icon></button></td>
                  </tr>
                } @empty {
                  <tr><td colspan="7"><div class="bea-ct-empty"><mat-icon>notifications_none</mat-icon><p>Aucune alerte en cours.</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
          <bea-pager [etat]="tAlertes" />
        </div>
        <p class="bea-ct-help"><mat-icon>schedule_send</mat-icon> Rappels automatiques quotidiens (7 h 30) aux responsables : au délai d’alerte du contrat, J-30, J-15, J-7, J-1, jour J, puis chaque semaine en cas de retard (notification + e-mail si configuré).</p>
      }

      <!-- ===================== ÉCHÉANCES ===================== -->
      @if (mode() === 'echeances') {
        <div class="bea-nf-kpi">
          <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" data-tone="A_VENIR" [class.is-on]="filtreEcheance.value.statut === 'A_VENIR'" (click)="filtrerEcheancesStatut('A_VENIR')"><p>À venir</p><strong>{{ kpiEcheances().aVenir }}</strong></button>
          <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" data-tone="DUE" [class.is-on]="filtreEcheance.value.statut === 'DUE'" (click)="filtrerEcheancesStatut('DUE')"><p>Bientôt</p><strong>{{ kpiEcheances().dues }}</strong></button>
          <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" data-tone="EN_RETARD" [class.is-on]="filtreEcheance.value.statut === 'EN_RETARD'" (click)="filtrerEcheancesStatut('EN_RETARD')"><p>Échues</p><strong>{{ kpiEcheances().retard }}</strong><small>{{ kpiEcheances().resteRetard | montant }}</small></button>
          <button type="button" class="bea-nf-kpi__card bea-ct-kpi-btn" data-tone="PAYEE" [class.is-on]="filtreEcheance.value.statut === 'PAYEE'" (click)="filtrerEcheancesStatut('PAYEE')"><p>Payées</p><strong>{{ kpiEcheances().payees }}</strong></button>
        </div>
        <form class="bea-mg__search bea-ct-filters" [formGroup]="filtreEcheance" (ngSubmit)="chargerEcheances()">
          <label class="bea-mg__field bea-ct-filters__q">Contrat / recherche <input formControlName="q" placeholder="Référence, objet, fournisseur, agence" /></label>
          <label class="bea-mg__field">Période
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
              <option value="DUE">Bientôt</option>
              <option value="EN_RETARD">Échue</option>
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
          <div class="bea-ct-filters__btns">
            <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Rechercher</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [attr.aria-expanded]="avance()" (click)="avance.set(!avance())"><mat-icon>tune</mat-icon> Filtres avancés</button>
          </div>
        </form>
        @if (avance()) {
          <form class="bea-adv-filters" [formGroup]="filtreEcheance" (ngSubmit)="chargerEcheances()">
            <label class="bea-mg__field">Fournisseur
              <select formControlName="fournisseur"><option value="">Tous</option>@for (f of fournisseursNoms(); track f) { <option [value]="f">{{ f }}</option> }</select>
            </label>
            <label class="bea-mg__field">Agence
              <select formControlName="agence"><option value="">Toutes</option>@for (a of agencesNoms(); track a) { <option [value]="a">{{ a }}</option> }</select>
            </label>
            <label class="bea-mg__field">Du <input type="date" formControlName="date_du" /></label>
            <label class="bea-mg__field">Au <input type="date" formControlName="date_au" /></label>
            <div class="bea-adv-filters__btns">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitEcheances()"><mat-icon>restart_alt</mat-icon> Réinitialiser</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary"><mat-icon>filter_alt</mat-icon> Appliquer</button>
            </div>
          </form>
        }
        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-list-tools">
            <span class="bea-list-tools__count">{{ echeances().length }} échéance(s) · reste {{ resteEcheances() | montant }}</span>
            <span class="bea-list-tools__btns">
              @if (cap().export) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!echeances().length || busy()" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!echeances().length || busy()" (click)="exporter('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
              }
            </span>
          </div>
          <div class="bea-mg__table-scroll bea-ct-table-wrap">
            <table class="bea-mg__table bea-ct-table">
              <thead>
                <tr>
                  @for (h of colsEcheances; track h[0]) {
                    <th [class.is-num]="['montant', 'paye', 'reste', 'jours'].includes(h[0])" [attr.aria-sort]="tEcheances.aria(h[0])"><button type="button" class="bea-sort" (click)="tEcheances.trier(h[0])">{{ h[1] }} <mat-icon>{{ tEcheances.icone(h[0]) }}</mat-icon></button></th>
                  }
                  <th class="is-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                @if (chargement()) {
                  @for (i of [1, 2, 3, 4, 5]; track i) { <tr><td colspan="11"><span class="bea-fx-skel bea-fx-skel--line"></span></td></tr> }
                } @else {
                  @for (e of tEcheances.lignes(); track e.id; let i = $index) {
                    <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 20 : 0">
                      <td class="is-nowrap"><strong>{{ date(e.date_prevue) }}</strong></td>
                      <td class="is-nowrap is-num" [class.bea-ct-neg]="e.jours < 0 && ouverte(e)">{{ ouverte(e) ? e.jours : '—' }}</td>
                      <td class="is-wide"><button type="button" class="bea-ct-link bea-sort" (click)="voirEcheance(e)"><code class="bea-mg__code">{{ e.reference }}</code></button><small class="bea-ct-sub">{{ e.titre }}</small></td>
                      <td class="is-wide">{{ e.fournisseur || '—' }}</td>
                      <td class="is-wide">{{ e.agence || '—' }}</td>
                      <td class="is-nowrap">{{ typeEcheance(e.type_echeance) }}</td>
                      <td class="is-nowrap is-num">{{ e.montant === null ? '—' : (e.montant | montant) }}</td>
                      <td class="is-nowrap is-num">{{ e.montant_paye | montant }}</td>
                      <td class="is-nowrap is-num"><strong class="bea-ct-strong">{{ e.reste | montant }}</strong></td>
                      <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statutEch(e) }}</span></td>
                      <td class="bea-mg__actions-cell is-nowrap">
                        <span class="bea-row-actions">
                          <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="voirEcheance(e)"><mat-icon>visibility</mat-icon></button>
                          @if (peutRegler(e)) { <button type="button" class="bea-mg__icon-btn bea-pay-btn" title="Marquer payée" (click)="regler(e)"><mat-icon>price_check</mat-icon></button> }
                          <button type="button" class="bea-mg__icon-btn" title="Plus d’actions" aria-haspopup="menu" (click)="menuEcheance($event, e)"><mat-icon>more_vert</mat-icon></button>
                        </span>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="11"><div class="bea-ct-empty"><mat-icon>event</mat-icon><p>Aucune échéance pour ces critères.</p><small>Les échéanciers sont générés automatiquement à la validation des contrats.</small></div></td></tr>
                  }
                }
              </tbody>
            </table>
          </div>
          <bea-pager [etat]="tEcheances" />
        </div>
      }

      <!-- ===================== PAIEMENTS ===================== -->
      @if (mode() === 'paiements') {
        <div class="bea-nf-kpi">
          <article class="bea-nf-kpi__card"><p>Montant prévu</p><strong>{{ paiementsTotaux().prevu | montant }}</strong></article>
          <article class="bea-nf-kpi__card"><p>Montant versé</p><strong>{{ paiementsTotaux().paye | montant }}</strong></article>
          <article class="bea-nf-kpi__card"><p>Écart (versé − prévu)</p><strong [class.bea-ct-neg]="paiementsTotaux().ecart < 0">{{ paiementsTotaux().ecart | montant }}</strong></article>
          <article class="bea-nf-kpi__card" data-tone="EN_RETARD"><p>En retard</p><strong>{{ paiementsTotaux().retard }}</strong></article>
        </div>
        <form class="bea-mg__search bea-ct-filters" [formGroup]="filtrePaiement" (ngSubmit)="chargerPaiements()">
          <label class="bea-mg__field bea-ct-filters__q">Contrat / recherche <input formControlName="q" placeholder="N° pièce, référence, objet, fournisseur, agence" /></label>
          <label class="bea-mg__field">Statut
            <select formControlName="statut" (change)="chargerPaiements()">
              <option value="">Tous</option>
              <option value="A_VENIR">À venir</option>
              <option value="EN_RETARD">En retard</option>
              <option value="PARTIELLEMENT_PAYE">Partiellement payé</option>
              <option value="PAYE">Payé</option>
            </select>
          </label>
          <div class="bea-ct-filters__btns">
            <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Rechercher</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [attr.aria-expanded]="avance()" (click)="avance.set(!avance())"><mat-icon>tune</mat-icon> Filtres avancés</button>
          </div>
        </form>
        @if (avance()) {
          <form class="bea-adv-filters" [formGroup]="filtrePaiement" (ngSubmit)="chargerPaiements()">
            <label class="bea-mg__field">Fournisseur
              <select formControlName="fournisseur"><option value="">Tous</option>@for (f of fournisseursNoms(); track f) { <option [value]="f">{{ f }}</option> }</select>
            </label>
            <label class="bea-mg__field">Agence
              <select formControlName="agence"><option value="">Toutes</option>@for (a of agencesNoms(); track a) { <option [value]="a">{{ a }}</option> }</select>
            </label>
            <label class="bea-mg__field">Payé du <input type="date" formControlName="date_du" /></label>
            <label class="bea-mg__field">au <input type="date" formControlName="date_au" /></label>
            <label class="bea-mg__field">Montant min. <input type="number" min="0" step="0.01" formControlName="montant_min" /></label>
            <label class="bea-mg__field">Montant max. <input type="number" min="0" step="0.01" formControlName="montant_max" /></label>
            <div class="bea-adv-filters__btns">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitPaiements()"><mat-icon>restart_alt</mat-icon> Réinitialiser</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary"><mat-icon>filter_alt</mat-icon> Appliquer</button>
            </div>
          </form>
        }
        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-list-tools">
            <span class="bea-list-tools__count">{{ paiements().length }} paiement(s)</span>
            <span class="bea-list-tools__btns">
              @if (cap().export) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!paiements().length || busy()" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!paiements().length || busy()" (click)="exporter('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
              }
            </span>
          </div>
          <div class="bea-mg__table-scroll bea-ct-table-wrap">
            <table class="bea-mg__table bea-ct-table">
              <thead>
                <tr>
                  @for (h of colsPaiements; track h[0]) {
                    <th [class.is-num]="['prevu', 'paye', 'ecart'].includes(h[0])" [attr.aria-sort]="tPaiements.aria(h[0])"><button type="button" class="bea-sort" (click)="tPaiements.trier(h[0])">{{ h[1] }} <mat-icon>{{ tPaiements.icone(h[0]) }}</mat-icon></button></th>
                  }
                  <th class="is-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                @if (chargement()) {
                  @for (i of [1, 2, 3, 4, 5]; track i) { <tr><td colspan="11"><span class="bea-fx-skel bea-fx-skel--line"></span></td></tr> }
                } @else {
                  @for (p of tPaiements.lignes(); track p.id; let i = $index) {
                    <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 20 : 0">
                      <td class="is-nowrap"><button type="button" class="bea-ct-link bea-sort" (click)="voirPaiement(p)"><code class="bea-mg__code">{{ p.paiement_ref || '—' }}</code></button></td>
                      <td class="is-wide"><code class="bea-mg__code">{{ p.reference }}</code><small class="bea-ct-sub">{{ p.titre }}</small></td>
                      <td class="is-wide">{{ p.fournisseur || '—' }}</td>
                      <td class="is-wide">{{ p.agence || '—' }}</td>
                      <td class="is-nowrap">{{ date(p.date_reelle) }}<small class="bea-ct-sub">prévu {{ date(p.echeance_date || p.date_prevue) }}</small></td>
                      <td class="is-nowrap is-num">{{ p.montant_prevu | montant }}</td>
                      <td class="is-nowrap is-num"><strong class="bea-ct-strong">{{ p.montant_paye | montant }}</strong></td>
                      <td class="is-nowrap is-num" [class.bea-ct-neg]="p.ecart < 0">{{ p.ecart | montant }}</td>
                      <td class="is-nowrap">{{ p.mode || '—' }}</td>
                      <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statut(p.statut) }}</span></td>
                      <td class="bea-mg__actions-cell is-nowrap">
                        <span class="bea-row-actions">
                          <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="voirPaiement(p)"><mat-icon>visibility</mat-icon></button>
                          @if (cap().manage && regleable(p.contrat_statut)) { <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editerPaiement(p)"><mat-icon>edit</mat-icon></button> }
                          <button type="button" class="bea-mg__icon-btn" title="Plus d’actions" aria-haspopup="menu" (click)="menuPaiement($event, p)"><mat-icon>more_vert</mat-icon></button>
                        </span>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="11"><div class="bea-ct-empty"><mat-icon>payments</mat-icon><p>Aucun paiement pour ces critères.</p><small>Réglez une échéance depuis l’onglet « Échéances » ou la fiche d’un contrat.</small></div></td></tr>
                  }
                }
              </tbody>
            </table>
          </div>
          <bea-pager [etat]="tPaiements" />
        </div>
      }

      <!-- ===================== RENOUVELLEMENTS ===================== -->
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
          <label class="bea-mg__field">Statut du renouvellement
            <select [value]="filtreRenouv()" (change)="filtreRenouv.set($any($event.target).value)">
              <option value="">Tous</option>
              @for (s of statutsRenouv; track s) { <option [value]="s">{{ s }}</option> }
            </select>
          </label>
        </div>
        @if (!filtreRenouv() || filtreRenouv() === 'À préparer') {
          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2>À préparer <small>{{ aRenouveler().length }}</small></h2></div>
            <div class="bea-mg__table-scroll bea-ct-table-wrap">
              <table class="bea-mg__table bea-ct-table">
                <thead><tr><th>Contrat</th><th>Fournisseur</th><th>Période actuelle (fin)</th><th>Préavis</th><th>Type</th><th class="is-num">Montant TTC</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
                <tbody>
                  @for (r of tARenouveler.lignes(); track r.id) {
                    <tr class="bea-ct-row">
                      <td class="is-wide"><button type="button" class="bea-ct-link bea-sort" (click)="voirContrat(r.id, 'renouvellements')"><code class="bea-mg__code">{{ r.reference }}</code></button><small class="bea-ct-sub">{{ r.titre }}</small></td>
                      <td class="is-wide">{{ r.fournisseur || '—' }}</td>
                      <td class="is-nowrap"><strong>{{ date(r.date_fin) }}</strong><small class="bea-ct-sub" [class.bea-ct-neg]="r.jours < 0">{{ jours(r.jours) }}</small></td>
                      <td class="is-nowrap">{{ date(r.date_preavis) }}</td>
                      <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="r.reconduction === 'TACITE' ? 'INFO' : 'ATTENTION'">{{ reconduction(r.reconduction) }}</span></td>
                      <td class="is-nowrap is-num">{{ r.montant | montant }} {{ r.devise }}</td>
                      <td class="is-nowrap"><span class="bea-ct-badge" data-tone="ATTENTION">À préparer</span></td>
                      <td class="bea-mg__actions-cell is-nowrap">
                        <span class="bea-row-actions">
                          <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="voirContrat(r.id, 'renouvellements')"><mat-icon>visibility</mat-icon></button>
                          @if (cap().manage) {
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-ct-btn-sm" [disabled]="busy()" (click)="reconduire(r)" title="Prolonge le même contrat d’une période identique"><mat-icon>update</mat-icon> Reconduire</button>
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-ct-btn-sm" [disabled]="busy()" (click)="renouveler(r)" title="Crée un nouveau contrat en brouillon"><mat-icon>autorenew</mat-icon> Renouveler</button>
                          }
                        </span>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="8"><div class="bea-ct-empty"><mat-icon>event_available</mat-icon><p>Aucun contrat n’arrive à terme sur cette période.</p></div></td></tr>
                  }
                </tbody>
              </table>
            </div>
            <bea-pager [etat]="tARenouveler" />
          </div>
        }
        @if (filtreRenouv() !== 'À préparer') {
          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2>Renouvellements (reconduction expresse) <small>{{ renouvRows().length }}</small></h2></div>
            <div class="bea-mg__table-scroll bea-ct-table-wrap">
              <table class="bea-mg__table bea-ct-table">
                <thead><tr><th>Nouveau contrat</th><th>Fournisseur</th><th>Ancienne période</th><th>Nouvelle période</th><th class="is-num">Ancien montant</th><th class="is-num">Nouveau montant</th><th class="is-num">Variation</th><th>Date</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
                <tbody>
                  @for (r of tRenouv.lignes(); track r.c.id) {
                    <tr class="bea-ct-row">
                      <td class="is-wide"><button type="button" class="bea-ct-link bea-sort" (click)="voirContrat(r.c.id, 'renouvellements')"><code class="bea-mg__code">{{ r.c.reference }}</code></button><small class="bea-ct-sub">{{ r.c.titre }}</small></td>
                      <td class="is-wide">{{ r.c.fournisseur_snapshot || '—' }}</td>
                      <td class="is-nowrap">@if (r.precedent) { {{ date(r.precedent.date_debut) }}<small class="bea-ct-sub">au {{ date(r.precedent.date_fin) }}</small> } @else { — }</td>
                      <td class="is-nowrap">{{ date(r.c.date_debut) }}<small class="bea-ct-sub">au {{ date(r.c.date_fin) }}</small></td>
                      <td class="is-nowrap is-num">{{ r.precedent ? (r.precedent.montant | montant) : '—' }}</td>
                      <td class="is-nowrap is-num">{{ r.c.montant | montant }}</td>
                      <td class="is-nowrap is-num"><span class="bea-dd__variation" [attr.data-sens]="r.sens">{{ r.precedent ? (r.ecart > 0 ? '+' : '') + (r.pct === null ? '—' : r.pct + ' %') : '—' }}</span></td>
                      <td class="is-nowrap">{{ date(r.c.date_signature || r.c.date_debut) }}</td>
                      <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="r.statut.code">{{ r.statut.label }}</span></td>
                      <td class="bea-mg__actions-cell is-nowrap">
                        <span class="bea-row-actions">
                          <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="voirContrat(r.c.id, 'renouvellements')"><mat-icon>visibility</mat-icon></button>
                          @if (r.precedent) { <button type="button" class="bea-mg__icon-btn" title="Contrat d’origine" (click)="voirContrat(r.precedent.id)"><mat-icon>history</mat-icon></button> }
                        </span>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="10"><div class="bea-ct-empty"><mat-icon>autorenew</mat-icon><p>Aucun renouvellement pour ces critères.</p><small>Les reconductions tacites sont tracées en avenant dans la fiche du contrat.</small></div></td></tr>
                  }
                </tbody>
              </table>
            </div>
            <bea-pager [etat]="tRenouv" />
          </div>
        }
      }

      <!-- ===================== MINI-PAGES ===================== -->
      @if (drawer(); as d) {
        @switch (d.type) {
          @case ('contrat') {
            <bea-ct-contrat-drawer [contratId]="d.contratId" [ongletInitial]="d.onglet" [config]="config()" [types]="types()" [version]="version()"
              (fermer)="fermerDrawer()" (payer)="regler($event)" (editer)="editerPaiement($event)" (modifie)="charger()" />
          }
          @case ('echeance') {
            <bea-ct-echeance-drawer [contratId]="d.contratId" [echeanceId]="$any(d).id" [ongletInitial]="d.onglet" [actionInitiale]="$any(d).action" [config]="config()" [version]="version()"
              (fermer)="fermerDrawer()" (payer)="regler($event)" (modifie)="charger()" (ouvrirContrat)="voirContrat($event)" />
          }
          @case ('paiement') {
            <bea-ct-paiement-drawer [contratId]="d.contratId" [paiementId]="$any(d).id" [ongletInitial]="d.onglet" [config]="config()" [version]="version()"
              (fermer)="fermerDrawer()" (editer)="editerPaiement($event)" (modifie)="charger()" (ouvrirContrat)="voirContrat($event)" />
          }
        }
      }

      @if (menu(); as mn) {
        <div class="bea-row-menu__veil" (click)="menu.set(null)"></div>
        <ul class="bea-row-menu" role="menu" [style.top.px]="mn.top" [style.left.px]="mn.left">
          @for (it of mn.items; track it.label) {
            <li role="none"><button type="button" role="menuitem" [class.is-danger]="it.danger" (click)="menu.set(null); it.action()"><mat-icon>{{ it.icone }}</mat-icon> {{ it.label }}</button></li>
          }
        </ul>
      }

      @if (paiementOuvert()) {
        <div class="bea-mg__backdrop bea-fx-over" (click)="fermerPaiement()"></div>
        <form class="bea-mg__modal bea-mg__modal--lg bea-ct-modal bea-fx-over" role="dialog" aria-modal="true" aria-labelledby="bea-ct-pay-title" [formGroup]="paiementForm" (ngSubmit)="sauverPaiement()">
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
            @if (echeanceChoisie(); as ec) {
              <div class="bea-ct-span2 bea-pay-recap">
                <div><span>Montant échéance</span><strong>{{ ec.montant === null ? '—' : (ec.montant | montant) }}</strong></div>
                <div><span>Déjà payé</span><strong>{{ dejaPaye() | montant }}</strong></div>
                <div><span>Ce paiement</span><strong>{{ paiementForm.controls.montant_paye.value | montant }}</strong></div>
                <div [attr.data-tone]="resteApres() < 0 ? 'danger' : resteApres() === 0 ? 'ok' : null"><span>Reste après</span><strong>{{ resteApres() | montant }}</strong></div>
              </div>
            }
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
          @if (resteApres() < 0) { <p class="bea-ct-help bea-ct-modal__help bea-ct-neg"><mat-icon>error</mat-icon> Le montant versé dépasse le reste dû sur l’échéance : le serveur refusera ce paiement.</p> }
          <p class="bea-ct-help bea-ct-modal__help"><mat-icon>info</mat-icon> Joignez la preuve de paiement depuis la mini-fiche du paiement (« Ajouter un justificatif »).</p>
          <footer class="bea-ct-modal__foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerPaiement()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="paiementForm.invalid || busy() || resteApres() < 0"><mat-icon>save</mat-icon> {{ busy() ? 'Enregistrement…' : 'Enregistrer' }}</button>
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
  private readonly actions = inject(ContratsActionsService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly statuts = STATUTS_CONTRAT;
  readonly etats = ETATS_FILTRE;
  readonly typesEcheance = TYPES_ECHEANCE;
  readonly niveaux = ['CRITIQUE', 'URGENT', 'ATTENTION', 'INFO'];
  readonly typesAlerte = Object.entries(ALERTE_TYPE_LABELS);
  readonly statutsRenouv = ['À préparer', 'En cours', 'En validation', 'Validé', 'Renouvelé', 'Refusé', 'Annulé'];

  readonly colsListe: Array<[string, string]> = [
    ['reference', 'N° contrat'], ['titre', 'Objet'], ['fournisseur', 'Fournisseur'], ['type', 'Type'], ['agence', 'Agence / point'],
    ['debut', 'Début'], ['fin', 'Fin'], ['montant', 'Montant'], ['periodicite', 'Périodicité'], ['statut', 'Statut'],
    ['reconduction', 'Renouvellement'], ['echeance', 'Échéance'],
  ];
  readonly colsEcheances: Array<[string, string]> = [
    ['date', 'Date'], ['jours', 'Jours restants'], ['contrat', 'Contrat'], ['fournisseur', 'Fournisseur'], ['agence', 'Agence'],
    ['type', 'Type'], ['montant', 'Montant'], ['paye', 'Payé'], ['reste', 'Reste'], ['statut', 'Statut'],
  ];
  readonly colsPaiements: Array<[string, string]> = [
    ['ref', 'N° pièce'], ['contrat', 'Contrat'], ['fournisseur', 'Fournisseur'], ['agence', 'Agence'], ['date', 'Date'],
    ['prevu', 'Prévu'], ['paye', 'Versé'], ['ecart', 'Écart'], ['mode', 'Mode'], ['statut', 'Statut'],
  ];

  readonly mode = signal<Mode>('liste');
  readonly config = signal<ContratsConfig | null>(null);
  readonly dashboard = signal<DashboardContrats | null>(null);
  readonly contrats = signal<Contrat[]>([]);
  readonly tous = signal<Contrat[]>([]);
  readonly alertes = signal<Alerte[]>([]);
  readonly echeances = signal<EcheanceRow[]>([]);
  readonly paiements = signal<PaiementRow[]>([]);
  readonly aRenouveler = signal<ARenouveler[]>([]);
  readonly types = signal<Array<{ code: string; libelle: string }>>([]);
  readonly agences = signal<RefItem[]>([]);
  readonly fournisseurs = signal<RefItem[]>([]);
  readonly contratsPayables = signal<Contrat[]>([]);
  readonly echeancesContrat = signal<EcheanceRow[]>([]);
  readonly horizonRenouv = signal('90');
  readonly filtreRenouv = signal('');
  readonly filtreNiveau = signal('');
  readonly filtreType = signal('');
  readonly avance = signal(false);
  readonly chargement = signal(false);
  readonly busy = signal(false);
  readonly paiementOuvert = signal(false);
  readonly paiementEditId = signal<string | null>(null);
  readonly drawer = signal<Drawer | null>(null);
  readonly menu = signal<Menu | null>(null);
  readonly version = signal(0);
  readonly filtreEnregistre = signal<boolean>(!!localStorage.getItem(FILTRE_STOCKAGE));
  private readonly montantSaisi = signal(0);
  private readonly echeanceSaisie = signal('');

  readonly entete = computed(() => TITRES[this.mode()]);
  readonly cap = computed(
    () => this.config()?.capacites ?? { create: false, manage: false, validate: false, settings: false, export: false, ged_write: false },
  );
  readonly totalListe = computed(() => this.contrats().reduce((s, c) => s + num(c.montant), 0));
  readonly resteEcheances = computed(() => this.echeances().reduce((s, e) => s + num(e.reste), 0));
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
  readonly fournisseursNoms = computed(() => this.noms(this.fournisseurs().map((f) => f.raison_sociale || f.libelle || '')));
  readonly agencesNoms = computed(() => this.noms(this.agences().map((a) => a.libelle || '')));

  readonly renouvRows = computed<RenouvRow[]>(() => {
    const index = new Map(this.tous().map((c) => [c.id, c]));
    const filtre = this.filtreRenouv();
    return this.contrats()
      .map((c) => {
        const precedent = c.contrat_precedent_id ? index.get(c.contrat_precedent_id) ?? null : null;
        const v = variation(num(precedent?.montant), num(c.montant));
        return { c, precedent, statut: renouvellementStatut(c), ecart: v.ecart, pct: v.pct, sens: v.sens };
      })
      .filter((r) => !filtre || r.statut.label === filtre);
  });

  readonly echeanceChoisie = computed(() => this.echeancesContrat().find((e) => e.id === this.echeanceSaisie()) ?? null);
  readonly dejaPaye = computed(() => {
    const e = this.echeanceChoisie();
    if (!e) return 0;
    const edit = this.paiementEditId();
    const courant = edit ? this.paiements().find((p) => p.id === edit)?.montant_paye ?? 0 : 0;
    return Math.max(num(e.montant_paye) - courant, 0);
  });
  readonly resteApres = computed(() => {
    const e = this.echeanceChoisie();
    if (!e || e.montant === null) return 0;
    return Math.round((num(e.montant) - this.dejaPaye() - this.montantSaisi()) * 100) / 100;
  });

  readonly filtres = this.fb.nonNullable.group({ q: [''], statut: [''], etat: [''], type_contrat: [''], agence_id: [''], fournisseur_id: [''], horizon: [''] });
  readonly filtreEcheance = this.fb.nonNullable.group({ q: [''], horizon: [''], statut: [''], type_echeance: [''], fournisseur: [''], agence: [''], date_du: [''], date_au: [''] });
  readonly filtrePaiement = this.fb.nonNullable.group({
    q: [''], statut: [''], fournisseur: [''], agence: [''], date_du: [''], date_au: [''],
    montant_min: [null as number | null], montant_max: [null as number | null],
  });
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

  readonly tListe = new TableState<Contrat>(() => this.contrats(), {
    reference: (c) => c.reference, titre: (c) => c.titre, fournisseur: (c) => c.fournisseur_snapshot, type: (c) => this.typeLabel(c.type_contrat),
    agence: (c) => c.agence_libelle_snapshot, debut: (c) => c.date_debut, fin: (c) => c.date_fin, montant: (c) => num(c.montant),
    periodicite: (c) => c.periodicite, statut: (c) => this.statut(c.etat), reconduction: (c) => c.reconduction, echeance: (c) => c.prochain_echeance,
  });
  readonly tAlertes = new TableState<Alerte>(() => this.alertesFiltrees(), {});
  readonly tEcheances = new TableState<EcheanceRow>(() => this.echeances(), {
    date: (e) => e.date_prevue, jours: (e) => e.jours, contrat: (e) => e.reference, fournisseur: (e) => e.fournisseur, agence: (e) => e.agence,
    type: (e) => e.type_echeance, montant: (e) => e.montant, paye: (e) => e.montant_paye, reste: (e) => e.reste, statut: (e) => e.statut,
  });
  readonly tPaiements = new TableState<PaiementRow>(() => this.paiements(), {
    ref: (p) => p.paiement_ref, contrat: (p) => p.reference, fournisseur: (p) => p.fournisseur, agence: (p) => p.agence, date: (p) => p.date_reelle || p.date_prevue,
    prevu: (p) => p.montant_prevu, paye: (p) => p.montant_paye, ecart: (p) => p.ecart, mode: (p) => p.mode, statut: (p) => p.statut,
  });
  readonly tARenouveler = new TableState<ARenouveler>(() => this.aRenouveler(), {});
  readonly tRenouv = new TableState<RenouvRow>(() => this.renouvRows(), {});

  ngOnInit(): void {
    this.api.get<ContratsConfig>('/mg/contrats/config').subscribe({ next: (c) => this.config.set(c), error: (e) => this.fail(e) });
    this.api.get<Array<{ code: string; libelle: string }>>('/mg/contrats/types').subscribe({ next: (r) => this.types.set(r), error: () => undefined });
    this.api.get<RefItem[]>('/mg/contrats/agences').subscribe({ next: (r) => this.agences.set(r), error: () => undefined });
    this.api.get<RefItem[]>('/mg/contrats/fournisseurs').subscribe({ next: (r) => this.fournisseurs.set(r), error: () => undefined });
    this.paiementForm.controls.montant_paye.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.montantSaisi.set(num(v)));
    this.paiementForm.controls.echeance_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.echeanceSaisie.set(v || ''));
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.sync());
  }

  private sync(): void {
    const path = (this.route.snapshot.routeConfig?.path ?? 'liste') as Mode;
    const changeMode = path !== this.mode();
    this.mode.set(path in TITRES ? path : 'liste');
    this.fermerPaiement(true);
    if (changeMode) {
      this.avance.set(false);
      this.drawer.set(null);
    }
    const qp = this.route.snapshot.queryParamMap;
    if (this.mode() === 'liste') {
      this.filtres.patchValue({
        q: qp.get('q') || '',
        statut: qp.get('statut') || '',
        etat: qp.get('etat') || '',
        type_contrat: qp.get('type') || '',
        agence_id: qp.get('agence') || '',
        fournisseur_id: qp.get('fournisseur') || '',
        horizon: qp.get('horizon') || '',
      });
      this.tListe.reinit();
    }
    if (this.mode() === 'paiements') this.filtrePaiement.patchValue({ statut: qp.get('statut') || '' });
    if (this.mode() === 'echeances') this.filtreEcheance.patchValue({ statut: qp.get('statut') || '', horizon: qp.get('horizon') || '' });
    if (this.mode() === 'alertes') this.filtreNiveau.set(qp.get('niveau') || '');
    const voir = qp.get('voir');
    if (voir) this.voirContrat(voir);
    this.charger();
  }

  charger(): void {
    switch (this.mode()) {
      case 'liste':
        this.chargerListe();
        this.api.get<DashboardContrats>('/mg/contrats/dashboard').subscribe({ next: (d) => this.dashboard.set(d), error: () => undefined });
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
        this.api.get<Contrat[]>('/mg/contrats', { size: '500' }).subscribe({ next: (r) => this.tous.set(r), error: () => undefined });
        break;
    }
  }

  // ——— Registre ———

  private paramsListe(): Record<string, string> {
    const raw = this.filtres.getRawValue();
    const params: Record<string, string> = {};
    if (raw.q.trim()) params['q'] = raw.q.trim();
    for (const k of ['statut', 'etat', 'type_contrat', 'agence_id', 'fournisseur_id', 'horizon'] as const) if (raw[k]) params[k] = raw[k];
    return params;
  }

  private chargerListe(): void {
    this.chargement.set(!this.contrats().length);
    this.api.get<Contrat[]>('/mg/contrats', { ...this.paramsListe(), size: '500' }).subscribe({
      next: (r) => {
        this.contrats.set(r);
        this.chargement.set(false);
      },
      error: (e) => {
        this.chargement.set(false);
        this.fail(e);
      },
    });
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
        fournisseur: raw.fournisseur_id || null,
        horizon: raw.horizon || null,
      },
    });
  }

  filtreRapide(patch: Partial<{ statut: string; etat: string }>): void {
    const raw = this.filtres.getRawValue();
    const actif = (patch.statut && raw.statut === patch.statut) || (patch.etat && raw.etat === patch.etat);
    this.filtres.reset({ q: '', statut: '', etat: '', type_contrat: '', agence_id: '', fournisseur_id: '', horizon: '' });
    if (!actif) this.filtres.patchValue(patch);
    this.appliquerFiltres();
  }

  filtresActifs(): boolean {
    return Object.values(this.filtres.getRawValue()).some((v) => !!String(v).trim());
  }

  nbAvances(): number {
    const raw = this.filtres.getRawValue();
    return [raw.etat, raw.agence_id, raw.fournisseur_id, raw.horizon].filter(Boolean).length;
  }

  reinitialiser(): void {
    this.filtres.reset({ q: '', statut: '', etat: '', type_contrat: '', agence_id: '', fournisseur_id: '', horizon: '' });
    this.appliquerFiltres();
  }

  enregistrerFiltre(): void {
    localStorage.setItem(FILTRE_STOCKAGE, JSON.stringify(this.filtres.getRawValue()));
    this.filtreEnregistre.set(true);
    this.feedback.success({ title: 'Filtre enregistré', message: 'Retrouvez-le via « Mon filtre » sur ce poste.' });
  }

  restaurerFiltre(): void {
    try {
      const v = JSON.parse(localStorage.getItem(FILTRE_STOCKAGE) || '{}');
      this.filtres.patchValue(v);
      this.appliquerFiltres();
    } catch {
      localStorage.removeItem(FILTRE_STOCKAGE);
      this.filtreEnregistre.set(false);
    }
  }

  allerRenouvellements(): void {
    void this.router.navigateByUrl('/contrats-echeances/renouvellements');
  }

  // ——— Échéances ———

  private paramsEcheances(): Record<string, string> {
    const raw = this.filtreEcheance.getRawValue();
    const params: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw)) if (String(v).trim()) params[k] = String(v).trim();
    return params;
  }

  chargerEcheances(): void {
    this.chargement.set(!this.echeances().length);
    this.tEcheances.reinit();
    this.api.get<EcheanceRow[]>('/mg/contrats/echeances', this.paramsEcheances()).subscribe({
      next: (r) => {
        this.echeances.set(r);
        this.chargement.set(false);
      },
      error: (e) => {
        this.chargement.set(false);
        this.fail(e);
      },
    });
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

  reinitEcheances(): void {
    this.filtreEcheance.reset();
    this.chargerEcheances();
  }

  voirEcheance(e: EcheanceRow, onglet = 'detail', action: 'reporter' | null = null): void {
    this.drawer.set({ type: 'echeance', contratId: e.contrat_id, id: e.id, onglet, action });
  }

  menuEcheance(ev: MouseEvent, e: EcheanceRow): void {
    const items: Menu['items'] = [];
    const modifiable = this.cap().manage && !['ARCHIVE', 'ANNULE'].includes(e.contrat_statut);
    if (modifiable && this.ouverte(e)) {
      items.push({ icone: 'event_repeat', label: 'Reporter', action: () => this.voirEcheance(e, 'detail', 'reporter') });
      items.push({ icone: 'event_busy', label: 'Annuler', danger: true, action: () => this.actions.annulerEcheance(e, this.busy).subscribe(() => this.apresAction()) });
    }
    if (modifiable && e.statut === 'ANNULEE') items.push({ icone: 'restore', label: 'Rétablir', action: () => this.actions.retablirEcheance(e, this.busy).subscribe(() => this.apresAction()) });
    items.push({ icone: 'folder_open', label: 'Documents', action: () => this.voirEcheance(e, 'documents') });
    items.push({ icone: 'history', label: 'Historique', action: () => this.voirEcheance(e, 'historique') });
    items.push({ icone: 'description', label: 'Voir le contrat', action: () => this.voirContrat(e.contrat_id, 'echeances') });
    if (modifiable && e.montant_paye === 0) items.push({ icone: 'delete', label: 'Supprimer', danger: true, action: () => this.actions.supprimerEcheance(e, this.busy).subscribe(() => this.apresAction()) });
    this.ouvrirMenu(ev, items);
  }

  // ——— Paiements ———

  private paramsPaiements(): Record<string, string> {
    const raw = this.filtrePaiement.getRawValue();
    const params: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw)) if (v !== null && String(v).trim()) params[k] = String(v).trim();
    return params;
  }

  chargerPaiements(): void {
    this.chargement.set(!this.paiements().length);
    this.tPaiements.reinit();
    this.api.get<PaiementRow[]>('/mg/contrats/paiements', this.paramsPaiements()).subscribe({
      next: (r) => {
        this.paiements.set(r);
        this.chargement.set(false);
      },
      error: (e) => {
        this.chargement.set(false);
        this.fail(e);
      },
    });
  }

  reinitPaiements(): void {
    this.filtrePaiement.reset();
    this.chargerPaiements();
  }

  voirPaiement(p: PaiementRow, onglet = 'detail'): void {
    this.drawer.set({ type: 'paiement', contratId: p.contrat_id, id: p.id, onglet });
  }

  menuPaiement(ev: MouseEvent, p: PaiementRow): void {
    const items: Menu['items'] = [];
    if (this.cap().ged_write) items.push({ icone: 'attach_file', label: 'Ajouter un justificatif', action: () => this.voirPaiement(p, 'documents') });
    items.push({ icone: 'history', label: 'Historique', action: () => this.voirPaiement(p, 'historique') });
    items.push({ icone: 'description', label: 'Voir le contrat', action: () => this.voirContrat(p.contrat_id, 'paiements') });
    if (this.cap().manage && this.regleable(p.contrat_statut)) {
      items.push({ icone: 'delete', label: 'Supprimer', danger: true, action: () => this.actions.supprimerPaiement(p, this.busy).subscribe(() => this.apresAction()) });
    }
    this.ouvrirMenu(ev, items);
  }

  // ——— Renouvellements ———

  changerHorizon(h: string): void {
    this.horizonRenouv.set(h);
    this.charger();
  }

  reconduire(r: ARenouveler): void {
    this.actions.reconduire(r, this.busy).subscribe(() => this.charger());
  }

  renouveler(r: ARenouveler): void {
    this.actions.renouveler(r, this.busy).subscribe((n) => void this.router.navigateByUrl(`/contrats-echeances/${n.id}`));
  }

  // ——— Mini-pages, menu, export ———

  voirContrat(id: string, onglet = 'resume'): void {
    this.drawer.set({ type: 'contrat', contratId: id, onglet });
  }

  fermerDrawer(): void {
    this.drawer.set(null);
    if (this.route.snapshot.queryParamMap.get('voir')) {
      void this.router.navigate([], { relativeTo: this.route, queryParams: { voir: null }, queryParamsHandling: 'merge', replaceUrl: true });
    }
  }

  menuContrat(ev: MouseEvent, c: Contrat): void {
    const items: Menu['items'] = [
      { icone: 'event', label: 'Échéances', action: () => this.voirContrat(c.id, 'echeances') },
      { icone: 'payments', label: 'Paiements', action: () => this.voirContrat(c.id, 'paiements') },
      { icone: 'receipt_long', label: 'Facturation', action: () => this.voirContrat(c.id, 'facturation') },
      { icone: 'autorenew', label: 'Renouveler', action: () => this.voirContrat(c.id, 'renouvellements') },
      { icone: 'history', label: 'Historique', action: () => this.voirContrat(c.id, 'historique') },
      { icone: 'picture_as_pdf', label: 'Fiche PDF', action: () => this.actions.pdf(c, this.busy) },
    ];
    if (this.cap().manage && SUPPRIMABLES.has(c.statut)) items.push({ icone: 'delete', label: 'Retirer du registre', danger: true, action: () => this.supprimerContrat(c) });
    this.ouvrirMenu(ev, items);
  }

  private ouvrirMenu(ev: MouseEvent, items: Menu['items']): void {
    const r = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const hauteur = items.length * 38 + 12;
    const top = r.bottom + hauteur > window.innerHeight ? Math.max(8, r.top - hauteur) : r.bottom + 4;
    this.menu.set({ top, left: Math.max(8, Math.min(r.right - 220, window.innerWidth - 228)), items });
  }

  private apresAction(): void {
    this.version.update((v) => v + 1);
    this.charger();
  }

  private exportCourant(): { rapport: string; filtres: Record<string, string> } | null {
    switch (this.mode()) {
      case 'liste':
        return { rapport: 'registre', filtres: this.paramsListe() };
      case 'echeances':
        return { rapport: 'echeancier', filtres: this.paramsEcheances() };
      case 'paiements':
        return { rapport: 'reglements', filtres: this.paramsPaiements() };
      default:
        return null;
    }
  }

  exporter(fmt: 'pdf' | 'xlsx'): void {
    const e = this.exportCourant();
    if (e) this.actions.exporter(e.rapport, fmt, e.filtres, this.busy);
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
      .subscribe(() => this.charger());
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

  // ——— Paiement (création / modification) ———

  private chargerPayables(): void {
    if (this.contratsPayables().length) return;
    this.api.get<Contrat[]>('/mg/contrats', { size: '500' }).subscribe({
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
    if (!this.paiements().some((x) => x.id === p.id)) this.paiements.update((rows) => [...rows, p]);
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
    if (this.paiementForm.invalid || this.resteApres() < 0) return;
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
        this.apresAction();
      });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.menu()) return this.menu.set(null);
    this.fermerPaiement();
  }

  @HostListener('window:resize')
  @HostListener('window:scroll')
  fermerMenu(): void {
    if (this.menu()) this.menu.set(null);
  }

  // ——— Libellés ———

  compteNiveau(n: string): number {
    return this.alertes().filter((a) => a.niveau === n).length;
  }

  private noms(liste: string[]): string[] {
    return [...new Set(liste.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'));
  }

  ouverte(e: EcheanceRow): boolean {
    return ['A_VENIR', 'DUE', 'EN_RETARD'].includes(e.statut);
  }

  peutRegler(e: EcheanceRow): boolean {
    return this.cap().manage && e.type_echeance === 'PAIEMENT' && e.reste > 0 && this.regleable(e.contrat_statut);
  }

  verrouille(statut: string): boolean {
    return statut === 'ARCHIVE' || statut === 'ANNULE';
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

  statutEch(e: EcheanceRow): string {
    return echeanceStatutLabel(e.statut, e.commentaire);
  }

  reconduction(code: string): string {
    return RECONDUCTION_LABELS[code] ?? code;
  }

  reconductionCourt(code: string): string {
    return ({ TACITE: 'Tacite', EXPRESSE: 'Expresse', AUCUNE: 'Aucune' } as Record<string, string>)[code] ?? code;
  }

  periodicite(code: string): string {
    return PERIODICITE_LABELS[code] ?? code;
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
