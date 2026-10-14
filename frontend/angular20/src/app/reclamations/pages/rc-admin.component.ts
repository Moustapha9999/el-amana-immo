import { ChangeDetectionStrategy, Component, OnInit, computed, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { Capacite } from '../reclamations.models';
import { ReclamationsStore } from '../reclamations.service';

const CAPS: ReadonlyArray<{ code: Capacite; libelle: string }> = [
  { code: 'voir', libelle: 'Consulter les dossiers' },
  { code: 'tout_voir', libelle: 'Périmètre : tous les dossiers' },
  { code: 'creer', libelle: 'Enregistrer une réclamation' },
  { code: 'modifier', libelle: 'Corriger une fiche' },
  { code: 'qualifier', libelle: 'Qualifier' },
  { code: 'affecter', libelle: 'Transmettre au service' },
  { code: 'traiter', libelle: 'Traiter et retourner' },
  { code: 'examiner_retour', libelle: 'Examiner le retour' },
  { code: 'envoyer_reponse', libelle: 'Enregistrer la réponse envoyée' },
  { code: 'refuser', libelle: 'Rejeter' },
  { code: 'annuler', libelle: 'Annuler' },
  { code: 'cloturer', libelle: 'Clôturer (Service Réclamations central)' },
  { code: 'rouvrir', libelle: 'Rouvrir' },
  { code: 'archiver', libelle: 'Archiver' },
  { code: 'referentiels_gerer', libelle: 'Gérer les référentiels' },
  { code: 'unites_gerer', libelle: 'Gérer les unités' },
  { code: 'reporting_exporter', libelle: 'Exporter Excel' },
  { code: 'admin', libelle: 'Administration du module' },
];

/** Synthèse d’administration : droits effectifs. Les grants se gèrent dans CORE ADMIN. */
@Component({
  selector: 'bea-rc-admin',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, ReclamationsUiComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Administration</h1>
          <p class="bea-ct-head__sub">Les profils et grants se gèrent dans CORE ADMIN. Cette page affiche vos droits effectifs dans le module.</p>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reclamations/parametres"><mat-icon>tune</mat-icon> Paramètres</a>
        </div>
      </header>

      @if (store.config(); as c) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Votre accès</h2></div>
          <dl class="bea-rc-dl">
            <dt>Utilisateur</dt><dd>{{ c.utilisateur }}</dd>
            <dt>Périmètre</dt><dd>{{ perimetre() }}</dd>
            <dt>Membre du SR</dt><dd>{{ c.acces.membre_service_central ? 'Oui' : 'Non' }}</dd>
            <dt>Unités</dt><dd>{{ c.acces.unites.length ? c.acces.unites.length + ' unité(s)' : '—' }}</dd>
          </dl>
        </section>
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Capacités</h2></div>
          <ul class="bea-rc-caps">
            @for (p of CAPS; track p.code) {
              <li [class.is-off]="!store.cap(p.code)">
                <mat-icon>{{ store.cap(p.code) ? 'check_circle' : 'cancel' }}</mat-icon>
                {{ p.libelle }}
              </li>
            }
          </ul>
        </section>
      } @else {
        <p class="bea-rc-pad bea-rc-muted">Chargement…</p>
      }
    </section>
  `,
})
export class RcAdminComponent implements OnInit {
  readonly store = inject(ReclamationsStore);
  readonly CAPS = CAPS;
  readonly perimetre = computed(() => {
    const p = this.store.config()?.acces.perimetre;
    if (p === 'TOUS') return 'Tous les dossiers';
    if (p === 'UNITES') return 'Vos unités';
    if (p === 'PERSONNEL') return 'Vos saisies';
    return '—';
  });

  ngOnInit(): void {
    this.store.charger();
  }
}
