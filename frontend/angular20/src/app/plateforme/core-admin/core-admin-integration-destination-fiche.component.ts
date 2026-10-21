import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  DestinationFiche,
  DestinationStatut,
  destinationStatutLabel,
  destinationStatutTone,
  ExecutionResume,
  executionStatutLabel,
  executionStatutTone,
  integrationDestinationsPermissions,
  integrationStudioPermissions,
  integrationTestsPermissions,
  TRANSITIONS_DESTINATION,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionService } from './core-admin-integration-execution.service';
import { ACCES_REFUSE_DEST } from './core-admin-integration-destinations.component';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { IntegrationSuppressionService, squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

@Component({
  selector: 'bea-core-admin-integration-destination-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      @if (chargement()) {
        ${squelette('Chargement de la destination…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_DEST}
      } @else if (erreur(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
      } @else if (fiche(); as f) {
        <header class="bea-admin-dash__head bea-admin-users__head">
          <div>
            <p class="bea-admin-kicker"><a routerLink="/admin/integrations/destinations">Destinations TEST</a></p>
            <h1>{{ f.nom }}</h1>
            <p><code>{{ f.code }}</code> — {{ f.environnement }} / {{ f.protocole }}</p>
          </div>
          <span [class]="tone(f.statut)">{{ label(f.statut) }}</span>
        </header>
        <div class="bea-integ-notice" role="note"><p>{{ f.avertissement }}</p></div>
        <section class="bea-admin-panel">
          <dl class="bea-admin-dl">
            <div><dt>Fournisseur</dt><dd><a class="bea-admin-table__link" [routerLink]="['/admin/integrations/fournisseurs', f.fournisseur_id]">{{ f.fournisseur_nom }}</a></dd></div>
            <div><dt>Hôtes</dt><dd class="bea-integ-path">{{ f.hotes.join(', ') }}</dd></div>
            <div><dt>Ports</dt><dd>{{ f.ports.join(', ') }}</dd></div>
            <div><dt>Méthodes</dt><dd>{{ f.methodes.join(', ') }}</dd></div>
            <div><dt>Opérations autorisées</dt><dd>{{ f.operations.length ? f.operations.length + ' opération(s) restreinte(s)' : 'Toutes les opérations GET/HEAD actives du fournisseur' }}</dd></div>
            @if (f.motif_statut) {
              <div><dt>Motif du statut</dt><dd>{{ f.motif_statut }}</dd></div>
            }
            <div><dt>Notes</dt><dd>{{ f.notes ?? '—' }}</dd></div>
            @if (f.valide_par) {
              <div><dt>Approuvée</dt><dd>{{ f.valide_le | date: 'dd/MM/yyyy HH:mm' }} — {{ f.valide_par.nom ?? '—' }}</dd></div>
            }
            <div><dt>Créée</dt><dd>{{ f.created_at | date: 'dd/MM/yyyy HH:mm' }} — {{ f.cree_par?.nom ?? '—' }}</dd></div>
          </dl>
        </section>
        <div class="bea-admin-actions">
          @if (droits.manage() && f.modifiable) {
            <a class="bea-admin-btn" [routerLink]="['/admin/integrations/destinations', f.id, 'modifier']">Modifier</a>
          }
          @for (t of transitions(); track t.cible) {
            <button type="button" class="bea-admin-btn" [class.bea-admin-btn--danger]="t.tone === 'danger'" [class.bea-admin-btn--ghost]="t.tone !== 'danger'" [disabled]="action()" (click)="changer(t.cible, t)">{{ t.libelle }}</button>
          }
          @if (droits.manage() && f.statut !== 'archivee') {
            <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="action()" (click)="archiver()">Archiver</button>
            <button type="button" class="bea-admin-btn bea-integ-btn-danger-ghost" [disabled]="action()" (click)="supprimer()"
                    title="Possible seulement si jamais approuvée, ni testée, ni liée à une alerte">
              <bea-admin-icon name="delete" /> Supprimer
            </button>
          }
          @if (f.statut === 'active' && droitsTests.execute()) {
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/tests" [queryParams]="{ fournisseur: f.fournisseur_id, destination: f.id }">Tester</a>
          }
          @if (droitsStudio.supervision()) {
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/supervision" [queryParams]="{ destination_id: f.id, fournisseur_id: f.fournisseur_id, periode: 'tout' }">Supervision</a>
          }
        </div>

        @if (droitsTests.view()) {
          <section class="bea-admin-panel">
            <div class="bea-admin-users__list-head">
              <h2>Derniers tests</h2>
              <a class="bea-admin-table__link" routerLink="/admin/integrations/executions" [queryParams]="{ destination_id: f.id, periode: 'tout' }">Historique complet</a>
            </div>
            @if (tests().length === 0) {
              <p class="bea-admin-panel__empty">Aucune mesure : cette destination n’a jamais été testée.</p>
            } @else {
              <ul>
                @for (e of tests(); track e.id) {
                  <li>
                    <a class="bea-admin-table__link" routerLink="/admin/integrations/executions" [queryParams]="{ execution: e.id, periode: 'tout' }">{{ e.started_at | date: 'dd/MM/yyyy HH:mm' }}</a>
                    — <span [class]="execTone(e.statut)">{{ execLabel(e.statut) }}</span>
                    {{ e.http_status ? '(HTTP ' + e.http_status + ')' : '' }} {{ e.duree_ms != null ? e.duree_ms + ' ms' : '' }}
                  </li>
                }
              </ul>
            }
          </section>
        }

        <section class="bea-admin-panel">
          <h2>Historique des modifications</h2>
          @if (historique() === null) {
            <p class="bea-admin-dash__loading">Chargement…</p>
          } @else if (historique()?.length === 0) {
            <p class="bea-admin-panel__empty">Aucun événement.</p>
          } @else {
            <ul>
              @for (h of historique(); track h.id) {
                <li>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }} — {{ h.libelle }}</li>
              }
            </ul>
          }
        </section>
      }
    </section>
  `,
})
export class CoreAdminIntegrationDestinationFicheComponent implements OnInit {
  private readonly service = inject(CoreAdminIntegrationExecutionService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly suppressions = inject(IntegrationSuppressionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly droits = integrationDestinationsPermissions();
  readonly droitsTests = integrationTestsPermissions();
  readonly droitsStudio = integrationStudioPermissions();
  readonly execLabel = executionStatutLabel;
  readonly execTone = executionStatutTone;
  readonly tests = signal<ExecutionResume[]>([]);
  readonly historique = signal<{ id: string; libelle: string; created_at: string }[] | null>(null);
  readonly fiche = signal<DestinationFiche | null>(null);
  readonly chargement = signal(true);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly action = signal(false);
  readonly label = destinationStatutLabel;
  readonly tone = destinationStatutTone;
  readonly transitions = computed(() => {
    const f = this.fiche();
    if (!f) return [];
    return f.transitions
      .map((cible) => ({ cible, t: TRANSITIONS_DESTINATION[cible] }))
      .filter((x): x is { cible: DestinationStatut; t: NonNullable<(typeof TRANSITIONS_DESTINATION)[DestinationStatut]> } => !!x.t && this.droits[x.t.droit]())
      .map(({ cible, t }) => ({ cible, ...t }));
  });
  private id = '';

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    this.charger();
  }

  charger(): void {
    this.service.ficheDestination(this.id).subscribe({
      next: (f) => {
        this.fiche.set(f);
        this.chargement.set(false);
        this.chargerAnnexes();
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Destination introuvable.'));
        this.chargement.set(false);
      },
    });
  }

  private chargerAnnexes(): void {
    this.service.historiqueDestination(this.id).subscribe({
      next: (h) => this.historique.set(h.items),
      error: () => this.historique.set([]),
    });
    if (this.droitsTests.view()) {
      this.service.executions({ destination_id: this.id }, 1, 5).subscribe({
        next: (r) => this.tests.set(r.items),
        error: () => this.tests.set([]),
      });
    }
  }

  async changer(cible: DestinationStatut, t: { libelle: string; motif: boolean; tone: 'primary' | 'danger' }): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    const consequence = CONSEQUENCES[cible] ? `\n\n${CONSEQUENCES[cible]}` : '';
    const valeurs = await this.dialogs.prompt({
      title: t.libelle,
      message: `${t.libelle} « ${f.nom} » ? Aucun appel réseau n’est déclenché.${consequence}`,
      tone: t.tone,
      confirmLabel: t.libelle,
      fields: t.motif ? [{ key: 'motif', label: 'Motif (obligatoire)' }] : [],
      validate: (v) => (t.motif && (v['motif'] ?? '').trim().length < 3 ? 'Motif obligatoire (3 caractères minimum).' : null),
    });
    if (!valeurs) return;
    const motif = t.motif ? valeurs['motif'].trim() : null;
    this.action.set(true);
    this.service.changerStatutDestination(f.id, f.revision, cible, motif).subscribe({
      next: (n) => { this.fiche.set(n); this.action.set(false); this.chargerAnnexes(); void this.dialogs.success('Statut mis à jour.'); },
      error: (err) => { this.action.set(false); void this.dialogs.error(messageErreur(err, 'Transition refusée.')); },
    });
  }

  async archiver(): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    const r = await this.dialogs.prompt({
      title: 'Archiver',
      message:
        `Archiver « ${f.nom} » ? L’historique est conservé.\n\n` +
        'Conséquences : plus aucun test ne pourra viser cette destination ; elle ne pourra plus être modifiée ni réactivée. ' +
        'Les exécutions passées et les alertes restent consultables.',
      tone: 'danger',
      confirmLabel: 'Archiver',
      fields: [{ key: 'motif', label: 'Motif (obligatoire)' }],
      validate: (v) => ((v['motif'] ?? '').trim().length < 3 ? 'Motif obligatoire (3 caractères minimum).' : null),
    });
    if (!r?.['motif']) return;
    this.action.set(true);
    this.service.archiverDestination(f.id, f.revision, r['motif'].trim()).subscribe({
      next: () => { void this.dialogs.success('Destination archivée.').then(() => this.router.navigate(['/admin/integrations/destinations'])); },
      error: (err) => { this.action.set(false); void this.dialogs.error(messageErreur(err, 'Archivage refusé.')); },
    });
  }

  async supprimer(): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    this.action.set(true);
    const ok = await this.suppressions.supprimer({
      objet: 'la destination',
      nom: f.nom,
      dependances: () => this.service.dependancesDestination(f.id),
      supprimer: (revision) => this.service.supprimerDestination(f.id, revision),
    });
    this.action.set(false);
    if (ok) void this.router.navigate(['/admin/integrations/destinations']);
  }
}

const CONSEQUENCES: Partial<Record<DestinationStatut, string>> = {
  suspendue:
    'Conséquences : tout test vers cette destination est refusé immédiatement par le serveur ; une alerte de suspension est ' +
    'enregistrée ; les exécutions passées restent consultables. La réactivation exige une nouvelle approbation.',
  active: 'Conséquences : des tests manuels GET/HEAD pourront viser ces hôtes, sous les contrôles SSRF, DNS, TLS et de quota.',
  a_valider: 'Conséquences : la destination devra être approuvée avant tout test.',
};
