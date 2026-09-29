import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { PaginationComponent } from '../shared/pagination.component';
import { DocumentViewerComponent, GedDoc } from './document-viewer.component';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { FeedbackService } from '../core/feedback/feedback.service';

interface ListOut {
  items: GedDoc[];
  total: number;
  page: number;
  size: number;
  ocr_pending_hint?: boolean;
}

interface FilterOpt {
  value: string;
  label: string;
}

interface CatalogueEspace {
  code: string;
  label: string;
  modules: { code: string; label: string }[];
}

interface CatalogueType {
  module_code: string;
  espace_code: string;
  type: string;
}

@Component({
  selector: 'bea-archives-generales',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, DatePipe, PaginationComponent, DocumentViewerComponent],
  template: `
    <section class="bea-mg bea-ag-reg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Archive Générale</p>
          <h1>{{ mode() === 'recherche' ? 'Recherche avancée' : 'Tous les documents' }}</h1>
          @if (mode() === 'recherche') {
            <p class="bea-stock-page__kicker">Recherche plein texte dans les métadonnées et le contenu OCR. Les résultats s'affichent en fiches.</p>
          }
        </div>
        <span class="bea-mg__count">{{ total() }} document(s)</span>
      </header>

      <form class="bea-ag-reg__filters" (ngSubmit)="$event.preventDefault(); search()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input [(ngModel)]="q" name="q" placeholder="Référence, nom, contenu OCR…" />
        </label>
        <label class="bea-mg__field">
          <select [ngModel]="espaceFilter" (ngModelChange)="onEspace($event)" name="espace">
            <option value="">Tous les départements</option>
            @for (o of espaces(); track o.value) {
              <option [value]="o.value">{{ o.label }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <select [ngModel]="moduleFilter" (ngModelChange)="onModule($event)" name="module">
            <option value="">Tous les modules</option>
            @for (o of visibleModules(); track o.value) {
              <option [value]="o.value">{{ o.label }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <select [(ngModel)]="docType" name="type">
            <option value="">Tous les types</option>
            @for (o of visibleTypes(); track o.value) {
              <option [value]="o.value">{{ o.label }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <select [(ngModel)]="ocrStatus" name="ocr">
            <option value="">OCR</option>
            <option value="pending">En attente</option>
            <option value="processing">En cours</option>
            <option value="done">Terminé</option>
            <option value="failed">À vérifier</option>
          </select>
        </label>
        <label class="bea-mg__field">
          <select [(ngModel)]="year" name="year">
            <option value="">Année</option>
            @for (y of years; track y) {
              <option [value]="y">{{ y }}</option>
            }
          </select>
        </label>
        @if (mode() === 'recherche') {
          <p class="bea-ag-search-note">La recherche dans le texte OCR est active.</p>
        }
        <button type="button" class="bea-mg__btn" (click)="reset()">Réinitialiser</button>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="search()">Filtrer</button>
        <div class="bea-ag-export">
          <button type="button" class="bea-mg__btn" (click)="toggleExport($event)">
            Exporter
            <mat-icon>expand_more</mat-icon>
          </button>
          @if (exportOpen()) {
            <div class="bea-ag-menu bea-ag-menu--anchor" (click)="$event.stopPropagation()">
              <button type="button" (click)="exportAs('xlsx')">Excel</button>
              <button type="button" (click)="exportAs('pdf')">PDF</button>
            </div>
          }
        </div>
      </form>

      @if (selected().size) {
        <div class="bea-ag-reg__bulk">
          <span>{{ selected().size }} sélectionné(s)</span>
          @if (canWrite()) {
            <button type="button" class="bea-mg__btn" (click)="bulkArchive()">Archiver</button>
            <button type="button" class="bea-mg__btn" (click)="confirmBulkTrash.set(true)">Corbeille</button>
          }
          <button type="button" class="bea-mg__btn" (click)="bulkDownload()">Télécharger</button>
        </div>
      }

      @if (ocrHint()) {
        <p class="bea-stock-page__kicker">Aucun plein texte — des documents sont encore en OCR.</p>
      }

      <div class="bea-mg__panel">
        @if (mode() === 'recherche' && idleSearch()) {
          <div class="bea-mg__empty">
            <mat-icon>manage_search</mat-icon>
            <p>Saisissez un mot-clé, un département ou un type, puis lancez la recherche.</p>
          </div>
        } @else if (mode() === 'recherche') {
          <div class="bea-ag-cards">
            @for (d of docs(); track d.id; let i = $index) {
              <article class="bea-ag-card" [style.--i]="i">
                <mat-icon>description</mat-icon>
                <div>
                  <strong>{{ d.reference || d.title || d.filename }}</strong>
                  <p>{{ d.filename }}</p>
                  <p>{{ espaceLabel(d.espace_code) }} · {{ moduleLabel(d.module_code) }} · {{ typeLabel(d.doc_type || d.entity) }}</p>
                  <span class="bea-ocr-badge" [attr.data-status]="d.ocr_status || 'pending'">{{ ocrLabel(d.ocr_status) }}</span>
                </div>
                <div class="bea-ag-icons">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="open(d.id)"><mat-icon>visibility</mat-icon></button>
                  <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="download(d)"><mat-icon>download</mat-icon></button>
                  @if (canWrite()) {
                    <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="startEdit(d)"><mat-icon>edit</mat-icon></button>
                    <button type="button" class="bea-mg__icon-btn" title="Supprimer" (click)="startTrash(d)"><mat-icon>delete</mat-icon></button>
                  }
                </div>
              </article>
            } @empty {
              <div class="bea-mg__empty"><p>Aucun document ne correspond à cette recherche.</p></div>
            }
          </div>
        } @else {
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table bea-ag-reg__table">
            <thead>
              <tr>
                <th><input type="checkbox" [checked]="allChecked()" (change)="toggleAll($event)" /></th>
                <th>Document</th>
                <th>Département</th>
                <th>Module</th>
                <th>Type</th>
                <th>OCR</th>
                <th>Date</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @if (loading()) {
                @for (i of skeletons; track i) {
                  <tr class="bea-ag-skel"><td colspan="8"></td></tr>
                }
              } @else {
                @for (d of docs(); track d.id; let i = $index) {
                  <tr [style.--i]="i" class="bea-ag-row">
                    <td><input type="checkbox" [checked]="selected().has(d.id)" (change)="toggle(d.id)" /></td>
                    <td>
                      <strong>{{ d.reference || d.title || d.filename }}</strong>
                      <div class="bea-ag__sub">{{ d.filename }}</div>
                    </td>
                    <td>{{ espaceLabel(d.espace_code) }}</td>
                    <td>{{ moduleLabel(d.module_code) }}</td>
                    <td>{{ typeLabel(d.doc_type || d.entity) }}</td>
                    <td><span class="bea-ocr-badge" [attr.data-status]="d.ocr_status || 'pending'">{{ ocrLabel(d.ocr_status) }}</span></td>
                    <td>{{ d.created_at ? (d.created_at | date: 'dd/MM/yyyy') : '—' }}</td>
                    <td class="bea-ag__row-actions">
                      <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="open(d.id)"><mat-icon>visibility</mat-icon></button>
                      <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="download(d)"><mat-icon>download</mat-icon></button>
                      @if (canWrite()) {
                        <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="startEdit(d)"><mat-icon>edit</mat-icon></button>
                        <button type="button" class="bea-mg__icon-btn" title="Supprimer" (click)="startTrash(d)"><mat-icon>delete</mat-icon></button>
                      }
                      <button type="button" class="bea-mg__icon-btn" title="Plus" (click)="toggleMenu($event, d)">
                        <mat-icon>more_vert</mat-icon>
                      </button>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="8">
                      <div class="bea-mg__empty">
                        <mat-icon>folder_open</mat-icon>
                        <p>Aucun document pour ces filtres.</p>
                      </div>
                    </td>
                  </tr>
                }
              }
            </tbody>
          </table>
        </div>
        @if (total() > 0) {
          <app-pagination [page]="page()" [total]="total()" [pageSize]="pageSize" label="document(s)" (pageChange)="goToPage($event)" />
        }
        }
      </div>
    </section>

    @if (menuDoc(); as d) {
      <div
        class="bea-ag-menu bea-ag-menu--fixed"
        [style.top.px]="menuTop()"
        [style.left.px]="menuLeft()"
        (click)="$event.stopPropagation()"
      >
        <button type="button" (click)="open(d.id)">Voir</button>
        <button type="button" (click)="download(d); menuDoc.set(null)">Télécharger</button>
        @if (canWrite()) {
          <button type="button" (click)="startEdit(d)">Modifier métadonnées</button>
          <button type="button" (click)="startVersion(d)">Nouvelle version</button>
          <button type="button" (click)="archiveOne(d)">Archiver</button>
          <button type="button" (click)="startTrash(d)">Corbeille</button>
        }
        <button type="button" (click)="open(d.id)">Documents liés</button>
      </div>
    }

    <bea-document-viewer [documentId]="viewerId()" (closed)="viewerId.set(null)" (openRelated)="open($event)" />

    @if (editDoc(); as d) {
      <div class="bea-modal" role="dialog">
        <form class="bea-modal__card" (ngSubmit)="saveMeta()">
          <header><h2>Modifier le document</h2><button type="button" (click)="editDoc.set(null)">×</button></header>
          <label>Nom<input [(ngModel)]="metaTitle" name="title" /></label>
          <label>Type<input [(ngModel)]="metaType" name="type" /></label>
          <label>Référence<input [(ngModel)]="metaRef" name="ref" /></label>
          <label>Description<textarea [(ngModel)]="metaDesc" name="desc" rows="3"></textarea></label>
          <p class="bea-stock-page__kicker">Les métadonnées GED uniquement. L'opération source n'est pas modifiée.</p>
          <footer>
            <button type="button" class="bea-mg__btn" (click)="editDoc.set(null)">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Enregistrer</button>
          </footer>
        </form>
      </div>
    }

    @if (versionDoc(); as d) {
      <div class="bea-modal" role="dialog">
        <form class="bea-modal__card" (ngSubmit)="saveVersion()">
          <header><h2>Nouvelle version</h2><button type="button" (click)="versionDoc.set(null)">×</button></header>
          <p>{{ d.filename }}</p>
          <input type="file" (change)="onVersionFile($event)" accept=".pdf,.png,.jpg,.jpeg" />
          <label>Commentaire<input [(ngModel)]="versionComment" name="vc" /></label>
          <footer>
            <button type="button" class="bea-mg__btn" (click)="versionDoc.set(null)">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!versionFile">Créer la version</button>
          </footer>
        </form>
      </div>
    }

    @if (trashDoc() || confirmBulkTrash()) {
      <div class="bea-modal" role="dialog">
        <div class="bea-modal__card">
          <header><h2>Mettre à la corbeille ?</h2></header>
          <p>Le document ne sera pas supprimé définitivement.</p>
          <footer>
            <button type="button" class="bea-mg__btn" (click)="trashDoc.set(null); confirmBulkTrash.set(false)">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="confirmTrash()">Mettre à la corbeille</button>
          </footer>
        </div>
      </div>
    }
  `,
  styles: `
    .bea-ag-search-note { margin: 0; font-size: 0.82rem; color: #1e40af; }
    .bea-ag-cards { display: grid; gap: 0.7rem; }
    .bea-ag-card {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 0.75rem;
      align-items: center;
      padding: 0.85rem 1rem;
      border: 1px solid #e2e8f0;
      border-radius: 0.75rem;
      background: #fff;
      animation: beaRow 0.35s ease both;
      animation-delay: calc(var(--i, 0) * 40ms);
    }
    .bea-ag-card p { margin: 0.15rem 0; color: #64748b; font-size: 0.82rem; }
    .bea-ag-icons { display: flex; gap: 0.15rem; }
    .bea-ag-reg__bulk {
      display: flex; gap: 0.45rem; align-items: center;
      margin-bottom: 0.6rem; padding: 0.5rem 0.7rem;
      background: #eff6ff; border-radius: 0.5rem; font-size: 0.88rem;
    }
    .bea-ag__sub { font-size: 0.78rem; color: #94a3b8; }
    .bea-ag__ocr-check { display: flex; align-items: center; gap: 0.35rem; font-size: 0.85rem; }
    .bea-ag__row-actions { white-space: nowrap; }
    .bea-ag-export { position: relative; }
    .bea-ag-export .bea-mg__btn {
      display: inline-flex;
      align-items: center;
      gap: 0.15rem;
    }
    .bea-ag-menu {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 0.55rem;
      box-shadow: 0 12px 32px rgb(15 23 42 / 16%);
      display: grid;
      min-width: 13.5rem;
      padding: 0.3rem;
      z-index: 40;
    }
    .bea-ag-menu--anchor {
      position: absolute;
      top: calc(100% + 0.3rem);
      right: 0;
    }
    .bea-ag-menu--fixed {
      position: fixed;
      z-index: 60;
    }
    .bea-ag-menu button {
      text-align: left;
      border: 0;
      background: transparent;
      padding: 0.5rem 0.7rem;
      cursor: pointer;
      font-size: 0.88rem;
      border-radius: 0.35rem;
      color: #0f172a;
    }
    .bea-ag-menu button:hover { background: #f1f5f9; }
    .bea-ag-row { animation: beaRow 0.35s ease both; animation-delay: calc(var(--i, 0) * 30ms); }
    .bea-ag-skel td {
      height: 2.4rem;
      background: linear-gradient(90deg, #f1f5f9, #e2e8f0, #f1f5f9);
      background-size: 200% 100%;
      animation: beaShimmer 1.1s linear infinite;
    }
    .bea-modal {
      position: fixed; inset: 0; z-index: 70;
      background: rgb(15 23 42 / 45%);
      display: grid; place-items: center;
      animation: beaFade 0.25s ease;
    }
    .bea-modal__card {
      background: #fff; border-radius: 0.75rem; padding: 1rem 1.1rem;
      width: min(28rem, 92vw); display: grid; gap: 0.55rem;
      animation: beaPop 0.3s ease;
    }
    .bea-modal__card header { display: flex; justify-content: space-between; align-items: center; }
    .bea-modal__card h2 { margin: 0; font-size: 1.05rem; }
    .bea-modal__card label { display: grid; gap: 0.2rem; font-size: 0.82rem; color: #475569; }
    .bea-modal__card input, .bea-modal__card textarea {
      border: 1px solid #cbd5e1; border-radius: 0.4rem; padding: 0.4rem 0.5rem; font: inherit;
    }
    .bea-modal__card footer { display: flex; justify-content: flex-end; gap: 0.4rem; }
    .bea-ocr-badge {
      display: inline-block; font-size: 0.72rem; font-weight: 650;
      padding: 0.15rem 0.45rem; border-radius: 0.35rem; background: #e2e8f0; color: #475569;
    }
    .bea-ocr-badge[data-status='pending'] { background: #fef3c7; color: #92400e; }
    .bea-ocr-badge[data-status='processing'] { background: #dbeafe; color: #1e40af; }
    .bea-ocr-badge[data-status='done'] { background: #dcfce7; color: #166534; }
    .bea-ocr-badge[data-status='failed'] { background: #ffedd5; color: #9a3412; }
    @keyframes beaRow { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
    @keyframes beaMenu { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
    @keyframes beaFade { from { opacity: 0; } to { opacity: 1; } }
    @keyframes beaPop { from { opacity: 0; transform: scale(0.98); } to { opacity: 1; transform: none; } }
    @keyframes beaShimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
    @media (prefers-reduced-motion: reduce) {
      .bea-ag-row, .bea-ag-menu, .bea-modal, .bea-modal__card, .bea-ag-skel td { animation: none; }
    }
  `,
})
export class ArchivesGeneralesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);

  readonly docs = signal<GedDoc[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 25;
  readonly loading = signal(false);
  readonly erreur = feedbackSignal('error', null);
  readonly ocrHint = signal(false);
  readonly idleSearch = signal(false);
  readonly mode = signal<'documents' | 'recherche'>('documents');
  readonly viewerId = signal<string | null>(null);
  readonly menuDoc = signal<GedDoc | null>(null);
  readonly menuTop = signal(0);
  readonly menuLeft = signal(0);
  readonly exportOpen = signal(false);
  readonly selected = signal<Set<string>>(new Set());
  readonly catalogue = signal<CatalogueEspace[]>([]);
  readonly typeRows = signal<CatalogueType[]>([]);
  readonly espaces = signal<FilterOpt[]>([]);
  readonly editDoc = signal<GedDoc | null>(null);
  readonly versionDoc = signal<GedDoc | null>(null);
  readonly trashDoc = signal<GedDoc | null>(null);
  readonly confirmBulkTrash = signal(false);

  readonly years = [2026, 2025, 2024];
  readonly skeletons = [1, 2, 3, 4];

  readonly canWrite = computed(() => this.has('ged.write'));
  readonly allChecked = computed(() => {
    const rows = this.docs();
    return rows.length > 0 && rows.every((d) => this.selected().has(d.id));
  });

  @HostListener('document:click')
  closeMenus(): void {
    this.menuDoc.set(null);
    this.exportOpen.set(false);
  }

  toggleExport(ev: MouseEvent): void {
    ev.stopPropagation();
    this.menuDoc.set(null);
    this.exportOpen.update((v) => !v);
  }

  toggleMenu(ev: MouseEvent, doc: GedDoc): void {
    ev.stopPropagation();
    this.exportOpen.set(false);
    if (this.menuDoc()?.id === doc.id) {
      this.menuDoc.set(null);
      return;
    }
    const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const width = 220;
    const height = 240;
    let left = rect.right - width;
    if (left < 8) left = 8;
    let top = rect.bottom + 6;
    if (top + height > window.innerHeight) top = Math.max(8, rect.top - height);
    this.menuTop.set(top);
    this.menuLeft.set(left);
    this.menuDoc.set(doc);
  }

  onEspace(code: string): void {
    this.espaceFilter = code;
    const mods = this.visibleModules();
    if (this.moduleFilter && !mods.some((m) => m.value === this.moduleFilter)) {
      this.moduleFilter = '';
    }
    this.docType = '';
  }

  onModule(code: string): void {
    this.moduleFilter = code;
    const types = this.visibleTypes();
    if (this.docType && !types.some((t) => t.value === this.docType)) {
      this.docType = '';
    }
  }

  visibleModules(): FilterOpt[] {
    const rows = this.catalogue();
    const source = this.espaceFilter
      ? rows.filter((e) => e.code === this.espaceFilter)
      : rows;
    const seen = new Map<string, string>();
    for (const espace of source) {
      for (const mod of espace.modules) {
        seen.set(mod.code, mod.label);
      }
    }
    return [...seen.entries()].map(([value, label]) => ({ value, label }));
  }

  visibleTypes(): FilterOpt[] {
    let rows = this.typeRows();
    if (this.espaceFilter) rows = rows.filter((r) => r.espace_code === this.espaceFilter);
    if (this.moduleFilter) rows = rows.filter((r) => r.module_code === this.moduleFilter);
    const seen = new Map<string, string>();
    for (const row of rows) {
      seen.set(row.type, this.typeLabel(row.type));
    }
    return [...seen.entries()].map(([value, label]) => ({ value, label }));
  }

  espaceLabel(code: string): string {
    return this.espaces().find((e) => e.value === code)?.label || code;
  }

  moduleLabel(code: string): string {
    for (const espace of this.catalogue()) {
      const mod = espace.modules.find((m) => m.code === code);
      if (mod) return mod.label;
    }
    return code;
  }

  typeLabel(value: string | null | undefined): string {
    if (!value) return '—';
    return value.replaceAll('_', ' ');
  }
  q = '';
  espaceFilter = '';
  moduleFilter = '';
  docType = '';
  ocrStatus = '';
  year = '';
  searchOcr = false;
  entity = '';
  entityId = '';
  agenceId = '';
  metaTitle = '';
  metaType = '';
  metaRef = '';
  metaDesc = '';
  versionComment = '';
  versionFile: File | null = null;

  ngOnInit(): void {
    const dataMode = this.route.snapshot.data['archivesMode'];
    this.mode.set(dataMode === 'recherche' ? 'recherche' : 'documents');
    if (this.mode() === 'recherche') this.searchOcr = true;
    this.loadFacets();
    this.route.queryParamMap.subscribe((qp) => {
      this.espaceFilter = qp.get('espace_code') || '';
      this.moduleFilter = qp.get('module_code') || '';
      this.docType = qp.get('doc_type') || '';
      this.ocrStatus = qp.get('ocr_status') || '';
      this.agenceId = qp.get('agence_id') || '';
      this.entity = qp.get('entity') || '';
      this.entityId = qp.get('entity_id') || '';
      this.q = qp.get('q') || this.q;
      this.page.set(1);
      this.load();
    });
  }

  has(code: string): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const codes = u.permission_codes ?? [];
    return codes.includes('*') || codes.includes(code);
  }

  ocrLabel(status: string | null | undefined): string {
    switch (status) {
      case 'processing': return 'En cours';
      case 'done': return 'Terminé';
      case 'failed': return 'À vérifier';
      default: return 'En attente';
    }
  }

  search(): void {
    this.page.set(1);
    this.load();
  }

  reset(): void {
    this.q = '';
    this.espaceFilter = '';
    this.moduleFilter = '';
    this.docType = '';
    this.ocrStatus = '';
    this.year = '';
    this.agenceId = '';
    this.entity = '';
    this.entityId = '';
    this.search();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  open(id: string): void {
    this.menuDoc.set(null);
    this.viewerId.set(id);
  }

  exportAs(fmt: 'xlsx' | 'pdf'): void {
    this.exportOpen.set(false);
    const params: Record<string, string> = { format: fmt, report_key: 'documents' };
    if (this.espaceFilter) params['espace_code'] = this.espaceFilter;
    if (this.moduleFilter) params['module_code'] = this.moduleFilter;
    if (this.docType) params['doc_type'] = this.docType;
    if (this.ocrStatus) params['ocr_status'] = this.ocrStatus;
    if (this.q.trim()) params['q'] = this.q.trim();
    if (this.year) {
      params['date_debut'] = `${this.year}-01-01`;
      params['date_fin'] = `${this.year}-12-31`;
    }
    this.api.download('/doc-archives/general/rapports/export', params).subscribe({
      next: (blob) => {
        const name = fmt === 'pdf' ? 'documents.pdf' : 'documents.xlsx';
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Export refusé.'),
    });
  }

  toggle(id: string): void {
    const next = new Set(this.selected());
    if (next.has(id)) next.delete(id);
    else next.add(id);
    this.selected.set(next);
  }

  toggleAll(ev: Event): void {
    const on = (ev.target as HTMLInputElement).checked;
    this.selected.set(on ? new Set(this.docs().map((d) => d.id)) : new Set());
  }

  startEdit(d: GedDoc): void {
    this.menuDoc.set(null);
    this.editDoc.set(d);
    this.metaTitle = d.title || d.filename;
    this.metaType = d.doc_type || '';
    this.metaRef = d.reference || '';
    this.metaDesc = d.description || '';
  }

  saveMeta(): void {
    const d = this.editDoc();
    if (!d) return;
    this.api.patch(`/documents/${d.id}`, {
      title: this.metaTitle,
      doc_type: this.metaType || null,
      reference: this.metaRef || null,
      description: this.metaDesc || null,
    }).subscribe({
      next: () => {
        this.editDoc.set(null);
        this.flash('Métadonnées enregistrées.');
        this.load();
      },
      error: () => this.erreur.set('Modification refusée.'),
    });
  }

  startVersion(d: GedDoc): void {
    this.menuDoc.set(null);
    this.versionDoc.set(d);
    this.versionFile = null;
    this.versionComment = '';
  }

  onVersionFile(ev: Event): void {
    this.versionFile = (ev.target as HTMLInputElement).files?.[0] ?? null;
  }

  saveVersion(): void {
    const d = this.versionDoc();
    if (!d || !this.versionFile) return;
    this.api.upload(`/documents/${d.id}/versions`, this.versionFile, {
      version_comment: this.versionComment,
    }).subscribe({
      next: () => {
        this.versionDoc.set(null);
        this.flash('Version créée. OCR relancé.');
        this.load();
      },
      error: () => this.erreur.set('Création de version refusée.'),
    });
  }

  startTrash(d: GedDoc): void {
    this.menuDoc.set(null);
    this.trashDoc.set(d);
  }

  confirmTrash(): void {
    const one = this.trashDoc();
    const ids = one ? [one.id] : [...this.selected()];
    this.trashDoc.set(null);
    this.confirmBulkTrash.set(false);
    let left = ids.length;
    for (const id of ids) {
      this.api.delete(`/documents/${id}`).subscribe({
        next: () => {
          left -= 1;
          if (left === 0) {
            this.selected.set(new Set());
            this.flash('Document(s) mis à la corbeille.');
            this.load();
          }
        },
        error: () => this.erreur.set('Mise à la corbeille refusée.'),
      });
    }
  }

  archiveOne(d: GedDoc): void {
    this.menuDoc.set(null);
    this.archiveIds([d.id]);
  }

  bulkArchive(): void {
    this.archiveIds([...this.selected()]);
  }

  bulkDownload(): void {
    for (const id of this.selected()) {
      const d = this.docs().find((x) => x.id === id);
      if (d) this.download(d);
    }
  }

  download(d: GedDoc): void {
    this.api.download(`/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename || 'document';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Téléchargement refusé.'),
    });
  }

  private archiveIds(ids: string[]): void {
    let left = ids.length;
    for (const id of ids) {
      this.api.patch(`/documents/${id}`, { archive: true }).subscribe({
        next: () => {
          left -= 1;
          if (left === 0) {
            this.flash('Archivage enregistré.');
            this.load();
          }
        },
        error: () => this.erreur.set('Archivage refusé.'),
      });
    }
  }

  private flash(msg: string): void {
    this.feedback.success({ title: msg });
  }

  private loadFacets(): void {
    this.api.get<{ espaces: CatalogueEspace[]; types: CatalogueType[] }>(
      '/doc-archives/general/filtres',
    ).subscribe({
      next: (d) => {
        this.catalogue.set(d.espaces ?? []);
        this.typeRows.set(d.types ?? []);
        this.espaces.set((d.espaces ?? []).map((e) => ({ value: e.code, label: e.label })));
      },
      error: () => this.erreur.set('Filtres départements indisponibles.'),
    });
  }

  private load(): void {
    this.menuDoc.set(null);
    const searching = this.mode() === 'recherche';
    const hasCriteria = !!(
      this.q.trim() || this.espaceFilter || this.moduleFilter || this.docType || this.ocrStatus || this.year || this.agenceId || this.entity
    );
    if (searching && !hasCriteria) {
      this.docs.set([]);
      this.total.set(0);
      this.loading.set(false);
      this.idleSearch.set(true);
      return;
    }
    this.idleSearch.set(false);
    this.loading.set(true);
    this.erreur.set(null);
    this.menuDoc.set(null);
    const params: Record<string, string | number | boolean> = {
      page: this.page(),
      size: this.pageSize,
      search_ocr: this.mode() === 'recherche' ? true : this.searchOcr,
    };
    if (this.q.trim()) params['q'] = this.q.trim();
    if (this.espaceFilter) params['espace_code'] = this.espaceFilter;
    if (this.moduleFilter) params['module_code'] = this.moduleFilter;
    if (this.docType) params['doc_type'] = this.docType;
    if (this.ocrStatus) params['ocr_status'] = this.ocrStatus;
    if (this.agenceId) params['agence_id'] = this.agenceId;
    if (this.entity) params['entity'] = this.entity;
    if (this.entityId) params['entity_id'] = this.entityId;
    if (this.year) {
      params['date_debut'] = `${this.year}-01-01`;
      params['date_fin'] = `${this.year}-12-31`;
    }
    this.api.get<ListOut>('/doc-archives/general', params).subscribe({
      next: (res) => {
        this.docs.set(res.items ?? []);
        this.total.set(res.total ?? 0);
        this.ocrHint.set(!!res.ocr_pending_hint && this.searchOcr);
        this.loading.set(false);
      },
      error: () => {
        this.docs.set([]);
        this.total.set(0);
        this.loading.set(false);
        this.erreur.set('Chargement impossible (permission archives.general.view ?).');
      },
    });
  }
}
