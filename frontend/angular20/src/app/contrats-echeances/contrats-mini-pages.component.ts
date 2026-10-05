import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { formatMontant } from '../shared/montant.pipe';
import { ContratsActionsService } from './contrats-actions.service';
import { ContratsDocumentsComponent } from './contrats-documents.component';
import {
  ACTION_LABELS,
  Contrat,
  ContratsConfig,
  EcheanceRow,
  Hist,
  PaiementRow,
  dateFr,
  dateHeureFr,
  echeanceStatutLabel,
  joursLabel,
  statutLabel,
  typeEcheanceLabel,
} from './contrats.models';
import { DetailDrawerComponent, DetailTimelineComponent, DrawerKpi, JalonsComponent, TimelineItem } from './shared/detail-drawer.component';

const VERROUILLES = new Set(['ARCHIVE', 'ANNULE']);
const REGLEABLES = new Set(['ACTIF', 'SUSPENDU', 'EXPIRE']);

function montant(v: number | null | undefined, devise = ''): string {
  return v === null || v === undefined ? '—' : `${formatMontant(v)}${devise ? ' ' + devise : ''}`;
}

function messageErreur(e: unknown): string {
  const s = (e as { status?: number })?.status;
  return s === 403 ? 'Accès refusé.' : s === 404 ? 'Élément introuvable (supprimé entre-temps ?).' : 'Le serveur n’a pas répondu correctement.';
}

export function timeline(historique: Hist[] | undefined, filtre?: (h: Hist) => boolean): TimelineItem[] {
  return (historique ?? [])
    .filter((h) => !filtre || filtre(h))
    .map((h) => ({
      titre: ACTION_LABELS[h.action] ?? h.action,
      date: dateHeureFr(h.created_at),
      auteur: h.user_nom,
      avant: h.from_statut && h.from_statut !== h.to_statut ? statutLabel(h.from_statut) : null,
      apres: h.from_statut && h.from_statut !== h.to_statut ? statutLabel(h.to_statut) : null,
      detail: h.commentaire,
    }));
}

