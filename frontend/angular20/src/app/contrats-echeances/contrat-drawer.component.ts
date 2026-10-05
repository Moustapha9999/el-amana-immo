import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { formatMontant } from '../shared/montant.pipe';
import { ContratsActionsService } from './contrats-actions.service';
import { ContratsDocumentsComponent } from './contrats-documents.component';
import { EcheanceDrawerComponent, PaiementDrawerComponent, timeline } from './contrats-mini-pages.component';
import {
  Contrat,
  ContratsConfig,
  EcheanceRow,
  FacturesContrat,
  PERIODICITE_LABELS,
  PaiementRow,
  RECONDUCTION_LABELS,
  TYPE_AVENANT_LABELS,
  dateFr,
  echeanceStatutLabel,
  joursLabel,
  num,
  renouvellementStatut,
  statutLabel,
  typeEcheanceLabel,
  variation,
} from './contrats.models';
import { fxStatut, fxTone } from './facturation/facturation.models';
import { DetailDrawerComponent, DetailTimelineComponent, DrawerKpi, DrawerTab } from './shared/detail-drawer.component';

const VERROUILLES = new Set(['ARCHIVE', 'ANNULE']);
const OUVERTES = new Set(['A_VENIR', 'DUE', 'EN_RETARD']);

interface AlerteResume {
  tone: 'ok' | 'warn' | 'danger';
  icone: string;
  texte: string;
}

interface Periode {
  libelle: string;
  debut: string | null;
  fin: string | null;
  montant: number;
  source: string;
}

