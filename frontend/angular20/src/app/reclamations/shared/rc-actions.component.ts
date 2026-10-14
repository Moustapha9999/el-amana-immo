import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { Dossier } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

interface DefAction {
  code: string;
  libelle: string;
  icone: string;
  verbe: string;
  primaire?: boolean;
  danger?: boolean;
  /** Motif saisi : obligatoire (true), facultatif (false), absent (undefined). */
  motif?: boolean;
}

interface Champs {
  unite_id: string;
  instructions: string;
  analyse: string;
  actions_menees: string;
  conclusion: string;
  decision_proposee: string;
  evaluation: string;
  resultat: string;
  motif_resolution: string;
  motif: string;
}

const BOUTONS: DefAction[] = [
  { code: 'affecter', libelle: 'Transmettre au service', icone: 'send', verbe: 'affecter', primaire: true, motif: false },
  { code: 'traiter_interne', libelle: 'Traiter au SR', icone: 'home_repair_service', verbe: 'traiter-interne', motif: true },
  { code: 'retourner', libelle: 'Retourner au SR', icone: 'assignment_return', verbe: 'retourner', primaire: true },
  { code: 'evaluer', libelle: 'Examiner le retour', icone: 'fact_check', verbe: 'evaluer', primaire: true, motif: false },
  { code: 'cloturer', libelle: 'Clôturer', icone: 'task_alt', verbe: 'cloturer', primaire: true },
  { code: 'refuser', libelle: 'Rejeter', icone: 'block', verbe: 'refuser', danger: true, motif: true },
  { code: 'annuler', libelle: 'Annuler / doublon', icone: 'content_copy', verbe: 'annuler', danger: true, motif: true },
  { code: 'rouvrir', libelle: 'Rouvrir', icone: 'lock_open', verbe: 'rouvrir', motif: true },
  { code: 'archiver', libelle: 'Archiver', icone: 'inventory_2', verbe: 'archiver', motif: false },
];

const PLACEHOLDERS: Record<string, string> = {
  traiter_interne: 'Analyse du SR : pourquoi le dossier est traité sans affectation',
  refuser: 'Motif du rejet (irrecevable, hors périmètre…)',
  annuler: 'Saisie en double, erreur de saisie…',
  rouvrir: 'Élément nouveau justifiant la réouverture',
};