/** Mini-page échéance : jalons J-30 → J+1, paiements rattachés, documents du contrat, historique, actions. */
@Component({
  selector: 'bea-ct-echeance-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, DetailDrawerComponent, DetailTimelineComponent, JalonsComponent, ContratsDocumentsComponent],
  template: `
    <bea-detail-drawer
      kicker="Échéance"
      [titre]="e() ? type(e()!.type_echeance) + ' du ' + date(e()!.date_prevue) : null"
      [sousTitre]="e() ? e()!.reference + ' · ' + e()!.titre + (e()!.fournisseur ? ' · ' + e()!.fournisseur : '') : null"
      [chargement]="chargement()"
      [erreur]="erreur()"
      [kpis]="kpis()"
      [onglets]="[{ key: 'detail', label: 'Détail' }, { key: 'paiements', label: 'Paiements', count: paiementsLies().length }, { key: 'documents', label: 'Documents' }, { key: 'historique', label: 'Historique' }]"
      [(onglet)]="onglet"
      [dessus]="dessus()"
      (fermer)="fermer.emit()"
      (reessayer)="charger()"
    >
      @if (e(); as e) {
        <span drawerBadges class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statutEch(e) }}</span>
      }
      @if (e(); as e) {
        <ng-container drawerActions>
          @if (peutRegler()) { <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="payer.emit(e)"><mat-icon>price_check</mat-icon> Marquer payée</button> }
          @if (modifiable() && ouverte()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirReport()"><mat-icon>event_repeat</mat-icon> Reporter</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-mg__btn--danger" [disabled]="busy()" (click)="annuler()"><mat-icon>event_busy</mat-icon> Annuler</button>
          }
          @if (modifiable() && e.statut === 'ANNULEE') { <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="retablir()"><mat-icon>restore</mat-icon> Rétablir</button> }
          @if (modifiable() && !paiementsLies().length) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-mg__btn--danger" [disabled]="busy()" (click)="supprimer()"><mat-icon>delete</mat-icon> Supprimer</button> }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirContrat.emit(e.contrat_id)"><mat-icon>description</mat-icon> Contrat</button>
        </ng-container>
      }
      @if (e(); as e) {
        @switch (onglet()) {
          @case ('detail') {
            <bea-jalons [jours]="e.jours" [termine]="e.statut === 'PAYEE' || e.statut === 'FAITE' ? 'ok' : e.statut === 'ANNULEE' ? 'muted' : null" />
            <dl class="bea-fx-dl">
              <dt>Contrat</dt><dd>{{ e.reference }} — {{ e.titre }}</dd>
              <dt>Fournisseur</dt><dd>{{ e.fournisseur || '—' }}</dd>
              <dt>Agence</dt><dd>{{ e.agence || '—' }}</dd>
              <dt>Type</dt><dd>{{ type(e.type_echeance) }}</dd>
              <dt>Date prévue</dt><dd>{{ date(e.date_prevue) }} <small [class.bea-ct-neg]="e.jours < 0 && ouverte()">{{ jours(e.jours) }}</small></dd>
              @if (e.date_reelle) { <dt>Date réelle</dt><dd>{{ date(e.date_reelle) }}</dd> }
              <dt>Responsable</dt><dd>{{ e.responsable || '—' }}</dd>
              @if (e.commentaire) { <dt>Commentaire</dt><dd class="bea-fx-dl__wrap">{{ e.commentaire }}</dd> }
            </dl>
          }
          @case ('paiements') {
            @if (paiementsLies().length) {
              <table class="bea-mg__table bea-ct-table bea-fx-mini">
                <thead><tr><th>N° pièce</th><th>Payé le</th><th class="is-num">Montant</th><th>Mode</th><th>Statut</th></tr></thead>
                <tbody>
                  @for (p of paiementsLies(); track p.id) {
                    <tr><td>{{ p.paiement_ref || '—' }}</td><td>{{ date(p.date_reelle) }}</td><td class="is-num">{{ m(p.montant_paye) }}</td><td>{{ p.mode || '—' }}</td><td><span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statut(p.statut) }}</span></td></tr>
                  }
                </tbody>
              </table>
            } @else {
              <div class="bea-ct-empty"><mat-icon>payments</mat-icon><p>Aucun paiement rattaché à cette échéance.</p></div>
            }
          }
          @case ('documents') {
            <bea-contrats-documents [contratId]="e.contrat_id" [reference]="e.reference" [lectureSeule]="!config()?.capacites?.ged_write || !modifiable()"
              [typesDocument]="config()?.types_document ?? []" [tailleMaxMo]="config()?.ged_taille_max_mo ?? 15" typeInitial="PREUVE_PAIEMENT" />
          }
          @case ('historique') {
            <bea-detail-timeline [items]="historique()" vide="Aucune opération sur les échéances de ce contrat." />
          }
        }
      }
    </bea-detail-drawer>

    @if (reportOuvert()) {
      <div class="bea-mg__backdrop bea-fx-over" (click)="reportOuvert.set(false)"></div>
      <form class="bea-mg__modal bea-ct-modal bea-fx-over" role="dialog" aria-modal="true" aria-labelledby="bea-ct-report-title" [formGroup]="reportForm" (ngSubmit)="reporter()">
        <header class="bea-ct-modal__head">
          <h2 id="bea-ct-report-title"><mat-icon>event_repeat</mat-icon> Reporter l’échéance</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="reportOuvert.set(false)"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-ct-grid bea-ct-modal__body">
          <label>Date actuelle <input [value]="date(e()?.date_prevue)" disabled /></label>
          <label>Nouvelle date * <input type="date" formControlName="date" /></label>
          <label class="bea-ct-span2">Motif * <input formControlName="motif" maxlength="300" placeholder="Accord fournisseur, retard de facturation…" /></label>
        </div>
        <footer class="bea-ct-modal__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reportOuvert.set(false)">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="reportForm.invalid || busy()"><mat-icon>save</mat-icon> Reporter</button>
        </footer>
      </form>
    }
  `,
})
export class EcheanceDrawerComponent {
  private readonly api = inject(ApiService);
  private readonly actions = inject(ContratsActionsService);
  private readonly fb = inject(FormBuilder);

