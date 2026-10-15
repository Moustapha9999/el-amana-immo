import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { CompteDossier, Dossier, Operation, Participant, StatutIdentification, dateFr, montantFr } from '../reclamations.models';

export const STATUT_ID_LIBELLE: Record<StatutIdentification, string> = {
  VERIFIE: 'Vérifié', A_VERIFIER: 'À vérifier', A_RENSEIGNER: 'À renseigner',
};
export const STATUT_ID_TON: Record<StatutIdentification, string> = {
  VERIFIE: 'ACTIF', A_VERIFIER: 'ATTENTION', A_RENSEIGNER: 'SUSPENDU',
};

interface GroupeCompte {
  compte: CompteDossier | null;
  operations: Operation[];
  montant: string | null;
  conteste: string | null;
}

interface GroupeClient {
  participant: Participant | null;
  comptes: GroupeCompte[];
  nb: number;
}

function somme(valeurs: Array<string | null>): string | null {
  const connus = valeurs.filter((v): v is string => v !== null);
  if (!connus.length) return null;
  return (Math.round(connus.reduce((a, v) => a + Number(v) * 100, 0)) / 100).toFixed(2);
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
            {{ g.nb }} opération{{ g.nb > 1 ? 's' : '' }} · {{ montant(g.participant?.montant_total ?? null) }}
            <br /><small>Contesté : {{ montant(g.participant?.montant_conteste_total ?? null) }}</small>
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
            <span class="bea-rc-groupe__tot">{{ c.operations.length }} · {{ montant(c.montant) }} <small>(contesté {{ montant(c.conteste) }})</small></span>
          </div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-rc-ops">
              <thead><tr>
                <th class="bea-rc-ops__n">N°</th><th>Référence</th><th class="bea-rc-ops__d">Date</th>
                <th class="bea-rc-ops__m">Montant</th><th class="bea-rc-ops__m">Contesté</th><th>Motif détaillé</th>
              </tr></thead>
              <tbody>
                @for (o of c.operations; track o.id) {
                  <tr>
                    <td class="bea-rc-ops__n">{{ o.ordre }}</td>
                    <td>{{ o.reference }}
                      @if (o.ligne_import) { <small class="bea-rc-hint" title="Ligne du fichier importé"> · import l.{{ o.ligne_import }}</small> }
                    </td>
                    <td class="bea-rc-ops__d">{{ o.date_operation ? date(o.date_operation) : '—' }}</td>
                    <td class="bea-rc-ops__m">{{ montant(o.montant, o.devise) }}</td>
                    <td class="bea-rc-ops__m">{{ montant(o.montant_conteste_effectif, o.devise) }}</td>
                    <td>{{ o.motif_detail ?? '' }}</td>
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
        {{ d.nb_operations }} opération{{ d.nb_operations > 1 ? 's' : '' }} · {{ montant(d.montant_total, d.devise) }}
        <br /><small>Contesté : {{ montant(d.montant_conteste_total, d.devise) }}</small>
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
            montant: somme(ops.map((o) => o.montant)),
            conteste: somme(ops.map((o) => o.montant_conteste_effectif)),
          }));
        return { participant: p, comptes: groupes, nb: groupes.reduce((a, g) => a + g.operations.length, 0) };
      });
  });

  montant(v: string | null | undefined, devise = 'MRU'): string {
    return montantFr(v, devise);
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
