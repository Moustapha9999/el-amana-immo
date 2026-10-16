import { ChangeDetectionStrategy, Component, computed, inject, input, model, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { formatMontant } from '../../shared/montant.pipe';
import { UiDialogService } from '../../shared/ui-dialog/ui-dialog.service';
import {
  ChampOperation,
  DEVISE_REFERENCE,
  LigneControlee,
  Operation,
  OperationSaisie,
  RegleEffective,
  Verification,
  lireMontant,
  operationVide,
  totauxParDevise,
} from '../reclamations.models';
import { ReclamationsService } from '../reclamations.service';

export function ligneVide(devise = DEVISE_REFERENCE): OperationSaisie {
  return operationVide(devise);
}

function montantTexte(v: string | null): string {
  return v !== null ? formatMontant(Number(v)) : '';
}

export function versSaisie(o: Operation): OperationSaisie {
  return {
    reference: o.reference ?? '',
    montant: montantTexte(o.montant),
    client_racine: o.client_racine ?? '',
    compte_reference: o.compte_reference ?? '',
    date_operation: o.date_operation ?? '',
    montant_conteste: montantTexte(o.montant_conteste),
    motif_detail: o.motif_detail ?? '',
    nature_mouvement: o.nature_mouvement ?? '',
    devise: o.devise ?? DEVISE_REFERENCE,
    montant_attendu: montantTexte(o.montant_attendu),
    compte_attendu: o.compte_attendu ?? '',
    role_operation: o.role_operation ?? '',
    commentaire: o.commentaire ?? '',
  };
}

function aujourdhui(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Montant attendu : zéro admis (opération qui n'aurait pas dû exister). */
function lireMontantOuZero(saisie: string): number | null {
  const t = saisie.trim().replace(/[\s\u00a0\u202f]/g, '');
  if (/^0+([.,]0{1,2})?$/.test(t)) return 0;
  return lireMontant(saisie);
}

const LIBELLES: Record<ChampOperation, string> = {
  client_racine: 'le client', compte_reference: 'le compte', reference: 'la référence', date_operation: 'la date',
  nature_mouvement: 'la nature (débit / crédit)', devise: 'la devise', montant: 'le montant initial',
  montant_conteste: 'le montant à extourner', montant_attendu: 'le montant attendu', compte_attendu: 'le compte attendu',
  role_operation: 'le rôle (initiale / en double)', motif_detail: 'le motif de la ligne',
};

/** Première erreur bloquante côté poste (confort de saisie : le backend refait tous les contrôles, règle
 * du motif comprise). Une même référence peut revenir dans un autre contexte : seule une ligne
 * strictement identique est refusée. */
export function operationsErreur(lignes: OperationSaisie[], regle?: RegleEffective | null): string | null {
  const requis = new Set<ChampOperation>(regle?.champs_requis ?? ['reference', 'montant']);
  const vues = new Map<string, number>();
  for (const [i, l] of lignes.entries()) {
    const n = i + 1;
    for (const champ of requis) {
      if (champ === 'client_racine') continue;
      if (!String(l[champ as keyof OperationSaisie] ?? '').trim()) return `Opération ${n} : ${LIBELLES[champ]} est obligatoire pour ce motif.`;
    }
    const montant = l.montant.trim() ? lireMontant(l.montant) : null;
    if (l.montant.trim() && montant === null) return `Opération ${n} : montant initial positif, deux décimales au plus.`;
    if (l.montant_conteste.trim()) {
      const conteste = lireMontant(l.montant_conteste);
      if (conteste === null) return `Opération ${n} : montant à extourner positif, deux décimales au plus.`;
      if (montant !== null && conteste > montant) return `Opération ${n} : le montant à extourner dépasse le montant initial.`;
    }
    if (l.montant_attendu.trim() && lireMontantOuZero(l.montant_attendu) === null) {
      return `Opération ${n} : montant attendu invalide.`;
    }
    if ((montant !== null || l.montant_conteste.trim()) && !l.devise) return `Opération ${n} : la devise est obligatoire.`;
    if (regle?.nature_attendue && l.nature_mouvement && l.nature_mouvement !== regle.nature_attendue) {
      return `Opération ${n} : le motif concerne une opération au ${regle.nature_attendue === 'DEBIT' ? 'débit' : 'crédit'}.`;
    }
    const racine = l.client_racine.trim();
    if (racine && !/^\d{6}$/.test(racine)) return `Opération ${n} : l’identifiant client comporte 6 chiffres.`;
    if (l.date_operation && l.date_operation > aujourdhui()) return `Opération ${n} : la date est dans le futur.`;
    const cle = [l.reference.trim().toLocaleLowerCase('fr'), l.compte_reference.trim().toLocaleLowerCase('fr'), racine,
      l.date_operation, montant ?? '', lireMontant(l.montant_conteste) ?? '', l.devise, l.nature_mouvement].join('|');
    const deja = vues.get(cle);
    if (deja && (l.reference.trim() || montant !== null)) return `Opération ${n} : identique à l’opération ${deja}.`;
    vues.set(cle, n);
  }
  return null;
}

export function operationsCorps(lignes: OperationSaisie[]): Array<Record<string, string | number | null>> {
  return lignes.map((l) => ({
    reference: l.reference.trim() || null,
    montant: l.montant.trim() ? lireMontant(l.montant) : null,
    montant_conteste: l.montant_conteste.trim() ? lireMontant(l.montant_conteste) : null,
    date_operation: l.date_operation || null,
    client_racine: l.client_racine.trim() || null,
    compte_reference: l.compte_reference.trim() || null,
    motif_detail: l.motif_detail.trim() || null,
    nature_mouvement: l.nature_mouvement || null,
    devise: l.devise || null,
    montant_attendu: l.montant_attendu.trim() ? lireMontantOuZero(l.montant_attendu) : null,
    compte_attendu: l.compte_attendu.trim() || null,
    role_operation: l.role_operation || null,
    commentaire: l.commentaire.trim() || null,
  }));
}

/** Clients distincts saisis (le client du dossier compris) : plus d'un = regroupement à justifier. */
export function clientsSaisis(lignes: OperationSaisie[], principal: string | null | undefined): number {
  const racines = new Set(lignes.map((l) => l.client_racine.trim()).filter((r) => r));
  if (principal) racines.add(principal);
  return racines.size;
}

type Colonne = { champ: ChampOperation; libelle: string; classe: string };
const OPTIONNELLES: ChampOperation[] = ['montant_attendu', 'compte_attendu', 'role_operation'];

/** Section « Opérations concernées » : une ligne par opération, colonnes et obligations selon la règle du motif. */
@Component({
  selector: 'bea-rc-operations',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (regle(); as r) {
      @if (r.consigne || r.controle_libelle) {
        <p class="bea-rc-hint"><mat-icon inline>rule</mat-icon> {{ r.consigne || r.controle_libelle }}
          @if (r.personnalisee && r.statut_validation !== 'VALIDEE') { <em>(règle proposée, en attente de validation)</em> }
        </p>
      }
    }
    @if (lignes().length) {
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table bea-rc-ops bea-rc-ops--large">
          <thead><tr>
            <th class="bea-rc-ops__n">N°</th>
            <th class="bea-rc-ops__c" title="Racine (6 chiffres). Vide : titulaire du compte, sinon client du dossier.">Client @if (req('client_racine')) {<em>*</em>}</th>
            <th class="bea-rc-ops__cpt">Compte @if (req('compte_reference')) {<em>*</em>}</th>
            <th>Référence @if (req('reference')) {<em>*</em>}</th>
            <th class="bea-rc-ops__d">Date @if (req('date_operation')) {<em>*</em>}</th>
            <th class="bea-rc-ops__nat">D/C @if (req('nature_mouvement')) {<em>*</em>}</th>
            <th class="bea-rc-ops__dev">Devise @if (req('devise')) {<em>*</em>}</th>
            <th class="bea-rc-ops__m">Montant initial @if (req('montant')) {<em>*</em>}</th>
            <th class="bea-rc-ops__m" title="Par défaut : le montant initial">À extourner @if (req('montant_conteste')) {<em>*</em>}</th>
            @for (c of colonnesOptionnelles(); track c.champ) {
              <th [class]="c.classe">{{ c.libelle }} @if (req(c.champ)) {<em>*</em>}</th>
            }
            <th>Motif de la ligne @if (req('motif_detail')) {<em>*</em>}</th>
            <th>Commentaire</th>
            <th class="bea-rc-ops__x"></th>
          </tr></thead>
          <tbody>
            @for (l of lignes(); track $index; let i = $index) {
              <tr [class.bea-rc-ops__ko]="statut(i) === 'ERREUR'">
                <td class="bea-rc-ops__n">{{ i + 1 }}</td>
                <td class="bea-rc-ops__c">
                  <input class="bea-rc-input" [value]="l.client_racine" (input)="maj(i, 'client_racine', $event)" maxlength="6" inputmode="numeric"
                         [attr.aria-label]="'Client de l’opération ' + (i + 1)" [placeholder]="principal() || 'Racine'"
                         [class.is-invalid]="ko(i, 'client_racine') || (!!l.client_racine.trim() && !racineValide(l))" [title]="msg(i, 'client_racine')" />
                </td>
                <td class="bea-rc-ops__cpt">
                  <input class="bea-rc-input" [value]="l.compte_reference" (input)="maj(i, 'compte_reference', $event)" maxlength="60"
                         [attr.aria-label]="'Compte de l’opération ' + (i + 1)" placeholder="N° de compte"
                         [class.is-invalid]="ko(i, 'compte_reference') || manque(l, 'compte_reference')" [title]="msg(i, 'compte_reference')" />
                </td>
                <td>
                  <input class="bea-rc-input" [value]="l.reference" (input)="maj(i, 'reference', $event)" maxlength="120"
                         [attr.aria-label]="'Référence de l’opération ' + (i + 1)"
                         [class.is-invalid]="ko(i, 'reference') || manque(l, 'reference')" [title]="msg(i, 'reference')" placeholder="N° de transaction, de virement…" />
                </td>
                <td class="bea-rc-ops__d">
                  <input class="bea-rc-input" type="date" [value]="l.date_operation" (input)="maj(i, 'date_operation', $event)" [max]="aujourdhui"
                         [attr.aria-label]="'Date de l’opération ' + (i + 1)"
                         [class.is-invalid]="ko(i, 'date_operation') || manque(l, 'date_operation')" [title]="msg(i, 'date_operation')" />
                </td>
                <td class="bea-rc-ops__nat">
                  <select class="bea-rc-input" [value]="l.nature_mouvement" (change)="maj(i, 'nature_mouvement', $event)"
                          [attr.aria-label]="'Nature de l’opération ' + (i + 1)"
                          [class.is-invalid]="ko(i, 'nature_mouvement') || manque(l, 'nature_mouvement')" [title]="msg(i, 'nature_mouvement')">
                    <option value="">—</option>
                    <option value="DEBIT">Débit</option>
                    <option value="CREDIT">Crédit</option>
                  </select>
                </td>
                <td class="bea-rc-ops__dev">
                  <select class="bea-rc-input" [value]="l.devise" (change)="maj(i, 'devise', $event)"
                          [attr.aria-label]="'Devise de l’opération ' + (i + 1)"
                          [class.is-invalid]="ko(i, 'devise') || manque(l, 'devise')" [title]="msg(i, 'devise')">
                    <option value="">—</option>
                    @for (d of devisesProposees(l); track d) { <option [value]="d">{{ d }}</option> }
                  </select>
                </td>
                <td class="bea-rc-ops__m">
                  <input class="bea-rc-input" [value]="l.montant" (input)="maj(i, 'montant', $event)" (blur)="formater(i, 'montant')" inputmode="decimal"
                         [attr.aria-label]="'Montant initial de l’opération ' + (i + 1)"
                         [class.is-invalid]="ko(i, 'montant') || manque(l, 'montant') || (l.montant !== '' && montantInvalide(l))" [title]="msg(i, 'montant')" placeholder="0,00" />
                </td>
                <td class="bea-rc-ops__m">
                  <input class="bea-rc-input" [value]="l.montant_conteste" (input)="maj(i, 'montant_conteste', $event)" (blur)="formater(i, 'montant_conteste')" inputmode="decimal"
                         [attr.aria-label]="'Montant à extourner de l’opération ' + (i + 1)"
                         [class.is-invalid]="ko(i, 'montant_conteste') || manque(l, 'montant_conteste') || contesteInvalide(l)" [title]="msg(i, 'montant_conteste')" placeholder="= montant" />
                </td>
                @for (c of colonnesOptionnelles(); track c.champ) {
                  <td [class]="c.classe">
                    @switch (c.champ) {
                      @case ('role_operation') {
                        <select class="bea-rc-input" [value]="l.role_operation" (change)="maj(i, 'role_operation', $event)"
                                [attr.aria-label]="'Rôle de l’opération ' + (i + 1)"
                                [class.is-invalid]="ko(i, 'role_operation') || manque(l, 'role_operation')" [title]="msg(i, 'role_operation')">
                          <option value="">—</option>
                          <option value="INITIALE">Initiale</option>
                          <option value="DOUBLON">En double</option>
                        </select>
                      }
                      @case ('montant_attendu') {
                        <input class="bea-rc-input" [value]="l.montant_attendu" (input)="maj(i, 'montant_attendu', $event)" (blur)="formater(i, 'montant_attendu')" inputmode="decimal"
                               [attr.aria-label]="'Montant attendu de l’opération ' + (i + 1)"
                               [class.is-invalid]="ko(i, 'montant_attendu') || manque(l, 'montant_attendu')" [title]="msg(i, 'montant_attendu')" placeholder="0,00" />
                      }
                      @default {
                        <input class="bea-rc-input" [value]="l.compte_attendu" (input)="maj(i, 'compte_attendu', $event)" maxlength="60"
                               [attr.aria-label]="'Compte attendu de l’opération ' + (i + 1)"
                               [class.is-invalid]="ko(i, 'compte_attendu') || manque(l, 'compte_attendu')" [title]="msg(i, 'compte_attendu')" placeholder="N° de compte" />
                      }
                    }
                  </td>
                }
                <td>
                  <input class="bea-rc-input" [value]="l.motif_detail" (input)="maj(i, 'motif_detail', $event)" maxlength="4000"
                         [attr.aria-label]="'Motif de la ligne ' + (i + 1)"
                         [class.is-invalid]="ko(i, 'motif_detail') || manque(l, 'motif_detail')" [title]="msg(i, 'motif_detail')"
                         [placeholder]="req('motif_detail') ? 'Obligatoire' : 'Facultatif'" />
                </td>
                <td>
                  <input class="bea-rc-input" [value]="l.commentaire" (input)="maj(i, 'commentaire', $event)" maxlength="4000"
                         [attr.aria-label]="'Commentaire de l’opération ' + (i + 1)" placeholder="Facultatif" />
                </td>
                <td class="bea-rc-ops__x">
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="dupliquer(i)" [attr.aria-label]="'Dupliquer l’opération ' + (i + 1)" title="Dupliquer">
                    <mat-icon>content_copy</mat-icon>
                  </button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="retirer(i)" [attr.aria-label]="'Retirer l’opération ' + (i + 1)" title="Retirer">
                    <mat-icon>delete</mat-icon>
                  </button>
                </td>
              </tr>
              @if (messages(i); as m) {
                <tr class="bea-rc-ops__msg">
                  <td></td>
                  <td [attr.colspan]="nbColonnes() - 1">
                    @for (e of m.erreurs; track $index) { <span class="bea-rc-ops__err"><mat-icon inline>error</mat-icon> {{ e }}</span> }
                    @for (a of m.avertissements; track $index) { <span class="bea-rc-ops__warn"><mat-icon inline>warning</mat-icon> {{ a }}</span> }
                  </td>
                </tr>
              }
            }
          </tbody>
          <tfoot>
            <tr>
              <td colspan="7"><strong>{{ lignes().length }} opération{{ lignes().length > 1 ? 's' : '' }}</strong></td>
              <td class="bea-rc-ops__m" colspan="2"><strong>{{ totaux() }}</strong></td>
              <td [attr.colspan]="nbColonnes() - 9"></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p class="bea-rc-hint">Client vide : titulaire du compte s’il est connu, sinon le client du dossier. Les montants de devises différentes ne sont jamais additionnés.</p>
    } @else {
      <p class="bea-rc-muted">Aucune opération rattachée. Ajoutez-en une si la réclamation porte sur une ou plusieurs transactions.</p>
    }
    <div class="bea-rc-ops__barre">
      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ajouter()"><mat-icon>add</mat-icon> Ajouter une opération</button>
      @if (lignes().length) {
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="verifier()" [disabled]="verification$()">
          <mat-icon>fact_check</mat-icon> {{ verification$() ? 'Vérification…' : 'Vérifier les opérations' }}
        </button>
        @if (verification() && perimee()) { <span class="bea-rc-muted">Saisie modifiée depuis la vérification.</span> }
      }
    </div>
    @if (verification(); as v) {
      <div class="bea-rc-recap" role="status">
        <strong>Récapitulatif</strong>
        <span>{{ v.recapitulatif.nb_operations }} opération(s) · {{ v.recapitulatif.nb_clients }} client(s) · {{ v.recapitulatif.nb_comptes }} compte(s)</span>
        <span>Montants : {{ parDevise(v) }}</span>
        @if (v.recapitulatif.nb_lignes_en_erreur) {
          <span class="bea-rc-ops__err">{{ v.recapitulatif.nb_lignes_en_erreur }} ligne(s) en erreur : corrigez-les avant d’enregistrer.</span>
        } @else {
          <span class="bea-rc-ops__ok"><mat-icon inline>check_circle</mat-icon> Aucune erreur bloquante.</span>
        }
        @if (v.recapitulatif.nb_avertissements) { <span class="bea-rc-ops__warn">{{ v.recapitulatif.nb_avertissements }} avertissement(s) (doublons potentiels, éléments à vérifier).</span> }
        @for (m of v.recapitulatif.a_completer_avant_transmission; track $index) {
          <span class="bea-rc-ops__warn">À compléter avant transmission : {{ m }}</span>
        }
      </div>
    }
  `,
  styles: [`
    .bea-rc-ops__nat { width: 6.5rem; }
    .bea-rc-ops__dev { width: 5.5rem; }
    .bea-rc-ops__x { white-space: nowrap; }
    .bea-rc-ops__ko > td { background: color-mix(in srgb, var(--bea-danger, #b42318) 6%, transparent); }
    .bea-rc-ops__msg td { padding-top: 0; font-size: .82rem; }
    .bea-rc-ops__err { color: var(--bea-danger, #b42318); margin-right: 1rem; display: inline-flex; gap: .25rem; align-items: center; }
    .bea-rc-ops__warn { color: var(--bea-warning-text, #8a5a00); margin-right: 1rem; display: inline-flex; gap: .25rem; align-items: center; }
    .bea-rc-ops__ok { color: var(--bea-success, #067647); display: inline-flex; gap: .25rem; align-items: center; }
    .bea-rc-ops__barre { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
    .bea-rc-recap { display: flex; flex-direction: column; gap: .25rem; margin-top: .75rem; padding: .75rem 1rem;
      border: 1px solid var(--bea-border, #d0d5dd); border-radius: 8px; font-size: .9rem; }
  `],
})
export class RcOperationsComponent {
  private readonly dialog = inject(UiDialogService);
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);

  readonly lignes = model.required<OperationSaisie[]>();
  readonly tente = input(false);
  /** Racine du client du dossier (indication). */
  readonly principal = input<string | null>(null);
  readonly regle = input<RegleEffective | null>(null);
  readonly devises = input<string[]>([DEVISE_REFERENCE]);
  /** Contexte de la vérification à blanc côté serveur. */
  readonly motifId = input<string | null>(null);
  readonly reclamationId = input<string | null>(null);
  readonly compteReference = input<string | null>(null);
  readonly verification = model<Verification | null>(null);
  readonly verification$ = signal(false);
  private readonly verifiees = signal<string | null>(null);
  readonly aujourdhui = aujourdhui();

  readonly requis = computed(() => new Set<string>(this.regle()?.champs_requis ?? ['reference', 'montant']));
  readonly colonnesOptionnelles = computed<Colonne[]>(() => {
    const libelles: Record<string, string> = { montant_attendu: 'Montant attendu', compte_attendu: 'Compte attendu', role_operation: 'Rôle' };
    return OPTIONNELLES.filter((c) => this.requis().has(c) || this.lignes().some((l) => !!String(l[c as keyof OperationSaisie]).trim()))
      .map((c) => ({ champ: c, libelle: libelles[c], classe: c === 'montant_attendu' ? 'bea-rc-ops__m' : c === 'role_operation' ? 'bea-rc-ops__nat' : 'bea-rc-ops__cpt' }));
  });
  readonly nbColonnes = computed(() => 13 + this.colonnesOptionnelles().length);
  readonly perimee = computed(() => this.verifiees() !== JSON.stringify(this.lignes()));

  private readonly controle = computed(() => {
    const v = this.verification();
    return v && !this.perimee() ? v.lignes : null;
  });

  readonly totaux = computed(() => {
    const groupes = new Map<string, number>();
    for (const l of this.lignes()) {
      const m = lireMontant(l.montant);
      if (m === null) continue;
      const d = l.devise || '—';
      groupes.set(d, (groupes.get(d) ?? 0) + m);
    }
    if (!groupes.size) return '—';
    return [...groupes.entries()]
      .sort(([a], [b]) => (a === DEVISE_REFERENCE ? -1 : b === DEVISE_REFERENCE ? 1 : a.localeCompare(b)))
      .map(([d, s]) => `${formatMontant(Math.round(s * 100) / 100)} ${d}`)
      .join(' · ');
  });

  req(champ: ChampOperation): boolean {
    return this.requis().has(champ);
  }

  devisesProposees(l: OperationSaisie): string[] {
    const liste = this.devises().length ? this.devises() : [DEVISE_REFERENCE];
    return l.devise && !liste.includes(l.devise) ? [...liste, l.devise] : liste;
  }

  /** Champ requis vide, signalé après une tentative d'enregistrement. */
  manque(l: OperationSaisie, champ: ChampOperation): boolean {
    return this.tente() && this.req(champ) && !String(l[champ as keyof OperationSaisie] ?? '').trim();
  }

  private ligneControlee(i: number): LigneControlee | undefined {
    return this.controle()?.find((x) => x.ligne === i + 1);
  }

  statut(i: number): string | null {
    return this.ligneControlee(i)?.statut ?? null;
  }

  ko(i: number, champ: string): boolean {
    return !!this.ligneControlee(i)?.erreurs_detail?.some((e) => e.champ === champ);
  }

  msg(i: number, champ: string): string {
    return (this.ligneControlee(i)?.erreurs_detail ?? []).filter((e) => e.champ === champ).map((e) => e.message).join(' ; ');
  }

  messages(i: number): { erreurs: string[]; avertissements: string[] } | null {
    const lg = this.ligneControlee(i);
    if (!lg || (!lg.erreurs.length && !lg.avertissements.length)) return null;
    return { erreurs: lg.erreurs, avertissements: lg.avertissements };
  }

  parDevise(v: Verification): string {
    return totauxParDevise(v.recapitulatif.par_devise);
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
    const valeur = (e.target as HTMLInputElement | HTMLSelectElement).value;
    this.lignes.update((ls) => ls.map((l, j) => (j === i ? { ...l, [champ]: valeur } : l)));
  }

  formater(i: number, champ: 'montant' | 'montant_conteste' | 'montant_attendu'): void {
    const n = champ === 'montant_attendu' ? lireMontantOuZero(this.lignes()[i][champ]) : lireMontant(this.lignes()[i][champ]);
    if (n === null) return;
    const texte = formatMontant(n);
    if (texte !== this.lignes()[i][champ]) {
      this.lignes.update((ls) => ls.map((l, j) => (j === i ? { ...l, [champ]: texte } : l)));
    }
  }

  ajouter(): void {
    const derniere = this.lignes().at(-1);
    // Saisie en série : client, compte et devise de la ligne précédente repris.
    this.lignes.update((ls) => [...ls, {
      ...ligneVide(derniere?.devise || DEVISE_REFERENCE),
      client_racine: derniere?.client_racine ?? '', compte_reference: derniere?.compte_reference ?? '',
    }]);
  }

  dupliquer(i: number): void {
    this.lignes.update((ls) => [...ls.slice(0, i + 1), { ...ls[i] }, ...ls.slice(i + 1)]);
    this.feedback.info('Ligne dupliquée : modifiez au moins un élément (référence, montant…) pour éviter un doublon.');
  }

  verifier(): void {
    const instantane = JSON.stringify(this.lignes());
    this.verification$.set(true);
    this.rc.verifierOperations({
      reclamation_id: this.reclamationId(), motif_id: this.motifId(),
      client_racine: this.reclamationId() ? null : this.principal(),
      compte_reference: this.reclamationId() ? null : this.compteReference(),
      operations: operationsCorps(this.lignes()),
    }).subscribe({
      next: (v) => {
        this.verification$.set(false);
        this.verifiees.set(instantane);
        this.verification.set(v);
      },
      error: (e) => {
        this.verification$.set(false);
        void describeApiErrorAsync(e).then((info) => this.feedback.apiError(info, 'Vérification impossible'));
      },
    });
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
