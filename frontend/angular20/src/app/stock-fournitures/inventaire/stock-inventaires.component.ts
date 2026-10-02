import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { debounceTime } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { PaginationComponent } from '../../shared/pagination.component';
import {
  Inventaire,
  InventaireStatut,
  InventaireSynthese,
  MOIS,
  PERM,
  Paginated,
  RefOption,
  STATUT_ICONS,
  STATUT_LABELS,
  aPermission,
  downloadBlob,
  signe,
} from './inventaire.model';

interface ImportLigne {
  ligne: number;
  code: string | null;
  designation: string | null;
  famille: string | null;
  stock_theorique_fichier: number | null;
  stock_theorique_systeme: number | null;
  stock_physique: number | null;
  ecart: number | null;
  observation: string | null;
  statut: string;
  methode: string | null;
  article_id: string | null;
  article_code: string | null;
  article_designation: string | null;
  anomalies: string[];
  avertissements: string[];
}

interface ImportAnalyse {
  fichier: string;
  feuilles: string[];
  feuille: string;
  ligne_entete: number;
  entetes: string[];
  mapping: Partial<Record<string, string>>;
  champs: { champ: string; libelle: string; obligatoire: boolean }[];
  colonnes_ambigues: { champ: string; libelle: string; colonnes: string[]; retenue: string }[];
  colonnes_ignorees: string[];
  periode: string;
  resume: Record<string, number>;
  anomalies: string[];
  avertissements: string[];
  bloquant: boolean;
  articles_absents: { id: string; code: string; designation: string }[];
  lignes: ImportLigne[];
}

interface ArticleOption {
  id: string;
  code: string;
  designation: string;
}

type ImportFiltre = 'tous' | 'bloquants' | 'ecarts' | 'exclus' | 'avertissements';

const IMPORT_STATUTS: Record<string, string> = {
  OK: 'Compté',
  NON_COMPTE: 'Non compté',
  EXCLU: 'Exclu',
  INCONNU: 'Article inconnu',
  DOUBLON: 'Doublon',
  QTE_INVALIDE: 'Quantité invalide',
  IGNORE: 'Ignoré',
  HORS_PERIMETRE: 'Hors périmètre',
};
const BLOQUANTS = new Set(['INCONNU', 'DOUBLON', 'QTE_INVALIDE']);

