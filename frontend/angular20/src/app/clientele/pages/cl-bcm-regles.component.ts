import { ChangeDetectionStrategy, Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, dateFr } from '../clientele.models';

export interface RegleBcm {
  code: string; libelle: string; explication: string; valeur: unknown;
  statut: 'CONFIRMEE' | 'A_VALIDER'; origine: string;
  valeur_defaut?: unknown; decidee?: boolean; decidee_le?: string | null;
}
interface Observe { valeur: string; nombre: number; }
interface ReglesOut {
  regles: RegleBcm[];
  historique: { code: string; valeur: unknown; statut: string; motif: string; par: string | null; le: string | null }[];
  observe: { categories_juridiques: Observe[]; statuts_gel: Observe[] };
  modifiable: boolean;
}
type Editeur = 'fixe' | 'liste' | 'interdit' | 'fenetre' | 'bool' | 'formes';
interface Brouillon {
  code: string; statut: 'CONFIRMEE' | 'A_VALIDER'; liste: string; interdit: string;
  type: string; annees: number; bool: boolean; pp: string; pm: string; cj: string;
}

const EDITEURS: Record<string, Editeur> = {
  'actif.valeurs_gel': 'liste', 'maj.evenements': 'liste', 'interdit.rattachement': 'interdit',
  'maj.fenetre': 'fenetre', 'forme.repli_profil': 'bool', 'forme.correspondance': 'formes',
};

