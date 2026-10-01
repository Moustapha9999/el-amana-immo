import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  OnDestroy,
  OnInit,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { Router } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { FeedbackService } from '../core/feedback/feedback.service';
import { MontantPipe, QuantitePipe } from '../shared/montant.pipe';
import {
  PIECES_ACCEPT,
  PIECES_FORMATS_LABEL,
  PieceNature,
  detacherReason,
  iconePiece,
  naturePiece,
  verifierPieceJointe,
} from '../shared/pieces-jointes';

interface BcLigne {
  id: string;
  description: string;
  quantite: number;
  quantite_recue: number;
  prix_unitaire: number;
  prix_total: number;
  total_ttc: number;
  taux_tva?: number;
  uom: string;
}

export interface BonApercu {
  id: string;
  reference: string;
  date_bc: string;
  statut: string;
  fournisseur_raison_sociale: string | null;
  fournisseur_nif: string | null;
  fournisseur_telephone: string | null;
  fournisseur_adresse: string | null;
  departement: string | null;
  projet: string | null;
  acheteur_nom: string | null;
  acheteur_tel: string | null;
  demandeur_nom: string | null;
  demandeur_date: string | null;
  adresse_facturation: string | null;
  adresse_livraison: string | null;
  agence_facturation_snapshot: string | null;
  agence_livraison_snapshot: string | null;
  date_livraison_prevue: string | null;
  conditions: string | null;
  incoterm: string | null;
  conditions_paiement: string | null;
  moyen_paiement: string | null;
  ref_paiement?: string | null;
  montant_paiement?: number | null;
  type_achat: string;
  devise: string;
  total_ht: number;
  total_tva: number;
  total_ttc: number;
  observation: string | null;
  pdf_version: number;
  lignes: BcLigne[];
}

interface ReceptionApercu {
  id: string;
  reference: string;
  bon_id: string;
  bon_reference?: string | null;
  date_reception: string;
  agence_id: string | null;
  statut: string;
  observation: string | null;
  lignes: { id: string; bc_ligne_id: string; quantite_recue: number }[];
}

const STATUT_LABELS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  SOUMIS: 'Soumis',
  VALIDE: 'Validé',
  ENVOYE: 'Envoyé',
  PARTIEL: 'Reçu partiel',
  RECU: 'Reçu',
  COMPLETE: 'Complète',
  RECUE: 'Reçue',
  ANOMALIE: 'Anomalie',
  CONFORME: 'Conforme',
  VALIDEE: 'Validée',
  A_PAYER: 'À payer',
  PARTIELLEMENT_PAYEE: 'Partiellement payée',
  PAYEE: 'Payée',
  PAYE: 'Payé',
  REJETEE: 'Rejeté',
  ANNULE: 'Annulé',
  ANNULEE: 'Annulée',
  CLOTURE: 'Clôturé',
};

const MODE_PAIEMENT_LABELS: Record<string, string> = {
  VIREMENT: 'Virement',
  CHEQUE: 'Chèque',
  ESPECES: 'Espèces',
  AUTRE: 'Autre',
};

export function statutAchatLabel(s: string | null | undefined): string {
  return s ? STATUT_LABELS[s] ?? s : '—';
}