/** Mini-page contrat : résumé, informations, facturation, échéances, paiements, renouvellements, documents, historique. */
@Component({
  selector: 'bea-ct-contrat-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, DetailDrawerComponent, DetailTimelineComponent, ContratsDocumentsComponent, EcheanceDrawerComponent, PaiementDrawerComponent],
  template: `
    <bea-detail-drawer
      kicker="Contrat"
      [titre]="c() ? c()!.reference + ' · ' + c()!.titre : null"
      [sousTitre]="c() ? (c()!.fournisseur_snapshot || 'Sans fournisseur') + ' · ' + (c()!.agence_libelle_snapshot || 'Toutes agences') + ' · ' + typeLabel(c()!.type_contrat) : null"
      [chargement]="chargement()"
      [erreur]="erreur()"
      [kpis]="kpis()"
      [onglets]="onglets()"
      [(onglet)]="onglet"
      [large]="true"
      (fermer)="fermer.emit()"
      (reessayer)="charger()"
    >
      @if (c(); as c) {
        <ng-container drawerBadges>
          <span class="bea-ct-badge" [attr.data-tone]="c.etat">{{ statut(c.etat) }}</span>
          @if (c.version > 1) { <span class="bea-ct-badge" data-tone="INFO">v{{ c.version }}</span> }
        </ng-container>
      }
      @if (c(); as c) {
        <ng-container drawerActions>
          <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/contrats-echeances', c.id]"><mat-icon>{{ modifiable() ? 'edit' : 'open_in_new' }}</mat-icon> {{ modifiable() ? 'Modifier' : 'Fiche complète' }}</a>
          @if (renouvelable()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="reconduire()"><mat-icon>update</mat-icon> Reconduire</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="renouveler()"><mat-icon>autorenew</mat-icon> Renouveler</button>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="pdf()"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
        </ng-container>
      }
      @if (c(); as c) {
        @switch (onglet()) {
          @case ('resume') {
            <ul class="bea-dd__alerts">
              @for (a of alertes(); track a.texte) { <li [attr.data-tone]="a.tone"><mat-icon>{{ a.icone }}</mat-icon> {{ a.texte }}</li> }
            </ul>
            <div class="bea-fx-mini">
              <div><span>Statut</span><strong>{{ statut(c.statut) }}</strong><small>{{ statut(c.etat) }}</small></div>
              <div><span>Fournisseur</span><strong>{{ c.fournisseur_snapshot || '—' }}</strong></div>
              <div><span>Montant TTC</span><strong>{{ m(num(c.montant)) }}</strong><small>{{ c.devise }} · {{ periodicite(c.periodicite) }}</small></div>
              <div><span>Prochaine échéance</span>
                @if (prochaine(); as p) { <strong>{{ date(p.date_prevue) }}</strong><small>{{ type(p.type_echeance) }} · {{ jours(p.jours) }}</small> } @else { <strong>—</strong> }
              </div>
              <div><span>Dernière facture</span>
                @if (derniereFacture(); as f) { <strong>{{ f.periode_label || date(f.date_facture) }}</strong><small>{{ f.montant_a_payer === null ? '—' : m(f.montant_a_payer) }} · {{ fx(f.statut_affiche) }}</small> } @else { <strong>—</strong><small>{{ facturesErreur() || 'Aucune facture' }}</small> }
              </div>
              <div><span>Dernier paiement</span>
                @if (dernierPaiement(); as p) { <strong>{{ date(p.date_reelle) }}</strong><small>{{ m(p.montant_paye) }} · {{ p.mode || '—' }}</small> } @else { <strong>—</strong> }
              </div>
              <div><span>Renouvellement</span><strong>{{ date(c.date_fin) }}</strong><small>{{ reconduction(c.reconduction) }}@if (c.date_preavis) { · préavis {{ date(c.date_preavis) }} }</small></div>
              <div><span>Reste à payer</span><strong>{{ m(resteAPayer()) }}</strong><small>{{ echeancesOuvertes() }} échéance(s) ouverte(s)</small></div>
            </div>
          }
          @case ('infos') {
            <dl class="bea-fx-dl">
              <dt>Référence</dt><dd>{{ c.reference }}@if (c.numero_contrat) { <small> · n° {{ c.numero_contrat }}</small> }</dd>
              <dt>Objet</dt><dd>{{ c.titre }}</dd>
              <dt>Type</dt><dd>{{ typeLabel(c.type_contrat) }}</dd>
              <dt>Fournisseur</dt><dd>{{ c.fournisseur_snapshot || '—' }}</dd>
              <dt>Agence / point</dt><dd>{{ c.agence_libelle_snapshot || '—' }}</dd>
              <dt>Responsable</dt><dd>{{ c.responsable_nom || '—' }}</dd>
              <dt>Signature</dt><dd>{{ date(c.date_signature) }}</dd>
              <dt>Période</dt><dd>du {{ date(c.date_debut) }} au {{ date(c.date_fin) }}@if (c.jours_restants !== null) { <small [class.bea-ct-neg]="c.jours_restants < 0"> {{ jours(c.jours_restants) }}</small> }</dd>
              <dt>Montant HT</dt><dd>{{ c.montant_ht === null ? '—' : m(num(c.montant_ht)) }}</dd>
              <dt>TVA</dt><dd>{{ c.taux_tva === null ? '—' : num(c.taux_tva) + ' %' }}</dd>
              <dt>Montant TTC</dt><dd>{{ m(num(c.montant)) }} {{ c.devise }}</dd>
              <dt>Périodicité</dt><dd>{{ periodicite(c.periodicite) }}</dd>
              <dt>Mode de paiement</dt><dd>{{ c.mode_paiement || '—' }}@if (c.ref_paiement) { <small> · {{ c.ref_paiement }}</small> }</dd>
              <dt>Reconduction</dt><dd>{{ reconduction(c.reconduction) }}@if (c.preavis_jours) { <small> · préavis {{ c.preavis_jours }} j</small> }</dd>
              <dt>Alerte</dt><dd>{{ c.alerte_jours }} j avant échéance</dd>
              @if (c.description) { <dt>Description</dt><dd class="bea-fx-dl__wrap">{{ c.description }}</dd> }
              @if (c.observation) { <dt>Observation</dt><dd class="bea-fx-dl__wrap">{{ c.observation }}</dd> }
            </dl>
          }
          @case ('facturation') {
            @if (facturesErreur(); as err) {
              <p class="bea-ct-help"><mat-icon>lock</mat-icon> {{ err }}</p>
            } @else if (factures(); as fxs) {
              <div class="bea-fx-mini">
                <div><span>Factures</span><strong>{{ fxs.nb }}</strong></div>
                <div><span>Total</span><strong>{{ m(fxs.total) }}</strong></div>
                <div><span>Reste à payer</span><strong>{{ m(fxs.reste) }}</strong></div>
              </div>
              <table class="bea-mg__table bea-ct-table bea-fx-mini">
                <thead><tr><th>Période</th><th>Référence</th><th>Point</th><th class="is-num">À payer</th><th class="is-num">Reste</th><th>Statut</th><th></th></tr></thead>
                <tbody>
                  @for (f of fxs.items; track f.id) {
                    <tr>
                      <td>{{ f.periode_label || date(f.date_facture) }}</td><td><code class="bea-mg__code">{{ f.reference }}</code></td><td>{{ f.point_nom || f.numero_fournisseur || '—' }}</td>
                      <td class="is-num">{{ f.montant_a_payer === null ? '—' : m(f.montant_a_payer) }}</td><td class="is-num">{{ f.reste === null ? '—' : m(f.reste) }}</td>
                      <td><span class="bea-ct-badge" [attr.data-tone]="fxTone(f.statut_affiche)">{{ fx(f.statut_affiche) }}</span></td>
                      <td><a class="bea-mg__icon-btn" title="Voir la facture" [routerLink]="'/contrats-echeances/factures/liste'" [queryParams]="{ facture: f.id }"><mat-icon>visibility</mat-icon></a></td>
                    </tr>
                  } @empty { <tr><td colspan="7"><div class="bea-ct-empty"><mat-icon>receipt_long</mat-icon><p>Aucune facture rattachée à ce contrat.</p></div></td></tr> }
                </tbody>
              </table>
            } @else {
              @for (i of [1, 2, 3]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
            }
          }
          @case ('echeances') {
            <table class="bea-mg__table bea-ct-table bea-fx-mini">
              <thead><tr><th>Date</th><th>Type</th><th class="is-num">Montant</th><th class="is-num">Reste</th><th>Statut</th><th></th></tr></thead>
              <tbody>
                @for (e of echeances(); track e.id) {
                  <tr>
                    <td>{{ date(e.date_prevue) }}@if (ouverte(e)) { <small class="bea-ct-sub" [class.bea-ct-neg]="e.jours < 0">{{ jours(e.jours) }}</small> }</td>
                    <td>{{ type(e.type_echeance) }}</td>
                    <td class="is-num">{{ e.montant === null ? '—' : m(e.montant) }}</td>
                    <td class="is-num">{{ m(e.reste) }}</td>
                    <td><span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statutEch(e) }}</span></td>
                    <td class="is-nowrap">
                      <span class="bea-row-actions">
                        <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="echeanceOuverte.set(e.id)"><mat-icon>visibility</mat-icon></button>
                        @if (peutRegler(e)) { <button type="button" class="bea-mg__icon-btn" title="Marquer payée" (click)="payer.emit(e)"><mat-icon>price_check</mat-icon></button> }
                      </span>
                    </td>
                  </tr>
                } @empty { <tr><td colspan="6"><div class="bea-ct-empty"><mat-icon>event</mat-icon><p>Aucune échéance : l’échéancier est généré à la validation.</p></div></td></tr> }
              </tbody>
            </table>
          }
          @case ('paiements') {
            <table class="bea-mg__table bea-ct-table bea-fx-mini">
              <thead><tr><th>N° pièce</th><th>Payé le</th><th class="is-num">Prévu</th><th class="is-num">Versé</th><th>Mode</th><th>Statut</th><th></th></tr></thead>
              <tbody>
                @for (p of paiements(); track p.id) {
                  <tr>
                    <td><code class="bea-mg__code">{{ p.paiement_ref || '—' }}</code></td><td>{{ date(p.date_reelle) }}</td>
                    <td class="is-num">{{ m(p.montant_prevu) }}</td><td class="is-num">{{ m(p.montant_paye) }}</td><td>{{ p.mode || '—' }}</td>
                    <td><span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statut(p.statut) }}</span></td>
                    <td><button type="button" class="bea-mg__icon-btn" title="Voir" (click)="paiementOuvert.set(p.id)"><mat-icon>visibility</mat-icon></button></td>
                  </tr>
                } @empty { <tr><td colspan="7"><div class="bea-ct-empty"><mat-icon>payments</mat-icon><p>Aucun paiement enregistré.</p></div></td></tr> }
              </tbody>
            </table>
          }
          @case ('renouvellements') {
            @if (periodes().length > 1) {
              <h3 class="bea-fx-drawer__h3"><mat-icon>compare_arrows</mat-icon> Dernière variation</h3>
              @let v = derniereVariation();
              <div class="bea-fx-mini">
                <div><span>Ancienne période</span><strong>{{ date(periodes()[1].debut) }} → {{ date(periodes()[1].fin) }}</strong><small>{{ m(periodes()[1].montant) }}</small></div>
                <div><span>Nouvelle période</span><strong>{{ date(periodes()[0].debut) }} → {{ date(periodes()[0].fin) }}</strong><small>{{ m(periodes()[0].montant) }}</small></div>
                <div><span>Variation</span><strong class="bea-dd__variation" [attr.data-sens]="v.sens">{{ v.ecart > 0 ? '+' : '' }}{{ m(v.ecart) }}</strong><small>{{ v.pct === null ? '—' : (v.pct > 0 ? '+' : '') + v.pct + ' %' }}</small></div>
              </div>
            }
            <h3 class="bea-fx-drawer__h3"><mat-icon>history</mat-icon> Périodes successives</h3>
            <table class="bea-mg__table bea-ct-table bea-fx-mini">
              <thead><tr><th>Période</th><th>Début</th><th>Fin</th><th class="is-num">Montant TTC</th><th>Origine</th></tr></thead>
              <tbody>
                @for (p of periodes(); track $index) {
                  <tr><td>{{ p.libelle }}</td><td>{{ date(p.debut) }}</td><td>{{ date(p.fin) }}</td><td class="is-num">{{ m(p.montant) }}</td><td>{{ p.source }}</td></tr>
                }
              </tbody>
            </table>
            @if (precedent(); as pr) {
              <p class="bea-ct-note">Issu du renouvellement de <a class="bea-ct-link" [routerLink]="['/contrats-echeances', pr.id]">{{ pr.reference }}</a> ({{ date(pr.date_debut) }} → {{ date(pr.date_fin) }}, {{ m(num(pr.montant)) }}).
                Statut du renouvellement : <span class="bea-ct-badge" [attr.data-tone]="renouv(c).code">{{ renouv(c).label }}</span></p>
            }
            @if (suivant(); as s) {
              <p class="bea-ct-note">Renouvelé par <a class="bea-ct-link" [routerLink]="['/contrats-echeances', s.id]">{{ s.reference }}</a> — <span class="bea-ct-badge" [attr.data-tone]="renouv(s).code">{{ renouv(s).label }}</span></p>
            }
          }
          @case ('documents') {
            <bea-contrats-documents [contratId]="c.id" [reference]="c.reference" [lectureSeule]="!config()?.capacites?.ged_write || verrouille()"
              [typesDocument]="config()?.types_document ?? []" [tailleMaxMo]="config()?.ged_taille_max_mo ?? 15" />
          }
          @case ('historique') {
            <bea-detail-timeline [items]="historique()" />
          }
        }
      }
    </bea-detail-drawer>

    @if (echeanceOuverte(); as eid) {
      <bea-ct-echeance-drawer [contratId]="contratId()" [echeanceId]="eid" [config]="config()" [dessus]="true" [version]="version()"
        (fermer)="echeanceOuverte.set(null)" (payer)="payer.emit($event)" (modifie)="recharger()" (ouvrirContrat)="echeanceOuverte.set(null)" />
    }
    @if (paiementOuvert(); as pid) {
      <bea-ct-paiement-drawer [contratId]="contratId()" [paiementId]="pid" [config]="config()" [dessus]="true" [version]="version()"
        (fermer)="paiementOuvert.set(null)" (editer)="editer.emit($event)" (modifie)="recharger()" (ouvrirContrat)="paiementOuvert.set(null)" />
    }
  `,
})
export class ContratDrawerComponent {
  private readonly api = inject(ApiService);
  private readonly actions = inject(ContratsActionsService);
  private readonly router = inject(Router);

