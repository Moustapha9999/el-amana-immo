import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { OrgEntiteSelectComponent } from '../../core/org/org-entite-select.component';
import { ORG_TYPE_LIBELLES, OrgTypeEntite } from '../../core/org/org-referentiel.models';
import { OrgReferentielService } from '../../core/org/org-referentiel.service';
import { ApiService } from '../../core/services/api.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  ORG_ACTION_LIBELLES,
  OrgAgenceAdmin,
  OrgControles,
  OrgCorrespondanceResume,
  OrgCorrespondances,
  OrgCorrespondanceValeur,
  OrgEntiteAdmin,
  OrgFiche,
  OrgHistoriqueLigne,
  OrgPoste,
  orgErreur,
} from './core-admin-organigramme.models';

type Onglet = 'organigramme' | 'controles' | 'correspondances' | 'agences' | 'historique';

const BASE = '/plateforme/admin/organisation';
const TYPES = Object.keys(ORG_TYPE_LIBELLES) as OrgTypeEntite[];
/** Type proposé par défaut pour une sous-entité (modifiable : la profondeur reste libre). */
const TYPE_ENFANT: Partial<Record<OrgTypeEntite, OrgTypeEntite>> = {
  CONSEIL: 'COMITE',
  DIRECTION_GENERALE: 'DIRECTION',
  DIRECTION: 'DEPARTEMENT',
  DEPARTEMENT: 'SERVICE',
  SERVICE: 'SECTION',
  SECTION: 'CELLULE',
};
const TYPE_COURT: Record<OrgTypeEntite, string> = {
  CONSEIL: 'Conseil',
  COMITE: 'Comité',
  DIRECTION_GENERALE: 'DG',
  DIRECTION: 'Direction',
  DEPARTEMENT: 'Dépt',
  SERVICE: 'Service',
  SECTION: 'Section',
  CELLULE: 'Cellule',
};

