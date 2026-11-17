import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { RbcmContextService } from './rbcm-context.service';
import { STATUS_LABELS, periodLabel } from './rbcm.models';

@Component({
  selector: 'bea-rbcm-campaign-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, RouterLink],
  styles: `
    :host { display: block; min-width: 0; margin: 0 0 1.15rem; }
    .bea-rbcm-picker {
      display: flex; flex-wrap: wrap; gap: 0.65rem 0.85rem; align-items: center;
      margin: 0; padding: 0; background: none; border: 0; box-shadow: none;
    }
  `,
  template: `
    <div class="bea-rbcm-picker">
      <mat-icon>calendar_month</mat-icon>
      <strong>SM</strong>
      <label class="bea-mg__field bea-mg__field--grow">
        <select
          [ngModel]="ctx.selectedId()"
          (ngModelChange)="ctx.select($event || null)"
          [disabled]="ctx.loading()"
          aria-label="Sélectionner une SM"
        >
          <option [ngValue]="null">— Sélectionner —</option>
          @for (c of ctx.campaigns(); track c.id) {
            <option [ngValue]="c.id">
              {{ periodLabel(c) }} · {{ STATUS_LABELS[c.status] || c.status }}
            </option>
          }
        </select>
      </label>
      @if (ctx.selected(); as c) {
        <span class="bea-ct-badge" [attr.data-tone]="c.status === 'CLOTUREE' ? 'ok' : null">
          {{ STATUS_LABELS[c.status] || c.status }}
        </span>
        <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/reporting-bcm-sm/campagnes', c.id]">
          Fiche
        </a>
      } @else {
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/campagnes/nouvelle">Créer</a>
      }
    </div>
  `,
})
export class RbcmCampaignPickerComponent implements OnInit {
  readonly ctx = inject(RbcmContextService);
  readonly periodLabel = periodLabel;
  readonly STATUS_LABELS = STATUS_LABELS;

  ngOnInit(): void {
    if (!this.ctx.campaigns().length) this.ctx.loadCampaigns();
  }
}