  readonly contratId = input.required<string>();
  readonly config = input<ContratsConfig | null>(null);
  readonly types = input<Array<{ code: string; libelle: string }>>([]);
  readonly ongletInitial = input('resume');
  /** Incrémenté par le parent après un paiement enregistré ailleurs. */
  readonly version = input(0);
  readonly fermer = output<void>();
  readonly payer = output<EcheanceRow>();
  readonly editer = output<PaiementRow>();
  readonly modifie = output<void>();

  readonly onglet = signal('resume');
  readonly c = signal<Contrat | null>(null);
  readonly echeances = signal<EcheanceRow[]>([]);
  readonly paiements = signal<PaiementRow[]>([]);
  readonly factures = signal<FacturesContrat | null>(null);
  readonly facturesErreur = signal<string | null>(null);
  readonly precedent = signal<Contrat | null>(null);
  readonly suivant = signal<Contrat | null>(null);
  readonly chargement = signal(true);
  readonly erreur = signal<string | null>(null);
  readonly busy = signal(false);
  readonly echeanceOuverte = signal<string | null>(null);
  readonly paiementOuvert = signal<string | null>(null);

  readonly num = num;
  readonly verrouille = computed(() => !this.c() || VERROUILLES.has(this.c()!.statut));
  readonly modifiable = computed(() => !!this.config()?.capacites.manage && !this.verrouille());
  readonly renouvelable = computed(() => !!this.config()?.capacites.manage && ['ACTIF', 'EXPIRE'].includes(this.c()?.statut ?? '') && !!this.c()?.date_fin);
  readonly prochaine = computed(() => this.echeances().filter((e) => OUVERTES.has(e.statut)).sort((a, b) => a.date_prevue.localeCompare(b.date_prevue))[0] ?? null);
  readonly echeancesOuvertes = computed(() => this.echeances().filter((e) => OUVERTES.has(e.statut)).length);
  readonly resteAPayer = computed(() => this.echeances().reduce((s, e) => s + (OUVERTES.has(e.statut) ? e.reste : 0), 0));
  readonly dernierPaiement = computed(() =>
    this.paiements().filter((p) => p.date_reelle).sort((a, b) => (b.date_reelle ?? '').localeCompare(a.date_reelle ?? ''))[0] ?? null,
  );
  readonly derniereFacture = computed(() => this.factures()?.items[0] ?? null);
  readonly historique = computed(() => timeline(this.c()?.historique));

