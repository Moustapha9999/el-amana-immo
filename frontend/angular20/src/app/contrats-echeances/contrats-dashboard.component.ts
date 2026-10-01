import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { ALERTE_TYPE_LABELS, Alerte, ContratsConfig, EcheanceRow, dateFr, joursLabel, statutLabel, typeEcheanceLabel } from './contrats.models';

interface Dashboard {
  total: number;
  actifs: number;
  brouillons: number;
  en_validation: number;
  rejetes: number;
  suspendus: number;
  expires: number;
  date_depassee: number;
  echeance_30: number;
  archives: number;
  annules: number;
  montant_actifs: number;
  paiements_a_venir: number;
  paiements_en_retard: number;
  paye_annee: number;
  alertes: number;
  alertes_critiques: number;
  prochaines_echeances: EcheanceRow[];
  alertes_top: Alerte[];
  par_type: { type: string; count: number; montant: number }[];
  top_fournisseurs: { fournisseur: string; montant: number }[];
}

@Component({
  selector: 'bea-contrats-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, MontantPipe],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>Contrats &amp; échéances</h1>
          <p class="bea-ct-head__sub">
            Pilotage des engagements fournisseurs : statuts, échéances, paiements et renouvellements.
            @if (config()?.agence_scope; as s) { <span class="bea-ct-badge" data-tone="INFO">Périmètre : {{ s.libelle || 'votre agence' }}</span> }
          </p>
        </div>
        <div class="bea-mg__actions">
          @if (config()?.capacites?.create) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/contrats-echeances/nouveau"><mat-icon>add</mat-icon> Nouveau contrat</a>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Actualiser" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      @if (dash(); as d) {
        @if (d.total === 0) {
          <div class="bea-mg__panel bea-ct-panel bea-ct-empty bea-ct-empty--hero">
            <mat-icon>description</mat-icon>
            <p>Aucun contrat enregistré.</p>
            @if (config()?.capacites?.create) {
              <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/contrats-echeances/nouveau">Créer le premier contrat</a>
            }
          </div>
        }

        <div class="bea-ct-dash__hero">
          <article class="bea-ct-hero">
            <mat-icon>account_balance_wallet</mat-icon>
            <div><p>Engagements actifs (TTC)</p><strong>{{ d.montant_actifs | montant }}</strong><small>{{ d.actifs }} contrat{{ d.actifs > 1 ? 's' : '' }} actif{{ d.actifs > 1 ? 's' : '' }}</small></div>
          </article>
          <a class="bea-ct-hero" routerLink="/contrats-echeances/echeances" [queryParams]="{ horizon: '90' }">
            <mat-icon>event_upcoming</mat-icon>
            <div><p>Paiements à venir</p><strong>{{ d.paiements_a_venir | montant }}</strong><small>Reste à payer sur échéances futures</small></div>
          </a>
          <a class="bea-ct-hero" data-tone="EN_RETARD" routerLink="/contrats-echeances/echeances" [queryParams]="{ statut: 'EN_RETARD' }">
            <mat-icon>running_with_errors</mat-icon>
            <div><p>Paiements en retard</p><strong>{{ d.paiements_en_retard | montant }}</strong><small>À régulariser</small></div>
          </a>
          <a class="bea-ct-hero" routerLink="/contrats-echeances/paiements" [queryParams]="{ statut: 'PAYE' }">
            <mat-icon>task_alt</mat-icon>
            <div><p>Payé depuis le 1ᵉʳ janvier</p><strong>{{ d.paye_annee | montant }}</strong><small>Règlements enregistrés</small></div>
          </a>
        </div>

        <h2 class="bea-ct-dash__title">Statuts des contrats</h2>
        <div class="bea-nf-kpi bea-ct-dash__statuts">
          @for (k of statutsKpi(); track k.label) {
            <a class="bea-nf-kpi__card" [attr.data-tone]="k.tone" routerLink="/contrats-echeances/liste" [queryParams]="k.params">
              <p>{{ k.label }}</p><strong>{{ k.value }}</strong>
            </a>
          }
          <a class="bea-nf-kpi__card" data-tone="URGENT" routerLink="/contrats-echeances/alertes">
            <p>Alertes</p><strong>{{ d.alertes }}</strong>
            @if (d.alertes_critiques) { <small>dont {{ d.alertes_critiques }} critique{{ d.alertes_critiques > 1 ? 's' : '' }} / urgente{{ d.alertes_critiques > 1 ? 's' : '' }}</small> }
          </a>
        </div>

        <div class="bea-ct-dash__grid">
          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top">
              <h2><mat-icon>schedule</mat-icon> Prochaines échéances</h2>
              <a class="bea-ct-link" routerLink="/contrats-echeances/echeances">Tout voir</a>
            </div>
            <ul class="bea-ct-dash__list">
              @for (e of d.prochaines_echeances; track e.id) {
                <li>
                  <a [routerLink]="['/contrats-echeances', e.contrat_id]">
                    <span class="bea-ct-dash__date"><strong>{{ date(e.date_prevue) }}</strong><small [class.bea-ct-neg]="e.jours < 0">{{ jours(e.jours) }}</small></span>
                    <span class="bea-ct-dash__main"><strong>{{ e.reference }}</strong> {{ e.titre }}<small>{{ typeEcheance(e.type_echeance) }}{{ e.fournisseur ? ' · ' + e.fournisseur : '' }}</small></span>
                    <span class="bea-ct-dash__amount">@if (e.reste) { {{ e.reste | montant }} <small>{{ e.devise }}</small> }</span>
                    <span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ statut(e.statut) }}</span>
                  </a>
                </li>
              } @empty {
                <li class="bea-ct-dash__none">Aucune échéance à venir.</li>
              }
            </ul>
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top">
              <h2><mat-icon>notifications_active</mat-icon> Alertes prioritaires</h2>
              <a class="bea-ct-link" routerLink="/contrats-echeances/alertes">Tout voir</a>
            </div>
            <ul class="bea-ct-dash__list">
              @for (a of d.alertes_top; track $index) {
                <li>
                  <a [routerLink]="['/contrats-echeances', a.contrat_id]">
                    <span class="bea-ct-badge" [attr.data-tone]="a.niveau">{{ statut(a.niveau) }}</span>
                    <span class="bea-ct-dash__main"><strong>{{ a.reference }}</strong> {{ a.message }}<small>{{ typeAlerte(a.type) }} · {{ a.titre }}</small></span>
                    <span class="bea-ct-dash__date"><strong>{{ date(a.echeance) }}</strong>@if (a.jours !== null) { <small [class.bea-ct-neg]="a.jours < 0">{{ jours(a.jours) }}</small> }</span>
                  </a>
                </li>
              } @empty {
                <li class="bea-ct-dash__none">Aucune alerte : tout est à jour.</li>
              }
            </ul>
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>category</mat-icon> Engagements actifs par type</h2></div>
            <ul class="bea-ct-bars">
              @for (t of d.par_type; track t.type) {
                <li>
                  <span class="bea-ct-bars__label">{{ t.type }} <small>{{ t.count }}</small></span>
                  <span class="bea-ct-bars__track"><span class="bea-ct-bars__fill" [style.width.%]="part(t.montant, maxType())"></span></span>
                  <span class="bea-ct-bars__value">{{ t.montant | montant }}</span>
                </li>
              } @empty {
                <li class="bea-ct-dash__none">Aucun contrat actif.</li>
              }
            </ul>
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>storefront</mat-icon> Principaux fournisseurs</h2></div>
            <ul class="bea-ct-bars">
              @for (f of d.top_fournisseurs; track f.fournisseur) {
                <li>
                  <span class="bea-ct-bars__label">{{ f.fournisseur }}</span>
                  <span class="bea-ct-bars__track"><span class="bea-ct-bars__fill bea-ct-bars__fill--alt" [style.width.%]="part(f.montant, maxFournisseur())"></span></span>
                  <span class="bea-ct-bars__value">{{ f.montant | montant }}</span>
                </li>
              } @empty {
                <li class="bea-ct-dash__none">Aucun fournisseur sur les contrats actifs.</li>
              }
            </ul>
          </div>
        </div>
      } @else {
        <div class="bea-ct-view__loading"><span class="bea-ct-view__spinner"></span> Chargement du tableau de bord…</div>
      }
    </section>
  `,
})
export class ContratsDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly dash = signal<Dashboard | null>(null);
  readonly config = signal<ContratsConfig | null>(null);

  readonly statutsKpi = computed(() => {
    const d = this.dash();
    if (!d) return [];
    return [
      { label: 'Actifs', value: d.actifs, tone: 'ACTIF', params: { statut: 'ACTIF' } },
      { label: 'Échéance ≤ 30 jours', value: d.echeance_30, tone: 'ECHEANCE_30', params: { etat: 'ECHEANCE_30' } },
      { label: 'Date dépassée, encore actifs', value: d.date_depassee, tone: 'DATE_DEPASSEE', params: { etat: 'DATE_DEPASSEE' } },
      { label: 'Brouillons', value: d.brouillons, tone: 'BROUILLON', params: { statut: 'BROUILLON' } },
      { label: 'En validation', value: d.en_validation, tone: 'EN_VALIDATION', params: { statut: 'EN_VALIDATION' } },
      { label: 'Rejetés', value: d.rejetes, tone: 'REJETE', params: { statut: 'REJETE' } },
      { label: 'Suspendus', value: d.suspendus, tone: 'SUSPENDU', params: { statut: 'SUSPENDU' } },
      { label: 'Expirés', value: d.expires, tone: 'EXPIRE', params: { statut: 'EXPIRE' } },
      { label: 'Annulés', value: d.annules, tone: 'ANNULE', params: { statut: 'ANNULE' } },
    ];
  });
  readonly maxType = computed(() => Math.max(0, ...(this.dash()?.par_type ?? []).map((t) => t.montant)));
  readonly maxFournisseur = computed(() => Math.max(0, ...(this.dash()?.top_fournisseurs ?? []).map((f) => f.montant)));

  ngOnInit(): void {
    this.api.get<ContratsConfig>('/mg/contrats/config').subscribe({ next: (c) => this.config.set(c), error: () => undefined });
    this.charger();
  }

  charger(): void {
    this.api.get<Dashboard>('/mg/contrats/dashboard').subscribe({
      next: (d) => this.dash.set(d),
      error: (e) => void describeApiErrorAsync(e).then((info) => this.feedback.apiError(info, 'Tableau de bord indisponible')),
    });
  }

  part(v: number, max: number): number {
    return max > 0 ? Math.max(4, Math.round((v / max) * 100)) : 0;
  }

  statut(code: string): string {
    return statutLabel(code);
  }

  typeAlerte(code: string): string {
    return ALERTE_TYPE_LABELS[code] ?? code;
  }

  typeEcheance(code: string): string {
    return typeEcheanceLabel(code);
  }

  date(iso: string | null): string {
    return dateFr(iso);
  }

  jours(n: number | null): string {
    return joursLabel(n);
  }
}
