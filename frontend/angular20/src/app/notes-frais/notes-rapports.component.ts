import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { FeedbackService } from '../core/feedback/feedback.service';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { MontantPipe } from '../shared/montant.pipe';
import { NoteApercuComponent } from './note-apercu.component';
import {
  canCreateNote,
  canDeleteNote,
  canEditNote,
  deleteNoteHint,
  editNoteHint,
  noteStatutLabel,
  noteStatutTone,
} from './notes-frais.shared';

interface RowNote {
  id: string;
  statut: string;
  demandeur_id: string | null;
}

interface ReportJson {
  key: string;
  title: string;
  headers: string[];
  rows: (string | number)[][];
  /** Notes alignées sur `rows` (rapports « note par note » uniquement). */
  notes?: RowNote[] | null;
  count: number;
}

type CellKind = 'text' | 'num' | 'date' | 'statut' | 'ref';

const NUM_HEADERS = new Set(['Montant', 'Montant total', 'Montant payé', 'Payé', 'Reste']);
const COUNT_HEADERS = new Set(['Nb notes', 'Nb lignes']);

@Component({
  selector: 'bea-notes-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, MontantPipe, NoteApercuComponent],
  template: `
    <section class="bea-mg bea-nf">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting</p>
          <h1>Rapports notes de frais</h1>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/notes-frais">Dashboard</a>
          @if (canCreate()) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/notes-frais/nouvelle">
              <mat-icon>add</mat-icon> Nouvelle note
            </a>
          }
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="load()">
        <label class="bea-mg__field">
          <mat-icon>insights</mat-icon>
          <select formControlName="key" (change)="load()">
            <option value="periode">Par période</option>
            <option value="agence">Par intitulé</option>
            <option value="demandeur">Par demandeur</option>
            <option value="categorie">Par catégorie</option>
            <option value="paiement">Paiements</option>
            <option value="attente">En attente</option>
            <option value="annuel">Annuel</option>
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>calendar_today</mat-icon>
          <input type="number" formControlName="annee" placeholder="Année" (change)="load()" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>date_range</mat-icon>
          <select formControlName="mois" (change)="load()">
            <option value="">Tous les mois</option>
            @for (m of moisOptions; track m.v) {
              <option [value]="m.v">{{ m.l }}</option>
            }
          </select>
        </label>
        <span class="bea-nf-search__spacer"></span>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!report()?.count" (click)="download('pdf')" title="Télécharger le rapport affiché">
          <mat-icon>picture_as_pdf</mat-icon> PDF
        </button>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!report()?.count" (click)="download('xlsx')" title="Télécharger le rapport affiché">
          <mat-icon>table_view</mat-icon> Excel
        </button>
      </form>

      @if (report(); as r) {
        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>{{ r.title }}</h2>
            <span class="bea-mg__count">{{ r.count }} ligne{{ r.count > 1 ? 's' : '' }}</span>
          </div>
          <div class="bea-mg__table-scroll bea-nf__registre-scroll">
            <table class="bea-mg__table bea-nf-table">
              <thead>
                <tr>
                  @for (h of r.headers; track h; let c = $index) {
                    <th [class.is-num]="kinds()[c] === 'num'">{{ h }}</th>
                  }
                  @if (hasActions()) {
                    <th class="bea-mg__th-actions">Actions</th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of r.rows; track $index; let i = $index) {
                  <tr class="bea-nf-row" [style.animation-delay.ms]="i < 20 ? i * 35 : 0" (dblclick)="openRow(i)">
                    @for (cell of row; track $index; let c = $index) {
                      @switch (kinds()[c]) {
                        @case ('ref') {
                          <td class="is-nowrap"><code class="bea-mg__code">{{ cell }}</code></td>
                        }
                        @case ('date') {
                          <td class="is-nowrap">{{ dateFr(cell) }}</td>
                        }
                        @case ('num') {
                          <td class="is-num is-nowrap">{{ cell | montant }}</td>
                        }
                        @case ('statut') {
                          <td class="is-nowrap">
                            <span class="bea-nf-badge" [attr.data-tone]="statutTone(cell)">{{ statutLabel(cell) }}</span>
                          </td>
                        }
                        @default {
                          <td>{{ cell === '' ? '—' : cell }}</td>
                        }
                      }
                    }
                    @if (r.notes?.[i]; as n) {
                      <td class="bea-mg__actions-cell">
                        <button type="button" class="bea-mg__icon-btn" title="Voir le détail" (click)="openRow(i)">
                          <mat-icon>visibility</mat-icon>
                        </button>
                        @if (canEdit(n)) {
                          <a class="bea-mg__icon-btn" [routerLink]="['/notes-frais/notes', n.id]" title="Modifier">
                            <mat-icon>edit</mat-icon>
                          </a>
                        } @else {
                          <button type="button" class="bea-mg__icon-btn" disabled [title]="editHint(n)">
                            <mat-icon>edit</mat-icon>
                          </button>
                        }
                        <button
                          type="button"
                          class="bea-mg__icon-btn bea-mg__icon-btn--danger"
                          [title]="deleteHint(n)"
                          [disabled]="!canDelete(n) || deletingId() === n.id"
                          (click)="remove(i)"
                        >
                          <mat-icon>delete</mat-icon>
                        </button>
                      </td>
                    }
                  </tr>
                } @empty {
                  <tr>
                    <td [attr.colspan]="r.headers.length + (hasActions() ? 1 : 0)">
                      <div class="bea-mg__empty">
                        <mat-icon>query_stats</mat-icon>
                        <p>Aucune donnée disponible.</p>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
              @if (totals(); as t) {
                <tfoot>
                  <tr>
                    @for (v of t; track $index; let c = $index) {
                      <td [class.is-num]="kinds()[c] === 'num'">
                        @if (c === 0) { Total }
                        @else if (v !== null) { {{ kinds()[c] === 'num' ? (v | montant) : v }} }
                      </td>
                    }
                    @if (hasActions()) { <td></td> }
                  </tr>
                </tfoot>
              }
            </table>
          </div>
        </div>
      }

      @if (apercuId(); as id) {
        <bea-note-apercu [noteId]="id" (closed)="apercuId.set(null)" (deleted)="onDeleted()" />
      }
    </section>
  `,
})
export class NotesRapportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);

  readonly report = signal<ReportJson | null>(null);
  readonly apercuId = signal<string | null>(null);
  readonly deletingId = signal<string | null>(null);
  readonly erreur = feedbackSignal('error', '');
  /** Rapport affiché : l'export reprend exactement celui-ci. */
  private affiche: { key: string; params: Record<string, string | number> } | null = null;

  readonly statutLabel = (v: string | number) => noteStatutLabel(String(v));
  readonly statutTone = (v: string | number) => noteStatutTone(String(v));
  readonly canCreate = computed(() => canCreateNote(this.auth.user()));

  readonly moisOptions = [
    'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
  ].map((l, i) => ({ v: String(i + 1), l }));

  readonly filters = this.fb.nonNullable.group({
    key: 'periode',
    annee: String(new Date().getFullYear()),
    mois: '',
  });

  readonly hasActions = computed(() => !!this.report()?.notes?.length);

  readonly kinds = computed<CellKind[]>(() =>
    (this.report()?.headers ?? []).map((h) => {
      if (h === 'Référence') return 'ref';
      if (h === 'Date') return 'date';
      if (h === 'Statut') return 'statut';
      if (NUM_HEADERS.has(h)) return 'num';
      return 'text';
    }),
  );

  /** Ligne de totaux : sommes des colonnes montants et compteurs. */
  readonly totals = computed<(number | null)[] | null>(() => {
    const r = this.report();
    if (!r || r.rows.length < 2) return null;
    return r.headers.map((h, c) => {
      if (!NUM_HEADERS.has(h) && !COUNT_HEADERS.has(h)) return null;
      const sum = r.rows.reduce((acc, row) => acc + (Number(row[c]) || 0), 0);
      return Math.round(sum * 100) / 100;
    });
  });

  ngOnInit(): void {
    this.load();
  }

  params(): Record<string, string | number> {
    const v = this.filters.getRawValue();
    const p: Record<string, string | number> = { format: 'json' };
    if (v.annee) p['annee'] = Number(v.annee);
    if (v.mois) p['mois'] = Number(v.mois);
    return p;
  }

  load(): void {
    this.erreur.set('');
    const key = this.filters.value.key || 'periode';
    const params = this.params();
    this.api.get<ReportJson>(`/mg/notes-frais/rapports/${key}`, params).subscribe({
      next: (r) => {
        this.report.set(r);
        this.affiche = { key, params };
      },
      error: (err) => {
        this.report.set(null);
        this.erreur.set(err?.error?.detail || 'Rapport indisponible');
      },
    });
  }

  dateFr(v: string | number): string {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v));
    return m ? `${m[3]}/${m[2]}/${m[1]}` : String(v || '—');
  }

  canEdit(n: RowNote): boolean {
    return canEditNote(this.auth.user(), n);
  }

  canDelete(n: RowNote): boolean {
    return canDeleteNote(this.auth.user(), n);
  }

  editHint(n: RowNote): string {
    return editNoteHint(this.auth.user(), n);
  }

  deleteHint(n: RowNote): string {
    return deleteNoteHint(this.auth.user(), n);
  }

  openRow(i: number): void {
    const id = this.report()?.notes?.[i]?.id;
    if (id) this.apercuId.set(id);
  }

  remove(i: number): void {
    const r = this.report();
    const id = r?.notes?.[i]?.id;
    if (!r || !id) return;
    const ref = String(r.rows[i][r.headers.indexOf('Référence')] ?? '');
    this.deletingId.set(id);
    this.feedback
      .run(() => this.api.delete<{ ok: boolean }>(`/mg/notes-frais/notes/${id}`), {
        confirm: { action: 'suppression', message: `Supprimer la note « ${ref} » ? Elle sera retirée du registre.` },
        loading: 'Suppression…',
        errorTitle: 'Suppression refusée',
        success: { title: 'Note supprimée', details: [{ label: 'Référence', value: ref }] },
      })
      .subscribe({
        next: () => this.load(),
        complete: () => this.deletingId.set(null),
      });
  }

  onDeleted(): void {
    this.apercuId.set(null);
    this.load();
  }

  download(format: 'xlsx' | 'pdf'): void {
    if (!this.affiche) return;
    const key = this.affiche.key;
    const params = { ...this.affiche.params, format };
    this.api.download(`/mg/notes-frais/rapports/${key}`, params).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `notes-${key}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible`),
    });
  }
}
