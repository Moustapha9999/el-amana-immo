import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { OrgEntiteSelectComponent } from '../../core/org/org-entite-select.component';
import {
  ORG_AFFECTATION_LIBELLES,
  ORG_PERIMETRE_LIBELLES,
  OrgAffectation,
  OrgPerimetre,
  OrgTypeAffectation,
} from '../../core/org/org-referentiel.models';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { OrgFiche, OrgPoste, orgErreur } from './core-admin-organigramme.models';

const BASE = '/plateforme/admin/organisation';

/**
 * Fiche utilisateur — rattachement à l'organigramme : une affectation principale, des affectations
 * secondaires ou d'intérim, et le périmètre organisationnel (jamais élargi automatiquement).
 */
@Component({
  selector: 'bea-core-admin-user-org',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, RouterLink, OrgEntiteSelectComponent],
  template: `
    <section class="bea-admin-panel">
      <h2>Organigramme — affectations</h2>
      <p class="bea-admin-panel__hint">
        L’affectation situe la personne dans l’organigramme. Elle ne donne aucun droit applicatif : les rôles et
        permissions restent gérés plus haut. Le périmètre « Entité » ou « Entité et sous-entités » élargit les
        dossiers visibles dans les modules qui l’appliquent ; par défaut il reste personnel.
      </p>

      @if (interdit()) {
        <p class="bea-admin-panel__empty">Gestion des affectations réservée à la permission « core.admin.organisation ».</p>
      } @else {
        @if (!affectations().length) {
          <p class="bea-admin-panel__empty">Aucune affectation : l’utilisateur n’est rattaché à aucune entité.</p>
        } @else {
          <div class="bea-admin-table-wrap">
            <table class="bea-admin-table">
              <thead>
                <tr><th>Entité</th><th>Type</th><th>Poste</th><th>Périmètre</th><th>Période</th><th>Actions</th></tr>
              </thead>
              <tbody>
                @for (a of affectations(); track a.id + ':' + rev()) {
                  <tr [class.bea-org-closed]="!a.actif">
                    <td>
                      <a class="bea-admin-table__link" routerLink="/admin/organigramme">{{ a.entite }}</a>
                      <div class="bea-admin-sessions__meta">{{ a.chemin }}</div>
                      @if (!a.entite_active) { <span class="bea-badge bea-badge--inactif">Entité désactivée</span> }
                    </td>
                    <td>{{ a.type_libelle }}</td>
                    <td>{{ a.poste || '—' }}</td>
                    <td>
                      @if (a.actif) {
                        <select [ngModel]="a.perimetre" (ngModelChange)="changerPerimetre(a, $event)" [disabled]="saving()" aria-label="Périmètre">
                          @for (p of perimetres; track p) { <option [value]="p">{{ perimetreLibelle(p) }}</option> }
                        </select>
                      } @else {
                        {{ a.perimetre_libelle }}
                      }
                    </td>
                    <td>
                      {{ a.date_debut | date: 'dd/MM/yyyy' }} → {{ a.date_fin ? (a.date_fin | date: 'dd/MM/yyyy') : 'en cours' }}
                    </td>
                    <td>
                      @if (a.actif) {
                        <button type="button" class="bea-admin-btn bea-admin-btn--tiny bea-admin-btn--danger" [disabled]="saving()" (click)="cloturer(a)">Clôturer</button>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }

        <div class="bea-admin-grid bea-org-new">
          <label class="bea-admin-field bea-admin-field--full">
            <span>Nouvelle affectation — entité</span>
            <bea-org-entite-select [ngModel]="entiteId()" (ngModelChange)="choisirEntite($event)" placeholder="— Choisir une entité —" />
          </label>
          <label class="bea-admin-field">
            <span>Type</span>
            <select [ngModel]="type()" (ngModelChange)="type.set($event); marquer()">
              @for (t of typesAffectation; track t) { <option [value]="t">{{ typeLibelle(t) }}</option> }
            </select>
          </label>
          <label class="bea-admin-field">
            <span>Poste</span>
            <select [ngModel]="posteId()" (ngModelChange)="posteId.set($event); marquer()" [disabled]="!postes().length">
              <option value="">— Aucun —</option>
              @for (p of postes(); track p.id) { <option [value]="p.id">{{ p.intitule }}{{ p.est_responsable ? ' (responsable)' : '' }}</option> }
            </select>
          </label>
          <label class="bea-admin-field">
            <span>Périmètre</span>
            <select [ngModel]="perimetre()" (ngModelChange)="perimetre.set($event); marquer()">
              @for (p of perimetres; track p) { <option [value]="p">{{ perimetreLibelle(p) }}</option> }
            </select>
          </label>
          <label class="bea-admin-field">
            <span>Date de début</span>
            <input type="date" [ngModel]="dateDebut()" (ngModelChange)="dateDebut.set($event); marquer()" />
          </label>
          <label class="bea-admin-field bea-admin-field--full">
            <span>Commentaire</span>
            <input type="text" maxlength="1000" [ngModel]="commentaire()" (ngModelChange)="commentaire.set($event); marquer()" />
          </label>
        </div>
        @if (type() === 'PRINCIPALE' && principale(); as p) {
          <p class="bea-admin-note">L’affectation principale actuelle ({{ p.entite }}) sera clôturée et conservée dans l’historique.</p>
        }
        <div class="bea-admin-form__actions">
          <button type="button" class="bea-admin-btn" [disabled]="saving() || !entiteId()" (click)="ajouter()">Affecter</button>
        </div>
      }
    </section>
  `,
  styles: [
    `
      .bea-org-closed {
        opacity: 0.6;
      }
      .bea-org-new {
        margin-top: 1rem;
      }
      :host .bea-admin-field input,
      :host .bea-admin-field select,
      :host td select {
        border: 0;
        border-radius: 8px;
        padding: 0.5rem 0.7rem;
        background: var(--bea-surface);
        color: var(--bea-ink);
        outline: none;
      }
      :host .bea-admin-field input:focus,
      :host .bea-admin-field select:focus,
      :host td select:focus {
        box-shadow: 0 0 0 2px var(--bea-brand-400);
      }
    `,
  ],
})
export class CoreAdminUserOrgComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);

  readonly userId = input.required<string>();
  readonly nomUtilisateur = input<string>('cet utilisateur');

  readonly perimetres = Object.keys(ORG_PERIMETRE_LIBELLES) as OrgPerimetre[];
  readonly typesAffectation = Object.keys(ORG_AFFECTATION_LIBELLES) as OrgTypeAffectation[];

  readonly affectations = signal<OrgAffectation[]>([]);
  readonly interdit = signal(false);
  readonly saving = signal(false);
  readonly rev = signal(0);
  readonly dirty = signal(false);

  readonly entiteId = signal<string | null>(null);
  readonly type = signal<OrgTypeAffectation>('PRINCIPALE');
  readonly perimetre = signal<OrgPerimetre>('PERSONNEL');
  readonly posteId = signal('');
  readonly postes = signal<OrgPoste[]>([]);
  readonly dateDebut = signal(new Date().toISOString().slice(0, 10));
  readonly commentaire = signal('');

  readonly hasUnsavedChanges = unsavedChanges(() => this.dirty() && !this.saving());

  ngOnInit(): void {
    this.charger();
  }

  isDirty(): boolean {
    return this.dirty() && !this.saving();
  }

  principale(): OrgAffectation | undefined {
    return this.affectations().find((a) => a.actif && a.type_affectation === 'PRINCIPALE');
  }

  perimetreLibelle(p: OrgPerimetre): string {
    return ORG_PERIMETRE_LIBELLES[p];
  }

  typeLibelle(t: OrgTypeAffectation): string {
    return ORG_AFFECTATION_LIBELLES[t];
  }

  marquer(): void {
    this.dirty.set(true);
  }

  choisirEntite(id: string | null): void {
    this.entiteId.set(id);
    this.posteId.set('');
    this.postes.set([]);
    this.dirty.set(!!id);
    if (!id) return;
    this.api.get<OrgFiche>(`${BASE}/entites/${id}`).subscribe({
      next: (f) => this.postes.set(f.postes.filter((p) => p.actif)),
      error: () => this.postes.set([]),
    });
  }

  async ajouter(): Promise<void> {
    const entiteId = this.entiteId();
    if (!entiteId || this.saving()) return;
    const elargi = this.perimetre() !== 'PERSONNEL';
    const ok = await this.dialogs.confirm({
      title: 'Nouvelle affectation',
      message:
        `Affecter ${this.nomUtilisateur()} (${this.typeLibelle(this.type()).toLowerCase()}) ?` +
        (elargi ? ` Le périmètre « ${this.perimetreLibelle(this.perimetre())} » élargit les dossiers visibles dans les modules concernés.` : ''),
      tone: elargi ? 'warn' : 'primary',
      confirmLabel: 'Affecter',
    });
    if (!ok) return;
    this.saving.set(true);
    this.api
      .post<OrgAffectation>(`${BASE}/affectations`, {
        user_id: this.userId(),
        entite_id: entiteId,
        type_affectation: this.type(),
        perimetre: this.perimetre(),
        poste_id: this.posteId() || null,
        date_debut: this.dateDebut() || null,
        commentaire: this.commentaire().trim() || null,
      })
      .subscribe({
        next: async (a) => {
          this.saving.set(false);
          this.reinitialiser();
          this.charger();
          await this.dialogs.success(`Affectation à « ${a.entite} » enregistrée.`);
        },
        error: (err) => this.echec(err, 'Affectation impossible.'),
      });
  }

  async changerPerimetre(a: OrgAffectation, perimetre: OrgPerimetre): Promise<void> {
    if (perimetre === a.perimetre) return;
    const ok = await this.dialogs.confirm({
      title: 'Modifier le périmètre',
      message: `Passer le périmètre de l’affectation « ${a.entite} » à « ${this.perimetreLibelle(perimetre)} » ?`,
      tone: perimetre === 'PERSONNEL' ? 'primary' : 'warn',
      confirmLabel: 'Modifier',
    });
    if (!ok) {
      this.rev.update((n) => n + 1);
      return;
    }
    this.saving.set(true);
    this.api.patch(`${BASE}/affectations/${a.id}`, { perimetre }).subscribe({
      next: async () => {
        this.saving.set(false);
        this.charger();
        await this.dialogs.success('Périmètre mis à jour.');
      },
      error: (err) => {
        this.charger();
        this.echec(err, 'Modification impossible.');
      },
    });
  }

  async cloturer(a: OrgAffectation): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Clôturer l’affectation',
      message: `Clôturer l’affectation à « ${a.entite} » à la date du jour ? Elle reste dans l’historique.`,
      tone: 'danger',
      confirmLabel: 'Clôturer',
    });
    if (!ok) return;
    this.saving.set(true);
    this.api.post(`${BASE}/affectations/${a.id}/cloturer`, {}).subscribe({
      next: async () => {
        this.saving.set(false);
        this.charger();
        await this.dialogs.success('Affectation clôturée.');
      },
      error: (err) => this.echec(err, 'Clôture impossible.'),
    });
  }

  private charger(): void {
    this.api.get<{ items: OrgAffectation[] }>(`${BASE}/affectations`, { user_id: this.userId() }).subscribe({
      next: (r) => {
        this.interdit.set(false);
        this.affectations.set(r.items ?? []);
        this.rev.update((n) => n + 1);
      },
      error: (err) => {
        if (err instanceof HttpErrorResponse && err.status === 403) {
          this.interdit.set(true);
        } else {
          void this.dialogs.error(orgErreur(err, 'Affectations indisponibles.'));
        }
      },
    });
  }

  private reinitialiser(): void {
    this.entiteId.set(null);
    this.type.set('PRINCIPALE');
    this.perimetre.set('PERSONNEL');
    this.posteId.set('');
    this.postes.set([]);
    this.dateDebut.set(new Date().toISOString().slice(0, 10));
    this.commentaire.set('');
    this.dirty.set(false);
  }

  private async echec(err: unknown, fallback: string): Promise<void> {
    this.saving.set(false);
    await this.dialogs.error(orgErreur(err, fallback));
  }
}
