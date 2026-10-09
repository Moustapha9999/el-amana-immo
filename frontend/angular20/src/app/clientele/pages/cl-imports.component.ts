import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { AnalyseImport, AnomaliePage, CL_BASE, ImportClientele, dateHeureFr, n, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';
import { ClLotComponent } from './cl-lot.component';

type Source = 'orion' | 'situation' | 'liste';
const SOURCES: readonly Source[] = ['orion', 'situation', 'liste'];

@Component({
  selector: 'bea-cl-imports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, ClienteleUiComponent, ClLotComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Référentiel clients</p>
          <h1>Importer</h1>
          <p class="bea-cl-head__sub">Choisissez le type de fichier. Racine CLIENT sur 6 chiffres. Aucun client n’est supprimé. Rien n’est enregistré avant confirmation.</p>
        </div>
        @if (source() === 'orion' && imp()) {
          <div class="bea-mg__actions">
            @if (imp()!.statut === 'ANALYSE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="abandonner()" [disabled]="busy()"><mat-icon>close</mat-icon> Abandonner</button>
            } @else {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()"><mat-icon>upload_file</mat-icon> Nouvel import</button>
            }
          </div>
        }
      </header>

      <div class="bea-cl-options" role="tablist" aria-label="Type de fichier">
        @for (o of options; track o.code) {
          <button type="button" role="tab" class="bea-cl-option" [class.is-on]="source() === o.code" [attr.aria-selected]="source() === o.code" (click)="choisirSource(o.code)">
            <mat-icon>{{ o.icon }}</mat-icon><strong>{{ o.titre }}</strong><span>{{ o.aide }}</span>
          </button>
        }
      </div>

      @if (source() === 'situation') {
        <bea-cl-lot type="SITUATION" />
      } @else if (source() === 'liste') {
        <bea-cl-lot type="LISTE" />
      } @else if (!imp()) {
        @if (store.cap().imports_executer) {
          <section class="bea-mg__panel" style="padding:1rem">
            <label class="bea-fx-dropzone" [class.is-over]="survol()" (dragover)="$event.preventDefault(); survol.set(true)" (dragleave)="survol.set(false)" (drop)="deposer($event)">
              <input type="file" accept=".xlsx,.xlsm" hidden (change)="choisir($any($event.target))" />
              @if (busy()) {
                <mat-icon class="bea-cl-spin">progress_activity</mat-icon><strong>Analyse du fichier…</strong>
              } @else {
                <mat-icon>upload_file</mat-icon>
                <strong>Déposez l’État des comptes ORION</strong>
                <span>.xlsx, 40 Mo maximum — colonnes CLIENT, COMPTE, RIB…</span>
              }
            </label>
          </section>
        }
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Historique</h2><span class="bea-mg__count">{{ historique().length }}</span></div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th>Fichier</th><th>Le</th><th>Par</th><th>Lignes</th><th>Clients</th><th>Comptes</th><th>Statut</th>@if (store.cap().admin) {<th></th>}</tr></thead>
              <tbody>
                @for (h of historique(); track h.id) {
                  <tr style="cursor:pointer" (click)="reprendre(h)">
                    <td><strong>{{ h.fichier_nom }}</strong></td>
                    <td>{{ dh(h.created_at) }}</td>
                    <td>{{ h.auteur || '—' }}</td>
                    <td>{{ n(h.nb_lignes) }}</td>
                    <td>{{ n(h.nb_clients) }}</td>
                    <td>{{ n(h.nb_comptes) }}</td>
                    <td><span class="bea-cl-badge" [attr.data-s]="h.statut">{{ h.statut }}</span></td>
                    @if (store.cap().admin) {
                      <td (click)="$event.stopPropagation()">
                        <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" (click)="supprimer(h)"><mat-icon>delete</mat-icon></button>
                      </td>
                    }
                  </tr>
                } @empty {
                  <tr><td [attr.colspan]="store.cap().admin ? 8 : 7"><div class="bea-cl-empty"><mat-icon>history</mat-icon>Aucun import.</div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </section>
      } @else {
        @let a = analyse()!;
        <ol class="bea-cl-steps">
          @for (e of etapes; track e; let i = $index) {
            <li [class.is-on]="etape() === i" [class.is-done]="etape() > i" (click)="etape() > i && imp()!.statut === 'ANALYSE' && etape.set(i)">{{ e }}</li>
          }
        </ol>

        @if (etape() === 0) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><div><h2>{{ a.feuille }}</h2><p class="bea-cl-hint">En-têtes ligne {{ a.ligne_entete }}</p></div></div>
            <div class="bea-cl-stats">
              @for (s of stats(); track s.label) {
                <div class="bea-cl-stat" [attr.data-tone]="s.tone"><span>{{ s.label }}</span><strong>{{ s.valeur }}</strong></div>
              }
            </div>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Mapping des colonnes</h2></div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Champ</th><th>En-tête du fichier</th></tr></thead>
                <tbody>
                  @for (c of a.colonnes; track c.champ) {
                    <tr>
                      <td>{{ c.libelle }} @if (c.obligatoire) { <em style="color:#b91c1c">*</em> }</td>
                      <td>
                        <select [(ngModel)]="mapping[c.champ]" (ngModelChange)="mappingChange.set(true)" style="font:inherit;padding:0.35rem 0.5rem;border:1px solid #dbe3ee;border-radius:0.5rem;width:100%">
                          @for (opt of a.colonnes; track opt.entete) { <option [ngValue]="opt.entete">{{ opt.entete }}</option> }
                          @for (x of a.colonnes_ignorees; track x) { <option [ngValue]="x">{{ x }}</option> }
                        </select>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            @if (a.colonnes_ignorees.length) {
              <p class="bea-cl-hint" style="padding:0 1.1rem 0.8rem">Colonnes supplémentaires : {{ a.colonnes_ignorees.join(', ') }}</p>
            }
            @if (mappingChange()) {
              <div style="padding:0 1.1rem 1rem"><button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="relancerMapping()">Relancer l’analyse</button></div>
            }
          </section>
        }

        @if (etape() === 1) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Anomalies</h2>
              <span style="display:flex;gap:0.4rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="chargerAnomalies()"><mat-icon>refresh</mat-icon> Actualiser</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporterAnomalies()"><mat-icon>table_view</mat-icon> Excel</button>
              </span>
            </div>
            <ul class="bea-cl-anoms">
              @for (x of anomalies(); track $index) {
                <li [attr.data-n]="x.bloquante ? 'bloquant' : 'alerte'"><mat-icon>{{ x.bloquante ? 'block' : 'warning' }}</mat-icon>
                  <span>@if (x.numero) {<b>Ligne {{ x.numero }} :</b> }{{ x.message }}</span></li>
              } @empty { <li data-n="info"><mat-icon>check</mat-icon><span>Aucune anomalie chargée — cliquez Actualiser.</span></li> }
            </ul>
            <p class="bea-cl-hint" style="padding:0 1.1rem 0.9rem">Les lignes rejetées ne sont pas importées. Les clients déjà en base ne sont jamais supprimés.</p>
          </section>
        }

        @if (etape() === 2) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Aperçu avant écriture</h2></div>
            <div class="bea-cl-stats">
              <div class="bea-cl-stat" data-tone="ok"><span>Clients à créer</span><strong>{{ a.apercu_ecriture.clients_a_creer }}</strong></div>
              <div class="bea-cl-stat"><span>Clients à mettre à jour</span><strong>{{ a.apercu_ecriture.clients_a_mettre_a_jour }}</strong></div>
              <div class="bea-cl-stat" data-tone="ok"><span>Comptes à créer</span><strong>{{ a.apercu_ecriture.comptes_a_creer }}</strong></div>
              <div class="bea-cl-stat"><span>Comptes à mettre à jour</span><strong>{{ a.apercu_ecriture.comptes_a_mettre_a_jour }}</strong></div>
              <div class="bea-cl-stat" data-tone="warn"><span>Comptes absents du fichier</span><strong>{{ a.apercu_ecriture.comptes_absents_du_fichier }}</strong></div>
            </div>
            @if (a.apercu_ecriture.comptes_absents_du_fichier) {
              <div class="bea-cl-note bea-cl-note--info"><mat-icon>info</mat-icon><span>Ces comptes restent en base : l’import ne les supprime pas.</span></div>
            }
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Ligne</th><th>Racine</th><th>Nom</th><th>Compte</th><th>État</th></tr></thead>
                <tbody>
                  @for (l of a.apercu; track l['ligne']) {
                    <tr><td>{{ l['ligne'] }}</td><td>{{ l['racine_client'] }}</td><td>{{ l['raison_sociale'] }}</td><td>{{ l['compte'] }}</td><td>{{ l['etat_compte'] }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @if (etape() === 3) {
          @if (imp()!.statut === 'IMPORTE') {
            <section class="bea-mg__panel">
              <div class="bea-cl-result"><mat-icon>task_alt</mat-icon><h2>Import terminé</h2></div>
              <div class="bea-cl-stats">
                <div class="bea-cl-stat" data-tone="ok"><span>Clients créés</span><strong>{{ imp()!.clients_crees }}</strong></div>
                <div class="bea-cl-stat"><span>Clients mis à jour</span><strong>{{ imp()!.clients_maj }}</strong></div>
                <div class="bea-cl-stat" data-tone="ok"><span>Comptes créés</span><strong>{{ imp()!.comptes_crees }}</strong></div>
                <div class="bea-cl-stat"><span>Comptes mis à jour</span><strong>{{ imp()!.comptes_maj }}</strong></div>
              </div>
            </section>
          } @else {
            <section class="bea-mg__panel" style="padding:1rem">
              <h2>Confirmation</h2>
              <label class="bea-cl-filters">Date d’extraction
                <input type="date" [(ngModel)]="dateExtraction" />
              </label>
              @if (a.deja_importe) {
                <label class="bea-cl-check"><input type="checkbox" [(ngModel)]="forcer" /> Ce fichier a déjà été importé le {{ dh(a.deja_importe.le) }} : je confirme le ré-import (aucune suppression).</label>
              }
            </section>
          }
        }

        @if (imp()!.statut === 'ANALYSE') {
          <div class="bea-cl-bar">
            <span>Étape {{ etape() + 1 }} / {{ etapes.length }}</span>
            <span style="display:flex;gap:0.5rem">
              @if (etape() > 0) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="etape.set(etape() - 1)">Précédent</button> }
              @if (etape() < 3) {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="suivant()">Suivant</button>
              } @else {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || (!!a.deja_importe && !forcer)" (click)="confirmer()"><mat-icon>cloud_done</mat-icon> Confirmer l’import</button>
              }
            </span>
          </div>
        }
      }
    </div>
  `,
})
export class ClImportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  readonly options: { code: Source; icon: string; titre: string; aide: string }[] = [
    { code: 'orion', icon: 'account_balance', titre: 'État des comptes ORION', aide: 'Extraction ORION (une ligne = un compte) : crée et met à jour clients et comptes.' },
    { code: 'situation', icon: 'assignment', titre: 'Situation des comptes PP & PM', aide: 'Classeur Conformité : reprise de la classe de risque LBC/FT par racine.' },
    { code: 'liste', icon: 'group_add', titre: 'Liste de clients', aide: 'Tout fichier avec une colonne Racine client : contrôler, évaluer, classer, exporter.' },
  ];
  readonly source = signal<Source>('orion');
  readonly etapes = ['Analyse & mapping', 'Contrôles', 'Aperçu', 'Confirmation'];
  readonly historique = signal<ImportClientele[]>([]);
  readonly imp = signal<ImportClientele | null>(null);
  readonly busy = signal(false);
  readonly survol = signal(false);
  readonly etape = signal(0);
  readonly mappingChange = signal(false);
  readonly anomalies = signal<AnomaliePage['items']>([]);
  mapping: Record<string, string> = {};
  dateExtraction = new Date().toISOString().slice(0, 10);
  forcer = false;
  readonly dh = dateHeureFr;
  readonly n = n;
  readonly analyse = computed<AnalyseImport | null>(() => this.imp()?.analyse ?? null);
  readonly stats = computed(() => {
    const s = (this.analyse()?.stats ?? {}) as Record<string, number>;
    return [
      { label: 'Lignes lues', valeur: s['lignes_lues'] ?? 0, tone: '' },
      { label: 'Valides', valeur: s['lignes_valides'] ?? 0, tone: 'ok' },
      { label: 'Rejets', valeur: s['lignes_rejetees'] ?? 0, tone: s['lignes_rejetees'] ? 'danger' : '' },
      { label: 'Clients', valeur: s['clients'] ?? 0, tone: '' },
      { label: 'Comptes', valeur: s['comptes'] ?? 0, tone: '' },
      { label: 'Anomalies', valeur: s['anomalies'] ?? 0, tone: s['anomalies'] ? 'warn' : '' },
    ];
  });
  readonly hasUnsavedChanges = unsavedChanges(() => this.imp()?.statut === 'ANALYSE' && !this.busy());

  ngOnInit(): void {
    this.store.charger();
    const s = this.route.snapshot.queryParamMap.get('source') as Source | null;
    if (s && SOURCES.includes(s)) this.source.set(s);
    this.chargerHistorique();
  }

  choisirSource(s: Source): void {
    if (s === this.source()) return;
    this.source.set(s);
    void this.router.navigate([], { relativeTo: this.route, queryParams: { source: s === 'orion' ? null : s }, replaceUrl: true });
  }

  private chargerHistorique(): void {
    this.api.get<ImportClientele[]>(`${CL_BASE}/imports`).subscribe({ next: (l) => this.historique.set(l), error: () => this.historique.set([]) });
  }

  deposer(e: DragEvent): void {
    e.preventDefault();
    this.survol.set(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) this.analyser(f);
  }

  choisir(input: HTMLInputElement): void {
    const f = input.files?.[0];
    input.value = '';
    if (f) this.analyser(f);
  }

  private analyser(f: File): void {
    if (!/\.(xlsx|xlsm)$/i.test(f.name)) {
      this.feedback.warning({ title: 'Format non pris en charge', message: 'Fichier .xlsx attendu.' });
      return;
    }
    const fd = new FormData();
    fd.append('fichier', f);
    this.feedback.run(() => this.api.post<ImportClientele>(`${CL_BASE}/imports/analyse`, fd), {
      busy: this.busy, loading: 'Analyse du fichier…',
      success: (r) => ({ title: 'Analyse terminée', message: `${r.nb_clients} client(s), ${r.nb_comptes} compte(s)` }),
      errorTitle: "Échec de l'analyse", retry: false,
    }).subscribe((r) => this.ouvrir(r));
  }

  reprendre(h: ImportClientele): void {
    this.api.get<ImportClientele>(`${CL_BASE}/imports/${h.id}`).subscribe({
      next: (r) => this.ouvrir(r),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Import introuvable')),
    });
  }

  private ouvrir(r: ImportClientele): void {
    this.mapping = { ...(r.analyse?.mapping ?? {}) };
    this.mappingChange.set(false);
    this.forcer = false;
    this.imp.set(r);
    this.etape.set(r.statut === 'IMPORTE' ? 3 : 0);
  }

  relancerMapping(): void {
    const r = this.imp()!;
    this.feedback.run(() => this.api.post<ImportClientele>(`${CL_BASE}/imports/${r.id}/mapping`, { mapping: this.mapping }), {
      busy: this.busy, loading: 'Nouvelle analyse…', success: { title: 'Mapping appliqué' }, errorTitle: 'Mapping refusé',
    }).subscribe((x) => this.ouvrir(x));
  }

  chargerAnomalies(): void {
    const r = this.imp()!;
    this.api.get<AnomaliePage>(`${CL_BASE}/imports/${r.id}/anomalies`, { taille: 80 }).subscribe({
      next: (p) => this.anomalies.set(p.items),
      error: () => this.anomalies.set([]),
    });
  }

  exporterAnomalies(): void {
    const r = this.imp()!;
    this.busy.set(true);
    this.api.download(`${CL_BASE}/imports/${r.id}/anomalies.xlsx`).subscribe({
      next: (b) => {
        this.busy.set(false);
        telecharger(b, `anomalies-${r.fichier_nom.replace(/\.xlsx?m?$/i, '')}.xlsx`);
      },
      error: (e) => {
        this.busy.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible'));
      },
    });
  }

  suivant(): void {
    const n = this.etape() + 1;
    this.etape.set(n);
    if (n === 1) this.chargerAnomalies();
  }

  abandonner(): void {
    const r = this.imp()!;
    this.feedback.run(() => this.api.post<ImportClientele>(`${CL_BASE}/imports/${r.id}/abandonner`, {}), {
      confirm: { action: 'annulation', title: 'Abandonner l’import', message: `Abandonner « ${r.fichier_nom} » ?`, hint: 'Aucune donnée clientèle n’a été écrite.' },
      busy: this.busy, success: { title: 'Import abandonné' }, errorTitle: 'Action impossible',
    }).subscribe(() => this.reinitialiser());
  }

  supprimer(h: ImportClientele): void {
    this.feedback.run(() => this.api.delete<void>(`${CL_BASE}/imports/${h.id}`), {
      confirm: { action: 'suppression', title: 'Supprimer de l’historique', message: `Supprimer « ${h.fichier_nom} » ?`, hint: 'Les clients déjà importés sont conservés.' },
      busy: this.busy, success: { title: 'Import retiré de l’historique' }, errorTitle: 'Suppression impossible',
    }).subscribe(() => this.chargerHistorique());
  }

  reinitialiser(): void {
    this.imp.set(null);
    this.etape.set(0);
    this.chargerHistorique();
  }

  confirmer(): void {
    const r = this.imp()!;
    this.feedback.run(
      () => this.api.post<ImportClientele>(`${CL_BASE}/imports/${r.id}/confirmer`, {
        date_extraction: this.dateExtraction, forcer: this.forcer,
      }),
      {
        confirm: { action: 'validation', title: 'Confirmer l’import', message: `Importer ${r.nb_clients} client(s) / ${r.nb_comptes} compte(s) ?`, hint: 'Aucun client existant n’est supprimé.' },
        busy: this.busy, loading: 'Import en cours…',
        success: (x) => ({ title: 'Import terminé', details: [
          { label: 'Clients créés', value: String(x.clients_crees ?? 0) },
          { label: 'Comptes créés', value: String(x.comptes_crees ?? 0) },
        ] }),
        errorTitle: "Échec de l'import", retry: false,
      },
    ).subscribe((x) => {
      this.imp.set({ ...r, ...x, analyse: r.analyse });
      this.etape.set(3);
    });
  }
}
