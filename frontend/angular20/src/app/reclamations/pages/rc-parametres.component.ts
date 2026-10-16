import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable, Subject, debounceTime, distinctUntilChanged, of, switchMap } from 'rxjs';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { OrgEntiteSelectComponent } from '../../core/org/org-entite-select.component';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import {
  ChampOperation, DEVISE_REFERENCE, Domaine, Membre, RefItem, RegleContenu, RegleMotif, Regles, TypeUnite, Unite, UtilisateurTrouve, dateFr,
} from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

type Onglet = 'referentiels' | 'regles' | 'unites';

interface BrouillonRegle extends RegleContenu {
  motif_id: string;
  motif: string;
}
type Vue = 'CLASSEMENT' | 'CANAL' | 'CANAL_REPONSE';

interface LigneRef {
  item: RefItem;
  niveau: number;
}

interface BrouillonRef {
  id: string | null;
  domaine: Domaine;
  parent: RefItem | null;
  libelle: string;
  code: string;
  description: string;
  ordre: number;
}

interface BrouillonUnite {
  id: string | null;
  type_unite: TypeUnite;
  libelle: string;
  code: string;
  parent_id: string;
  agence_id: string;
  org_entite_id: string | null;
  email: string;
  description: string;
  ordre: number;
}

interface NoeudUnite {
  unite: Unite;
  niveau: number;
}

const ICONES_UNITE: Record<TypeUnite, string> = {
  DIRECTION: 'account_balance', DEPARTEMENT: 'domain', SERVICE: 'groups', AGENCE: 'storefront', CELLULE: 'hub',
};

const ENFANT: Partial<Record<Domaine, Domaine>> = { TYPE: 'MOTIF', MOTIF: 'SOUS_MOTIF' };

