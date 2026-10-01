import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  forwardRef,
  inject,
  input,
  signal,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';

export interface SupplierOption {
  id: string;
  code: string;
  raison_sociale: string;
  telephone?: string | null;
  email?: string | null;
  is_active?: boolean;
}

/** Sélecteur fournisseurs actifs — recherche code / nom / téléphone. */
@Component({
  selector: 'bea-supplier-select',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => SupplierSelectComponent),
      multi: true,
    },
  ],
  template: `
    <div class="bea-supplier-select">
      <label class="bea-ach__field bea-ach__field--grow" style="width:100%;min-width:0">
        <mat-icon>storefront</mat-icon>
        <input
          type="search"
          [value]="query()"
          [disabled]="disabled()"
          [placeholder]="placeholder()"
          (input)="onQuery($event)"
          (focus)="open.set(true)"
          autocomplete="off"
        />
      </label>
      @if (selected(); as s) {
        <div class="bea-supplier-select__chip">
          <code class="bea-ach__code">{{ s.code }}</code>
          <span>{{ s.raison_sociale }}</span>
          @if (!disabled()) {
            <button type="button" class="bea-ach__icon-btn" title="Effacer" (click)="clear()">
              <mat-icon>close</mat-icon>
            </button>
          }
        </div>
      }
      @if (open() && !disabled()) {
        <ul class="bea-supplier-select__list" role="listbox">
          @for (o of options(); track o.id) {
            <li>
              <button type="button" (click)="pick(o)">
                <code class="bea-ach__code">{{ o.code }}</code>
                <strong>{{ o.raison_sociale }}</strong>
                <span>{{ o.telephone || o.email || '' }}</span>
              </button>
            </li>
          } @empty {
            <li class="bea-supplier-select__empty">Aucun fournisseur actif</li>
          }
        </ul>
      }
    </div>
  `,
  styles: [
    `
      .bea-supplier-select {
        position: relative;
        display: grid;
        gap: 0.35rem;
        width: 100%;
      }
      .bea-supplier-select__chip {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        font-size: 0.85rem;
        color: #0f172a;
      }
      .bea-supplier-select__list {
        position: absolute;
        z-index: 20;
        top: calc(100% + 2px);
        left: 0;
        right: 0;
        margin: 0;
        padding: 0.25rem;
        list-style: none;
        max-height: 14rem;
        overflow: auto;
        background: #fff;
        border: 1px solid #cbd5e1;
        border-radius: 0.65rem;
        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.12);
      }
      .bea-supplier-select__list button {
        display: grid;
        grid-template-columns: auto 1fr;
        gap: 0.15rem 0.55rem;
        width: 100%;
        text-align: left;
        border: 0;
        background: transparent;
        padding: 0.45rem 0.55rem;
        border-radius: 0.45rem;
        cursor: pointer;
        font: inherit;
        color: #0f172a;
      }
      .bea-supplier-select__list button span {
        grid-column: 2;
        font-size: 0.78rem;
        color: #64748b;
      }
      .bea-supplier-select__list button:hover {
        background: #eef5fb;
      }
      .bea-supplier-select__empty {
        padding: 0.65rem;
        color: #64748b;
        font-size: 0.85rem;
      }
    `,
  ],
})
export class SupplierSelectComponent implements OnInit, ControlValueAccessor {
  private readonly api = inject(ApiService);

  readonly placeholder = input('Rechercher un fournisseur (code, nom, téléphone)…');
  readonly required = input(false);

  readonly options = signal<SupplierOption[]>([]);
  readonly selected = signal<SupplierOption | null>(null);
  readonly query = signal('');
  readonly open = signal(false);
  readonly disabled = signal(false);

  private onChange: (v: string | null) => void = () => undefined;
  private onTouched: () => void = () => undefined;
  private value: string | null = null;

  ngOnInit(): void {
    this.search('');
  }

  writeValue(value: string | null): void {
    this.value = value;
    if (!value) {
      this.selected.set(null);
      return;
    }
    const found = this.options().find((o) => o.id === value);
    if (found) {
      this.selected.set(found);
      this.query.set(`${found.code} — ${found.raison_sociale}`);
      return;
    }
    this.api.get<SupplierOption>(`/mg/achats/fournisseurs/${value}`).subscribe({
      next: (f) => {
        this.selected.set(f);
        this.query.set(`${f.code} — ${f.raison_sociale}`);
      },
    });
  }

  registerOnChange(fn: (v: string | null) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }

  onQuery(ev: Event): void {
    const q = (ev.target as HTMLInputElement).value;
    this.query.set(q);
    this.open.set(true);
    this.search(q);
    this.onTouched();
  }

  pick(o: SupplierOption): void {
    this.selected.set(o);
    this.value = o.id;
    this.query.set(`${o.code} — ${o.raison_sociale}`);
    this.open.set(false);
    this.onChange(o.id);
    this.onTouched();
  }

  clear(): void {
    this.selected.set(null);
    this.value = null;
    this.query.set('');
    this.onChange(null);
    this.search('');
  }

  private search(q: string): void {
    this.api
      .get<{ items: SupplierOption[] }>('/mg/achats/fournisseurs', {
        q: q.trim(),
        actifs_seulement: 'true',
        page: 1,
        size: 30,
      })
      .subscribe({
        next: (res) => this.options.set(res.items ?? []),
        error: () => this.options.set([]),
      });
  }
}