  readonly contratId = input.required<string>();
  readonly echeanceId = input.required<string>();
  readonly config = input<ContratsConfig | null>(null);
  readonly dessus = input(false);
  readonly ongletInitial = input('detail');
  /** « reporter » : ouvre directement la saisie du report après chargement. */
  readonly actionInitiale = input<'reporter' | null>(null);
  /** Incrémenté par le parent après un paiement pour recharger. */
  readonly version = input(0);
  readonly fermer = output<void>();
  readonly payer = output<EcheanceRow>();
  readonly modifie = output<void>();
  readonly ouvrirContrat = output<string>();

  readonly onglet = signal('detail');
  readonly e = signal<EcheanceRow | null>(null);
  readonly contrat = signal<Contrat | null>(null);
  readonly paiements = signal<PaiementRow[]>([]);
  readonly chargement = signal(true);
  readonly erreur = signal<string | null>(null);
  readonly busy = signal(false);
  readonly reportOuvert = signal(false);
  readonly reportForm = this.fb.nonNullable.group({ date: ['', Validators.required], motif: ['', [Validators.required, Validators.maxLength(300)]] });

  readonly paiementsLies = computed(() => this.paiements().filter((p) => p.echeance_id === this.echeanceId()));
  readonly modifiable = computed(() => !!this.config()?.capacites.manage && !!this.contrat() && !VERROUILLES.has(this.contrat()!.statut));
  readonly ouverte = computed(() => ['A_VENIR', 'DUE', 'EN_RETARD'].includes(this.e()?.statut ?? ''));
  readonly peutRegler = computed(() => {
    const e = this.e();
    return !!e && this.modifiable() && e.type_echeance === 'PAIEMENT' && e.reste > 0 && REGLEABLES.has(e.contrat_statut);
  });
  readonly historique = computed(() => timeline(this.contrat()?.historique, (h) => h.action.startsWith('echeance') || h.action.startsWith('paiement')));
  readonly kpis = computed<DrawerKpi[]>(() => {
    const e = this.e();
    if (!e) return [];
    return [
      { label: 'Montant', value: montant(e.montant), hint: e.devise },
      { label: 'Payé', value: montant(e.montant_paye), hint: e.devise },
      { label: 'Reste', value: montant(e.reste), hint: e.devise, tone: e.reste > 0 ? (e.statut === 'EN_RETARD' ? 'danger' : 'warn') : 'ok' },
      { label: 'Jours restants', value: this.ouverte() ? String(e.jours) : '—', hint: this.ouverte() ? joursLabel(e.jours) : statutLabel(e.statut), tone: this.ouverte() && e.jours < 0 ? 'danger' : null },
    ];
  });

  private actionFaite = false;

  constructor() {
    effect(() => {
      const ong = this.ongletInitial();
      this.echeanceId();
      untracked(() => {
        this.onglet.set(ong);
        this.actionFaite = false;
      });
    });
    effect(() => {
      this.contratId();
      this.echeanceId();
      this.version();
      untracked(() => this.charger());
    });
  }

  charger(): void {
    this.chargement.set(!this.e());
    this.erreur.set(null);
    const id = this.contratId();
    forkJoin({
      ech: this.api.get<EcheanceRow[]>('/mg/contrats/echeances', { contrat_id: id }),
      contrat: this.api.get<Contrat>(`/mg/contrats/${id}`),
      paiements: this.api.get<PaiementRow[]>('/mg/contrats/paiements', { contrat_id: id }),
    }).subscribe({
      next: (r) => {
        const e = r.ech.find((x) => x.id === this.echeanceId()) ?? null;
        this.e.set(e);
        this.contrat.set(r.contrat);
        this.paiements.set(r.paiements);
        this.chargement.set(false);
        if (!e) this.erreur.set('Échéance introuvable (supprimée entre-temps ?).');
        if (e && !this.actionFaite && this.actionInitiale() === 'reporter' && this.modifiable() && this.ouverte()) this.ouvrirReport();
        this.actionFaite = true;
      },
      error: (err) => {
        this.chargement.set(false);
        this.erreur.set(messageErreur(err));
      },
    });
  }