/** Fiche de consultation d'un bon de commande (fenêtre « mini page »). */
@Component({
  selector: 'bea-achats-bon-apercu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, DatePipe, MontantPipe, QuantitePipe],
  template: `
    <div class="bea-apercu__backdrop" (click)="closed.emit()" role="presentation"></div>
    <div class="bea-apercu" role="dialog" aria-modal="true" aria-label="Détail du bon de commande">
      @if (bon(); as b) {
        <header class="bea-apercu__hero">
          <span class="bea-apercu__hero-icon"><mat-icon>request_quote</mat-icon></span>
          <div class="bea-apercu__hero-txt">
            <p>Bon de commande · {{ b.type_achat === 'FOURNITURE' ? 'Fournitures' : b.type_achat }}</p>
            <h2>{{ b.reference }}</h2>
            <div class="bea-apercu__hero-meta">
              <span class="bea-ach__badge" [attr.data-statut]="b.statut">{{ statutLabel(b.statut) }}</span>
              <span><mat-icon>event</mat-icon> {{ b.date_bc | date: 'dd/MM/yyyy' }}</span>
              @if (b.pdf_version > 1) {
                <span><mat-icon>history</mat-icon> PDF v{{ b.pdf_version }}</span>
              }
            </div>
          </div>
          <button type="button" class="bea-apercu__close" (click)="closed.emit()" title="Fermer">
            <mat-icon>close</mat-icon>
          </button>
        </header>

        <div class="bea-apercu__body">
          <div class="bea-apercu__kpis">
            <div class="bea-apercu__kpi">
              <span>Total HT</span>
              <strong>{{ b.total_ht | montant }} <small>{{ b.devise }}</small></strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>TVA</span>
              <strong>{{ b.total_tva | montant }} <small>{{ b.devise }}</small></strong>
            </div>
            <div class="bea-apercu__kpi bea-apercu__kpi--main">
              <span>Total TTC</span>
              <strong>{{ b.total_ttc | montant }} <small>{{ b.devise }}</small></strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>Réception</span>
              <strong>{{ avancement() }} %</strong>
              <div class="bea-apercu__bar"><i [style.width.%]="avancement()"></i></div>
            </div>
          </div>

          <div class="bea-apercu__cards">
            <section class="bea-apercu__card">
              <h3><mat-icon>storefront</mat-icon> Fournisseur</h3>
              <dl>
                <div class="bea-apercu__wide"><dt>Raison sociale</dt><dd>{{ b.fournisseur_raison_sociale || '—' }}</dd></div>
                <div><dt>NIF</dt><dd>{{ b.fournisseur_nif || '—' }}</dd></div>
                <div><dt>Téléphone</dt><dd>{{ b.fournisseur_telephone || '—' }}</dd></div>
                <div class="bea-apercu__wide"><dt>Adresse</dt><dd>{{ b.fournisseur_adresse || '—' }}</dd></div>
              </dl>
            </section>
            <section class="bea-apercu__card">
              <h3><mat-icon>account_balance</mat-icon> Acheteur (BEA)</h3>
              <dl>
                <div><dt>Département</dt><dd>{{ b.departement || '—' }}</dd></div>
                <div><dt>Projet</dt><dd>{{ b.projet || '—' }}</dd></div>
                <div><dt>Acheteur</dt><dd>{{ b.acheteur_nom || '—' }}</dd></div>
                <div><dt>Tél. acheteur</dt><dd>{{ b.acheteur_tel || '—' }}</dd></div>
                <div><dt>Demandeur</dt><dd>{{ b.demandeur_nom || '—' }}</dd></div>
                <div><dt>Date de la demande</dt><dd>{{ b.demandeur_date ? (b.demandeur_date | date: 'dd/MM/yyyy') : '—' }}</dd></div>
              </dl>
            </section>
            <section class="bea-apercu__card">
              <h3><mat-icon>local_shipping</mat-icon> Livraison &amp; facturation</h3>
              <dl>
                <div><dt>Livraison prévue</dt><dd>{{ b.date_livraison_prevue ? (b.date_livraison_prevue | date: 'dd/MM/yyyy') : '—' }}</dd></div>
                <div><dt>Agence de livraison</dt><dd>{{ b.agence_livraison_snapshot || '—' }}</dd></div>
                <div class="bea-apercu__wide"><dt>Adresse de livraison</dt><dd>{{ b.adresse_livraison || '—' }}</dd></div>
                <div><dt>Agence de facturation</dt><dd>{{ b.agence_facturation_snapshot || '—' }}</dd></div>
                <div><dt>Adresse de facturation</dt><dd>{{ b.adresse_facturation || '—' }}</dd></div>
              </dl>
            </section>
            <section class="bea-apercu__card">
              <h3><mat-icon>gavel</mat-icon> Conditions &amp; paiement</h3>
              <dl>
                <div><dt>Moyen de paiement</dt><dd>{{ b.moyen_paiement || '—' }}</dd></div>
                @if (b.moyen_paiement === 'Cash' && b.montant_paiement != null) {
                  <div><dt>Montant en espèces</dt><dd>{{ b.montant_paiement | montant }} {{ b.devise }}</dd></div>
                } @else if (b.ref_paiement) {
                  <div><dt>{{ b.moyen_paiement === 'Amanty' ? 'Tél. Amanty' : 'RIB / compte' }}</dt><dd>{{ b.ref_paiement }}</dd></div>
                }
                <div><dt>Conditions de paiement</dt><dd>{{ b.conditions_paiement || '—' }}</dd></div>
                <div><dt>Incoterm</dt><dd>{{ b.incoterm || '—' }}</dd></div>
                <div><dt>Conditions</dt><dd>{{ b.conditions || '—' }}</dd></div>
              </dl>
            </section>
          </div>

          <section class="bea-apercu__card">
            <h3><mat-icon>list_alt</mat-icon> Lignes de la commande <em>{{ b.lignes.length }}</em></h3>
            <div class="bea-apercu__table-scroll">
              <table class="bea-apercu__table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Désignation</th>
                    <th class="num">Qté</th>
                    <th class="num">Reçu</th>
                    <th>Unité</th>
                    <th class="num">PU</th>
                    <th class="num">Total HT</th>
                    <th class="num">Total TTC</th>
                  </tr>
                </thead>
                <tbody>
                  @for (l of b.lignes; track l.id; let i = $index) {
                    <tr>
                      <td class="muted">{{ i + 1 }}</td>
                      <td>{{ l.description }}</td>
                      <td class="num">{{ l.quantite | quantite }}</td>
                      <td class="num">
                        <span class="bea-apercu__recu" [attr.data-etat]="etatLigne(l)">{{ l.quantite_recue | quantite }}</span>
                      </td>
                      <td>{{ l.uom || 'U' }}</td>
                      <td class="num">{{ l.prix_unitaire | montant }}</td>
                      <td class="num">{{ l.prix_total | montant }}</td>
                      <td class="num">{{ l.total_ttc | montant }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="8" class="bea-apercu__empty">Aucune ligne.</td></tr>
                  }
                </tbody>
                @if (b.lignes.length) {
                  <tfoot>
                    <tr>
                      <td colspan="6">Totaux ({{ b.devise }})</td>
                      <td class="num">{{ b.total_ht | montant }}</td>
                      <td class="num">{{ b.total_ttc | montant }}</td>
                    </tr>
                  </tfoot>
                }
              </table>
            </div>
          </section>

          <section class="bea-apercu__card">
            <h3><mat-icon>inventory_2</mat-icon> Réceptions liées <em>{{ receptions().length }}</em></h3>
            @if (receptions().length) {
              <ul class="bea-apercu__links">
                @for (r of receptions(); track r.id) {
                  <li>
                    <code>{{ r.reference }}</code>
                    <span>{{ r.date_reception | date: 'dd/MM/yyyy' }}</span>
                    <span class="bea-ach__badge" [attr.data-statut]="r.statut">{{ statutLabel(r.statut) }}</span>
                  </li>
                }
              </ul>
            } @else {
              <p class="bea-apercu__empty">Aucune réception enregistrée pour ce bon.</p>
            }
          </section>

          @if (b.observation) {
            <p class="bea-apercu__note"><mat-icon>chat_bubble_outline</mat-icon><span>{{ b.observation }}</span></p>
          }
        </div>

        <footer class="bea-apercu__foot">
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="telechargerPdf(b)" [disabled]="pdfBusy()">
            <mat-icon>picture_as_pdf</mat-icon> {{ pdfBusy() ? 'Génération…' : 'PDF' }}
          </button>
          <span class="bea-apercu__spacer"></span>
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closed.emit()">Fermer</button>
          <button type="button" class="bea-ach__btn" (click)="modifier(b.id)"><mat-icon>edit</mat-icon> Modifier</button>
        </footer>
      } @else {
        <div class="bea-apercu__loading">
          <mat-icon>{{ erreur() ? 'error_outline' : 'hourglass_empty' }}</mat-icon>
          <p>{{ erreur() || 'Chargement du bon de commande…' }}</p>
          @if (erreur()) {
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closed.emit()">Fermer</button>
          }
        </div>
      }
    </div>
  `,
})
export class AchatsBonApercuComponent implements OnInit {
  readonly bonId = input.required<string>();
  readonly closed = output<void>();

  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly feedback = inject(FeedbackService);

  readonly bon = signal<BonApercu | null>(null);
  readonly receptions = signal<ReceptionApercu[]>([]);
  readonly erreur = signal('');
  readonly pdfBusy = signal(false);

  readonly avancement = computed(() => {
    const lignes = this.bon()?.lignes ?? [];
    const total = lignes.reduce((s, l) => s + (Number(l.quantite) || 0), 0);
    if (!total) return 0;
    const recu = lignes.reduce((s, l) => s + Math.min(Number(l.quantite_recue) || 0, Number(l.quantite) || 0), 0);
    return Math.round((recu / total) * 100);
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    this.closed.emit();
  }

  ngOnInit(): void {
    this.api.get<BonApercu>(`/mg/achats/bons/${this.bonId()}`).subscribe({
      next: (b) => this.bon.set(b),
      error: () => this.erreur.set('Bon de commande introuvable.'),
    });
    this.api.get<ReceptionApercu[]>('/mg/achats/receptions').subscribe({
      next: (rows) => this.receptions.set(rows.filter((r) => r.bon_id === this.bonId())),
    });
  }

  statutLabel(s: string): string {
    return statutAchatLabel(s);
  }

  etatLigne(l: BcLigne): string {
    const recu = Number(l.quantite_recue) || 0;
    if (recu <= 0) return 'aucun';
    return recu >= Number(l.quantite) ? 'complet' : 'partiel';
  }

  modifier(id: string): void {
    this.closed.emit();
    void this.router.navigateByUrl(`/achats-appro/bons/${id}`);
  }

  telechargerPdf(b: BonApercu): void {
    this.pdfBusy.set(true);
    this.api
      .download(`/mg/achats/bons/${b.id}/pdf`, {
        signataire_1: 'Signature Chef Sce Moyens Généraux',
        signataire_2: 'Signature Directrice des Ressources',
      })
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `Bon-Commande-${(b.reference.replace(/\D/g, '') || '0').padStart(6, '0')}.pdf`;
          a.click();
          URL.revokeObjectURL(url);
          this.pdfBusy.set(false);
        },
        error: () => {
          this.pdfBusy.set(false);
          this.feedback.error({ title: 'Export PDF impossible', message: 'Réessayez depuis la fiche du bon.' });
        },
      });
  }
}