  readonly onglets = computed<DrawerTab[]>(() => [
    { key: 'resume', label: 'Résumé' },
    { key: 'infos', label: 'Informations' },
    { key: 'facturation', label: 'Facturation', count: this.factures()?.nb ?? null },
    { key: 'echeances', label: 'Échéances', count: this.echeances().length },
    { key: 'paiements', label: 'Paiements', count: this.paiements().length },
    { key: 'renouvellements', label: 'Renouvellements' },
    { key: 'documents', label: 'Documents' },
    { key: 'historique', label: 'Historique', count: this.c()?.historique?.length ?? null },
  ]);

  readonly kpis = computed<DrawerKpi[]>(() => {
    const c = this.c();
    if (!c) return [];
    const paye = this.paiements().reduce((s, p) => s + p.montant_paye, 0);
    const retard = this.echeances().filter((e) => e.statut === 'EN_RETARD').length;
    return [
      { label: 'Montant TTC', value: formatMontant(num(c.montant)), hint: c.devise },
      { label: 'Payé', value: formatMontant(paye), hint: c.devise, tone: 'ok' },
      { label: 'Reste à payer', value: formatMontant(this.resteAPayer()), hint: retard ? `${retard} en retard` : c.devise, tone: retard ? 'danger' : this.resteAPayer() ? 'warn' : null },
      { label: 'Fin de contrat', value: dateFr(c.date_fin), hint: c.jours_restants === null ? null : joursLabel(c.jours_restants), tone: (c.jours_restants ?? 99) < 0 ? 'danger' : (c.jours_restants ?? 99) <= 30 ? 'warn' : null },
    ];
  });