@Component({
  selector: 'bea-core-admin-organigramme',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, ReactiveFormsModule, RouterLink, CoreAdminIconComponent, OrgEntiteSelectComponent],
  template: `
    <section class="bea-admin-dash bea-org">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Organigramme BEA</h1>
          <p>
            Référentiel organisationnel central (organigramme juillet 2024) partagé par tous les modules.
            Une entité désactivée reste dans l’historique : aucun dossier, document ni écriture n’est supprimé.
          </p>
        </div>
      </header>

      @if (controles(); as c) {
        <div class="bea-admin-kpis">
          @for (k of kpis(c); track k.label) {
            <button type="button" class="bea-admin-kpi bea-admin-kpi--link" [attr.data-tone]="k.tone" (click)="ouvrir(k.onglet)">
              <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="k.icon" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">{{ k.label }}</p>
                <p class="bea-admin-kpi__value">{{ k.value }}</p>
              </div>
            </button>
          }
        </div>
      }

      <nav class="bea-org-tabs" aria-label="Sections de l’organigramme">
        @for (t of onglets; track t.id) {
          <button type="button" class="bea-org-tab" [class.bea-org-tab--on]="onglet() === t.id" (click)="ouvrir(t.id)">
            <bea-admin-icon [name]="t.icon" /> {{ t.label }}
          </button>
        }
      </nav>

      @switch (onglet()) {
        @case ('organigramme') {
          <div class="bea-org-layout">
            <!-- Arbre -->
            <section class="bea-admin-panel bea-org-col bea-org-tree">
              <div class="bea-org-tree__tools">
                <input type="search" class="bea-org-input" [ngModel]="recherche()" (ngModelChange)="recherche.set($event)"
                       placeholder="Rechercher : libellé, sigle, code…" aria-label="Rechercher une entité" />
                <div class="bea-org-tree__row">
                  <label class="bea-org-check">
                    <input type="checkbox" [ngModel]="voirInactives()" (ngModelChange)="voirInactives.set($event)" />
                    Entités désactivées
                  </label>
                  <button type="button" class="bea-admin-btn bea-admin-btn--tiny" (click)="nouvelle(null)">
                    <bea-admin-icon name="add" /> Nouvelle entité
                  </button>
                </div>
                <p class="bea-org-muted">{{ arbreVisible().length }} entité(s)</p>
              </div>
              @if (chargement()) {
                <p class="bea-admin-dash__loading">Chargement de l’organigramme…</p>
              } @else if (!arbreVisible().length) {
                <p class="bea-admin-panel__empty">Aucune entité pour ce filtre.</p>
              } @else {
                <ul class="bea-org-tree__list bea-org-scroll" role="tree">
                  @for (e of arbreVisible(); track e.id) {
                    <li role="treeitem" [attr.aria-selected]="e.id === selectionId()">
                      <button
                        type="button"
                        class="bea-org-node"
                        [class.bea-org-node--on]="e.id === selectionId()"
                        [class.bea-org-node--off]="!e.actif"
                        [style.padding-left.rem]="0.5 + (recherche() ? 0 : e.profondeur * 1)"
                        (click)="selectionner(e.id)"
                      >
                        <span class="bea-org-type" [attr.data-type]="e.type_entite">{{ typeCourt(e.type_entite) }}</span>
                        <span class="bea-org-node__main">
                          <span class="bea-org-node__label">{{ e.libelle }}</span>
                          @if (recherche() && e.chemin) {
                            <span class="bea-org-node__path">{{ e.chemin }}</span>
                          }
                        </span>
                        <span class="bea-org-node__flags">
                          @if (e.a_confirmer) { <span class="bea-org-dot bea-org-dot--warn" title="À confirmer"></span> }
                          @if (!e.actif) { <span class="bea-org-dot bea-org-dot--off" title="Désactivée"></span> }
                          @if (e.nb_utilisateurs) { <span class="bea-org-count" title="Utilisateurs affectés">{{ e.nb_utilisateurs }}</span> }
                        </span>
                      </button>
                    </li>
                  }
                </ul>
                <p class="bea-org-legend">
                  <span><span class="bea-org-dot bea-org-dot--warn"></span> À confirmer</span>
                  <span><span class="bea-org-dot bea-org-dot--off"></span> Désactivée</span>
                  <span><span class="bea-org-count">n</span> Utilisateurs</span>
                </p>
              }
            </section>

            <!-- Fiche / formulaire -->
            <section class="bea-org-col bea-org-detail bea-org-scroll">
              @if (mode(); as m) {
                <form class="bea-admin-panel bea-org-card" [formGroup]="form" (ngSubmit)="enregistrer()">
                  <h2 class="bea-org-card__title">{{ m === 'creer' ? 'Nouvelle entité' : 'Modifier « ' + (fiche()?.entite?.libelle ?? '') + ' »' }}</h2>
                  <div class="bea-org-form">
                    <label class="bea-org-field">
                      <span>Type *</span>
                      <select class="bea-org-input" formControlName="type_entite">
                        @for (t of types; track t) { <option [value]="t">{{ typeLibelle(t) }}</option> }
                      </select>
                    </label>
                    <label class="bea-org-field">
                      <span>Sigle</span>
                      <input class="bea-org-input" type="text" formControlName="sigle" maxlength="40" />
                    </label>
                    <label class="bea-org-field bea-org-field--full">
                      <span>Libellé *</span>
                      <input class="bea-org-input" type="text" formControlName="libelle" maxlength="255" />
                    </label>
                    <label class="bea-org-field">
                      <span>Code {{ m === 'creer' ? '(auto si vide)' : '' }}</span>
                      <input class="bea-org-input" type="text" formControlName="code" maxlength="20" />
                    </label>
                    <label class="bea-org-field">
                      <span>Entité parente</span>
                      <bea-org-entite-select
                        formControlName="parent_id"
                        [entites]="entites()"
                        [exclure]="m === 'modifier' ? selectionId() : null"
                        placeholder="— Aucune (entité racine) —"
                      />
                    </label>
                    <label class="bea-org-field bea-org-field--full">
                      <span>Autres libellés reconnus (séparés par « ; »)</span>
                      <input class="bea-org-input" type="text" formControlName="alias" placeholder="ex. Département Informatique; DI" />
                    </label>
                    <label class="bea-org-field bea-org-field--full">
                      <span>Description</span>
                      <textarea class="bea-org-input" formControlName="description" rows="2"></textarea>
                    </label>
                    <label class="bea-org-check bea-org-field--full">
                      <input type="checkbox" formControlName="a_confirmer" /> Point à confirmer
                    </label>
                    @if (form.controls.a_confirmer.value) {
                      <label class="bea-org-field bea-org-field--full">
                        <span>Ce qui reste à confirmer</span>
                        <textarea class="bea-org-input" formControlName="note_confirmation" rows="2"></textarea>
                      </label>
                    }
                  </div>
                  <div class="bea-org-actions">
                    <button type="submit" class="bea-admin-btn" [disabled]="saving() || form.invalid">
                      {{ saving() ? 'Enregistrement…' : m === 'creer' ? 'Créer' : 'Enregistrer' }}
                    </button>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="annulerForm()">Annuler</button>
                  </div>
                </form>
              } @else if (fiche(); as f) {
                <!-- Identité -->
                <div class="bea-admin-panel bea-org-card">
                  @if (f.chemin.length > 1) {
                    <nav class="bea-org-crumbs" aria-label="Chemin">
                      @for (c of f.chemin; track c.id; let last = $last) {
                        @if (!last) {
                          <button type="button" class="bea-org-link" (click)="selectionner(c.id)">{{ c.libelle }}</button>
                          <span class="bea-org-sep">›</span>
                        }
                      }
                    </nav>
                  }
                  <div class="bea-org-head">
                    <h2 class="bea-org-card__title">
                      {{ f.entite.libelle }}
                      @if (f.entite.sigle) { <small>({{ f.entite.sigle }})</small> }
                    </h2>
                    <div class="bea-org-tags">
                      <span class="bea-org-type" [attr.data-type]="f.entite.type_entite">{{ f.entite.type_libelle }}</span>
                      <span class="bea-badge" [class.bea-badge--actif]="f.entite.actif" [class.bea-badge--inactif]="!f.entite.actif">
                        {{ f.entite.actif ? 'Active' : 'Désactivée' }}
                      </span>
                    </div>
                  </div>
                  <dl class="bea-org-dl">
                    <dt>Code</dt><dd><code>{{ f.entite.code }}</code></dd>
                    <dt>Source</dt><dd>{{ f.entite.source || '—' }}</dd>
                    <dt>Sous-entités</dt><dd>{{ f.entite.nb_enfants }}</dd>
                    <dt>Utilisateurs</dt><dd>{{ f.entite.nb_utilisateurs }}</dd>
                    @if (f.entite.alias.length) { <dt>Libellés reconnus</dt><dd>{{ f.entite.alias.join(' ; ') }}</dd> }
                    @if (f.entite.description) { <dt>Description</dt><dd>{{ f.entite.description }}</dd> }
                  </dl>
                  @if (f.entite.a_confirmer) {
                    <p class="bea-org-alert">
                      <bea-admin-icon name="help" />
                      <span><strong>À confirmer :</strong> {{ f.entite.note_confirmation || 'point non précisé.' }}</span>
                    </p>
                  }
                  <div class="bea-org-actions">
                    <button type="button" class="bea-admin-btn bea-admin-btn--tiny" (click)="modifier(f)"><bea-admin-icon name="edit" /> Modifier / déplacer</button>
                    @if (f.entite.actif) {
                      <button type="button" class="bea-admin-btn bea-admin-btn--tiny bea-admin-btn--ghost" (click)="nouvelle(f.entite)">
                        <bea-admin-icon name="add" /> Sous-entité
                      </button>
                    }
                    @if (f.entite.a_confirmer) {
                      <button type="button" class="bea-admin-btn bea-admin-btn--tiny bea-admin-btn--ghost" [disabled]="saving()" (click)="confirmerEntite(f)">
                        <bea-admin-icon name="check" /> Marquer confirmée
                      </button>
                    }
                    <span class="bea-org-spacer"></span>
                    @if (f.entite.actif) {
                      <button type="button" class="bea-admin-btn bea-admin-btn--tiny bea-admin-btn--danger" [disabled]="saving()" (click)="changerStatut(f, false)">Désactiver</button>
                    } @else {
                      <button type="button" class="bea-admin-btn bea-admin-btn--tiny" [disabled]="saving()" (click)="changerStatut(f, true)">Réactiver</button>
                    }
                  </div>
                </div>

                <!-- Postes -->
                <div class="bea-admin-panel bea-org-card">
                  <div class="bea-org-card__head">
                    <h2 class="bea-org-card__title">Postes / fonctions</h2>
                    <span class="bea-org-count">{{ f.postes.length }}</span>
                  </div>
                  <p class="bea-org-muted">Un poste est une fonction, distincte de la personne qui l’occupe et de ses droits applicatifs.</p>
                  @if (!f.postes.length) {
                    <p class="bea-admin-panel__empty">Aucun poste défini.</p>
                  } @else {
                    <div class="bea-org-scroll bea-org-scroll--sm">
                      <table class="bea-admin-table bea-org-table">
                        <thead><tr><th>Intitulé</th><th>Titulaire</th><th class="bea-org-right">Actions</th></tr></thead>
                        <tbody>
                          @for (p of f.postes; track p.id + ':' + rev()) {
                            <tr [class.bea-org-row--off]="!p.actif">
                              <td>
                                <div class="bea-org-strong">{{ p.intitule }}</div>
                                <div class="bea-org-tags">
                                  @if (p.est_responsable) { <span class="bea-badge bea-badge--info">Responsable</span> }
                                  @if (p.a_confirmer) { <span class="bea-badge bea-badge--warn" [title]="p.note_confirmation || ''">À confirmer</span> }
                                  @if (!p.actif) { <span class="bea-badge bea-badge--inactif">Inactif</span> }
                                </div>
                              </td>
                              <td>
                                <select class="bea-org-input" [ngModel]="p.titulaire_user_id ?? ''" (ngModelChange)="designerTitulaire(p, $event)"
                                        [disabled]="saving() || !p.actif" aria-label="Titulaire du poste">
                                  <option value="">— Vacant —</option>
                                  @for (u of titulairesPossibles(f, p); track u.id) { <option [value]="u.id">{{ u.nom }}</option> }
                                </select>
                              </td>
                              <td class="bea-org-right">
                                <div class="bea-admin-row-actions">
                                  <button type="button" class="bea-admin-icon-btn" [disabled]="saving()" (click)="renommerPoste(p)" title="Renommer" aria-label="Renommer">
                                    <bea-admin-icon name="edit" />
                                  </button>
                                  <button type="button" class="bea-admin-icon-btn" [disabled]="saving()" (click)="majPoste(p, { est_responsable: !p.est_responsable })"
                                          [title]="p.est_responsable ? 'Retirer la responsabilité' : 'Poste de responsable'" aria-label="Responsable">
                                    <bea-admin-icon name="workspace_premium" />
                                  </button>
                                  @if (p.a_confirmer) {
                                    <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--ok" [disabled]="saving()" (click)="majPoste(p, { a_confirmer: false })"
                                            title="Marquer confirmé" aria-label="Marquer confirmé">
                                      <bea-admin-icon name="check" />
                                    </button>
                                  }
                                  <button type="button" class="bea-admin-icon-btn" [class.bea-admin-icon-btn--danger]="p.actif" [disabled]="saving()"
                                          (click)="majPoste(p, { actif: !p.actif })" [title]="p.actif ? 'Désactiver' : 'Réactiver'" [attr.aria-label]="p.actif ? 'Désactiver' : 'Réactiver'">
                                    <bea-admin-icon [name]="p.actif ? 'block' : 'restart_alt'" />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          }
                        </tbody>
                      </table>
                    </div>
                  }
                  @if (f.entite.actif) {
                    <div class="bea-org-inline">
                      <input type="text" class="bea-org-input" [ngModel]="posteIntitule()" (ngModelChange)="posteIntitule.set($event)" maxlength="200"
                             placeholder="Nouveau poste (ex. Chef de service)" aria-label="Intitulé du nouveau poste" />
                      <label class="bea-org-check">
                        <input type="checkbox" [ngModel]="posteResponsable()" (ngModelChange)="posteResponsable.set($event)" /> Responsable
                      </label>
                      <button type="button" class="bea-admin-btn bea-admin-btn--tiny" [disabled]="saving() || !posteIntitule().trim()" (click)="ajouterPoste(f)">Ajouter</button>
                    </div>
                  }
                </div>

                <!-- Utilisateurs -->
                <div class="bea-admin-panel bea-org-card">
                  <div class="bea-org-card__head">
                    <h2 class="bea-org-card__title">Utilisateurs rattachés</h2>
                    <span class="bea-org-count">{{ f.affectations.length }}</span>
                  </div>
                  @if (!f.affectations.length) {
                    <p class="bea-admin-panel__empty">Aucun utilisateur affecté. Les affectations se gèrent depuis la fiche utilisateur.</p>
                  } @else {
                    <ul class="bea-org-items bea-org-scroll bea-org-scroll--sm">
                      @for (a of f.affectations; track a.id) {
                        <li class="bea-org-item">
                          <a class="bea-org-item__title bea-org-link" [routerLink]="['/admin/users', a.user_id]">{{ a.utilisateur || a.email }}</a>
                          <span class="bea-org-item__meta">
                            {{ a.type_libelle }} · {{ a.poste || 'sans poste' }} · {{ a.perimetre_libelle }} · depuis le {{ a.date_debut | date: 'dd/MM/yyyy' }}
                          </span>
                        </li>
                      }
                    </ul>
                  }
                </div>

                <!-- Sous-entités et données -->
                <div class="bea-admin-panel bea-org-card">
                  <h2 class="bea-org-card__title">Sous-entités, agences et données rattachées</h2>
                  @if (f.enfants.length) {
                    <ul class="bea-org-items bea-org-scroll bea-org-scroll--sm">
                      @for (c of f.enfants; track c.id) {
                        <li class="bea-org-item bea-org-item--row">
                          <span class="bea-org-type" [attr.data-type]="c.type_entite">{{ typeCourt(c.type_entite) }}</span>
                          <button type="button" class="bea-org-link" (click)="selectionner(c.id)">{{ c.libelle }}</button>
                          @if (!c.actif) { <span class="bea-badge bea-badge--inactif">Désactivée</span> }
                        </li>
                      }
                    </ul>
                  }
                  @if (f.agences.length) {
                    <p class="bea-org-line"><strong>Agences :</strong> {{ agencesTexte(f) }}</p>
                  }
                  @if (f.usages_sous_arbre.length) {
                    <ul class="bea-org-items">
                      @for (u of f.usages_sous_arbre; track u.liaison) {
                        <li class="bea-org-item bea-org-item--row">
                          <span class="bea-org-count">{{ u.nombre }}</span> {{ u.libelle }} <span class="bea-org-muted">({{ u.module }})</span>
                        </li>
                      }
                    </ul>
                    <p class="bea-org-muted">Comptage sur l’entité et ses sous-entités. Ces données sont conservées en cas de désactivation.</p>
                  } @else if (!f.enfants.length && !f.agences.length) {
                    <p class="bea-admin-panel__empty">Aucune donnée de module rattachée pour l’instant.</p>
                  }
                </div>
              } @else {
                <div class="bea-admin-panel bea-org-card">
                  <p class="bea-admin-panel__empty">Sélectionnez une entité dans l’organigramme pour afficher sa fiche.</p>
                </div>
              }
            </section>
          </div>
        }

        @case ('controles') {
          @if (controles(); as c) {
            <div class="bea-org-grid">
              <section class="bea-admin-panel bea-org-card bea-org-card--wide">
                <div class="bea-org-card__head">
                  <h2 class="bea-org-card__title">Points à confirmer</h2>
                  <span class="bea-org-count bea-org-count--warn">{{ c.a_confirmer.length + c.postes_a_confirmer.length }}</span>
                </div>
                <p class="bea-org-muted">Lectures ambiguës de l’organigramme : signalées, jamais tranchées automatiquement.</p>
                <ul class="bea-org-items bea-org-scroll bea-org-scroll--md">
                  @for (e of c.a_confirmer; track e.id) {
                    <li class="bea-org-item">
                      <button type="button" class="bea-org-item__title bea-org-link" (click)="voirEntite(e.id)">{{ e.libelle }}</button>
                      <span class="bea-org-item__path">{{ parentChemin(e.chemin) }}</span>
                      <span class="bea-org-item__meta">{{ e.detail || 'à préciser' }}</span>
                    </li>
                  }
                  @for (p of c.postes_a_confirmer; track p.id) {
                    <li class="bea-org-item">
                      <button type="button" class="bea-org-item__title bea-org-link" (click)="voirEntite(p.entite_id)">Poste « {{ p.intitule }} »</button>
                      <span class="bea-org-item__path">{{ p.entite }}</span>
                      <span class="bea-org-item__meta">{{ p.note_confirmation || 'à préciser' }}</span>
                    </li>
                  }
                </ul>
              </section>

              <section class="bea-admin-panel bea-org-card">
                <div class="bea-org-card__head">
                  <h2 class="bea-org-card__title">Doublons</h2>
                  <span class="bea-org-count">{{ c.doublons.length }}</span>
                </div>
                @if (!c.doublons.length) {
                  <p class="bea-admin-panel__empty">Aucun libellé en double parmi les entités actives.</p>
                } @else {
                  <ul class="bea-org-items bea-org-scroll bea-org-scroll--sm">
                    @for (d of c.doublons; track d.libelle) {
                      <li class="bea-org-item">
                        <span class="bea-org-item__title">{{ d.libelle }}</span>
                        @for (e of d.entites; track e.id) {
                          <button type="button" class="bea-org-link bea-org-item__path" (click)="voirEntite(e.id)">sous {{ parentChemin(e.chemin) || 'la racine' }}</button>
                        }
                      </li>
                    }
                  </ul>
                }
                <p class="bea-org-muted">Un même libellé sous deux parents différents peut être légitime (ex. deux « Service Commercial »).</p>
              </section>

              <section class="bea-admin-panel bea-org-card">
                <div class="bea-org-card__head">
                  <h2 class="bea-org-card__title">Incohérences</h2>
                  <span class="bea-org-count">{{ c.incoherences.length + c.non_rattachees.length }}</span>
                </div>
                @if (!c.incoherences.length && !c.non_rattachees.length) {
                  <p class="bea-admin-panel__empty">Aucune incohérence ; toutes les entités actives ont un parent.</p>
                } @else {
                  <ul class="bea-org-items bea-org-scroll bea-org-scroll--sm">
                    @for (e of c.non_rattachees; track e.id) {
                      <li class="bea-org-item">
                        <button type="button" class="bea-org-item__title bea-org-link" (click)="voirEntite(e.id)">{{ e.libelle }}</button>
                        <span class="bea-org-item__meta">Aucune entité parente ({{ e.type_libelle }})</span>
                      </li>
                    }
                    @for (e of c.incoherences; track e.id + e.detail) {
                      <li class="bea-org-item">
                        <button type="button" class="bea-org-item__title bea-org-link" (click)="voirEntite(e.id)">{{ e.libelle }}</button>
                        <span class="bea-org-item__path">{{ parentChemin(e.chemin) }}</span>
                        <span class="bea-org-item__meta">{{ e.detail }}</span>
                      </li>
                    }
                  </ul>
                }
              </section>

              <section class="bea-admin-panel bea-org-card">
                <div class="bea-org-card__head">
                  <h2 class="bea-org-card__title">Postes de responsable vacants</h2>
                  <span class="bea-org-count">{{ c.responsables_vacants.length }}</span>
                </div>
                @if (!c.responsables_vacants.length) {
                  <p class="bea-admin-panel__empty">Tous les postes de responsable ont un titulaire.</p>
                } @else {
                  <ul class="bea-org-items bea-org-scroll bea-org-scroll--md">
                    @for (p of c.responsables_vacants; track p.id) {
                      <li class="bea-org-item">
                        <span class="bea-org-item__title">{{ p.intitule }}</span>
                        <button type="button" class="bea-org-link bea-org-item__path" (click)="voirEntite(p.entite_id)">{{ p.entite }}</button>
                      </li>
                    }
                  </ul>
                }
              </section>

              <section class="bea-admin-panel bea-org-card">
                <div class="bea-org-card__head">
                  <h2 class="bea-org-card__title">Utilisateurs sans affectation principale</h2>
                  <span class="bea-org-count">{{ c.resume.utilisateurs_sans_affectation }}</span>
                </div>
                @if (!c.utilisateurs_sans_affectation.length) {
                  <p class="bea-admin-panel__empty">Tous les utilisateurs actifs sont affectés.</p>
                } @else {
                  <ul class="bea-org-items bea-org-scroll bea-org-scroll--md">
                    @for (u of c.utilisateurs_sans_affectation; track u.id) {
                      <li class="bea-org-item bea-org-item--row">
                        <a class="bea-org-link bea-org-strong" [routerLink]="['/admin/users', u.id]">{{ u.nom }}</a>
                        <span class="bea-org-muted">{{ u.email }}</span>
                      </li>
                    }
                  </ul>
                  @if (c.resume.utilisateurs_sans_affectation > c.utilisateurs_sans_affectation.length) {
                    <p class="bea-org-muted">Liste limitée aux {{ c.utilisateurs_sans_affectation.length }} premiers.</p>
                  }
                }
              </section>
            </div>
          } @else {
            <p class="bea-admin-dash__loading">Chargement des contrôles…</p>
          }
        }

        @case ('correspondances') {
          <section class="bea-admin-panel bea-org-card">
            <h2 class="bea-org-card__title">Anciennes saisies libres à rattacher</h2>
            <p class="bea-org-muted">
              Seules les correspondances exactes ont été rattachées automatiquement. Les autres valeurs attendent une
              décision : les suggestions ne sont jamais appliquées sans validation, et le texte d’origine est conservé.
            </p>
            <div class="bea-org-scroll bea-org-scroll--sm">
              <table class="bea-admin-table bea-org-table">
                <thead>
                  <tr><th>Données</th><th>Module</th><th class="bea-org-num">Valeurs en attente</th><th class="bea-org-num">Lignes en attente</th><th class="bea-org-num">Lignes rattachées</th><th></th></tr>
                </thead>
                <tbody>
                  @for (r of resumeCorrespondances(); track r.liaison) {
                    <tr [class.bea-org-row--on]="r.liaison === liaison()">
                      <td class="bea-org-strong">{{ r.libelle }}</td>
                      <td class="bea-org-muted">{{ r.module }}</td>
                      <td class="bea-org-num">{{ r.valeurs }}</td>
                      <td class="bea-org-num">{{ r.lignes }}</td>
                      <td class="bea-org-num">{{ r.lignes_rattachees }}</td>
                      <td class="bea-org-right">
                        <button type="button" class="bea-admin-btn bea-admin-btn--tiny" [disabled]="!r.valeurs" (click)="chargerCorrespondances(r.liaison)">Traiter</button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
          @if (correspondances(); as cs) {
            <section class="bea-admin-panel bea-org-card">
              <div class="bea-org-card__head">
                <h2 class="bea-org-card__title">{{ cs.libelle }}</h2>
                <span class="bea-org-count">{{ cs.valeurs.length }} valeur(s)</span>
              </div>
              @if (!cs.valeurs.length) {
                <p class="bea-admin-panel__empty">Tout est rattaché.</p>
              } @else {
                <div class="bea-org-scroll bea-org-scroll--lg">
                  <table class="bea-admin-table bea-org-table">
                    <thead><tr><th>Valeur saisie</th><th class="bea-org-num">Lignes</th><th>Entité de l’organigramme</th><th></th></tr></thead>
                    <tbody>
                      @for (v of cs.valeurs; track v.cle) {
                        <tr>
                          <td class="bea-org-cell-valeur">
                            <div class="bea-org-strong">{{ v.exemples[0] || v.cle }}</div>
                            @if (v.exemples.length > 1) { <div class="bea-org-muted">{{ v.exemples.slice(1).join(' · ') }}</div> }
                          </td>
                          <td class="bea-org-num">{{ v.lignes }}</td>
                          <td class="bea-org-cell-choix">
                            <bea-org-entite-select [ngModel]="choix()[v.cle] || null" (ngModelChange)="choisirCorrespondance(v, $event)"
                                                   [entites]="entitesActives()" placeholder="— Choisir une entité —" />
                            @if (v.suggestions.length) {
                              <div class="bea-org-suggest">
                                <span class="bea-org-muted">Suggestions :</span>
                                @for (s of v.suggestions; track s.id) {
                                  <button type="button" class="bea-org-chip" [class.bea-org-chip--on]="choix()[v.cle] === s.id" (click)="choisirCorrespondance(v, s.id)"
                                          [title]="s.chemin || s.libelle">{{ s.libelle }}</button>
                                }
                              </div>
                            }
                          </td>
                          <td class="bea-org-right">
                            <button type="button" class="bea-admin-btn bea-admin-btn--tiny" [disabled]="saving() || !choix()[v.cle]" (click)="appliquer(cs, v)">Rattacher</button>
                          </td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              }
            </section>
          }
        }

        @case ('agences') {
          <section class="bea-admin-panel bea-org-card">
            <div class="bea-org-card__head">
              <h2 class="bea-org-card__title">Agences physiques</h2>
              <span class="bea-org-count">{{ agences().length }}</span>
            </div>
            <p class="bea-org-muted">
              Les agences restent dans leur référentiel existant ; leur rattachement hiérarchique est facultatif et
              n’est renseigné que lorsqu’il est établi (sinon : à confirmer).
            </p>
            <div class="bea-org-scroll bea-org-scroll--lg">
              <table class="bea-admin-table bea-org-table">
                <thead><tr><th>Code</th><th>Agence</th><th>Ville</th><th>Rattachement</th></tr></thead>
                <tbody>
                  @for (a of agences(); track a.id + ':' + rev()) {
                    <tr>
                      <td><code>{{ a.code }}</code></td>
                      <td class="bea-org-strong">{{ a.libelle }}@if (!a.actif) { <span class="bea-badge bea-badge--inactif">Inactive</span> }</td>
                      <td class="bea-org-muted">{{ a.ville || '—' }}</td>
                      <td class="bea-org-cell-choix">
                        <bea-org-entite-select [ngModel]="a.org_entite_id" (ngModelChange)="rattacherAgence(a, $event)" [entites]="entitesActives()"
                                               placeholder="— Non rattachée (à confirmer) —" [ariaLabel]="'Rattachement de ' + a.libelle" />
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('historique') {
          <section class="bea-admin-panel bea-org-card">
            <div class="bea-org-card__head">
              <h2 class="bea-org-card__title">Historique des modifications</h2>
              <span class="bea-org-count">{{ histTotal() }}</span>
            </div>
            @if (!historique().length) {
              <p class="bea-admin-panel__empty">Aucune modification enregistrée.</p>
            } @else {
              <div class="bea-org-scroll bea-org-scroll--lg">
                <table class="bea-admin-table bea-org-table">
                  <thead><tr><th>Date</th><th>Action</th><th>Objet</th><th>Par</th><th>Référence</th></tr></thead>
                  <tbody>
                    @for (h of historique(); track h.id) {
                      <tr>
                        <td class="bea-org-nowrap">{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                        <td class="bea-org-strong">{{ actionLibelle(h.action) }}</td>
                        <td>{{ objetHistorique(h) }}</td>
                        <td>{{ h.utilisateur || '—' }}</td>
                        <td class="bea-org-muted"><code>{{ h.request_id || '—' }}</code></td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              <div class="bea-admin-pager">
                <span>Page {{ histPage() }} / {{ histPages() }}</span>
                <div>
                  <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="histPage() <= 1" (click)="chargerHistorique(histPage() - 1)">Précédent</button>
                  <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="histPage() >= histPages()" (click)="chargerHistorique(histPage() + 1)">Suivant</button>
                </div>
              </div>
            }
          </section>
        }
      }
    </section>
  `,
  styles: [
    `
      /* Champs sans bordure : fond teinté, contour seulement au focus. */
      .bea-org-input {
        width: 100%;
        box-sizing: border-box;
        border: 0;
        border-radius: 8px;
        padding: 0.5rem 0.7rem;
        font: inherit;
        color: var(--bea-ink);
        background: var(--bea-surface);
        outline: none;
      }
      .bea-org-input:focus {
        box-shadow: 0 0 0 2px var(--bea-brand-400);
      }
      .bea-org-muted {
        color: var(--bea-ink-muted);
        font-size: 0.85rem;
        margin: 0.25rem 0 0;
      }
      .bea-org-strong {
        font-weight: 600;
      }
      .bea-org-nowrap {
        white-space: nowrap;
      }
      .bea-org-num {
        text-align: right;
        white-space: nowrap;
      }
      .bea-org-right {
        text-align: right;
      }
      .bea-org-spacer {
        flex: 1;
      }

      /* Onglets */
      .bea-org-tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin: 0 0 1rem;
        padding: 0.3rem;
        border-radius: 12px;
        background: var(--bea-surface-card);
        width: fit-content;
        max-width: 100%;
      }
      .bea-org-tab {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        border: 0;
        border-radius: 9px;
        padding: 0.5rem 0.9rem;
        background: transparent;
        color: var(--bea-ink-muted);
        font: inherit;
        font-weight: 600;
        cursor: pointer;
      }
      .bea-org-tab:hover {
        background: var(--bea-surface);
      }
      .bea-org-tab--on,
      .bea-org-tab--on:hover {
        background: var(--bea-brand-900);
        color: #fff;
      }

      /* Mise en page organigramme : deux colonnes à défilement indépendant */
      .bea-org-layout {
        display: grid;
        grid-template-columns: minmax(300px, 0.85fr) minmax(0, 1.5fr);
        gap: 1rem;
        height: calc(100vh - 290px);
        min-height: 460px;
      }
      @media (max-width: 1100px) {
        .bea-org-layout {
          grid-template-columns: 1fr;
          height: auto;
        }
        .bea-org-tree__list {
          max-height: 50vh;
        }
      }
      .bea-org-col {
        min-height: 0;
      }
      .bea-org-tree {
        display: flex;
        flex-direction: column;
        margin: 0;
      }
      .bea-org-detail {
        display: flex;
        flex-direction: column;
        gap: 1rem;
        padding-right: 0.25rem;
      }
      .bea-org-detail > * {
        margin: 0;
        flex-shrink: 0;
      }
      .bea-org-scroll {
        overflow: auto;
        scrollbar-width: thin;
      }
      .bea-org-scroll--sm {
        max-height: 260px;
      }
      .bea-org-scroll--md {
        max-height: 360px;
      }
      .bea-org-scroll--lg {
        max-height: calc(100vh - 360px);
        min-height: 240px;
      }
      .bea-org-scroll thead th {
        position: sticky;
        top: 0;
        z-index: 1;
        background: var(--bea-surface-card);
      }

      /* Arbre */
      .bea-org-tree__tools {
        display: grid;
        gap: 0.5rem;
        padding-bottom: 0.6rem;
        margin-bottom: 0.4rem;
        border-bottom: 1px solid var(--bea-line);
      }
      .bea-org-tree__row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
      }
      .bea-org-tree__list {
        flex: 1;
        list-style: none;
        margin: 0;
        padding: 0 0.25rem 0 0;
      }
      .bea-org-node {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        width: 100%;
        min-height: 2.1rem;
        text-align: left;
        border: 0;
        border-radius: 8px;
        background: transparent;
        color: var(--bea-ink);
        font: inherit;
        padding: 0.3rem 0.5rem;
        cursor: pointer;
      }
      .bea-org-node:hover {
        background: var(--bea-surface);
      }
      .bea-org-node--on,
      .bea-org-node--on:hover {
        background: var(--bea-chip);
      }
      .bea-org-node--off .bea-org-node__label {
        color: var(--bea-ink-muted);
        text-decoration: line-through;
      }
      .bea-org-node__main {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
      }
      .bea-org-node__label {
        font-size: 0.9rem;
        line-height: 1.25;
      }
      .bea-org-node--on .bea-org-node__label {
        font-weight: 650;
      }
      .bea-org-node__path {
        font-size: 0.75rem;
        color: var(--bea-ink-muted);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .bea-org-node__flags {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        flex-shrink: 0;
      }
      .bea-org-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 0.9rem;
        margin: 0.5rem 0 0;
        padding-top: 0.5rem;
        border-top: 1px solid var(--bea-line);
        font-size: 0.75rem;
        color: var(--bea-ink-muted);
      }
      .bea-org-legend > span {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
      }

      /* Pastilles de type */
      .bea-org-type {
        flex-shrink: 0;
        min-width: 4.4rem;
        text-align: center;
        font-size: 0.66rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        padding: 0.18rem 0.4rem;
        border-radius: 999px;
        background: var(--bea-surface);
        color: var(--bea-ink-muted);
      }
      .bea-org-type[data-type='CONSEIL'],
      .bea-org-type[data-type='DIRECTION_GENERALE'] {
        background: var(--bea-brand-900);
        color: #fff;
      }
      .bea-org-type[data-type='DIRECTION'] {
        background: var(--bea-chip);
        color: var(--bea-chip-ink);
      }
      .bea-org-type[data-type='DEPARTEMENT'] {
        background: var(--bea-ok-bg);
        color: var(--bea-ok-ink);
      }
      .bea-org-type[data-type='COMITE'] {
        background: var(--bea-warn-bg);
        color: var(--bea-warn-ink);
      }
      .bea-org-dot {
        display: inline-block;
        width: 0.55rem;
        height: 0.55rem;
        border-radius: 50%;
      }
      .bea-org-dot--warn {
        background: #f59e0b;
      }
      .bea-org-dot--off {
        background: #94a3b8;
      }
      .bea-org-count {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 1.4rem;
        padding: 0.05rem 0.45rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
        background: var(--bea-chip);
        color: var(--bea-chip-ink);
      }
      .bea-org-count--warn {
        background: var(--bea-warn-bg);
        color: var(--bea-warn-ink);
      }

      /* Cartes */
      .bea-org-card {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        min-width: 0;
      }
      .bea-org-card__head {
        display: flex;
        align-items: center;
        gap: 0.5rem;
      }
      .bea-org-card__title {
        margin: 0;
        font-size: 1.05rem;
      }
      .bea-org-card__title small {
        font-weight: 500;
        color: var(--bea-ink-muted);
      }
      .bea-org-head {
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
      }
      .bea-org-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        align-items: center;
      }
      .bea-org-crumbs {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.25rem;
        font-size: 0.8rem;
        color: var(--bea-ink-muted);
      }
      .bea-org-sep {
        opacity: 0.6;
      }
      .bea-org-link {
        border: 0;
        background: none;
        padding: 0;
        font: inherit;
        color: var(--bea-brand-800);
        text-align: left;
        text-decoration: none;
        cursor: pointer;
      }
      .bea-org-link:hover {
        text-decoration: underline;
      }
      .bea-org-dl {
        display: grid;
        grid-template-columns: max-content 1fr;
        gap: 0.3rem 1rem;
        margin: 0.25rem 0 0;
        font-size: 0.88rem;
      }
      .bea-org-dl dt {
        color: var(--bea-ink-muted);
      }
      .bea-org-dl dd {
        margin: 0;
      }
      .bea-org-alert {
        display: flex;
        gap: 0.5rem;
        align-items: flex-start;
        margin: 0;
        padding: 0.6rem 0.75rem;
        border-radius: 8px;
        background: var(--bea-warn-bg);
        color: var(--bea-warn-ink);
        font-size: 0.88rem;
      }
      .bea-org-actions {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.5rem;
        margin-top: 0.25rem;
      }
      .bea-org-inline {
        display: grid;
        grid-template-columns: 1fr auto auto;
        gap: 0.6rem;
        align-items: center;
        margin-top: 0.25rem;
      }
      .bea-org-check {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.88rem;
        white-space: nowrap;
      }
      .bea-org-table td {
        vertical-align: middle;
      }
      .bea-org-row--off {
        opacity: 0.6;
      }
      .bea-org-row--on td {
        background: var(--bea-chip);
      }
      .bea-org-line {
        margin: 0;
        font-size: 0.9rem;
      }

      /* Listes */
      .bea-org-items {
        list-style: none;
        margin: 0;
        padding: 0;
      }
      .bea-org-item {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        padding: 0.55rem 0.25rem;
        border-bottom: 1px solid var(--bea-line);
        text-align: left;
      }
      .bea-org-item:last-child {
        border-bottom: 0;
      }
      .bea-org-item--row {
        flex-direction: row;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.5rem;
      }
      .bea-org-item__title {
        font-weight: 650;
      }
      .bea-org-item__path {
        font-size: 0.78rem;
        color: var(--bea-ink-muted);
      }
      button.bea-org-item__path {
        color: var(--bea-brand-800);
      }
      .bea-org-item__meta {
        font-size: 0.85rem;
        color: var(--bea-ink);
      }

      /* Contrôles */
      .bea-org-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1rem;
        align-items: start;
      }
      .bea-org-grid > * {
        margin: 0;
      }
      .bea-org-card--wide {
        grid-column: 1 / -1;
      }
      @media (max-width: 1000px) {
        .bea-org-grid {
          grid-template-columns: 1fr;
        }
      }

      /* Formulaire */
      .bea-org-form {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.75rem 1rem;
      }
      .bea-org-field {
        display: flex;
        flex-direction: column;
        gap: 0.3rem;
        font-size: 0.85rem;
        color: var(--bea-ink-muted);
      }
      .bea-org-field--full {
        grid-column: 1 / -1;
      }

      /* Correspondances / agences */
      .bea-org-cell-valeur {
        min-width: 160px;
      }
      .bea-org-cell-choix {
        min-width: 300px;
        width: 50%;
      }
      .bea-org-suggest {
        display: flex;
        flex-wrap: wrap;
        gap: 0.3rem;
        align-items: center;
        margin-top: 0.35rem;
      }
      .bea-org-chip {
        border: 0;
        border-radius: 999px;
        padding: 0.2rem 0.6rem;
        font: inherit;
        font-size: 0.78rem;
        background: var(--bea-chip);
        color: var(--bea-chip-ink);
        cursor: pointer;
      }
      .bea-org-chip--on {
        background: var(--bea-brand-800);
        color: #fff;
      }
    `,
  ],
})
export class CoreAdminOrganigrammeComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly referentiel = inject(OrgReferentielService);

  readonly hasUnsavedChanges = unsavedChanges(
    () => this.mode() !== null && this.form.dirty && !this.saving(),
    () => this.form,
  );

  readonly types = TYPES;
  readonly onglets: { id: Onglet; label: string; icon: string }[] = [
    { id: 'organigramme', label: 'Organigramme', icon: 'account_tree' },
    { id: 'controles', label: 'Contrôles', icon: 'rule' },
    { id: 'correspondances', label: 'Correspondances', icon: 'link' },
    { id: 'agences', label: 'Agences', icon: 'store' },
    { id: 'historique', label: 'Historique', icon: 'history' },
  ];

  readonly onglet = signal<Onglet>('organigramme');
  readonly chargement = signal(true);
  readonly saving = signal(false);
  readonly entites = signal<OrgEntiteAdmin[]>([]);
  readonly recherche = signal('');
  readonly voirInactives = signal(false);
  readonly selectionId = signal<string | null>(null);
  readonly fiche = signal<OrgFiche | null>(null);
  readonly mode = signal<'creer' | 'modifier' | null>(null);
  readonly posteIntitule = signal('');
  readonly posteResponsable = signal(false);
  readonly controles = signal<OrgControles | null>(null);
  readonly resumeCorrespondances = signal<OrgCorrespondanceResume[]>([]);
  readonly liaison = signal<string | null>(null);
  readonly correspondances = signal<OrgCorrespondances | null>(null);
  readonly choix = signal<Record<string, string>>({});
  readonly agences = signal<OrgAgenceAdmin[]>([]);
  readonly historique = signal<OrgHistoriqueLigne[]>([]);
  /** Incrémenté à chaque rechargement : réinitialise les listes déroulantes après refus ou échec. */
  readonly rev = signal(0);
  readonly histPage = signal(1);
  readonly histTotal = signal(0);
  readonly histPages = computed(() => Math.max(1, Math.ceil(this.histTotal() / 50)));

  readonly entitesActives = computed(() => this.entites().filter((e) => e.actif));
  readonly arbreVisible = computed(() => {
    const q = this.normaliser(this.recherche());
    return this.entites().filter((e) => {
      if (!this.voirInactives() && !e.actif) return false;
      if (!q) return true;
      return [e.libelle, e.sigle, e.code, ...(e.alias ?? [])].some((v) => v && this.normaliser(v).includes(q));
    });
  });

  readonly form = this.fb.nonNullable.group({
    type_entite: ['SERVICE' as OrgTypeEntite, Validators.required],
    libelle: ['', [Validators.required, Validators.maxLength(255)]],
    sigle: [''],
    code: [''],
    parent_id: [null as string | null],
    alias: [''],
    description: [''],
    a_confirmer: [false],
    note_confirmation: [''],
  });

  ngOnInit(): void {
    this.chargerEntites();
    this.chargerControles();
  }

  typeLibelle(t: OrgTypeEntite): string {
    return ORG_TYPE_LIBELLES[t];
  }

  typeCourt(t: OrgTypeEntite): string {
    return TYPE_COURT[t] ?? t;
  }

  /** Chemin des parents seulement (« Direction › Département »), sans l'entité elle-même. */
  parentChemin(chemin: string | null): string {
    const parts = (chemin ?? '').split(' › ');
    return parts.slice(0, -1).join(' › ');
  }

  kpis(c: OrgControles) {
    const r = c.resume;
    return [
      { label: 'Entités actives', value: r.actives, icon: 'account_tree', tone: 'blue', onglet: 'organigramme' as Onglet },
      { label: 'À confirmer', value: r.a_confirmer + r.postes_a_confirmer, icon: 'help', tone: 'amber', onglet: 'controles' as Onglet },
      { label: 'Incohérences', value: r.incoherences + r.non_rattachees + r.doublons, icon: 'report', tone: 'rose', onglet: 'controles' as Onglet },
      { label: 'Sans affectation', value: r.utilisateurs_sans_affectation, icon: 'person_off', tone: 'teal', onglet: 'controles' as Onglet },
      { label: 'Correspondances', value: r.correspondances_en_attente, icon: 'link', tone: 'green', onglet: 'correspondances' as Onglet },
      { label: 'Agences non rattachées', value: r.agences_non_rattachees, icon: 'store', tone: 'amber', onglet: 'agences' as Onglet },
    ];
  }

  ouvrir(o: Onglet): void {
    this.onglet.set(o);
    if (o === 'controles') this.chargerControles();
    if (o === 'correspondances') this.chargerResumeCorrespondances();
    if (o === 'agences') this.chargerAgences();
    if (o === 'historique') this.chargerHistorique(1);
  }

  // ------------------------------------------------------------------ organigramme
  async selectionner(id: string): Promise<void> {
    if (!(await this.quitterFormulaire())) return;
    this.selectionId.set(id);
    this.chargerFiche(id);
  }

  voirEntite(id: string): void {
    this.onglet.set('organigramme');
    this.voirInactives.set(true);
    void this.selectionner(id);
  }

  async nouvelle(parent: OrgEntiteAdmin | null): Promise<void> {
    if (!(await this.quitterFormulaire())) return;
    this.form.reset({
      type_entite: parent ? (TYPE_ENFANT[parent.type_entite] ?? 'SERVICE') : 'DIRECTION',
      libelle: '',
      sigle: '',
      code: '',
      parent_id: parent?.id ?? null,
      alias: '',
      description: '',
      a_confirmer: false,
      note_confirmation: '',
    });
    this.mode.set('creer');
  }

  modifier(f: OrgFiche): void {
    const e = f.entite;
    this.form.reset({
      type_entite: e.type_entite,
      libelle: e.libelle,
      sigle: e.sigle ?? '',
      code: e.code,
      parent_id: e.parent_id,
      alias: (e.alias ?? []).join('; '),
      description: e.description ?? '',
      a_confirmer: e.a_confirmer,
      note_confirmation: e.note_confirmation ?? '',
    });
    this.mode.set('modifier');
  }

  async annulerForm(): Promise<void> {
    if (await this.quitterFormulaire()) this.mode.set(null);
  }

  async enregistrer(): Promise<void> {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const creation = this.mode() === 'creer';
    const actuelle = this.fiche()?.entite;
    const deplacement = !creation && actuelle && (actuelle.parent_id ?? null) !== (v.parent_id ?? null);
    const parent = this.entites().find((e) => e.id === v.parent_id);
    const ok = await this.dialogs.confirm({
      title: creation ? 'Créer l’entité' : 'Enregistrer les modifications',
      message: creation
        ? `Créer « ${v.libelle.trim()} » sous ${parent ? `« ${parent.libelle} »` : 'la racine de l’organigramme'} ?`
        : deplacement
          ? `Déplacer « ${v.libelle.trim()} » sous ${parent ? `« ${parent.libelle} »` : 'la racine'} ? Les données rattachées suivent l’entité.`
          : `Enregistrer les modifications de « ${v.libelle.trim()} » ?`,
      confirmLabel: creation ? 'Créer' : 'Enregistrer',
    });
    if (!ok) return;
    const corps: Record<string, unknown> = {
      type_entite: v.type_entite,
      libelle: v.libelle.trim(),
      sigle: v.sigle.trim(),
      description: v.description.trim(),
      alias: v.alias.split(';').map((a) => a.trim()).filter(Boolean),
      a_confirmer: v.a_confirmer,
      note_confirmation: v.a_confirmer ? v.note_confirmation.trim() : '',
    };
    if (v.code.trim()) corps['code'] = v.code.trim();
    if (creation) {
      corps['parent_id'] = v.parent_id;
    } else if (v.parent_id) {
      corps['parent_id'] = v.parent_id;
    } else {
      corps['detacher_parent'] = true;
    }
    this.saving.set(true);
    const req = creation
      ? this.api.post<OrgEntiteAdmin>(`${BASE}/entites`, corps)
      : this.api.patch<OrgEntiteAdmin>(`${BASE}/entites/${this.selectionId()}`, corps);
    req.subscribe({
      next: async (e) => {
        this.saving.set(false);
        this.form.markAsPristine();
        this.mode.set(null);
        this.apresModification(e.id);
        await this.dialogs.success(creation ? `Entité « ${e.libelle} » créée.` : `Entité « ${e.libelle} » enregistrée.`);
      },
      error: (err) => this.echec(err, 'Enregistrement impossible.'),
    });
  }

  async confirmerEntite(f: OrgFiche): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Point confirmé',
      message: `Le point « ${f.entite.note_confirmation || 'à confirmer'} » est-il validé pour « ${f.entite.libelle} » ?`,
      confirmLabel: 'Marquer confirmée',
    });
    if (!ok) return;
    this.saving.set(true);
    this.api.patch<OrgEntiteAdmin>(`${BASE}/entites/${f.entite.id}`, { a_confirmer: false }).subscribe({
      next: async () => {
        this.saving.set(false);
        this.apresModification(f.entite.id);
        await this.dialogs.success('Entité marquée comme confirmée.');
      },
      error: (err) => this.echec(err, 'Mise à jour impossible.'),
    });
  }

  async changerStatut(f: OrgFiche, actif: boolean): Promise<void> {
    const conserves = f.usages_sous_arbre.reduce((n, u) => n + u.nombre, 0);
    const valeurs = await this.dialogs.prompt({
      title: actif ? 'Réactiver l’entité' : 'Désactiver l’entité',
      message: actif
        ? `Réactiver « ${f.entite.libelle} » ?`
        : `Désactiver « ${f.entite.libelle} » ? Elle ne sera plus proposée dans les modules. ` +
          `${conserves ? `Les ${conserves} élément(s) rattaché(s) sont conservés.` : 'Aucune donnée n’est supprimée.'}`,
      tone: actif ? 'primary' : 'danger',
      confirmLabel: actif ? 'Réactiver' : 'Désactiver',
      fields: [{ key: 'motif', label: 'Motif' }],
      validate: (v) => (!actif && !(v['motif'] || '').trim() ? 'Le motif est obligatoire.' : null),
    });
    if (!valeurs) return;
    this.saving.set(true);
    this.api.post<OrgEntiteAdmin>(`${BASE}/entites/${f.entite.id}/${actif ? 'reactiver' : 'desactiver'}`, { motif: valeurs['motif'] || null }).subscribe({
      next: async () => {
        this.saving.set(false);
        this.apresModification(f.entite.id);
        await this.dialogs.success(actif ? 'Entité réactivée.' : 'Entité désactivée. Les données rattachées sont conservées.');
      },
      error: (err) => this.echec(err, 'Changement de statut impossible.'),
    });
  }

  titulairesPossibles(f: OrgFiche, p: OrgPoste): { id: string; nom: string }[] {
    const vus = new Map<string, string>();
    for (const a of f.affectations) {
      if (a.actif) vus.set(a.user_id, a.utilisateur || a.email || a.user_id);
    }
    if (p.titulaire_user_id && !vus.has(p.titulaire_user_id)) {
      vus.set(p.titulaire_user_id, p.titulaire_nom || 'Titulaire actuel');
    }
    return [...vus.entries()].map(([id, nom]) => ({ id, nom }));
  }

  ajouterPoste(f: OrgFiche): void {
    const intitule = this.posteIntitule().trim();
    if (!intitule || this.saving()) return;
    this.saving.set(true);
    this.api.post<OrgPoste>(`${BASE}/entites/${f.entite.id}/postes`, { intitule, est_responsable: this.posteResponsable() }).subscribe({
      next: async () => {
        this.saving.set(false);
        this.posteIntitule.set('');
        this.posteResponsable.set(false);
        this.chargerFiche(f.entite.id);
        await this.dialogs.success(`Poste « ${intitule} » ajouté.`);
      },
      error: (err) => this.echec(err, 'Ajout du poste impossible.'),
    });
  }

  async renommerPoste(p: OrgPoste): Promise<void> {
    const v = await this.dialogs.prompt({
      title: 'Renommer le poste',
      message: `Nouvel intitulé pour « ${p.intitule} » :`,
      fields: [{ key: 'intitule', label: 'Intitulé' }],
      validate: (x) => (!(x['intitule'] || '').trim() ? 'Intitulé obligatoire.' : null),
      confirmLabel: 'Renommer',
    });
    if (v) this.majPoste(p, { intitule: v['intitule'].trim() });
  }

  designerTitulaire(p: OrgPoste, userId: string): void {
    this.majPoste(p, userId ? { titulaire_user_id: userId } : { retirer_titulaire: true });
  }

  majPoste(p: OrgPoste, patch: Record<string, unknown>): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.api.patch<OrgPoste>(`${BASE}/postes/${p.id}`, patch).subscribe({
      next: async () => {
        this.saving.set(false);
        this.chargerFiche(p.entite_id);
        this.chargerControles();
        await this.dialogs.success('Poste mis à jour.');
      },
      error: (err) => {
        this.chargerFiche(p.entite_id);
        this.echec(err, 'Mise à jour du poste impossible.');
      },
    });
  }

  agencesTexte(f: OrgFiche): string {
    return f.agences.map((a) => `${a.code} ${a.libelle}`).join(', ');
  }

  // ------------------------------------------------------------------ correspondances
  chargerCorrespondances(liaison: string): void {
    this.liaison.set(liaison);
    this.choix.set({});
    this.api.get<OrgCorrespondances>(`${BASE}/correspondances/${liaison}`).subscribe({
      next: (c) => this.correspondances.set(c),
      error: (err) => this.echec(err, 'Chargement impossible.'),
    });
  }

  choisirCorrespondance(v: OrgCorrespondanceValeur, entiteId: string | null): void {
    this.choix.update((c) => {
      const out = { ...c };
      if (entiteId) out[v.cle] = entiteId;
      else delete out[v.cle];
      return out;
    });
  }

  async appliquer(cs: OrgCorrespondances, v: OrgCorrespondanceValeur): Promise<void> {
    const entiteId = this.choix()[v.cle];
    const entite = this.entites().find((e) => e.id === entiteId);
    if (!entite) return;
    const ok = await this.dialogs.confirm({
      title: 'Rattacher la valeur',
      message:
        `Rattacher les ${v.lignes} ligne(s) « ${v.exemples[0] || v.cle} » (${cs.libelle}) à « ${entite.chemin || entite.libelle} » ? ` +
        'Le texte saisi d’origine est conservé et la valeur sera reconnue automatiquement à l’avenir.',
      confirmLabel: 'Rattacher',
    });
    if (!ok) return;
    this.saving.set(true);
    this.api
      .post<{ lignes_rattachees: number }>(`${BASE}/correspondances`, { liaison: cs.liaison, valeur: v.cle, entite_id: entiteId, memoriser_alias: true })
      .subscribe({
        next: async (r) => {
          this.saving.set(false);
          this.chargerCorrespondances(cs.liaison);
          this.chargerResumeCorrespondances();
          this.chargerEntites();
          await this.dialogs.success(`${r.lignes_rattachees} ligne(s) rattachée(s).`);
        },
        error: (err) => this.echec(err, 'Rattachement impossible.'),
      });
  }

  // ------------------------------------------------------------------ agences
  async rattacherAgence(a: OrgAgenceAdmin, entiteId: string | null): Promise<void> {
    if ((a.org_entite_id ?? null) === (entiteId ?? null)) return;
    const entite = this.entites().find((e) => e.id === entiteId);
    const ok = await this.dialogs.confirm({
      title: 'Rattachement d’agence',
      message: entite
        ? `Rattacher l’agence ${a.code} ${a.libelle} à « ${entite.chemin || entite.libelle} » ?`
        : `Retirer le rattachement de l’agence ${a.code} ${a.libelle} ?`,
      confirmLabel: 'Confirmer',
    });
    if (!ok) {
      this.chargerAgences();
      return;
    }
    this.saving.set(true);
    this.api.patch(`${BASE}/agences/${a.id}`, { org_entite_id: entiteId }).subscribe({
      next: async () => {
        this.saving.set(false);
        this.chargerAgences();
        this.chargerControles();
        this.referentiel.invalider();
        await this.dialogs.success('Rattachement enregistré.');
      },
      error: (err) => {
        this.chargerAgences();
        this.echec(err, 'Rattachement impossible.');
      },
    });
  }

  // ------------------------------------------------------------------ historique
  actionLibelle(action: string): string {
    return ORG_ACTION_LIBELLES[action] ?? action;
  }

  objetHistorique(h: OrgHistoriqueLigne): string {
    const apres = h.apres ?? h.avant ?? {};
    const champ = (k: string) => (typeof apres[k] === 'string' ? (apres[k] as string) : null);
    return champ('chemin') || champ('libelle') || champ('intitule') || champ('agence') || champ('entite') || champ('utilisateur') || h.entity;
  }

  chargerHistorique(page: number): void {
    this.api.get<{ items: OrgHistoriqueLigne[]; total: number; page: number }>(`${BASE}/historique`, { page, size: 50 }).subscribe({
      next: (r) => {
        this.historique.set(r.items ?? []);
        this.histTotal.set(r.total ?? 0);
        this.histPage.set(r.page ?? page);
      },
      error: (err) => this.echec(err, 'Historique indisponible.'),
    });
  }

  // ------------------------------------------------------------------ chargements
  private chargerEntites(): void {
    this.api.get<{ items: OrgEntiteAdmin[] }>(`${BASE}/entites`).subscribe({
      next: (r) => {
        this.entites.set(r.items ?? []);
        this.chargement.set(false);
        if (!this.selectionId() && r.items?.length) {
          const dg = r.items.find((e) => e.type_entite === 'DIRECTION_GENERALE') ?? r.items[0];
          this.selectionId.set(dg.id);
          this.chargerFiche(dg.id);
        }
      },
      error: (err) => {
        this.chargement.set(false);
        this.echec(err, 'Organigramme indisponible.');
      },
    });
  }

  private chargerFiche(id: string): void {
    this.api.get<OrgFiche>(`${BASE}/entites/${id}`).subscribe({
      next: (f) => {
        this.fiche.set(f);
        this.rev.update((n) => n + 1);
      },
      error: (err) => this.echec(err, 'Fiche indisponible.'),
    });
  }

  private chargerControles(): void {
    this.api.get<OrgControles>(`${BASE}/controles`).subscribe({
      next: (c) => {
        this.controles.set(c);
        this.resumeCorrespondances.set(c.correspondances ?? []);
      },
      error: (err) => this.echec(err, 'Contrôles indisponibles.'),
    });
  }

  private chargerResumeCorrespondances(): void {
    this.api.get<{ items: OrgCorrespondanceResume[] }>(`${BASE}/correspondances`).subscribe({
      next: (r) => this.resumeCorrespondances.set(r.items ?? []),
      error: (err) => this.echec(err, 'Correspondances indisponibles.'),
    });
  }

  private chargerAgences(): void {
    this.api.get<{ items: OrgAgenceAdmin[] }>(`${BASE}/agences`).subscribe({
      next: (r) => {
        this.agences.set(r.items ?? []);
        this.rev.update((n) => n + 1);
      },
      error: (err) => this.echec(err, 'Agences indisponibles.'),
    });
  }

  private apresModification(id: string): void {
    this.referentiel.invalider();
    this.selectionId.set(id);
    this.chargerEntites();
    this.chargerFiche(id);
    this.chargerControles();
  }

  private async echec(err: unknown, fallback: string): Promise<void> {
    this.saving.set(false);
    await this.dialogs.error(orgErreur(err, fallback));
  }

  private async quitterFormulaire(): Promise<boolean> {
    if (this.mode() === null || !this.form.dirty) {
      this.mode.set(null);
      return true;
    }
    const ok = await this.dialogs.confirm({
      title: 'Modifications non enregistrées',
      message: 'Abandonner les modifications en cours ?',
      tone: 'warn',
      confirmLabel: 'Abandonner',
    });
    if (ok) {
      this.form.markAsPristine();
      this.mode.set(null);
    }
    return ok;
  }

  private normaliser(v: string): string {
    return v
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim();
  }
}
