import { DatePipe, JsonPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  AUCUN_APPEL,
  FournisseurFiche,
  integrationFournisseursPermissions,
  mecanismeLabel,
  OperationDetail,
} from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { ACCES_REFUSE_FOURNISSEURS, BANDEAU_AUCUN_APPEL } from './core-admin-integration-fournisseurs.component';
import { operationExigeSecret } from './core-admin-integration-execution.models';
import { IntegrationSuppressionService, squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

@Component({
  selector: 'bea-core-admin-integration-fournisseur-operation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe, JsonPipe, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      @if (chargement()) {
        ${squelette('Chargement de l’opération…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_FOURNISSEURS}
      } @else if (erreur(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        <a class="bea-admin-btn bea-admin-btn--ghost" [routerLink]="['/admin/integrations/fournisseurs', fid]">Retour au fournisseur</a>
      } @else if (op(); as o) {
        <header class="bea-admin-dash__head bea-admin-users__head">
          <div>
            <p class="bea-admin-kicker">
              <a routerLink="/admin/integrations/fournisseurs">Fournisseurs externes</a> ›
              <a [routerLink]="['/admin/integrations/fournisseurs', fid]" [queryParams]="{ onglet: 'operations' }">{{ fournisseur()?.nom ?? 'Fournisseur' }}</a>
            </p>
            <h1>
              <span class="bea-integ-method" [attr.data-m]="o.methode">{{ o.methode }}</span>
              <span class="bea-integ-path">{{ o.chemin }}</span>
            </h1>
            <p>{{ o.nom ?? o.operation_id ?? '—' }}</p>
          </div>
          <div class="bea-admin-users__head-actions">
            <span class="bea-badge">{{ o.origine === 'openapi' ? 'Spécification importée' : 'Configuration manuelle' }}</span>
            @if (o.statut === 'archivee') { <span class="bea-badge bea-badge--inactif">Archivée</span> }
            @if (o.deprecie) { <span class="bea-badge bea-badge--inactif">Dépréciée</span> }
            <span class="bea-integ-pill" [attr.data-tone]="executabilite(o).ok ? 'ok' : 'warn'" [title]="executabilite(o).raison">
              {{ executabilite(o).ok ? 'Testable en TEST' : 'Non testable' }}
            </span>
          </div>
        </header>

        ${BANDEAU_AUCUN_APPEL}

        <section class="bea-admin-panel">
          <h2>Provenance</h2>
          <p>{{ o.source }}</p>
          @if (o.conflit) {
            <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>Conflit : une autre opération (importée ou manuelle) porte la même méthode et le même chemin.</p></div>
          }
          @if (o.description) { <p>{{ o.description }}</p> }
          @if (o.tags.length) { <p class="bea-integ-muted">Tags : {{ o.tags.join(', ') }}</p> }
          @if (o.notes) { <p class="bea-integ-muted">Notes : {{ o.notes }}</p> }
          <p class="bea-integ-muted">
            Créée le {{ o.created_at | date: 'dd/MM/yyyy HH:mm' }} ({{ o.cree_par?.nom ?? '—' }}) — modifiée le {{ o.updated_at | date: 'dd/MM/yyyy HH:mm' }} ({{ o.modifie_par?.nom ?? '—' }})
          </p>
          <p class="bea-integ-muted">Exécution de test : {{ executabilite(o).raison }}</p>
          @if (gerable()) {
            <div class="bea-admin-actions">
              <a class="bea-admin-btn" [routerLink]="['/admin/integrations/fournisseurs', fid, 'operations', o.id, 'modifier']">Modifier</a>
              <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="action()" (click)="archiver()">Archiver</button>
              <button type="button" class="bea-admin-btn bea-integ-btn-danger-ghost" [disabled]="action()" (click)="supprimer()">
                <bea-admin-icon name="delete" /> Supprimer
              </button>
            </div>
          } @else if (o.origine === 'openapi') {
            <p class="bea-integ-muted">
              Opération importée : elle appartient à la version v{{ o.spec_numero }} de la spécification et n'est jamais
              modifiée ni supprimée individuellement. Pour la retirer, importez une nouvelle version sans elle.
            </p>
          }
        </section>

        <section class="bea-admin-panel">
          <h2>Authentification déclarée</h2>
          @for (m of o.mecanismes; track $index) {
            <p>{{ m.nom }} : {{ mecanisme(m) }} @if (m.description) { <span class="bea-integ-muted">— {{ m.description }}</span> }</p>
          } @empty {
            <p class="bea-admin-panel__empty">Aucun mécanisme déclaré.</p>
          }
          <p class="bea-admin-note">Aucun secret n'est stocké : les exemples utilisent des variables d'environnement à renseigner hors de BEA DIGITAL.</p>
        </section>

        <section class="bea-admin-panel">
          <h2>Paramètres</h2>
          @if (o.parametres.length === 0 && o.entetes.length === 0) {
            <p class="bea-admin-panel__empty">Aucun paramètre déclaré.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead><tr><th>Nom</th><th>Emplacement</th><th>Requis</th><th>Type</th><th>Description</th></tr></thead>
                <tbody>
                  @for (p of o.parametres; track p.nom + p.emplacement) {
                    <tr>
                      <td><code>{{ p.nom }}</code> @if (p.deprecie) { <span class="bea-badge bea-badge--inactif">Déprécié</span> }</td>
                      <td>{{ p.emplacement }}</td>
                      <td>{{ p.requis ? 'Oui' : 'Non' }}</td>
                      <td>{{ typeDe(p.schema) }}</td>
                      <td>{{ p.description ?? '—' }}</td>
                    </tr>
                  }
                  @for (h of o.entetes; track h.nom) {
                    <tr>
                      <td><code>{{ h.nom }}</code></td>
                      <td>header</td>
                      <td>{{ h.requis ? 'Oui' : 'Non' }}</td>
                      <td>—</td>
                      <td>{{ h.description ?? '—' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </section>

        <section class="bea-admin-panel">
          <h2>Corps de requête</h2>
          @if (o.corps; as c) {
            <p class="bea-integ-muted">{{ c.requis ? 'Obligatoire' : 'Facultatif' }} @if (c.description) { — {{ c.description }} }</p>
            @for (ct of c.contenus; track ct.type_contenu) {
              <p><code>{{ ct.type_contenu }}</code></p>
              @if (ct.schema) { <pre class="bea-integ-pre">{{ ct.schema | json }}</pre> }
            }
          } @else {
            <p class="bea-admin-panel__empty">Aucun corps déclaré.</p>
          }
        </section>

        <section class="bea-admin-panel">
          <h2>Réponses déclarées</h2>
          @for (r of o.reponses; track r.code) {
            <div class="bea-integ-section">
              <h3>{{ r.code }} @if (r.description) { <span class="bea-integ-muted">— {{ r.description }}</span> }</h3>
              @for (ct of r.contenus; track ct.type_contenu) {
                <p><code>{{ ct.type_contenu }}</code></p>
                @if (ct.schema) { <pre class="bea-integ-pre">{{ ct.schema | json }}</pre> }
              }
            </div>
          } @empty {
            <p class="bea-admin-panel__empty">Aucune réponse déclarée.</p>
          }
        </section>

        <section class="bea-admin-panel">
          <h2>Exemples d'appel — non testés</h2>
          <div class="bea-integ-notice" role="note">
            <bea-admin-icon name="warning" />
            <ul>
              @for (a of o.avertissements; track a) { <li>{{ a }}</li> }
            </ul>
          </div>
          <div class="bea-admin-grid">
            <div>
              <h3>Éléments déclarés</h3>
              <ul>@for (d of o.elements_declares; track d) { <li>{{ d }}</li> } @empty { <li>—</li> }</ul>
            </div>
            <div>
              <h3>Éléments vérifiés</h3>
              <ul>@for (v of o.elements_verifies; track v) { <li>{{ v }}</li> } @empty { <li>Aucun : rien n'a été vérifié auprès du fournisseur.</li> }</ul>
            </div>
          </div>
          @for (ex of o.exemples; track ex.langage) {
            <p><strong>{{ ex.libelle }}</strong> <span class="bea-badge bea-badge--bientot">Non testé</span></p>
            <pre class="bea-integ-pre">{{ ex.code }}</pre>
          }
        </section>
      }
    </section>
  `,
})
export class CoreAdminIntegrationFournisseurOperationComponent implements OnInit {
  private readonly service = inject(CoreAdminIntegrationFournisseursService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly suppressions = inject(IntegrationSuppressionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly droits = integrationFournisseursPermissions();

  readonly chargement = signal(true);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly op = signal<OperationDetail | null>(null);
  readonly fournisseur = signal<FournisseurFiche | null>(null);
  readonly action = signal(false);
  readonly mecanisme = mecanismeLabel;

  fid = '';
  private opId = '';

  ngOnInit(): void {
    this.fid = this.route.snapshot.paramMap.get('id') ?? '';
    this.opId = this.route.snapshot.paramMap.get('opId') ?? '';
    this.service.fiche(this.fid).subscribe({ next: (f) => this.fournisseur.set(f), error: () => this.fournisseur.set(null) });
    this.service.operation(this.fid, this.opId).subscribe({
      next: (o) => {
        this.op.set(o);
        this.chargement.set(false);
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Opération introuvable.'));
        this.chargement.set(false);
      },
    });
  }

  gerable(): boolean {
    const o = this.op();
    return !!o && o.origine === 'manuelle' && o.statut === 'active' && this.droits.manage() && !!this.fournisseur()?.modifiable;
  }

  /** Miroir indicatif des règles serveur d'exécution (le serveur reste seul juge). */
  executabilite(o: OperationDetail): { ok: boolean; raison: string } {
    if (o.statut !== 'active') return { ok: false, raison: 'opération archivée.' };
    if (o.methode !== 'GET' && o.methode !== 'HEAD') return { ok: false, raison: 'seules les méthodes GET et HEAD sont testables.' };
    if (o.origine === 'openapi' || operationExigeSecret(o)) {
      return { ok: false, raison: 'authentification requise ou non précisée — aucun coffre de secrets approuvé.' };
    }
    return { ok: true, raison: 'GET/HEAD sans authentification, via une destination TEST approuvée uniquement.' };
  }

  async supprimer(): Promise<void> {
    const o = this.op();
    if (!o || this.action()) return;
    this.action.set(true);
    const ok = await this.suppressions.supprimer({
      objet: 'l’opération manuelle',
      nom: `${o.methode} ${o.chemin}`,
      dependances: () => this.service.dependancesOperation(this.fid, o.id),
      supprimer: (revision) => this.service.supprimerOperation(this.fid, o.id, revision),
    });
    this.action.set(false);
    if (ok) void this.router.navigate(['/admin/integrations/fournisseurs', this.fid], { queryParams: { onglet: 'operations' } });
  }

  typeDe(schema: unknown): string {
    if (schema && typeof schema === 'object' && 'type' in schema) return String((schema as { type: unknown }).type);
    return '—';
  }

  async archiver(): Promise<void> {
    const o = this.op();
    if (!o || this.action()) return;
    const ok = await this.dialogs.confirm({
      title: 'Archiver l’opération',
      message: `Archiver ${o.methode} ${o.chemin} ? Elle reste consultable mais n'apparaît plus parmi les opérations courantes.`,
      confirmLabel: 'Archiver',
      tone: 'danger',
    });
    if (!ok) return;
    this.action.set(true);
    this.service.archiverOperation(this.fid, o.id, o.revision).subscribe({
      next: (r) => {
        this.op.set(r);
        this.action.set(false);
        void this.dialogs.success(`Opération archivée. ${AUCUN_APPEL}`);
      },
      error: (err) => {
        this.action.set(false);
        void this.dialogs.error(messageErreur(err, 'Archivage impossible.'));
      },
    });
  }
}
