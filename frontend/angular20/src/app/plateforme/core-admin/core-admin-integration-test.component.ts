import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, Input, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, FormControl, FormRecord, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  DestinationResume,
  ExecutionDetail,
  TestApercu,
  executionFamilleLabel,
  executionStatutLabel,
  executionStatutTone,
  integrationTestsPermissions,
  messageTest,
  operationExigeSecret,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionService } from './core-admin-integration-execution.service';
import { OperationResume } from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { EtatVisuel, etatExecution, LIBELLES_ETAT } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

@Component({
  selector: 'bea-core-admin-integration-test',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DatePipe],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-panel">
      <h2>Test contrôlé (TEST)</h2>
      <p class="bea-admin-panel__hint">
        L’appel n’est envoyé qu’après aperçu puis confirmation. L’URL est construite côté serveur à partir d’une destination approuvée.
        Aucun secret n’est transmis. Seules les méthodes GET et HEAD sont testables ; aucune redirection n’est suivie.
      </p>
      <ol class="bea-integ-stepper" aria-label="Étapes du test">
        @for (e of etapes; track e; let i = $index) {
          <li [attr.data-etat]="etatEtape(i + 1)" [attr.aria-current]="etapeCourante() === i + 1 ? 'step' : null">{{ e }}</li>
        }
      </ol>
      @if (!droits.execute()) {
        <div class="bea-integ-notice" role="note"><p>Consultation seulement : la permission <code>core.admin.integrations.tests.execute</code> est absente.</p></div>
      }
      @if (chargement()) {
        <p class="bea-admin-dash__loading" role="status">Chargement des opérations et destinations…</p>
      } @else if (erreurChargement(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
      } @else {
        @if (operations().length === 0) {
          <div class="bea-integ-notice bea-integ-notice--info" role="note">
            <p>Aucune opération GET ou HEAD active pour ce fournisseur. Les autres méthodes ne sont jamais testables.</p>
          </div>
        }
        @if (destinations().length === 0) {
          <div class="bea-integ-notice bea-integ-notice--info" role="note">
            <p>
              Aucune destination TEST approuvée pour ce fournisseur.
              <a class="bea-admin-table__link" routerLink="/admin/integrations/destinations" [queryParams]="{ fournisseur: fournisseurId }">Gérer les destinations</a>
            </p>
          </div>
        }
        <form class="bea-admin-form" [formGroup]="form" (ngSubmit)="preparer()">
          <h3 class="bea-integ-muted">1. Sélection</h3>
          <div class="bea-admin-grid">
            <label class="bea-admin-field">
              <span>Opération GET/HEAD</span>
              <select formControlName="operation_id" [attr.aria-describedby]="secretRequis() ? 'integ-test-secret' : null">
                <option value="">Choisir…</option>
                @for (o of operations(); track o.id) {
                  <option [value]="o.id">{{ o.methode }} {{ o.chemin }}{{ o.nom ? ' — ' + o.nom : '' }}</option>
                }
              </select>
            </label>
            <label class="bea-admin-field">
              <span>Destination approuvée</span>
              <select formControlName="destination_id">
                <option value="">Choisir…</option>
                @for (d of destinations(); track d.id) {
                  <option [value]="d.id">{{ d.nom }} — {{ d.hotes.join(', ') }}</option>
                }
              </select>
            </label>
          </div>
          @if (chargementOperation()) {
            <p class="bea-admin-dash__loading">Lecture de l’opération…</p>
          }
          @if (secretRequis()) {
            <div id="integ-test-secret" class="bea-integ-notice bea-integ-notice--danger" role="alert">
              <p>
                Test bloqué : cette opération déclare une authentification (ou ne précise pas qu’elle n’en exige aucune).
                Aucun coffre de secrets n’est approuvé ; aucun secret ne peut être saisi ni transmis.
                Seules les opérations configurées avec le mécanisme « aucun » sont testables.
              </p>
            </div>
          }
          @if (paramsPath().length || paramsQuery().length) {
            <h3 class="bea-integ-muted">2. Paramètres</h3>
            <div class="bea-integ-params">
              @for (p of paramsPath(); track p) {
                <label class="bea-admin-field">
                  <span>Chemin : {{ p }}<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                  <input type="text" [formControl]="ctrl('p_' + p)" maxlength="200" required autocomplete="off" />
                </label>
              }
              @for (p of paramsQuery(); track p) {
                <label class="bea-admin-field"><span>Requête : {{ p }}</span><input type="text" [formControl]="ctrl('q_' + p)" maxlength="200" autocomplete="off" /></label>
              }
            </div>
            <p class="bea-integ-help">Valeurs fictives uniquement ; aucune donnée client réelle ni secret.</p>
          }
          <div class="bea-admin-actions">
            <button type="submit" class="bea-admin-btn" [disabled]="!peutPreparer()" [attr.aria-busy]="action() === 'apercu'">
              @if (action() === 'apercu') { <span class="bea-integ-spinner" aria-hidden="true"></span> }
              {{ action() === 'apercu' ? 'Préparation…' : 'Préparer l’aperçu' }}
            </button>
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/destinations" [queryParams]="{ fournisseur: fournisseurId }">Gérer les destinations</a>
          </div>
          @if (!peutPreparer() && raisonBlocage(); as r) {
            <p class="bea-integ-help" role="status">Aperçu indisponible : {{ r }}</p>
          }
        </form>
      }
      @if (erreur(); as e) {
        <div class="bea-integ-etat" [attr.data-etat]="etatErreur()" role="alert">
          <div>
            <h3>{{ libelleEtat(etatErreur()) }}</h3>
            <p>{{ e }}</p>
          </div>
        </div>
      }
      @if (apercu(); as a) {
        <section class="bea-integ-section bea-integ-step" aria-live="polite">
          <h2>3. Aperçu — aucun appel n’a encore été envoyé</h2>
          <dl class="bea-integ-recap">
            <dt>Méthode</dt><dd><span class="bea-integ-method" [attr.data-m]="a.methode">{{ a.methode }}</span></dd>
            <dt>URL construite</dt><dd class="bea-integ-path">{{ a.url }}</dd>
            <dt>Environnement</dt><dd>{{ a.environnement }}</dd>
            <dt>Authentification</dt><dd>{{ a.authentification }}</dd>
            <dt>En-têtes envoyés</dt><dd>{{ a.entetes_envoyes.join(', ') || '—' }}</dd>
            <dt>Redirections</dt><dd>{{ a.redirections }}</dd>
          </dl>
          <p class="bea-integ-muted">{{ a.avertissement }}</p>
        </section>
        <section class="bea-integ-section bea-integ-step" aria-labelledby="integ-test-confirm">
          <h2 id="integ-test-confirm">4. Confirmation</h2>
          @if (!droits.execute()) {
            <p class="bea-integ-help">Exécution indisponible : permission <code>core.admin.integrations.tests.execute</code> requise.</p>
          } @else if (secretRequis()) {
            <p class="bea-integ-help">Exécution bloquée : un secret serait requis et aucun coffre n’est approuvé.</p>
          } @else {
            <div class="bea-integ-etat" [attr.data-etat]="action() === 'execution' ? 'en_cours' : 'attente'" role="status">
              <div>
                <h3>{{ action() === 'execution' ? libelleEtat('en_cours') : libelleEtat('attente') }}</h3>
                <p>Une seule requête {{ a.methode }} sera envoyée vers l’hôte approuvé, sous contrôle SSRF, DNS, TLS, quota, taille et délai.</p>
              </div>
            </div>
            <div class="bea-admin-actions">
              <button type="button" class="bea-admin-btn" [disabled]="action() !== null" (click)="executer()" [attr.aria-busy]="action() === 'execution'">
                @if (action() === 'execution') { <span class="bea-integ-spinner" aria-hidden="true"></span> }
                {{ action() === 'execution' ? 'Exécution…' : 'Exécuter le test' }}
              </button>
            </div>
          }
        </section>
      }
      @if (resultat(); as r) {
        <section class="bea-integ-section bea-integ-step" aria-live="polite">
          <h2>5. Résultat</h2>
          <div class="bea-integ-etat" [attr.data-etat]="etatResultat(r.statut)">
            <div>
              <h3>{{ libelleEtat(etatResultat(r.statut)) }} — <span [class]="tone(r.statut)">{{ label(r.statut) }}</span></h3>
              <p>{{ famille(r.statut) }}{{ r.message ? ' — ' + r.message : '' }}</p>
            </div>
          </div>
          <dl class="bea-integ-recap" style="margin-top: 0.75rem">
            <dt>Identifiant de corrélation</dt><dd><code>{{ r.correlation_id }}</code></dd>
            <dt>Statut HTTP</dt><dd>{{ r.http_status ?? '—' }}</dd>
            <dt>Latence</dt><dd>{{ r.duree_ms != null ? r.duree_ms + ' ms' : '—' }}</dd>
            <dt>Début</dt><dd>{{ r.started_at | date: 'dd/MM/yyyy HH:mm:ss' }}</dd>
          </dl>
          @if (r.reponse?.extrait) {
            <p class="bea-integ-muted">Extrait assaini (2 Kio maximum, secrets masqués) :</p>
            <pre class="bea-integ-result">{{ r.reponse?.extrait }}</pre>
          }
          <div class="bea-admin-actions">
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/executions" [queryParams]="{ execution: r.id, periode: 'tout' }">Voir dans l’historique</a>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="nouveauTest()">Préparer un autre test</button>
          </div>
        </section>
      }
    </section>
  `,
})
export class CoreAdminIntegrationTestComponent implements OnInit {
  @Input({ required: true }) fournisseurId = '';
  @Input() destinationInitiale = '';
  private readonly tests = inject(CoreAdminIntegrationExecutionService);
  private readonly fourn = inject(CoreAdminIntegrationFournisseursService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  readonly droits = integrationTestsPermissions();
  readonly form = this.fb.nonNullable.group({ operation_id: '', destination_id: '' });
  readonly paramsForm = new FormRecord<FormControl<string>>({});
  readonly operations = signal<OperationResume[]>([]);
  readonly destinations = signal<DestinationResume[]>([]);
  readonly paramsPath = signal<string[]>([]);
  readonly paramsQuery = signal<string[]>([]);
  readonly secretRequis = signal(false);
  readonly chargement = signal(true);
  readonly chargementOperation = signal(false);
  readonly erreurChargement = signal<string | null>(null);
  readonly apercu = signal<TestApercu | null>(null);
  readonly resultat = signal<ExecutionDetail | null>(null);
  readonly erreur = signal<string | null>(null);
  readonly action = signal<'apercu' | 'execution' | null>(null);
  readonly label = executionStatutLabel;
  readonly tone = executionStatutTone;
  readonly famille = executionFamilleLabel;
  readonly etapes = ['Sélection', 'Paramètres', 'Aperçu (sans appel)', 'Confirmation', 'Résultat'];
  readonly erreurCode = signal<string | null>(null);
  private attendus = 2;

  etapeCourante(): number {
    if (this.resultat()) return 5;
    if (this.apercu()) return 4;
    const v = this.form.getRawValue();
    if (!v.operation_id || !v.destination_id) return 1;
    const pathRempli = this.paramsPath().every((p) => (this.paramsForm.controls['p_' + p]?.value ?? '').trim() !== '');
    return pathRempli ? 3 : 2;
  }

  etatEtape(n: number): 'fait' | 'courant' | null {
    const c = this.etapeCourante();
    return n < c ? 'fait' : n === c ? 'courant' : null;
  }

  raisonBlocage(): string | null {
    const v = this.form.getRawValue();
    if (!this.droits.execute()) return 'permission d’exécution absente.';
    if (this.secretRequis()) return 'opération authentifiée (secret requis).';
    if (this.chargementOperation()) return 'lecture de l’opération en cours.';
    if (!v.operation_id) return 'choisissez une opération.';
    if (!v.destination_id) return 'choisissez une destination approuvée.';
    if (this.etapeCourante() === 2) return 'renseignez les paramètres de chemin obligatoires.';
    return null;
  }

  etatErreur(): EtatVisuel {
    switch (this.erreurCode()) {
      case 'QUOTA': case 'QUOTA_INDISPONIBLE': return 'quota';
      case 'SECRET_REQUIS': return 'secret';
      case 'TIMEOUT': return 'delai';
      case 'DNS': case 'TLS': case 'RESEAU': return 'reseau';
      default: return 'refus';
    }
  }

  etatResultat(statut: string): EtatVisuel {
    return etatExecution(statut);
  }

  libelleEtat(e: EtatVisuel): string {
    return LIBELLES_ETAT[e];
  }

  nouveauTest(): void {
    this.resultat.set(null);
    this.invalider();
  }

  private codeErreur(err: unknown): string | null {
    const corps = (err as { error?: { code?: unknown } } | null)?.error;
    return typeof corps?.code === 'string' ? corps.code : null;
  }

  ngOnInit(): void {
    this.fourn.operations(this.fournisseurId, {}, 1, 200).subscribe({
      next: (r) => {
        this.operations.set(r.items.filter((o) => o.statut === 'active' && (o.methode === 'GET' || o.methode === 'HEAD')));
        this.termine();
      },
      error: (err) => this.echecChargement(err),
    });
    this.tests.listerDestinations({ fournisseur_id: this.fournisseurId, statut: 'active' }, 1, 100).subscribe({
      next: (r) => {
        this.destinations.set(r.items);
        if (this.destinationInitiale && r.items.some((d) => d.id === this.destinationInitiale)) {
          this.form.controls.destination_id.setValue(this.destinationInitiale);
        }
        this.termine();
      },
      error: (err) => this.echecChargement(err),
    });
    this.form.controls.operation_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((id) => this.adapterParams(id));
    this.form.controls.destination_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.invalider());
    this.paramsForm.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.invalider());
  }

  private termine(): void {
    this.attendus -= 1;
    if (this.attendus <= 0) this.chargement.set(false);
  }

  private echecChargement(err: unknown): void {
    this.erreurChargement.set(
      estAccesRefuse(err)
        ? 'Accès refusé : la préparation d’un test exige aussi la consultation des fournisseurs (core.admin.integrations.fournisseurs.view) et des destinations (core.admin.integrations.destinations.view).'
        : messageErreur(err, 'Impossible de charger les opérations ou destinations.'),
    );
    this.chargement.set(false);
  }

  /** Toute modification après l’aperçu l’invalide : on n’exécute que ce qui a été prévisualisé. */
  private invalider(): void {
    this.apercu.set(null);
    this.erreur.set(null);
    this.erreurCode.set(null);
  }

  peutPreparer(): boolean {
    const v = this.form.getRawValue();
    if (!this.droits.execute() || this.action() !== null || this.secretRequis() || this.chargementOperation()) return false;
    if (!v.operation_id || !v.destination_id) return false;
    return this.paramsPath().every((p) => (this.paramsForm.controls['p_' + p]?.value ?? '').trim() !== '');
  }

  private adapterParams(id: string): void {
    this.invalider();
    this.resultat.set(null);
    this.paramsPath.set([]);
    this.paramsQuery.set([]);
    this.secretRequis.set(false);
    if (!id) return;
    this.chargementOperation.set(true);
    this.fourn.operation(this.fournisseurId, id).subscribe({
      next: (op) => {
        const path = op.parametres.filter((p) => p.emplacement === 'path').map((p) => p.nom);
        const query = op.parametres.filter((p) => p.emplacement === 'query').map((p) => p.nom);
        for (const p of path) this.ctrl('p_' + p);
        for (const p of query) this.ctrl('q_' + p);
        this.paramsPath.set(path);
        this.paramsQuery.set(query);
        this.secretRequis.set(operationExigeSecret(op));
        this.chargementOperation.set(false);
      },
      error: (err) => {
        this.erreur.set(messageErreur(err, 'Opération illisible.'));
        this.chargementOperation.set(false);
      },
    });
  }

  ctrl(nom: string): FormControl<string> {
    if (!this.paramsForm.contains(nom)) this.paramsForm.addControl(nom, new FormControl('', { nonNullable: true }), { emitEvent: false });
    return this.paramsForm.controls[nom];
  }

  private valeurs(): { parametres_chemin: Record<string, string>; parametres_requete: Record<string, string> } {
    const v = this.paramsForm.getRawValue();
    const chemin: Record<string, string> = {};
    const requete: Record<string, string> = {};
    for (const p of this.paramsPath()) chemin[p] = (v['p_' + p] ?? '').trim();
    for (const p of this.paramsQuery()) {
      const valeur = (v['q_' + p] ?? '').trim();
      if (valeur) requete[p] = valeur;
    }
    return { parametres_chemin: chemin, parametres_requete: requete };
  }

  preparer(): void {
    if (!this.peutPreparer()) return;
    const v = this.form.getRawValue();
    this.action.set('apercu');
    this.erreur.set(null);
    this.resultat.set(null);
    this.tests.apercu({
      fournisseur_id: this.fournisseurId,
      operation_id: v.operation_id,
      destination_id: v.destination_id,
      ...this.valeurs(),
    }).subscribe({
      next: (a) => { this.apercu.set(a); this.action.set(null); },
      error: (err) => { this.erreurCode.set(this.codeErreur(err)); this.erreur.set(messageTest(err, 'Aperçu refusé.')); this.action.set(null); },
    });
  }

  async executer(): Promise<void> {
    const a = this.apercu();
    const v = this.form.getRawValue();
    if (!a || !v.operation_id || !v.destination_id || this.action() !== null || !this.droits.execute()) return;
    const ok = await this.dialogs.confirm({
      title: 'Exécuter le test',
      message: `Envoyer ${a.methode} vers ${a.url} ? Seule cette destination approuvée sera contactée. Aucune redirection ne sera suivie et aucun secret n’est transmis.`,
      confirmLabel: 'Exécuter le test',
    });
    if (!ok || this.apercu() !== a) return;
    this.action.set('execution');
    this.tests.executer({
      fournisseur_id: this.fournisseurId,
      operation_id: v.operation_id,
      destination_id: v.destination_id,
      ...this.valeurs(),
    }).subscribe({
      next: (r) => {
        this.resultat.set(r);
        this.apercu.set(null);
        this.action.set(null);
        void this.dialogs.success(`Test enregistré : ${executionStatutLabel(r.statut)}.`);
      },
      error: (err) => { this.erreurCode.set(this.codeErreur(err)); this.erreur.set(messageTest(err, 'Exécution refusée.')); this.action.set(null); },
    });
  }
}