  readonly alertes = computed<AlerteResume[]>(() => {
    const c = this.c();
    if (!c) return [];
    const out: AlerteResume[] = [];
    if (c.etat === 'DATE_DEPASSEE') out.push({ tone: 'danger', icone: 'event_busy', texte: 'Date de fin dépassée : contrat toujours actif, à renouveler ou clôturer.' });
    else if (c.jours_restants !== null && c.jours_restants >= 0 && c.jours_restants <= 30 && ['ACTIF', 'SUSPENDU'].includes(c.statut)) {
      out.push({ tone: 'warn', icone: 'schedule', texte: `Fin de contrat ${joursLabel(c.jours_restants).toLowerCase()}.` });
    }
    if (c.date_preavis && ['ACTIF', 'SUSPENDU'].includes(c.statut)) {
      const j = Math.round((new Date(c.date_preavis).getTime() - Date.now()) / 86400000);
      if (j >= 0 && j <= 30) out.push({ tone: 'warn', icone: 'campaign', texte: `Date limite de préavis le ${dateFr(c.date_preavis)}.` });
    }
    const retard = this.echeances().filter((e) => e.statut === 'EN_RETARD');
    if (retard.length) out.push({ tone: 'danger', icone: 'money_off', texte: `${retard.length} échéance(s) en retard — ${formatMontant(retard.reduce((s, e) => s + e.reste, 0))} ${c.devise}.` });
    if (!c.fournisseur_id) out.push({ tone: 'warn', icone: 'store', texte: 'Aucun fournisseur rattaché.' });
    if (!c.responsable_id && !c.responsable_nom) out.push({ tone: 'warn', icone: 'person_off', texte: 'Aucun responsable : les rappels ne seront pas envoyés.' });
    if (!out.length) out.push({ tone: 'ok', icone: 'check_circle', texte: 'Aucune alerte sur ce contrat.' });
    return out;
  });