export function texteRegle(v: unknown): string {
  if (Array.isArray(v)) return v.length ? v.join(', ') : '—';
  if (typeof v === 'boolean') return v ? 'oui' : 'non';
  if (v && typeof v === 'object') {
    return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k} : ${texteRegle(x)}`).join(' · ');
  }
  return v == null ? '—' : String(v);
}

@Component({
  selector: 'bea-cl-bcm-regles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  template: `
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top">
        <h2>Règles de calcul</h2>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvert.set(!ouvert())">
          <mat-icon>{{ ouvert() ? 'expand_less' : 'tune' }}</mat-icon> {{ ouvert() ? 'Masquer les règles courantes' : 'Règles courantes et décisions' }}
        </button>
      </div>
      @if (appliquees().length) {
        <p class="bea-cl-hint" style="padding:0 1.1rem">Règles figées dans cette déclaration au moment du calcul.</p>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Règle</th><th>Valeur appliquée</th><th>Statut</th><th>Origine</th></tr></thead>
            <tbody>
              @for (r of appliquees(); track r.code) {
                <tr>
                  <td [title]="r.explication">{{ r.libelle }}</td>
                  <td>{{ texte(r.valeur) }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="r.statut === 'CONFIRMEE' ? 'VALIDEE' : 'A_CONTROLER'">{{ r.statut === 'CONFIRMEE' ? 'Confirmée' : 'À valider' }}</span></td>
                  <td>{{ r.origine }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
      @if (ouvert() && data(); as x) {
        <p class="bea-cl-note"><mat-icon>info</mat-icon>
          Une décision s’applique au prochain calcul. Une déclaration validée garde les règles de son calcul.</p>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Règle</th><th>Valeur courante</th><th>Statut</th><th>Origine</th>@if (x.modifiable) { <th></th> }</tr></thead>
            <tbody>
              @for (r of x.regles; track r.code) {
                <tr>
                  <td><strong>{{ r.libelle }}</strong><br /><span class="bea-cl-hint">{{ r.explication }}</span></td>
                  <td>{{ texte(r.valeur) }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="r.statut === 'CONFIRMEE' ? 'VALIDEE' : 'A_CONTROLER'">{{ r.statut === 'CONFIRMEE' ? 'Confirmée' : 'À valider' }}</span></td>
                  <td>{{ r.origine }}</td>
                  @if (x.modifiable) {
                    <td><button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="editer(r)"><mat-icon>edit</mat-icon> Décider</button></td>
                  }
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (brouillon(); as b) {
          <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); enregistrer()">
            <strong style="flex-basis:100%">{{ libelle(b.code) }}</strong>
            @switch (editeur(b.code)) {
              @case ('liste') {
                <label style="flex:1 1 24rem">Valeurs (séparées par des virgules)
                  <input [(ngModel)]="b.liste" name="liste" />
                </label>
                @if (b.code === 'actif.valeurs_gel') {
                  <p class="bea-cl-hint" style="flex-basis:100%">Valeurs observées :
                    @for (o of x.observe.statuts_gel; track o.valeur) { {{ o.valeur }} ({{ o.nombre }}) · }
                  </p>
                }
              }
              @case ('interdit') {
                <label>Rattachement
                  <select [(ngModel)]="b.interdit" name="interdit">
                    <option value="HORS_COLONNES">Hors colonnes (décompte séparé)</option>
                    <option value="ELEVE">Compté en risque élevé (déclaration uniquement)</option>
                  </select>
                </label>
              }
              @case ('fenetre') {
                <label>Type
                  <select [(ngModel)]="b.type" name="type">
                    <option value="CALENDAIRE">Calendaire (1er janvier Y-n)</option>
                    <option value="GLISSANTE">Glissante (12 × n mois)</option>
                  </select>
                </label>
                <label>Années<input type="number" min="1" max="10" [(ngModel)]="b.annees" name="annees" /></label>
              }
              @case ('bool') {
                <label><input type="checkbox" [(ngModel)]="b.bool" name="bool" /> Activer</label>
              }
              @case ('formes') {
                <label style="flex:1 1 16rem">Personnes physiques (une catégorie par ligne)<textarea rows="4" [(ngModel)]="b.pp" name="pp"></textarea></label>
                <label style="flex:1 1 16rem">Personnes morales<textarea rows="4" [(ngModel)]="b.pm" name="pm"></textarea></label>
                <label style="flex:1 1 16rem">Constructions juridiques<textarea rows="4" [(ngModel)]="b.cj" name="cj"></textarea></label>
                <p class="bea-cl-hint" style="flex-basis:100%">Catégories ORION observées :
                  @for (o of x.observe.categories_juridiques; track o.valeur) { {{ o.valeur }} ({{ o.nombre }}) · }
                </p>
              }
              @default {
                <p class="bea-cl-hint" style="flex-basis:100%">Valeur fixée par arbitrage : seul le statut est décidable.</p>
              }
            }
            <label>Statut
              <select [(ngModel)]="b.statut" name="statut">
                <option value="CONFIRMEE">Confirmée</option>
                <option value="A_VALIDER">À valider</option>
              </select>
            </label>
            <div style="display:flex;gap:0.45rem;align-items:flex-end">
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>gavel</mat-icon> Enregistrer la décision</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="brouillon.set(null)">Annuler</button>
            </div>
          </form>
        }
        @if (x.historique.length) {
          <p class="bea-cl-hint" style="padding:0.6rem 1.1rem 0">Historique des décisions (non modifiable)</p>
          <ol class="bea-cl-timeline" style="margin:0.4rem 1.1rem 0.9rem 1.6rem">
            @for (h of x.historique; track $index) {
              <li><strong>{{ libelle(h.code) }} → {{ texte(h.valeur) }} ({{ h.statut === 'CONFIRMEE' ? 'confirmée' : 'à valider' }})</strong>
                <span>{{ dateFr(h.le) }}{{ h.par ? ' · ' + h.par : '' }} — {{ h.motif }}</span></li>
            }
          </ol>
        }
      }
    </section>
  `,
})
export class ClBcmReglesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly appliquees = input<RegleBcm[]>([]);
  readonly decidee = output<void>();
  readonly data = signal<ReglesOut | null>(null);
  readonly ouvert = signal(false);
  readonly brouillon = signal<Brouillon | null>(null);
  readonly busy = signal(false);
  readonly dateFr = dateFr;
  readonly texte = texteRegle;

  ngOnInit(): void {
    this.charger();
  }

  charger(): void {
    this.api.get<ReglesOut>(`${CL_BASE}/bcm/regles`).subscribe({
      next: (d) => this.data.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Règles BCM indisponibles')),
    });
  }

  editeur(code: string): Editeur {
    return EDITEURS[code] ?? 'fixe';
  }

  libelle(code: string): string {
    return this.data()?.regles.find((r) => r.code === code)?.libelle ?? code;
  }

  editer(r: RegleBcm): void {
    const v = r.valeur as never;
    const formes = (r.code === 'forme.correspondance' ? v : {}) as Record<string, string[]>;
    const fenetre = (r.code === 'maj.fenetre' ? v : {}) as { type?: string; annees?: number };
    this.brouillon.set({
      code: r.code, statut: r.statut,
      liste: Array.isArray(r.valeur) ? (r.valeur as string[]).join(', ') : '',
      interdit: typeof r.valeur === 'string' ? r.valeur : 'HORS_COLONNES',
      type: fenetre.type ?? 'CALENDAIRE', annees: fenetre.annees ?? 5,
      bool: r.valeur === true,
      pp: (formes['PP'] ?? []).join('\n'), pm: (formes['PM'] ?? []).join('\n'), cj: (formes['CJ'] ?? []).join('\n'),
    });
  }

  private valeur(b: Brouillon): unknown {
    const lignes = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean);
    switch (this.editeur(b.code)) {
      case 'liste': return b.liste.split(',').map((x) => x.trim()).filter(Boolean);
      case 'interdit': return b.interdit;
      case 'fenetre': return { type: b.type, annees: Number(b.annees) };
      case 'bool': return b.bool;
      case 'formes': return { PP: lignes(b.pp), PM: lignes(b.pm), CJ: lignes(b.cj) };
      default: return this.data()?.regles.find((r) => r.code === b.code)?.valeur;
    }
  }

  enregistrer(): void {
    const b = this.brouillon();
    if (!b) return;
    const valeur = this.valeur(b);
    this.feedback.runWithReason((motif) => this.api.post<ReglesOut>(`${CL_BASE}/bcm/regles/${b.code}`, {
      valeur, statut: b.statut, motif,
    }), {
      reason: {
        title: 'Décision sur une règle BCM',
        message: `${this.libelle(b.code)} : ${texteRegle(valeur)} (${b.statut === 'CONFIRMEE' ? 'confirmée' : 'à valider'}).`,
        hint: 'La décision est historisée et s’applique au prochain calcul. Les déclarations validées ne changent pas.',
        reasonLabel: 'Motif (référence de la décision Conformité)',
      },
      busy: this.busy,
      loading: 'Enregistrement de la décision…',
      success: { title: 'Décision enregistrée', message: 'Recalculez la déclaration pour l’appliquer.' },
      errorTitle: 'Décision refusée',
    }).subscribe((d) => {
      this.data.set(d);
      this.brouillon.set(null);
      this.decidee.emit();
    });
  }
}
