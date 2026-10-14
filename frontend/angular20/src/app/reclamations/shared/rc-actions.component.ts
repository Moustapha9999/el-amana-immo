import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { switchMap } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { Dossier, depuisSaisieLocale, maintenantLocal } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { CLASSEMENT_VIDE, Classement, RcClassementComponent, classementCorps, classementDe, classementErreur } from './rc-classement.component';

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
  priorite: string;
  unite_id: string;
  instructions: string;
  analyse: string;
  actions_menees: string;
  conclusion: string;
  decision_proposee: string;
  evaluation: string;
  objet: string;
  contenu: string;
  canal_envoi_id: string;
  destinataire: string;
  envoye_le: string;
  reference_envoi: string;
  resultat: string;
  motif_resolution: string;
  motif: string;
}

const BOUTONS: DefAction[] = [
  { code: 'qualifier', libelle: 'Qualifier', icone: 'rule', verbe: 'qualifier', primaire: true, motif: false },
  { code: 'affecter', libelle: 'Transmettre au service', icone: 'send', verbe: 'affecter', primaire: true, motif: false },
  { code: 'traiter_interne', libelle: 'Traiter au SR', icone: 'home_repair_service', verbe: 'traiter-interne', motif: true },
  { code: 'retourner', libelle: 'Retourner au SR', icone: 'assignment_return', verbe: 'retourner', primaire: true },
  { code: 'evaluer', libelle: 'Examiner le retour', icone: 'fact_check', verbe: 'evaluer', primaire: true, motif: false },
  { code: 'enregistrer_reponse', libelle: 'Enregistrer la réponse envoyée', icone: 'outgoing_mail', verbe: 'reponse', primaire: true },
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
  imports: [FormsModule, MatIconModule, RcClassementComponent],
  template: `
    <div class="bea-mg__actions bea-rc-actions">
      @for (b of visibles(); track b.code) {
        <button type="button" class="bea-mg__btn" [class.bea-mg__btn--primary]="b.primaire" [class.bea-mg__btn--ghost]="!b.primaire && !b.danger"
                [disabled]="busy()" (click)="ouvrir(b)">
          <mat-icon>{{ b.icone }}</mat-icon> {{ b.libelle }}
        </button>
      }
    </div>
    @if (dossier().statut === 'A_CLOTURER' && !dossier().actions['cloturer'] && dossier().reponse_courante?.statut === 'ENVOYEE') {
      <div class="bea-rc-note"><mat-icon>info</mat-icon><span>Réponse enregistrée : la clôture est réservée au Service Réclamations central.</span></div>
    }
    @if (enCours(); as a) {
      <div class="bea-mg__backdrop" (click)="fermer()"></div>
      <form class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" (ngSubmit)="confirmer()">
        <div class="bea-mg__modal-head">
          <h2>{{ a.libelle }} — {{ dossier().reference }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
        </div>
        <div class="bea-rc-form">
          @if (a.code === 'qualifier') {
            <bea-rc-classement [(valeur)]="classement" [tente]="tente()" />
            <label>Priorité
              <select [(ngModel)]="f.priorite" name="priorite">
                @for (p of store.libelles('priorites'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
              </select>
            </label>
          }
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
          @if (a.code === 'enregistrer_reponse') {
            <div class="bea-rc-note"><mat-icon>info</mat-icon>
              <span>Enregistrez la réponse telle qu’elle a été envoyée au client. Le dossier reste « À clôturer » jusqu’à la clôture par le Service Réclamations.</span>
            </div>
            <div class="bea-rc-row">
              <label>Canal d’envoi <em>*</em>
                <select [(ngModel)]="f.canal_envoi_id" name="canal_envoi_id"><option value="">—</option>
                  @for (c of store.refs('CANAL_REPONSE'); track c.id) { <option [value]="c.id">{{ c.libelle }}</option> }
                </select>
              </label>
              <label>Date d’envoi <em>*</em><input type="datetime-local" [(ngModel)]="f.envoye_le" name="envoye_le" [max]="maintenant" /></label>
              <label>Résultat
                <select [(ngModel)]="f.resultat" name="resultat"><option value="">—</option>
                  @for (r of store.libelles('resultats'); track r.code) { <option [value]="r.code">{{ r.libelle }}</option> }
                </select>
              </label>
            </div>
            <div class="bea-rc-row">
              <label>Destinataire <input [(ngModel)]="f.destinataire" name="destinataire" maxlength="255" /></label>
              <label>Référence d’envoi <input [(ngModel)]="f.reference_envoi" name="reference_envoi" maxlength="120" placeholder="N° de courrier, d’accusé…" /></label>
            </div>
            <label>Objet <input [(ngModel)]="f.objet" name="objet_reponse" maxlength="255" /></label>
            <label>Contenu de la réponse <em>*</em><textarea [(ngModel)]="f.contenu" name="contenu" rows="6" maxlength="50000"></textarea></label>
            <label>Preuve d’envoi (facultatif)
              <input type="file" (change)="choisirPreuve($event)" accept=".pdf,.png,.jpg,.jpeg,.msg,.eml" />
              <span class="bea-rc-hint">Courrier signé, accusé de réception, capture de l’e-mail… Classée « Preuve d’envoi » dans les documents.</span>
            </label>
          }
          @if (a.code === 'cloturer') {
            <label>Résultat
              <select [(ngModel)]="f.resultat" name="resultat"><option value="">— Repris de la réponse envoyée —</option>
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
  readonly classement = signal<Classement>({ ...CLASSEMENT_VIDE });
  readonly maintenant = maintenantLocal();
  private preuve: File | null = null;
  f: Champs = this.vierge();

  private vierge(d?: Dossier): Champs {
    return {
      priorite: d?.priorite ?? 'NORMALE',
      unite_id: d?.unite_concernee_ref?.actif ? d.unite_concernee_ref.id : (d?.unite_traitement_ref?.id ?? ''),
      instructions: '', analyse: '', actions_menees: '', conclusion: '', decision_proposee: '', evaluation: 'SUFFISANT',
      objet: d ? `Réponse à votre réclamation ${d.reference}` : '', contenu: '', canal_envoi_id: '',
      destinataire: d?.client.email ?? d?.client.nom ?? '', envoye_le: maintenantLocal(), reference_envoi: '',
      resultat: '', motif_resolution: '', motif: '',
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
    this.preuve = null;
    this.tente.set(false);
    this.classement.set(classementDe(d));
    this.enCours.set(b);
  }

  fermer(): void {
    this.enCours.set(null);
  }

  choisirPreuve(e: Event): void {
    this.preuve = (e.target as HTMLInputElement).files?.[0] ?? null;
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
      case 'qualifier': {
        const c = this.classement();
        const err = c.type_id ? classementErreur(c) : 'Le type de réclamation est obligatoire pour qualifier.';
        if (err) return this.avertir('Classement incomplet', err);
        Object.assign(corps, classementCorps(c), { priorite: this.f.priorite || null });
        break;
      }
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
      case 'enregistrer_reponse': {
        const envoyeLe = depuisSaisieLocale(this.f.envoye_le);
        if (!this.f.canal_envoi_id || !this.f.contenu.trim() || !envoyeLe) {
          return this.avertir('Réponse incomplète', 'Canal, date d’envoi et contenu de la réponse sont obligatoires.');
        }
        Object.assign(corps, {
          objet: this.f.objet.trim() || null, contenu: this.f.contenu.trim(), resultat: this.f.resultat || null,
          canal_envoi_id: this.f.canal_envoi_id, destinataire: this.f.destinataire.trim() || null,
          envoye_le: envoyeLe, reference_envoi: this.f.reference_envoi.trim() || null,
        });
        break;
      }
      case 'cloturer':
        if (!this.f.resultat && !d.reponse_courante?.resultat) {
          return this.avertir('Résultat obligatoire', 'La réponse envoyée n’indique pas de résultat : choisissez-le.');
        }
        corps['resultat'] = this.f.resultat || null;
        corps['motif_resolution'] = this.f.motif_resolution.trim() || null;
        break;
    }

    const preuve = a.code === 'enregistrer_reponse' ? this.preuve : null;
    const appel = a.code === 'enregistrer_reponse' ? this.rc.enregistrerReponse(d.id, corps) : this.rc.action(d.id, a.verbe, corps);
    this.feedback
      .run(() => appel, {
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
        if (preuve) this.joindrePreuve(r, preuve);
      });
  }

  private joindrePreuve(d: Dossier, fichier: File): void {
    this.feedback
      .run(() => this.rc.deposer(d.id, fichier, 'PREUVE_ENVOI', 'Preuve d’envoi de la réponse').pipe(switchMap(() => this.rc.lire(d.id))), {
        busy: this.busy,
        loading: 'Dépôt de la preuve d’envoi…',
        success: () => ({ title: 'Preuve d’envoi jointe', details: [{ label: 'Fichier', value: fichier.name }] }),
        errorTitle: 'Réponse enregistrée, preuve non jointe',
        errorHint: 'Déposez la preuve depuis l’onglet Documents (catégorie « Preuve d’envoi »).',
        retry: false,
      })
      .subscribe((r) => this.modifie.emit(r));
  }
}

function retourInsuffisant(f: Champs): boolean {
  return f.evaluation === 'INSUFFISANT';
}
