import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { PaginationComponent } from '../shared/pagination.component';

interface Doc {
  id: string;
  filename: string;
  title?: string | null;
  reference?: string | null;
  doc_type?: string | null;
  module_code: string;
  entity: string;
  entity_id: string;
  created_at: string | null;
  size_bytes: number | null;
  deleted_at?: string | null;
  ocr_status?: string | null;
  ocr_error?: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

@Component({
  selector: 'bea-archives-documents',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, DatePipe, RouterLink, PaginationComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Archives</p>
          <h1>{{ pageTitle() }}</h1>
        </div>
        <div class="bea-mg__actions">
          <span class="bea-mg__count">{{ total() }} document(s)</span>
          @if (!trashMode()) {
            <label class="bea-mg__btn bea-mg__btn--primary" style="cursor:pointer">
              <mat-icon>upload_file</mat-icon> Ajouter
              <input type="file" hidden (change)="onFile($event)" />
            </label>
          }
        </div>
      </header>

      <form class="bea-mg__search" (ngSubmit)="$event.preventDefault(); applyFilters()">
        <label class="bea-mg__field">
          <mat-icon>folder</mat-icon>
          <select [(ngModel)]="moduleFilter" name="module" (ngModelChange)="applyFilters()">
            <option value="">Tous les modules</option>
            <option value="stock-fournitures">Stock</option>
            <option value="achats-appro">Achats</option>
            <option value="notes-frais">Notes de frais</option>
            <option value="contrats-echeances">Contrats</option>
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>category</mat-icon>
          <input [(ngModel)]="docType" name="docType" placeholder="Type…" (keyup.enter)="applyFilters()" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>event</mat-icon>
          <input type="number" [(ngModel)]="year" name="year" placeholder="Annee" (change)="applyFilters()" />
        </label>
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input [(ngModel)]="q" name="q" placeholder="Reference, nom, type…" (keyup.enter)="applyFilters()" />
        </label>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="applyFilters()">
          <mat-icon>filter_list</mat-icon> Filtrer
        </button>
      </form>

      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (msg()) { <p class="bea-stock-page__ok">{{ msg() }}</p> }

      <div class="bea-mg__panel">
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Fichier</th>
                <th>Ref.</th>
                <th>Module</th>
                <th>Type / entite</th>
                <th>OCR</th>
                <th>Date</th>
                <th>Taille</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (d of docs(); track d.id; let i = $index) {
                <tr [style.--i]="i">
                  <td>{{ d.title || d.filename || '—' }}</td>
                  <td><code class="bea-mg__code">{{ d.reference || '—' }}</code></td>
                  <td>{{ moduleLabel(d.module_code) }}</td>
                  <td>{{ d.doc_type || entityLabel(d.entity) }}</td>
                  <td>
                    <span class="bea-ocr-badge" [attr.data-status]="d.ocr_status || 'pending'">
                      {{ ocrLabel(d.ocr_status) }}
                    </span>
                    @if (d.ocr_status === 'failed') {
                      <button type="button" class="bea-mg__icon-btn" title="Relancer OCR" (click)="retryOcr(d)">
                        <mat-icon>refresh</mat-icon>
                      </button>
                    }
                  </td>
                  <td>{{ d.created_at ? (d.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                  <td>{{ sizeLabel(d.size_bytes) }}</td>
                  <td class="bea-mg__actions-cell">
                    @if (!trashMode()) {
                      <button type="button" class="bea-mg__icon-btn" title="Telecharger" (click)="download(d)">
                        <mat-icon>download</mat-icon>
                      </button>
                      @if (entityLink(d); as link) {
                        <a class="bea-mg__icon-btn" [routerLink]="link" title="Fiche metier"><mat-icon>open_in_new</mat-icon></a>
                      }
                      <a class="bea-mg__icon-btn" [routerLink]="['/archives-mg/dossiers', d.module_code, d.entity, d.entity_id]" title="Dossier">
                        <mat-icon>account_tree</mat-icon>
                      </a>
                      <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--warn" title="Corbeille" (click)="softDelete(d)">
                        <mat-icon>delete</mat-icon>
                      </button>
                    } @else {
                      <button type="button" class="bea-mg__icon-btn" title="Restaurer" (click)="restore(d)">
                        <mat-icon>restore</mat-icon>
                      </button>
                    }
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8">
                    <div class="bea-mg__empty">
                      <mat-icon>folder_open</mat-icon>
                      <p>Aucun document pour ces criteres.</p>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (total() > 0) {
          <app-pagination [page]="page()" [total]="total()" [pageSize]="pageSize" label="document(s)" (pageChange)="goToPage($event)" />
        }
      </div>
    </section>
  `,
  styles: `
    a.bea-mg__icon-btn { text-decoration: none; color: inherit; }
    .bea-ocr-badge {
      display: inline-block;
      font-size: 0.72rem;
      font-weight: 650;
      padding: 0.15rem 0.45rem;
      border-radius: 0.35rem;
      background: #e2e8f0;
      color: #475569;
    }
    .bea-ocr-badge[data-status='pending'] { background: #fef3c7; color: #92400e; }
    .bea-ocr-badge[data-status='processing'] { background: #dbeafe; color: #1e40af; }
    .bea-ocr-badge[data-status='done'] { background: #dcfce7; color: #166534; }
    .bea-ocr-badge[data-status='failed'] { background: #fee2e2; color: #991b1b; }
  `,
})
export class ArchivesDocumentsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly docs = signal<Doc[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly erreur = signal<string | null>(null);
  readonly msg = signal('');
  readonly trashMode = signal(false);
  readonly pageTitle = signal('Tous les documents');

  moduleFilter = '';
  q = '';
  docType = '';
  year: number | null = null;
  recentDays: number | null = null;
  mine = false;

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((qp) => {
      this.moduleFilter = qp.get('module_code') || '';
      this.q = qp.get('q') || '';
      this.docType = qp.get('doc_type') || '';
      const y = qp.get('year');
      this.year = y ? Number(y) : null;
      const rd = qp.get('recent_days');
      this.recentDays = rd ? Number(rd) : null;
      this.mine = qp.get('mine') === '1';
      const trash = this.router.url.includes('/corbeille') || qp.get('trash') === '1';
      this.trashMode.set(trash);
      this.pageTitle.set(trash ? 'Corbeille' : this.mine ? 'Mes documents' : 'Tous les documents');
      if (this.moduleFilter === 'achats-appro') this.pageTitle.set('Documents Achats');
      if (this.moduleFilter === 'stock-fournitures') this.pageTitle.set('Documents Stock');
      if (this.moduleFilter === 'notes-frais') this.pageTitle.set('Documents Notes de frais');
      if (this.moduleFilter === 'contrats-echeances') this.pageTitle.set('Documents Contrats');
      this.page.set(1);
      this.load();
    });
  }

  ocrLabel(status: string | null | undefined): string {
    switch (status) {
      case 'processing':
        return 'En cours';
      case 'done':
        return 'Termine';
      case 'failed':
        return 'Echec';
      default:
        return 'En attente';
    }
  }

  moduleLabel(code: string | null): string {
    const map: Record<string, string> = {
      'stock-fournitures': 'Stock',
      'achats-appro': 'Achats',
      'notes-frais': 'Notes de frais',
      'contrats-echeances': 'Contrats',
    };
    return (code && map[code]) || code || '—';
  }

  entityLabel(entity: string | null): string {
    const map: Record<string, string> = {
      article: 'Article',
      demande_fourniture: 'Demande stock',
      inventaire: 'Inventaire',
      bon_commande: 'Bon de commande',
      achat_demande: 'Demande achat',
      achat_facture: 'Facture',
      achat_reception: 'Reception',
      achat_paiement: 'Paiement',
      fournisseur: 'Fournisseur',
      note_frais: 'Note de frais',
      contrat: 'Contrat',
    };
    return (entity && map[entity]) || entity || '—';
  }

  sizeLabel(bytes: number | null): string {
    if (bytes == null) return '—';
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  }

  entityLink(d: Doc): string[] | null {
    if (!d.module_code || !d.entity || !d.entity_id) return null;
    const id = d.entity_id;
    if (d.module_code === 'stock-fournitures') {
      if (d.entity === 'article') return ['/stock-fournitures/articles', id];
      if (d.entity === 'demande_fourniture') return ['/stock-fournitures/demandes', id];
      if (d.entity === 'inventaire') return ['/stock-fournitures/inventaires'];
    }
    if (d.module_code === 'achats-appro') {
      if (d.entity === 'bon_commande') return ['/achats-appro/bons', id];
      if (d.entity === 'achat_demande') return ['/achats-appro/demandes', id];
      if (d.entity === 'achat_facture') return ['/achats-appro/factures', id];
      if (d.entity === 'achat_reception') return ['/achats-appro/receptions', id];
      if (d.entity === 'achat_paiement') return ['/achats-appro/paiements', id];
      if (d.entity === 'fournisseur') return ['/achats-appro/fournisseurs', id];
    }
    if (d.module_code === 'notes-frais' && d.entity === 'note_frais') return ['/notes-frais/notes', id];
    if (d.module_code === 'contrats-echeances' && d.entity === 'contrat') return ['/contrats-echeances', id];
    return null;
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  load(): void {
    this.erreur.set(null);
    const params: Record<string, string | number | boolean> = {
      page: this.page(),
      size: this.pageSize,
    };
    if (this.moduleFilter) params['module_code'] = this.moduleFilter;
    if (this.q.trim()) params['q'] = this.q.trim();
    if (this.docType.trim()) params['doc_type'] = this.docType.trim();
    if (this.year) params['year'] = this.year;
    if (this.recentDays) params['recent_days'] = this.recentDays;
    if (this.mine) params['mine'] = 'true';
    if (this.trashMode()) params['trash'] = 'true';
    this.api.get<Paginated<Doc>>('/mg/archives/documents', params).subscribe({
      next: (res) => {
        this.docs.set(res.items);
        this.total.set(res.total);
      },
      error: () => {
        this.docs.set([]);
        this.total.set(0);
        this.erreur.set('Chargement archives impossible.');
      },
    });
  }

  download(d: Doc): void {
    this.api.download(`/mg/archives/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename || 'document';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Telechargement impossible.'),
    });
  }

  softDelete(d: Doc): void {
    this.api.delete(`/mg/archives/documents/${d.id}`).subscribe({
      next: () => {
        this.msg.set(`${d.filename} deplace dans la corbeille.`);
        this.load();
      },
      error: () => this.erreur.set('Suppression refusee.'),
    });
  }

  restore(d: Doc): void {
    this.api.post(`/mg/archives/documents/${d.id}/restore`, {}).subscribe({
      next: () => {
        this.msg.set(`${d.filename} restaure.`);
        this.load();
      },
      error: () => this.erreur.set('Restauration refusee.'),
    });
  }

  retryOcr(d: Doc): void {
    this.api.post<Doc>(`/mg/archives/documents/${d.id}/retry-ocr`, {}).subscribe({
      next: () => {
        this.msg.set(`OCR relance pour ${d.filename}.`);
        this.load();
      },
      error: () => this.erreur.set('Relance OCR refusee.'),
    });
  }

  onFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const module_code = this.moduleFilter || 'achats-appro';
    this.api.upload<Doc>('/mg/archives/documents', file, {
      module_code,
      entity: 'manuel',
      entity_id: crypto.randomUUID(),
      doc_type: 'JUSTIFICATIF',
      title: file.name,
    }).subscribe({
      next: () => {
        this.msg.set('Document depose — OCR en cours.');
        this.load();
      },
      error: () => this.erreur.set('Upload refuse (permission create/archive ?).'),
    });
    input.value = '';
  }
}
