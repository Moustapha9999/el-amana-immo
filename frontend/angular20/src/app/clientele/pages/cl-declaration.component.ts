import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { PaginationComponent } from '../../shared/pagination.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateFr, telecharger, valeurIndic } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface FicheBcm {
  libelle_officiel: string; tableau: string; ligne: string; colonne: string;
  colonne_libelle: string; definition: string; periode: string;
  population: string | null; source: string | null; formule: string | null;
  classification_utilisee: string; eer_utilise: boolean; historique_utilise: boolean;
  validation_metier: string; reserve: string | null;
}
interface Cellule {
  code: string; valeur: number | null; ratio: number | null; statut: string;
  indicateur: string | null; cutoff: string; reserve: string | null; fiche?: FicheBcm | null;
}
interface Ligne { code: string; libelle: string; definition: string; cellules: Record<string, Cellule>; }
interface Colonne { code: string; libelle: string; }
interface Tableau {
  code: string; titre: string; sous_titre: string; type: string;
  colonnes: Colonne[]; lignes: Ligne[];
}
interface Controle {
  code: string; libelle: string; ok: boolean; bloquant: boolean;
  attendu: number | null; observe: number | null; message: string;
  niveau?: 'CONFORME' | 'ATTENTION' | 'ERREUR';
}
interface Actions {
  calculer: boolean; controler: boolean; valider: boolean; cloturer: boolean;
  archiver: boolean; supprimer: boolean; exporter: boolean;
}
interface Declaration {
  id: string; annee: number; mois: number; libelle: string;
  date_debut: string; date_fin: string; fin_mois_precedent: string;
  statut: string; moteur_version: string | null; grille_version: string | null;
  simulation: boolean; bcm_officielle: boolean; commentaire: string | null;
  cellules: { tableaux: Tableau[]; mappings?: Record<string, string> } | null;
  controles: Controle[]; actions: Actions;
}
interface Detail extends Cellule {
  calcule: boolean; total: number; page: number; taille: number;
  colonnes: string[]; items: Record<string, string | number | null>[];
  source: string; figee?: boolean; ligne?: string; tableau?: string;
}

const ETAPES = ['BROUILLON', 'CALCULEE', 'A_CONTROLER', 'VALIDEE', 'CLOTUREE', 'ARCHIVEE'];