function aujourdhui(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

@Component({
  selector: 'bea-stock-inventaires',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, DatePipe, MatIconModule, PaginationComponent],
  styleUrl: './inventaire.css',
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Stock &amp; Fournitures · Inventaire mensuel</p>
          <h1>Inventaires</h1>
        </div>
        <div class="bea-mg__actions">
          @if (peutExporter()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('xlsx')">
              <mat-icon>table_view</mat-icon> Excel
            </button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('pdf')">
              <mat-icon>picture_as_pdf</mat-icon> PDF
            </button>
          }
          @if (peutSaisir()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirImport()">
              <mat-icon>upload_file</mat-icon> Importer Excel
            </button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirCreation()">
              <mat-icon>add</mat-icon> Nouvel inventaire
            </button>
          }
        </div>
      </header>

      @if (synthese(); as s) {
        <div class="inv-shortcuts">
          <button type="button" class="inv-shortcut" style="--i:0" [disabled]="!s.dernier" (click)="s.dernier && ouvrir(s.dernier)">
            <mat-icon>history</mat-icon>
            <span>
              <small>Dernier inventaire</small>
              @if (s.dernier; as d) {
                <strong>{{ d.reference }}</strong>
                <em>{{ d.periode_libelle }} · {{ statutLabel(d.statut) }}</em>
              } @else {
                <strong>Aucun</strong>
              }
            </span>
          </button>
          <button type="button" class="inv-shortcut" style="--i:1" [disabled]="!s.en_cours" (click)="s.en_cours && ouvrir(s.en_cours)">
            <mat-icon>fact_check</mat-icon>
            <span>
              <small>Inventaire en cours</small>
              @if (s.en_cours; as e) {
                <strong>{{ e.reference }} · {{ e.stats.progression }} %</strong>
                <em>{{ e.stats.comptes }} / {{ e.stats.a_compter }} articles comptés</em>
              } @else {
                <strong>Aucun</strong>
              }
            </span>
          </button>
          <button type="button" class="inv-shortcut" style="--i:2" (click)="filtrerStatut('A_CONTROLER')">
            <mat-icon>rule</mat-icon>
            <span>
              <small>À contrôler</small>
              <strong>{{ s.nb_a_controler }} inventaire(s)</strong>
              <em>En attente de validation</em>
            </span>
          </button>
        </div>
      }

      <form class="bea-mg__search inv-filters" [formGroup]="filtres" (ngSubmit)="$event.preventDefault()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Référence, libellé, responsable…" aria-label="Rechercher" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>event</mat-icon>
          <select formControlName="mois" aria-label="Mois">
            <option value="">Tous les mois</option>
            @for (m of mois; track $index) {
              <option [value]="$index + 1">{{ m }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <input type="number" formControlName="annee" min="2000" max="2100" placeholder="Année" aria-label="Année" style="width:5rem" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>flag</mat-icon>
          <select formControlName="statut" aria-label="Statut">
            <option value="">Tous les statuts</option>
            @for (s of statuts; track s) {
              <option [value]="s">{{ statutLabel(s) }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>store</mat-icon>
          <select formControlName="agence_id" aria-label="Agence">
            <option value="">Toutes agences</option>
            @for (a of agences(); track a.id) {
              <option [value]="a.id">{{ a.libelle }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>difference</mat-icon>
          <select formControlName="ecarts" aria-label="Écarts">
            <option value="">Avec ou sans écart</option>
            <option value="avec">Avec écarts</option>
            <option value="sans">Sans écart</option>
          </select>
        </label>
        @if (filtresActifs()) {
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()">
            <mat-icon>filter_alt_off</mat-icon> Réinitialiser
          </button>
        }
      </form>

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Campagnes d’inventaire</h2>
          <span class="bea-mg__count">{{ total() }} inventaire(s)</span>
        </div>
        @if (chargement() && !items().length) {
          <div class="inv-skeleton"></div>
          <div class="inv-skeleton"></div>
          <div class="inv-skeleton"></div>
        } @else {
          <div class="bea-mg__table-scroll inv-table-wrap">
            <table class="bea-mg__table">
              <thead>
                <tr>
                  <th>Référence</th>
                  <th>Période</th>
                  <th>Agence</th>
                  <th>Responsable</th>
                  <th>Statut</th>
                  <th>Progression</th>
                  <th class="inv-num">Écarts</th>
                  <th class="inv-num">Écart net</th>
                </tr>
              </thead>
              <tbody>
                @for (inv of items(); track inv.id) {
                  <tr class="inv-row-link" tabindex="0" (click)="ouvrir(inv)" (keydown.enter)="ouvrir(inv)">
                    <td>
                      <code class="bea-mg__code">{{ inv.reference }}</code>
                      @if (inv.source === 'IMPORT_EXCEL') {
                        <mat-icon title="Importé depuis Excel" style="font-size:1rem;width:1rem;height:1rem;vertical-align:-.2rem;color:#64748b">upload_file</mat-icon>
                      }
                    </td>
                    <td>
                      {{ inv.periode_libelle || '—' }}
                      <br /><small style="color:#64748b">{{ inv.date_debut | date: 'dd/MM/yyyy' }}</small>
                    </td>
                    <td>{{ inv.agence_libelle || 'Toutes agences' }}</td>
                    <td>{{ inv.responsable_nom || '—' }}</td>
                    <td>
                      <span class="inv-badge" [attr.data-statut]="inv.statut">
                        <mat-icon>{{ statutIcon(inv.statut) }}</mat-icon>{{ statutLabel(inv.statut) }}
                      </span>
                    </td>
                    <td class="inv-progress-cell">
                      <div class="inv-progress" [attr.data-complet]="inv.stats.progression >= 100">
                        <span [style.width.%]="inv.stats.progression"></span>
                      </div>
                      <small>{{ inv.stats.comptes }} / {{ inv.stats.a_compter }} · {{ inv.stats.progression }} %</small>
                    </td>
                    <td class="inv-num">
                      <span class="inv-ecart" data-signe="moins">{{ inv.stats.ecarts_negatifs }}</span> /
                      <span class="inv-ecart" data-signe="plus">{{ inv.stats.ecarts_positifs }}</span>
                    </td>
                    <td class="inv-num">
                      <span class="inv-ecart" [attr.data-signe]="ton(inv.stats.ecart_net)">{{ signe(inv.stats.ecart_net) }}</span>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="8" class="bea-mg__empty">
                      <mat-icon>fact_check</mat-icon>
                      <p>{{ filtresActifs() ? 'Aucun inventaire ne correspond aux filtres.' : 'Aucun inventaire pour le moment.' }}</p>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="inv-cards">
            @for (inv of items(); track inv.id) {
              <button type="button" class="inv-card" (click)="ouvrir(inv)">
                <header>
                  <code class="bea-mg__code">{{ inv.reference }}</code>
                  <span class="inv-badge" [attr.data-statut]="inv.statut">{{ statutLabel(inv.statut) }}</span>
                </header>
                <p>{{ inv.periode_libelle }} · {{ inv.agence_libelle || 'Toutes agences' }}</p>
                <div class="inv-progress" [attr.data-complet]="inv.stats.progression >= 100">
                  <span [style.width.%]="inv.stats.progression"></span>
                </div>
                <footer>
                  <span>{{ inv.stats.comptes }} / {{ inv.stats.a_compter }} comptés</span>
                  <span>{{ inv.stats.ecarts_negatifs + inv.stats.ecarts_positifs }} écart(s)</span>
                  <span class="inv-ecart" [attr.data-signe]="ton(inv.stats.ecart_net)">{{ signe(inv.stats.ecart_net) }}</span>
                </footer>
              </button>
            } @empty {
              <p class="bea-mg__empty">Aucun inventaire.</p>
            }
          </div>
          @if (total() > taille) {
            <app-pagination [page]="page()" [total]="total()" [pageSize]="taille" label="inventaire(s)" (pageChange)="allerPage($event)" />
          }
        }
      </div>

      @if (creationOuverte()) {
        <div class="bea-mg__backdrop" (click)="fermerCreation()" role="presentation"></div>
        <div class="bea-mg__modal" role="dialog" aria-modal="true" aria-label="Nouvel inventaire">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Création</p>
              <h2>Nouvel inventaire mensuel</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="fermerCreation()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <form [formGroup]="creation" (ngSubmit)="creer()">
            <div class="bea-mg__modal-body">
              <div class="bea-mg__grid">
                <label>
                  Date d’inventaire *
                  <input type="date" formControlName="date_debut" [max]="aujourdhui" />
                </label>
                <label>
                  Période
                  <input [value]="periodeCreation()" disabled />
                </label>
                <label>
                  Agence
                  <select formControlName="agence_id">
                    <option value="">Toutes agences</option>
                    @for (a of agences(); track a.id) {
                      <option [value]="a.id">{{ a.libelle }}</option>
                    }
                  </select>
                </label>
                <label>
                  Famille
                  <select formControlName="famille_id">
                    <option value="">Toutes familles</option>
                    @for (f of familles(); track f.id) {
                      <option [value]="f.id">{{ f.libelle }}</option>
                    }
                  </select>
                </label>
                <label class="bea-mg__span2">
                  Responsable de l’inventaire
                  <input formControlName="responsable_nom" maxlength="160" />
                </label>
                <label class="bea-mg__span2">
                  Libellé
                  <input formControlName="libelle" maxlength="255" [placeholder]="'Inventaire ' + periodeCreation()" />
                </label>
                <label class="bea-mg__span2">
                  Observations
                  <textarea formControlName="observation" rows="2"></textarea>
                </label>
              </div>
              <ul class="inv-msgs">
                <li data-ton="info">
                  <mat-icon>info</mat-icon>
                  <span>Le numéro (INV-AAAA-MM-NNN) est attribué automatiquement. Le stock théorique de chaque article
                    du périmètre est figé à la date choisie ; un seul inventaire par périmètre et par mois.</span>
                </li>
              </ul>
            </div>
            <footer class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerCreation()">Annuler</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="creation.invalid || enCours()">
                <mat-icon>add</mat-icon> Créer l’inventaire
              </button>
            </footer>
          </form>
        </div>
      }

      @if (importOuvert()) {
        <div class="bea-mg__backdrop" (click)="fermerImport()" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--lg" style="width:min(64rem, calc(100vw - 1.5rem))" role="dialog" aria-modal="true" aria-label="Importer un inventaire Excel">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Import Excel</p>
              <h2>Importer un inventaire</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="fermerImport()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="bea-mg__modal-body">
            <ol class="inv-steps">
              <li [attr.data-actif]="!analyse()" [attr.data-fait]="!!analyse()"><mat-icon>upload_file</mat-icon> 1. Fichier</li>
              <li [attr.data-actif]="!!analyse()"><mat-icon>rule</mat-icon> 2. Contrôle &amp; mapping</li>
              <li><mat-icon>check</mat-icon> 3. Import</li>
            </ol>

            <form [formGroup]="importForm" class="bea-mg__grid">
              <label class="bea-mg__span2 inv-drop" [attr.data-actif]="!!fichier()" (dragover)="$event.preventDefault()" (drop)="deposer($event)">
                <mat-icon>{{ fichier() ? 'description' : 'cloud_upload' }}</mat-icon>
                <strong>{{ fichier()?.name || 'Choisir ou déposer le fichier Excel (.xlsx)' }}</strong>
                <small>Colonnes attendues : Réf./Code, Article, Stock théorique, Stock physique… (détection automatique)</small>
                <input type="file" accept=".xlsx,.xlsm" (change)="choisirFichier($event)" />
              </label>
              <label>
                Date d’inventaire *
                <input type="date" formControlName="date_inventaire" [max]="aujourdhui" />
              </label>
              <label>
                Agence (périmètre)
                <select formControlName="agence_id">
                  <option value="">Toutes agences</option>
                  @for (a of agences(); track a.id) {
                    <option [value]="a.id">{{ a.libelle }}</option>
                  }
                </select>
              </label>
              <label>
                Responsable
                <input formControlName="responsable_nom" maxlength="160" />
              </label>
              <label>
                Observations
                <input formControlName="observation" />
              </label>
            </form>

            @if (analyse(); as a) {
              <h3 class="inv-section-title" style="margin-top:1rem">Résultat de l’analyse · feuille « {{ a.feuille }} », en-tête ligne {{ a.ligne_entete }} · {{ a.periode }}</h3>
              <div class="inv-resume">
                <div><span>Lignes détectées</span><strong>{{ a.resume['lignes_detectees'] }}</strong></div>
                <div><span>À importer</span><strong>{{ a.resume['a_importer'] }}</strong></div>
                <div><span>Comptés</span><strong>{{ a.resume['comptes'] }}</strong></div>
                <div [attr.data-ton]="a.resume['exclus'] ? 'warn' : null"><span>Exclus</span><strong>{{ a.resume['exclus'] }}</strong></div>
                <div [attr.data-ton]="a.resume['ecarts_physique_systeme'] ? 'warn' : null"><span>Écarts</span><strong>{{ a.resume['ecarts_physique_systeme'] }}</strong></div>
                <div [attr.data-ton]="a.resume['inconnus'] ? 'bad' : null"><span>Inconnus</span><strong>{{ a.resume['inconnus'] }}</strong></div>
                <div [attr.data-ton]="a.resume['doublons'] ? 'bad' : null"><span>Doublons</span><strong>{{ a.resume['doublons'] }}</strong></div>
                <div [attr.data-ton]="a.resume['quantites_invalides'] ? 'bad' : null"><span>Qté invalides</span><strong>{{ a.resume['quantites_invalides'] }}</strong></div>
                <div [attr.data-ton]="a.resume['sans_code'] ? 'warn' : null"><span>Sans code</span><strong>{{ a.resume['sans_code'] }}</strong></div>
              </div>
              <ul class="inv-msgs">
                @for (m of a.anomalies; track m) {
                  <li data-ton="bad"><mat-icon>error</mat-icon><span>{{ m }}</span></li>
                }
                @for (m of a.avertissements; track m) {
                  <li data-ton="warn"><mat-icon>warning</mat-icon><span>{{ m }}</span></li>
                }
                @if (!a.bloquant) {
                  <li data-ton="info"><mat-icon>check_circle</mat-icon><span>Aucune anomalie bloquante : l’inventaire peut être importé. Il sera créé « En cours », sans validation ni ajustement.</span></li>
                }
              </ul>

              <details style="margin:.5rem 0" [open]="a.colonnes_ambigues.length > 0">
                <summary style="cursor:pointer;font-weight:600;color:#1a5278">Mapping des colonnes</summary>
                <div class="inv-mapping" style="margin-top:.6rem">
                  @for (c of a.champs; track c.champ) {
                    <label>
                      {{ c.libelle }}{{ c.obligatoire ? ' *' : '' }}
                      <select [value]="mappingChoisi()[c.champ] ?? a.mapping[c.champ] ?? ''" (change)="changerMapping(c.champ, $event)">
                        <option value="">— non utilisée —</option>
                        @for (e of a.entetes; track e) {
                          <option [value]="e">{{ e }}</option>
                        }
                      </select>
                    </label>
                  }
                </div>
                @if (a.colonnes_ignorees.length) {
                  <p style="font-size:.78rem;color:#64748b">Colonnes ignorées : {{ a.colonnes_ignorees.join(', ') }}</p>
                }
              </details>

              <div class="inv-tabs" role="tablist">
                @for (t of importFiltres; track t.id) {
                  <button type="button" [attr.data-actif]="importFiltre() === t.id" (click)="importFiltre.set(t.id)">
                    {{ t.label }} ({{ compterImport(t.id) }})
                  </button>
                }
              </div>
              <div class="inv-preview">
                <table class="bea-mg__table">
                  <thead>
                    <tr>
                      <th>Ligne</th>
                      <th>Code</th>
                      <th>Article</th>
                      <th class="inv-num">Théo. fichier</th>
                      <th class="inv-num">Théo. système</th>
                      <th class="inv-num">Physique</th>
                      <th class="inv-num">Écart</th>
                      <th>Statut</th>
                      <th>Résolution / remarques</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (l of lignesImport(); track l.ligne) {
                      <tr [attr.data-bloquant]="estBloquant(l)">
                        <td>{{ l.ligne }}</td>
                        <td><code>{{ l.code || '—' }}</code></td>
                        <td>{{ l.designation }}</td>
                        <td class="inv-num">{{ l.stock_theorique_fichier ?? '—' }}</td>
                        <td class="inv-num">{{ l.stock_theorique_systeme ?? '—' }}</td>
                        <td class="inv-num">{{ l.stock_physique ?? '—' }}</td>
                        <td class="inv-num"><span class="inv-ecart" [attr.data-signe]="ton(l.ecart)">{{ l.ecart == null ? '—' : signe(l.ecart) }}</span></td>
                        <td><span class="inv-badge">{{ importStatut(l.statut) }}</span></td>
                        <td>
                          @if (estBloquant(l) || l.statut === 'IGNORE' || resolutions()[l.ligne]) {
                            <select [value]="resolutions()[l.ligne] || ''" (change)="resoudre(l.ligne, $event)" aria-label="Résolution">
                              <option value="">— à résoudre —</option>
                              <option value="IGNORER">Ignorer cette ligne</option>
                              @for (art of articles(); track art.id) {
                                <option [value]="art.id">{{ art.code }} — {{ art.designation }}</option>
                              }
                            </select>
                          }
                          @for (m of l.anomalies; track m) {
                            <small style="display:block;color:#b91c1c">{{ m }}</small>
                          }
                          @for (m of l.avertissements; track m) {
                            <small style="display:block;color:#92400e">{{ m }}</small>
                          }
                        </td>
                      </tr>
                    } @empty {
                      <tr><td colspan="9" class="bea-mg__empty">Aucune ligne dans ce filtre.</td></tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerImport()">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!fichier() || importForm.invalid || enCours()" (click)="analyser()">
              <mat-icon>rule</mat-icon> {{ analyse() ? 'Ré-analyser' : 'Analyser le fichier' }}
            </button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!analyse() || analyse()!.bloquant || analyseObsolete() || enCours()" (click)="importer()"
              [title]="analyseObsolete() ? 'Ré-analysez après vos modifications' : ''">
              <mat-icon>download_done</mat-icon> Importer {{ analyse()?.resume?.['a_importer'] ?? '' }} ligne(s)
            </button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class StockInventairesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);

  readonly mois = MOIS;
  readonly statuts = Object.keys(STATUT_LABELS) as InventaireStatut[];
  readonly aujourdhui = aujourdhui();
  readonly taille = 20;
  readonly signe = signe;

  readonly items = signal<Inventaire[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly chargement = signal(false);
  readonly synthese = signal<InventaireSynthese | null>(null);
  readonly agences = signal<RefOption[]>([]);
  readonly familles = signal<RefOption[]>([]);
  readonly enCours = signal(false);

  readonly peutSaisir = computed(() => aPermission(this.auth.user(), PERM.saisie));
  readonly peutExporter = computed(() => aPermission(this.auth.user(), PERM.export));

  readonly filtres = this.fb.nonNullable.group({
    q: '',
    mois: '',
    annee: '',
    statut: '',
    agence_id: '',
    ecarts: '',
  });
  private readonly valeursFiltres = signal(this.filtres.getRawValue());
  readonly filtresActifs = computed(() => Object.values(this.valeursFiltres()).some((v) => `${v}`.trim() !== ''));

  readonly creationOuverte = signal(false);
  readonly creation = this.fb.nonNullable.group({
    date_debut: [this.aujourdhui, Validators.required],
    agence_id: '',
    famille_id: '',
    responsable_nom: '',
    libelle: '',
    observation: '',
  });
  private readonly dateCreation = signal(this.aujourdhui);
  readonly periodeCreation = computed(() => {
    const d = this.dateCreation();
    if (!d) return '—';
    const [y, m] = d.split('-').map(Number);
    return `${MOIS[m - 1]} ${y}`;
  });

  readonly importOuvert = signal(false);
  readonly fichier = signal<File | null>(null);
  readonly analyse = signal<ImportAnalyse | null>(null);
  readonly analyseObsolete = signal(false);
  readonly mappingChoisi = signal<Partial<Record<string, string>>>({});
  readonly resolutions = signal<Record<number, string>>({});
  readonly articles = signal<ArticleOption[]>([]);
  readonly importFiltre = signal<ImportFiltre>('tous');
  readonly importFiltres: { id: ImportFiltre; label: string }[] = [
    { id: 'tous', label: 'Toutes' },
    { id: 'bloquants', label: 'À résoudre' },
    { id: 'ecarts', label: 'Écarts' },
    { id: 'exclus', label: 'Exclus' },
    { id: 'avertissements', label: 'Avertissements' },
  ];
  readonly importForm = this.fb.nonNullable.group({
    date_inventaire: [this.aujourdhui, Validators.required],
    agence_id: '',
    responsable_nom: '',
    observation: '',
  });
  readonly lignesImport = computed(() => {
    const a = this.analyse();
    if (!a) return [];
    const f = this.importFiltre();
    return a.lignes.filter((l) => this.matchImport(l, f));
  });

  readonly hasUnsavedChanges = unsavedChanges(
    () => (this.creationOuverte() && this.creation.dirty) || (this.importOuvert() && !!this.fichier()),
  );

  constructor() {
    this.filtres.valueChanges.pipe(debounceTime(300), takeUntilDestroyed()).subscribe(() => {
      this.valeursFiltres.set(this.filtres.getRawValue());
      this.page.set(1);
      this.charger();
    });
    this.creation.controls.date_debut.valueChanges.pipe(takeUntilDestroyed()).subscribe((d) => this.dateCreation.set(d));
    this.importForm.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      if (this.analyse()) this.analyseObsolete.set(true);
    });
  }

  ngOnInit(): void {
    this.api.get<RefOption[]>('/mg/stock/agences').subscribe({ next: (a) => this.agences.set(a) });
    this.api.get<RefOption[]>('/mg/stock/familles').subscribe({ next: (f) => this.familles.set(f) });
    this.charger();
    this.chargerSynthese();
  }

  statutLabel(s: InventaireStatut): string {
    return STATUT_LABELS[s] ?? s;
  }

  statutIcon(s: InventaireStatut): string {
    return STATUT_ICONS[s] ?? 'help';
  }

  ton(n: number | null | undefined): string {
    if (n == null) return '';
    return n < 0 ? 'moins' : n > 0 ? 'plus' : 'zero';
  }

  importStatut(s: string): string {
    return IMPORT_STATUTS[s] ?? s;
  }

  charger(): void {
    const v = this.filtres.getRawValue();
    const params: Record<string, string | number> = { page: this.page(), size: this.taille };
    for (const [k, val] of Object.entries(v)) {
      if (`${val}`.trim()) params[k] = `${val}`.trim();
    }
    this.chargement.set(true);
    this.api.get<Paginated<Inventaire>>('/mg/stock/inventaires', params).subscribe({
      next: (r) => {
        this.items.set(r.items);
        this.total.set(r.total);
        this.chargement.set(false);
      },
      error: () => {
        this.chargement.set(false);
        this.feedback.error({ title: 'Chargement des inventaires impossible' });
      },
    });
  }

  chargerSynthese(): void {
    this.api.get<InventaireSynthese>('/mg/stock/inventaires/synthese').subscribe({ next: (s) => this.synthese.set(s) });
  }

  allerPage(p: number): void {
    this.page.set(p);
    this.charger();
  }

  filtrerStatut(statut: InventaireStatut): void {
    this.filtres.patchValue({ statut });
  }

  reinitialiser(): void {
    this.filtres.reset({ q: '', mois: '', annee: '', statut: '', agence_id: '', ecarts: '' });
  }

  ouvrir(inv: Inventaire): void {
    this.router.navigate(['/stock-fournitures/inventaires', inv.id]);
  }

  exporter(format: 'xlsx' | 'pdf'): void {
    const params: Record<string, string> = { format };
    for (const [k, val] of Object.entries(this.filtres.getRawValue())) {
      if (`${val}`.trim()) params[k] = `${val}`.trim();
    }
    this.feedback
      .run(() => this.api.download('/mg/stock/inventaires/export', params), {
        loading: `Export ${format.toUpperCase()}…`,
        errorTitle: 'Export impossible',
        success: () => null,
      })
      .subscribe((blob) => downloadBlob(blob, `inventaires-stock.${format}`));
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.importOuvert()) this.fermerImport();
    else if (this.creationOuverte()) this.fermerCreation();
  }

  ouvrirCreation(): void {
    this.creation.reset({
      date_debut: this.aujourdhui,
      agence_id: '',
      famille_id: '',
      responsable_nom: this.auth.user()?.full_name ?? '',
      libelle: '',
      observation: '',
    });
    this.dateCreation.set(this.aujourdhui);
    this.creationOuverte.set(true);
  }

  fermerCreation(): void {
    this.creationOuverte.set(false);
    this.creation.markAsPristine();
  }

  creer(): void {
    if (this.creation.invalid) return;
    const v = this.creation.getRawValue();
    const body: Record<string, unknown> = { date_debut: v.date_debut };
    for (const k of ['agence_id', 'famille_id', 'responsable_nom', 'libelle', 'observation'] as const) {
      if (v[k].trim()) body[k] = v[k].trim();
    }
    this.feedback
      .run(() => this.api.post<Inventaire>('/mg/stock/inventaires', body), {
        loading: 'Création de l’inventaire…',
        busy: this.enCours,
        idempotent: true,
        errorTitle: 'Création refusée',
        errorHint: 'Vos saisies ont été conservées.',
        success: (inv) => ({
          title: 'Inventaire créé',
          details: [
            { label: 'Référence', value: inv.reference },
            { label: 'Articles à compter', value: String(inv.stats.a_compter) },
          ],
        }),
      })
      .subscribe((inv) => {
        this.fermerCreation();
        this.ouvrir(inv);
      });
  }

  ouvrirImport(): void {
    this.fichier.set(null);
    this.analyse.set(null);
    this.mappingChoisi.set({});
    this.resolutions.set({});
    this.importFiltre.set('tous');
    this.importForm.reset({
      date_inventaire: this.aujourdhui,
      agence_id: '',
      responsable_nom: this.auth.user()?.full_name ?? '',
      observation: '',
    });
    this.importOuvert.set(true);
    if (!this.articles().length) {
      this.api.get<Paginated<ArticleOption>>('/mg/stock/articles', { size: 500 }).subscribe({
        next: (r) => this.articles.set(r.items),
      });
    }
  }

  fermerImport(): void {
    this.importOuvert.set(false);
    this.fichier.set(null);
  }

  choisirFichier(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.prendreFichier(input.files?.[0] ?? null);
    input.value = '';
  }

  deposer(event: DragEvent): void {
    event.preventDefault();
    this.prendreFichier(event.dataTransfer?.files?.[0] ?? null);
  }

  private prendreFichier(file: File | null): void {
    if (!file) return;
    if (!/\.(xlsx|xlsm)$/i.test(file.name)) {
      this.feedback.warning({ title: 'Format non pris en charge', message: 'Choisissez un classeur Excel .xlsx.' });
      return;
    }
    this.fichier.set(file);
    this.analyse.set(null);
    this.mappingChoisi.set({});
    this.resolutions.set({});
  }

  changerMapping(champ: string, event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    this.mappingChoisi.update((m) => ({ ...m, [champ]: val }));
    this.analyseObsolete.set(true);
  }

  resoudre(ligne: number, event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    this.resolutions.update((r) => {
      const next = { ...r };
      if (val) next[ligne] = val;
      else delete next[ligne];
      return next;
    });
    this.analyseObsolete.set(true);
  }

  estBloquant(l: ImportLigne): boolean {
    return BLOQUANTS.has(l.statut);
  }

  private matchImport(l: ImportLigne, f: ImportFiltre): boolean {
    switch (f) {
      case 'bloquants':
        return this.estBloquant(l);
      case 'ecarts':
        return !!l.ecart;
      case 'exclus':
        return l.statut === 'EXCLU' || l.statut === 'IGNORE' || l.statut === 'HORS_PERIMETRE';
      case 'avertissements':
        return l.avertissements.length > 0;
      default:
        return true;
    }
  }

  compterImport(f: ImportFiltre): number {
    return this.analyse()?.lignes.filter((l) => this.matchImport(l, f)).length ?? 0;
  }

  private optionsImport(): string {
    const v = this.importForm.getRawValue();
    const d = v.date_inventaire;
    const opts: Record<string, unknown> = {
      date_inventaire: d,
      annee: Number(d.slice(0, 4)),
      mois: Number(d.slice(5, 7)),
      mapping: this.mappingChoisi(),
      resolutions: Object.fromEntries(Object.entries(this.resolutions()).map(([k, val]) => [String(k), val])),
    };
    if (v.agence_id) opts['agence_id'] = v.agence_id;
    if (v.responsable_nom.trim()) opts['responsable_nom'] = v.responsable_nom.trim();
    if (v.observation.trim()) opts['observation'] = v.observation.trim();
    const feuille = this.analyse()?.feuille;
    if (feuille) opts['feuille'] = feuille;
    return JSON.stringify(opts);
  }

  analyser(): void {
    const file = this.fichier();
    if (!file) return;
    this.feedback
      .run(() => this.api.upload<ImportAnalyse>('/mg/stock/inventaires/import/analyse', file, { options: this.optionsImport() }), {
        loading: 'Analyse du fichier…',
        busy: this.enCours,
        errorTitle: 'Analyse impossible',
        success: () => null,
      })
      .subscribe((a) => {
        this.analyse.set(a);
        this.analyseObsolete.set(false);
        if (a.bloquant && a.resume['inconnus'] + a.resume['doublons'] + a.resume['quantites_invalides'] > 0) {
          this.importFiltre.set('bloquants');
        }
      });
  }

  importer(): void {
    const file = this.fichier();
    const a = this.analyse();
    if (!file || !a || a.bloquant) return;
    this.feedback
      .run(
        () =>
          this.api.upload<{ inventaire: Inventaire; resume: Record<string, number> }>(
            '/mg/stock/inventaires/import',
            file,
            { options: this.optionsImport() },
          ),
        {
          confirm: {
            action: 'enregistrement',
            title: 'Importer l’inventaire',
            message: `Créer l’inventaire ${a.periode} à partir de « ${a.fichier} » (${a.resume['a_importer']} articles) ?`,
            hint: 'L’inventaire sera créé « En cours ». Aucune validation ni aucun ajustement de stock ne sera effectué.',
          },
          loading: 'Import en cours…',
          busy: this.enCours,
          idempotent: true,
          errorTitle: 'Import refusé',
          success: (r) => ({
            title: 'Inventaire importé',
            details: [
              { label: 'Référence', value: r.inventaire.reference },
              { label: 'Articles comptés', value: String(r.resume['comptes']) },
              { label: 'Écarts', value: String(r.resume['ecarts_physique_systeme']) },
            ],
          }),
        },
      )
      .subscribe((r) => {
        this.fermerImport();
        this.ouvrir(r.inventaire);
      });
  }
}
