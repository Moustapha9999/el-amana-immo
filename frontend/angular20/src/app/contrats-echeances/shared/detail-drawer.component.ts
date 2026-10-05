import { ChangeDetectionStrategy, Component, HostListener, computed, input, model, output } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

export interface DrawerKpi {
  label: string;
  value: string;
  hint?: string | null;
  tone?: 'ok' | 'warn' | 'danger' | null;
}

export interface DrawerTab {
  key: string;
  label: string;
  count?: number | null;
}

/**
 * Mini-page de détail (panneau latéral) commune aux contrats, échéances, paiements,
 * renouvellements et factures : en-tête, KPI, actions, onglets, corps, squelette, erreur + réessayer.
 * Contenu projeté : [drawerBadges], [drawerActions], corps par défaut.
 */
@Component({
  selector: 'bea-detail-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <div class="bea-fx-drawer__backdrop" [class.bea-fx-over]="dessus()" (click)="fermer.emit()"></div>
    <aside class="bea-fx-drawer" [class.bea-fx-drawer--lg]="large()" [class.bea-fx-over]="dessus()" role="dialog" aria-modal="true" [attr.aria-label]="titre() || kicker()">
      <header class="bea-fx-drawer__head">
        <div>
          <p class="bea-ct-view__kicker">
            @if (kicker()) { <span class="bea-ct-badge" data-tone="info">{{ kicker() }}</span> }
            <ng-content select="[drawerBadges]" />
          </p>
          @if (titre()) { <h2>{{ titre() }}</h2> } @else { <span class="bea-fx-skel bea-fx-skel--title"></span> }
          @if (sousTitre()) { <p class="bea-ct-view__sub">{{ sousTitre() }}</p> }
        </div>
        <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer.emit()"><mat-icon>close</mat-icon></button>
      </header>

      @if (erreur()) {
        <div class="bea-dd__error" role="alert">
          <p><strong>Chargement impossible.</strong> {{ erreur() }}</p>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reessayer.emit()"><mat-icon>refresh</mat-icon> Réessayer</button>
        </div>
      } @else if (chargement()) {
        <div class="bea-fx-drawer__skeleton">
          <div class="bea-fx-kpis">@for (i of [1, 2, 3, 4]; track i) { <span class="bea-fx-skel bea-fx-skel--box"></span> }</div>
          @for (i of [1, 2, 3, 4, 5, 6]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
        </div>
      } @else {
        @if (kpis().length) {
          <div class="bea-fx-drawer__kpis">
            @for (k of kpis(); track k.label) {
              <div [attr.data-tone]="k.tone || null"><span>{{ k.label }}</span><strong>{{ k.value }}</strong>@if (k.hint) { <small>{{ k.hint }}</small> }</div>
            }
          </div>
        }
        <div class="bea-fx-drawer__actions"><ng-content select="[drawerActions]" /></div>
        @if (onglets().length > 1) {
          <nav class="bea-ct-tabs bea-fx-drawer__tabs" role="tablist">
            @for (t of onglets(); track t.key) {
              <button type="button" role="tab" [attr.aria-selected]="onglet() === t.key" [class.is-on]="onglet() === t.key" (click)="onglet.set(t.key)">
                {{ t.label }}@if (t.count !== undefined && t.count !== null) { ({{ t.count }}) }
              </button>
            }
          </nav>
        }
        <div class="bea-fx-drawer__body"><ng-content /></div>
      }
    </aside>
  `,
})
export class DetailDrawerComponent {
  readonly titre = input<string | null>(null);
  readonly kicker = input<string | null>(null);
  readonly sousTitre = input<string | null>(null);
  readonly chargement = input(false);
  readonly erreur = input<string | null>(null);
  readonly kpis = input<DrawerKpi[]>([]);
  readonly onglets = input<DrawerTab[]>([]);
  readonly large = input(false);
  /** Au-dessus d'un autre panneau (ex. paiement ouvert depuis une fiche). */
  readonly dessus = input(false);
  readonly onglet = model<string>('');
  readonly fermer = output<void>();
  readonly reessayer = output<void>();

  @HostListener('document:keydown.escape')
  echap(): void {
    if (document.querySelector('.bea-mg__modal, .cdk-overlay-container .cdk-overlay-pane')) return;
    if (!this.dessus() && document.querySelector('.bea-fx-drawer.bea-fx-over')) return;
    this.fermer.emit();
  }
}

export interface TimelineItem {
  titre: string;
  date: string;
  auteur?: string | null;
  detail?: string | null;
  avant?: string | null;
  apres?: string | null;
}

/** Historique en frise : action, auteur, date, ancienne → nouvelle valeur. */
@Component({
  selector: 'bea-detail-timeline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (items().length) {
      <ol class="bea-fx-timeline">
        @for (h of items(); track $index) {
          <li>
            <span class="bea-fx-timeline__dot"></span>
            <div>
              <strong>{{ h.titre }}</strong>
              <small>{{ h.date }}@if (h.auteur) { · {{ h.auteur }} }</small>
              @if (h.avant || h.apres) {
                <span class="bea-fx-timeline__diff">@if (h.avant) { <del>{{ h.avant }}</del> → } <ins>{{ h.apres || '—' }}</ins></span>
              }
              @if (h.detail) { <span>{{ h.detail }}</span> }
            </div>
          </li>
        }
      </ol>
    } @else {
      <div class="bea-ct-empty"><mat-icon>history</mat-icon><p>{{ vide() }}</p></div>
    }
  `,
})
export class DetailTimelineComponent {
  readonly items = input<TimelineItem[]>([]);
  readonly vide = input('Aucun événement enregistré.');
}

const JALONS = [
  { j: 30, label: 'J-30' },
  { j: 15, label: 'J-15' },
  { j: 7, label: 'J-7' },
  { j: 1, label: 'J-1' },
  { j: 0, label: 'J0' },
  { j: -1, label: 'J+1' },
];

/** Indicateur d'approche d'une échéance : J-30 → J+1, dynamique selon les jours restants. */
@Component({
  selector: 'bea-jalons',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ol class="bea-jalons" [attr.data-tone]="tone()" [attr.aria-label]="resume()">
      @for (m of jalons; track m.j; let i = $index) {
        <li [class.is-passe]="etat(i) === 'passe'" [class.is-courant]="etat(i) === 'courant'">{{ m.label }}</li>
      }
    </ol>
  `,
})
export class JalonsComponent {
  readonly jours = input<number | null>(null);
  /** Échéance soldée ou annulée : frise neutre (ok / muted). */
  readonly termine = input<'ok' | 'muted' | null>(null);
  readonly jalons = JALONS;

  private readonly courant = computed(() => {
    const j = this.jours();
    if (j === null || this.termine()) return -1;
    let idx = -1;
    JALONS.forEach((m, i) => {
      if (j <= m.j) idx = i;
    });
    return idx;
  });

  readonly tone = computed(() => this.termine() ?? ((this.jours() ?? 99) < 0 ? 'danger' : null));

  readonly resume = computed(() => {
    const j = this.jours();
    if (this.termine() === 'ok') return 'Échéance soldée';
    if (j === null) return 'Sans date';
    return j === 0 ? 'Échéance aujourd’hui' : j > 0 ? `J-${j}` : `Dépassée de ${-j} jour(s)`;
  });

  etat(i: number): 'passe' | 'courant' | null {
    const c = this.courant();
    return i === c ? 'courant' : i < c ? 'passe' : null;
  }
}
