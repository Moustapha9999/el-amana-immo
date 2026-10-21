import { JsonPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  consoleRequete,
  formatOctets,
  IntegrationConsoleOperation,
  IntegrationConsoleOperations,
  IntegrationConsoleResultat,
  IntegrationErreur,
  integrationErreur,
  PERMISSION_STUDIO,
} from './core-admin-integrations.models';
import { CoreAdminIntegrationsService } from './core-admin-integrations.service';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

@Component({
  selector: 'bea-core-admin-integrations-console',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [JsonPipe, RouterLink, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Console de test — lecture seule</h1>
          <p>
            Exécute une opération GET interne inscrite sur la liste d'autorisation, avec votre propre session et vos propres
            permissions. Aucune URL libre, aucune méthode d'écriture.
          </p>
        </div>
      </header>

      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement des opérations autorisées…</p>
      } @else if (erreur(); as e) {
        @if (e.accesRefuse) {
          <div class="bea-admin-panel">
            <h2>Accès refusé</h2>
            <p class="bea-admin-panel__hint">
              Session BEA DIGITAL (Login 1) et permission <code>{{ permissionStudio }}</code> requises.
            </p>
          </div>
        } @else {
          <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e.message }}</p></div>
          <button type="button" class="bea-admin-btn" (click)="charger()">Réessayer</button>
        }
      } @else if (catalogue(); as cat) {
        <div class="bea-integ-notice" role="note">
          <bea-admin-icon name="dns" />
          <div>
            <p><strong>Environnement cible : {{ cat.environnement }}</strong> — les appels portent sur les données réelles de cet environnement.</p>
            <ul>
              <li>Méthodes : {{ cat.limites.methodes.join(', ') }} uniquement.</li>
              <li>Réponse limitée à {{ formatOctets(cat.limites.taille_max_octets) }} ; au-delà, le corps n'est pas affiché.</li>
              <li>Délai maximal : {{ cat.limites.delai_max_secondes }} s.</li>
              <li>Les champs sensibles (secrets, jetons, coordonnées, identifiants personnels) sont masqués ; les corps ne sont pas conservés.</li>
            </ul>
            <p class="bea-integ-muted">{{ cat.avertissement }}</p>
          </div>
        </div>

        @if (cat.items.length === 0) {
          <div class="bea-admin-panel"><p class="bea-admin-panel__empty">Aucune opération n'est actuellement admissible à la console.</p></div>
        } @else {
          <div class="bea-admin-panel bea-integ-section">
            <label class="bea-admin-field bea-integ-section">
              <span>Opération</span>
              <select [value]="selection()" (change)="choisir($any($event.target).value)">
                <option value="">— Choisir une opération —</option>
                @for (op of cat.items; track op.operation_id) {
                  <option [value]="op.operation_id">{{ op.methode }} {{ op.chemin }} — {{ op.nom }}</option>
                }
              </select>
            </label>

            @if (operation(); as op) {
              <dl class="bea-admin-dl bea-integ-section">
                <div><dt>Chemin</dt><dd><span class="bea-integ-method" [attr.data-m]="op.methode">{{ op.methode }}</span> <span class="bea-integ-path">{{ op.chemin }}</span></dd></div>
                <div><dt>Permissions</dt><dd>@for (p of op.permissions; track p) {<code>{{ p }}</code>&nbsp;}</dd></div>
                <div><dt>Admise car</dt><dd>{{ op.justification }}</dd></div>
                <div><dt>Fiche</dt><dd><a class="bea-admin-table__link" [routerLink]="['/admin/integrations/catalogue', op.operation_id]">{{ op.operation_id }}</a></dd></div>
              </dl>

              @if (op.parametres.length) {
                <div class="bea-integ-params">
                  @for (p of op.parametres; track p.emplacement + p.nom) {
                    <label class="bea-admin-field">
                      <span>{{ p.nom }} ({{ p.emplacement }}){{ p.requis ? ' *' : '' }}</span>
                      @if (p.valeurs.length) {
                        <select [value]="valeurs()[p.nom] ?? ''" (change)="saisir(p.nom, $any($event.target).value)">
                          <option value="">—</option>
                          @for (v of p.valeurs; track v) {
                            <option [value]="v">{{ v }}</option>
                          }
                        </select>
                      } @else {
                        <input
                          type="text"
                          maxlength="200"
                          [value]="valeurs()[p.nom] ?? ''"
                          [placeholder]="p.defaut !== null && p.defaut !== undefined ? 'défaut : ' + p.defaut : p.type"
                          (input)="saisir(p.nom, $any($event.target).value)"
                        />
                      }
                    </label>
                  }
                </div>
              } @else {
                <p class="bea-integ-muted">Cette opération n'accepte aucun paramètre.</p>
              }

              <button type="button" class="bea-admin-btn" [disabled]="busy() || manquants().length > 0" (click)="executer(op)">
                <bea-admin-icon name="play_arrow" /> Exécuter
              </button>
              @if (manquants().length) {
                <span class="bea-integ-muted"> Paramètre(s) requis : {{ manquants().join(', ') }}</span>
              }
            }
          </div>

          @if (refus(); as r) {
            <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ r }}</p></div>
          }

          @if (resultat(); as res) {
            <div class="bea-admin-panel bea-integ-section">
              <h2>Résultat</h2>
              <dl class="bea-admin-dl bea-integ-section">
                <div><dt>Statut HTTP</dt><dd><span [class]="'bea-badge ' + (res.statut_http < 400 ? 'bea-badge--actif' : 'bea-badge--inactif')">{{ res.statut_http }}</span></dd></div>
                <div><dt>Durée</dt><dd>{{ res.duree_ms }} ms</dd></div>
                <div><dt>Taille</dt><dd>{{ formatOctets(res.taille_octets) }}{{ res.tronquee ? ' — au-delà de la limite' : '' }}</dd></div>
                <div><dt>Champs masqués</dt><dd>{{ res.champs_masques }}</dd></div>
                <div><dt>Environnement</dt><dd>{{ res.environnement }}</dd></div>
                @if (res.request_id) {
                  <div><dt>Référence</dt><dd><code>{{ res.request_id }}</code></dd></div>
                }
              </dl>
              @if (res.message) {
                <p class="bea-integ-muted">{{ res.message }}</p>
              }
              @if (res.corps !== null && res.corps !== undefined) {
                <pre class="bea-integ-pre">{{ res.corps | json }}</pre>
              }
            </div>
          }
        }
      }
    </section>
  `,
})
export class CoreAdminIntegrationsConsoleComponent implements OnInit {
  private readonly studio = inject(CoreAdminIntegrationsService);
  private readonly route = inject(ActivatedRoute);
  private readonly feedback = inject(FeedbackService);

  readonly permissionStudio = PERMISSION_STUDIO;
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly erreur = signal<IntegrationErreur | null>(null);
  readonly catalogue = signal<IntegrationConsoleOperations | null>(null);
  readonly selection = signal('');
  readonly valeurs = signal<Partial<Record<string, string>>>({});
  readonly resultat = signal<IntegrationConsoleResultat | null>(null);
  readonly refus = signal('');

  readonly operation = computed<IntegrationConsoleOperation | null>(
    () => this.catalogue()?.items.find((op) => op.operation_id === this.selection()) ?? null,
  );
  readonly manquants = computed(() => {
    const op = this.operation();
    if (!op) return [];
    const v = this.valeurs();
    return op.parametres.filter((p) => p.requis && !(v[p.nom] ?? '').trim()).map((p) => p.nom);
  });

  readonly formatOctets = formatOctets;

  ngOnInit(): void {
    this.charger();
  }

  charger(): void {
    this.loading.set(true);
    this.erreur.set(null);
    this.studio.operationsConsole().subscribe({
      next: (data) => {
        this.catalogue.set(data);
        this.loading.set(false);
        const demande = this.route.snapshot.queryParamMap.get('operation');
        if (demande && data.items.some((op) => op.operation_id === demande)) {
          this.choisir(demande);
        }
      },
      error: (err) => {
        this.erreur.set(integrationErreur(err, 'Impossible de charger les opérations de la console.'));
        this.loading.set(false);
      },
    });
  }

  choisir(operationId: string): void {
    this.selection.set(operationId);
    this.valeurs.set({});
    this.resultat.set(null);
    this.refus.set('');
  }

  saisir(nom: string, valeur: string): void {
    this.valeurs.update((v) => ({ ...v, [nom]: valeur }));
  }

  executer(op: IntegrationConsoleOperation): void {
    this.resultat.set(null);
    this.refus.set('');
    this.feedback
      .run(() => this.studio.executer(consoleRequete(op, this.valeurs())), {
        busy: this.busy,
        loading: 'Exécution en cours…',
        success: (r) => ({ title: 'Exécution terminée', details: [{ label: 'Statut HTTP', value: String(r.statut_http) }] }),
        errorTitle: "Exécution refusée ou en échec",
        retry: false,
        onError: (info) => this.refus.set(info.message),
      })
      .subscribe((r) => this.resultat.set(r));
  }
}
