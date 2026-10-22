import { ChangeDetectionStrategy, Component, OnInit, computed, forwardRef, inject, input, signal } from '@angular/core';
import {
  AbstractControl,
  ControlValueAccessor,
  NG_VALIDATORS,
  NG_VALUE_ACCESSOR,
  ValidationErrors,
  Validator,
} from '@angular/forms';
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

/** Valeur sentinelle de l'option « Autre (préciser) ». */
export const AUTRE_LIBELLE = '__AUTRE__';

/** Espaces superflus retirés, comme `nettoyer_libelle` côté serveur. */
export function nettoyerLibelle(valeur: string | null | undefined): string {
  return (valeur ?? '').replace(/\s+/g, ' ').trim();
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
  providers: [
    { provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => OrgEntiteLibelleSelectComponent), multi: true },
    { provide: NG_VALIDATORS, useExisting: forwardRef(() => OrgEntiteLibelleSelectComponent), multi: true },
  ],
  template: `
    <select
      class="bea-org-select"
      [disabled]="disabled()"
      [attr.aria-label]="ariaLabel()"
      (change)="choisir($any($event.target).value)"
      (blur)="onTouched()"
    >
      <option value="" [selected]="!value()">{{ placeholder() }}</option>
      @if (!autre() && ancienneSaisie(); as ancienne) {
        <option [value]="ancienne" selected>{{ ancienne }} — ancienne saisie, non rattachée</option>
      }
      @for (e of options(); track e.id) {
        <option [value]="e.libelle" [selected]="!saisieLibre() && e.id === selectionId()">
          {{ indent(e) }}{{ e.libelle }}{{ e.sigle ? ' (' + e.sigle + ')' : '' }}{{ e.a_confirmer ? ' — à confirmer' : '' }}
        </option>
      }
      @if (autre()) {
        <option [value]="AUTRE" [selected]="saisieLibre()">Autre (préciser)…</option>
      }
    </select>
    @if (saisieLibre()) {
      <input
        class="bea-org-select bea-org-select__autre"
        maxlength="120"
        autocomplete="off"
        placeholder="Département ou service absent de la liste"
        aria-label="Département / service saisi (Autre)"
        [disabled]="disabled()"
        [value]="texteLibre()"
        [attr.aria-invalid]="!!erreurLibre()"
        (input)="saisir($any($event.target).value)"
        (blur)="libreTouche.set(true); onTouched()"
      />
      @if (erreurLibre(); as e) {
        <small class="bea-org-select__err">{{ e }}</small>
      } @else {
        <small class="bea-org-select__hint">Enregistré tel quel, sans être ajouté à l’organigramme.</small>
      }
    }
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
      .bea-org-select__autre {
        margin-top: 0.4rem;
      }
      .bea-org-select__err,
      .bea-org-select__hint {
        display: block;
        margin-top: 0.25rem;
        font-size: 0.78rem;
      }
      .bea-org-select__err {
        color: var(--bea-danger, #c0392b);
      }
      .bea-org-select__hint {
        opacity: 0.7;
      }
    `,
  ],
})
export class OrgEntiteLibelleSelectComponent implements ControlValueAccessor, Validator, OnInit {
  private readonly referentiel = inject(OrgReferentielService);
  protected readonly AUTRE = AUTRE_LIBELLE;

  /** Ajoute « Autre (préciser) » : libellé libre, enregistré sans créer d'entité. */
  readonly autre = input(false);
  readonly saisieLibre = signal(false);
  readonly texteLibre = signal('');
  protected readonly libreTouche = signal(false);

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

  readonly erreurLibre = computed(() => (this.libreTouche() ? this.erreurTexte() : null));

  private onChange: (v: string | null) => void = () => {};
  private onValidatorChange: () => void = () => {};
  onTouched: () => void = () => {};

  ngOnInit(): void {
    this.referentiel.entitesActives().subscribe({
      next: (items) => {
        this.entites.set(items);
        this.basculerSaisieLibre();
      },
    });
  }

  indent(e: OrgEntiteOption): string {
    return '\u00a0\u00a0'.repeat(Math.max(0, (e.profondeur ?? 0) - 1));
  }

  choisir(libelle: string): void {
    if (libelle === AUTRE_LIBELLE) {
      this.saisieLibre.set(true);
      this.libreTouche.set(false);
      this.texteLibre.set('');
      this.value.set(null);
      this.onChange(null);
      this.onValidatorChange();
      return;
    }
    this.saisieLibre.set(false);
    const v = libelle || null;
    this.value.set(v);
    this.onChange(v);
    this.onValidatorChange();
  }

  saisir(texte: string): void {
    this.texteLibre.set(texte);
    this.libreTouche.set(true);
    const v = nettoyerLibelle(texte) || null;
    this.value.set(v);
    this.onChange(v);
  }

  writeValue(v: string | null): void {
    this.value.set(v || null);
    this.saisieLibre.set(false);
    this.basculerSaisieLibre();
  }

  validate(_control: AbstractControl): ValidationErrors | null {
    const e = this.erreurTexte();
    return e ? { orgAutre: e } : null;
  }

  registerOnValidatorChange(fn: () => void): void {
    this.onValidatorChange = fn;
  }

  /** Valeur texte hors référentiel avec `autre` actif : affichée comme saisie « Autre ». */
  private basculerSaisieLibre(): void {
    const v = this.value();
    if (this.autre() && v && this.entites().length && !this.selectionId()) {
      this.saisieLibre.set(true);
      this.texteLibre.set(v);
    }
  }

  private erreurTexte(): string | null {
    if (!this.saisieLibre()) return null;
    const v = nettoyerLibelle(this.texteLibre());
    if (!v) return 'Saisissez le nom du département ou du service.';
    if (v.length > 120) return '120 caractères au plus.';
    const cle = orgCle(v);
    const existante = this.entites().find((e) => orgCle(e.libelle) === cle || (e.alias ?? []).includes(cle));
    return existante ? `« ${existante.libelle} » existe déjà dans la liste : sélectionnez-le au lieu de « Autre ».` : null;
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
