import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateFr, dateHeureFr } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';
import { ClBcmReglesComponent } from './cl-bcm-regles.component';

export interface SicResume {
  id: string; type: 'PP' | 'PM'; date_reference: string; date_debut: string | null;
  statut: string; statut_libelle: string; ref_version: string | null;
  nb_candidats: number; nb_lignes: number; nb_exclus: number;
  nb_bloquantes: number; nb_a_corriger: number; nb_avertissements: number;
  fichier_nom: string | null; created_at: string | null; generee_le: string | null;
  depot_le: string | null; depot_resultat: string | null; cree_par: string | null;
}

export const BADGE_SIC: Record<string, string> = {
  BROUILLON: 'BROUILLON', A_CORRIGER: 'A_CONTROLER', CONTROLEE: 'CALCULEE',
  VALIDEE_EXPORT: 'VALIDEE', GENEREE: 'CLOTUREE', DEPOSEE: 'ARCHIVEE',
};

export const RESULTATS_DEPOT: Record<string, string> = {
  ACCEPTE: 'Accepté', ACCEPTE_PARTIELLEMENT: 'Accepté partiellement', REJETE: 'Rejeté', EN_ATTENTE: 'En attente',
};

function finMoisPrecedent(): string {
  const d = new Date();
  const fin = new Date(d.getFullYear(), d.getMonth(), 0);
  return `${fin.getFullYear()}-${String(fin.getMonth() + 1).padStart(2, '0')}-${String(fin.getDate()).padStart(2, '0')}`;
}

@Component({
  selector: 'bea-cl-sic',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent, ClBcmReglesComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Déclarations BCM</p>
          <h1>Déclaration SIC</h1>
          <p class="bea-cl-head__sub">Fichiers PP (10 colonnes) et PM (6 colonnes) au format du modèle SIC de la BCM. BEA DIGITAL prépare, contrôle et trace ; le dépôt sur la plateforme SIC reste manuel.</p>
        </div>
        <div style="display:flex;gap:0.45rem;align-items:flex-start">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/referentiels-bcm"><mat-icon>library_books</mat-icon> Référentiels BCM</a>
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/declarations-historique"><mat-icon>history</mat-icon> Historique</a>
        </div>
      </header>
      <p class="bea-cl-note bea-cl-note--info"><mat-icon>info</mat-icon>Aucune donnée n’est inventée : un champ obligatoire absent exclut le client du fichier et le liste dans le rapport d’anomalies. La déclaration ne modifie ni la classification, ni le KYC, ni les comptes.</p>
      @if (store.cap().bcm_preparer) {
        <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); creer()">
          <label>Fichier
            <select [(ngModel)]="type" name="type">
              <option value="PP">PP — personnes physiques</option>
              <option value="PM">PM — personnes morales</option>
            </select>
          </label>
          <label>Date de référence<input type="date" [(ngModel)]="dateReference" name="date_reference" required /></label>
          <label>Date de début (périmètre « nouveaux clients »)<input type="date" [(ngModel)]="dateDebut" name="date_debut" /></label>
          <div style="display:flex;align-items:end">
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !dateReference"><mat-icon>fact_check</mat-icon> Préparer et contrôler</button>
          </div>
        </form>
      }
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Déclarations SIC</h2>
          <label class="bea-cl-hint" style="display:flex;align-items:center;gap:0.4rem">Fichier
            <select [ngModel]="filtre()" (ngModelChange)="filtre.set($event); charger()" name="filtre">
              <option value="">PP et PM</option>
              <option value="PP">PP</option>
              <option value="PM">PM</option>
            </select>
          </label>
        </div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr>
              <th>Fichier</th><th>Date de référence</th><th>Statut</th><th>Référentiel</th>
              <th style="text-align:right">Candidats</th><th style="text-align:right">Exportés</th><th style="text-align:right">Exclus</th>
              <th>Anomalies</th><th>Créée</th><th>Dépôt</th>
            </tr></thead>
            <tbody>
              @for (r of liste(); track r.id) {
                <tr>
                  <td><a [routerLink]="['/clientele/sic', r.id]"><strong>SIC {{ r.type }}</strong></a></td>
                  <td>{{ dateFr(r.date_reference) }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="badge[r.statut]">{{ r.statut_libelle }}</span></td>
                  <td>{{ r.ref_version ?? '—' }}</td>
                  <td style="text-align:right">{{ r.nb_candidats }}</td>
                  <td style="text-align:right">{{ r.nb_lignes }}</td>
                  <td style="text-align:right">{{ r.nb_exclus }}</td>
                  <td class="bea-cl-hint">{{ r.nb_bloquantes }} bloq. · {{ r.nb_a_corriger }} à corr. · {{ r.nb_avertissements }} avert.</td>
                  <td>{{ dateHeureFr(r.created_at) }}<br /><span class="bea-cl-hint">{{ r.cree_par ?? '—' }}</span></td>
                  <td>{{ r.depot_le ? dateFr(r.depot_le) + ' · ' + resultats[r.depot_resultat ?? ''] : '—' }}</td>
                </tr>
              } @empty {
                <tr><td colspan="10"><div class="bea-cl-empty">Aucune déclaration SIC.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>
      <bea-cl-bcm-regles registre="SIC" />
    </div>
  `,
})
export class ClSicComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  readonly liste = signal<SicResume[]>([]);
  readonly filtre = signal('');
  readonly busy = signal(false);
  readonly dateFr = dateFr;
  readonly dateHeureFr = dateHeureFr;
  readonly badge = BADGE_SIC;
  readonly resultats = RESULTATS_DEPOT;
  type: 'PP' | 'PM' = 'PP';
  dateReference = finMoisPrecedent();
  dateDebut = '';

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    const params: Record<string, string> = this.filtre() ? { type: this.filtre() } : {};
    this.api.get<SicResume[]>(`${CL_BASE}/sic`, params).subscribe({
      next: (d) => this.liste.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Déclarations SIC indisponibles')),
    });
  }

  creer(): void {
    const body = { type: this.type, date_reference: this.dateReference, date_debut: this.dateDebut || null };
    this.feedback.run(() => this.api.post<SicResume>(`${CL_BASE}/sic`, body), {
      busy: this.busy,
      idempotent: true,
      loading: 'Préparation et contrôle des clients…',
      success: (r) => ({
        title: `Déclaration SIC ${r.type} préparée`,
        details: [
          { label: 'Candidats', value: String(r.nb_candidats) },
          { label: 'Exportables', value: String(r.nb_lignes) },
          { label: 'Exclus', value: String(r.nb_exclus) },
        ],
      }),
      errorTitle: 'Préparation impossible',
    }).subscribe((r) => void this.router.navigate(['/clientele/sic', r.id]));
  }
}
