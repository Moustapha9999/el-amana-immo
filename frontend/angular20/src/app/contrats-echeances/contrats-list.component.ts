import { MontantPipe } from '../shared/montant.pipe';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface Contrat {
  id: string;
  reference: string;
  titre: string;
  numero_contrat: string | null;
  description: string | null;
  type_contrat: string;
  fournisseur_id: string | null;
  fournisseur_snapshot: string | null;
  agence_id: string | null;
  agence_libelle_snapshot: string | null;
  responsable_id: string | null;
  responsable_nom: string | null;
  date_signature: string | null;
  date_debut: string;
  date_fin: string | null;
  prochain_echeance: string | null;
  montant: number | null;
  montant_ht: number | null;
  taux_tva: number | null;
  devise: string;
  periodicite: string;
  mode_paiement: string | null;
  alerte_jours: number;
  observation: string | null;
  statut: string;
  contrat_precedent_id: string | null;
  echeances?: Echeance[];
  paiements?: Paiement[];
  historique?: Hist[];
}

interface Echeance {
  id: string;
  type_echeance: string;
  date_prevue: string;
  montant: number | null;
  statut: string;
  commentaire: string | null;
}

interface Paiement {
  id: string;
  reference: string | null;
  date_prevue: string;
  date_reelle: string | null;
  montant_prevu: number;
  montant_paye: number;
  statut: string;
  mode: string | null;
}

interface Hist {
  id: string;
  action: string;
  from_statut: string | null;
  to_statut: string | null;
  user_nom: string | null;
  commentaire: string | null;
  created_at: string;
}

interface RefItem {
  id: string;
  libelle?: string;
  raison_sociale?: string;
  code?: string;
  full_name?: string;
}

interface Alerte {
  type: string;
  contrat_id: string;
  reference: string;
  titre: string;
  fournisseur: string | null;
  agence: string | null;
  echeance: string | null;
  jours: number | null;
  niveau: string;
  statut: string;
}