/** Actions du circuit (Réception → Affectation → Traitement → Clôture) : formulaire motivé, puis appel backend. */
@Component({
  selector: 'bea-rc-actions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  template: `
    <div class="bea-mg__actions bea-rc-actions">
      @for (b of visibles(); track b.code) {
        <button type="button" class="bea-mg__btn" [class.bea-mg__btn--primary]="b.primaire" [class.bea-mg__btn--ghost]="!b.primaire && !b.danger"
                [disabled]="busy()" (click)="ouvrir(b)">
          <mat-icon>{{ b.icone }}</mat-icon> {{ b.libelle }}
        </button>
      }
    </div>
    @if (dossier().statut === 'A_CLOTURER' && !dossier().actions['cloturer']) {
      <div class="bea-rc-note"><mat-icon>info</mat-icon><span>La clôture est réservée au Service Réclamations central.</span></div>
    }
    @if (enCours(); as a) {
      <div class="bea-mg__backdrop" (click)="fermer()"></div>
      <form class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" (ngSubmit)="confirmer()">
        <div class="bea-mg__modal-head">
          <h2>{{ a.libelle }} — {{ dossier().reference }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
        </div>
        <div class="bea-rc-form">
          @if (a.code === 'affecter' || (a.code === 'evaluer' && f.evaluation === 'INSUFFISANT')) {
            <label>Service destinataire <em>*</em>
              <select [(ngModel)]="f.unite_id" name="unite_id"><option value="">—</option>
                @for (u of store.unitesActives(); track u.id) {
                  @if (!u.est_service_reclamations) { <option [value]="u.id">{{ u.libelle }}</option> }
                }
              </select>
            </label>
            <label>Instructions <textarea [(ngModel)]="f.instructions" name="instructions" rows="3" maxlength="8000"></textarea></label>
          }
          @if (a.code === 'retourner') {
            <label>Analyse <em>*</em><textarea [(ngModel)]="f.analyse" name="analyse" rows="4" maxlength="20000"></textarea></label>
            <label>Actions menées <textarea [(ngModel)]="f.actions_menees" name="actions_menees" rows="2" maxlength="20000"></textarea></label>
            <label>Conclusion <em>*</em><textarea [(ngModel)]="f.conclusion" name="conclusion" rows="3" maxlength="8000"></textarea></label>
            <label>Décision proposée
              <select [(ngModel)]="f.decision_proposee" name="decision_proposee"><option value="">—</option>
                @for (r of store.libelles('resultats'); track r.code) { <option [value]="r.code">{{ r.libelle }}</option> }
              </select>
            </label>
          }
          @if (a.code === 'evaluer') {
            <label>Évaluation <em>*</em>
              <select [(ngModel)]="f.evaluation" name="evaluation">
                @for (e of store.libelles('evaluations'); track e.code) { <option [value]="e.code">{{ e.libelle }}</option> }
              </select>
            </label>
          }
          @if (a.code === 'cloturer') {
            <label>Résultat <em>*</em>
              <select [(ngModel)]="f.resultat" name="resultat"><option value="">—</option>
                @for (r of store.libelles('resultats'); track r.code) { <option [value]="r.code">{{ r.libelle }}</option> }
              </select>
            </label>
            <label>Motif de résolution <textarea [(ngModel)]="f.motif_resolution" name="motif_resolution" rows="2" maxlength="4000"></textarea></label>
          }
          @if (a.motif !== undefined) {
            <label>{{ a.code === 'evaluer' ? 'Commentaire' : 'Motif' }} @if (motifObligatoire(a)) { <em>*</em> }
              <textarea [(ngModel)]="f.motif" name="motif" rows="2" maxlength="4000" [placeholder]="placeholder(a)"></textarea>
            </label>
          }
        </div>
        <div class="bea-mg__modal-foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Confirmer</button>
        </div>
      </form>
    }
  `,
})
export class RcActionsComponent {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);

  readonly dossier = input.required<Dossier>();
  readonly modifie = output<Dossier>();
  readonly busy = signal(false);
  readonly tente = signal(false);
  readonly enCours = signal<DefAction | null>(null);
  f: Champs = this.vierge();

  private vierge(d?: Dossier): Champs {
    return {
      unite_id: d?.unite_concernee_ref?.actif ? d.unite_concernee_ref.id : (d?.unite_traitement_ref?.id ?? ''),
      instructions: '', analyse: '', actions_menees: '', conclusion: '', decision_proposee: '', evaluation: 'SUFFISANT',
      resultat: d?.affectation_courante?.decision_proposee ?? '', motif_resolution: '', motif: '',
    };
  }

  visibles(): DefAction[] {
    const a = this.dossier().actions ?? {};
    return BOUTONS.filter((b) => a[b.code]);
  }

  placeholder(a: DefAction): string {
    if (a.code === 'evaluer') return retourInsuffisant(this.f) ? 'Obligatoire : ce qui manque au retour du service' : '';
    return PLACEHOLDERS[a.code] ?? '';
  }

  ouvrir(b: DefAction): void {
    const d = this.dossier();
    this.f = this.vierge(d);
    this.tente.set(false);
    this.enCours.set(b);
  }

  fermer(): void {
    this.enCours.set(null);
  }

  motifObligatoire(a: DefAction): boolean {
    return a.motif === true || (a.code === 'evaluer' && retourInsuffisant(this.f));
  }

  private avertir(title: string, message: string): void {
    this.feedback.warning({ title, message });
  }

  confirmer(): void {
    const a = this.enCours();
    const d = this.dossier();
    if (!a) return;
    this.tente.set(true);
    if (this.motifObligatoire(a) && !this.f.motif.trim()) {
      this.avertir('Motif obligatoire', a.code === 'evaluer' ? 'Expliquez pourquoi le retour est insuffisant.' : 'Indiquez le motif de cette action.');
      return;
    }
    const corps: Record<string, unknown> = { revision: d.revision, motif: this.f.motif.trim() || null };
    switch (a.code) {
      case 'affecter':
      case 'evaluer':
        if (a.code === 'affecter' && !this.f.unite_id) return this.avertir('Service obligatoire', 'Choisissez le service destinataire.');
        if (a.code === 'evaluer') {
          corps['evaluation'] = this.f.evaluation;
          corps['commentaire'] = this.f.motif.trim() || null;
          if (this.f.evaluation !== 'INSUFFISANT') break;
          if (!this.f.unite_id) return this.avertir('Service obligatoire', 'Choisissez le service qui reprend le traitement.');
        }
        corps['unite_id'] = this.f.unite_id;
        corps['instructions'] = this.f.instructions.trim() || null;
        break;
      case 'retourner':
        if (!this.f.analyse.trim() || !this.f.conclusion.trim()) return this.avertir('Retour incomplet', 'Analyse et conclusion sont obligatoires.');
        Object.assign(corps, {
          analyse: this.f.analyse.trim(), actions_menees: this.f.actions_menees.trim() || null,
          conclusion: this.f.conclusion.trim(), decision_proposee: this.f.decision_proposee || null,
        });
        break;
      case 'cloturer':
        if (!this.f.resultat) return this.avertir('Résultat obligatoire', 'Choisissez le résultat de la réclamation.');
        corps['resultat'] = this.f.resultat;
        corps['motif_resolution'] = this.f.motif_resolution.trim() || null;
        break;
    }

    this.feedback
      .run(() => this.rc.action(d.id, a.verbe, corps), {
        busy: this.busy,
        loading: 'Enregistrement…',
        success: (r) => ({ title: a.libelle, details: [{ label: 'Référence', value: r.reference }, { label: 'Statut', value: r.statut_libelle }] }),
        errorTitle: 'Action refusée',
        errorHint: 'Vos saisies ont été conservées.',
        retry: false,
      })
      .subscribe((r) => {
        this.enCours.set(null);
        this.modifie.emit(r);
      });
  }
}

function retourInsuffisant(f: Champs): boolean {
  return f.evaluation === 'INSUFFISANT';
}