function normaliser(texte: string): string {
  return texte.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

/** Paramètres du module : référentiels de qualification et organisation (unités, membres). */
@Component({
  selector: 'bea-rc-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ReclamationsUiComponent, OrgEntiteSelectComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Paramètres</h1>
          <p class="bea-ct-head__sub">Référentiels de qualification et organisation des unités. Un élément désactivé ou supprimé n’est plus proposé dans les listes ; les dossiers existants conservent leur libellé.</p>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reclamations/dossiers"><mat-icon>arrow_back</mat-icon> Réclamations</a>
        </div>
      </header>

      @if (!store.config()) {
        <section class="bea-mg__panel bea-rc-pad"><p class="bea-rc-muted">Chargement…</p></section>
      } @else {
        <nav class="bea-ct-tabs" aria-label="Paramètres">
          @if (store.cap('referentiels_voir')) {
            <button type="button" [class.is-on]="onglet() === 'referentiels'" (click)="choisir('referentiels')"><mat-icon>category</mat-icon> Référentiels</button>
          }
          @if (store.cap('referentiels_voir')) {
            <button type="button" [class.is-on]="onglet() === 'regles'" (click)="choisir('regles')"><mat-icon>rule</mat-icon> Règles par motif & devises</button>
          }
          @if (voirUnites()) {
            <button type="button" [class.is-on]="onglet() === 'unites'" (click)="choisir('unites')"><mat-icon>account_tree</mat-icon> Unités & membres</button>
          }
        </nav>

        @if (onglet() === 'regles' && store.cap('referentiels_voir')) {
          @if (regles(); as rg) {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Devises proposées</h2></div>
              <div class="bea-rc-form">
                <p class="bea-rc-hint">Codes ISO à 3 lettres. {{ deviseRef }} reste la devise de référence ; aucune conversion n’est faite : les totaux sont toujours présentés par devise.</p>
                @if (gererRefs()) {
                  <div class="bea-rc-row">
                    <label>Devises (séparées par des espaces ou des virgules)
                      <input [ngModel]="devisesSaisie()" (ngModelChange)="devisesSaisie.set($event)" name="devises" maxlength="200" placeholder="MRU USD EUR" />
                    </label>
                  </div>
                  <span class="bea-mg__actions">
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !devisesModifiees()" (click)="enregistrerDevises()"><mat-icon>save</mat-icon> Enregistrer les devises</button>
                  </span>
                } @else {
                  <p>@for (c of rg.devises; track c) { <span class="bea-ct-badge" data-tone="INFO">{{ c }}</span> }</p>
                }
              </div>
            </section>

            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Règles par motif</h2></div>
              <p class="bea-rc-hint bea-rc-pad">Champs exigés pour chaque opération, contrôle spécifique et pièces attendues. Une règle proposée s’applique déjà
                mais doit être validée par la Conformité ; toute modification la repasse en « proposée ». Sans règle personnalisée, la règle par défaut s’applique
                ({{ libellesChamps(rg.defaut.champs_requis) }}).</p>
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead><tr><th>Motif</th><th>Champs obligatoires</th><th>Contrôle</th><th>Pièces / régularisation</th><th>Validation</th>
                    @if (gererRefs() || validerRefs()) { <th></th> }</tr></thead>
                  <tbody>
                    @for (r of rg.items; track r.motif_id) {
                      <tr [class.bea-rc-muted]="!r.motif_actif">
                        <td><strong>{{ r.motif }}</strong>@if (r.motif_code) { <code>{{ r.motif_code }}</code> }<small class="bea-ct-sub">{{ r.type ?? '' }}</small></td>
                        <td>{{ libellesChamps(r.champs_requis) }}@if (r.operations_min) { <small class="bea-ct-sub">au moins {{ r.operations_min }} opération(s)</small> }</td>
                        <td>{{ libelleControle(r.controle) }}@if (r.nature_attendue) { <small class="bea-ct-sub">nature attendue : {{ r.nature_attendue === 'DEBIT' ? 'débit' : 'crédit' }}</small> }</td>
                        <td>{{ r.justificatif_requis ? 'Justificatif exigé' : '—' }}@if (r.regularisation) { <small class="bea-ct-sub">Régularisation à confirmer si favorable</small> }</td>
                        <td>
                          @if (!r.personnalisee) { <span class="bea-ct-badge" data-tone="SUSPENDU">Règle par défaut</span> }
                          @else { <span class="bea-ct-badge" [attr.data-tone]="r.statut_validation === 'VALIDEE' ? 'ACTIF' : 'ATTENTION'">{{ r.statut_validation === 'VALIDEE' ? 'Validée' : 'Proposée' }}</span> }
                          @if (r.valide_le) { <small class="bea-ct-sub">{{ dateFr(r.valide_le) }}</small> }
                        </td>
                        @if (gererRefs() || validerRefs()) {
                          <td class="bea-rc-refs__act"><span class="bea-rc-refs__btns">
                            @if (gererRefs()) {
                              <button type="button" class="bea-mg__icon-btn" title="Modifier la règle" (click)="editerRegle(r)"><mat-icon>edit</mat-icon></button>
                            }
                            @if (validerRefs() && r.personnalisee) {
                              @if (r.statut_validation !== 'VALIDEE') {
                                <button type="button" class="bea-mg__icon-btn" title="Valider (Conformité)" [disabled]="busy()" (click)="validerRegle(r, 'VALIDEE')"><mat-icon>verified</mat-icon></button>
                              } @else {
                                <button type="button" class="bea-mg__icon-btn" title="Repasser en « proposée »" [disabled]="busy()" (click)="validerRegle(r, 'PROPOSEE')"><mat-icon>undo</mat-icon></button>
                              }
                            }
                          </span></td>
                        }
                      </tr>
                    } @empty {
                      <tr><td colspan="6"><div class="bea-ct-empty"><mat-icon>rule</mat-icon><p>Aucun motif : créez d’abord les types et motifs dans l’onglet Référentiels.</p></div></td></tr>
                    }
                  </tbody>
                </table>
              </div>
            </section>
          } @else if (reglesErreur()) {
            <section class="bea-mg__panel bea-rc-pad"><div class="bea-ct-empty"><mat-icon>cloud_off</mat-icon><p>Règles indisponibles.</p>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="chargerRegles()"><mat-icon>refresh</mat-icon> Réessayer</button></div></section>
          } @else {
            <section class="bea-mg__panel bea-rc-pad"><p class="bea-rc-muted">Chargement des règles…</p></section>
          }
        }

        @if (onglet() === 'referentiels' && store.cap('referentiels_voir')) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <div class="bea-ct-tabs">
                <button type="button" [class.is-on]="vue() === 'CLASSEMENT'" (click)="vue.set('CLASSEMENT')">Types, motifs et sous-motifs</button>
                <button type="button" [class.is-on]="vue() === 'CANAL'" (click)="vue.set('CANAL')">Canaux de réception</button>
                <button type="button" [class.is-on]="vue() === 'CANAL_REPONSE'" (click)="vue.set('CANAL_REPONSE')">Canaux de réponse</button>
              </div>
              @if (gererRefs()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouveauRef(domaineRacine(), null)">
                  <mat-icon>add</mat-icon> {{ vue() === 'CLASSEMENT' ? 'Nouveau type' : 'Nouveau canal' }}
                </button>
              }
            </div>
            <div class="bea-rc-filtres-ref">
              <label class="bea-mg__field">
                <span>Rechercher</span>
                <input type="search" [ngModel]="filtreRef()" (ngModelChange)="filtreRef.set($event)" placeholder="Libellé ou code (ex. T21)" />
              </label>
              <label class="bea-rc-toggle">
                <input type="checkbox" [ngModel]="voirInactifs()" (ngModelChange)="voirInactifs.set($event)" />
                Afficher les éléments désactivés ({{ nbInactifs() }})
              </label>
            </div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table bea-rc-refs">
                <thead><tr><th class="bea-rc-refs__lib">Libellé</th><th class="bea-rc-refs__code">Code</th><th class="bea-rc-refs__niv">Niveau</th>
                  <th class="bea-rc-refs__num" title="Dossiers et éléments rattachés">Utilisations</th><th class="bea-rc-refs__etat">État</th>
                  @if (vue() === 'CLASSEMENT') { <th class="bea-rc-refs__val" title="Valeur proposée ou validée par la Conformité">Validation</th> }
                  @if (gererRefs() || validerRefs()) { <th class="bea-rc-refs__act"></th> }</tr></thead>
                <tbody>
                  @for (l of lignesRef(); track l.item.id) {
                    <tr>
                      <td class="bea-rc-refs__lib" [style.padding-left.rem]="0.75 + l.niveau * 1.5">
                        @if (l.niveau) { <span class="bea-rc-muted">└ </span> }
                        <span [class.bea-rc-muted]="!l.item.actif" [class.bea-rc-refs__type]="!l.niveau">{{ l.item.libelle }}</span>
                        @if (l.item.description) { <br /><small class="bea-rc-hint">{{ l.item.description }}</small> }
                      </td>
                      <td class="bea-rc-refs__code"><code>{{ l.item.code ?? '' }}</code></td>
                      <td class="bea-rc-refs__niv">{{ libelleDomaine(l.item.domaine) }}</td>
                      <td class="bea-rc-refs__num">{{ l.item.usage }}</td>
                      <td class="bea-rc-refs__etat">
                        @if (l.item.actif && !store.utilisable(l.item)) {
                          <span class="bea-ct-badge" data-tone="SUSPENDU" title="Le type ou le motif parent est désactivé">Masqué (parent inactif)</span>
                        } @else {
                          <span class="bea-ct-badge" [attr.data-tone]="l.item.actif ? 'ACTIF' : 'SUSPENDU'">{{ l.item.actif ? 'Actif' : 'Inactif' }}</span>
                        }
                      </td>
                      @if (vue() === 'CLASSEMENT') {
                        <td class="bea-rc-refs__val">
                          @if (l.item.a_valider) {
                            <span class="bea-ct-badge" [attr.data-tone]="l.item.statut_validation === 'VALIDEE' ? 'ACTIF' : 'ATTENTION'"
                                  [title]="l.item.statut_validation_libelle">{{ l.item.statut_validation === 'VALIDEE' ? 'Validée' : 'À valider' }}</span>
                            @if (l.item.valide_le) { <small class="bea-ct-sub">{{ dateFr(l.item.valide_le) }}</small> }
                          }
                        </td>
                      }
                      @if (gererRefs() || validerRefs()) {
                        <td class="bea-rc-refs__act"><span class="bea-rc-refs__btns">
                          @if (validerRefs() && l.item.a_valider) {
                            @if (l.item.statut_validation !== 'VALIDEE') {
                              <button type="button" class="bea-mg__icon-btn" title="Valider (Conformité)" [disabled]="busy()" (click)="validerRef(l.item, 'VALIDEE')"><mat-icon>verified</mat-icon></button>
                            } @else {
                              <button type="button" class="bea-mg__icon-btn" title="Repasser en « proposé »" [disabled]="busy()" (click)="validerRef(l.item, 'PROPOSEE')"><mat-icon>undo</mat-icon></button>
                            }
                          }
                          @if (gererRefs()) {
                          @if (enfant(l.item.domaine) && l.item.actif) {
                            <button type="button" class="bea-mg__icon-btn" [title]="'Ajouter un ' + (l.item.domaine === 'TYPE' ? 'motif' : 'sous-motif')" (click)="nouveauRef(enfant(l.item.domaine)!, l.item)"><mat-icon>add</mat-icon></button>
                          }
                          <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editerRef(l.item)"><mat-icon>edit</mat-icon></button>
                          <button type="button" class="bea-mg__icon-btn" [title]="l.item.actif ? 'Désactiver' : 'Réactiver'" [disabled]="busy()" (click)="basculerRef(l.item)">
                            <mat-icon>{{ l.item.actif ? 'toggle_on' : 'toggle_off' }}</mat-icon>
                          </button>
                          <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" [disabled]="busy()" (click)="supprimerRef(l.item)"><mat-icon>delete</mat-icon></button>
                          }
                        </span></td>
                      }
                    </tr>
                  } @empty {
                    <tr><td colspan="7">
                      <div class="bea-ct-empty"><mat-icon>category</mat-icon>
                        <p>{{ filtreRef() ? 'Aucun élément ne correspond à la recherche.' : vue() === 'CLASSEMENT' ? 'Aucun type de réclamation. Créez la nomenclature validée par la banque.' : 'Aucun canal.' }}</p>
                      </div>
                    </td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @if (onglet() === 'unites' && voirUnites()) {
          <div class="bea-rc-split">
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top">
                <h2>Organisation</h2>
                @if (gererUnites()) {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="nouvelleUnite(null)"><mat-icon>add</mat-icon> Unité</button>
                }
              </div>
              <ul class="bea-rc-tree">
                @for (n of arbre(); track n.unite.id) {
                  <li>
                    <button type="button" [class.is-on]="selection()?.id === n.unite.id" [class.is-off]="!n.unite.actif"
                            [style.padding-left.rem]="0.55 + n.niveau * 1.1" (click)="selectionner(n.unite)">
                      <mat-icon>{{ icone(n.unite.type_unite) }}</mat-icon>
                      <span>{{ n.unite.libelle }}</span>
                      @if (n.unite.est_service_reclamations) { <span class="bea-ct-badge" data-tone="ACTIF">SR</span> }
                      <small>{{ n.unite.nb_membres }}</small>
                    </button>
                  </li>
                } @empty {
                  <li class="bea-rc-pad bea-rc-muted">Aucune unité.</li>
                }
              </ul>
            </section>

            <div>
              @if (brouillonUnite(); as u) {
                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top"><h2>{{ u.id ? 'Modifier l’unité' : 'Nouvelle unité' }}</h2></div>
                  <form class="bea-rc-form" (ngSubmit)="enregistrerUnite()">
                    <div class="bea-rc-row">
                      <label>Type <em>*</em>
                        <select [(ngModel)]="u.type_unite" name="type_unite">
                          @for (t of store.libelles('types_unite'); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
                        </select>
                      </label>
                      <label>Libellé <em>*</em><input [(ngModel)]="u.libelle" name="libelle" maxlength="200" required /></label>
                      <label>Code <input [(ngModel)]="u.code" name="code" maxlength="40" /></label>
                    </div>
                    <div class="bea-rc-row">
                      <label>Rattachée à
                        <select [(ngModel)]="u.parent_id" name="parent_id">
                          <option value="">— Aucune (niveau racine) —</option>
                          @for (p of parentsPossibles(); track p.id) { <option [value]="p.id">{{ p.libelle }} ({{ p.type_libelle }})</option> }
                        </select>
                      </label>
                      <label>Agence ORION
                        <select [(ngModel)]="u.agence_id" name="agence_id">
                          <option value="">—</option>
                          @for (a of store.config()!.agences; track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
                        </select>
                      </label>
                      <label>E-mail de l’unité <input type="email" [(ngModel)]="u.email" name="email" maxlength="255" /></label>
                    </div>
                    @if (u.type_unite !== 'AGENCE') {
                      <div class="bea-rc-row">
                        <label>Entité de l’organigramme BEA
                          <bea-org-entite-select [(ngModel)]="u.org_entite_id" name="org_entite_id" placeholder="— Non rattachée —" />
                        </label>
                      </div>
                    }
                    <div class="bea-rc-row">
                      <label>Description <textarea [(ngModel)]="u.description" name="description" rows="2" maxlength="2000"></textarea></label>
                      @if (u.id) { <label>Ordre d’affichage <input type="number" min="0" [(ngModel)]="u.ordre" name="ordre" /></label> }
                    </div>
                    <div class="bea-mg__actions">
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="annulerUnite()">Annuler</button>
                      <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer</button>
                    </div>
                  </form>
                </section>
              } @else if (selection(); as u) {
                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top">
                    <h2>{{ u.libelle }}</h2>
                    @if (gererUnites()) {
                      <span class="bea-mg__actions">
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="nouvelleUnite(u)"><mat-icon>subdirectory_arrow_right</mat-icon> Sous-unité</button>
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="editerUnite(u)"><mat-icon>edit</mat-icon> Modifier</button>
                        @if (!u.est_service_reclamations) {
                          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="basculerUnite(u)">
                            <mat-icon>{{ u.actif ? 'toggle_on' : 'toggle_off' }}</mat-icon> {{ u.actif ? 'Désactiver' : 'Réactiver' }}
                          </button>
                        }
                      </span>
                    }
                  </div>
                  <dl class="bea-rc-dl">
                    <dt>Type</dt><dd>{{ u.type_libelle }}</dd>
                    <dt>Code</dt><dd>{{ u.code ?? '—' }}</dd>
                    <dt>Rattachée à</dt><dd>{{ libelleUnite(u.parent_id) }}</dd>
                    <dt>Agence ORION</dt><dd>{{ u.agence ?? '—' }}</dd>
                    @if (u.type_unite !== 'AGENCE') { <dt>Organigramme BEA</dt><dd>{{ u.org_entite ?? 'Non rattachée' }}</dd> }
                    <dt>E-mail</dt><dd>{{ u.email ?? '—' }}</dd>
                    <dt>Dossiers liés</dt><dd>{{ u.nb_dossiers }}</dd>
                    <dt>État</dt><dd><span class="bea-ct-badge" [attr.data-tone]="u.actif ? 'ACTIF' : 'SUSPENDU'">{{ u.actif ? 'Active' : 'Inactive' }}</span>
                      @if (u.est_service_reclamations) { <span class="bea-ct-badge" data-tone="INFO">Service Réclamations central</span> }</dd>
                  </dl>
                </section>

                <section class="bea-mg__panel">
                  <div class="bea-mg__panel-top"><h2>Membres</h2></div>
                  @if (gererUnites() && u.actif) {
                    <div class="bea-rc-form">
                      <div class="bea-rc-row">
                        <label>Ajouter un utilisateur
                          <input [ngModel]="recherche()" (ngModelChange)="chercher($event)" name="recherche" placeholder="Nom ou e-mail (2 caractères min.)" autocomplete="off" />
                        </label>
                        <label>Rôle dans l’unité
                          <select [(ngModel)]="roleAjout" name="roleAjout">
                            <option value="AGENT">Agent</option>
                            <option value="RESPONSABLE">Responsable</option>
                          </select>
                        </label>
                      </div>
                      @if (trouves().length) {
                        <ul class="bea-rc-tree">
                          @for (t of trouves(); track t.id) {
                            <li>
                              <button type="button" [disabled]="busy()" (click)="ajouterMembre(u, t)">
                                <mat-icon>person_add</mat-icon>
                                <span>{{ t.nom }} <span class="bea-rc-hint">{{ t.email }}</span></span>
                                @if (!t.acces_module) { <small title="Sans profil Réclamations : il ne verra le module qu’après attribution d’un profil">sans accès au module</small> }
                              </button>
                            </li>
                          }
                        </ul>
                      }
                    </div>
                  }
                  @if (membres(); as liste) {
                    <div class="bea-mg__table-wrap">
                      <table class="bea-mg__table">
                        <thead><tr><th>Utilisateur</th><th>Rôle</th><th>Depuis</th><th>État</th>@if (gererUnites()) { <th></th> }</tr></thead>
                        <tbody>
                          @for (m of liste; track m.id) {
                            <tr>
                              <td>{{ m.nom }}<br /><small class="bea-rc-hint">{{ m.email }}{{ m.compte_actif ? '' : ' · compte désactivé' }}</small></td>
                              <td>
                                @if (gererUnites() && m.actif) {
                                  <select class="bea-rc-input" [ngModel]="m.role_membre" (ngModelChange)="changerRole(u, m, $event)" [name]="'role-' + m.id" [disabled]="busy()">
                                    <option value="AGENT">Agent</option>
                                    <option value="RESPONSABLE">Responsable</option>
                                  </select>
                                } @else {
                                  {{ m.role_membre === 'RESPONSABLE' ? 'Responsable' : 'Agent' }}
                                }
                              </td>
                              <td>{{ date(m.depuis) }}</td>
                              <td><span class="bea-ct-badge" [attr.data-tone]="m.actif ? 'ACTIF' : 'SUSPENDU'">{{ m.actif ? 'Actif' : 'Retiré' }}</span></td>
                              @if (gererUnites()) {
                                <td class="bea-mg__row-actions">
                                  <button type="button" class="bea-mg__icon-btn" [class.bea-mg__icon-btn--danger]="m.actif" [title]="m.actif ? 'Retirer de l’unité' : 'Réintégrer'" [disabled]="busy()" (click)="basculerMembre(u, m)">
                                    <mat-icon>{{ m.actif ? 'person_remove' : 'person_add' }}</mat-icon>
                                  </button>
                                </td>
                              }
                            </tr>
                          } @empty {
                            <tr><td colspan="5" class="bea-rc-muted">Aucun membre. Les agents doivent être rattachés à une unité pour enregistrer des réclamations.</td></tr>
                          }
                        </tbody>
                      </table>
                    </div>
                  } @else {
                    <p class="bea-rc-pad bea-rc-muted">Chargement des membres…</p>
                  }
                </section>
              } @else {
                <section class="bea-mg__panel bea-rc-pad"><p class="bea-rc-muted">Sélectionnez une unité pour voir sa fiche et ses membres.</p></section>
              }
            </div>
          </div>
        }

        @if (!store.cap('referentiels_voir') && !voirUnites()) {
          <section class="bea-mg__panel bea-rc-pad"><p class="bea-rc-muted">Vous n’avez accès à aucun paramètre du module.</p></section>
        }
      }

      @if (brouillonRef(); as r) {
        <div class="bea-mg__backdrop" (click)="fermerRef()"></div>
        <form class="bea-mg__modal" role="dialog" aria-modal="true" (ngSubmit)="enregistrerRef()">
          <div class="bea-mg__modal-head">
            <h2>{{ r.id ? 'Modifier' : 'Nouveau' }} — {{ libelleDomaine(r.domaine) }}</h2>
            <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerRef()"><mat-icon>close</mat-icon></button>
          </div>
          <div class="bea-rc-form">
            @if (r.parent) { <p class="bea-rc-hint">Rattaché à : <strong>{{ r.parent.libelle }}</strong></p> }
            <label>Libellé <em>*</em><input [(ngModel)]="r.libelle" name="libelle" maxlength="200" required /></label>
            <div class="bea-rc-row">
              <label>Code <input [(ngModel)]="r.code" name="code" maxlength="40" placeholder="Facultatif, ex. MONETIQUE" /></label>
              @if (r.id) { <label>Ordre d’affichage <input type="number" min="0" [(ngModel)]="r.ordre" name="ordre" /></label> }
            </div>
            <label>Description <textarea [(ngModel)]="r.description" name="description" rows="2" maxlength="2000"></textarea></label>
          </div>
          <div class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerRef()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer</button>
          </div>
        </form>
      }

      @if (brouillonRegle(); as b) {
        <div class="bea-mg__backdrop" (click)="fermerRegle()"></div>
        <form class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" (ngSubmit)="enregistrerRegle()">
          <div class="bea-mg__modal-head">
            <h2>Règle du motif — {{ b.motif }}</h2>
            <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerRegle()"><mat-icon>close</mat-icon></button>
          </div>
          <div class="bea-rc-form">
            <p class="bea-rc-hint">Champs obligatoires pour chaque opération (saisie manuelle et import Excel) :</p>
            <div class="bea-rc-row bea-rc-regle__champs">
              @for (c of regles()?.champs ?? []; track c.code) {
                <label class="bea-rc-toggle"><input type="checkbox" [checked]="b.champs_requis.includes($any(c.code))" (change)="basculerChamp(c.code)" /> {{ c.libelle }}</label>
              }
            </div>
            <div class="bea-rc-row">
              <label>Contrôle spécifique
                <select [(ngModel)]="b.controle" name="controle">
                  <option [ngValue]="null">Aucun</option>
                  @for (c of regles()?.controles ?? []; track c.code) { <option [ngValue]="c.code">{{ c.libelle }}</option> }
                </select>
              </label>
              <label>Nature attendue
                <select [(ngModel)]="b.nature_attendue" name="nature_attendue">
                  <option [ngValue]="null">Indifférente</option>
                  <option ngValue="DEBIT">Débit</option>
                  <option ngValue="CREDIT">Crédit</option>
                </select>
              </label>
              <label>Opérations minimum
                <input type="number" min="0" max="500" [(ngModel)]="b.operations_min" name="operations_min" />
              </label>
            </div>
            <div class="bea-rc-row">
              <label class="bea-rc-toggle"><input type="checkbox" [(ngModel)]="b.justificatif_requis" name="justificatif_requis" /> Justificatif exigé avant transmission</label>
              <label class="bea-rc-toggle"><input type="checkbox" [(ngModel)]="b.regularisation" name="regularisation" /> Décision favorable = régularisation à confirmer (extourne, correction)</label>
            </div>
            <label>Consigne aux agents
              <textarea [(ngModel)]="b.consigne" name="consigne" rows="2" maxlength="2000" placeholder="Facultatif — affichée à la saisie"></textarea>
            </label>
            <div class="bea-rc-note bea-rc-note--warn"><mat-icon>info</mat-icon><span>L’enregistrement repasse la règle en « proposée » : elle s’applique aux nouvelles saisies et attend la validation de la Conformité.</span></div>
          </div>
          <div class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerRegle()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer la règle</button>
          </div>
        </form>
      }
    </section>
  `,
})
export class RcParametresComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly store = inject(ReclamationsStore);

  readonly onglet = signal<Onglet>('referentiels');
  readonly vue = signal<Vue>('CLASSEMENT');
  readonly busy = signal(false);
  readonly brouillonRef = signal<BrouillonRef | null>(null);
  readonly brouillonUnite = signal<BrouillonUnite | null>(null);
  readonly selectionId = signal<string | null>(null);
  readonly membres = signal<Membre[] | null>(null);
  readonly recherche = signal('');
  readonly trouves = signal<UtilisateurTrouve[]>([]);
  roleAjout: 'AGENT' | 'RESPONSABLE' = 'AGENT';
  private initialRef = '';
  private initialUnite = '';
  private initialRegle = '';
  readonly deviseRef = DEVISE_REFERENCE;
  readonly regles = signal<Regles | null>(null);
  readonly reglesErreur = signal(false);
  readonly brouillonRegle = signal<BrouillonRegle | null>(null);
  readonly devisesSaisie = signal('');
  readonly devisesModifiees = computed(() => this.parserDevises(this.devisesSaisie()).join(' ') !== (this.regles()?.devises ?? []).join(' '));
  private readonly saisie$ = new Subject<string>();

  readonly gererRefs = computed(() => this.store.cap('referentiels_gerer'));
  readonly validerRefs = computed(() => this.store.cap('referentiels_valider'));
  readonly dateFr = dateFr;
  readonly gererUnites = computed(() => this.store.cap('unites_gerer'));
  readonly voirUnites = computed(() => this.store.cap('unites_gerer') || this.store.cap('tout_voir'));
  readonly domaineRacine = computed<Domaine>(() => {
    const v = this.vue();
    return v === 'CLASSEMENT' ? 'TYPE' : v;
  });
  readonly selection = computed(() => this.store.unites().find((u) => u.id === this.selectionId()) ?? null);

  readonly filtreRef = signal('');
  readonly voirInactifs = signal(false);

  private readonly arbreRef = computed<Array<LigneRef & { lignee: string[] }>>(() => {
    const vue = this.vue();
    if (vue !== 'CLASSEMENT') return this.store.refs(vue, true).map((item) => ({ item, niveau: 0, lignee: [] }));
    const motifs = this.store.refs('MOTIF', true);
    const sous = this.store.refs('SOUS_MOTIF', true);
    const lignes: Array<LigneRef & { lignee: string[] }> = [];
    for (const t of this.store.refs('TYPE', true)) {
      lignes.push({ item: t, niveau: 0, lignee: [] });
      for (const m of motifs.filter((x) => x.parent_id === t.id)) {
        lignes.push({ item: m, niveau: 1, lignee: [t.id] });
        for (const s of sous.filter((x) => x.parent_id === m.id)) lignes.push({ item: s, niveau: 2, lignee: [t.id, m.id] });
      }
    }
    return lignes;
  });

  readonly nbInactifs = computed(() => this.arbreRef().filter((l) => !this.store.utilisable(l.item)).length);

  /** Filtre texte : une valeur trouvée s'affiche avec ses parents et ses enfants. */
  readonly lignesRef = computed<LigneRef[]>(() => {
    const voirInactifs = this.voirInactifs();
    const visibles = this.arbreRef().filter((l) => voirInactifs || this.store.utilisable(l.item));
    const q = normaliser(this.filtreRef());
    if (!q) return visibles;
    const trouves = new Set(visibles.filter((l) => normaliser(`${l.item.libelle} ${l.item.code ?? ''}`).includes(q)).map((l) => l.item.id));
    const parents = new Set(visibles.filter((l) => trouves.has(l.item.id)).flatMap((l) => l.lignee));
    return visibles.filter((l) => trouves.has(l.item.id) || parents.has(l.item.id) || l.lignee.some((id) => trouves.has(id)));
  });

  descendants(r: RefItem): RefItem[] {
    return this.arbreRef().filter((l) => l.lignee.includes(r.id)).map((l) => l.item);
  }

  readonly arbre = computed<NoeudUnite[]>(() => {
    const unites = this.store.unites();
    const ids = new Set(unites.map((u) => u.id));
    const enfants = new Map<string | null, Unite[]>();
    for (const u of unites) {
      const p = u.parent_id && ids.has(u.parent_id) ? u.parent_id : null;
      enfants.set(p, [...(enfants.get(p) ?? []), u]);
    }
    const resultat: NoeudUnite[] = [];
    const vus = new Set<string>();
    const parcourir = (parent: string | null, niveau: number) => {
      for (const u of enfants.get(parent) ?? []) {
        if (vus.has(u.id)) continue;
        vus.add(u.id);
        resultat.push({ unite: u, niveau });
        parcourir(u.id, niveau + 1);
      }
    };
    parcourir(null, 0);
    return resultat;
  });

  readonly parentsPossibles = computed(() => {
    const b = this.brouillonUnite();
    if (!b?.id) return this.store.unitesActives();
    const exclus = new Set<string>([b.id]);
    let ajout = true;
    while (ajout) {
      ajout = false;
      for (const u of this.store.unites()) {
        if (u.parent_id && exclus.has(u.parent_id) && !exclus.has(u.id)) {
          exclus.add(u.id);
          ajout = true;
        }
      }
    }
    return this.store.unitesActives().filter((u) => !exclus.has(u.id));
  });

  readonly hasUnsavedChanges = unsavedChanges(() => {
    if (this.busy()) return false;
    const r = this.brouillonRef();
    const u = this.brouillonUnite();
    const g = this.brouillonRegle();
    return (!!r && JSON.stringify(r) !== this.initialRef) || (!!u && JSON.stringify(u) !== this.initialUnite)
      || (!!g && JSON.stringify(g) !== this.initialRegle) || (this.onglet() === 'regles' && this.devisesModifiees());
  });

  ngOnInit(): void {
    this.store.charger();
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((q) => {
      const o = q.get('onglet');
      this.onglet.set(o === 'unites' ? 'unites' : o === 'regles' ? 'regles' : 'referentiels');
      if (o === 'regles' && !this.regles()) this.chargerRegles();
    });
    this.saisie$
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((q): Observable<UtilisateurTrouve[]> => (q.trim().length >= 2 ? this.rc.utilisateurs(q.trim()) : of([]))),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (l) => this.trouves.set(l),
        error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Recherche impossible')),
      });
  }

  choisir(o: Onglet): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { onglet: o === 'referentiels' ? null : o }, replaceUrl: true });
    if (o === 'regles' && !this.regles()) this.chargerRegles();
  }

  libelleDomaine(d: Domaine): string {
    return this.store.libelles('domaines').find((x) => x.code === d)?.libelle ?? d;
  }

  enfant(d: Domaine): Domaine | undefined {
    return ENFANT[d];
  }

  icone(t: TypeUnite): string {
    return ICONES_UNITE[t] ?? 'groups';
  }

  date(iso: string | null): string {
    return dateFr(iso);
  }

  libelleUnite(id: string | null): string {
    if (!id) return '—';
    return this.store.unites().find((u) => u.id === id)?.libelle ?? '—';
  }

  private rafraichir(): void {
    this.store.recharger$().subscribe({
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Actualisation impossible')),
    });
  }

  // ------------------------------------------------------------ référentiels
  nouveauRef(domaine: Domaine, parent: RefItem | null): void {
    this.ouvrirRef({ id: null, domaine, parent, libelle: '', code: '', description: '', ordre: 0 });
  }

  editerRef(r: RefItem): void {
    const parent = r.parent_id ? [...this.store.refs('TYPE', true), ...this.store.refs('MOTIF', true)].find((x) => x.id === r.parent_id) ?? null : null;
    this.ouvrirRef({ id: r.id, domaine: r.domaine, parent, libelle: r.libelle, code: r.code ?? '', description: r.description ?? '', ordre: r.ordre });
  }

  private ouvrirRef(b: BrouillonRef): void {
    this.initialRef = JSON.stringify(b);
    this.brouillonRef.set(b);
  }

  fermerRef(): void {
    this.brouillonRef.set(null);
  }

  enregistrerRef(): void {
    const r = this.brouillonRef();
    if (!r) return;
    if (!r.libelle.trim()) {
      this.feedback.warning({ title: 'Libellé obligatoire', message: 'Saisissez le libellé.' });
      return;
    }
    const commun = { libelle: r.libelle.trim(), code: r.code.trim() || null, description: r.description.trim() || null };
    const appel = r.id
      ? this.rc.modifierReferentiel(r.id, { ...commun, ordre: r.ordre })
      : this.rc.creerReferentiel({ ...commun, domaine: r.domaine, parent_id: r.parent?.id ?? null });
    this.feedback
      .run(() => appel, {
        busy: this.busy,
        loading: 'Enregistrement…',
        success: (x) => ({ title: r.id ? 'Élément modifié' : 'Élément créé', details: [{ label: this.libelleDomaine(x.domaine), value: x.libelle }] }),
        errorTitle: 'Enregistrement refusé',
        errorHint: 'Vos saisies ont été conservées.',
        retry: false,
      })
      .subscribe(() => {
        this.brouillonRef.set(null);
        this.rafraichir();
      });
  }

  basculerRef(r: RefItem): void {
    const actif = !r.actif;
    this.feedback
      .run(() => this.rc.modifierReferentiel(r.id, { actif }), {
        confirm: actif ? undefined : {
          title: 'Désactiver l’élément',
          message: `« ${r.libelle} » ne sera plus proposé à la saisie${this.descendants(r).length ? ', ni ses motifs et sous-motifs' : ''}. Les dossiers existants le conservent.`,
          confirmLabel: 'Désactiver',
          tone: 'warn',
        },
        busy: this.busy,
        success: () => ({ title: actif ? 'Élément réactivé' : 'Élément désactivé', details: [{ label: 'Libellé', value: r.libelle }] }),
        errorTitle: 'Action refusée',
        retry: false,
      })
      .subscribe(() => this.rafraichir());
  }

  validerRef(r: RefItem, statut: 'VALIDEE' | 'PROPOSEE'): void {
    this.feedback
      .run(() => this.rc.validerReferentiel(r.id, statut), {
        confirm: {
          title: statut === 'VALIDEE' ? 'Valider la valeur' : 'Repasser en « proposé »',
          message: statut === 'VALIDEE'
            ? `« ${r.libelle} » sera marqué comme validé par la Conformité. Le parent doit déjà être validé.`
            : `« ${r.libelle} » redeviendra une valeur proposée, en attente de validation. Les dossiers existants la conservent.`,
          confirmLabel: statut === 'VALIDEE' ? 'Valider' : 'Repasser en proposé',
          tone: statut === 'VALIDEE' ? 'success' : 'warn',
        },
        busy: this.busy,
        success: () => ({ title: statut === 'VALIDEE' ? 'Valeur validée' : 'Valeur repassée en proposé', details: [{ label: 'Libellé', value: r.libelle }] }),
        errorTitle: 'Validation refusée',
        retry: false,
      })
      .subscribe(() => this.rafraichir());
  }

  supprimerRef(r: RefItem): void {
    const n = this.descendants(r).length;
    const cascade = n ? ` Ses ${n} élément(s) rattaché(s) (motifs, sous-motifs) seront supprimés avec lui.` : '';
    const historique = r.usage
      ? ' Les éléments déjà portés par des dossiers ne sont que masqués : les dossiers existants conservent leur libellé.'
      : '';
    this.feedback
      .run(() => this.rc.supprimerReferentiel(r.id), {
        confirm: {
          action: 'suppression',
          message: `Supprimer « ${r.libelle} » ? Il ne sera plus proposé dans aucune liste.${cascade}${historique}`,
        },
        busy: this.busy,
        success: (x) => ({
          title: 'Élément supprimé',
          details: [
            { label: 'Libellé', value: r.libelle },
            ...(x.supprimes ? [{ label: 'Effacés définitivement', value: String(x.supprimes) }] : []),
            ...(x.conserves ? [{ label: 'Masqués (historique conservé)', value: String(x.conserves) }] : []),
          ],
        }),
        errorTitle: 'Suppression refusée',
        retry: false,
      })
      .subscribe(() => this.rafraichir());
  }

  // ------------------------------------------------------------ règles par motif & devises
  chargerRegles(): void {
    this.reglesErreur.set(false);
    this.rc.regles().subscribe({
      next: (r) => {
        this.regles.set(r);
        this.devisesSaisie.set(r.devises.join(' '));
      },
      error: (e) => {
        this.reglesErreur.set(true);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Règles indisponibles'));
      },
    });
  }

  libellesChamps(champs: string[]): string {
    const lib = new Map((this.regles()?.champs ?? []).map((c) => [c.code, c.libelle]));
    return champs.length ? champs.map((c) => lib.get(c) ?? c).join(', ') : 'aucun';
  }

  libelleControle(code: string | null): string {
    if (!code) return '—';
    return this.regles()?.controles.find((c) => c.code === code)?.libelle ?? code;
  }

  private parserDevises(texte: string): string[] {
    return [...new Set(texte.toUpperCase().split(/[\s,;]+/).filter(Boolean))];
  }

  enregistrerDevises(): void {
    const devises = this.parserDevises(this.devisesSaisie());
    const invalides = devises.filter((d) => !/^[A-Z]{3}$/.test(d));
    if (invalides.length) {
      this.feedback.warning({ title: 'Code devise invalide', message: `Codes ISO à 3 lettres attendus : ${invalides.join(', ')}.` });
      return;
    }
    if (!devises.includes(DEVISE_REFERENCE)) {
      this.feedback.warning({ title: 'Devise de référence obligatoire', message: `${DEVISE_REFERENCE} doit rester dans la liste.` });
      return;
    }
    this.feedback
      .run(() => this.rc.modifierDevises(devises), {
        busy: this.busy,
        loading: 'Enregistrement…',
        success: (l) => ({ title: 'Devises enregistrées', details: [{ label: 'Devises', value: l.join(' ') }] }),
        errorTitle: 'Enregistrement refusé',
        retry: false,
      })
      .subscribe(() => {
        this.chargerRegles();
        this.rafraichir();
      });
  }

  editerRegle(r: RegleMotif): void {
    const b: BrouillonRegle = {
      motif_id: r.motif_id, motif: r.motif, champs_requis: [...r.champs_requis], operations_min: r.operations_min,
      nature_attendue: r.nature_attendue, controle: r.controle, justificatif_requis: r.justificatif_requis,
      regularisation: r.regularisation, consigne: r.consigne ?? '',
    };
    this.initialRegle = JSON.stringify(b);
    this.brouillonRegle.set(b);
  }

  fermerRegle(): void {
    this.brouillonRegle.set(null);
  }

  basculerChamp(code: string): void {
    this.brouillonRegle.update((b) => {
      if (!b) return b;
      const c = code as ChampOperation;
      return { ...b, champs_requis: b.champs_requis.includes(c) ? b.champs_requis.filter((x) => x !== c) : [...b.champs_requis, c] };
    });
  }

  enregistrerRegle(): void {
    const b = this.brouillonRegle();
    if (!b) return;
    const corps: RegleContenu = {
      champs_requis: b.champs_requis, operations_min: Math.max(0, Number(b.operations_min) || 0),
      nature_attendue: b.nature_attendue, controle: b.controle, justificatif_requis: b.justificatif_requis,
      regularisation: b.regularisation, consigne: b.consigne?.trim() || null,
    };
    this.feedback
      .run(() => this.rc.enregistrerRegle(b.motif_id, corps), {
        busy: this.busy,
        loading: 'Enregistrement…',
        success: (r) => ({ title: 'Règle enregistrée', message: 'Elle est « proposée » jusqu’à la validation de la Conformité.',
          details: [{ label: 'Motif', value: r.motif }, { label: 'Champs obligatoires', value: this.libellesChamps(r.champs_requis) }] }),
        errorTitle: 'Enregistrement refusé',
        errorHint: 'Vos saisies ont été conservées.',
        retry: false,
      })
      .subscribe(() => {
        this.brouillonRegle.set(null);
        this.chargerRegles();
        this.rafraichir();
      });
  }

  validerRegle(r: RegleMotif, statut: 'VALIDEE' | 'PROPOSEE'): void {
    this.feedback
      .run(() => this.rc.validerRegle(r.motif_id, statut), {
        confirm: {
          title: statut === 'VALIDEE' ? 'Valider la règle' : 'Repasser en « proposée »',
          message: statut === 'VALIDEE'
            ? `La règle du motif « ${r.motif} » sera marquée comme validée par la Conformité.`
            : `La règle du motif « ${r.motif} » redeviendra proposée, en attente de validation.`,
          confirmLabel: statut === 'VALIDEE' ? 'Valider' : 'Repasser en proposée',
          tone: statut === 'VALIDEE' ? 'success' : 'warn',
        },
        busy: this.busy,
        success: () => ({ title: statut === 'VALIDEE' ? 'Règle validée' : 'Règle repassée en proposée', details: [{ label: 'Motif', value: r.motif }] }),
        errorTitle: 'Validation refusée',
        retry: false,
      })
      .subscribe(() => {
        this.chargerRegles();
        this.rafraichir();
      });
  }

  // ------------------------------------------------------------ unités
  selectionner(u: Unite): void {
    if (this.brouillonUnite()) return;
    this.selectionId.set(u.id);
    this.trouves.set([]);
    this.recherche.set('');
    this.chargerMembres(u.id);
  }

  private chargerMembres(id: string): void {
    this.membres.set(null);
    this.rc.membres(id).subscribe({
      next: (l) => {
        if (this.selectionId() === id) this.membres.set(l);
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Membres indisponibles')),
    });
  }

  nouvelleUnite(parent: Unite | null): void {
    const type: TypeUnite = parent?.type_unite === 'DIRECTION' ? 'DEPARTEMENT' : parent ? 'SERVICE' : 'DIRECTION';
    this.ouvrirUnite({
      id: null, type_unite: type, libelle: '', code: '', parent_id: parent?.id ?? '', agence_id: '', org_entite_id: null,
      email: '', description: '', ordre: 0,
    });
  }

  editerUnite(u: Unite): void {
    this.ouvrirUnite({
      id: u.id, type_unite: u.type_unite, libelle: u.libelle, code: u.code ?? '', parent_id: u.parent_id ?? '',
      agence_id: u.agence_id ?? '', org_entite_id: u.org_entite_id ?? null, email: u.email ?? '',
      description: u.description ?? '', ordre: u.ordre,
    });
  }

  private ouvrirUnite(b: BrouillonUnite): void {
    this.initialUnite = JSON.stringify(b);
    this.brouillonUnite.set(b);
  }

  annulerUnite(): void {
    this.brouillonUnite.set(null);
  }

  enregistrerUnite(): void {
    const u = this.brouillonUnite();
    if (!u) return;
    if (!u.libelle.trim()) {
      this.feedback.warning({ title: 'Libellé obligatoire', message: 'Saisissez le nom de l’unité.' });
      return;
    }
    const corps: Record<string, unknown> = {
      type_unite: u.type_unite, libelle: u.libelle.trim(), code: u.code.trim() || null,
      email: u.email.trim() || null, description: u.description.trim() || null,
    };
    if (u.id) {
      corps['ordre'] = u.ordre;
      if (u.parent_id) corps['parent_id'] = u.parent_id;
      else corps['detacher_parent'] = true;
      if (u.agence_id) corps['agence_id'] = u.agence_id;
      else corps['detacher_agence'] = true;
      if (u.org_entite_id && u.type_unite !== 'AGENCE') corps['org_entite_id'] = u.org_entite_id;
      else corps['detacher_org_entite'] = true;
    } else {
      corps['parent_id'] = u.parent_id || null;
      corps['agence_id'] = u.agence_id || null;
      corps['org_entite_id'] = u.type_unite !== 'AGENCE' ? u.org_entite_id || null : null;
    }
    const appel = u.id ? this.rc.modifierUnite(u.id, corps) : this.rc.creerUnite(corps);
    this.feedback
      .run(() => appel, {
        busy: this.busy,
        loading: 'Enregistrement…',
        success: (x) => ({ title: u.id ? 'Unité modifiée' : 'Unité créée', details: [{ label: x.type_libelle, value: x.libelle }] }),
        errorTitle: 'Enregistrement refusé',
        errorHint: 'Vos saisies ont été conservées.',
        retry: false,
      })
      .subscribe((x) => {
        this.brouillonUnite.set(null);
        this.selectionId.set(x.id);
        this.chargerMembres(x.id);
        this.rafraichir();
      });
  }

  basculerUnite(u: Unite): void {
    const actif = !u.actif;
    this.feedback
      .run(() => this.rc.modifierUnite(u.id, { actif }), {
        confirm: actif ? undefined : {
          title: 'Désactiver l’unité',
          message: `« ${u.libelle} » ne sera plus proposée (réception, affectation). Les dossiers existants la conservent.`,
          confirmLabel: 'Désactiver',
          tone: 'warn',
        },
        busy: this.busy,
        success: () => ({ title: actif ? 'Unité réactivée' : 'Unité désactivée', details: [{ label: 'Unité', value: u.libelle }] }),
        errorTitle: 'Action refusée',
        retry: false,
      })
      .subscribe(() => this.rafraichir());
  }

  // ------------------------------------------------------------ membres
  chercher(q: string): void {
    this.recherche.set(q);
    this.saisie$.next(q);
  }

  ajouterMembre(u: Unite, t: UtilisateurTrouve): void {
    const role = this.roleAjout;
    this.feedback
      .run(() => this.rc.ajouterMembre(u.id, t.id, role), {
        busy: this.busy,
        success: () => ({
          title: 'Membre ajouté',
          details: [{ label: 'Utilisateur', value: t.nom }, { label: 'Unité', value: u.libelle }],
          message: t.acces_module ? undefined : 'Cet utilisateur n’a pas encore de profil Réclamations : attribuez-le dans l’administration.',
        }),
        errorTitle: 'Ajout refusé',
        retry: false,
      })
      .subscribe((l) => {
        this.membres.set(l);
        this.recherche.set('');
        this.trouves.set([]);
        this.saisie$.next('');
        this.rafraichir();
      });
  }

  changerRole(u: Unite, m: Membre, role: 'AGENT' | 'RESPONSABLE'): void {
    if (role === m.role_membre) return;
    this.feedback
      .run(() => this.rc.modifierMembre(u.id, m.id, { role_membre: role }), {
        busy: this.busy,
        success: () => ({ title: 'Rôle modifié', details: [{ label: m.nom, value: role === 'RESPONSABLE' ? 'Responsable' : 'Agent' }] }),
        errorTitle: 'Modification refusée',
        retry: false,
        onError: () => this.chargerMembres(u.id),
      })
      .subscribe((l) => this.membres.set(l));
  }

  basculerMembre(u: Unite, m: Membre): void {
    const actif = !m.actif;
    this.feedback
      .run(() => this.rc.modifierMembre(u.id, m.id, { actif }), {
        confirm: actif ? undefined : {
          title: 'Retirer de l’unité',
          message: `${m.nom} ne fera plus partie de « ${u.libelle} » et perdra l’accès aux dossiers de cette unité.`,
          confirmLabel: 'Retirer',
          tone: 'warn',
        },
        busy: this.busy,
        success: () => ({ title: actif ? 'Membre réintégré' : 'Membre retiré', details: [{ label: 'Utilisateur', value: m.nom }] }),
        errorTitle: 'Action refusée',
        retry: false,
      })
      .subscribe((l) => {
        this.membres.set(l);
        this.rafraichir();
      });
  }
}
