import { ChangeDetectionStrategy, Component, DestroyRef, HostListener, computed, effect, inject, input, output, signal, untracked, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { MontantPipe, formatMontant, parseMontant } from '../shared/montant.pipe';
import { FactureFormComponent } from './facture-form.component';
import {
  ACTION_LABELS,
  FX_BASE,
  FactureDetail,
  FxDocument,
  FxPaiement,
  TYPE_POINT_LABELS,
  aujourdhui,
  dateFr,
  dateHeureFr,
  fxStatut,
  fxTone,
  joursLabel,
  tailleFichier,
  telechargerBlob,
} from './facturation.models';
import { FacturationStore } from './facturation.store';
import { JalonsComponent } from '../contrats-echeances/shared/detail-drawer.component';

type Onglet = 'details' | 'documents' | 'paiements' | 'historique';

/** Action déclenchée à l'ouverture depuis un menu de ligne ; les règles restent celles de la fiche. */
export type FactureActionInitiale =
  | 'modifier' | 'payer' | 'supprimer' | 'dupliquer' | 'documents' | 'paiements' | 'historique'
  | 'enregistrer' | 'controler' | 'valider' | 'contester' | 'annuler' | 'archiver';

const CONFIRMATIONS: Record<string, { action: 'validation' | 'archivage' | 'enregistrement' | 'soumission'; message: string; hint?: string }> = {
  enregistrer: { action: 'enregistrement', message: 'Marquer cette facture comme reçue ?' },
  controler: { action: 'soumission', message: 'Envoyer cette facture en contrôle ?' },
  valider: { action: 'validation', message: 'Valider cette facture ?', hint: 'Les montants seront figés ; la facture passera « À payer ».' },
  archiver: { action: 'archivage', message: 'Archiver cette facture ?', hint: 'Elle restera consultable dans l’historique.' },
};

/** Fiche facture en panneau latéral : détails, documents (GED), paiements, historique, actions. */
@Component({
  selector: 'bea-fx-facture-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, MontantPipe, FactureFormComponent, JalonsComponent],
  template: `
    <div class="bea-fx-drawer__backdrop" (click)="fermer()"></div>
    <aside class="bea-fx-drawer" role="dialog" aria-modal="true" aria-labelledby="bea-fx-drawer-title">
      @if (f(); as f) {
        <header class="bea-fx-drawer__head">
          <div>
            <p class="bea-ct-view__kicker">
              <span class="bea-ct-badge" [attr.data-tone]="tone(f.statut)">{{ statut(f.statut) }}</span>
              @if (f.statut_paiement) { <span class="bea-ct-badge" [attr.data-tone]="tone(f.statut_paiement)">{{ statut(f.statut_paiement) }}</span> }
              @if (f.etat_echeance === 'EN_RETARD' || f.etat_echeance === 'PROCHE') {
                <span class="bea-ct-badge" [attr.data-tone]="tone(f.etat_echeance)">{{ jours(f.jours_echeance) }}</span>
              }
            </p>
            <h2 id="bea-fx-drawer-title">{{ f.reference }}@if (f.numero_fournisseur) { <small> · n° {{ f.numero_fournisseur }}</small> }</h2>
            <p class="bea-ct-view__sub">{{ f.fournisseur || '—' }}{{ f.point_nom ? ' · ' + f.point_nom : '' }}{{ f.periode_label ? ' · ' + f.periode_label : '' }}</p>
          </div>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
        </header>

        <div class="bea-fx-drawer__kpis">
          <div><span>Montant TTC</span><strong>{{ f.montant_ttc | montant }}</strong><small>{{ f.devise }}</small></div>
          <div><span>À payer</span><strong>{{ f.montant_a_payer | montant }}</strong><small>{{ f.devise }}</small></div>
          <div><span>Payé</span><strong>{{ f.montant_paye | montant }}</strong><small>{{ f.devise }}</small></div>
          <div [attr.data-tone]="f.reste ? 'warn' : 'ok'"><span>Reste</span><strong>{{ f.reste | montant }}</strong><small>{{ f.devise }}</small></div>
        </div>

        <input #fichier type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.doc,.docx,.xls,.xlsx" (change)="choisirFichier($event)" />
        <div class="bea-fx-drawer__actions">
          @if (f.modifiable) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="formOuvert.set(true)"><mat-icon>edit</mat-icon> Modifier</button> }
          @for (a of f.actions; track a) {
            <button type="button" class="bea-mg__btn" [class.bea-mg__btn--primary]="a === 'valider'" [class.bea-mg__btn--ghost]="a !== 'valider'"
              [class.bea-mg__btn--danger]="a === 'annuler'" [disabled]="busy()" (click)="transition(a)">
              <mat-icon>{{ action(a).icon }}</mat-icon> {{ action(a).label }}
            </button>
          }
          @if (f.statut === 'VALIDEE' && f.reste && f.capacites.payment_create) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirPaiement()"><mat-icon>payments</mat-icon> Enregistrer un paiement</button>
          }
          @if (f.capacites.documents_create && f.statut !== 'ARCHIVEE') {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="onglet.set('documents'); fichier.click()"><mat-icon>attach_file</mat-icon> Ajouter un document</button>
          }
          @if (f.capacites.create) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="dupliquer()"><mat-icon>content_copy</mat-icon> Dupliquer</button> }
          @if (f.supprimable) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-mg__btn--danger" [disabled]="busy()" (click)="supprimer()"><mat-icon>delete</mat-icon> Supprimer</button> }
        </div>

        <nav class="bea-ct-tabs bea-fx-drawer__tabs">
          <button type="button" [class.is-on]="onglet() === 'details'" (click)="onglet.set('details')">Détails</button>
          @if (f.capacites.documents_view) { <button type="button" [class.is-on]="onglet() === 'documents'" (click)="onglet.set('documents')">Documents ({{ f.documents.length }})</button> }
          @if (f.capacites.payment_view) { <button type="button" [class.is-on]="onglet() === 'paiements'" (click)="onglet.set('paiements')">Paiements ({{ paiementsActifs().length }})</button> }
          <button type="button" [class.is-on]="onglet() === 'historique'" (click)="onglet.set('historique')">Historique</button>
        </nav>

        <div class="bea-fx-drawer__body">
          @switch (onglet()) {
            @case ('details') {
              @if (f.date_echeance) {
                <bea-jalons [jours]="f.jours_echeance" [termine]="f.statut === 'ANNULEE' ? 'muted' : (f.reste === 0 && f.montant_paye) ? 'ok' : null" />
              }
              <dl class="bea-fx-dl bea-ct-pane">
                <dt>Fournisseur</dt><dd>{{ f.fournisseur || '—' }}</dd>
                <dt>Point de facturation</dt>
                <dd>@if (f.point) { <a class="bea-ct-link" [routerLink]="base + '/points'" [queryParams]="{ point: f.point.id }">{{ f.point.code }} · {{ f.point.nom }}</a> <small>{{ typePoint(f.point.type_point) }}</small> } @else { — }</dd>
                <dt>Agence</dt><dd>{{ f.agence || '—' }}</dd>
                <dt>Réf. fournisseur</dt><dd><code class="bea-mg__code">{{ f.reference_fournisseur || '—' }}</code>@if (f.point?.compteur) { <small> compteur {{ f.point!.compteur }}</small> }</dd>
                <dt>Type</dt><dd>{{ store.typeFacture(f.type_facture) }}</dd>
                <dt>Contrat</dt><dd>@if (f.contrat) { <a class="bea-ct-link" [routerLink]="['/contrats-echeances', f.contrat.id]">{{ f.contrat.reference }}</a> {{ f.contrat.titre }} } @else { — }</dd>
                <dt>Date de facture</dt><dd>{{ date(f.date_facture) }}</dd>
                <dt>Réception</dt><dd>{{ date(f.date_reception) }}</dd>
                <dt>Période</dt><dd>{{ f.periode_label || '—' }}@if (f.periode_debut) { <small> du {{ date(f.periode_debut) }} au {{ date(f.periode_fin) }}</small> }</dd>
                <dt>Échéance</dt><dd>{{ date(f.date_echeance) }}@if (f.jours_echeance !== null) { <small [class.bea-ct-neg]="f.jours_echeance < 0"> {{ jours(f.jours_echeance) }}</small> }</dd>
                <dt>Montant HT</dt><dd>{{ f.montant_ht === null ? 'Non renseigné' : (f.montant_ht | montant) }}</dd>
                <dt>TVA</dt><dd>{{ f.montant_tva === null ? 'Non renseignée' : (f.montant_tva | montant) }}</dd>
                @if (f.autres_taxes) { <dt>Autres taxes</dt><dd>{{ f.autres_taxes | montant }}</dd> }
                @if (f.remise) { <dt>Remise</dt><dd>− {{ f.remise | montant }}</dd> }
                <dt>Saisie par</dt><dd>{{ f.created_by_nom || '—' }} <small>{{ dateHeure(f.created_at) }}</small></dd>
                @if (f.valide_at) { <dt>Validée par</dt><dd>{{ f.valide_by_nom || '—' }} <small>{{ dateHeure(f.valide_at) }}</small></dd> }
                @if (f.motif) { <dt>Motif</dt><dd>{{ f.motif }}</dd> }
                @if (f.observation) { <dt>Observation</dt><dd class="bea-fx-dl__wrap">{{ f.observation }}</dd> }
              </dl>
              @if (f.lignes.length) {
                <h3 class="bea-fx-drawer__h3">Lignes</h3>
                <table class="bea-mg__table bea-ct-table bea-fx-mini">
                  <thead><tr><th>Désignation</th><th class="is-num">Qté</th><th class="is-num">P.U.</th><th class="is-num">Montant</th></tr></thead>
                  <tbody>
                    @for (l of f.lignes; track $index) {
                      <tr><td>{{ l.description }}</td><td class="is-num">{{ l.quantite }} {{ l.unite }}</td><td class="is-num">{{ l.prix_unitaire | montant }}</td><td class="is-num">{{ l.montant | montant }}</td></tr>
                    }
                  </tbody>
                </table>
              }
            }
            @case ('documents') {
              <div class="bea-ct-pane">
                @if (fichierChoisi(); as fc) {
                  <form class="bea-fx-upload" [formGroup]="docForm" (ngSubmit)="televerser()">
                    <p><mat-icon>description</mat-icon> {{ fc.name }} <small>{{ taille(fc.size) }}</small></p>
                    <div class="bea-ct-grid">
                      <label>Type de document
                        <select formControlName="doc_type">
                          @for (t of store.config()?.types_document ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
                        </select>
                      </label>
                      <label>Titre <input formControlName="title" maxlength="255" [placeholder]="fc.name" /></label>
                    </div>
                    <div class="bea-fx-upload__btns">
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fichierChoisi.set(null)">Annuler</button>
                      <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>cloud_upload</mat-icon> {{ busy() ? 'Envoi…' : 'Déposer en GED' }}</button>
                    </div>
                  </form>
                } @else if (f.capacites.documents_create && f.statut !== 'ARCHIVEE') {
                  <button type="button" class="bea-fx-dropzone" (click)="fichier.click()" (dragover)="$event.preventDefault()" (drop)="deposer($event)">
                    <mat-icon>cloud_upload</mat-icon> Glisser un fichier ou cliquer — facture originale, scan, justificatif, preuve de paiement…
                    <small>Facultatif · max {{ store.config()?.ged_taille_max_mo ?? 15 }} Mo · stocké dans la GED centrale</small>
                  </button>
                }
                <ul class="bea-ct-list">
                  @for (d of f.documents; track d.id) {
                    <li class="bea-fx-doc">
                      <mat-icon>{{ icone(d) }}</mat-icon>
                      <span class="bea-fx-doc__main"><strong>{{ d.title }}</strong><small>{{ d.doc_type_label }} · {{ taille(d.size_bytes) }} · {{ d.uploaded_by || '—' }} · {{ dateHeure(d.created_at) }}</small></span>
                      <button type="button" class="bea-mg__icon-btn" title="Aperçu" (click)="apercu(d)"><mat-icon>visibility</mat-icon></button>
                      <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="telecharger(d)"><mat-icon>download</mat-icon></button>
                      @if (f.capacites.documents_delete && f.statut !== 'ARCHIVEE') {
                        <button type="button" class="bea-mg__icon-btn" title="Retirer" (click)="retirerDocument(d)"><mat-icon>delete</mat-icon></button>
                      }
                    </li>
                  } @empty {
                    <li class="bea-ct-dash__none">Aucun document. Les pièces sont facultatives.</li>
                  }
                </ul>
              </div>
            }
            @case ('paiements') {
              <ul class="bea-ct-list bea-ct-pane">
                @for (p of f.paiements; track p.id) {
                  <li class="bea-fx-pay" [class.is-off]="p.statut !== 'PAYE'">
                    <span class="bea-fx-pay__date"><strong>{{ date(p.date_paiement) }}</strong><small>{{ p.reference }}</small></span>
                    <span class="bea-fx-doc__main"><strong>{{ p.montant | montant }} {{ f.devise }}</strong><small>{{ p.mode_paiement || '—' }}{{ p.reference_paiement ? ' · ' + p.reference_paiement : '' }} · {{ p.created_by || '—' }}</small>
                      @if (p.observation) { <small>{{ p.observation }}</small> }</span>
                    <span class="bea-ct-badge" [attr.data-tone]="tone(p.statut)">{{ statut(p.statut) }}</span>
                    @if (p.statut === 'PAYE' && f.statut === 'VALIDEE' && f.capacites.payment_delete) {
                      <button type="button" class="bea-mg__icon-btn" title="Annuler le paiement" (click)="annulerPaiement(p)"><mat-icon>undo</mat-icon></button>
                    }
                  </li>
                } @empty {
                  <li class="bea-ct-dash__none">{{ f.statut === 'VALIDEE' ? 'Aucun paiement enregistré.' : 'Le paiement est possible après validation de la facture.' }}</li>
                }
              </ul>
            }
            @case ('historique') {
              <ol class="bea-fx-timeline bea-ct-pane">
                @for (h of f.historique; track h.id) {
                  <li><span class="bea-fx-timeline__dot"></span><div><strong>{{ h.message }}</strong><small>{{ h.user_nom || 'Système' }} · {{ dateHeure(h.created_at) }}</small></div></li>
                } @empty { <li class="bea-ct-dash__none">Aucun évènement.</li> }
              </ol>
            }
          }
        </div>
      } @else {
        <div class="bea-fx-drawer__skeleton">
          <span class="bea-fx-skel bea-fx-skel--title"></span><span class="bea-fx-skel"></span>
          <div class="bea-fx-drawer__kpis">@for (i of [1, 2, 3, 4]; track i) { <span class="bea-fx-skel bea-fx-skel--box"></span> }</div>
          @for (i of [1, 2, 3, 4, 5, 6]; track i) { <span class="bea-fx-skel"></span> }
        </div>
      }
    </aside>

    @if (formOuvert() && f()) {
      <bea-fx-facture-form [facture]="f()" (saved)="formOuvert.set(false); recharger(true)" (closed)="formOuvert.set(false)" />
    }

    @if (paiementOuvert() && f(); as f) {
      <div class="bea-mg__backdrop bea-fx-over" (click)="fermerPaiement()"></div>
      <form class="bea-mg__modal bea-ct-modal bea-fx-over" role="dialog" aria-modal="true" aria-labelledby="bea-fx-pay-title" [formGroup]="payForm" (ngSubmit)="payer()">
        <header class="bea-ct-modal__head">
          <h2 id="bea-fx-pay-title"><mat-icon>payments</mat-icon> Paiement — {{ f.reference }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerPaiement()"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-ct-grid bea-ct-modal__body">
          <div class="bea-ct-span2 bea-pay-recap">
            <div><span>Montant facture</span><strong>{{ f.montant_a_payer | montant }}</strong></div>
            <div><span>Déjà payé</span><strong>{{ f.montant_paye | montant }}</strong></div>
            <div><span>Ce paiement</span><strong>{{ cePaiement() | montant }}</strong></div>
            <div [attr.data-tone]="resteApres(f) < 0 ? 'danger' : resteApres(f) === 0 ? 'ok' : null"><span>Reste après</span><strong>{{ resteApres(f) | montant }}</strong></div>
          </div>
          @if (resteApres(f) < 0) { <p class="bea-ct-span2 bea-ct-help bea-ct-neg"><mat-icon>error</mat-icon> Le paiement dépasse le reste à payer ({{ f.reste | montant }} {{ f.devise }}).</p> }
          <label>Date de paiement * <input type="date" formControlName="date_paiement" [max]="today" /></label>
          <label>Montant * <input inputmode="decimal" formControlName="montant" /></label>
          <label>Mode
            <select formControlName="mode_paiement">
              <option value="">—</option>
              @for (m of store.config()?.modes_paiement ?? []; track m) { <option [value]="m">{{ m }}</option> }
            </select>
          </label>
          <label>Référence (OV, chèque…) <input formControlName="reference_paiement" maxlength="120" /></label>
          <label class="bea-ct-span2">Justificatif (document de la facture)
            <select formControlName="justificatif_document_id">
              <option value="">— Aucun —</option>
              @for (d of f.documents; track d.id) { <option [value]="d.id">{{ d.title }} ({{ d.doc_type_label }})</option> }
            </select>
          </label>
          <label class="bea-ct-span2">Observation <input formControlName="observation" maxlength="2000" /></label>
        </div>
        <footer class="bea-ct-modal__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerPaiement()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="payForm.invalid || busy() || resteApres(f) < 0"><mat-icon>save</mat-icon> {{ busy() ? 'Enregistrement…' : 'Enregistrer' }}</button>
        </footer>
      </form>
    }

    @if (preview(); as p) {
      <div class="bea-mg__backdrop bea-fx-over" (click)="fermerApercu()"></div>
      <div class="bea-mg__modal bea-mg__modal--lg bea-ct-modal bea-fx-over bea-fx-preview" role="dialog" aria-modal="true" aria-label="Aperçu du document">
        <header class="bea-ct-modal__head">
          <h2><mat-icon>visibility</mat-icon> {{ p.doc.title }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerApercu()"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-fx-preview__body">
          @if (p.kind === 'image') { <img [src]="p.url" [alt]="p.doc.title" /> }
          @else if (p.kind === 'pdf') { <iframe [src]="p.url" title="Aperçu PDF"></iframe> }
          @else { <p class="bea-ct-dash__none">Aperçu indisponible pour ce format. Utilisez « Télécharger ».</p> }
        </div>
      </div>
    }
  `,
})
export class FactureDrawerComponent {
  readonly factureId = input.required<string>();
  readonly actionInitiale = input<FactureActionInitiale | null>(null);
  readonly changed = output<void>();
  readonly closed = output<void>();

  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly sanitizer = inject(DomSanitizer);

  readonly base = FX_BASE;
  readonly today = aujourdhui();
  readonly f = signal<FactureDetail | null>(null);
  readonly onglet = signal<Onglet>('details');
  readonly busy = signal(false);
  readonly formOuvert = signal(false);
  readonly paiementOuvert = signal(false);
  readonly fichierChoisi = signal<File | null>(null);
  readonly preview = signal<{ doc: FxDocument; url: SafeResourceUrl; raw: string; kind: 'pdf' | 'image' | 'autre' } | null>(null);
  private readonly courant = signal<string>('');
  private enAttente: FactureActionInitiale | null = null;
  private readonly formRef = viewChild(FactureFormComponent);

  readonly paiementsActifs = computed(() => (this.f()?.paiements ?? []).filter((p) => p.statut === 'PAYE'));

  readonly payForm = this.fb.group({
    date_paiement: [aujourdhui(), Validators.required],
    montant: ['', Validators.required],
    mode_paiement: [''],
    reference_paiement: [''],
    justificatif_document_id: [''],
    observation: [''],
  });
  readonly docForm = this.fb.group({ doc_type: ['FACTURE_SCANNEE'], title: [''] });

  readonly isDirty = unsavedChanges(() => (this.paiementOuvert() && this.payForm.dirty) || !!this.fichierChoisi(), () => this.payForm);

  constructor() {
    this.store.charger();
    effect(() => {
      const id = this.factureId();
      const action = this.actionInitiale();
      untracked(() => {
        this.courant.set(id);
        this.onglet.set('details');
        this.enAttente = action;
        this.recharger();
      });
    });
    inject(DestroyRef).onDestroy(() => this.revoquerApercu());
  }

  /** Utilisé par la page hôte pour son garde de navigation. */
  dirty(): boolean {
    return this.isDirty() || !!this.formRef()?.isDirty();
  }

  recharger(notifier = false): void {
    const id = this.courant();
    if (!id) return;
    if (!notifier) this.f.set(null);
    this.api.get<FactureDetail>(`/mg/factures/${id}`).subscribe({
      next: (d) => {
        this.f.set(d);
        if (notifier) this.changed.emit();
        const action = this.enAttente;
        this.enAttente = null;
        if (action) this.appliquerActionInitiale(d, action);
      },
      error: (e) => {
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Facture indisponible'));
        this.closed.emit();
      },
    });
  }

  private appliquerActionInitiale(d: FactureDetail, action: FactureActionInitiale): void {
    const refus = (message: string) => this.feedback.warning({ title: 'Action indisponible', message });
    switch (action) {
      case 'modifier':
        if (d.modifiable) this.formOuvert.set(true);
        else refus(`La facture ${d.reference} (${fxStatut(d.statut)}) n'est plus modifiable.`);
        break;
      case 'payer':
        if (d.statut === 'VALIDEE' && d.reste && d.capacites.payment_create) {
          this.onglet.set('paiements');
          this.ouvrirPaiement();
        } else refus(d.statut !== 'VALIDEE' ? 'Le paiement est possible après validation de la facture.' : 'Aucun reste à payer sur cette facture.');
        break;
      case 'supprimer':
        if (d.supprimable) this.supprimer();
        else refus(`La facture ${d.reference} ne peut pas être supprimée : annulez-la plutôt.`);
        break;
      case 'dupliquer':
        this.dupliquer();
        break;
      case 'documents':
      case 'paiements':
      case 'historique':
        this.onglet.set(action);
        break;
      default:
        if (d.actions.includes(action)) this.transition(action);
        else refus(`Action non disponible pour une facture ${fxStatut(d.statut).toLowerCase()}.`);
    }
  }

  private appliquer(d: FactureDetail): void {
    this.f.set(d);
    this.changed.emit();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.preview()) return this.fermerApercu();
    if (this.paiementOuvert()) return this.fermerPaiement();
    if (this.formOuvert()) return;
    this.fermer();
  }

  fermer(): void {
    if (this.busy() || this.formOuvert()) return;
    this.closed.emit();
  }

  transition(action: string): void {
    const f = this.f();
    if (!f) return;
    const url = `/mg/factures/${f.id}/${action}`;
    const success = (d: FactureDetail) => ({ title: this.action(action).label + ' : fait', details: [{ label: 'Facture', value: d.reference }, { label: 'Statut', value: fxStatut(d.statut) }] });
    if (action === 'contester' || action === 'annuler') {
      this.feedback
        .runWithReason((motif) => this.api.post<FactureDetail>(url, { motif }), {
          reason: {
            title: action === 'annuler' ? 'Annuler la facture' : 'Contester la facture',
            message: action === 'annuler'
              ? `La facture ${f.reference} sera annulée (conservée dans l'historique, exclue des totaux).`
              : `La facture ${f.reference} sera marquée contestée auprès du fournisseur.`,
            reasonLabel: 'Motif',
            required: true,
            tone: action === 'annuler' ? 'danger' : 'warn',
            confirmLabel: action === 'annuler' ? 'Annuler la facture' : 'Contester',
          },
          loading: 'Mise à jour…',
          busy: this.busy,
          errorTitle: 'Action refusée',
          success,
        })
        .subscribe((d) => this.appliquer(d));
      return;
    }
    const c = CONFIRMATIONS[action];
    this.feedback
      .run(() => this.api.post<FactureDetail>(url, {}), {
        confirm: c ? { action: c.action, message: c.message, hint: c.hint } : undefined,
        loading: 'Mise à jour…',
        busy: this.busy,
        errorTitle: 'Action refusée',
        success,
      })
      .subscribe((d) => this.appliquer(d));
  }

  dupliquer(): void {
    const f = this.f();
    if (!f) return;
    this.feedback
      .run(() => this.api.post<FactureDetail>(`/mg/factures/${f.id}/dupliquer`, {}), {
        confirm: { action: 'ajout', message: `Créer un brouillon pour la période suivante à partir de ${f.reference} ?`, hint: 'Rattachements repris, montants à saisir depuis la nouvelle facture.' },
        loading: 'Duplication…',
        busy: this.busy,
        idempotent: true,
        errorTitle: 'Duplication impossible',
        success: (d) => ({ title: 'Brouillon créé', details: [{ label: 'Référence', value: d.reference }, { label: 'Période', value: d.periode_label ?? '—' }] }),
      })
      .subscribe((d) => {
        this.courant.set(d.id);
        this.appliquer(d);
        this.formOuvert.set(true);
      });
  }

  supprimer(): void {
    const f = this.f();
    if (!f) return;
    this.feedback
      .runWithReason((motif) => this.api.delete(`/mg/factures/${f.id}?motif=${encodeURIComponent(motif)}`), {
        reason: {
          title: 'Supprimer la facture',
          message: `Supprimer ${f.reference} ? Suppression logique : la trace reste dans l'audit.`,
          reasonLabel: 'Motif',
          required: true,
          tone: 'danger',
          confirmLabel: 'Supprimer',
        },
        loading: 'Suppression…',
        busy: this.busy,
        errorTitle: 'Suppression refusée',
        success: { title: 'Facture supprimée' },
      })
      .subscribe(() => {
        this.changed.emit();
        this.closed.emit();
      });
  }

  ouvrirPaiement(): void {
    const f = this.f();
    if (!f) return;
    this.payForm.reset({ date_paiement: aujourdhui(), montant: f.reste ? String(f.reste) : '', mode_paiement: '', reference_paiement: '', justificatif_document_id: '', observation: '' });
    this.paiementOuvert.set(true);
  }

  fermerPaiement(): void {
    if (this.busy()) return;
    this.paiementOuvert.set(false);
    this.payForm.markAsPristine();
  }

  cePaiement(): number {
    return parseMontant(this.payForm.controls.montant.value ?? '') ?? 0;
  }

  resteApres(f: FactureDetail): number {
    return Math.round(((f.reste ?? 0) - this.cePaiement()) * 100) / 100;
  }

  payer(): void {
    const f = this.f();
    if (!f || this.payForm.invalid) return;
    const v = this.payForm.getRawValue();
    const montant = parseMontant(v.montant);
    if (!montant || montant <= 0) {
      this.feedback.warning({ title: 'Montant invalide', message: 'Saisissez un montant positif.' });
      return;
    }
    const body = {
      date_paiement: v.date_paiement,
      montant,
      mode_paiement: v.mode_paiement || null,
      reference_paiement: v.reference_paiement?.trim() || null,
      justificatif_document_id: v.justificatif_document_id || null,
      observation: v.observation?.trim() || null,
    };
    this.feedback
      .run(() => this.api.post<FactureDetail>(`/mg/factures/${f.id}/paiements`, body), {
        loading: 'Enregistrement du paiement…',
        busy: this.busy,
        idempotent: true,
        errorTitle: 'Paiement refusé',
        errorHint: 'Vos données saisies ont été conservées.',
        success: (d) => ({
          title: 'Paiement enregistré',
          details: [
            { label: 'Montant', value: `${formatMontant(montant)} ${d.devise}` },
            { label: 'Statut', value: fxStatut(d.statut_paiement) },
            { label: 'Reste', value: `${formatMontant(d.reste)} ${d.devise}` },
          ],
        }),
      })
      .subscribe((d) => {
        this.payForm.markAsPristine();
        this.paiementOuvert.set(false);
        this.onglet.set('paiements');
        this.appliquer(d);
      });
  }

  annulerPaiement(p: FxPaiement): void {
    this.feedback
      .runWithReason((motif) => this.api.post<FactureDetail>(`/mg/factures/paiements/${p.id}/annuler`, { motif }), {
        reason: {
          title: 'Annuler le paiement',
          message: `Annuler le paiement ${p.reference} de ${formatMontant(p.montant)} ? Il reste visible, barré, dans l'historique.`,
          reasonLabel: 'Motif',
          required: true,
          tone: 'danger',
          confirmLabel: 'Annuler le paiement',
        },
        loading: 'Annulation…',
        busy: this.busy,
        errorTitle: 'Annulation refusée',
        success: (d) => ({ title: 'Paiement annulé', details: [{ label: 'Statut', value: fxStatut(d.statut_paiement) }] }),
      })
      .subscribe((d) => this.appliquer(d));
  }

  choisirFichier(ev: Event): void {
    const el = ev.target as HTMLInputElement;
    const file = el.files?.[0] ?? null;
    el.value = '';
    this.preparer(file);
  }

  deposer(ev: DragEvent): void {
    ev.preventDefault();
    this.preparer(ev.dataTransfer?.files?.[0] ?? null);
  }

  private preparer(file: File | null): void {
    if (!file) return;
    const max = (this.store.config()?.ged_taille_max_mo ?? 15) * 1024 * 1024;
    if (file.size > max) {
      this.feedback.warning({ title: 'Fichier trop volumineux', message: `Taille maximale : ${this.store.config()?.ged_taille_max_mo ?? 15} Mo.` });
      return;
    }
    const nom = file.name.toLowerCase();
    const type = nom.includes('paiement') || nom.includes('virement') ? 'PREUVE_PAIEMENT' : 'FACTURE_SCANNEE';
    this.docForm.reset({ doc_type: type, title: '' });
    this.fichierChoisi.set(file);
  }

  televerser(): void {
    const f = this.f();
    const file = this.fichierChoisi();
    if (!f || !file) return;
    const v = this.docForm.getRawValue();
    const fields: Record<string, string> = { doc_type: v.doc_type || 'FACTURE_SCANNEE' };
    if (v.title?.trim()) fields['title'] = v.title.trim();
    this.feedback
      .run(() => this.api.upload<FxDocument>(`/mg/factures/${f.id}/documents`, file, fields), {
        loading: 'Dépôt du document en GED…',
        busy: this.busy,
        idempotent: true,
        errorTitle: 'Dépôt refusé',
        success: (d) => ({ title: 'Document ajouté', details: [{ label: 'Fichier', value: d.filename }, { label: 'Type', value: d.doc_type_label ?? '—' }] }),
      })
      .subscribe(() => {
        this.fichierChoisi.set(null);
        this.recharger(true);
      });
  }

  retirerDocument(d: FxDocument): void {
    const f = this.f();
    if (!f) return;
    this.feedback
      .runWithReason((motif) => this.api.delete(`/mg/factures/${f.id}/documents/${d.id}?motif=${encodeURIComponent(motif)}`), {
        reason: { title: 'Retirer le document', message: `Retirer « ${d.title} » ? Il est conservé en corbeille GED.`, reasonLabel: 'Motif', required: true, tone: 'danger', confirmLabel: 'Retirer' },
        loading: 'Retrait…',
        busy: this.busy,
        errorTitle: 'Retrait refusé',
        success: { title: 'Document retiré' },
      })
      .subscribe(() => this.recharger(true));
  }

  apercu(d: FxDocument): void {
    const f = this.f();
    if (!f) return;
    const mime = d.mime_type ?? '';
    const kind = mime.includes('pdf') ? 'pdf' : mime.startsWith('image/') ? 'image' : 'autre';
    if (kind === 'autre') {
      this.preview.set({ doc: d, url: '', raw: '', kind });
      return;
    }
    this.api.download(`/mg/factures/${f.id}/documents/${d.id}/download`, { inline: 'true' }).subscribe({
      next: (blob) => {
        this.revoquerApercu();
        const raw = URL.createObjectURL(blob);
        this.preview.set({ doc: d, url: this.sanitizer.bypassSecurityTrustResourceUrl(raw), raw, kind });
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Aperçu impossible')),
    });
  }

  fermerApercu(): void {
    this.revoquerApercu();
    this.preview.set(null);
  }

  private revoquerApercu(): void {
    const p = this.preview();
    if (p?.raw) URL.revokeObjectURL(p.raw);
  }

  telecharger(d: FxDocument): void {
    const f = this.f();
    if (!f) return;
    this.api.download(`/mg/factures/${f.id}/documents/${d.id}/download`).subscribe({
      next: (blob) => telechargerBlob(blob, d.filename),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Téléchargement impossible')),
    });
  }

  icone(d: FxDocument): string {
    const m = d.mime_type ?? '';
    if (m.includes('pdf')) return 'picture_as_pdf';
    if (m.startsWith('image/')) return 'image';
    if (m.includes('sheet') || m.includes('excel')) return 'table_view';
    return 'description';
  }

  action(code: string): { label: string; icon: string } {
    return ACTION_LABELS[code] ?? { label: code, icon: 'bolt' };
  }

  statut(code: string | null | undefined): string {
    return fxStatut(code);
  }

  tone(code: string | null | undefined): string {
    return fxTone(code);
  }

  typePoint(code: string): string {
    return TYPE_POINT_LABELS[code] ?? code;
  }

  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }

  dateHeure(iso: string | null | undefined): string {
    return iso ? dateHeureFr(iso) : '';
  }

  jours(n: number | null | undefined): string {
    return joursLabel(n);
  }

  taille(n: number): string {
    return tailleFichier(n);
  }
}
