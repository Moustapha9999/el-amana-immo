import { Injectable, WritableSignal, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { CL_BASE } from './clientele.models';

export interface DeclarationRef { id: string; libelle: string; statut: string; }

/** Désactivation, réactivation et suppression d'une déclaration BCM (liste, aperçu, fiche). */
@Injectable({ providedIn: 'root' })
export class ClDeclarationCycleService {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);

  desactiver<T>(d: DeclarationRef, busy?: WritableSignal<boolean>): Observable<T> {
    return this.feedback.runWithReason(
      (motif) => this.api.post<T>(`${CL_BASE}/declarations/${d.id}/desactiver`, { motif }),
      {
        reason: {
          title: `Désactiver ${d.libelle}`,
          message: 'La déclaration est mise de côté : plus de calcul ni de contrôle tant qu’elle n’est pas réactivée.',
          hint: 'Le motif est conservé dans la fiche et dans l’audit.',
          reasonLabel: 'Motif de désactivation',
          maxLength: 2000,
          confirmLabel: 'Désactiver',
          tone: 'warn',
          icon: 'pause_circle',
        },
        busy,
        loading: 'Désactivation…',
        success: { title: 'Déclaration désactivée', details: [{ label: 'Période', value: d.libelle }] },
        errorTitle: 'Désactivation impossible',
      },
    );
  }

  reactiver<T>(d: DeclarationRef, busy?: WritableSignal<boolean>): Observable<T> {
    return this.feedback.run(() => this.api.post<T>(`${CL_BASE}/declarations/${d.id}/reactiver`, {}), {
      confirm: {
        title: `Réactiver ${d.libelle}`,
        message: 'La déclaration reprend son cycle (brouillon ou calculée). Un nouveau contrôle sera nécessaire.',
        confirmLabel: 'Réactiver',
        tone: 'primary',
        icon: 'play_circle',
      },
      busy,
      loading: 'Réactivation…',
      success: { title: 'Déclaration réactivée', details: [{ label: 'Période', value: d.libelle }] },
      errorTitle: 'Réactivation impossible',
    });
  }

  supprimer(d: DeclarationRef, busy?: WritableSignal<boolean>): Observable<void> {
    const url = `${CL_BASE}/declarations/${d.id}`;
    const commun = {
      busy,
      loading: 'Suppression…',
      success: { title: 'Déclaration supprimée', details: [{ label: 'Période', value: d.libelle }] },
      errorTitle: 'Suppression impossible',
    };
    if (d.statut === 'BROUILLON') {
      return this.feedback.run(() => this.api.delete<void>(url), {
        ...commun,
        confirm: {
          title: `Supprimer ${d.libelle}`,
          message: 'Supprimer définitivement ce brouillon ?',
          confirmLabel: 'Supprimer',
          tone: 'danger',
          icon: 'delete',
        },
      });
    }
    return this.feedback.runWithReason(
      (motif) => this.api.delete<void>(`${url}?motif=${encodeURIComponent(motif)}`),
      {
        ...commun,
        reason: {
          title: `Supprimer ${d.libelle}`,
          message: 'Les chiffres calculés et les contrôles de cette déclaration seront définitivement effacés.',
          hint: 'Irréversible. Le motif et un instantané sont conservés dans l’audit.',
          reasonLabel: 'Motif de suppression',
          maxLength: 2000,
          confirmLabel: 'Supprimer définitivement',
          tone: 'danger',
          icon: 'delete_forever',
        },
      },
    );
  }
}
