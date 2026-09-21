import { ChangeDetectionStrategy, Component, Input, OnChanges, inject, signal } from '@angular/core';
import { ApiService } from '../core/services/api.service';

interface GedDoc {
  id: string;
  filename: string;
  size_bytes: number;
}

@Component({
  selector: 'bea-mg-ged',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-stock-panel" style="margin-top:1rem">
      <h2>Pièces jointes (GED)</h2>
      @if (!entityId) {
        <p class="bea-stock-panel__empty">Enregistrer d’abord la fiche pour attacher des fichiers.</p>
      } @else {
        <input type="file" (change)="onFile($event)" />
        @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
        <ul>
          @for (d of docs(); track d.id) {
            <li>{{ d.filename }} ({{ d.size_bytes }} o)</li>
          } @empty {
            <li>Aucun document.</li>
          }
        </ul>
      }
    </section>
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