interface LigneReceptionVue {
  id: string;
  description: string;
  uom: string;
  commande: number;
  recuIci: number;
  recuTotal: number;
  reste: number;
}

/** Fiche de consultation d'une réception (fenêtre « mini page »). */
@Component({
  selector: 'bea-achats-reception-apercu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, DatePipe, QuantitePipe, AchatsBonApercuComponent],
  template: `
    <div class="bea-apercu__backdrop" (click)="closed.emit()" role="presentation"></div>
    <div class="bea-apercu bea-apercu--reception" role="dialog" aria-modal="true" aria-label="Détail de la réception">
      @if (reception(); as r) {
        <header class="bea-apercu__hero">
          <span class="bea-apercu__hero-icon"><mat-icon>inventory_2</mat-icon></span>
          <div class="bea-apercu__hero-txt">
            <p>Réception · contrôle physique</p>
            <h2>{{ r.reference }}</h2>
            <div class="bea-apercu__hero-meta">
              <span class="bea-ach__badge" [attr.data-statut]="r.statut">{{ statutLabel(r.statut) }}</span>
              <span><mat-icon>event</mat-icon> {{ r.date_reception | date: 'dd/MM/yyyy' }}</span>
            </div>
          </div>
          <button type="button" class="bea-apercu__close" (click)="closed.emit()" title="Fermer">
            <mat-icon>close</mat-icon>
          </button>
        </header>

        <div class="bea-apercu__body">
          <div class="bea-apercu__kpis">
            <div class="bea-apercu__kpi bea-apercu__kpi--main">
              <span>Quantité reçue</span>
              <strong>{{ totalRecu() | quantite }}</strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>Lignes reçues</span>
              <strong>{{ lignes().length }}</strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>Reste sur le BC</span>
              <strong>{{ resteBc() | quantite }}</strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>BC reçu à</span>
              <strong>{{ avancementBc() }} %</strong>
              <div class="bea-apercu__bar"><i [style.width.%]="avancementBc()"></i></div>
            </div>
          </div>

          <div class="bea-apercu__cards">
            <section class="bea-apercu__card">
              <h3><mat-icon>request_quote</mat-icon> Bon de commande</h3>
              <dl>
                <div><dt>Référence</dt><dd><code>{{ bon()?.reference || r.bon_reference || '—' }}</code></dd></div>
                <div><dt>Statut du BC</dt><dd>
                  @if (bon(); as b) {
                    <span class="bea-ach__badge" [attr.data-statut]="b.statut">{{ statutLabel(b.statut) }}</span>
                  } @else { — }
                </dd></div>
                <div class="bea-apercu__wide"><dt>Fournisseur</dt><dd>{{ bon()?.fournisseur_raison_sociale || '—' }}</dd></div>
                <div><dt>Date du BC</dt><dd>{{ bon()?.date_bc ? (bon()!.date_bc | date: 'dd/MM/yyyy') : '—' }}</dd></div>
                <div><dt>Livraison prévue</dt><dd>{{ bon()?.date_livraison_prevue ? (bon()!.date_livraison_prevue | date: 'dd/MM/yyyy') : '—' }}</dd></div>
              </dl>
            </section>
            <section class="bea-apercu__card">
              <h3><mat-icon>place</mat-icon> Lieu de réception</h3>
              <dl>
                <div class="bea-apercu__wide"><dt>Agence</dt><dd>{{ agence() || bon()?.agence_livraison_snapshot || '—' }}</dd></div>
                <div class="bea-apercu__wide"><dt>Adresse de livraison</dt><dd>{{ bon()?.adresse_livraison || '—' }}</dd></div>
              </dl>
            </section>
          </div>

          <section class="bea-apercu__card">
            <h3><mat-icon>fact_check</mat-icon> Articles reçus <em>{{ lignes().length }}</em></h3>
            <div class="bea-apercu__table-scroll">
              <table class="bea-apercu__table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Désignation</th>
                    <th>Unité</th>
                    <th class="num">Commandé</th>
                    <th class="num">Reçu ici</th>
                    <th class="num">Reçu au total</th>
                    <th class="num">Reste</th>
                  </tr>
                </thead>
                <tbody>
                  @for (l of lignes(); track l.id; let i = $index) {
                    <tr>
                      <td class="muted">{{ i + 1 }}</td>
                      <td>{{ l.description }}</td>
                      <td>{{ l.uom }}</td>
                      <td class="num">{{ l.commande | quantite }}</td>
                      <td class="num"><strong>{{ l.recuIci | quantite }}</strong></td>
                      <td class="num">{{ l.recuTotal | quantite }}</td>
                      <td class="num">
                        <span class="bea-apercu__recu" [attr.data-etat]="l.reste > 0 ? 'partiel' : 'complet'">{{ l.reste | quantite }}</span>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="7" class="bea-apercu__empty">Aucune ligne.</td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>

          @if (r.observation) {
            <p class="bea-apercu__note"><mat-icon>chat_bubble_outline</mat-icon><span>{{ r.observation }}</span></p>
          }
        </div>

        <footer class="bea-apercu__foot">
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="bonOuvert.set(true)">
            <mat-icon>request_quote</mat-icon> Voir le BC
          </button>
          <span class="bea-apercu__spacer"></span>
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closed.emit()">Fermer</button>
          <button type="button" class="bea-ach__btn" (click)="modifier(r.id)"><mat-icon>edit</mat-icon> Modifier</button>
        </footer>
      } @else {
        <div class="bea-apercu__loading">
          <mat-icon>{{ erreur() ? 'error_outline' : 'hourglass_empty' }}</mat-icon>
          <p>{{ erreur() || 'Chargement de la réception…' }}</p>
          @if (erreur()) {
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closed.emit()">Fermer</button>
          }
        </div>
      }
    </div>

    @if (bonOuvert() && reception(); as r) {
      <bea-achats-bon-apercu [bonId]="r.bon_id" (closed)="bonOuvert.set(false)" />
    }
  `,
})
export class AchatsReceptionApercuComponent implements OnInit {
  readonly receptionId = input.required<string>();
  readonly closed = output<void>();

  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly reception = signal<ReceptionApercu | null>(null);
  readonly bon = signal<BonApercu | null>(null);
  readonly agences = signal<{ id: string; libelle: string }[]>([]);
  readonly erreur = signal('');
  readonly bonOuvert = signal(false);

  readonly agence = computed(() => {
    const id = this.reception()?.agence_id;
    return id ? this.agences().find((a) => a.id === id)?.libelle ?? null : null;
  });

  readonly lignes = computed<LigneReceptionVue[]>(() => {
    const r = this.reception();
    if (!r) return [];
    const bcLignes = new Map((this.bon()?.lignes ?? []).map((l) => [l.id, l]));
    return r.lignes.map((l) => {
      const bc = bcLignes.get(l.bc_ligne_id);
      const commande = Number(bc?.quantite) || 0;
      const recuTotal = Number(bc?.quantite_recue) || 0;
      return {
        id: l.id,
        description: bc?.description ?? '—',
        uom: bc?.uom || 'U',
        commande,
        recuIci: Number(l.quantite_recue) || 0,
        recuTotal,
        reste: Math.max(0, commande - recuTotal),
      };
    });
  });

  readonly totalRecu = computed(() => this.lignes().reduce((s, l) => s + l.recuIci, 0));

