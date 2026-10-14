import { ChangeDetectionStrategy, Component, computed, inject, input, model } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AUTRE, Dossier, RefItem } from '../reclamations.models';
import { ReclamationsStore } from '../reclamations.service';

/** Type → motif → sous-motif. `motif` / `sous_motif` : id du référentiel, `AUTRE` ou vide. */
export interface Classement {
  type_id: string;
  motif: string;
  motif_autre: string;
  sous_motif: string;
  sous_motif_autre: string;
}

export const CLASSEMENT_VIDE: Classement = { type_id: '', motif: '', motif_autre: '', sous_motif: '', sous_motif_autre: '' };

export function classementDe(d: Dossier): Classement {
  return {
    type_id: d.type_ref?.id ?? '',
    motif: d.motif_autre ? AUTRE : (d.motif_ref?.id ?? ''),
    motif_autre: d.motif_autre ?? '',
    sous_motif: d.sous_motif_autre ? AUTRE : (d.sous_motif_ref?.id ?? ''),
    sous_motif_autre: d.sous_motif_autre ?? '',
  };
}

export function classementErreur(c: Classement): string | null {
  if (c.motif === AUTRE && !c.motif_autre.trim()) return 'Précisez le motif « Autre ».';
  if (c.sous_motif === AUTRE && !c.sous_motif_autre.trim()) return 'Précisez le sous-motif « Autre ».';
  return null;
}

/** Corps API : chaque niveau est soit un id du référentiel, soit une saisie libre. */
export function classementCorps(c: Classement): Record<string, string | null> {
  return {
    type_id: c.type_id || null,
    motif_id: c.motif && c.motif !== AUTRE ? c.motif : null,
    motif_autre: c.motif === AUTRE ? c.motif_autre.trim() : null,
    sous_motif_id: c.sous_motif && c.sous_motif !== AUTRE ? c.sous_motif : null,
    sous_motif_autre: c.sous_motif === AUTRE ? c.sous_motif_autre.trim() : null,
  };
}

@Component({
  selector: 'bea-rc-classement',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <div class="bea-rc-row">
      <label>Type de réclamation
        <select [value]="valeur().type_id" (change)="choisirType(champ($event))">
          <option value="">— À qualifier —</option>
          @for (t of store.refs('TYPE'); track t.id) { <option [value]="t.id" [selected]="t.id === valeur().type_id">{{ lib(t) }}</option> }
        </select>
      </label>
      <label>Motif
        <select [value]="valeur().motif" (change)="choisirMotif(champ($event))">
          <option value="">— Choisir —</option>
          @for (m of motifs(); track m.id) { <option [value]="m.id" [selected]="m.id === valeur().motif">{{ lib(m) }}</option> }
          <option [value]="autre" [selected]="valeur().motif === autre">Autre (préciser)</option>
        </select>
        @if (!motifs().length) {
          <span class="bea-rc-hint">{{ valeur().type_id ? 'Aucun motif pour ce type' : 'Aucun motif au référentiel' }} : choisissez « Autre ».</span>
        }
      </label>
      <label>Sous-motif
        <select [value]="valeur().sous_motif" (change)="choisirSousMotif(champ($event))" [disabled]="!valeur().motif">
          <option value="">{{ valeur().motif ? '— Aucun —' : '— Choisir d’abord un motif —' }}</option>
          @for (m of sousMotifs(); track m.id) { <option [value]="m.id" [selected]="m.id === valeur().sous_motif">{{ lib(m) }}</option> }
          @if (valeur().motif) { <option [value]="autre" [selected]="valeur().sous_motif === autre">Autre (préciser)</option> }
        </select>
      </label>
    </div>
    @if (valeur().motif === autre || valeur().sous_motif === autre) {
      <div class="bea-rc-row">
        @if (valeur().motif === autre) {
          <label>Précisez le motif <em>*</em>
            <input [value]="valeur().motif_autre" (input)="maj({ motif_autre: champ($event) })" maxlength="200"
                   [class.is-invalid]="tente() && !valeur().motif_autre.trim()" placeholder="Motif non prévu au référentiel" />
            @if (tente() && !valeur().motif_autre.trim()) { <span class="bea-rc-err">Le motif « Autre » doit être précisé</span> }
          </label>
        }
        @if (valeur().sous_motif === autre) {
          <label>Précisez le sous-motif <em>*</em>
            <input [value]="valeur().sous_motif_autre" (input)="maj({ sous_motif_autre: champ($event) })" maxlength="200"
                   [class.is-invalid]="tente() && !valeur().sous_motif_autre.trim()" />
            @if (tente() && !valeur().sous_motif_autre.trim()) { <span class="bea-rc-err">Le sous-motif « Autre » doit être précisé</span> }
          </label>
        }
      </div>
    }
    @if (store.cap('referentiels_gerer')) {
      <p class="bea-rc-hint">Motifs et sous-motifs : <a routerLink="/reclamations/parametres">gérer le référentiel</a> (ajout, modification, activation).</p>
    }
  `,
})
export class RcClassementComponent {
  readonly store = inject(ReclamationsStore);
  readonly valeur = model.required<Classement>();
  readonly tente = input(false);
  readonly autre = AUTRE;

  readonly motifs = computed(() => {
    const t = this.valeur().type_id;
    return t ? this.store.enfants('MOTIF', t) : this.store.refs('MOTIF');
  });
  readonly sousMotifs = computed(() => {
    const m = this.valeur().motif;
    return m && m !== AUTRE ? this.store.enfants('SOUS_MOTIF', m) : [];
  });

  lib(r: RefItem): string {
    return r.libelle;
  }

  champ(e: Event): string {
    return (e.target as HTMLInputElement | HTMLSelectElement).value;
  }

  maj(partiel: Partial<Classement>): void {
    this.valeur.update((v) => ({ ...v, ...partiel }));
  }

  choisirType(typeId: string): void {
    const v = this.valeur();
    const motif = this.store.refs('MOTIF', true).find((m) => m.id === v.motif);
    const garde = !motif || (typeId && motif.parent_id === typeId);
    this.maj(garde ? { type_id: typeId } : { type_id: typeId, motif: '', sous_motif: '', sous_motif_autre: '' });
  }

  choisirMotif(motifId: string): void {
    const v = this.valeur();
    if (motifId === AUTRE || !motifId) {
      const sous = v.sous_motif === AUTRE ? AUTRE : '';
      this.maj({ motif: motifId, sous_motif: motifId ? sous : '', sous_motif_autre: motifId ? v.sous_motif_autre : '' });
      return;
    }
    const motif = this.store.refs('MOTIF', true).find((m) => m.id === motifId);
    const sous = this.store.refs('SOUS_MOTIF', true).find((m) => m.id === v.sous_motif);
    this.maj({
      motif: motifId,
      motif_autre: '',
      type_id: motif?.parent_id ?? v.type_id,
      sous_motif: v.sous_motif === AUTRE || (sous && sous.parent_id === motifId) ? v.sous_motif : '',
    });
  }

  choisirSousMotif(id: string): void {
    this.maj(id === AUTRE ? { sous_motif: id } : { sous_motif: id, sous_motif_autre: '' });
  }
}
