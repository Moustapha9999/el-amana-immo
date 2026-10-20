import { ChangeDetectionStrategy, Component, ElementRef, inject, input, signal, viewChild } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { n, telecharger } from './clientele.models';
import { ClienteleStore } from './clientele.store';

type Format = 'xlsx' | 'pdf';
type Portee = 'filtre' | 'tout';
interface Apercu { filtre: number; tout: number; max_xlsx: number; max_pdf: number }

/**
 * Boutons Excel / PDF d'une liste du module. Avec ``apercu`` : choix explicite entre les lignes filtrées
 * et tout le périmètre autorisé, nombre de lignes affiché avant génération (côté serveur).
 */
@Component({
  selector: 'bea-cl-export',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (store.cap().exporter) {
      <span class="bea-cl-xbtns">
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrir('xlsx')" [disabled]="busy()"><mat-icon>table_view</mat-icon> Excel</button>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrir('pdf')" [disabled]="busy()"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
      </span>
    }
    <dialog #dlg class="bea-cl-xdlg" [attr.aria-label]="'Export ' + libelle()" (close)="format.set(null)" (click)="$event.target === dlg && fermer()">
    @if (format(); as fmt) {
        <div class="bea-cl-modal__box bea-cl-export__box">
          <header class="bea-cl-modal__head">
            <div>
              <p class="bea-cl-modal__kicker">Export {{ fmt === 'pdf' ? 'PDF' : 'Excel' }}</p>
              <h2>{{ libelle() }}</h2>
              <p class="bea-cl-modal__sub">Le fichier est une sortie : le modifier ne change ni la classe ni l’historique.</p>
            </div>
            <button type="button" class="bea-cl-modal__close" (click)="fermer()" aria-label="Fermer"><mat-icon>close</mat-icon></button>
          </header>
          <div class="bea-cl-modal__body">
            @if (apercuData(); as a) {
              <div class="bea-cl-options" role="radiogroup" aria-label="Lignes à exporter">
                <button type="button" class="bea-cl-option" role="radio" [attr.aria-checked]="portee() === 'filtre'" [class.is-on]="portee() === 'filtre'" [disabled]="!filtresActifs()" (click)="portee.set('filtre')">
                  <mat-icon>filter_alt</mat-icon>
                  <strong>Lignes filtrées · {{ n(a.filtre) }}</strong>
                  <span>{{ filtresActifs() ? 'Correspond aux filtres et à la recherche affichés.' : 'Aucun filtre actif sur la liste.' }}</span>
                </button>
                <button type="button" class="bea-cl-option" role="radio" [attr.aria-checked]="portee() === 'tout'" [class.is-on]="portee() === 'tout'" (click)="portee.set('tout')">
                  <mat-icon>select_all</mat-icon>
                  <strong>Tout le périmètre · {{ n(a.tout) }}</strong>
                  <span>{{ perimetre() }}</span>
                </button>
              </div>
              @let nb = portee() === 'filtre' ? a.filtre : a.tout;
              @let max = fmt === 'pdf' ? a.max_pdf : a.max_xlsx;
              @if (nb > max) {
                <p class="bea-cl-note bea-cl-note--warn">{{ n(nb) }} lignes : l’export {{ fmt === 'pdf' ? 'PDF' : 'Excel' }} est limité à {{ n(max) }} lignes.{{ fmt === 'pdf' ? ' Utilisez l’export Excel ou affinez les filtres.' : ' Affinez les filtres.' }}</p>
              } @else if (nb === 0) {
                <p class="bea-cl-note">Aucune ligne à exporter.</p>
              } @else {
                <p class="bea-cl-hint">{{ n(nb) }} ligne(s) seront exportées{{ fmt === 'pdf' ? ' (paysage, en-têtes répétés, pagination)' : ' (en-têtes filtrables, première ligne figée, onglet de synthèse)' }}.</p>
              }
            } @else {
              <p class="bea-cl-hint"><mat-icon class="bea-cl-spin">progress_activity</mat-icon> Calcul du nombre de lignes…</p>
            }
          </div>
          <footer class="bea-cl-modal__foot">
            <span></span>
            <span class="bea-cl-modal__foot-r">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="generer()" [disabled]="busy() || !exportable()">
                <mat-icon>download</mat-icon> Générer le fichier
              </button>
            </span>
          </footer>
        </div>
    }
    </dialog>
  `,
  styles: `
    .bea-cl-xbtns { display: inline-flex; gap: 0.4rem; flex-wrap: wrap; }
    .bea-cl-xdlg { width: 100%; height: 100%; max-width: none; max-height: none; margin: 0; padding: 1.5rem; border: 0; background: transparent; }
    .bea-cl-xdlg[open] { display: grid; place-items: center; }
    .bea-cl-xdlg::backdrop { background: rgba(15, 23, 42, 0.45); backdrop-filter: blur(2px); }
    .bea-cl-export__box { width: min(40rem, 100%); }
    .bea-cl-option:disabled { opacity: 0.5; cursor: not-allowed; }
  `,
})
export class ClExportComponent {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly n = n;

  /** Chemin sans extension : ``{chemin}.xlsx`` / ``{chemin}.pdf``. */
  readonly chemin = input.required<string>();
  /** Chemin de l'aperçu ``{filtre, tout}`` ; absent = export direct sans choix de portée. */
  readonly apercu = input<string | null>(null);
  readonly params = input<Record<string, string>>({});
  readonly filtresActifs = input(false);
  readonly libelle = input.required<string>();
  readonly perimetre = input('Toutes les lignes que vos droits permettent de consulter.');
  readonly nomFichier = input.required<string>();

  private readonly dlg = viewChild.required<ElementRef<HTMLDialogElement>>('dlg');
  readonly format = signal<Format | null>(null);
  readonly portee = signal<Portee>('tout');
  readonly apercuData = signal<Apercu | null>(null);
  readonly busy = signal(false);

  exportable(): boolean {
    const a = this.apercuData();
    const fmt = this.format();
    if (!a || !fmt) return false;
    const nb = this.portee() === 'filtre' ? a.filtre : a.tout;
    return nb > 0 && nb <= (fmt === 'pdf' ? a.max_pdf : a.max_xlsx);
  }

  ouvrir(fmt: Format): void {
    const apercu = this.apercu();
    if (!apercu) {
      this.telecharger(fmt, null);
      return;
    }
    this.portee.set(this.filtresActifs() ? 'filtre' : 'tout');
    this.apercuData.set(null);
    this.format.set(fmt);
    const dlg = this.dlg().nativeElement;
    if (!dlg.open) dlg.showModal();
    this.api.get<Apercu>(apercu, this.params()).subscribe({
      next: (a) => this.apercuData.set(a),
      error: (e) => {
        this.fermer();
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible'));
      },
    });
  }

  fermer(): void {
    const dlg = this.dlg().nativeElement;
    if (dlg.open) dlg.close();
    this.format.set(null);
  }

  generer(): void {
    const fmt = this.format();
    if (fmt && this.exportable()) this.telecharger(fmt, this.portee());
  }

  private telecharger(fmt: Format, portee: Portee | null): void {
    const jour = new Date().toISOString().slice(0, 10);
    const suffixe = portee ? `-${portee === 'filtre' ? 'filtre' : 'complet'}` : '';
    const params = portee ? { ...this.params(), portee } : this.params();
    this.feedback.run(() => this.api.download(`${this.chemin()}.${fmt}`, params), {
      busy: this.busy,
      loading: `Génération du fichier ${fmt === 'pdf' ? 'PDF' : 'Excel'}…`,
      success: (b) => {
        telecharger(b, `${this.nomFichier()}${suffixe}-${jour}.${fmt}`);
        this.fermer();
        return { title: 'Fichier généré', message: `${this.libelle()} — ${fmt === 'pdf' ? 'PDF' : 'Excel'}` };
      },
      errorTitle: 'Échec de l’export',
    }).subscribe();
  }
}
