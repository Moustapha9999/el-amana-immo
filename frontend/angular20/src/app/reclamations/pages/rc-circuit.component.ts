import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { ColonneCircuit, dateFr, montantFr, tonePriorite, toneStatut } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

/** Pipeline : dossiers ouverts hors archives, une colonne par étape (Réception → Affectation → Traitement → Clôture). */
@Component({
  selector: 'bea-rc-circuit',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, ReclamationsUiComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Pipeline des réclamations</h1>
          <p class="bea-ct-head__sub">{{ total() }} dossier{{ total() > 1 ? 's' : '' }} ouvert{{ total() > 1 ? 's' : '' }} dans votre périmètre, hors archives.</p>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      @if (erreur()) {
        <div class="bea-ct-empty bea-ct-empty--hero"><mat-icon>cloud_off</mat-icon>
          <p>Impossible de charger le circuit.</p>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon> Réessayer</button>
        </div>
      } @else if (colonnes()) {
        <div class="bea-rc-kanban">
          @for (c of colonnes(); track c.etape) {
            <section class="bea-rc-kanban__col">
              <header>
                <h2>{{ c.libelle }}</h2>
                <span>{{ c.items.length }}</span>
              </header>
              <ul>
                @for (d of c.items; track d.id) {
                  <li>
                    <a [routerLink]="['/reclamations/dossiers', d.id]">
                      <strong>{{ d.reference }}</strong>
                      <span>{{ d.objet }}</span>
                      <small>{{ d.client_nom || '—' }} · {{ date(d.date_reclamation ?? d.date_premiere_reception) }}</small>
                      @if (d.nb_operations) { <small>{{ d.nb_operations }} opération{{ d.nb_operations > 1 ? 's' : '' }} · {{ montant(d.montant_total, d.devise) }}</small> }
                      <span class="bea-rc-kanban__badges">
                        <span class="bea-ct-badge" [attr.data-tone]="toneStatut(d.statut)">{{ d.statut_libelle }}</span>
                        @if (d.priorite !== 'NORMALE') { <span class="bea-ct-badge" [attr.data-tone]="tonePriorite(d.priorite)">{{ d.priorite_libelle }}</span> }
                      </span>
                    </a>
                  </li>
                } @empty {
                  <li class="bea-rc-muted">Aucun dossier à cette étape.</li>
                }
              </ul>
            </section>
          }
        </div>
      } @else {
        <p class="bea-rc-pad bea-rc-muted">Chargement du circuit…</p>
      }
    </section>
  `,
})
export class RcCircuitComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);

  readonly toneStatut = toneStatut;
  readonly tonePriorite = tonePriorite;
  readonly colonnes = signal<ColonneCircuit[] | null>(null);
  readonly total = signal(0);
  readonly erreur = signal(false);

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    this.erreur.set(false);
    this.rc.circuit().subscribe({
      next: (r) => {
        this.colonnes.set(r.colonnes);
        this.total.set(r.total);
      },
      error: (e) => {
        this.erreur.set(true);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Circuit indisponible'));
      },
    });
  }

  date(iso: string | null): string {
    return dateFr(iso);
  }

  montant(v: string | null, devise: string): string {
    return montantFr(v, devise);
  }
}
