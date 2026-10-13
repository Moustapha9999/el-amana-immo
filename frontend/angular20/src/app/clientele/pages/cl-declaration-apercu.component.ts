import { ChangeDetectionStrategy, Component, HostListener, OnInit, inject, input, output, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClDeclarationCycleService } from '../cl-declaration-cycle.service';
import { CL_BASE, dateFr, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

export interface ApercuDeclaration {
  id: string; annee: number; mois: number; libelle: string;
  date_debut: string; date_fin: string; fin_mois_precedent: string;
  statut: string; moteur_version: string | null; grille_version: string | null;
  calculee_le: string | null; validee_le: string | null;
  desactivee_le: string | null; motif_desactivation: string | null;
  simulation: boolean; bcm_officielle: boolean; commentaire: string | null;
  actions: { exporter: boolean; desactiver: boolean; reactiver: boolean; supprimer: boolean };
  journal: { etape: string; le: string; par: string | null }[];
  synthese: {
    tableaux: number; cellules: number; a_configurer: number;
    controles: number; controles_ok: number; controles_bloquants: number;
  };
}

const ETAPES = ['BROUILLON', 'CALCULEE', 'A_CONTROLER', 'VALIDEE', 'CLOTUREE', 'ARCHIVEE'];

@Component({
  selector: 'bea-cl-declaration-apercu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    <div class="bea-cl-modal" role="presentation" (click)="fermer.emit()">
      <article class="bea-cl-modal__box" role="dialog" aria-modal="true" aria-labelledby="cl-apercu-titre" (click)="$event.stopPropagation()">
        @if (d(); as x) {
          <header class="bea-cl-modal__head">
            <div>
              <p class="bea-cl-modal__kicker">Déclaration BCM · {{ x.annee }}-{{ pad(x.mois) }}</p>
              <h2 id="cl-apercu-titre">{{ x.libelle }}</h2>
              <p class="bea-cl-modal__sub">{{ dateFr(x.date_debut) }} → {{ dateFr(x.date_fin) }} · fin mois précédent {{ dateFr(x.fin_mois_precedent) }}</p>
            </div>
            <div class="bea-cl-modal__head-r">
              <span class="bea-cl-badge" [attr.data-s]="x.statut">{{ x.statut.replaceAll('_', ' ') }}</span>
              <button type="button" class="bea-cl-modal__close" (click)="fermer.emit()" aria-label="Fermer"><mat-icon>close</mat-icon></button>
            </div>
          </header>
          <div class="bea-cl-modal__body">
            @if (x.statut === 'DESACTIVEE') {
              <p class="bea-cl-note bea-cl-note--warn"><mat-icon>pause_circle</mat-icon>
                <span>Désactivée le {{ dateFr(x.desactivee_le) }} — <strong>{{ x.motif_desactivation }}</strong></span></p>
            } @else {
              <ol class="bea-cl-steps bea-cl-steps--mini">
                @for (s of etapes; track s) {
                  <li [class.is-on]="x.statut===s" [class.is-done]="rang(x.statut) > rang(s)">{{ s.replaceAll('_', ' ') }}</li>
                }
              </ol>
            }
            @if (x.simulation) {
              <p class="bea-cl-note"><mat-icon>info</mat-icon>Mois non clos — préparation uniquement.</p>
            }
            <div class="bea-cl-kpis">
              <div><mat-icon>table_chart</mat-icon><strong>{{ x.synthese.tableaux }}</strong><span>tableaux</span></div>
              <div><mat-icon>grid_on</mat-icon><strong>{{ x.synthese.cellules }}</strong><span>cellules</span></div>
              <div [class.is-warn]="x.synthese.a_configurer > 0"><mat-icon>tune</mat-icon><strong>{{ x.synthese.a_configurer }}</strong><span>à configurer</span></div>
              <div [class.is-ok]="x.synthese.controles > 0 && x.synthese.controles_ok === x.synthese.controles"><mat-icon>rule</mat-icon><strong>{{ x.synthese.controles_ok }}/{{ x.synthese.controles }}</strong><span>contrôles OK</span></div>
              <div [class.is-ko]="x.synthese.controles_bloquants > 0"><mat-icon>error</mat-icon><strong>{{ x.synthese.controles_bloquants }}</strong><span>bloquants</span></div>
            </div>
            <div class="bea-cl-modal__cols">
              <section>
                <h3>Informations</h3>
                <dl class="bea-cl-dl">
                  <dt>Période</dt><dd>{{ x.libelle }}</dd>
                  <dt>Statut BCM</dt><dd>{{ x.bcm_officielle ? 'Mois clos (officiel)' : 'Simulation' }}</dd>
                  <dt>Moteur</dt><dd>{{ x.moteur_version ?? '—' }}</dd>
                  <dt>Grille</dt><dd>{{ x.grille_version ?? '—' }}</dd>
                  <dt>Calculée</dt><dd>{{ dateFr(x.calculee_le) }}</dd>
                  <dt>Validée</dt><dd>{{ dateFr(x.validee_le) }}</dd>
                  @if (x.commentaire) { <dt>Commentaire</dt><dd>{{ x.commentaire }}</dd> }
                </dl>
              </section>
              <section>
                <h3>Historique</h3>
                <ol class="bea-cl-timeline">
                  @for (j of x.journal; track $index) {
                    <li><strong>{{ j.etape }}</strong><span>{{ dateFr(j.le) }}{{ j.par ? ' · ' + j.par : '' }}</span></li>
                  } @empty {
                    <li><span>Aucun événement.</span></li>
                  }
                </ol>
              </section>
            </div>
          </div>
          <footer class="bea-cl-modal__foot">
            <div class="bea-cl-modal__foot-l">
              @if (x.actions.supprimer && store.cap().admin) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-cl-btn--danger" (click)="supprimer(x)" [disabled]="busy()"><mat-icon>delete</mat-icon> Supprimer</button>
              }
              @if (x.actions.desactiver && store.cap().bcm_preparer) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="desactiver(x)" [disabled]="busy()"><mat-icon>pause_circle</mat-icon> Désactiver</button>
              }
              @if (x.actions.reactiver && store.cap().bcm_preparer) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reactiver(x)" [disabled]="busy()"><mat-icon>play_circle</mat-icon> Réactiver</button>
              }
            </div>
            <div class="bea-cl-modal__foot-r">
              @if (x.actions.exporter && store.cap().exporter) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter(x, 'xlsx')"><mat-icon>download</mat-icon> Excel</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter(x, 'pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
              }
              <a class="bea-mg__btn bea-mg__btn--primary" [routerLink]="['/clientele/declarations', x.id]"><mat-icon>open_in_new</mat-icon> Ouvrir la déclaration</a>
            </div>
          </footer>
        } @else {
          <div class="bea-cl-result"><mat-icon class="bea-cl-spin">progress_activity</mat-icon><span>Chargement…</span></div>
        }
      </article>
    </div>
  `,
})
export class ClDeclarationApercuComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly cycle = inject(ClDeclarationCycleService);
  readonly store = inject(ClienteleStore);
  readonly declarationId = input.required<string>();
  readonly fermer = output<void>();
  readonly modifiee = output<void>();
  readonly d = signal<ApercuDeclaration | null>(null);
  readonly busy = signal(false);
  readonly dateFr = dateFr;
  readonly etapes = ETAPES;

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.busy() || document.querySelector('.cdk-overlay-container .cdk-overlay-pane')) return;
    this.fermer.emit();
  }

  ngOnInit(): void {
    this.api.get<ApercuDeclaration>(`${CL_BASE}/declarations/${this.declarationId()}`).subscribe({
      next: (d) => this.d.set(d),
      error: (e) => {
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Déclaration indisponible'));
        this.fermer.emit();
      },
    });
  }

  pad(m: number): string {
    return String(m).padStart(2, '0');
  }

  rang(s: string): number {
    return ETAPES.indexOf(s);
  }

  desactiver(x: ApercuDeclaration): void {
    this.cycle.desactiver<ApercuDeclaration>(x, this.busy).subscribe((d) => {
      this.d.set(d);
      this.modifiee.emit();
    });
  }

  reactiver(x: ApercuDeclaration): void {
    this.cycle.reactiver<ApercuDeclaration>(x, this.busy).subscribe((d) => {
      this.d.set(d);
      this.modifiee.emit();
    });
  }

  supprimer(x: ApercuDeclaration): void {
    this.cycle.supprimer(x, this.busy).subscribe(() => {
      this.modifiee.emit();
      this.fermer.emit();
    });
  }

  exporter(x: ApercuDeclaration, format: 'xlsx' | 'pdf'): void {
    this.api.download(`${CL_BASE}/declarations/${x.id}/export.${format}`).subscribe({
      next: (b) => telecharger(b, `declaration-bcm-${x.annee}-${this.pad(x.mois)}.${format}`),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible')),
    });
  }
}
