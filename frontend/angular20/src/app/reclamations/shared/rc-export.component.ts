import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { telechargerBlob } from '../reclamations.models';
import { Filtres, ReclamationsService, ReclamationsStore } from '../reclamations.service';

type Format = 'pdf' | 'xlsx';

/** Boutons PDF / Excel de la liste filtrée (mêmes filtres que la page, périmètre serveur). */
@Component({
  selector: 'bea-rc-export',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (store.cap('reporting_exporter')) {
      <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-rc-dl-btn" [disabled]="busy()" (click)="telecharger('pdf')" title="Télécharger la liste en PDF">
        <mat-icon>picture_as_pdf</mat-icon> PDF
      </button>
      <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-rc-dl-btn" [disabled]="busy()" (click)="telecharger('xlsx')" title="Télécharger la liste en Excel">
        <mat-icon>table_view</mat-icon> Excel
      </button>
    }
  `,
})
export class RcExportComponent {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);
  readonly filtres = input<Filtres>({});
  readonly busy = signal(false);

  telecharger(format: Format): void {
    const libelle = format === 'pdf' ? 'PDF' : 'Excel';
    this.feedback
      .run(() => this.rc.exporter(this.filtres(), format), {
        busy: this.busy,
        loading: `Préparation du fichier ${libelle}…`,
        success: () => ({ title: `Export ${libelle} prêt` }),
        errorTitle: 'Export refusé',
        retry: false,
      })
      .subscribe((b) => telechargerBlob(b, `reclamations-${new Date().toISOString().slice(0, 10)}.${format}`));
  }
}