  readonly resteBc = computed(() =>
    (this.bon()?.lignes ?? []).reduce(
      (s, l) => s + Math.max(0, (Number(l.quantite) || 0) - (Number(l.quantite_recue) || 0)),
      0,
    ),
  );

  readonly avancementBc = computed(() => {
    const lignes = this.bon()?.lignes ?? [];
    const total = lignes.reduce((s, l) => s + (Number(l.quantite) || 0), 0);
    if (!total) return 0;
    const recu = lignes.reduce((s, l) => s + Math.min(Number(l.quantite_recue) || 0, Number(l.quantite) || 0), 0);
    return Math.round((recu / total) * 100);
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.bonOuvert()) return;
    this.closed.emit();
  }

  ngOnInit(): void {
    this.api.get<{ id: string; libelle: string }[]>('/mg/achats/agences').subscribe({
      next: (rows) => this.agences.set(rows),
    });
    this.api.get<ReceptionApercu>(`/mg/achats/receptions/${this.receptionId()}`).subscribe({
      next: (r) => {
        this.reception.set(r);
        this.api.get<BonApercu>(`/mg/achats/bons/${r.bon_id}`).subscribe({ next: (b) => this.bon.set(b) });
      },
      error: () => this.erreur.set('Réception introuvable.'),
    });
  }

  statutLabel(s: string): string {
    return statutAchatLabel(s);
  }

  modifier(id: string): void {
    this.closed.emit();
    void this.router.navigateByUrl(`/achats-appro/receptions/${id}`);
  }
}

interface FactureApercu {
  id: string;
  reference: string;
  numero_fournisseur: string | null;
  fournisseur_id: string;
  bon_id: string;
  reception_id: string | null;
  date_facture: string;
  date_echeance: string | null;
  montant_ht: number;
  montant_tva: number;
  montant_ttc: number;
  devise: string;
  statut: string;
  ecart_quantite: boolean;
  ecart_montant: boolean;
  observation: string | null;
  lignes: { id: string; designation: string; quantite: number; prix_unitaire: number; total_ht: number }[];
}

interface PaiementApercu {
  id: string;
  reference: string;
  facture_id: string;
  montant: number;
  date_echeance: string | null;
  date_paiement: string | null;
  mode_paiement: string | null;
  reference_paiement: string | null;
  statut: string;
  observation: string | null;
}

interface EcheanceVue {
  etat: 'solde' | 'retard' | 'proche' | 'ok' | 'aucune';
  label: string;
}

function echeanceVue(dateEcheance: string | null | undefined, solde: boolean): EcheanceVue {
  if (solde) return { etat: 'solde', label: 'Soldé' };
  if (!dateEcheance) return { etat: 'aucune', label: 'Sans échéance' };
  const jour = new Date();
  jour.setHours(0, 0, 0, 0);
  const diff = Math.round((new Date(`${dateEcheance}T00:00:00`).getTime() - jour.getTime()) / 86_400_000);
  if (diff < 0) return { etat: 'retard', label: `En retard de ${-diff} j` };
  if (diff === 0) return { etat: 'proche', label: "Échéance aujourd'hui" };
  return { etat: diff <= 7 ? 'proche' : 'ok', label: `Dans ${diff} j` };
}

interface Justificatif {
  id: string;
  filename: string;
  title: string | null;
  mime_type: string | null;
  size_bytes: number;
  created_at: string | null;
  ocr_status: string;
  ocr_extrait: string | null;
}

interface DossierEtape {
  id: string;
  reference: string;
  statut: string;
  date_op: string | null;
  montant: number | null;
}

interface FactureDossier {
  justificatifs: Justificatif[];
  demande: DossierEtape | null;
  bon: DossierEtape | null;
  receptions: DossierEtape[];
  paiements: DossierEtape[];
  autres_factures: DossierEtape[];
  controles: { code: string; libelle: string; ok: boolean | null; detail: string | null }[];
  evenements: { action: string; message: string | null; user_nom: string | null; created_at: string }[];
  total_paye: number;
  reste_a_payer: number;
}

const ACTION_LABELS: Record<string, string> = {
  create: 'Création',
  update: 'Modification',
  deactivate: 'Désactivation',
  delete: 'Suppression',
};

function totalPaye(paiements: PaiementApercu[]): number {
  return paiements.filter((p) => p.statut === 'PAYE').reduce((s, p) => s + (Number(p.montant) || 0), 0);
}