  readonly periodes = computed<Periode[]>(() => {
    const c = this.c();
    if (!c) return [];
    const recon = (c.avenants ?? []).filter((a) => a.type_avenant === 'RECONDUCTION').sort((a, b) => b.numero - a.numero);
    const out: Periode[] = [{ libelle: 'Période en cours', debut: recon[0]?.date_effet ?? c.date_debut, fin: c.date_fin, montant: num(c.montant), source: recon.length ? TYPE_AVENANT_LABELS[recon[0].type_avenant] ?? 'Avenant' : 'Contrat initial' }];
    recon.forEach((a, i) => {
      out.push({
        libelle: `Période ${recon.length - i}`,
        debut: recon[i + 1]?.date_effet ?? c.date_debut,
        fin: a.date_fin_avant,
        montant: num(a.montant_ttc_avant),
        source: i === recon.length - 1 ? 'Contrat initial' : TYPE_AVENANT_LABELS[recon[i + 1].type_avenant] ?? 'Avenant',
      });
    });
    const pr = this.precedent();
    if (pr) out.push({ libelle: 'Contrat précédent', debut: pr.date_debut, fin: pr.date_fin, montant: num(pr.montant), source: pr.reference });
    return out;
  });

  readonly derniereVariation = computed(() => {
    const p = this.periodes();
    return variation(p[1]?.montant ?? 0, p[0]?.montant ?? 0);
  });

  constructor() {
    effect(() => {
      const ong = this.ongletInitial();
      this.contratId();
      untracked(() => {
        this.onglet.set(ong);
        this.echeanceOuverte.set(null);
        this.paiementOuvert.set(null);
        this.c.set(null);
        this.charger();
      });
    });
    effect(() => {
      if (this.version()) untracked(() => this.recharger(false));
    });
  }

