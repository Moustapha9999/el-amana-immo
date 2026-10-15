import { ChangeDetectionStrategy, Component, computed, inject, input, model } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { formatMontant } from '../../shared/montant.pipe';
import { UiDialogService } from '../../shared/ui-dialog/ui-dialog.service';
import { Operation, OperationSaisie, lireMontant, montantFr } from '../reclamations.models';

export function ligneVide(): OperationSaisie {
  return { reference: '', montant: '', client_racine: '', compte_reference: '', date_operation: '', montant_conteste: '', motif_detail: '' };
}

export function versSaisie(o: Operation): OperationSaisie {
  return {
    reference: o.reference,
    montant: o.montant !== null ? formatMontant(Number(o.montant)) : '',
    client_racine: o.client_racine ?? '',
    compte_reference: o.compte_reference ?? '',
    date_operation: o.date_operation ?? '',
    montant_conteste: o.montant_conteste !== null ? formatMontant(Number(o.montant_conteste)) : '',
    motif_detail: o.motif_detail ?? '',
  };
}

function aujourdhui(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Première erreur bloquante de la liste, sinon `null`. Une même référence peut revenir dans un autre
 * contexte (compte, date, montant) : seule une ligne strictement identique est refusée. */
export function operationsErreur(lignes: OperationSaisie[]): string | null {
  const vues = new Map<string, number>();
  for (const [i, l] of lignes.entries()) {
    const n = i + 1;
    const ref = l.reference.trim();
    if (!ref) return `Opération ${n} : la référence est obligatoire.`;
    const montant = lireMontant(l.montant);
    if (montant === null) return `Opération ${n} : montant positif en MRU, deux décimales au plus.`;
    if (l.montant_conteste.trim()) {
      const conteste = lireMontant(l.montant_conteste);
      if (conteste === null) return `Opération ${n} : montant contesté positif, deux décimales au plus.`;
      if (conteste > montant) return `Opération ${n} : le montant contesté dépasse le montant de l’opération.`;
    }
    const racine = l.client_racine.trim();
    if (racine && !/^\d{6}$/.test(racine)) return `Opération ${n} : l’identifiant client comporte 6 chiffres.`;
    if (l.date_operation && l.date_operation > aujourdhui()) return `Opération ${n} : la date est dans le futur.`;
    const cle = [ref.toLocaleLowerCase('fr'), l.compte_reference.trim().toLocaleLowerCase('fr'), racine, l.date_operation,
      montant, lireMontant(l.montant_conteste) ?? ''].join('|');
    const deja = vues.get(cle);
    if (deja) return `Opération ${n} : identique à l’opération ${deja}.`;
    vues.set(cle, n);
  }
  return null;
}

export function operationsCorps(lignes: OperationSaisie[]): Array<Record<string, string | number | null>> {
  return lignes.map((l) => {
    const conteste = lireMontant(l.montant_conteste);
    return {
      reference: l.reference.trim(),
      montant: lireMontant(l.montant) ?? 0,
      montant_conteste: conteste,
      date_operation: l.date_operation || null,
      client_racine: l.client_racine.trim() || null,
      compte_reference: l.compte_reference.trim() || null,
      motif_detail: l.motif_detail.trim() || null,
    };
  });
}

/** Clients distincts saisis (le client du dossier compris) : plus d'un = regroupement à justifier. */
export function clientsSaisis(lignes: OperationSaisie[], principal: string | null | undefined): number {
  const racines = new Set(lignes.map((l) => l.client_racine.trim()).filter((r) => r));
  if (principal) racines.add(principal);
  return racines.size;
}

/** Section « Opérations concernées » : une ligne par opération (client, compte, référence, date, montants, motif). */
@Component({
  selector: 'bea-rc-operations',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (lignes().length) {
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table bea-rc-ops bea-rc-ops--large">
          <thead><tr>
            <th class="bea-rc-ops__n">N°</th>
            <th class="bea-rc-ops__c" title="Racine (6 chiffres). Vide : titulaire du compte, sinon client du dossier.">Client</th>
            <th class="bea-rc-ops__cpt">Compte</th>
            <th>Référence <em>*</em></th>
            <th class="bea-rc-ops__d">Date</th>
            <th class="bea-rc-ops__m">Montant (MRU) <em>*</em></th>
            <th class="bea-rc-ops__m" title="Par défaut : le montant de l’opération">Montant contesté</th>
            <th>Motif détaillé</th>
            <th class="bea-rc-ops__x"></th>
          </tr></thead>
          <tbody>
            @for (l of lignes(); track $index; let i = $index) {
              <tr>
                <td class="bea-rc-ops__n">{{ i + 1 }}</td>
                <td class="bea-rc-ops__c">
                  <input class="bea-rc-input" [value]="l.client_racine" (input)="maj(i, 'client_racine', $event)" maxlength="6" inputmode="numeric"
                         [attr.aria-label]="'Client de l’opération ' + (i + 1)" [placeholder]="principal() || 'Racine'"
                         [class.is-invalid]="!!l.client_racine.trim() && !racineValide(l)" />
                </td>
                <td class="bea-rc-ops__cpt">
                  <input class="bea-rc-input" [value]="l.compte_reference" (input)="maj(i, 'compte_reference', $event)" maxlength="60"
                         [attr.aria-label]="'Compte de l’opération ' + (i + 1)" placeholder="N° de compte" />
                </td>
                <td>
                  <input class="bea-rc-input" [value]="l.reference" (input)="maj(i, 'reference', $event)" maxlength="120"
                         [attr.aria-label]="'Référence de l’opération ' + (i + 1)"
                         [class.is-invalid]="tente() && !l.reference.trim()" placeholder="N° de transaction, de virement…" />
                </td>
                <td class="bea-rc-ops__d">
                  <input class="bea-rc-input" type="date" [value]="l.date_operation" (input)="maj(i, 'date_operation', $event)" [max]="aujourdhui"
                         [attr.aria-label]="'Date de l’opération ' + (i + 1)" />
                </td>
                <td class="bea-rc-ops__m">
                  <input class="bea-rc-input" [value]="l.montant" (input)="maj(i, 'montant', $event)" (blur)="formater(i, 'montant')" inputmode="decimal"
                         [attr.aria-label]="'Montant de l’opération ' + (i + 1)"
                         [class.is-invalid]="(tente() || l.montant !== '') && montantInvalide(l)" placeholder="0,00" />
                </td>
                <td class="bea-rc-ops__m">
                  <input class="bea-rc-input" [value]="l.montant_conteste" (input)="maj(i, 'montant_conteste', $event)" (blur)="formater(i, 'montant_conteste')" inputmode="decimal"
                         [attr.aria-label]="'Montant contesté de l’opération ' + (i + 1)"
                         [class.is-invalid]="contesteInvalide(l)" placeholder="= montant" />
                </td>
                <td>
                  <input class="bea-rc-input" [value]="l.motif_detail" (input)="maj(i, 'motif_detail', $event)" maxlength="4000"
                         [attr.aria-label]="'Motif détaillé de l’opération ' + (i + 1)" placeholder="Facultatif" />
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
              <td colspan="5"><strong>{{ lignes().length }} opération{{ lignes().length > 1 ? 's' : '' }}</strong></td>
              <td class="bea-rc-ops__m"><strong>{{ total() }}</strong></td>
              <td class="bea-rc-ops__m"><strong>{{ totalConteste() }}</strong></td>
              <td colspan="2"></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p class="bea-rc-hint">Client vide : titulaire du compte s’il est connu, sinon le client du dossier. Un client ou un compte absent de la base reste « à vérifier ».</p>
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
  /** Racine du client du dossier (indication). */
  readonly principal = input<string | null>(null);
  readonly aujourdhui = aujourdhui();

  readonly total = computed(() => this.somme(this.lignes().map((l) => lireMontant(l.montant))));
  readonly totalConteste = computed(() =>
    this.somme(this.lignes().map((l) => (l.montant_conteste.trim() ? lireMontant(l.montant_conteste) : lireMontant(l.montant)))),
  );

  private somme(montants: Array<number | null>): string {
    const s = montants.reduce<number>((a, m) => a + (m ?? 0), 0);
    return montantFr(Math.round(s * 100) / 100);
  }

  montantInvalide(l: OperationSaisie): boolean {
    return lireMontant(l.montant) === null;
  }

  contesteInvalide(l: OperationSaisie): boolean {
    if (!l.montant_conteste.trim()) return false;
    const c = lireMontant(l.montant_conteste);
    const m = lireMontant(l.montant);
    return c === null || (m !== null && c > m);
  }

  racineValide(l: OperationSaisie): boolean {
    return /^\d{6}$/.test(l.client_racine.trim());
  }

  maj(i: number, champ: keyof OperationSaisie, e: Event): void {
    const valeur = (e.target as HTMLInputElement).value;
    this.lignes.update((ls) => ls.map((l, j) => (j === i ? { ...l, [champ]: valeur } : l)));
  }

  formater(i: number, champ: 'montant' | 'montant_conteste'): void {
    const n = lireMontant(this.lignes()[i][champ]);
    if (n === null) return;
    const texte = formatMontant(n);
    if (texte !== this.lignes()[i][champ]) {
      this.lignes.update((ls) => ls.map((l, j) => (j === i ? { ...l, [champ]: texte } : l)));
    }
  }

  ajouter(): void {
    const derniere = this.lignes().at(-1);
    // Saisie en série : client et compte de la ligne précédente repris.
    this.lignes.update((ls) => [...ls, { ...ligneVide(), client_racine: derniere?.client_racine ?? '', compte_reference: derniere?.compte_reference ?? '' }]);
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
