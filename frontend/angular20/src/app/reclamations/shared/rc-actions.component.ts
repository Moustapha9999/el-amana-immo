import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { Dossier } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { maintenantLocal, depuisSaisieLocale } from '../reclamations.models';

interface DefAction {
  code: string;
  libelle: string;
  icone: string;
  verbe: string;
  reponse?: boolean;
  primaire?: boolean;
  danger?: boolean;
}

interface Champs {
  type_id: string;
  motif_id: string;
  priorite: string;
  unite_id: string;
  instructions: string;
  analyse: string;
  actions_menees: string;
  conclusion: string;
  decision_proposee: string;
  evaluation: string;
  canal_envoi_id: string;
  destinataire: string;
  envoye_le: string;
  reference_envoi: string;
  resultat: string;
  motif_resolution: string;
  conditions_reprise: string;
  motif: string;
}

const BOUTONS: DefAction[] = [
  { code: 'recevoir_sr', libelle: 'Réception SR', icone: 'move_to_inbox', verbe: 'recevoir-sr', primaire: true },
  { code: 'qualifier', libelle: 'Qualifier', icone: 'rule', verbe: 'qualifier', primaire: true },
  { code: 'affecter', libelle: 'Transmettre au service', icone: 'send', verbe: 'affecter', primaire: true },
  { code: 'traiter_interne', libelle: 'Traiter au SR', icone: 'home_repair_service', verbe: 'traiter-interne' },
  { code: 'prendre', libelle: 'Prendre en charge', icone: 'play_arrow', verbe: 'prendre', primaire: true },
  { code: 'retourner', libelle: 'Retourner au SR', icone: 'assignment_return', verbe: 'retourner', primaire: true },
  { code: 'evaluer', libelle: 'Examiner le retour', icone: 'fact_check', verbe: 'evaluer', primaire: true },
  { code: 'demander_info', libelle: 'Demander une info', icone: 'help', verbe: 'demander-info' },
  { code: 'reprendre', libelle: 'Reprendre', icone: 'replay', verbe: 'reprendre' },
  { code: 'suspendre', libelle: 'Suspendre', icone: 'pause', verbe: 'suspendre' },
  { code: 'refuser', libelle: 'Refuser', icone: 'block', verbe: 'refuser', danger: true },
  { code: 'annuler', libelle: 'Annuler / doublon', icone: 'content_copy', verbe: 'annuler', danger: true },
  { code: 'soumettre_reponse', libelle: 'Soumettre la réponse', icone: 'forward_to_inbox', verbe: 'soumettre', reponse: true, primaire: true },
  { code: 'valider_reponse', libelle: 'Valider la réponse', icone: 'verified', verbe: 'valider', reponse: true, primaire: true },
  { code: 'renvoyer_reponse', libelle: 'Renvoyer le brouillon', icone: 'undo', verbe: 'renvoyer', reponse: true, danger: true },
  { code: 'envoyer_reponse', libelle: 'Envoyer au client', icone: 'outgoing_mail', verbe: 'envoyer', reponse: true, primaire: true },
  { code: 'cloturer', libelle: 'Clôturer', icone: 'task_alt', verbe: 'cloturer', primaire: true },
  { code: 'rouvrir', libelle: 'Rouvrir', icone: 'lock_open', verbe: 'rouvrir' },
  { code: 'archiver', libelle: 'Archiver', icone: 'inventory_2', verbe: 'archiver' },
];