/** Fiche de consultation d'une facture fournisseur (fenêtre « mini page »). */
@Component({
  selector: 'bea-achats-facture-apercu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, DatePipe, MontantPipe, QuantitePipe, AchatsBonApercuComponent],
  template: `
    <div class="bea-apercu__backdrop" (click)="closed.emit()" role="presentation"></div>
    <div class="bea-apercu" role="dialog" aria-modal="true" aria-label="Détail de la facture">
      @if (facture(); as f) {
        <header class="bea-apercu__hero">
          <span class="bea-apercu__hero-icon"><mat-icon>receipt_long</mat-icon></span>
          <div class="bea-apercu__hero-txt">
            <p>Facture fournisseur{{ f.numero_fournisseur ? ' · N° ' + f.numero_fournisseur : '' }}</p>
            <h2>{{ f.reference }}</h2>
            <div class="bea-apercu__hero-meta">
              <span class="bea-ach__badge" [attr.data-statut]="f.statut">{{ statutLabel(f.statut) }}</span>
              <span><mat-icon>event</mat-icon> {{ f.date_facture | date: 'dd/MM/yyyy' }}</span>
              <span class="bea-apercu__pill" [attr.data-etat]="echeance().etat">
                <mat-icon>schedule</mat-icon> {{ echeance().label }}
              </span>
            </div>
          </div>
          <button type="button" class="bea-apercu__close" (click)="closed.emit()" title="Fermer">
            <mat-icon>close</mat-icon>
          </button>
        </header>

        <div class="bea-apercu__body">
          <div class="bea-apercu__kpis">
            <div class="bea-apercu__kpi">
              <span>Montant HT</span>
              <strong>{{ f.montant_ht | montant }} <small>{{ f.devise }}</small></strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>TVA</span>
              <strong>{{ f.montant_tva | montant }} <small>{{ f.devise }}</small></strong>
            </div>
            <div class="bea-apercu__kpi bea-apercu__kpi--main">
              <span>Montant TTC</span>
              <strong>{{ f.montant_ttc | montant }} <small>{{ f.devise }}</small></strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>Réglé</span>
              <strong>{{ avancementPaiement() }} %</strong>
              <div class="bea-apercu__bar"><i [style.width.%]="avancementPaiement()"></i></div>
            </div>
          </div>

          <section class="bea-apercu__card bea-preuve" [attr.data-etat]="dossier()?.justificatifs?.length ? 'ok' : 'manquante'">
            <h3>
              <mat-icon>{{ dossier()?.justificatifs?.length ? 'verified_user' : 'report' }}</mat-icon>
              Facture du fournisseur (preuve)
              <em>{{ dossier()?.justificatifs?.length ? dossier()!.justificatifs.length + ' pièce(s)' : 'Manquante' }}</em>
            </h3>
            @for (d of dossier()?.justificatifs ?? []; track d.id) {
              <div class="bea-preuve__doc">
                <mat-icon [attr.data-nature]="nature(d)">{{ icone(d) }}</mat-icon>
                <div class="bea-preuve__meta">
                  <strong>{{ d.title || d.filename }}</strong>
                  <span>{{ d.filename }} · {{ taille(d.size_bytes) }}{{ d.created_at ? ' · ajoutée le ' + (d.created_at | date: 'dd/MM/yyyy HH:mm') : '' }}</span>
                </div>
                <small class="bea-preuve__ocr" [attr.data-status]="d.ocr_status">{{ ocrLabel(d.ocr_status) }}</small>
                @if (visualisable(d)) {
                  <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="voirPiece(d)" [disabled]="pieceBusy()">
                    <mat-icon>{{ pieceOuverte()?.id === d.id ? 'visibility_off' : 'visibility' }}</mat-icon>
                    {{ pieceOuverte()?.id === d.id ? 'Masquer' : 'Voir' }}
                  </button>
                } @else {
                  <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="telechargerPiece(d)" title="Ouvrir dans Word / Excel">
                    <mat-icon>open_in_new</mat-icon> Ouvrir
                  </button>
                }
                <button type="button" class="bea-ach__icon-btn" title="Télécharger" (click)="telechargerPiece(d)">
                  <mat-icon>download</mat-icon>
                </button>
                @if (peutDetacher(f)) {
                  <button
                    type="button"
                    class="bea-ach__icon-btn bea-preuve__detach"
                    title="Détacher la pièce"
                    [attr.aria-label]="'Détacher ' + d.filename"
                    [disabled]="detaching() === d.id"
                    (click)="detacherPiece(d)"
                  >
                    <mat-icon>link_off</mat-icon>
                  </button>
                }
              </div>
              @if (pieceOuverte()?.id === d.id && pieceUrl(); as url) {
                <div class="bea-preuve__viewer">
                  @if (estImage(d)) {
                    <img [src]="url" [alt]="d.filename" />
                  } @else {
                    <iframe [src]="url" title="Facture fournisseur"></iframe>
                  }
                </div>
              }
              @if (d.ocr_extrait) {
                <details class="bea-preuve__texte">
                  <summary>Texte lu automatiquement (OCR)</summary>
                  <p>{{ d.ocr_extrait }}</p>
                </details>
              }
            } @empty {
              <p class="bea-preuve__vide">
                La facture remise par le fournisseur ({{ piecesFormats }}) n'est pas encore rattachée. Sans preuve, le paiement ne devrait pas être engagé.
              </p>
            }
            <label class="bea-ach__btn bea-preuve__ajout" [class.bea-ach__btn--ghost]="!!dossier()?.justificatifs?.length">
              <mat-icon>{{ uploadBusy() ? 'hourglass_empty' : 'attach_file' }}</mat-icon>
              {{ uploadBusy() ? 'Envoi…' : dossier()?.justificatifs?.length ? 'Ajouter une pièce' : 'Joindre la facture du fournisseur' }}
              <input type="file" [accept]="piecesAccept" hidden (change)="joindre($event, f)" [disabled]="uploadBusy()" />
            </label>
          </section>

          <div class="bea-apercu__cards">
            <section class="bea-apercu__card">
              <h3><mat-icon>storefront</mat-icon> Fournisseur</h3>
              <dl>
                <div class="bea-apercu__wide"><dt>Raison sociale</dt><dd>{{ bon()?.fournisseur_raison_sociale || '—' }}</dd></div>
                <div><dt>NIF</dt><dd>{{ bon()?.fournisseur_nif || '—' }}</dd></div>
                <div><dt>N° facture fournisseur</dt><dd>{{ f.numero_fournisseur || '—' }}</dd></div>
              </dl>
            </section>
            <section class="bea-apercu__card">
              <h3><mat-icon>link</mat-icon> Rattachement</h3>
              <dl>
                <div><dt>Bon de commande</dt><dd>
                  <button type="button" class="bea-apercu__ref-btn" (click)="bonOuvert.set(true)">
                    <code>{{ bon()?.reference || '—' }}</code>
                  </button>
                </dd></div>
                <div><dt>Réception</dt><dd><code>{{ reception()?.reference || '—' }}</code></dd></div>
                <div><dt>Date de facture</dt><dd>{{ f.date_facture | date: 'dd/MM/yyyy' }}</dd></div>
                <div><dt>Échéance</dt><dd>{{ f.date_echeance ? (f.date_echeance | date: 'dd/MM/yyyy') : '—' }}</dd></div>
              </dl>
            </section>
          </div>

          <section class="bea-apercu__card bea-apercu__match" [attr.data-etat]="anomalie() ? 'anomalie' : 'conforme'">
            <h3>
              <mat-icon>{{ anomalie() ? 'report_problem' : 'verified' }}</mat-icon>
              Rapprochement BC · réception · facture
              <em>{{ anomalie() ? 'Écart détecté' : 'Conforme' }}</em>
            </h3>
            <div class="bea-apercu__match-grid">
              <div [attr.data-ko]="f.ecart_quantite">
                <span>Quantités</span>
                <p>Commandé <strong>{{ qtyCommandee() | quantite }}</strong></p>
                <p>Reçu <strong>{{ qtyRecue() | quantite }}</strong></p>
                <p>Facturé <strong>{{ qtyFacturee() | quantite }}</strong></p>
              </div>
              <div [attr.data-ko]="f.ecart_montant">
                <span>Montants TTC</span>
                <p>BC <strong>{{ (bon()?.total_ttc ?? 0) | montant }}</strong></p>
                <p>Facture <strong>{{ f.montant_ttc | montant }}</strong></p>
                <p>Écart <strong>{{ ecartMontant() > 0 ? '+' : '' }}{{ ecartMontant() | montant }}</strong></p>
              </div>
            </div>
          </section>

          @if (dossier(); as d) {
            <div class="bea-apercu__cards">
              <section class="bea-apercu__card">
                <h3><mat-icon>checklist</mat-icon> Points de contrôle <em>{{ nbControlesOk() }}/{{ d.controles.length }}</em></h3>
                <ul class="bea-ctrl">
                  @for (c of d.controles; track c.code) {
                    <li [attr.data-ok]="c.ok === null ? 'na' : c.ok">
                      <mat-icon>{{ c.ok === null ? 'radio_button_unchecked' : c.ok ? 'check_circle' : 'cancel' }}</mat-icon>
                      <div>
                        <span>{{ c.libelle }}</span>
                        @if (c.detail) {
                          <small>{{ c.detail }}</small>
                        }
                      </div>
                    </li>
                  }
                </ul>
              </section>
              <section class="bea-apercu__card">
                <h3><mat-icon>route</mat-icon> Parcours d'achat</h3>
                <ol class="bea-parcours">
                  <li [attr.data-fait]="!!d.demande">
                    <span>Demande d'achat</span>
                    <strong>{{ d.demande?.reference || 'Sans DA' }}</strong>
                    @if (d.demande) { <small>{{ statutLabel(d.demande.statut) }} · {{ d.demande.date_op | date: 'dd/MM/yyyy' }}</small> }
                  </li>
                  <li [attr.data-fait]="!!d.bon">
                    <span>Bon de commande</span>
                    <strong>{{ d.bon?.reference || '—' }}</strong>
                    @if (d.bon) { <small>{{ statutLabel(d.bon.statut) }} · {{ (d.bon.montant ?? 0) | montant }} {{ f.devise }}</small> }
                  </li>
                  <li [attr.data-fait]="d.receptions.length > 0">
                    <span>Réception{{ d.receptions.length > 1 ? 's' : '' }}</span>
                    <strong>{{ d.receptions.length ? referencesDe(d.receptions) : 'Aucune' }}</strong>
                    @if (d.receptions.length) { <small>{{ statutLabel(d.receptions[0].statut) }} · {{ d.receptions[0].date_op | date: 'dd/MM/yyyy' }}</small> }
                  </li>
                  <li data-fait="true" data-courant="true">
                    <span>Facture</span>
                    <strong>{{ f.reference }}</strong>
                    <small>{{ statutLabel(f.statut) }} · {{ f.montant_ttc | montant }} {{ f.devise }}</small>
                  </li>
                  <li [attr.data-fait]="d.reste_a_payer <= 0 && d.total_paye > 0">
                    <span>Paiement</span>
                    <strong>{{ d.paiements.length ? referencesDe(d.paiements) : 'Non engagé' }}</strong>
                    <small>Payé {{ d.total_paye | montant }} · reste {{ d.reste_a_payer | montant }}</small>
                  </li>
                </ol>
                @if (d.autres_factures.length) {
                  <p class="bea-apercu__sum">Autres factures sur ce BC : {{ referencesDe(d.autres_factures) }}</p>
                }
              </section>
            </div>
          }

          <section class="bea-apercu__card">
            <h3><mat-icon>list_alt</mat-icon> Lignes facturées <em>{{ f.lignes.length }}</em></h3>
            <div class="bea-apercu__table-scroll">
              <table class="bea-apercu__table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Désignation</th>
                    <th class="num">Qté</th>
                    <th class="num">PU</th>
                    <th class="num">Total HT</th>
                  </tr>
                </thead>
                <tbody>
                  @for (l of f.lignes; track l.id; let i = $index) {
                    <tr>
                      <td class="muted">{{ i + 1 }}</td>
                      <td>{{ l.designation }}</td>
                      <td class="num">{{ l.quantite | quantite }}</td>
                      <td class="num">{{ l.prix_unitaire | montant }}</td>
                      <td class="num">{{ l.total_ht | montant }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="5" class="bea-apercu__empty">Aucune ligne.</td></tr>
                  }
                </tbody>
                @if (f.lignes.length) {
                  <tfoot>
                    <tr>
                      <td colspan="4">Total HT ({{ f.devise }})</td>
                      <td class="num">{{ f.montant_ht | montant }}</td>
                    </tr>
                  </tfoot>
                }
              </table>
            </div>
          </section>

          <section class="bea-apercu__card">
            <h3><mat-icon>payments</mat-icon> Paiements suivis <em>{{ paiements().length }}</em></h3>
            @if (paiements().length) {
              <ul class="bea-apercu__links">
                @for (p of paiements(); track p.id) {
                  <li>
                    <code>{{ p.reference }}</code>
                    <span>{{ p.montant | montant }} {{ f.devise }}</span>
                    <span class="muted">{{ p.date_paiement ? (p.date_paiement | date: 'dd/MM/yyyy') : (p.date_echeance ? 'éch. ' + (p.date_echeance | date: 'dd/MM/yyyy') : '') }}</span>
                    <span class="bea-ach__badge" [attr.data-statut]="p.statut">{{ statutLabel(p.statut) }}</span>
                  </li>
                }
              </ul>
              <p class="bea-apercu__sum">Reste à payer : <strong>{{ reste() | montant }} {{ f.devise }}</strong></p>
            } @else {
              <p class="bea-apercu__empty">Aucun paiement suivi pour cette facture.</p>
            }
          </section>

          @if (f.observation) {
            <p class="bea-apercu__note"><mat-icon>chat_bubble_outline</mat-icon><span>{{ f.observation }}</span></p>
          }

          @if (dossier()?.evenements?.length) {
            <section class="bea-apercu__card">
              <h3><mat-icon>history</mat-icon> Historique <em>{{ dossier()!.evenements.length }}</em></h3>
              <ul class="bea-histo">
                @for (e of dossier()!.evenements; track $index) {
                  <li>
                    <time>{{ e.created_at | date: 'dd/MM/yyyy HH:mm' }}</time>
                    <span>{{ actionLabel(e.action) }}{{ e.message ? ' — ' + e.message : '' }}</span>
                    <small>{{ e.user_nom || 'Système' }}</small>
                  </li>
                }
              </ul>
            </section>
          }
        </div>

        <footer class="bea-apercu__foot">
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="bonOuvert.set(true)">
            <mat-icon>request_quote</mat-icon> Voir le BC
          </button>
          <span class="bea-apercu__spacer"></span>
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closed.emit()">Fermer</button>
          <button type="button" class="bea-ach__btn" (click)="modifier(f.id)"><mat-icon>edit</mat-icon> Modifier</button>
        </footer>
      } @else {
        <div class="bea-apercu__loading">
          <mat-icon>{{ erreur() ? 'error_outline' : 'hourglass_empty' }}</mat-icon>
          <p>{{ erreur() || 'Chargement de la facture…' }}</p>
          @if (erreur()) {
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closed.emit()">Fermer</button>
          }
        </div>
      }
    </div>

    @if (bonOuvert() && facture(); as f) {
      <bea-achats-bon-apercu [bonId]="f.bon_id" (closed)="bonOuvert.set(false)" />
    }
  `,
})
export class AchatsFactureApercuComponent implements OnInit, OnDestroy {
  readonly factureId = input.required<string>();
  readonly closed = output<void>();

  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly feedback = inject(FeedbackService);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly auth = inject(AuthService);