  private apres(): void {
    this.modifie.emit();
    this.charger();
  }

  ouvrirReport(): void {
    const e = this.e();
    if (!e) return;
    this.reportForm.reset({ date: e.date_prevue, motif: '' });
    this.reportOuvert.set(true);
  }

  reporter(): void {
    const e = this.e();
    if (!e || this.reportForm.invalid) return;
    const { date, motif } = this.reportForm.getRawValue();
    this.actions.reporterEcheance(e, date, motif.trim(), this.busy).subscribe(() => {
      this.reportOuvert.set(false);
      this.apres();
    });
  }

  annuler(): void {
    const e = this.e();
    if (e) this.actions.annulerEcheance(e, this.busy).subscribe(() => this.apres());
  }

  retablir(): void {
    const e = this.e();
    if (e) this.actions.retablirEcheance(e, this.busy).subscribe(() => this.apres());
  }

  supprimer(): void {
    const e = this.e();
    if (!e) return;
    this.actions.supprimerEcheance(e, this.busy).subscribe(() => {
      this.modifie.emit();
      this.fermer.emit();
    });
  }

  statutEch(e: EcheanceRow): string {
    return echeanceStatutLabel(e.statut, e.commentaire);
  }
  statut(c: string): string {
    return statutLabel(c);
  }
  type(c: string): string {
    return typeEcheanceLabel(c);
  }
  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }
  jours(n: number): string {
    return joursLabel(n);
  }
  m(v: number | null): string {
    return montant(v);
  }
}

/** Mini-page paiement : récapitulatif prévu / versé / reste, échéance, justificatifs (GED), historique. */
@Component({
  selector: 'bea-ct-paiement-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, DetailDrawerComponent, DetailTimelineComponent, ContratsDocumentsComponent],
  template: `
    <bea-detail-drawer
      kicker="Paiement"
      [titre]="p() ? (p()!.paiement_ref || 'Paiement sans n° de pièce') : null"
      [sousTitre]="p() ? p()!.reference + ' · ' + p()!.titre + (p()!.fournisseur ? ' · ' + p()!.fournisseur : '') : null"
      [chargement]="chargement()"
      [erreur]="erreur()"
      [kpis]="kpis()"
      [onglets]="[{ key: 'detail', label: 'Détail' }, { key: 'documents', label: 'Justificatifs' }, { key: 'historique', label: 'Historique' }]"
      [(onglet)]="onglet"
      [dessus]="dessus()"
      (fermer)="fermer.emit()"
      (reessayer)="charger()"
    >
      @if (p(); as p) {
        <span drawerBadges class="bea-ct-badge" [attr.data-tone]="p.statut">{{ statut(p.statut) }}</span>
      }
      @if (p(); as p) {
        <ng-container drawerActions>
          @if (modifiable()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="editer.emit(p)"><mat-icon>edit</mat-icon> Modifier</button>
          }
          @if (config()?.capacites?.ged_write && !verrouille()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="onglet.set('documents')"><mat-icon>attach_file</mat-icon> Ajouter un justificatif</button>
          }
          @if (modifiable()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-mg__btn--danger" [disabled]="busy()" (click)="supprimer()"><mat-icon>delete</mat-icon> Supprimer</button>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirContrat.emit(p.contrat_id)"><mat-icon>description</mat-icon> Contrat</button>
        </ng-container>
      }
      @if (p(); as p) {
        @switch (onglet()) {
          @case ('detail') {
            <dl class="bea-fx-dl">
              <dt>Contrat</dt><dd>{{ p.reference }} — {{ p.titre }}</dd>
              <dt>Fournisseur</dt><dd>{{ p.fournisseur || '—' }}</dd>
              <dt>Agence</dt><dd>{{ p.agence || '—' }}</dd>
              <dt>Échéance réglée</dt><dd>{{ p.echeance_date ? date(p.echeance_date) : 'Hors échéancier' }}</dd>
              <dt>Date prévue</dt><dd>{{ date(p.date_prevue) }}</dd>
              <dt>Date de paiement</dt><dd>{{ date(p.date_reelle) }}</dd>
              <dt>Mode</dt><dd>{{ p.mode || '—' }}</dd>
              <dt>N° de pièce</dt><dd>{{ p.paiement_ref || '—' }}</dd>
              @if (p.commentaire) { <dt>Commentaire</dt><dd class="bea-fx-dl__wrap">{{ p.commentaire }}</dd> }
            </dl>
          }
          @case ('documents') {
            <p class="bea-ct-help"><mat-icon>info</mat-icon> Les justificatifs sont classés dans la GED du contrat (typologie « Preuve de paiement »).</p>
            <bea-contrats-documents [contratId]="p.contrat_id" [reference]="p.reference" [lectureSeule]="!config()?.capacites?.ged_write || verrouille()"
              [typesDocument]="config()?.types_document ?? []" [tailleMaxMo]="config()?.ged_taille_max_mo ?? 15" typeInitial="PREUVE_PAIEMENT" />
          }
          @case ('historique') {
            <bea-detail-timeline [items]="historique()" vide="Aucune opération de paiement tracée sur ce contrat." />
          }
        }
      }
    </bea-detail-drawer>
  `,
})
export class PaiementDrawerComponent {
  private readonly api = inject(ApiService);
  private readonly actions = inject(ContratsActionsService);

