import { ChangeDetectionStrategy, Component, Input, OnChanges, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';

interface GedDoc {
  id: string;
  filename: string;
  size_bytes: number;
}

@Component({
  selector: 'bea-mg-ged',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <section class="bea-mg-ged">
      <div class="bea-mg-ged__head">
        <h3>Pièces jointes (GED)</h3>
        @if (entityId) {
          <label class="bea-mg__btn bea-mg__btn--ghost bea-mg-ged__upload">
            <mat-icon>attach_file</mat-icon>
            Ajouter
            <input type="file" hidden (change)="onFile($event)" />
          </label>
        }
      </div>
      @if (!entityId) {
        <p class="bea-stock-page__kicker">Enregistrer d’abord la fiche pour attacher des fichiers.</p>
      } @else {
        @if (erreur()) {
          <p class="bea-stock-page__error">{{ erreur() }}</p>
        }
        <ul class="bea-mg-ged__list">
          @for (d of docs(); track d.id) {
            <li>
              <mat-icon>description</mat-icon>
              <span>{{ d.filename }}</span>
              <small>{{ sizeLabel(d.size_bytes) }}</small>
              <button
                type="button"
                class="bea-mg-ged__dl"
                title="Télécharger"
                (click)="download(d)"
              >
                <mat-icon>download</mat-icon>
              </button>
            </li>
          } @empty {
            <li class="bea-mg-ged__empty">Aucun document.</li>
          }
        </ul>
      }
    </section>
  `,
  styles: `
    .bea-mg-ged {
      margin-top: 1rem;
      padding-top: 0.85rem;
      border-top: 1px solid #e2e8f0;
    }
    .bea-mg-ged__head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      margin-bottom: 0.65rem;
    }
    .bea-mg-ged__head h3 {
      margin: 0;
      font-size: 0.95rem;
      font-weight: 650;
      color: #0f172a;
    }
    .bea-mg-ged__upload {
      cursor: pointer;
      margin: 0;
    }
    .bea-mg-ged__list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.35rem;
    }
    .bea-mg-ged__list li {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.45rem 0.55rem;
      border-radius: 0.5rem;
      background: #f8fafc;
      font-size: 0.88rem;
      color: #334155;
    }
    .bea-mg-ged__list mat-icon {
      font-size: 1.1rem;
      width: 1.1rem;
      height: 1.1rem;
      color: #64748b;
    }
    .bea-mg-ged__list span {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bea-mg-ged__list small {
      color: #94a3b8;
      font-size: 0.75rem;
      white-space: nowrap;
    }
    .bea-mg-ged__dl {
      display: inline-grid;
      place-items: center;
      width: 1.75rem;
      height: 1.75rem;
      border: 1px solid #e2e8f0;
      border-radius: 0.4rem;
      background: #fff;
      color: #1a5278;
      cursor: pointer;
      padding: 0;
    }
    .bea-mg-ged__dl:hover {
      border-color: #1a5278;
      background: #f0f7fc;
    }
    .bea-mg-ged__dl mat-icon {
      font-size: 1rem;
      width: 1rem;
      height: 1rem;
      color: inherit;
    }
    .bea-mg-ged__empty {
      color: #94a3b8;
      background: transparent !important;
      padding-left: 0 !important;
    }
  `,
})
export class MgGedPanelComponent implements OnChanges {
  @Input({ required: true }) moduleCode!: string;
  @Input({ required: true }) entity!: string;
  @Input() entityId: string | null = null;
  @Input() espaceCode = 'moyens-generaux';

  private readonly api = inject(ApiService);
  readonly docs = signal<GedDoc[]>([]);
  readonly erreur = signal<string | null>(null);

  ngOnChanges(): void {
    this.reload();
  }

  sizeLabel(bytes: number): string {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  }

  reload(): void {
    if (!this.entityId) {
      this.docs.set([]);
      return;
    }
    const q = `module_code=${encodeURIComponent(this.moduleCode)}&entity=${encodeURIComponent(this.entity)}&entity_id=${encodeURIComponent(this.entityId)}`;
    this.api.get<{ items: GedDoc[] }>(`/ged/documents?${q}`).subscribe({
      next: (res) => this.docs.set(res.items ?? []),
      error: () => this.erreur.set('Lecture GED impossible (permission ged.read ?).'),
    });
  }

  download(doc: GedDoc): void {
    this.api.download(`/ged/documents/${doc.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = doc.filename || 'document';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Téléchargement impossible.'),
    });
  }

  onFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !this.entityId) return;
    this.api
      .upload<GedDoc>('/ged/documents', file, {
        espace_code: this.espaceCode,
        module_code: this.moduleCode,
        entity: this.entity,
        entity_id: this.entityId,
      })
      .subscribe({
        next: () => {
          this.erreur.set(null);
          this.reload();
          input.value = '';
        },
        error: () => this.erreur.set('Upload GED refusé (permission ged.write ?).'),
      });
  }
}
