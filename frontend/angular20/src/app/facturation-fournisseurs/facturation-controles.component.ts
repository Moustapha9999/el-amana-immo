import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { FX_BASE, FxControleRow, FxControles, FxLotResultat, nettoyer } from './facturation.models';
import { FacturationStore } from './facturation.store';
import { FactureActionInitiale, FactureDrawerComponent } from './facture-drawer.component';

type Onglet = 'tous' | 'ok' | 'attention' | 'bloquant';

const ONGLETS: { code: Onglet; label: string; icon: string; tone: string }[] = [
  { code: 'tous', label: 'À valider', icon: 'pending_actions', tone: 'INFO' },
  { code: 'ok', label: 'Prêtes', icon: 'task_alt', tone: 'OK' },
  { code: 'attention', label: 'À vérifier', icon: 'warning', tone: 'WARN' },
  { code: 'bloquant', label: 'Incomplètes', icon: 'block', tone: 'DANGER' },
];

/** Factures reçues en attente de validation : contrôles automatiques indicatifs, validation en lot. */
@Component({
  selector: 'bea-fx-controles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, MontantPipe, FactureDrawerComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux · Facturation fournisseurs</p>
          <h1>À valider</h1>
          <p class="bea-ct-head__sub">Factures saisies en attente de validation. Circuit : saisie → facture scannée → validation → paiement. Les factures incomplètes (pièce ou champ obligatoire manquant) ne peuvent pas être validées.</p>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="chargement()" (click)="charger()"><mat-icon>refresh</mat-icon> Actualiser</button>
        </div>
      </header>

      <div class="bea-fx-tabs" role="tablist">
        @for (o of onglets; track o.code) {
          <button type="button" role="tab" class="bea-fx-tab" [class.is-active]="onglet() === o.code" [attr.aria-selected]="onglet() === o.code" (click)="choisirOnglet(o.code)">
            <mat-icon>{{ o.icon }}</mat-icon> {{ o.label }} <span class="bea-ct-badge" [attr.data-tone]="o.tone">{{ compte(o.code) }}</span>
          </button>
        }
      </div>

      <div class="bea-mg__search bea-ct-filters bea-fx-filters">
        <label class="bea-mg__field bea-fx-grow">Rechercher <input type="search" [value]="q()" (input)="q.set($any($event.target).value)" placeholder="Référence, fournisseur, point…" /></label>
        <label class="bea-mg__field">Profil
          <select [value]="profilId()" (change)="profilId.set($any($event.target).value); charger()">
            <option value="">Tous</option>
            @for (p of store.ref()?.profils ?? []; track p.id) { <option [value]="p.id" [selected]="p.id === profilId()">{{ p.libelle }}</option> }
          </select>
        </label>
        @if (!store.config()?.agence_scope) {
          <label class="bea-mg__field">Agence
            <select [value]="agenceId()" (change)="agenceId.set($any($event.target).value); charger()">
              <option value="">Toutes</option>
              @for (a of store.ref()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
            </select>
          </label>
        }
      </div>

      <div class="bea-mg__panel bea-ct-panel">
        @if (selection().size) {
          <div class="bea-fx-bulk">
            <span><strong>{{ selection().size }}</strong> sélectionnée(s)</span>
            @if (store.cap().validate && validables().length) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="valider(validables())"><mat-icon>verified</mat-icon> Valider ({{ validables().length }})</button>
            }
            @if (selection().size > validables().length) {
              <small class="bea-fx-sub">{{ selection().size - validables().length }} incomplète(s) ignorée(s)</small>
            }
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="toutSelectionner(false)">Désélectionner</button>
          </div>
        }
        @if (chargement() && !data()) {
          @for (i of [1, 2, 3, 4, 5]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
        } @else {
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-fx-ctrl-table">
              <thead>
                <tr>
                  <th class="bea-fx-col-check"><input type="checkbox" aria-label="Tout sélectionner" [checked]="toutSelectionne()" (change)="toutSelectionner($any($event.target).checked)" /></th>
                  <th>Facture</th><th>Fournisseur</th><th>Point / agence</th><th class="is-num">Montant TTC</th><th>Pièce</th><th>Vérifications</th><th></th>
                </tr>
              </thead>
              <tbody>
                @for (r of visibles(); track r.id; let i = $index) {
                  <tr class="bea-fx-row-in" [style.--i]="i" [class.is-selected]="selection().has(r.id)">
                    <td class="bea-fx-col-check"><input type="checkbox" [attr.aria-label]="'Sélectionner ' + r.reference" [checked]="selection().has(r.id)" (change)="basculer(r.id)" /></td>
                    <td><button type="button" class="bea-ct-link" (click)="ouvrir(r.id)"><strong>{{ r.reference }}</strong></button><small class="bea-fx-sub">{{ r.numero_fournisseur || 'Sans n°' }} · {{ r.periode_label || '—' }}</small></td>
                    <td>{{ r.profil || r.fournisseur || '—' }}</td>
                    <td>{{ r.point_nom || '—' }}<small class="bea-fx-sub">{{ r.agence || '' }}</small></td>
                    <td class="is-num">{{ r.montant_ttc | montant }}</td>
                    <td>
                      @if (r.nb_documents) {
                        <span class="bea-fx-verdict" data-niveau="ok"><mat-icon>attach_file</mat-icon> {{ r.nb_documents }}</span>
                      } @else {
                        <span class="bea-fx-verdict" [attr.data-niveau]="pieceBloquante(r) ? 'bloquant' : 'attention'"><mat-icon>attach_file</mat-icon> Aucune</span>
                      }
                    </td>
                    <td>
                      <span class="bea-fx-verdict" [attr.data-niveau]="r.niveau_controle">
                        <mat-icon>{{ r.niveau_controle === 'bloquant' ? 'block' : r.niveau_controle === 'attention' ? 'warning' : 'task_alt' }}</mat-icon>
                        {{ r.niveau_controle === 'bloquant' ? 'Incomplète' : r.niveau_controle === 'attention' ? r.nb_attention + ' point(s) à vérifier' : 'Prête' }}
                      </span>
                      @if (r.controles.length) {
                        <ul class="bea-fx-ctrl-list">@for (c of r.controles; track c.code) { <li [attr.data-niveau]="c.niveau">{{ c.message }}</li> }</ul>
                      }
                    </td>
                    <td class="bea-fx-ctrl-actions">
                      @if (!r.nb_documents && store.cap().documents_create) {
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrir(r.id, 'documents')"><mat-icon>upload_file</mat-icon> Joindre le scan</button>
                      }
                      @if (r.niveau_controle !== 'bloquant' && store.cap().validate) {
                        <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="valider([r])"><mat-icon>verified</mat-icon> Valider</button>
                      }
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="8"><div class="bea-ct-empty"><mat-icon>verified</mat-icon><p>{{ onglet() === 'tous' ? 'Aucune facture en attente de validation.' : 'Aucune facture dans cette catégorie.' }}</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
        }
      </div>
      <p class="bea-ct-help"><mat-icon>info</mat-icon> Les vérifications « à vérifier » (TVA, échéance…) n’empêchent pas la validation. <a class="bea-ct-link" [routerLink]="base + '/parametres'">Pièce obligatoire : Paramètres</a></p>
    </section>

    @if (factureId(); as id) {
      <bea-fx-facture-drawer [factureId]="id" [actionInitiale]="actionInitiale()" (closed)="factureId.set(null)" (changed)="charger()" />
    }
  `,
})
export class FacturationControlesComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(UiDialogService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  readonly base = FX_BASE;
  readonly onglets = ONGLETS;
  readonly data = signal<FxControles | null>(null);
  readonly chargement = signal(false);
  readonly busy = signal(false);
  readonly onglet = signal<Onglet>('tous');
  readonly q = signal('');
  readonly profilId = signal('');
  readonly agenceId = signal('');
  readonly fournisseurId = signal('');
  readonly selection = signal<Set<string>>(new Set());
  readonly factureId = signal<string | null>(null);
  readonly actionInitiale = signal<FactureActionInitiale | null>(null);
  private readonly drawer = viewChild(FactureDrawerComponent);
  readonly hasUnsavedChanges = () => !!this.drawer()?.dirty();

  readonly visibles = computed(() => {
    const o = this.onglet();
    const q = this.q().trim().toLowerCase();
    return (this.data()?.items ?? []).filter(
      (r) =>
        (o === 'tous' || r.niveau_controle === o) &&
        (!q || [r.reference, r.numero_fournisseur, r.profil, r.fournisseur, r.point_nom, r.agence].some((v) => v?.toLowerCase().includes(q))),
    );
  });

  private readonly selectionnees = computed(() => (this.data()?.items ?? []).filter((r) => this.selection().has(r.id)));
  readonly validables = computed(() => this.selectionnees().filter((r) => r.niveau_controle !== 'bloquant'));
  readonly toutSelectionne = computed(() => this.visibles().length > 0 && this.visibles().every((r) => this.selection().has(r.id)));

  ngOnInit(): void {
    this.store.charger();
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((m) => {
      this.profilId.set(m.get('profil_id') ?? '');
      this.fournisseurId.set(m.get('supplier_id') ?? '');
      this.charger();
    });
  }

  charger(): void {
    this.chargement.set(true);
    const params = nettoyer({ profil_id: this.profilId(), agency_id: this.agenceId(), supplier_id: this.fournisseurId() });
    this.api.get<FxControles>('/mg/factures/controles', params).subscribe({
      next: (d) => {
        this.data.set(d);
        const ids = new Set(d.items.map((r) => r.id));
        this.selection.update((s) => new Set([...s].filter((id) => ids.has(id))));
        this.chargement.set(false);
      },
      error: (e) => {
        this.chargement.set(false);
        if (!this.data()) this.data.set({ items: [], compteurs: { a_valider: 0, bloquant: 0, attention: 0, pret: 0 } });
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Factures à valider indisponibles'));
      },
    });
  }

  compte(o: Onglet): number {
    const c = this.data()?.compteurs;
    if (!c) return 0;
    return { tous: c.a_valider, bloquant: c.bloquant, attention: c.attention, ok: c.pret }[o];
  }

  pieceBloquante(r: FxControleRow): boolean {
    return r.controles.some((c) => c.code === 'document_absent' && c.niveau === 'bloquant');
  }

  ouvrir(id: string, action: FactureActionInitiale | null = null): void {
    this.actionInitiale.set(action);
    this.factureId.set(id);
  }

  choisirOnglet(o: Onglet): void {
    this.onglet.set(o);
    this.selection.set(new Set());
  }

  basculer(id: string): void {
    this.selection.update((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  toutSelectionner(on: boolean): void {
    this.selection.set(on ? new Set(this.visibles().map((r) => r.id)) : new Set());
  }

  valider(cibles: FxControleRow[]): void {
    if (!cibles.length) return;
    const une = cibles.length === 1;
    this.dialog
      .confirm({
        title: une ? `Valider ${cibles[0].reference} ?` : `Valider ${cibles.length} factures ?`,
        message: une ? 'La facture devient payable ; les montants sont figés.' : 'Les factures validées deviennent payables ; les montants sont figés.',
        confirmLabel: 'Valider',
        tone: 'primary',
        icon: 'verified',
      })
      .subscribe((ok) => {
        if (!ok) return;
        this.feedback
          .run(() => this.api.post<FxLotResultat>('/mg/factures/controles/lot', { ids: cibles.map((r) => r.id), action: 'valider' }), {
            loading: 'Validation en cours…',
            busy: this.busy,
            retry: false,
            errorTitle: 'Validation impossible',
            success: (r) => ({
              title: r.echecs ? 'Validation partielle' : une ? 'Facture validée' : 'Factures validées',
              message: r.succes ? 'Prêtes pour le paiement.' : undefined,
              details: [
                { label: 'Validées', value: String(r.succes) },
                ...(r.echecs ? [{ label: 'Refusées', value: String(r.echecs) }] : []),
                ...r.resultats.filter((x) => !x.ok).slice(0, 5).map((x) => ({
                  label: cibles.find((c) => c.id === x.id)?.reference ?? 'Facture',
                  value: x.message ?? 'Refusée',
                })),
              ],
            }),
          })
          .subscribe(() => {
            this.selection.set(new Set());
            this.charger();
          });
      });
  }
}
