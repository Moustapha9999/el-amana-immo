import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { IndicateurDelai, Pilotage, dateFr } from '../reclamations.models';

export type ParamsListe = Record<string, string | null>;

const ICONES: Record<string, string> = {
  prise_en_charge: 'move_to_inbox',
  traitement_service: 'engineering',
  reponse_client: 'outgoing_mail',
  cloture: 'task_alt',
};

/** Quatre délais, réouverture et performance des services. Chaque compte ouvre la liste filtrée correspondante. */
@Component({
  selector: 'bea-rc-pilotage',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink],
  styleUrl: './rc-pilotage.component.css',
  template: `
    @let p = pilotage();
    <p class="rcp-periode"><mat-icon>date_range</mat-icon> {{ periodeLibelle() }} — durées en jours calendaires (heures entre parenthèses).</p>
    <div class="rcp-delais">
      @for (d of p.delais; track d.code) {
        <article class="rcp-delai" [style.--i]="$index">
          <header>
            <span class="rcp-delai__ico"><mat-icon>{{ icone(d) }}</mat-icon></span>
            <h3>{{ d.libelle }}</h3>
            <mat-icon class="rcp-info" [title]="d.definition" aria-hidden="false" [attr.aria-label]="d.definition">info</mat-icon>
          </header>
          <a class="rcp-delai__val" routerLink="/reclamations/dossiers" [queryParams]="lien('delai_' + d.code + '_termines')"
             [title]="'Liste des ' + d.termines.n + ' ' + d.unite + '(s) mesuré(s)'">
            @if (d.termines.moyenne_jours === null) { <strong class="is-na">N/A</strong> }
            @else { <strong>{{ d.termines.moyenne_jours }} j</strong><small>({{ d.termines.moyenne_heures }} h)</small> }
          </a>
          <p class="rcp-delai__n">Moyenne sur <b>{{ d.termines.n }}</b> {{ d.unite }}(s) terminé(s)</p>
          <a class="rcp-ligne" routerLink="/reclamations/dossiers" [queryParams]="lien('delai_' + d.code + '_en_cours')">
            <mat-icon>pending</mat-icon> En cours <b>{{ d.en_cours.n }}</b>
            <small>{{ d.en_cours.age_moyen_jours === null ? 'âge N/A' : 'âge moyen ' + d.en_cours.age_moyen_jours + ' j' }}</small>
          </a>
          @if (d.anomalies.n) {
            <a class="rcp-ligne is-warn" routerLink="/reclamations/dossiers" [queryParams]="lien('delai_' + d.code + '_anomalies')"
               [title]="d.anomalies.references.join(', ')">
              <mat-icon>report</mat-icon> {{ d.anomalies.n }} durée(s) négative(s) exclue(s)
            </a>
          }
        </article>
      }
    </div>

    <div class="rcp-bas">
      <article class="rcp-reouv">
        <header><h3><mat-icon>replay</mat-icon> Taux de réouverture</h3></header>
        <strong class="rcp-reouv__taux" [class.is-na]="p.reouverture.taux === null">
          {{ p.reouverture.taux === null ? 'N/A' : p.reouverture.taux + ' %' }}
        </strong>
        <p class="rcp-formule">{{ p.reouverture.formule }}</p>
        <div class="rcp-reouv__liens">
          <a routerLink="/reclamations/dossiers" [queryParams]="lien('reouvertes')"><b>{{ p.reouverture.reouvertes }}</b> réouvert(s)</a>
          <span>÷</span>
          <a routerLink="/reclamations/dossiers" [queryParams]="lien('clotures')"><b>{{ p.reouverture.cloturees }}</b> clôturé(s)</a>
        </div>
        <small class="rcp-note">{{ p.reouverture.nb_reouvertures }} réouverture(s) enregistrée(s) ·
          {{ p.reouverture.dossiers_plusieurs_reouvertures }} dossier(s) réouvert(s) plusieurs fois</small>
      </article>

      <article class="rcp-services">
        <header><h3><mat-icon>account_tree</mat-icon> Performance des services</h3>
          <small>Affectés et retournés : flux de la période · En cours et en retard : stock actuel</small>
        </header>
        <div class="rcp-table">
          <table>
            <thead><tr>
              <th>Service</th><th>Affectés</th><th>En cours</th><th>Retournés</th><th>Délai moyen</th><th>Âge moyen</th><th>En retard</th>
            </tr></thead>
            <tbody>
              @for (s of p.services; track s.unite_id) {
                <tr>
                  <td>{{ s.libelle }}</td>
                  <td><a routerLink="/reclamations/dossiers" [queryParams]="lien('service_affectes', s.unite_id)">{{ s.affectes }}</a></td>
                  <td><a routerLink="/reclamations/dossiers" [queryParams]="lien('service_en_cours', s.unite_id)">{{ s.en_cours }}</a></td>
                  <td><a routerLink="/reclamations/dossiers" [queryParams]="lien('service_retournes', s.unite_id)">{{ s.retournes }}</a></td>
                  <td>{{ s.delai_moyen_jours === null ? 'N/A' : s.delai_moyen_jours + ' j' }}</td>
                  <td>{{ s.age_moyen_jours === null ? 'N/A' : s.age_moyen_jours + ' j' }}</td>
                  <td><a routerLink="/reclamations/dossiers" [queryParams]="lien('service_retard', s.unite_id)" [class.is-ko]="s.en_retard > 0">{{ s.en_retard }}</a></td>
                </tr>
              } @empty {
                <tr><td colspan="7" class="rcp-vide">Aucune affectation à un service sur la période.</td></tr>
              }
            </tbody>
          </table>
        </div>
      </article>
    </div>
  `,
})
export class RcPilotageComponent {
  readonly pilotage = input.required<Pilotage>();
  /** Filtres de la page (agence, période) repris dans les liens vers la liste. */
  readonly filtres = input<ParamsListe>({});

  readonly periodeLibelle = computed(() => {
    const { debut, fin } = this.pilotage().periode;
    if (!debut && !fin) return 'Toute la période';
    if (debut && fin) return `Du ${dateFr(debut)} au ${dateFr(fin)}`;
    return debut ? `Depuis le ${dateFr(debut)}` : `Jusqu’au ${dateFr(fin)}`;
  });

  icone(d: IndicateurDelai): string {
    return ICONES[d.code] ?? 'timer';
  }

  lien(indicateur: string, uniteId: string | null = null): ParamsListe {
    const f = this.filtres();
    return {
      client_agence_id: f['client_agence_id'] ?? null,
      indicateur,
      kpi_debut: this.pilotage().periode.debut,
      kpi_fin: this.pilotage().periode.fin,
      kpi_unite_id: uniteId,
    };
  }
}
