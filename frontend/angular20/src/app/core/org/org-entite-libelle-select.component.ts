import { ChangeDetectionStrategy, Component, OnInit, computed, forwardRef, inject, input, signal } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { OrgReferentielService } from './org-referentiel.service';
import { OrgEntiteOption, OrgTypeEntite } from './org-referentiel.models';

/** Même normalisation que la fonction SQL `org_cle` (accents, casse, ponctuation). */
export function orgCle(texte: string | null | undefined): string {
  return (texte ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

/**
 * Sélecteur d'entité de l'organigramme pour les champs « département / service » encore stockés en
 * texte (`departement`). Valeur = libellé exact de l'entité : la base rattache alors `org_entite_id`
 * automatiquement (déclencheur `org_rattacher_texte`). Une ancienne saisie qui ne correspond à
 * aucune entité reste affichée et conservée tant que l'utilisateur ne choisit pas une entité.
 */
@Component({
  selector: 'bea-org-entite-libelle-select',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [{ provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => OrgEntiteLibelleSelectComponent), multi: true }],
  template: `
    <select
      class="bea-org-select"
      [disabled]="disabled()"
      [attr.aria-label]="ariaLabel()"
      (change)="choisir($any($event.target).value)"
      (blur)="onTouched()"
    >
      <option value="" [selected]="!value()">{{ placeholder() }}</option>
      @if (ancienneSaisie(); as ancienne) {
        <option [value]="ancienne" selected>{{ ancienne }} — ancienne saisie, non rattachée</option>
      }
      @for (e of options(); track e.id) {
        <option [value]="e.libelle" [selected]="e.id === selectionId()">
          {{ indent(e) }}{{ e.libelle }}{{ e.sigle ? ' (' + e.sigle + ')' : '' }}{{ e.a_confirmer ? ' — à confirmer' : '' }}
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
export class OrgEntiteLibelleSelectComponent implements ControlValueAccessor, OnInit {
  private readonly referentiel = inject(OrgReferentielService);

  /** Par défaut : niveaux opérationnels (pas le Conseil ni les comités). */
  readonly types = input<OrgTypeEntite[]>(['DIRECTION_GENERALE', 'DIRECTION', 'DEPARTEMENT', 'SERVICE', 'SECTION', 'CELLULE']);
  readonly placeholder = input('— Choisir dans l’organigramme —');
  readonly ariaLabel = input('Département / service (organigramme)');

  private readonly entites = signal<OrgEntiteOption[]>([]);
  readonly value = signal<string | null>(null);
  readonly disabled = signal(false);

  readonly options = computed(() => {
    const types = this.types();
    return this.entites().filter((e) => !types.length || types.includes(e.type_entite));
  });

  /** Entité correspondant à la valeur texte (libellé ou alias), comme le rattachement en base. */
  readonly selectionId = computed(() => {
    const cle = orgCle(this.value());
    if (!cle) return null;
    const trouvees = this.entites().filter((e) => orgCle(e.libelle) === cle || (e.alias ?? []).includes(cle));
    return trouvees[0]?.id ?? null;
  });

  readonly ancienneSaisie = computed(() => {
    const v = this.value();
    return v && !this.selectionId() && this.entites().length ? v : null;
  });

  private onChange: (v: string | null) => void = () => {};
  onTouched: () => void = () => {};

  ngOnInit(): void {
    this.referentiel.entitesActives().subscribe({ next: (items) => this.entites.set(items) });
  }

  indent(e: OrgEntiteOption): string {
    return '\u00a0\u00a0'.repeat(Math.max(0, (e.profondeur ?? 0) - 1));
  }

  choisir(libelle: string): void {
    const v = libelle || null;
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
}
