import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import {
  CompteDossier, DEVISE_REFERENCE, Dossier, Operation, Participant, StatutIdentification, TotalDevise, dateFr, montantFr, totauxParDevise,
} from '../reclamations.models';

export const STATUT_ID_LIBELLE: Record<StatutIdentification, string> = {
  VERIFIE: 'Vérifié', A_VERIFIER: 'À vérifier', A_RENSEIGNER: 'À renseigner',
};
export const STATUT_ID_TON: Record<StatutIdentification, string> = {
  VERIFIE: 'ACTIF', A_VERIFIER: 'ATTENTION', A_RENSEIGNER: 'SUSPENDU',
};

interface GroupeCompte {
  compte: CompteDossier | null;
  operations: Operation[];
  totaux: TotalDevise[];
}

interface GroupeClient {
  participant: Participant | null;
  comptes: GroupeCompte[];
  nb: number;
  totaux: TotalDevise[];
}

function somme(valeurs: Array<string | null>): string | null {
  const connus = valeurs.filter((v): v is string => v !== null);
  if (!connus.length) return null;
  return (Math.round(connus.reduce((a, v) => a + Number(v) * 100, 0)) / 100).toFixed(2);
}

/** Jamais de somme entre devises : un total par devise. */
function parDevise(ops: Operation[]): TotalDevise[] {
  const groupes = new Map<string, Operation[]>();
  for (const o of ops) groupes.set(o.devise, [...(groupes.get(o.devise) ?? []), o]);
  return [...groupes.entries()]
    .sort(([a], [b]) => (a === DEVISE_REFERENCE ? -1 : b === DEVISE_REFERENCE ? 1 : a.localeCompare(b)))
    .map(([devise, liste]) => ({
      devise, nb: liste.length,
      montant: somme(liste.map((o) => o.montant)),
      montant_conteste: somme(liste.map((o) => o.montant_conteste_effectif)),
    }));
}

/** Opérations du dossier groupées par client puis par compte, avec sous-totaux et statuts de vérification.
 * Clients associés masqués quand l'utilisateur n'est pas en charge du dossier. */
