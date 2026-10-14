import { ChangeDetectionStrategy, Component, computed, inject, input, model } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { UiDialogService } from '../../shared/ui-dialog/ui-dialog.service';
import { OperationSaisie, lireMontant, montantFr } from '../reclamations.models';

/** Erreur de saisie de la liste (référence obligatoire et unique, montant > 0 à 2 décimales), sinon `null`. */
export function operationsErreur(lignes: OperationSaisie[]): string | null {
  const vues = new Set<string>();
  for (const [i, l] of lignes.entries()) {
    const ref = l.reference.trim();
    if (!ref) return `Opération ${i + 1} : la référence est obligatoire.`;
    if (lireMontant(l.montant) === null) return `Opération ${i + 1} : montant positif en MRU, deux décimales au plus.`;
    const cle = ref.toLocaleLowerCase('fr');
    if (vues.has(cle)) return `L’opération « ${ref} » est saisie deux fois.`;
    vues.add(cle);
  }
  return null;
}

export function operationsCorps(lignes: OperationSaisie[]): Array<{ reference: string; montant: number }> {
  return lignes.map((l) => ({ reference: l.reference.trim(), montant: lireMontant(l.montant) ?? 0 }));
}

/** Section « Opérations concernées » : lignes référence + montant (MRU), ajout / retrait, total. */
@Component({
  selector: 'bea-rc-operations',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (lignes().length) {
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table bea-rc-ops">
          <thead><tr><th class="bea-rc-ops__n">N°</th><th>Référence de l’opération <em>*</em></th><th class="bea-rc-ops__m">Montant (MRU) <em>*</em></th><th class="bea-rc-ops__x"></th></tr></thead>
          <tbody>
            @for (l of lignes(); track $index; let i = $index) {
              <tr>
                <td class="bea-rc-ops__n">{{ i + 1 }}</td>
                <td>
                  <input class="bea-rc-input" [value]="l.reference" (input)="maj(i, 'reference', $event)" maxlength="120"
                         [attr.aria-label]="'Référence de l’opération ' + (i + 1)"
                         [class.is-invalid]="tente() && !l.reference.trim()" placeholder="N° de transaction, de virement…" />
                </td>
                <td class="bea-rc-ops__m">
                  <input class="bea-rc-input" [value]="l.montant" (input)="maj(i, 'montant', $event)" inputmode="decimal"
                         [attr.aria-label]="'Montant de l’opération ' + (i + 1)"
                         [class.is-invalid]="(tente() || l.montant !== '') && montantInvalide(l)" placeholder="0,00" />
                </td>
                <td class="bea-rc-ops__x">
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="retirer(i)" [attr.aria-label]="'Retirer l’opération ' + (i + 1)">
                    <mat-icon>delete</mat-icon>
                  </button>
                </td>
              </tr>
            }
          </tbody>
          <tfoot>
            <tr>
              <td colspan="2"><strong>{{ lignes().length }} opération{{ lignes().length > 1 ? 's' : '' }}</strong></td>
              <td class="bea-rc-ops__m"><strong>{{ total() }}</strong></td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    } @else {
      <p class="bea-rc-muted">Aucune opération rattachée. Ajoutez-en une si la réclamation porte sur une ou plusieurs transactions.</p>
    }
    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ajouter()"><mat-icon>add</mat-icon> Ajouter une opération</button>
  `,
})
export class RcOperationsComponent {
  private readonly dialog = inject(UiDialogService);
  readonly lignes = model.required<OperationSaisie[]>();
  readonly tente = input(false);

  readonly total = computed(() => {
    const montants = this.lignes().map((l) => lireMontant(l.montant));
    const somme = montants.reduce<number>((a, m) => a + (m ?? 0), 0);
    return montantFr(Math.round(somme * 100) / 100);
  });

  montantInvalide(l: OperationSaisie): boolean {
    return lireMontant(l.montant) === null;
  }

  maj(i: number, champ: keyof OperationSaisie, e: Event): void {
    const valeur = (e.target as HTMLInputElement).value;
    this.lignes.update((ls) => ls.map((l, j) => (j === i ? { ...l, [champ]: valeur } : l)));
  }

  ajouter(): void {
    this.lignes.update((ls) => [...ls, { reference: '', montant: '' }]);
  }

  retirer(i: number): void {
    const l = this.lignes()[i];
    const enlever = () => this.lignes.update((ls) => ls.filter((_, j) => j !== i));
    if (!l.reference.trim() && !l.montant.trim()) {
      enlever();
      return;
    }
    this.dialog
      .confirm({
        title: 'Retirer l’opération',
        message: `Retirer l’opération ${l.reference.trim() || i + 1} de la liste ?`,
        hint: 'Le retrait ne sera définitif qu’à l’enregistrement.',
        confirmLabel: 'Retirer',
        tone: 'danger',
        icon: 'delete',
      })
      .subscribe((ok) => {
        if (ok) enlever();
      });
  }
}
