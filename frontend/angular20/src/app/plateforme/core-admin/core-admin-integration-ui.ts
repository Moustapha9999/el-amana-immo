import { ChangeDetectionStrategy, Component, Injectable, inject, input, output } from '@angular/core';
import { firstValueFrom, Observable } from 'rxjs';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { messageErreur } from './core-admin-integration-clients.models';
import { TRI_STYLES } from './core-admin-integrations.styles';

/** Réponse de `GET …/{id}/dependances` : ce qui empêche une suppression définitive (jamais de cascade). */
export interface BilanSuppression {
  supprimable: boolean;
  conditions: string[];
  dependances: { code: string; libelle: string; nombre: number }[];
  alternative: string;
  /** Révision vérifiée : la suppression est refusée si l'objet a changé depuis. */
  revision: number;
}

export type OrdreTri = 'asc' | 'desc';

/** États visuels d'un test (§ résultat) ; la couleur n'est jamais la seule indication : un libellé accompagne toujours l'état. */
export type EtatVisuel = 'attente' | 'en_cours' | 'succes' | 'http' | 'reseau' | 'refus' | 'secret' | 'quota' | 'delai';

export function etatExecution(statut: string): EtatVisuel {
  switch (statut) {
    case 'succes': return 'succes';
    case 'http_erreur': case 'trop_volumineux': case 'reponse_invalide': return 'http';
    case 'dns': case 'tls': return 'reseau';
    case 'timeout': return 'delai';
    case 'secret_requis': return 'secret';
    case 'quota': return 'quota';
    default: return 'refus';
  }
}

export const LIBELLES_ETAT: Record<EtatVisuel, string> = {
  attente: 'En attente de confirmation',
  en_cours: 'Exécution en cours',
  succes: 'Succès',
  http: 'Échec HTTP',
  reseau: 'Erreur réseau',
  refus: 'Destination ou appel refusé',
  secret: 'Secret requis',
  quota: 'Quota atteint',
  delai: 'Délai dépassé',
};

/** Squelette de chargement (le texte reste annoncé aux lecteurs d'écran). */
export function squelette(libelle: string): string {
  return `
    <div class="bea-admin-panel" role="status" aria-live="polite">
      <span class="bea-integ-muted">${libelle}</span>
      <div class="bea-integ-skeleton" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
    </div>`;
}

/** Nouveau couple (tri, ordre) après un clic sur une colonne : même colonne = inversion. */
export function basculerTri(actuel: { tri: string; ordre: OrdreTri }, colonne: string, ordreInitial: OrdreTri = 'asc') {
  if (actuel.tri === colonne) return { tri: colonne, ordre: (actuel.ordre === 'asc' ? 'desc' : 'asc') as OrdreTri };
  return { tri: colonne, ordre: ordreInitial };
}

export function ariaSort(actuel: { tri: string; ordre: OrdreTri }, colonne: string): 'ascending' | 'descending' | 'none' {
  if (actuel.tri !== colonne) return 'none';
  return actuel.ordre === 'asc' ? 'ascending' : 'descending';
}

/** Bouton d'en-tête de colonne triable (placer `[attr.aria-sort]` sur le `th`). */
@Component({
  selector: 'bea-integ-tri',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: [TRI_STYLES],
  template: `
    <button
      type="button"
      class="bea-integ-tri"
      [attr.data-actif]="actif()"
      [attr.data-ordre]="actif() ? ordre() : null"
      [attr.aria-label]="'Trier par ' + libelle()"
      (click)="trier.emit(colonne())"
    >
      {{ libelle() }}<span class="bea-integ-tri__fleche" aria-hidden="true">▼</span>
    </button>
  `,
})
export class IntegrationTriComponent {
  readonly colonne = input.required<string>();
  readonly libelle = input.required<string>();
  readonly tri = input.required<string>();
  readonly ordre = input<OrdreTri>('desc');
  readonly trier = output<string>();
  actif(): boolean {
    return this.tri() === this.colonne();
  }
}

export interface OptionsSuppression {
  /** Type affiché, ex. « l'application », « le fournisseur ». */
  objet: string;
  nom: string;
  dependances: () => Observable<BilanSuppression>;
  supprimer: (revision: number) => Observable<unknown>;
}

/**
 * Suppression définitive en trois temps : bilan des dépendances (serveur), confirmation explicite,
 * appel DELETE. Rien n'est retiré de l'écran avant la réponse du serveur ; en cas de blocage,
 * l'alternative (archivage, suspension) est proposée, jamais une cascade.
 */
@Injectable({ providedIn: 'root' })
export class IntegrationSuppressionService {
  private readonly dialogs = inject(BeaAdminDialogService);

  async supprimer(o: OptionsSuppression): Promise<boolean> {
    let bilan: BilanSuppression;
    try {
      bilan = await firstValueFrom(o.dependances());
    } catch (err) {
      await this.dialogs.error(messageErreur(err, 'Impossible de vérifier les dépendances.'));
      return false;
    }
    if (!bilan.supprimable) {
      await this.dialogs.feedback({
        title: 'Suppression impossible',
        message: messageBlocage(o, bilan),
        tone: 'warn',
        okLabel: 'Compris',
      });
      return false;
    }
    const ok = await this.dialogs.confirm({
      title: 'Supprimer définitivement ?',
      message:
        `Supprimer ${o.objet} « ${o.nom} » ? Cette action est irréversible.\n` +
        'Aucun objet lié n’existe. La suppression reste tracée dans le journal d’audit.',
      tone: 'danger',
      confirmLabel: 'Supprimer définitivement',
    });
    if (!ok) return false;
    try {
      await firstValueFrom(o.supprimer(bilan.revision), { defaultValue: null });
    } catch (err) {
      await this.dialogs.error(messageErreur(err, 'Suppression impossible.'), 'Suppression refusée');
      return false;
    }
    await this.dialogs.success(`« ${o.nom} » a été supprimé définitivement.`, 'Suppression effectuée');
    return true;
  }
}

export function messageBlocage(o: Pick<OptionsSuppression, 'objet' | 'nom'>, bilan: BilanSuppression): string {
  const lignes = [`${capitaliser(o.objet)} « ${o.nom} » ne peut pas être supprimé :`];
  for (const c of bilan.conditions) lignes.push(`• ${capitaliser(c)}`);
  for (const d of bilan.dependances) lignes.push(`• ${d.libelle} : ${d.nombre}`);
  lignes.push('', `Alternative : ${bilan.alternative}`);
  return lignes.join('\n');
}

function capitaliser(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}
