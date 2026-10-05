import { Injectable, WritableSignal, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { Contrat, PREFIXE_REPORT, dateFr, telechargerBlob, typeEcheanceLabel } from './contrats.models';

export interface EcheanceRef {
  id: string;
  type_echeance: string;
  date_prevue: string;
  reference: string;
  commentaire: string | null;
}

/** Opérations contrats partagées par la liste et les mini-pages (confirmations + retours standard). */
@Injectable({ providedIn: 'root' })
export class ContratsActionsService {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);

  reconduire(c: { id: string; reference: string; titre: string }, busy: WritableSignal<boolean>): Observable<Contrat> {
    return this.feedback.run(() => this.api.post<Contrat>(`/mg/contrats/${c.id}/reconduire`, {}), {
      confirm: {
        action: 'renouvellement',
        title: 'Reconduction tacite',
        message: `Reconduire ${c.reference} « ${c.titre} » pour une période identique ?`,
        hint: 'Le même contrat est prolongé ; un avenant de reconduction est tracé et l’échéancier complété.',
      },
      loading: 'Reconduction…',
      busy,
      idempotent: true,
      errorTitle: 'Échec de la reconduction',
      success: (r) => ({ title: 'Contrat reconduit', details: [{ label: 'Contrat', value: r.reference }, { label: 'Nouvelle fin', value: dateFr(r.date_fin) }] }),
    });
  }

  renouveler(c: { id: string; reference: string }, busy: WritableSignal<boolean>): Observable<Contrat> {
    return this.feedback.run(() => this.api.post<Contrat>(`/mg/contrats/${c.id}/renouveler`, {}), {
      confirm: {
        action: 'renouvellement',
        title: 'Reconduction expresse',
        message: `Préparer un nouveau contrat à partir de ${c.reference} ?`,
        hint: 'Un nouveau contrat en brouillon est créé pour la période suivante ; il suivra le circuit de validation.',
      },
      loading: 'Préparation…',
      busy,
      idempotent: true,
      errorTitle: 'Échec du renouvellement',
      success: (n) => ({ title: 'Renouvellement préparé', details: [{ label: 'Nouvelle référence', value: n.reference }, { label: 'Issu de', value: c.reference }] }),
    });
  }

  reporterEcheance(e: EcheanceRef, nouvelleDate: string, motif: string, busy: WritableSignal<boolean>): Observable<unknown> {
    const trace = `${PREFIXE_REPORT} du ${dateFr(e.date_prevue)} au ${dateFr(nouvelleDate)}${motif ? ' — ' + motif : ''}`;
    return this.feedback.run(
      () => this.api.patch(`/mg/contrats/echeances/${e.id}`, { date_prevue: nouvelleDate, commentaire: trace }),
      {
        loading: 'Report de l’échéance…',
        busy,
        errorTitle: 'Report impossible',
        errorHint: 'La saisie a été conservée.',
        success: { title: 'Échéance reportée', details: [{ label: 'Contrat', value: e.reference }, { label: 'Nouvelle date', value: dateFr(nouvelleDate) }] },
      },
    );
  }

  annulerEcheance(e: EcheanceRef, busy: WritableSignal<boolean>): Observable<unknown> {
    return this.feedback.runWithReason(
      (motif) => this.api.patch(`/mg/contrats/echeances/${e.id}`, { date_prevue: e.date_prevue, statut: 'ANNULEE', commentaire: `Annulée — ${motif}` }),
      {
        reason: {
          title: 'Annuler l’échéance',
          message: `${typeEcheanceLabel(e.type_echeance)} du ${dateFr(e.date_prevue)} — ${e.reference}`,
          reasonLabel: 'Motif d’annulation',
          required: true,
          tone: 'danger',
          confirmLabel: 'Annuler l’échéance',
        },
        loading: 'Annulation…',
        busy,
        errorTitle: 'Annulation impossible',
        success: { title: 'Échéance annulée', details: [{ label: 'Contrat', value: e.reference }] },
      },
    );
  }

  retablirEcheance(e: EcheanceRef, busy: WritableSignal<boolean>): Observable<unknown> {
    return this.feedback.run(
      () => this.api.patch(`/mg/contrats/echeances/${e.id}`, { date_prevue: e.date_prevue, statut: 'A_VENIR', commentaire: e.commentaire }),
      {
        confirm: { action: 'restauration', message: `Rétablir l’échéance du ${dateFr(e.date_prevue)} (${e.reference}) ?` },
        loading: 'Rétablissement…',
        busy,
        errorTitle: 'Rétablissement impossible',
        success: { title: 'Échéance rétablie' },
      },
    );
  }

  supprimerEcheance(e: EcheanceRef, busy: WritableSignal<boolean>): Observable<unknown> {
    return this.feedback.run(() => this.api.delete(`/mg/contrats/echeances/${e.id}`), {
      confirm: {
        action: 'suppression',
        message: `Supprimer l’échéance « ${typeEcheanceLabel(e.type_echeance)} » du ${dateFr(e.date_prevue)} (${e.reference}) ?`,
        hint: 'Refusé si des paiements y sont rattachés ; l’opération est tracée.',
      },
      loading: 'Suppression…',
      busy,
      errorTitle: 'Suppression impossible',
      success: { title: 'Échéance supprimée' },
    });
  }

  supprimerPaiement(p: { id: string; paiement_ref: string | null; reference: string }, busy: WritableSignal<boolean>): Observable<unknown> {
    return this.feedback.run(() => this.api.delete(`/mg/contrats/paiements/${p.id}`), {
      confirm: {
        action: 'suppression',
        message: `Supprimer le paiement ${p.paiement_ref || 'sans référence'} du contrat ${p.reference} ?`,
        hint: 'L’échéance rattachée repasse en « à payer » ; l’opération est tracée.',
      },
      loading: 'Suppression…',
      busy,
      errorTitle: 'Échec de la suppression',
      success: { title: 'Paiement supprimé' },
    });
  }

  pdf(c: { id: string; reference: string }, busy: WritableSignal<boolean>): void {
    const nom = `Contrat-${c.reference}.pdf`;
    this.feedback
      .run(() => this.api.download(`/mg/contrats/${c.id}/pdf`), {
        loading: 'Préparation du PDF…',
        busy,
        errorTitle: 'Téléchargement impossible',
        success: (blob) => {
          telechargerBlob(blob, nom);
          return { title: 'Téléchargement prêt', details: [{ label: 'Fichier', value: nom }] };
        },
      })
      .subscribe();
  }

  /** Export PDF / Excel d'une liste, avec exactement les filtres affichés. */
  exporter(rapport: string, fmt: 'pdf' | 'xlsx', filtres: Record<string, string>, busy: WritableSignal<boolean>): void {
    const nom = `contrats-${rapport}-${new Date().toISOString().slice(0, 10)}.${fmt}`;
    const params: Record<string, string> = { fmt };
    for (const [k, v] of Object.entries(filtres)) if (v) params[k] = v;
    this.feedback
      .run(() => this.api.download(`/mg/contrats/rapports/${rapport}`, params), {
        loading: 'Génération de l’export…',
        busy,
        errorTitle: 'Export impossible',
        success: (blob) => {
          telechargerBlob(blob, nom);
          return { title: 'Export prêt', details: [{ label: 'Fichier', value: nom }] };
        },
      })
      .subscribe();
  }
}