@Component({
  selector: 'bea-contrats-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MgGedPanelComponent, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances</p>
          <h1>{{ titre() }}</h1>
        </div>
        <div class="bea-mg__actions">
          @if (mode() === 'fiche' || mode() === 'nouveau') {
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/contrats-echeances/liste">Retour liste</a>
          } @else if (mode() === 'echeances') {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirEcheance()">Nouvelle échéance</button>
          } @else {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/contrats-echeances/nouveau">Nouveau contrat</a>
          }
        </div>
      </header>

      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (msg()) { <p class="bea-stock-page__ok">{{ msg() }}</p> }

      @if (mode() === 'liste' || mode() === 'renouvellements') {
        <form class="bea-mg__search" [formGroup]="filtres" (ngSubmit)="loadListe()">
          <label class="bea-mg__field">Recherche
            <input formControlName="q" placeholder="Référence, objet, fournisseur, agence, responsable" />
          </label>
          <label class="bea-mg__field">Statut
            <select formControlName="statut" (change)="loadListe()">
              <option value="">Tous</option>
              @for (s of statuts; track s) { <option [value]="s">{{ s }}</option> }
            </select>
          </label>
          <label class="bea-mg__field">Échéance
            <select formControlName="horizon" (change)="loadListe()">
              <option value="">Toutes</option>
              <option value="retard">En retard</option>
              <option value="7">≤ 7 jours</option>
              <option value="30">≤ 30 jours</option>
              <option value="60">≤ 60 jours</option>
              <option value="90">≤ 90 jours</option>
            </select>
          </label>
          <button type="submit" class="bea-mg__btn bea-mg__btn--ghost">Filtrer</button>
        </form>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Référence</th><th>Objet</th><th>Type</th><th>Fournisseur</th><th>Agence</th>
                <th>Responsable</th><th>Début</th><th>Fin</th><th>Montant</th><th>Statut</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (c of contrats(); track c.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i * 35">
                  <td><code class="bea-mg__code">{{ c.reference }}</code></td>
                  <td>{{ c.titre }}</td>
                  <td>{{ c.type_contrat }}</td>
                  <td>{{ c.fournisseur_snapshot || '—' }}</td>
                  <td>{{ c.agence_libelle_snapshot || '—' }}</td>
                  <td>{{ c.responsable_nom || '—' }}</td>
                  <td>{{ c.date_debut }}</td>
                  <td>{{ c.date_fin || '—' }}</td>
                  <td>{{ c.montant | montant }} {{ c.devise }}</td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="c.statut">{{ c.statut }}</span></td>
                  <td class="bea-mg__actions-cell">
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', c.id]" title="Consulter"><mat-icon>visibility</mat-icon></a>
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', c.id]" title="Modifier"><mat-icon>edit</mat-icon></a>
                    <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerContrat(c)">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="11">
                    <div class="bea-ct-empty"><mat-icon>description</mat-icon><p>Aucun contrat enregistré.</p></div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'alertes') {
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Type</th><th>Contrat</th><th>Référence</th><th>Fournisseur</th><th>Agence</th>
                <th>Échéance</th><th>Jours</th><th>Niveau</th><th>Statut</th><th></th>
              </tr>
            </thead>
            <tbody>
              @for (a of alertes(); track $index; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i * 35">
                  <td>{{ a.type }}</td>
                  <td>{{ a.titre }}</td>
                  <td><code class="bea-mg__code">{{ a.reference }}</code></td>
                  <td>{{ a.fournisseur || '—' }}</td>
                  <td>{{ a.agence || '—' }}</td>
                  <td>{{ a.echeance || '—' }}</td>
                  <td>{{ a.jours ?? '—' }}</td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="a.niveau">{{ a.niveau }}</span></td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="a.statut">{{ a.statut }}</span></td>
                  <td><a class="bea-ct-link" [routerLink]="['/contrats-echeances', a.contrat_id]">Consulter</a></td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="10">
                    <div class="bea-ct-empty"><mat-icon>notifications_none</mat-icon><p>Aucune alerte.</p></div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'echeances') {
        @if (echeanceOuverte()) {
          <form class="bea-mg__panel bea-ct-panel bea-ct-section" [formGroup]="echeanceForm" (ngSubmit)="sauverEcheance()">
            <div class="bea-mg__panel-top"><h2>{{ echeanceEditId() ? 'Modifier l’échéance' : 'Nouvelle échéance' }}</h2></div>
            <div class="bea-mg__modal-body bea-ct-grid">
              <label>Contrat
                <select formControlName="contrat_id">
                  <option value="">—</option>
                  @for (c of contrats(); track c.id) { <option [value]="c.id">{{ c.reference }} — {{ c.titre }}</option> }
                </select>
              </label>
              <label>Type <input formControlName="type_echeance" /></label>
              <label>Date prévue <input type="date" formControlName="date_prevue" /></label>
              <label>Date réelle <input type="date" formControlName="date_reelle" /></label>
              <label>Montant <input type="number" formControlName="montant" /></label>
              <label>Statut
                <select formControlName="statut">
                  <option value="A_VENIR">À venir</option>
                  <option value="FAITE">Faite</option>
                  <option value="ANNULEE">Annulée</option>
                </select>
              </label>
              <label>Commentaire <input formControlName="commentaire" /></label>
            </div>
            <div class="bea-mg__actions" style="padding: 0 1rem 1rem">
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="echeanceForm.invalid">Enregistrer</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerEcheance()">Fermer</button>
            </div>
          </form>
        }
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead><tr><th>Contrat</th><th>Type</th><th>Date</th><th>Jours</th><th>Montant</th><th>Statut</th><th>Actions</th></tr></thead>
            <tbody>
              @for (e of echeances(); track e.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i * 35">
                  <td><code class="bea-mg__code">{{ e.reference }}</code> — {{ e.titre }}</td>
                  <td>{{ e.type_echeance }}</td>
                  <td>{{ e.date_prevue }}</td>
                  <td>{{ e.jours }}</td>
                  <td>{{ e.montant | montant }}</td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ e.statut }}</span></td>
                  <td class="bea-mg__actions-cell">
                    <a class="bea-mg__icon-btn" [routerLink]="['/contrats-echeances', e.contrat_id]" title="Consulter"><mat-icon>visibility</mat-icon></a>
                    <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="modifierEcheance(e)"><mat-icon>edit</mat-icon></button>
                    <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerEcheance(e)">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7">
                    <div class="bea-ct-empty"><mat-icon>event</mat-icon><p>Aucune échéance.</p></div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'paiements') {
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr><th>Contrat</th><th>Réf. paiement</th><th>Prévu</th><th>Payé</th><th>Reste</th><th>Statut</th><th></th></tr>
            </thead>
            <tbody>
              @for (p of paiements(); track p.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i * 35">
                  <td><code class="bea-mg__code">{{ p.reference }}</code> — {{ p.titre }}</td>
                  <td>{{ p.paiement_ref || '—' }}</td>
                  <td>{{ p.date_prevue }} · {{ p.montant_prevu | montant }}</td>
                  <td>{{ p.montant_paye | montant }}</td>
                  <td>{{ p.reste | montant }}</td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ p.statut }}</span></td>
                  <td><a class="bea-ct-link" [routerLink]="['/contrats-echeances', p.contrat_id]">Consulter</a></td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7">
                    <div class="bea-ct-empty"><mat-icon>payments</mat-icon><p>Aucun paiement.</p></div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'nouveau' || mode() === 'fiche') {
        <form [formGroup]="form" (ngSubmit)="save()">
          <div class="bea-mg__panel bea-ct-panel bea-ct-section">
          <div class="bea-mg__panel-top"><h2>Informations</h2></div>
          <div class="bea-mg__modal-body bea-ct-grid">
            <label>Objet <input formControlName="titre" /></label>
            <label>N° contrat <input formControlName="numero_contrat" /></label>
            <label>Type
              <select formControlName="type_contrat">
                @for (t of types(); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            <label>Devise <input formControlName="devise" /></label>
            <label>Description <input formControlName="description" /></label>
            <label>Observation <input formControlName="observation" /></label>
          </div>
          </div>
          <div class="bea-mg__panel bea-ct-panel bea-ct-section">
          <div class="bea-mg__panel-top"><h2>Fournisseur, agence, responsable</h2></div>
          <div class="bea-mg__modal-body bea-ct-grid">
            <label>Fournisseur
              <select formControlName="fournisseur_id">
                <option value="">—</option>
                @for (f of fournisseurs(); track f.id) { <option [value]="f.id">{{ f.raison_sociale }}</option> }
              </select>
            </label>
            <label>Agence
              <select formControlName="agence_id">
                <option value="">—</option>
                @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
              </select>
            </label>
            <label>Responsable
              <select formControlName="responsable_id">
                <option value="">—</option>
                @for (u of responsables(); track u.id) { <option [value]="u.id">{{ u.full_name }}</option> }
              </select>
            </label>
          </div>
          </div>
          <div class="bea-mg__panel bea-ct-panel bea-ct-section">
          <div class="bea-mg__panel-top"><h2>Dates et montants</h2></div>
          <div class="bea-mg__modal-body bea-ct-grid">
            <label>Signature <input type="date" formControlName="date_signature" /></label>
            <label>Début <input type="date" formControlName="date_debut" /></label>
            <label>Fin <input type="date" formControlName="date_fin" /></label>
            <label>Montant HT <input type="number" formControlName="montant_ht" /></label>
            <label>TVA % <input type="number" formControlName="taux_tva" /></label>
            <label>Périodicité
              <select formControlName="periodicite">
                <option value="MENSUEL">Mensuel</option>
                <option value="TRIMESTRIEL">Trimestriel</option>
                <option value="SEMESTRIEL">Semestriel</option>
                <option value="ANNUEL">Annuel</option>
                <option value="UNIQUE">Unique</option>
              </select>
            </label>
            <label>Mode de paiement <input formControlName="mode_paiement" /></label>
            <label>Alerte (jours) <input type="number" formControlName="alerte_jours" /></label>
          </div>
          <p class="bea-ct-note">TTC recalculé par le serveur à l’enregistrement. Montant actuel : {{ fiche()?.montant | montant }} {{ fiche()?.devise || form.controls.devise.value }}</p>
          <div class="bea-mg__actions" style="padding: 0 1rem 1rem">
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || saving()">
              {{ contratId() ? 'Enregistrer' : 'Enregistrer brouillon' }}
            </button>
          </div>
          </div>
        </form>

        @if (fiche(); as c) {
          <div class="bea-mg__actions">
            @if (c.statut === 'BROUILLON' || c.statut === 'EN_PREPARATION') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('soumettre')">Soumettre</button>
            }
            @if (c.statut === 'EN_VALIDATION') {
              <label>Motif de rejet <input [value]="motif()" (input)="setMotif($event)" /></label>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('valider')">Valider</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('rejeter')">Rejeter</button>
            }
            @if (c.statut === 'ACTIF') {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('suspendre')">Suspendre</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('expirer')">Marquer expiré</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="renouveler()">Préparer renouvellement</button>
            }
            @if (c.statut === 'SUSPENDU') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('reprendre')">Reprendre</button>
            }
            @if (c.statut === 'EXPIRE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="renouveler()">Préparer renouvellement</button>
            }
            @if (c.statut !== 'ARCHIVE' && c.statut !== 'ANNULE' && c.statut !== 'BROUILLON') {
              <label>Motif d’annulation <input [value]="motif()" (input)="setMotif($event)" /></label>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('archiver')">Archiver</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="transition('annuler')">Annuler</button>
            }
            @if (c.statut === 'BROUILLON') {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="supprimer()">Retirer le brouillon</button>
            }
          </div>
          @if (c.contrat_precedent_id) {
            <p>Contrat précédent : <a [routerLink]="['/contrats-echeances', c.contrat_precedent_id]">ouvrir</a></p>
          }

          <div class="bea-ct-tabs">
            <button type="button" [class.is-on]="onglet() === 'echeances'" (click)="onglet.set('echeances')">Échéances</button>
            <button type="button" [class.is-on]="onglet() === 'paiements'" (click)="onglet.set('paiements')">Paiements</button>
            <button type="button" [class.is-on]="onglet() === 'documents'" (click)="onglet.set('documents')">Documents</button>
            <button type="button" [class.is-on]="onglet() === 'historique'" (click)="onglet.set('historique')">Historique</button>
          </div>

          @if (onglet() === 'echeances') {
            <div class="bea-ct-pane">
            <form class="bea-ct-grid" [formGroup]="echeanceForm" (ngSubmit)="addEcheance()">
              <label>Type <input formControlName="type_echeance" /></label>
              <label>Date <input type="date" formControlName="date_prevue" /></label>
              <label>Montant <input type="number" formControlName="montant" /></label>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary">{{ echeanceEditId() ? 'Enregistrer' : 'Ajouter l’échéance' }}</button>
            </form>
            <ul class="bea-ct-list">
              @for (e of c.echeances || []; track e.id) {
                <li>
                  <strong>{{ e.date_prevue }}</strong>
                  <span>{{ e.type_echeance }}</span>
                  <span class="bea-ct-badge" [attr.data-tone]="e.statut">{{ e.statut }}</span>
                  <span>{{ e.montant | montant }}</span>
                  <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editerEcheanceFiche(e)"><mat-icon>edit</mat-icon></button>
                  <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerEcheance(e)"><mat-icon>delete</mat-icon></button>
                </li>
              } @empty { <li>Aucune échéance.</li> }
            </ul>
            </div>
          }
          @if (onglet() === 'paiements') {
            <div class="bea-ct-pane">
            <form class="bea-ct-grid" [formGroup]="paiementForm" (ngSubmit)="addPaiement()">
              <label>Référence <input formControlName="reference" /></label>
              <label>Date prévue <input type="date" formControlName="date_prevue" /></label>
              <label>Date réelle <input type="date" formControlName="date_reelle" /></label>
              <label>Montant prévu <input type="number" formControlName="montant_prevu" /></label>
              <label>Montant payé <input type="number" formControlName="montant_paye" /></label>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Enregistrer le suivi</button>
            </form>
            <p class="bea-ct-note">Suivi interne uniquement : aucun virement n’est exécuté.</p>
            <ul class="bea-ct-list">
              @for (p of c.paiements || []; track p.id) {
                <li>
                  <strong>{{ p.date_prevue }}</strong>
                  <span class="bea-ct-badge" [attr.data-tone]="p.statut">{{ p.statut }}</span>
                  <span>prévu {{ p.montant_prevu | montant }}</span>
                  <span>payé {{ p.montant_paye | montant }}</span>
                </li>
              } @empty { <li>Aucun paiement.</li> }
            </ul>
            </div>
          }
          @if (onglet() === 'documents') {
            <div class="bea-ct-pane bea-mg__panel">
              <bea-mg-ged moduleCode="contrats-echeances" entity="contrat" [entityId]="c.id" />
            </div>
          }
          @if (onglet() === 'historique') {
            <ul class="bea-ct-list bea-ct-pane">
              @for (h of c.historique || []; track h.id) {
                <li>
                  <strong>{{ h.created_at }}</strong>
                  <span>{{ h.action }}</span>
                  <span>{{ h.user_nom || '—' }}</span>
                  @if (h.to_statut) { <span class="bea-ct-badge" [attr.data-tone]="h.to_statut">{{ h.to_statut }}</span> }
                </li>
              } @empty { <li>Aucun historique.</li> }
            </ul>
          }
        }
      }
    </section>
  `,
})
export class ContratsListComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly dialogs = inject(UiDialogService);

  readonly statuts = ['BROUILLON', 'EN_PREPARATION', 'EN_VALIDATION', 'ACTIF', 'SUSPENDU', 'EXPIRE', 'ARCHIVE', 'REJETE', 'ANNULE'];
  readonly mode = signal<'liste' | 'alertes' | 'echeances' | 'paiements' | 'renouvellements' | 'nouveau' | 'fiche'>('liste');
  readonly titre = signal('Contrats');
  readonly contrats = signal<Contrat[]>([]);
  readonly alertes = signal<Alerte[]>([]);
  readonly echeances = signal<Array<Echeance & { reference: string; titre: string; contrat_id: string; jours: number }>>([]);
  readonly paiements = signal<Array<Paiement & { reference: string; titre: string; contrat_id: string; paiement_ref: string | null; reste: number }>>([]);
  readonly fiche = signal<Contrat | null>(null);
  readonly contratId = signal<string | null>(null);
  readonly erreur = signal<string | null>(null);
  readonly msg = signal<string | null>(null);
  readonly saving = signal(false);
  readonly onglet = signal<'echeances' | 'paiements' | 'documents' | 'historique'>('echeances');
  readonly motif = signal('');
  readonly types = signal<Array<{ code: string; libelle: string }>>([]);
  readonly fournisseurs = signal<RefItem[]>([]);
  readonly agences = signal<RefItem[]>([]);
  readonly responsables = signal<RefItem[]>([]);

  readonly filtres = this.fb.nonNullable.group({ q: [''], statut: [''], horizon: [''] });
  readonly form = this.fb.nonNullable.group({
    titre: ['', Validators.required],
    numero_contrat: [''],
    description: [''],
    type_contrat: ['AUTRE'],
    devise: ['MRU'],
    fournisseur_id: [''],
    agence_id: [''],
    responsable_id: [''],
    date_signature: [''],
    date_debut: ['', Validators.required],
    date_fin: [''],
    montant_ht: [null as number | null],
    taux_tva: [0],
    periodicite: ['ANNUEL'],
    mode_paiement: [''],
    alerte_jours: [30],
    observation: [''],
  });
  readonly echeanceOuverte = signal(false);
  readonly echeanceEditId = signal<string | null>(null);
  readonly echeanceForm = this.fb.nonNullable.group({
    contrat_id: [''],
    type_echeance: ['PAIEMENT'],
    date_prevue: ['', Validators.required],
    date_reelle: [''],
    montant: [null as number | null],
    statut: ['A_VENIR'],
    commentaire: [''],
  });
  readonly paiementForm = this.fb.nonNullable.group({
    reference: [''],
    date_prevue: ['', Validators.required],
    date_reelle: [''],
    montant_prevu: [0],
    montant_paye: [0],
  });

  ngOnInit(): void {
    this.route.url.subscribe(() => this.sync());
    this.route.queryParamMap.subscribe(() => this.sync());
  }

  private sync(): void {
    const path = this.route.snapshot.routeConfig?.path ?? '';
    const id = this.route.snapshot.paramMap.get('id');
    this.erreur.set(null);
    if (path === 'nouveau') {
      this.mode.set('nouveau');
      this.titre.set('Nouveau contrat');
      this.contratId.set(null);
      this.fiche.set(null);
      this.form.reset({
        titre: '', numero_contrat: '', description: '', type_contrat: 'AUTRE', devise: 'MRU',
        fournisseur_id: '', agence_id: '', responsable_id: '', date_signature: '',
        date_debut: new Date().toISOString().slice(0, 10), date_fin: '', montant_ht: null,
        taux_tva: 0, periodicite: 'ANNUEL', mode_paiement: '', alerte_jours: 30, observation: '',
      });
      this.loadRefs();
      return;
    }
    if (id && path === ':id') {
      this.mode.set('fiche');
      this.contratId.set(id);
      this.loadRefs();
      this.loadOne(id);
      return;
    }
    if (path === 'alertes') {
      this.mode.set('alertes');
      this.titre.set('Alertes');
      this.api.get<Alerte[]>('/mg/contrats/alertes').subscribe({
        next: (rows) => this.alertes.set(rows),
        error: (e) => this.fail(e),
      });
      return;
    }
    if (path === 'echeances') {
      this.mode.set('echeances');
      this.titre.set('Échéances');
      this.api.get<Array<Echeance & { reference: string; titre: string; contrat_id: string; jours: number }>>('/mg/contrats/echeances').subscribe({
        next: (rows) => this.echeances.set(rows),
        error: (e) => this.fail(e),
      });
      return;
    }
    if (path === 'paiements') {
      this.mode.set('paiements');
      this.titre.set('Paiements');
      const statut = this.route.snapshot.queryParamMap.get('statut') || '';
      const params: Record<string, string> = {};
      if (statut) params['statut'] = statut;
      this.api.get<Array<Paiement & { reference: string; titre: string; contrat_id: string; paiement_ref: string | null; reste: number }>>('/mg/contrats/paiements', params).subscribe({
        next: (rows) => this.paiements.set(rows),
        error: (e) => this.fail(e),
      });
      return;
    }
    this.mode.set(path === 'renouvellements' ? 'renouvellements' : 'liste');
    this.titre.set(path === 'renouvellements' ? 'Renouvellements' : 'Contrats');
    const qp = this.route.snapshot.queryParamMap;
    this.filtres.patchValue({
      statut: qp.get('statut') || '',
      horizon: qp.get('horizon') || '',
    });
    this.loadListe();
  }

  loadListe(): void {
    const raw = this.filtres.getRawValue();
    const params: Record<string, string> = {};
    if (raw.q.trim()) params['q'] = raw.q.trim();
    if (raw.statut) params['statut'] = raw.statut;
    if (raw.horizon) params['horizon'] = raw.horizon;
    if (this.mode() === 'renouvellements') params['renouveles'] = 'true';
    this.api.get<Contrat[]>('/mg/contrats', params).subscribe({
      next: (rows) => this.contrats.set(rows),
      error: (e) => this.fail(e),
    });
  }

  loadRefs(): void {
    this.api.get<Array<{ code: string; libelle: string }>>('/mg/contrats/types').subscribe({
      next: (rows) => this.types.set(rows),
      error: () => undefined,
    });
    this.api.get<RefItem[]>('/mg/contrats/fournisseurs').subscribe({
      next: (rows) => this.fournisseurs.set(rows),
      error: () => undefined,
    });
    this.api.get<RefItem[]>('/mg/contrats/agences').subscribe({
      next: (rows) => this.agences.set(rows),
      error: () => undefined,
    });
    this.api.get<RefItem[]>('/mg/contrats/responsables').subscribe({
      next: (rows) => this.responsables.set(rows),
      error: () => undefined,
    });
  }

  loadOne(id: string): void {
    this.api.get<Contrat>(`/mg/contrats/${id}`).subscribe({
      next: (c) => {
        this.fiche.set(c);
        this.titre.set(c.reference);
        this.form.patchValue({
          titre: c.titre,
          numero_contrat: c.numero_contrat ?? '',
          description: c.description ?? '',
          type_contrat: c.type_contrat || 'AUTRE',
          devise: c.devise || 'MRU',
          fournisseur_id: c.fournisseur_id ?? '',
          agence_id: c.agence_id ?? '',
          responsable_id: c.responsable_id ?? '',
          date_signature: c.date_signature ?? '',
          date_debut: c.date_debut,
          date_fin: c.date_fin ?? '',
          montant_ht: c.montant_ht,
          taux_tva: c.taux_tva ?? 0,
          periodicite: c.periodicite || 'ANNUEL',
          mode_paiement: c.mode_paiement ?? '',
          alerte_jours: c.alerte_jours ?? 30,
          observation: c.observation ?? '',
        });
      },
      error: (e) => this.fail(e, 'Contrat introuvable.'),
    });
  }

  save(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.erreur.set(null);
    const raw = this.form.getRawValue();
    const body = {
      ...raw,
      fournisseur_id: raw.fournisseur_id || null,
      agence_id: raw.agence_id || null,
      responsable_id: raw.responsable_id || null,
      date_signature: raw.date_signature || null,
      date_fin: raw.date_fin || null,
      numero_contrat: raw.numero_contrat || null,
      description: raw.description || null,
      mode_paiement: raw.mode_paiement || null,
      observation: raw.observation || null,
      montant_ht: raw.montant_ht,
    };
    const id = this.contratId();
    const req = id
      ? this.api.patch<Contrat>(`/mg/contrats/${id}`, body)
      : this.api.post<Contrat>('/mg/contrats', body);
    req.subscribe({
      next: (c) => {
        this.saving.set(false);
        this.msg.set('Contrat enregistré.');
        void this.router.navigateByUrl(`/contrats-echeances/${c.id}`);
      },
      error: (e) => {
        this.saving.set(false);
        this.fail(e, 'Enregistrement impossible.');
      },
    });
  }

  transition(action: string): void {
    const id = this.contratId();
    if (!id) return;
    let commentaire: string | null = null;
    if (action === 'rejeter' || action === 'annuler') {
      commentaire = this.motif().trim();
      if (!commentaire) {
        this.erreur.set('Motif obligatoire.');
        return;
      }
    }
    this.api.post<Contrat>(`/mg/contrats/${id}/transition`, { action, commentaire }).subscribe({
      next: (c) => {
        this.fiche.set(c);
        this.msg.set('Statut mis à jour.');
      },
      error: (e) => this.fail(e),
    });
  }

  renouveler(): void {
    const id = this.contratId();
    if (!id) return;
    this.api.post<Contrat>(`/mg/contrats/${id}/renouveler`, {}).subscribe({
      next: (c) => void this.router.navigateByUrl(`/contrats-echeances/${c.id}`),
      error: (e) => this.fail(e),
    });
  }

  supprimer(): void {
    const id = this.contratId();
    if (!id) return;
    this.api.delete(`/mg/contrats/${id}`).subscribe({
      next: () => void this.router.navigateByUrl('/contrats-echeances/liste'),
      error: (e) => this.fail(e),
    });
  }

  supprimerContrat(c: Contrat): void {
    this.dialogs
      .confirmAction('suppression', `Retirer le contrat ${c.reference} du registre ? L’historique reste en base.`)
      .subscribe((ok) => {
        if (!ok) return;
        this.api.delete(`/mg/contrats/${c.id}`).subscribe({
          next: () => this.loadListe(),
          error: (e) => this.fail(e),
        });
      });
  }

  ouvrirEcheance(): void {
    this.echeanceEditId.set(null);
    this.echeanceForm.reset({
      contrat_id: '', type_echeance: 'PAIEMENT', date_prevue: '', date_reelle: '',
      montant: null, statut: 'A_VENIR', commentaire: '',
    });
    this.echeanceOuverte.set(true);
    if (!this.contrats().length) this.loadListe();
  }

  modifierEcheance(e: Echeance & { contrat_id: string; date_reelle?: string | null; commentaire?: string | null }): void {
    this.echeanceEditId.set(e.id);
    this.echeanceForm.patchValue({
      contrat_id: e.contrat_id,
      type_echeance: e.type_echeance,
      date_prevue: e.date_prevue,
      date_reelle: e.date_reelle ?? '',
      montant: e.montant,
      statut: e.statut,
      commentaire: e.commentaire ?? '',
    });
    this.echeanceOuverte.set(true);
    if (!this.contrats().length) this.loadListe();
  }

  fermerEcheance(): void {
    this.echeanceOuverte.set(false);
    this.echeanceEditId.set(null);
  }

  sauverEcheance(): void {
    if (this.echeanceForm.invalid) return;
    const raw = this.echeanceForm.getRawValue();
    const body = {
      type_echeance: raw.type_echeance,
      date_prevue: raw.date_prevue,
      date_reelle: raw.date_reelle || null,
      montant: raw.montant,
      statut: raw.statut,
      commentaire: raw.commentaire || null,
    };
    const editId = this.echeanceEditId();
    const req = editId
      ? this.api.patch(`/mg/contrats/echeances/${editId}`, body)
      : this.api.post(`/mg/contrats/${raw.contrat_id}/echeances`, body);
    if (!editId && !raw.contrat_id) {
      this.erreur.set('Choisissez un contrat.');
      return;
    }
    req.subscribe({
      next: () => {
        this.fermerEcheance();
        this.sync();
      },
      error: (e) => this.fail(e),
    });
  }

  editerEcheanceFiche(e: Echeance): void {
    this.echeanceEditId.set(e.id);
    this.echeanceForm.patchValue({
      type_echeance: e.type_echeance,
      date_prevue: e.date_prevue,
      montant: e.montant,
      statut: e.statut,
      commentaire: e.commentaire ?? '',
    });
  }

  supprimerEcheance(e: { id: string }): void {
    this.dialogs.confirmAction('suppression', 'Supprimer cette échéance ?').subscribe((ok) => {
      if (!ok) return;
      this.api.delete(`/mg/contrats/echeances/${e.id}`).subscribe({
        next: () => this.sync(),
        error: (err) => this.fail(err),
      });
    });
  }

  addEcheance(): void {
    const id = this.contratId();
    if (!id || this.echeanceForm.invalid) return;
    const raw = this.echeanceForm.getRawValue();
    const body = {
      type_echeance: raw.type_echeance,
      date_prevue: raw.date_prevue,
      date_reelle: raw.date_reelle || null,
      montant: raw.montant,
      statut: raw.statut,
      commentaire: raw.commentaire || null,
    };
    const editId = this.echeanceEditId();
    const req = editId
      ? this.api.patch<Contrat>(`/mg/contrats/echeances/${editId}`, body)
      : this.api.post<Contrat>(`/mg/contrats/${id}/echeances`, body);
    req.subscribe({
      next: (c) => {
        if (editId) this.loadOne(id);
        else this.fiche.set(c);
        this.echeanceEditId.set(null);
        this.echeanceForm.reset({
          contrat_id: '', type_echeance: 'PAIEMENT', date_prevue: '', date_reelle: '',
          montant: null, statut: 'A_VENIR', commentaire: '',
        });
      },
      error: (e) => this.fail(e),
    });
  }

  addPaiement(): void {
    const id = this.contratId();
    if (!id || this.paiementForm.invalid) return;
    const raw = this.paiementForm.getRawValue();
    this.api.post<Contrat>(`/mg/contrats/${id}/paiements`, {
      reference: raw.reference || null,
      date_prevue: raw.date_prevue,
      date_reelle: raw.date_reelle || null,
      montant_prevu: raw.montant_prevu,
      montant_paye: raw.montant_paye,
    }).subscribe({
      next: (c) => this.fiche.set(c),
      error: (e) => this.fail(e),
    });
  }

  setMotif(event: Event): void {
    this.motif.set((event.target as HTMLInputElement).value);
  }

  private fail(err: unknown, fallback = 'Opération impossible.'): void {
    const detail = err instanceof HttpErrorResponse ? err.error?.detail : null;
    this.erreur.set(typeof detail === 'string' ? detail : fallback);
  }
}
