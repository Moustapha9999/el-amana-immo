import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormGroup, ReactiveFormsModule } from '@angular/forms';
import { ChampPaiement } from './facturation.models';

/** Champs de paiement communs aux formulaires : moyen + détail exigé par ce moyen (configuré backend). */
@Component({
  selector: 'bea-fx-paiement-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule],
  host: { style: 'display: contents' },
  template: `
    <ng-container [formGroup]="group()">
      <label>Moyen de paiement *
        <select formControlName="mode_paiement">
          <option value="">— Sélectionner —</option>
          @for (m of modes(); track m) { <option [value]="m">{{ m }}</option> }
        </select>
      </label>
      @for (c of champs(); track c.champ) {
        @if (c.champ === 'carte_derniers_chiffres') {
          <label>{{ c.libelle }}{{ c.obligatoire ? ' *' : '' }}
            <input formControlName="carte_derniers_chiffres" inputmode="numeric" maxlength="4" pattern="[0-9]{4}" placeholder="1234" autocomplete="off" />
            <small class="bea-fx-form__hint">Le numéro complet de la carte n'est jamais saisi ni conservé.</small>
          </label>
        } @else {
          <label>{{ c.libelle }}{{ c.obligatoire ? ' *' : '' }}
            <input [formControlName]="c.champ" [attr.maxlength]="c.champ === 'reference_paiement' ? 120 : c.champ === 'numero_cheque' ? 40 : 120" autocomplete="off" />
          </label>
        }
      }
    </ng-container>
  `,
})
export class FxPaiementDetailComponent implements OnInit {
  readonly group = input.required<FormGroup>();
  readonly moyens = input<Record<string, ChampPaiement[]>>({});
  readonly modesListe = input<string[]>([]);

  private readonly destroyRef = inject(DestroyRef);
  private readonly mode = signal('');

  readonly modes = computed(() => {
    const liste = this.modesListe().length ? this.modesListe() : Object.keys(this.moyens());
    const actuel = this.mode();
    return actuel && !liste.includes(actuel) ? [...liste, actuel] : liste;
  });
  readonly champs = computed(() => this.moyens()[this.mode()] ?? []);

  ngOnInit(): void {
    const ctrl = this.group().get('mode_paiement');
    this.mode.set(ctrl?.value ?? '');
    const sub = ctrl?.valueChanges.subscribe((v) => this.mode.set(v ?? ''));
    this.destroyRef.onDestroy(() => sub?.unsubscribe());
  }
}

/** Valeurs de détail à envoyer : uniquement les champs exigés par le moyen choisi. */
export function corpsDetailPaiement(
  v: Partial<Record<ChampPaiement['champ'], string | null>>,
  champs: ChampPaiement[] | undefined,
): Record<string, string | null> {
  const out: Record<string, string | null> = { compte: null, banque: null, numero_cheque: null, carte_derniers_chiffres: null, reference_paiement: null };
  for (const c of champs ?? []) out[c.champ] = v[c.champ]?.trim() || null;
  return out;
}
