import { ChangeDetectionStrategy, Component, OnInit, computed, forwardRef, inject, input, signal } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { OrgReferentielService } from './org-referentiel.service';
import { OrgEntiteOption, OrgTypeEntite } from './org-referentiel.models';

/**
 * Sélecteur d'entité de l'organigramme BEA (composant partagé, sans dépendance UI).
 * Valeur = id de l'entité (ou null). Compatible `ngModel` et formulaires réactifs.
 *
 * Usage : `<bea-org-entite-select [(ngModel)]="entiteId" />`
 * ou `<bea-org-entite-select formControlName="org_entite_id" [types]="['DIRECTION', 'DEPARTEMENT']" />`.
 */
@Component({
  selector: 'bea-org-entite-select',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [{ provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => OrgEntiteSelectComponent), multi: true }],
  template: `
    <select
      class="bea-org-select"
      [disabled]="disabled()"
      [attr.aria-label]="ariaLabel()"
      [value]="value() ?? ''"
      (change)="choisir($any($event.target).value)"
      (blur)="onTouched()"
    >
      <option value="">{{ placeholder() }}</option>
      @for (e of options(); track e.id) {
        <option [value]="e.id" [selected]="e.id === value()" [disabled]="!e.actif && e.id !== value()">
          {{ indent(e) }}{{ e.libelle }}{{ e.sigle ? ' (' + e.sigle + ')' : '' }}{{ e.actif ? '' : ' — désactivée' }}{{ e.a_confirmer ? ' — à confirmer' : '' }}
        </option>
      }
    </select>
  `,
  styles: [
    `
      :host {
        display: block;
      }
      .bea-org-select {
        width: 100%;
        box-sizing: border-box;
        border: 0;
        border-radius: 8px;
        padding: 0.5rem 0.7rem;
        font: inherit;
        color: var(--bea-ink, inherit);
        background: var(--bea-surface, rgba(127, 127, 127, 0.1));
        outline: none;
        text-overflow: ellipsis;
      }
      .bea-org-select:focus {
        box-shadow: 0 0 0 2px var(--bea-brand-400, #5dade2);
      }
      .bea-org-select:disabled {
        opacity: 0.6;
      }
    `,
  ],
})
export class OrgEntiteSelectComponent implements ControlValueAccessor, OnInit {
  private readonly referentiel = inject(OrgReferentielService);

  /** Liste fournie par l'appelant (ex. CORE ADMIN, inactives comprises). Sinon : entités actives. */
  readonly entites = input<OrgEntiteOption[] | null>(null);
  readonly types = input<OrgTypeEntite[] | null>(null);
  /** Exclut cette entité et ses descendantes (choix d'un parent sans cycle). */
  readonly exclure = input<string | null>(null);
  readonly placeholder = input('— Aucune —');
  readonly ariaLabel = input('Entité de l’organigramme');

  private readonly chargees = signal<OrgEntiteOption[]>([]);
  readonly value = signal<string | null>(null);
  readonly disabled = signal(false);

  readonly options = computed(() => {
    const source = this.entites() ?? this.chargees();
    const types = this.types();
    const exclues = this.descendants(source, this.exclure());
    return source.filter((e) => !exclues.has(e.id) && (!types?.length || types.includes(e.type_entite) || e.id === this.value()));
  });

  private onChange: (v: string | null) => void = () => {};
  onTouched: () => void = () => {};

  ngOnInit(): void {
    if (this.entites() === null) {
      this.referentiel.entitesActives().subscribe({ next: (items) => this.chargees.set(items) });
    }
  }

  indent(e: OrgEntiteOption): string {
    return '\u00a0\u00a0'.repeat(Math.max(0, e.profondeur ?? 0));
  }

  choisir(id: string): void {
    const v = id || null;
    this.value.set(v);
    this.onChange(v);
  }

  writeValue(v: string | null): void {
    this.value.set(v || null);
  }

  registerOnChange(fn: (v: string | null) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(disabled: boolean): void {
    this.disabled.set(disabled);
  }

  private descendants(source: OrgEntiteOption[], racine: string | null): Set<string> {
    const out = new Set<string>();
    if (!racine) return out;
    out.add(racine);
    let ajoute = true;
    while (ajoute) {
      ajoute = false;
      for (const e of source) {
        if (e.parent_id && out.has(e.parent_id) && !out.has(e.id)) {
          out.add(e.id);
          ajoute = true;
        }
      }
    }
    return out;
  }
}