  charger(): void {
    this.chargement.set(!this.c());
    this.erreur.set(null);
    const id = this.contratId();
    forkJoin({
      contrat: this.api.get<Contrat>(`/mg/contrats/${id}`),
      echeances: this.api.get<EcheanceRow[]>('/mg/contrats/echeances', { contrat_id: id }),
      paiements: this.api.get<PaiementRow[]>('/mg/contrats/paiements', { contrat_id: id }),
    }).subscribe({
      next: (r) => {
        this.c.set(r.contrat);
        this.echeances.set(r.echeances);
        this.paiements.set(r.paiements);
        this.chargement.set(false);
        this.chargerLies(r.contrat);
      },
      error: (e: { status?: number }) => {
        this.chargement.set(false);
        this.erreur.set(e?.status === 404 ? 'Contrat introuvable (supprimé entre-temps ?).' : e?.status === 403 ? 'Accès refusé.' : 'Le serveur n’a pas répondu correctement.');
      },
    });
  }

  private chargerLies(c: Contrat): void {
    this.api.get<FacturesContrat>(`/mg/factures/contrats/${c.id}`).subscribe({
      next: (r) => {
        this.factures.set(r);
        this.facturesErreur.set(null);
      },
      error: (e: { status?: number }) => this.facturesErreur.set(e?.status === 403 ? 'Vous n’avez pas accès à la gestion des factures.' : 'Factures indisponibles pour le moment.'),
    });
    this.precedent.set(null);
    if (c.contrat_precedent_id) {
      this.api.get<Contrat>(`/mg/contrats/${c.contrat_precedent_id}`).subscribe({ next: (p) => this.precedent.set(p), error: () => undefined });
    }
    this.suivant.set(null);
    this.api.get<Contrat[]>('/mg/contrats', { renouveles: 'true' }).subscribe({
      next: (rows) => this.suivant.set(rows.find((x) => x.contrat_precedent_id === c.id && x.statut !== 'ANNULE') ?? null),
      error: () => undefined,
    });
  }

  recharger(emettre = true): void {
    if (emettre) this.modifie.emit();
    this.charger();
  }

  reconduire(): void {
    const c = this.c();
    if (c) this.actions.reconduire(c, this.busy).subscribe(() => this.recharger());
  }

  renouveler(): void {
    const c = this.c();
    if (!c) return;
    this.actions.renouveler(c, this.busy).subscribe((n) => {
      this.modifie.emit();
      void this.router.navigateByUrl(`/contrats-echeances/${n.id}`);
    });
  }

  pdf(): void {
    const c = this.c();
    if (c) this.actions.pdf(c, this.busy);
  }

  ouverte(e: EcheanceRow): boolean {
    return OUVERTES.has(e.statut);
  }
  peutRegler(e: EcheanceRow): boolean {
    return this.modifiable() && e.type_echeance === 'PAIEMENT' && e.reste > 0 && ['ACTIF', 'SUSPENDU', 'EXPIRE'].includes(e.contrat_statut);
  }
  renouv(c: Contrat): { code: string; label: string } {
    return renouvellementStatut(c);
  }
  typeLabel(code: string): string {
    return this.types().find((t) => t.code === code)?.libelle ?? code;
  }
  statutEch(e: EcheanceRow): string {
    return echeanceStatutLabel(e.statut, e.commentaire);
  }
  statut(code: string | null | undefined): string {
    return statutLabel(code);
  }
  periodicite(code: string): string {
    return PERIODICITE_LABELS[code] ?? code;
  }
  reconduction(code: string): string {
    return RECONDUCTION_LABELS[code] ?? code;
  }
  type(code: string): string {
    return typeEcheanceLabel(code);
  }
  fx(code: string): string {
    return fxStatut(code);
  }
  fxTone(code: string): string {
    return fxTone(code);
  }
  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }
  jours(n: number | null | undefined): string {
    return joursLabel(n);
  }
  m(v: number | null | undefined): string {
    return v === null || v === undefined ? '—' : formatMontant(v);
  }
}