@Component({
  selector: 'bea-cl-declaration',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, PaginationComponent, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker"><a routerLink="/clientele/declarations">Déclarations BCM</a></p>
          <h1>{{ d()?.libelle ?? 'Déclaration' }}</h1>
          <p class="bea-cl-head__sub">{{ dateFr(d()?.date_debut) }} → {{ dateFr(d()?.date_fin) }} · fin mois précédent {{ dateFr(d()?.fin_mois_precedent) }} · moteur {{ d()?.moteur_version ?? '—' }}</p>
        </div>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
          @if (d()?.actions?.exporter && store.cap().exporter) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('xlsx')"><mat-icon>download</mat-icon> Excel</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
          }
        </div>
      </header>
      @if (d(); as x) {
        <ol class="bea-cl-steps">
          @for (s of etapes; track s) {
            <li [class.is-on]="x.statut===s" [class.is-done]="rang(x.statut) > rang(s)">{{ s.replaceAll('_', ' ') }}</li>
          }
        </ol>
        @if (x.simulation) {
          <p class="bea-cl-note"><mat-icon>info</mat-icon>Mois non clos — préparation uniquement. La validation officielle est bloquée tant que le mois n’est pas terminé.</p>
        }
        <div class="bea-cl-bar">
          <span class="bea-cl-badge" [attr.data-s]="x.statut">{{ x.statut.replaceAll('_', ' ') }}</span>
          <div style="display:flex;gap:0.45rem;flex-wrap:wrap">
            @if (x.actions.calculer && store.cap().bcm_preparer) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="agir('calculer', 'Calculer')" [disabled]="busy()"><mat-icon>calculate</mat-icon> Calculer</button>
            }
            @if (x.actions.controler && store.cap().bcm_preparer) {
              <button type="button" class="bea-mg__btn" (click)="agir('controler', 'Soumettre au contrôle', { action: 'validation', title: 'Soumettre au contrôle', message: 'Passer en à contrôler ?' })"><mat-icon>rule</mat-icon> Contrôle</button>
            }
            @if (x.actions.valider && store.cap().bcm_valider) {
              <button type="button" class="bea-mg__btn" (click)="agir('valider', 'Valider', { action: 'validation', title: 'Valider la déclaration', message: 'Figer le snapshot ? Elle ne se recalculera plus.', hint: 'Les cellules À CONFIGURER restent vides.' })"><mat-icon>verified</mat-icon> Valider</button>
            }
            @if (x.actions.cloturer && store.cap().bcm_cloturer) {
              <button type="button" class="bea-mg__btn" (click)="agir('cloturer', 'Clôturer', { action: 'validation', title: 'Clôturer', message: 'Clôturer cette déclaration validée ?' })"><mat-icon>lock</mat-icon> Clôturer</button>
            }
            @if (x.actions.archiver && store.cap().bcm_cloturer) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="agir('archiver', 'Archiver', { action: 'validation', title: 'Archiver', message: 'Archiver cette déclaration clôturée ?' })"><mat-icon>inventory_2</mat-icon> Archiver</button>
            }
            @if (x.actions.supprimer && store.cap().admin) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="supprimer()"><mat-icon>delete</mat-icon> Supprimer</button>
            }
          </div>
        </div>
        @if (x.controles.length) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Contrôles</h2></div>
            <ul class="bea-cl-anoms">
              @for (c of x.controles; track c.code) {
                <li [attr.data-n]="c.niveau === 'CONFORME' || c.ok ? 'info' : (c.niveau === 'ERREUR' || c.bloquant ? 'bloquant' : 'alerte')">
                  <mat-icon>{{ c.ok ? 'check_circle' : (c.bloquant ? 'error' : 'warning') }}</mat-icon>
                  <span><strong>{{ c.niveau ?? (c.ok ? 'CONFORME' : 'ATTENTION') }}</strong> — {{ c.libelle }} : {{ c.message }} (attendu {{ c.attendu ?? '—' }}, observé {{ c.observe ?? '—' }})</span>
                </li>
              }
            </ul>
          </section>
        }
        @for (tab of x.cellules?.tableaux ?? []; track tab.code) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>{{ tab.code }} — {{ tab.titre }}</h2></div>
            <p class="bea-cl-hint" style="padding:0 1.1rem">{{ tab.sous_titre }}</p>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table bea-cl-bcm">
                <thead>
                  <tr>
                    <th>Déclarations</th>
                    @for (col of tab.colonnes; track col.code) { <th>{{ col.libelle }}</th> }
                  </tr>
                </thead>
                <tbody>
                  @for (ligne of tab.lignes; track ligne.code) {
                    <tr>
                      <td>{{ ligne.libelle }}</td>
                      @for (col of tab.colonnes; track col.code) {
                        <td>
                          @if (ligne.cellules[col.code]; as cell) {
                            <button type="button" [class.is-lock]="cell.statut==='A_CONFIGURER'" [class.is-on]="choisi()===cell.code" (click)="ouvrir(cell)">{{ afficher(cell) }}</button>
                          }
                        </td>
                      }
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }
        @if (detail(); as det) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Population — {{ det.code }}</h2></div>
            <dl class="bea-cl-dl">
              @if (det.fiche; as f) {
                <dt>Libellé officiel</dt><dd>{{ f.libelle_officiel }}</dd>
                <dt>Tableau</dt><dd>{{ f.tableau }} · {{ f.colonne_libelle }}</dd>
                <dt>Définition</dt><dd>{{ f.definition }}</dd>
                <dt>Période</dt><dd>{{ f.periode }}</dd>
                <dt>Population</dt><dd>{{ f.population ?? '—' }}</dd>
                <dt>Source BEA-DIGITAL</dt><dd>{{ f.source ?? '—' }}@if (det.figee) { (déclaration figée) }</dd>
                <dt>Formule</dt><dd><code>{{ f.formule || 'À CONFIGURER' }}</code></dd>
                <dt>Classification</dt><dd>{{ f.classification_utilisee }}</dd>
                <dt>EER</dt><dd>{{ f.eer_utilise ? 'oui' : 'non' }}</dd>
                <dt>Historique</dt><dd>{{ f.historique_utilise ? 'oui' : 'non' }}</dd>
                <dt>Validation métier</dt><dd><span class="bea-cl-badge" [attr.data-s]="f.validation_metier">{{ f.validation_metier }}</span></dd>
                @if (f.reserve) { <dt>Réserve</dt><dd>{{ f.reserve }}</dd> }
              } @else {
                @if (det.ligne) { <dt>Ligne</dt><dd>{{ det.ligne }}</dd> }
                <dt>Statut</dt><dd><span class="bea-cl-badge" [attr.data-s]="det.statut">{{ det.statut }}</span></dd>
                @if (det.reserve) { <dt>Réserve</dt><dd>{{ det.reserve }}</dd> }
                <dt>Source</dt><dd>{{ det.source }}@if (det.figee) { (déclaration figée) }</dd>
              }
            </dl>
            @if (!det.calcule) {
              <p class="bea-cl-note"><mat-icon>block</mat-icon>Aucun chiffre n’est produit tant que la Conformité n’a pas défini cet indicateur.</p>
            } @else {
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead><tr>@for (c of det.colonnes; track c) { <th>{{ c }}</th> }</tr></thead>
                  <tbody>
                    @for (r of det.items; track $index) {
                      <tr>
                        @for (c of det.colonnes; track c) {
                          <td>
                            @if (c === 'racine_client' && r[c]) {
                              <a [routerLink]="['/clientele/clients', r[c]]"><code>{{ r[c] }}</code></a>
                            } @else { {{ r[c] ?? '—' }} }
                          </td>
                        }
                      </tr>
                    } @empty {
                      <tr><td [attr.colspan]="det.colonnes.length"><div class="bea-cl-empty">Aucune ligne.</div></td></tr>
                    }
                  </tbody>
                </table>
              </div>
              <app-pagination [page]="det.page" [total]="det.total" [pageSize]="det.taille" label="lignes" (pageChange)="page.set($event); chargerDetail()" />
            }
          </section>
        }
      }
    </div>
  `,
})
export class ClDeclarationComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  readonly d = signal<Declaration | null>(null);
  readonly detail = signal<Detail | null>(null);
  readonly choisi = signal<string | null>(null);
  readonly page = signal(1);
  readonly busy = signal(false);
  readonly dateFr = dateFr;
  readonly etapes = ETAPES;

  ngOnInit(): void {
    this.store.charger();
    this.route.paramMap.subscribe(() => this.charger());
  }

  id(): string {
    return this.route.snapshot.paramMap.get('id') ?? '';
  }

  rang(s: string): number {
    return ETAPES.indexOf(s);
  }

  afficher(cell: Cellule): string {
    if (cell.code.endsWith('.ratio') && cell.valeur != null) return `${cell.valeur} %`;
    return valeurIndic(cell.statut, cell.valeur);
  }

  charger(): void {
    this.api.get<Declaration>(`${CL_BASE}/declarations/${this.id()}`).subscribe({
      next: (d) => this.d.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Déclaration indisponible')),
    });
  }

  ouvrir(cell: Cellule): void {
    this.choisi.set(cell.code);
    this.page.set(1);
    this.chargerDetail();
  }

  chargerDetail(): void {
    const code = this.choisi();
    if (!code) return;
    this.api.get<Detail>(`${CL_BASE}/declarations/${this.id()}/cellules/${code}`, {
      page: this.page(), taille: 50,
    }).subscribe({
      next: (d) => this.detail.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Population indisponible')),
    });
  }

  agir(action: string, titre: string, confirm?: { action: 'validation'; title: string; message: string; hint?: string }): void {
    this.feedback.run(() => this.api.post<Declaration>(`${CL_BASE}/declarations/${this.id()}/${action}`, {}), {
      confirm,
      busy: this.busy,
      loading: `${titre}…`,
      success: { title: `${titre} effectué` },
      errorTitle: 'Action impossible',
    }).subscribe((d) => {
      this.d.set(d);
      if (this.choisi()) this.chargerDetail();
    });
  }

  supprimer(): void {
    this.feedback.run(() => this.api.delete<void>(`${CL_BASE}/declarations/${this.id()}`), {
      confirm: { action: 'suppression', title: 'Supprimer le brouillon', message: 'Supprimer cette déclaration en brouillon ?' },
      busy: this.busy, success: { title: 'Déclaration supprimée' }, errorTitle: 'Suppression impossible',
    }).subscribe(() => void this.router.navigate(['/clientele/declarations']));
  }

  exporter(format: 'xlsx' | 'pdf'): void {
    const nom = `declaration-bcm-${this.d()?.annee}-${String(this.d()?.mois).padStart(2, '0')}.${format}`;
    this.api.download(`${CL_BASE}/declarations/${this.id()}/export.${format}`).subscribe({
      next: (b) => telecharger(b, nom),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible')),
    });
  }
}