  readonly contratId = input.required<string>();
  readonly paiementId = input.required<string>();
  readonly config = input<ContratsConfig | null>(null);
  readonly dessus = input(false);
  readonly ongletInitial = input('detail');
  readonly version = input(0);
  readonly fermer = output<void>();
  readonly editer = output<PaiementRow>();
  readonly modifie = output<void>();
  readonly ouvrirContrat = output<string>();

  readonly onglet = signal('detail');
  readonly p = signal<PaiementRow | null>(null);
  readonly contrat = signal<Contrat | null>(null);
  readonly chargement = signal(true);
  readonly erreur = signal<string | null>(null);
  readonly busy = signal(false);

  readonly verrouille = computed(() => !this.contrat() || VERROUILLES.has(this.contrat()!.statut));
  readonly modifiable = computed(() => !!this.config()?.capacites.manage && !!this.p() && REGLEABLES.has(this.p()!.contrat_statut));
  readonly historique = computed(() => timeline(this.contrat()?.historique, (h) => h.action.startsWith('paiement')));
  readonly kpis = computed<DrawerKpi[]>(() => {
    const p = this.p();
    if (!p) return [];
    return [
      { label: 'Prévu', value: montant(p.montant_prevu), hint: p.devise },
      { label: 'Versé', value: montant(p.montant_paye), hint: p.devise, tone: 'ok' },
      { label: 'Reste', value: montant(p.reste), hint: p.devise, tone: p.reste > 0 ? 'warn' : null },
      { label: 'Écart', value: montant(p.ecart), hint: 'versé − prévu', tone: p.ecart < 0 ? 'danger' : null },
    ];
  });

  constructor() {
    effect(() => {
      const ong = this.ongletInitial();
      this.paiementId();
      untracked(() => this.onglet.set(ong));
    });
    effect(() => {
      this.contratId();
      this.paiementId();
      this.version();
      untracked(() => this.charger());
    });
  }

  charger(): void {
    this.chargement.set(!this.p());
    this.erreur.set(null);
    const id = this.contratId();
    forkJoin({
      paiements: this.api.get<PaiementRow[]>('/mg/contrats/paiements', { contrat_id: id }),
      contrat: this.api.get<Contrat>(`/mg/contrats/${id}`),
    }).subscribe({
      next: (r) => {
        const p = r.paiements.find((x) => x.id === this.paiementId()) ?? null;
        this.p.set(p);
        this.contrat.set(r.contrat);
        this.chargement.set(false);
        if (!p) this.erreur.set('Paiement introuvable (supprimé entre-temps ?).');
      },
      error: (err) => {
        this.chargement.set(false);
        this.erreur.set(messageErreur(err));
      },
    });
  }

  supprimer(): void {
    const p = this.p();
    if (!p) return;
    this.actions.supprimerPaiement(p, this.busy).subscribe(() => {
      this.modifie.emit();
      this.fermer.emit();
    });
  }

  statut(c: string): string {
    return statutLabel(c);
  }
  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }
}