  readonly detaching = signal<string | null>(null);
  readonly dossier = signal<FactureDossier | null>(null);
  readonly pieceOuverte = signal<Justificatif | null>(null);
  readonly pieceUrl = signal<SafeResourceUrl | null>(null);
  readonly pieceBusy = signal(false);
  readonly uploadBusy = signal(false);
  private blobUrl: string | null = null;

  readonly nbControlesOk = computed(() => (this.dossier()?.controles ?? []).filter((c) => c.ok === true).length);

  readonly facture = signal<FactureApercu | null>(null);
  readonly bon = signal<BonApercu | null>(null);
  readonly reception = signal<ReceptionApercu | null>(null);
  readonly paiements = signal<PaiementApercu[]>([]);
  readonly erreur = signal('');
  readonly bonOuvert = signal(false);

  readonly paye = computed(() => totalPaye(this.paiements()));
  readonly reste = computed(() => Math.max(0, (Number(this.facture()?.montant_ttc) || 0) - this.paye()));
  readonly avancementPaiement = computed(() => {
    const ttc = Number(this.facture()?.montant_ttc) || 0;
    return ttc ? Math.min(100, Math.round((this.paye() / ttc) * 100)) : 0;
  });
  readonly echeance = computed(() => {
    const f = this.facture();
    const solde = !!f && Number(f.montant_ttc) > 0 && this.reste() <= 0;
    return echeanceVue(f?.date_echeance, solde);
  });
  readonly anomalie = computed(() => {
    const f = this.facture();
    return !!f && (f.ecart_quantite || f.ecart_montant || f.statut === 'ANOMALIE');
  });
  readonly qtyCommandee = computed(() => (this.bon()?.lignes ?? []).reduce((s, l) => s + (Number(l.quantite) || 0), 0));
  readonly qtyRecue = computed(() => (this.bon()?.lignes ?? []).reduce((s, l) => s + (Number(l.quantite_recue) || 0), 0));
  readonly qtyFacturee = computed(() => (this.facture()?.lignes ?? []).reduce((s, l) => s + (Number(l.quantite) || 0), 0));
  readonly ecartMontant = computed(
    () => Math.round(((Number(this.facture()?.montant_ttc) || 0) - (Number(this.bon()?.total_ttc) || 0)) * 100) / 100,
  );

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.bonOuvert()) return;
    this.closed.emit();
  }

  ngOnInit(): void {
    const id = this.factureId();
    this.api.get<FactureApercu>(`/mg/achats/factures/${id}`).subscribe({
      next: (f) => {
        this.facture.set(f);
        this.api.get<BonApercu>(`/mg/achats/bons/${f.bon_id}`).subscribe({ next: (b) => this.bon.set(b) });
        if (f.reception_id) {
          this.api
            .get<ReceptionApercu>(`/mg/achats/receptions/${f.reception_id}`)
            .subscribe({ next: (r) => this.reception.set(r) });
        }
      },
      error: () => this.erreur.set('Facture introuvable.'),
    });
    this.api.get<PaiementApercu[]>('/mg/achats/paiements', { facture_id: id }).subscribe({
      next: (rows) => this.paiements.set(rows.filter((p) => p.facture_id === id)),
    });
    this.chargerDossier();
  }

  ngOnDestroy(): void {
    this.libererPiece();
  }

  private chargerDossier(): void {
    this.api.get<FactureDossier>(`/mg/achats/factures/${this.factureId()}/dossier`).subscribe({
      next: (d) => this.dossier.set(d),
    });
  }

  private libererPiece(): void {
    if (this.blobUrl) URL.revokeObjectURL(this.blobUrl);
    this.blobUrl = null;
    this.pieceUrl.set(null);
  }

  readonly piecesAccept = PIECES_ACCEPT;
  readonly piecesFormats = PIECES_FORMATS_LABEL;

  nature(d: Justificatif): PieceNature {
    return naturePiece(d.filename, d.mime_type);
  }

  icone(d: Justificatif): string {
    return iconePiece(d.filename, d.mime_type);
  }

  estImage(d: Justificatif): boolean {
    return this.nature(d) === 'image' && !/\.tiff?$/i.test(d.filename);
  }

  visualisable(d: Justificatif): boolean {
    return this.nature(d) === 'pdf' || this.estImage(d);
  }

  taille(bytes: number): string {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} Mo`;
  }

  ocrLabel(s: string): string {
    return { done: 'Lue (OCR)', processing: 'Lecture…', failed: 'OCR échoué' }[s] ?? 'OCR en attente';
  }

  actionLabel(a: string): string {
    return ACTION_LABELS[a] ?? a;
  }

  referencesDe(etapes: DossierEtape[]): string {
    return etapes.map((e) => e.reference).join(', ');
  }

  voirPiece(d: Justificatif): void {
    if (this.pieceOuverte()?.id === d.id) {
      this.pieceOuverte.set(null);
      this.libererPiece();
      return;
    }
    this.pieceBusy.set(true);
    this.api.download(`/ged/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        this.libererPiece();
        const typed = blob.type ? blob : new Blob([blob], { type: this.estImage(d) ? 'image/*' : 'application/pdf' });
        this.blobUrl = URL.createObjectURL(typed);
        this.pieceUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.blobUrl));
        this.pieceOuverte.set(d);
        this.pieceBusy.set(false);
      },
      error: () => {
        this.pieceBusy.set(false);
        this.feedback.error({ title: 'Pièce illisible', message: 'Accès GED refusé ou fichier introuvable.' });
      },
    });
  }

  telechargerPiece(d: Justificatif): void {
    this.api.download(`/ged/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename || 'facture-fournisseur';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.feedback.error({ title: 'Téléchargement impossible', message: 'Accès GED refusé ou fichier introuvable.' }),
    });
  }

  /** Une facture payée garde ses preuves (piste d'audit du paiement). */
  peutDetacher(f: FactureApercu): boolean {
    return f.statut !== 'PAYEE' && this.auth.canWriteGed();
  }

  detacherPiece(d: Justificatif): void {
    this.detaching.set(d.id);
    this.feedback
      .runWithReason(
        (motif) => this.api.delete(`/ged/documents/${d.id}?reason=${encodeURIComponent(motif)}`),
        {
          reason: detacherReason(d.filename),
          loading: 'Détachement de la pièce…',
          errorTitle: 'Détachement refusé',
          success: { title: 'Pièce détachée', details: [{ label: 'Fichier', value: d.filename }] },
        },
      )
      .subscribe({
        next: () => {
          if (this.pieceOuverte()?.id === d.id) {
            this.pieceOuverte.set(null);
            this.libererPiece();
          }
          this.chargerDossier();
        },
        error: () => this.detaching.set(null),
        complete: () => this.detaching.set(null),
      });
  }

  joindre(ev: Event, f: FactureApercu): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    const refus = verifierPieceJointe(file);
    if (refus) {
      this.feedback.error({ title: 'Pièce refusée', message: refus });
      return;
    }
    this.uploadBusy.set(true);
    this.api
      .upload('/documents/from-operation', file, {
        espace_code: 'moyens-generaux',
        module_code: 'achats-appro',
        source_type: 'achat_facture',
        source_id: f.id,
        doc_type: 'FACTURE_FOURNISSEUR',
        title: `Facture fournisseur ${f.numero_fournisseur || f.reference}`,
        reference: f.numero_fournisseur || f.reference,
        date_document: f.date_facture,
        fournisseur_id: f.fournisseur_id,
      })
      .subscribe({
        next: () => {
          this.uploadBusy.set(false);
          this.feedback.success({ title: 'Pièce rattachée', message: `Facture fournisseur archivée pour ${f.reference}.` });
          this.chargerDossier();
        },
        error: (err: { status?: number; error?: { detail?: unknown } }) => {
          this.uploadBusy.set(false);
          const detail = err?.error?.detail;
          this.feedback.error({
            title: 'Archivage refusé',
            message: typeof detail === 'string' && err.status !== 403 ? detail : 'Vérifiez la permission ged.write.',
          });
        },
      });
  }

  statutLabel(s: string): string {
    return statutAchatLabel(s);
  }

  modifier(id: string): void {
    this.closed.emit();
    void this.router.navigateByUrl(`/achats-appro/factures/${id}`);
  }
}

/** Fiche de consultation d'un suivi de paiement (fenêtre « mini page »). */
@Component({
  selector: 'bea-achats-paiement-apercu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, DatePipe, MontantPipe, AchatsFactureApercuComponent],
  template: `
    <div class="bea-apercu__backdrop" (click)="closed.emit()" role="presentation"></div>
    <div class="bea-apercu bea-apercu--reception" role="dialog" aria-modal="true" aria-label="Détail du paiement">
      @if (paiement(); as p) {
        <header class="bea-apercu__hero">
          <span class="bea-apercu__hero-icon"><mat-icon>payments</mat-icon></span>
          <div class="bea-apercu__hero-txt">
            <p>Suivi de paiement · trésorerie interne</p>
            <h2>{{ p.reference }}</h2>
            <div class="bea-apercu__hero-meta">
              <span class="bea-ach__badge" [attr.data-statut]="p.statut">{{ statutLabel(p.statut) }}</span>
              @if (p.mode_paiement) {
                <span><mat-icon>account_balance_wallet</mat-icon> {{ modeLabel(p.mode_paiement) }}</span>
              }
              <span class="bea-apercu__pill" [attr.data-etat]="echeance().etat">
                <mat-icon>schedule</mat-icon> {{ echeance().label }}
              </span>
            </div>
          </div>
          <button type="button" class="bea-apercu__close" (click)="closed.emit()" title="Fermer">
            <mat-icon>close</mat-icon>
          </button>
        </header>

        <div class="bea-apercu__body">
          <div class="bea-apercu__kpis">
            <div class="bea-apercu__kpi bea-apercu__kpi--main">
              <span>Montant</span>
              <strong>{{ p.montant | montant }} <small>{{ devise() }}</small></strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>Facture TTC</span>
              <strong>{{ (facture()?.montant_ttc ?? 0) | montant }} <small>{{ devise() }}</small></strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>Reste sur facture</span>
              <strong>{{ reste() | montant }} <small>{{ devise() }}</small></strong>
            </div>
            <div class="bea-apercu__kpi">
              <span>Facture réglée</span>
              <strong>{{ avancement() }} %</strong>
              <div class="bea-apercu__bar"><i [style.width.%]="avancement()"></i></div>
            </div>
          </div>

          <div class="bea-apercu__cards">
            <section class="bea-apercu__card">
              <h3><mat-icon>account_balance_wallet</mat-icon> Règlement</h3>
              <dl>
                <div><dt>Mode de paiement</dt><dd>{{ p.mode_paiement ? modeLabel(p.mode_paiement) : '—' }}</dd></div>
                <div><dt>Réf. paiement</dt><dd>{{ p.reference_paiement || '—' }}</dd></div>
                <div><dt>Date d'échéance</dt><dd>{{ p.date_echeance ? (p.date_echeance | date: 'dd/MM/yyyy') : '—' }}</dd></div>
                <div><dt>Date de paiement</dt><dd>{{ p.date_paiement ? (p.date_paiement | date: 'dd/MM/yyyy') : '—' }}</dd></div>
              </dl>
            </section>
            <section class="bea-apercu__card">
              <h3><mat-icon>receipt_long</mat-icon> Facture</h3>
              <dl>
                <div><dt>Référence</dt><dd>
                  <button type="button" class="bea-apercu__ref-btn" (click)="factureOuverte.set(true)">
                    <code>{{ facture()?.reference || '—' }}</code>
                  </button>
                </dd></div>
                <div><dt>N° fournisseur</dt><dd>{{ facture()?.numero_fournisseur || '—' }}</dd></div>
                <div class="bea-apercu__wide"><dt>Fournisseur</dt><dd>{{ bon()?.fournisseur_raison_sociale || '—' }}</dd></div>
                <div><dt>Date de facture</dt><dd>{{ facture()?.date_facture ? (facture()!.date_facture | date: 'dd/MM/yyyy') : '—' }}</dd></div>
                <div><dt>Bon de commande</dt><dd><code>{{ bon()?.reference || '—' }}</code></dd></div>
              </dl>
            </section>
          </div>

          <section class="bea-apercu__card">
            <h3><mat-icon>history</mat-icon> Paiements de la facture <em>{{ autres().length }}</em></h3>
            @if (autres().length) {
              <ul class="bea-apercu__links">
                @for (o of autres(); track o.id) {
                  <li [class.bea-apercu__links-current]="o.id === p.id">
                    <code>{{ o.reference }}</code>
                    <span>{{ o.montant | montant }} {{ devise() }}</span>
                    <span class="muted">{{ o.date_paiement ? (o.date_paiement | date: 'dd/MM/yyyy') : (o.date_echeance ? 'éch. ' + (o.date_echeance | date: 'dd/MM/yyyy') : '') }}</span>
                    <span class="bea-ach__badge" [attr.data-statut]="o.statut">{{ statutLabel(o.statut) }}</span>
                  </li>
                }
              </ul>
            } @else {
              <p class="bea-apercu__empty">Aucun autre paiement.</p>
            }
          </section>

          @if (p.observation) {
            <p class="bea-apercu__note"><mat-icon>chat_bubble_outline</mat-icon><span>{{ p.observation }}</span></p>
          }
          <p class="bea-apercu__hint"><mat-icon>info</mat-icon> Suivi interne uniquement : aucun virement ni écriture comptable n'est émis.</p>
        </div>

        <footer class="bea-apercu__foot">
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="factureOuverte.set(true)">
            <mat-icon>receipt_long</mat-icon> Voir la facture
          </button>
          <span class="bea-apercu__spacer"></span>
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closed.emit()">Fermer</button>
          <button type="button" class="bea-ach__btn" (click)="modifier(p.id)"><mat-icon>edit</mat-icon> Modifier</button>
        </footer>
      } @else {
        <div class="bea-apercu__loading">
          <mat-icon>{{ erreur() ? 'error_outline' : 'hourglass_empty' }}</mat-icon>
          <p>{{ erreur() || 'Chargement du paiement…' }}</p>
          @if (erreur()) {
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closed.emit()">Fermer</button>
          }
        </div>
      }
    </div>

    @if (factureOuverte() && paiement(); as p) {
      <bea-achats-facture-apercu [factureId]="p.facture_id" (closed)="factureOuverte.set(false)" />
    }
  `,
})
export class AchatsPaiementApercuComponent implements OnInit {
  readonly paiementId = input.required<string>();
  readonly closed = output<void>();

  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly paiement = signal<PaiementApercu | null>(null);
  readonly facture = signal<FactureApercu | null>(null);
  readonly bon = signal<BonApercu | null>(null);
  readonly autres = signal<PaiementApercu[]>([]);
  readonly erreur = signal('');
  readonly factureOuverte = signal(false);

  readonly devise = computed(() => this.facture()?.devise || 'MRU');
  readonly reste = computed(() => Math.max(0, (Number(this.facture()?.montant_ttc) || 0) - totalPaye(this.autres())));
  readonly avancement = computed(() => {
    const ttc = Number(this.facture()?.montant_ttc) || 0;
    return ttc ? Math.min(100, Math.round((totalPaye(this.autres()) / ttc) * 100)) : 0;
  });
  readonly echeance = computed(() => {
    const p = this.paiement();
    return echeanceVue(p?.date_echeance, p?.statut === 'PAYE');
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.factureOuverte()) return;
    this.closed.emit();
  }

  ngOnInit(): void {
    this.api.get<PaiementApercu>(`/mg/achats/paiements/${this.paiementId()}`).subscribe({
      next: (p) => {
        this.paiement.set(p);
        this.api.get<FactureApercu>(`/mg/achats/factures/${p.facture_id}`).subscribe({
          next: (f) => {
            this.facture.set(f);
            this.api.get<BonApercu>(`/mg/achats/bons/${f.bon_id}`).subscribe({ next: (b) => this.bon.set(b) });
          },
        });
        this.api.get<PaiementApercu[]>('/mg/achats/paiements', { facture_id: p.facture_id }).subscribe({
          next: (rows) => this.autres.set(rows.filter((o) => o.facture_id === p.facture_id)),
        });
      },
      error: () => this.erreur.set('Paiement introuvable.'),
    });
  }

  statutLabel(s: string): string {
    return statutAchatLabel(s);
  }

  modeLabel(m: string): string {
    return MODE_PAIEMENT_LABELS[m] ?? m;
  }

  modifier(id: string): void {
    this.closed.emit();
    void this.router.navigateByUrl(`/achats-appro/paiements/${id}`);
  }
}