/** Actions du circuit : chaque bouton ouvre un formulaire motivé, puis appelle le backend. */
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
    @if (enCours(); as a) {
      <div class="bea-mg__backdrop" (click)="fermer()"></div>
      <form class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" (ngSubmit)="confirmer()">
        <div class="bea-mg__modal-head">
          <h2>{{ a.libelle }} — {{ dossier().reference }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
        </div>
        <div class="bea-rc-form">
          @if (a.code === 'qualifier') {
            <div class="bea-rc-row">
              <label>Type <em>*</em>
                <select [(ngModel)]="f.type_id" name="type_id"><option value="">—</option>
                  @for (t of store.refs('TYPE'); track t.id) { <option [value]="t.id">{{ t.libelle }}</option> }
                </select>
              </label>
              <label>Motif
                <select [(ngModel)]="f.motif_id" name="motif_id"><option value="">—</option>
                  @for (m of store.enfants('MOTIF', f.type_id); track m.id) { <option [value]="m.id">{{ m.libelle }}</option> }
                </select>
              </label>
              <label>Priorité
                <select [(ngModel)]="f.priorite" name="priorite">
                  @for (p of store.libelles('priorites'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
                </select>
              </label>
            </div>
          }
          @if (a.code === 'affecter' || (a.code === 'evaluer' && f.evaluation === 'INSUFFISANT')) {
            <label>Service destinataire <em>*</em>
              <select [(ngModel)]="f.unite_id" name="unite_id"><option value="">—</option>
                @for (u of store.unitesActives(); track u.id) {
                  @if (!u.est_service_reclamations) { <option [value]="u.id">{{ u.libelle }}</option> }
                }
              </select>
            </label>
            <label>Instructions <textarea [(ngModel)]="f.instructions" name="instructions" rows="3"></textarea></label>
          }
          @if (a.code === 'retourner') {
            <label>Analyse <em>*</em><textarea [(ngModel)]="f.analyse" name="analyse" rows="4"></textarea></label>
            <label>Actions menées <textarea [(ngModel)]="f.actions_menees" name="actions_menees" rows="2"></textarea></label>
            <label>Conclusion <em>*</em><textarea [(ngModel)]="f.conclusion" name="conclusion" rows="3"></textarea></label>
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
          @if (a.code === 'envoyer_reponse') {
            <div class="bea-rc-row">
              <label>Canal d'envoi <em>*</em>
                <select [(ngModel)]="f.canal_envoi_id" name="canal_envoi_id"><option value="">—</option>
                  @for (c of store.refs('CANAL_REPONSE'); track c.id) { <option [value]="c.id">{{ c.libelle }}</option> }
                </select>
              </label>
              <label>Destinataire <input [(ngModel)]="f.destinataire" name="destinataire" /></label>
              <label>Date d'envoi <input type="datetime-local" [(ngModel)]="f.envoye_le" name="envoye_le" /></label>
            </div>
            <label>Référence d'envoi <input [(ngModel)]="f.reference_envoi" name="reference_envoi" /></label>
          }
          @if (a.code === 'cloturer') {
            <label>Résultat <em>*</em>
              <select [(ngModel)]="f.resultat" name="resultat">
                @for (r of store.libelles('resultats'); track r.code) { <option [value]="r.code">{{ r.libelle }}</option> }
              </select>
            </label>
            <label>Motif de la décision <textarea [(ngModel)]="f.motif_resolution" name="motif_resolution" rows="2"></textarea></label>
          }
          @if (a.code === 'suspendre') {
            <label>Conditions de reprise <textarea [(ngModel)]="f.conditions_reprise" name="conditions_reprise" rows="2"></textarea></label>
          }
          @if (motifRequis(a)) {
            <label>Motif @if (motifObligatoire(a)) { <em>*</em> }
              <textarea [(ngModel)]="f.motif" name="motif" rows="2" [placeholder]="a.code === 'traiter_interne' ? 'Pourquoi le SR traite sans affectation ?' : ''"></textarea>
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
  readonly enCours = signal<DefAction | null>(null);
  f: Champs = {
    type_id: '', motif_id: '', priorite: 'NORMALE', unite_id: '', instructions: '',
    analyse: '', actions_menees: '', conclusion: '', decision_proposee: '',
    evaluation: 'SUFFISANT', canal_envoi_id: '', destinataire: '', envoye_le: '',
    reference_envoi: '', resultat: 'FAVORABLE', motif_resolution: '',
    conditions_reprise: '', motif: '',
  };

  visibles(): DefAction[] {
    const a = this.dossier().actions ?? {};
    return BOUTONS.filter((b) => a[b.code]);
  }

  ouvrir(b: DefAction): void {
    const d = this.dossier();
    this.f = {
      type_id: d.type_ref?.id ?? '', motif_id: d.motif_ref?.id ?? '', priorite: d.priorite,
      unite_id: d.unite_traitement_ref?.id ?? '', instructions: '', analyse: '',
      actions_menees: '', conclusion: '', decision_proposee: '', evaluation: 'SUFFISANT',
      canal_envoi_id: '', destinataire: d.client.nom ?? '', envoye_le: maintenantLocal(),
      reference_envoi: '', resultat: d.resultat ?? 'FAVORABLE', motif_resolution: '',
      conditions_reprise: '', motif: '',
    };
    this.enCours.set(b);
  }

  fermer(): void {
    this.enCours.set(null);
  }

  motifRequis(a: DefAction): boolean {
    return !['prendre', 'soumettre_reponse', 'envoyer_reponse'].includes(a.code);
  }

  motifObligatoire(a: DefAction): boolean {
    return ['traiter_interne', 'demander_info', 'suspendre', 'refuser', 'annuler', 'rouvrir', 'evaluer', 'renvoyer_reponse'].includes(a.code);
  }

  confirmer(): void {
    const a = this.enCours();
    const d = this.dossier();
    if (!a) return;
    if (this.motifObligatoire(a) && !this.f.motif.trim() && a.code !== 'evaluer') {
      this.feedback.warning({ title: 'Motif obligatoire', message: 'Indiquez le motif de cette action.' });
      return;
    }
    const corps: Record<string, unknown> = { revision: d.revision, motif: this.f.motif.trim() || null };
    if (a.code === 'qualifier') {
      corps['type_id'] = this.f.type_id || null;
      corps['motif_id'] = this.f.motif_id || null;
      corps['priorite'] = this.f.priorite || null;
    }
    if (a.code === 'affecter' || (a.code === 'evaluer' && this.f.evaluation === 'INSUFFISANT')) {
      if (!this.f.unite_id && a.code === 'affecter') {
        this.feedback.warning({ title: 'Service obligatoire', message: 'Choisissez le service destinataire.' });
        return;
      }
      corps['unite_id'] = this.f.unite_id || null;
      corps['instructions'] = this.f.instructions.trim() || null;
    }
    if (a.code === 'retourner') {
      if (!this.f.analyse.trim() || !this.f.conclusion.trim()) {
        this.feedback.warning({ title: 'Retour incomplet', message: 'Analyse et conclusion sont obligatoires.' });
        return;
      }
      corps['analyse'] = this.f.analyse;
      corps['actions_menees'] = this.f.actions_menees.trim() || null;
      corps['conclusion'] = this.f.conclusion;
      corps['decision_proposee'] = this.f.decision_proposee || null;
    }
    if (a.code === 'evaluer') {
      corps['evaluation'] = this.f.evaluation;
      corps['commentaire'] = this.f.motif.trim() || null;
    }
    if (a.code === 'envoyer_reponse') {
      if (!this.f.canal_envoi_id) {
        this.feedback.warning({ title: 'Canal obligatoire', message: 'Indiquez le canal d’envoi.' });
        return;
      }
      corps['canal_envoi_id'] = this.f.canal_envoi_id;
      corps['destinataire'] = this.f.destinataire.trim() || null;
      corps['envoye_le'] = depuisSaisieLocale(this.f.envoye_le);
      corps['reference_envoi'] = this.f.reference_envoi.trim() || null;
    }
    if (a.code === 'cloturer') {
      corps['resultat'] = this.f.resultat;
      corps['motif_resolution'] = this.f.motif_resolution.trim() || this.f.motif.trim() || null;
    }
    if (a.code === 'suspendre') corps['conditions_reprise'] = this.f.conditions_reprise.trim() || null;

    const appel = a.reponse && a.code !== 'envoyer_reponse'
      ? this.rc.actionReponse(d.id, a.verbe, corps)
      : a.code === 'envoyer_reponse'
        ? this.rc.actionReponse(d.id, 'envoyer', corps)
        : this.rc.action(d.id, a.verbe, corps);
    this.feedback
      .run(() => appel, {
        busy: this.busy,
        loading: 'Enregistrement…',
        success: (r) => ({ title: a.libelle, details: [{ label: 'Référence', value: r.reference }, { label: 'Statut', value: r.statut_libelle }] }),
        errorTitle: 'Action refusée',
        retry: false,
      })
      .subscribe((r) => {
        this.enCours.set(null);
        this.modifie.emit(r);
      });
  }
}