@Component({
  selector: 'bea-rc-operations-vue',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @let d = dossier();
    @if (d.nb_clients > 1) {
      <div class="bea-rc-note bea-rc-note--warn bea-rc-fiche__alerte">
        <mat-icon>groups</mat-icon>
        <span><strong>Regroupement de {{ d.nb_clients }} clients.</strong>
          @if (d.justification_regroupement) { Justification : {{ d.justification_regroupement }} }
          @if (d.clients_masques) { <br />L’identité des clients associés est masquée : vous n’êtes pas en charge de ce dossier. }
        </span>
      </div>
    }
    @for (g of groupes(); track g.participant?.id ?? 'aucun') {
      <div class="bea-rc-groupe">
        <div class="bea-rc-groupe__client">
          <mat-icon>{{ g.participant?.role === 'PRINCIPAL' ? 'person' : 'person_add' }}</mat-icon>
          <strong>{{ g.participant?.nom || (g.participant?.racine ? 'Client ' + g.participant?.racine : 'Client non renseigné') }}</strong>
          @if (g.participant?.racine) { <code>{{ g.participant?.racine }}</code> }
          @if (g.participant) {
            <span class="bea-ct-badge" data-tone="INFO">{{ g.participant.role_libelle }}</span>
            <span class="bea-ct-badge" [attr.data-tone]="ton(g.participant.statut)">{{ libelle(g.participant.statut) }}</span>
          }
          <span class="bea-rc-groupe__tot">
            {{ g.nb }} opération{{ g.nb > 1 ? 's' : '' }} · {{ tot(g.totaux) }}
            <br /><small>À extourner : {{ tot(g.totaux, 'montant_conteste') }}</small>
          </span>
        </div>
        @for (c of g.comptes; track c.compte?.id ?? 'sans-compte') {
          <div class="bea-rc-groupe__compte">
            <mat-icon>account_balance_wallet</mat-icon>
            @if (c.compte) {
              Compte <code>{{ c.compte.compte_reference }}</code>
              <span class="bea-ct-badge" [attr.data-tone]="ton(c.compte.statut)">{{ libelle(c.compte.statut) }}</span>
            } @else {
              <span>Compte non renseigné</span>
              <span class="bea-ct-badge" data-tone="SUSPENDU">À renseigner</span>
            }
            <span class="bea-rc-groupe__tot">{{ c.operations.length }} · {{ tot(c.totaux) }} <small>(à extourner {{ tot(c.totaux, 'montant_conteste') }})</small></span>
          </div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-rc-ops">
              <thead><tr>
                <th class="bea-rc-ops__n">N°</th><th>Référence</th><th class="bea-rc-ops__d">Date</th><th>D/C</th><th>Devise</th>
                <th class="bea-rc-ops__m">Montant initial</th><th class="bea-rc-ops__m">À extourner</th>
                @if (avecControles()) { <th class="bea-rc-ops__m">Montant attendu</th><th>Compte attendu</th><th>Rôle</th> }
                <th>Motif de la ligne</th><th>Commentaire</th>
              </tr></thead>
              <tbody>
                @for (o of c.operations; track o.id) {
                  <tr>
                    <td class="bea-rc-ops__n">{{ o.ordre }}</td>
                    <td>{{ o.reference }}
                      @if (o.ligne_import) { <small class="bea-rc-hint" title="Ligne du fichier importé"> · import l.{{ o.ligne_import }}</small> }
                    </td>
                    <td class="bea-rc-ops__d">{{ o.date_operation ? date(o.date_operation) : '—' }}</td>
                    <td>{{ o.nature_mouvement === 'DEBIT' ? 'D' : o.nature_mouvement === 'CREDIT' ? 'C' : '—' }}</td>
                    <td>{{ o.devise }}</td>
                    <td class="bea-rc-ops__m">{{ montant(o.montant, o.devise) }}</td>
                    <td class="bea-rc-ops__m">{{ montant(o.montant_conteste_effectif, o.devise) }}</td>
                    @if (avecControles()) {
                      <td class="bea-rc-ops__m">{{ o.montant_attendu !== null ? montant(o.montant_attendu, o.devise) : '' }}</td>
                      <td>{{ o.compte_attendu ?? '' }}</td>
                      <td>{{ o.role_operation === 'INITIALE' ? 'Initiale' : o.role_operation === 'DOUBLON' ? 'Doublon' : '' }}</td>
                    }
                    <td>{{ o.motif_detail ?? '' }}</td>
                    <td>{{ o.commentaire ?? '' }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </div>
    }
    <div class="bea-rc-groupe bea-rc-groupe__client">
      <strong>Total du dossier</strong>
      <span class="bea-rc-groupe__tot">
        {{ d.nb_operations }} opération{{ d.nb_operations > 1 ? 's' : '' }} · {{ tot(d.par_devise) }}
        <br /><small>À extourner : {{ tot(d.par_devise, 'montant_conteste') }}</small>
      </span>
    </div>
  `,
})
export class RcOperationsVueComponent {
  readonly dossier = input.required<Dossier>();

  readonly groupes = computed<GroupeClient[]>(() => {
    const d = this.dossier();
    const comptes = new Map(d.comptes.map((c) => [c.id, c]));
    const parClient = new Map<string | null, Map<string | null, Operation[]>>();
    for (const o of d.operations) {
      const p = parClient.get(o.participant_id) ?? new Map<string | null, Operation[]>();
      parClient.set(o.participant_id, p);
      p.set(o.compte_id, [...(p.get(o.compte_id) ?? []), o]);
    }
    const ordre = [...d.participants.map((p) => p.id as string | null), null];
    return ordre
      .filter((id) => parClient.has(id))
      .map((id) => {
        const p = d.participants.find((x) => x.id === id) ?? null;
        const parCompte = parClient.get(id)!;
        const groupes = [...parCompte.entries()]
          .sort(([a], [b]) => (a === null ? 1 : b === null ? -1 : (comptes.get(a)?.compte_reference ?? '').localeCompare(comptes.get(b)?.compte_reference ?? '')))
          .map(([cid, ops]) => ({
            compte: cid ? comptes.get(cid) ?? null : null,
            operations: ops,
            totaux: parDevise(ops),
          }));
        const toutes = groupes.flatMap((g) => g.operations);
        return { participant: p, comptes: groupes, nb: toutes.length, totaux: parDevise(toutes) };
      });
  });

  readonly avecControles = computed(() =>
    this.dossier().operations.some((o) => o.montant_attendu !== null || o.compte_attendu || o.role_operation));

  montant(v: string | null | undefined, devise = 'MRU'): string {
    return montantFr(v, devise);
  }

  tot(t: TotalDevise[] | null | undefined, champ: 'montant' | 'montant_conteste' = 'montant'): string {
    return totauxParDevise(t, champ);
  }

  date(iso: string): string {
    return dateFr(iso);
  }

  libelle(s: StatutIdentification): string {
    return STATUT_ID_LIBELLE[s] ?? s;
  }

  ton(s: StatutIdentification): string {
    return STATUT_ID_TON[s] ?? 'INFO';
  }
}
