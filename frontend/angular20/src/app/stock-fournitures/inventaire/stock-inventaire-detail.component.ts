import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  OnInit,
  computed,
  inject,
  input,
  signal,
  viewChildren,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { Observable, Subject, debounceTime } from 'rxjs';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { MgGedPanelComponent } from '../../moyens-generaux/mg-ged-panel.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { StockAlertesWatcherService } from '../stock-alertes-watcher.service';
import {
  ACTION_LABELS,
  Ajustement,
  Inventaire,
  InventaireHistorique,
  InventaireLigne,
  InventaireStats,
  InventaireStatut,
  LIGNE_LABELS,
  LigneFiltre,
  LigneStatut,
  MSG_VERROU,
  PERM,
  Paginated,
  Rapprochement,
  RefOption,
  STATUT_ICONS,
  STATUT_LABELS,
  VERROUILLES,
  ValidationPreview,
  aPermission,
  downloadBlob,
  pourcentage,
  signe,
} from './inventaire.model';

type EtatSaisie = 'saving' | 'ok' | 'erreur';

interface SaveOut {
  ligne: InventaireLigne;
  stats: InventaireStats;
  statut: InventaireStatut;
}

interface ArticleOption {
  id: string;
  code: string;
  designation: string;
}

interface ReferenceAnalyse {
  fichier: string;
  source_officielle: string | null;
  date_comptage: string | null;
  calcul: Record<string, number>;
  mouvements: Record<string, number>;
  registre_ecarts: { code: string; ecart: number }[];
  anomalies: string[];
  bloquant: boolean;
}

const CHAMPS_SOURCE: { cle: string; label: string }[] = [
  { cle: 'categorie', label: 'Catégorie' },
  { cle: 'statut_agence', label: 'Statut agence' },
  { cle: 'stock_initial', label: 'Stock initial' },
  { cle: 'entrees', label: 'Entrées' },
  { cle: 'sorties', label: 'Sorties' },
  { cle: 'stock_final_theorique', label: 'Stock final théorique' },
  { cle: 'verifie', label: 'Vérifié' },
  { cle: 'stock_physique', label: 'Stock physique constaté' },
  { cle: 'ecart', label: 'Écart (banque)' },
  { cle: 'statut_inventaire', label: 'Statut inventaire' },
  { cle: 'stock_actuel_agence', label: 'Stock actuel agence' },
  { cle: 'consommation', label: 'Consommation (sorties)' },
  { cle: 'alerte', label: 'Alerte stock' },
  { cle: 'observations', label: 'Observations' },
  { cle: 'decision', label: 'Décision' },
];

const KPIS: { id: LigneFiltre; label: string; icon: string; cle: keyof InventaireStats; ton?: string }[] = [
  { id: '', label: 'Articles', icon: 'inventory_2', cle: 'total' },
  { id: 'compte', label: 'Comptés', icon: 'task_alt', cle: 'comptes' },
  { id: 'non_compte', label: 'Non comptés', icon: 'pending', cle: 'non_comptes' },
  { id: 'conforme', label: 'Sans écart', icon: 'check_circle', cle: 'sans_ecart', ton: 'ok' },
  { id: 'negatif', label: 'Écarts négatifs', icon: 'remove_circle', cle: 'ecarts_negatifs', ton: 'neg' },
  { id: 'positif', label: 'Écarts positifs', icon: 'add_circle', cle: 'ecarts_positifs', ton: 'pos' },
  { id: 'exclu', label: 'Exclus', icon: 'block', cle: 'exclus' },
];

@Component({
  selector: 'bea-stock-inventaire-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, DatePipe, MatIconModule, RouterLink, PaginationComponent, MgGedPanelComponent],
  styleUrls: ['./inventaire.css', './inventaire-rappro.css'],
  template: `
    <section class="bea-mg">
      <a class="inv-back" routerLink="/stock-fournitures/inventaires"><mat-icon>arrow_back</mat-icon> Inventaires</a>

      @if (inv(); as d) {
        <div class="inv-hero">
          <div class="inv-hero__top">
            <div>
              <p class="inv-hero__kicker">Inventaire mensuel · {{ d.reference }}</p>
              <h1>{{ d.libelle }}</h1>
              <div class="inv-hero__meta">
                <span class="inv-badge"><mat-icon>{{ statutIcon(d.statut) }}</mat-icon>{{ statutLabel(d.statut) }}</span>
                <span><mat-icon>event</mat-icon>{{ d.periode_libelle }} · {{ d.date_debut | date: 'dd/MM/yyyy' }}</span>
                <span><mat-icon>store</mat-icon>{{ d.agence_libelle || 'Toutes agences' }}</span>
                @if (d.famille_libelle) {
                  <span><mat-icon>category</mat-icon>{{ d.famille_libelle }}</span>
                }
                <span><mat-icon>person</mat-icon>{{ d.responsable_nom || '—' }}</span>
                @if (d.source === 'IMPORT_EXCEL') {
                  <span><mat-icon>upload_file</mat-icon>Import {{ d.import_meta?.fichier }}</span>
                }
                <span title="Photo du stock théorique"><mat-icon>photo_camera</mat-icon>{{ d.snapshot_at | date: 'dd/MM/yyyy HH:mm' }}</span>
              </div>
            </div>
            <div class="inv-hero__actions">
              @if (peutExporter()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
              }
              @if (peutModifier()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirEdition()"><mat-icon>edit</mat-icon> Modifier</button>
              }
              @if (saisieOuverte() && !d.nb_ajustements) {
                <label class="bea-mg__btn bea-mg__btn--ghost" title="Classeur de rapprochement (Inventaire_Reference, Mouvements_A_Appliquer, Ecarts_Banque, Controle, Meta)">
                  <mat-icon>account_balance</mat-icon> Référence banque
                  <input type="file" accept=".xlsx" hidden (change)="choisirReference($event)" />
                </label>
              }
              @switch (d.statut) {
                @case ('BROUILLON') {
                  @if (peut('saisie')) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="enCours()" (click)="transition('demarrer')"><mat-icon>play_arrow</mat-icon> Démarrer le comptage</button>
                  }
                }
                @case ('EN_COURS') {
                  @if (peut('saisie')) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="enCours() || !d.stats.comptes" (click)="soumettre()"><mat-icon>send</mat-icon> Soumettre au contrôle</button>
                  }
                }
                @case ('A_CONTROLER') {
                  @if (peut('validation') || peut('gestion')) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="enCours()" (click)="reprendre()"><mat-icon>undo</mat-icon> Renvoyer en comptage</button>
                  }
                  @if (peut('validation')) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="enCours()" (click)="ouvrirValidation()"><mat-icon>verified</mat-icon> Valider</button>
                  }
                }
                @case ('VALIDE') {
                  @if (peut('ajustement')) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="enCours()" (click)="genererAjustements()"><mat-icon>published_with_changes</mat-icon> Générer les ajustements</button>
                  }
                }
                @case ('AJUSTE') {
                  @if (peut('validation') || peut('gestion')) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="enCours()" (click)="archiver()"><mat-icon>inventory_2</mat-icon> Archiver</button>
                  }
                }
              }
              @if (peutAnnuler()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="enCours()" (click)="annuler()"><mat-icon>block</mat-icon> Annuler</button>
              }
              @if (peutSupprimer()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="enCours()" (click)="supprimer()"><mat-icon>delete</mat-icon> Supprimer</button>
              }
            </div>
          </div>
          <div class="inv-hero__progress">
            <div>
              <span>{{ d.stats.comptes }} / {{ d.stats.a_compter }} articles comptés</span>
              <strong>{{ d.stats.progression }} %</strong>
            </div>
            <div class="inv-progress" [attr.data-complet]="d.stats.progression >= 100" role="progressbar" [attr.aria-valuenow]="d.stats.progression" aria-valuemin="0" aria-valuemax="100">
              <span [style.width.%]="d.stats.progression"></span>
            </div>
          </div>
        </div>

        @if (verrouille()) {
          <div class="inv-banner" data-ton="lock"><mat-icon>lock</mat-icon><span>{{ msgVerrou }}</span></div>
        }
        @if (d.statut === 'ANNULE' && d.motif_annulation) {
          <div class="inv-banner" data-ton="bad"><mat-icon>block</mat-icon><span>Annulé le {{ d.annule_at | date: 'dd/MM/yyyy HH:mm' }} — motif : {{ d.motif_annulation }}</span></div>
        }
        @if (d.mouvements_depuis > 0) {
          <div class="inv-banner" data-ton="warn">
            <mat-icon>warning</mat-icon>
            <span>{{ d.mouvements_depuis }} mouvement(s) de stock ont été enregistrés sur ce périmètre après la photo du théorique.
              Les écarts restent calculés sur le théorique figé ; les ajustements corrigeront uniquement l’écart constaté.</span>
          </div>
        }
        @if (d.validation_forcee) {
          <div class="inv-banner" data-ton="warn"><mat-icon>gpp_maybe</mat-icon><span>Validation forcée par {{ d.valide_by_nom }} avec des articles non comptés (non ajustés).</span></div>
        }
        @if (d.statut === 'A_CONTROLER') {
          <div class="inv-banner" data-ton="info"><mat-icon>rule</mat-icon><span>Comptage soumis au contrôle : vérifiez les écarts avant validation. Les corrections restent possibles pour le valideur.</span></div>
        }

        @if (d.stats.rapprochement) {
          <div class="bea-mg__panel inv-rappro">
            <div class="bea-mg__panel-top">
              <h2><mat-icon>account_balance</mat-icon> Rapprochement sur la référence banque</h2>
              @if (rappro(); as r) {
                <span class="inv-badge" [attr.data-ligne]="r.ok ? 'CONFORME' : r.en_attente ? 'NON_COMPTE' : 'ECART_NEGATIF'">
                  {{ r.ok ? 'Contrôles conformes' : r.en_attente ? 'Contrôles en attente des ajustements' : 'Contrôle(s) en échec' }}
                </span>
              }
            </div>
            <p class="inv-rappro__source">
              Source officielle : <strong>{{ meta()?.source_officielle || '—' }}</strong>
              · plan : {{ meta()?.fichier || '—' }}
              · inventaire au {{ meta()?.date_inventaire || '—' }} · comptage du {{ meta()?.date_comptage || '—' }}
            </p>
            <div class="inv-rappro__flux">
              <div><span>Stock système avant rapprochement</span><strong>{{ nombre(d.stats.total_systeme) }}</strong></div>
              <div data-ton="neg"><span>Ajustements ({{ d.nb_ajustements || d.stats.ajustements_prevus }})</span><strong>{{ signe(d.stats.ajustement_net) }}</strong></div>
              <div data-ton="ok"><span>Stock actuel banque (retenu)</span><strong>{{ nombre(d.stats.total_retenu) }}</strong></div>
              <div><span>Stock physique compté</span><strong>{{ nombre(d.stats.total_physique) }}</strong></div>
              <div [attr.data-ton]="d.stats.ecart_a_regulariser ? 'pos' : 'ok'"><span>Écart physique restant</span><strong>{{ signe(d.stats.ecart_a_regulariser) }}</strong></div>
            </div>
            @if (rappro()?.registre_ecarts?.length) {
              <h3 class="inv-section-title">Écarts d’inventaire à régulariser (non intégrés au stock)</h3>
              <div class="bea-mg__table-scroll">
                <table class="bea-mg__table">
                  <thead><tr><th>Article</th><th class="inv-num">Théorique banque</th><th class="inv-num">Physique</th><th class="inv-num">Stock retenu</th><th class="inv-num">Écart</th><th>Statut</th><th>Décision</th></tr></thead>
                  <tbody>
                    @for (e of rappro()!.registre_ecarts; track e.ligne_id) {
                      <tr>
                        <td><strong>{{ e.code }}</strong> — {{ e.designation }}</td>
                        <td class="inv-num">{{ e.theorique_reference }}</td>
                        <td class="inv-num">{{ e.stock_physique }}</td>
                        <td class="inv-num">{{ e.stock_retenu }}</td>
                        <td class="inv-num"><span class="inv-ecart" [attr.data-signe]="ton(e.ecart)">{{ signe(e.ecart) }}</span></td>
                        <td><span class="inv-badge" data-ligne="ECART_POSITIF">À régulariser</span></td>
                        <td>{{ e.decision }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
            @if (rappro(); as r) {
              <details class="inv-rappro__controles" [open]="!r.ok && !r.en_attente">
                <summary>Contrôles de clôture ({{ nbControlesOk() }} / {{ r.controles.length }} conformes)</summary>
                <ul>
                  @for (c of r.controles; track c.code) {
                    <li [attr.data-etat]="c.ok ? 'ok' : c.en_attente ? 'attente' : 'ko'">
                      <mat-icon>{{ c.ok ? 'check_circle' : c.en_attente ? 'schedule' : 'cancel' }}</mat-icon>
                      <span>{{ c.libelle }}</span>
                      <small>attendu {{ c.attendu }} · obtenu {{ c.obtenu }}</small>
                    </li>
                  }
                </ul>
              </details>
            }
          </div>
        }

        <div class="inv-kpis">
          @for (k of kpis; track k.id; let i = $index) {
            <button type="button" class="inv-kpi" [style.--i]="i" [attr.data-ton]="k.ton" [attr.data-actif]="filtre() === k.id" (click)="choisirFiltre(k.id)">
              <span><mat-icon>{{ k.icon }}</mat-icon>{{ k.label }}</span>
              <strong>{{ d.stats[k.cle] }}</strong>
            </button>
          }
          <div class="inv-kpi" style="cursor:default" [attr.data-ton]="d.stats.ecart_net < 0 ? 'neg' : d.stats.ecart_net > 0 ? 'pos' : 'ok'">
            <span><mat-icon>functions</mat-icon>Écart net</span>
            <strong>{{ signe(d.stats.ecart_net) }}</strong>
          </div>
        </div>

        <div class="bea-mg__panel">
          <div class="inv-toolbar" [formGroup]="recherche">
            <label class="bea-mg__field">
              <mat-icon>search</mat-icon>
              <input formControlName="q" placeholder="Code, désignation, référence…" aria-label="Rechercher un article" />
            </label>
            <select formControlName="famille_id" aria-label="Famille">
              <option value="">Toutes familles</option>
              @for (f of familles(); track f.id) {
                <option [value]="f.id">{{ f.libelle }}</option>
              }
            </select>
            <select [value]="filtre()" (change)="choisirFiltre($any($event.target).value)" aria-label="Filtre">
              <option value="">Toutes les lignes</option>
              <option value="non_compte">Non comptés</option>
              <option value="compte">Comptés</option>
              <option value="conforme">Sans écart</option>
              <option value="ecart">Avec écart</option>
              <option value="negatif">Écarts négatifs</option>
              <option value="positif">Écarts positifs</option>
              <option value="exclu">Exclus</option>
              <option value="ajustement">Avec ajustement de stock</option>
              @if (d.stats.rapprochement) {
                <option value="a_regulariser">Écarts à régulariser</option>
              }
            </select>
            <span class="bea-mg__count">{{ total() }} ligne(s)</span>
            @if (saisieOuverte() && peut('saisie') && (d.statut === 'BROUILLON' || d.statut === 'EN_COURS')) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirAjout()"><mat-icon>add</mat-icon> Ajouter un article</button>
            }
          </div>
          @if (saisieOuverte()) {
            <p style="margin:.6rem 1.15rem 0;font-size:.78rem;color:#64748b">
              <mat-icon style="font-size:.95rem;width:.95rem;height:.95rem;vertical-align:-.15rem">keyboard</mat-icon>
              Saisie rapide : tapez la quantité, <kbd>Entrée</kbd> enregistre et passe à l’article suivant, <kbd>Échap</kbd> annule la frappe.
            </p>
          }
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table inv-lignes">
              <thead>
                <tr>
                  <th class="inv-th-sort" (click)="trier('code')">Article <mat-icon>{{ iconeTri('code') }}</mat-icon></th>
                  <th class="inv-th-sort inv-col-opt" (click)="trier('famille')">Famille <mat-icon>{{ iconeTri('famille') }}</mat-icon></th>
                  <th class="inv-th-sort inv-num" (click)="trier('theorique')">Théorique <mat-icon>{{ iconeTri('theorique') }}</mat-icon></th>
                  <th class="inv-num">Physique</th>
                  <th class="inv-th-sort inv-num" (click)="trier('ecart')">Écart <mat-icon>{{ iconeTri('ecart') }}</mat-icon></th>
                  <th class="inv-num inv-col-opt">Écart %</th>
                  <th class="inv-col-opt">Statut</th>
                  <th class="bea-mg__th-actions"></th>
                </tr>
              </thead>
              <tbody>
                @for (l of lignes(); track l.id; let i = $index) {
                  <tr [attr.data-ligne]="l.statut_ligne" [attr.data-selected]="selection()?.id === l.id">
                    <td class="inv-article">
                      <strong>{{ l.article_code }}</strong>
                      <small>{{ l.article_designation }}@if (l.ajout_manuel) { · ajout manuel }</small>
                    </td>
                    <td class="inv-col-opt">{{ l.famille_libelle || '—' }}</td>
                    <td class="inv-num">
                      @if (l.stock_cible != null) {
                        {{ l.theorique_reference }}
                        @if (l.stock_theorique !== l.theorique_reference) {
                          <br /><small style="color:#92400e" title="Stock BEA DIGITAL figé avant rapprochement">système : {{ l.stock_theorique }}</small>
                        }
                      } @else {
                        {{ l.stock_theorique }}
                        @if (l.stock_theorique_source != null && l.stock_theorique_source !== l.stock_theorique) {
                          <br /><small style="color:#92400e" title="Théorique du fichier importé">fichier : {{ l.stock_theorique_source }}</small>
                        }
                      }
                    </td>
                    <td class="inv-num">
                      @if (saisieOuverte() && l.statut_comptage !== 'EXCLU') {
                        <span class="inv-saisie">
                          <input
                            #saisie
                            type="number"
                            inputmode="numeric"
                            min="0"
                            step="1"
                            [attr.data-index]="i"
                            [attr.data-etat]="etats()[l.id]"
                            [value]="brouillons()[l.id] ?? l.stock_physique ?? ''"
                            [attr.aria-label]="'Stock physique ' + l.article_code"
                            (input)="taper(l, $event)"
                            (keydown.enter)="$event.preventDefault(); enregistrer(l, i, true)"
                            (keydown.escape)="$event.stopPropagation(); annulerFrappe(l, $event)"
                            (blur)="enregistrer(l, i, false)"
                          />
                          <span class="inv-save" [attr.data-etat]="etats()[l.id]" aria-live="polite">
                            @switch (etats()[l.id]) {
                              @case ('saving') { <mat-icon>autorenew</mat-icon> Enregistrement… }
                              @case ('ok') { <mat-icon>check</mat-icon> Enregistré }
                              @case ('erreur') { <mat-icon>error</mat-icon> Erreur }
                            }
                          </span>
                        </span>
                      } @else {
                        {{ l.stock_physique ?? '—' }}
                      }
                    </td>
                    <td class="inv-num">
                      <span class="inv-ecart" [attr.data-signe]="ton(l.ecart)">{{ l.ecart == null ? '—' : signe(l.ecart) }}</span>
                      @if (l.stock_cible != null && l.ajustement_prevu) {
                        <br /><small title="Ajustement de stock vers le stock retenu ({{ l.stock_cible }})">ajust. {{ signe(l.ajustement_prevu) }}</small>
                      }
                    </td>
                    <td class="inv-num inv-col-opt">{{ l.ecart == null ? '—' : pourcentage(l.ecart_pourcentage) }}</td>
                    <td class="inv-col-opt">
                      @if (l.ancienne_agence) {
                        <span class="inv-badge" data-ligne="EXCLU">Ancienne agence</span>
                      } @else {
                        <span class="inv-badge" [attr.data-ligne]="l.statut_ligne">{{ ligneLabel(l.statut_ligne) }}</span>
                      }
                      @if (l.a_regulariser) {
                        <span class="inv-badge" data-ligne="ECART_POSITIF" title="Écart physique non intégré au stock">À régulariser</span>
                      }
                    </td>
                    <td class="bea-mg__actions-cell">
                      <button type="button" class="bea-mg__icon-btn" title="Détail de la ligne" (click)="ouvrirLigne(l)"><mat-icon>chevron_right</mat-icon></button>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="8" class="bea-mg__empty">
                      <mat-icon>search_off</mat-icon>
                      <p>{{ chargementLignes() ? 'Chargement…' : 'Aucune ligne pour ce filtre.' }}</p>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          @if (total() > taille) {
            <app-pagination [page]="page()" [total]="total()" [pageSize]="taille" label="ligne(s)" (pageChange)="allerPage($event)" />
          }
        </div>

        @if (ajustements().length) {
          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Ajustements de stock générés</h2>
              <span class="bea-mg__count">{{ ajustements().length }} mouvement(s) · {{ d.ajustements_at | date: 'dd/MM/yyyy HH:mm' }} par {{ d.ajustements_by_nom }}</span>
            </div>
            <div class="bea-mg__table-scroll">
              <table class="bea-mg__table">
                <thead><tr><th>Mouvement</th><th>Article</th><th class="inv-num">Quantité</th><th>Détail</th></tr></thead>
                <tbody>
                  @for (a of ajustements(); track a.id) {
                    <tr>
                      <td><code class="bea-mg__code">{{ a.reference }}</code></td>
                      <td>{{ a.article_code }} — {{ a.article_designation }}</td>
                      <td class="inv-num"><span class="inv-ecart" [attr.data-signe]="ton(a.quantite)">{{ signe(a.quantite) }}</span></td>
                      <td>{{ a.observation }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        }

        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Historique</h2>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="chargerHistorique()"><mat-icon>refresh</mat-icon></button>
          </div>
          <div style="padding:1rem 1.15rem">
            <ul class="inv-timeline">
              @for (h of historique(); track h.id) {
                <li>
                  <strong>{{ actionLabel(h.action) }}</strong>
                  @if (h.entity === 'mg_inventaire_ligne' && h.after?.['article']) { · {{ h.after?.['article'] }} }
                  <small>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }} · {{ h.user_nom || 'Système' }}{{ resumeAudit(h) }}</small>
                </li>
              } @empty {
                <li><small>Aucun événement.</small></li>
              }
            </ul>
          </div>
        </div>

        <bea-mg-ged moduleCode="stock-fournitures" entity="inventaire" [entityId]="d.id" />
      } @else {
        <div class="inv-skeleton" style="height:9rem"></div>
        <div class="inv-skeleton"></div>
        <div class="inv-skeleton"></div>
      }

      @if (selection(); as s) {
        <div class="bea-mg__backdrop" (click)="fermerLigne()" role="presentation"></div>
        <aside class="inv-side" role="dialog" aria-modal="true" [attr.aria-label]="'Ligne ' + s.article_code">
          <header>
            <div>
              <p class="bea-stock-page__kicker">{{ s.article_code }} · <span class="inv-badge" [attr.data-ligne]="s.statut_ligne">{{ ligneLabel(s.statut_ligne) }}</span></p>
              <h2>{{ s.article_designation }}</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="fermerLigne()" title="Fermer"><mat-icon>close</mat-icon></button>
          </header>
          <div class="inv-side__body">
            <dl>
              <dt>Famille</dt><dd>{{ s.famille_libelle || '—' }}</dd>
              <dt>Unité</dt><dd>{{ s.unite || '—' }}</dd>
              <dt>Emplacement</dt><dd>{{ s.emplacement || '—' }}</dd>
              <dt>Stock système (figé)</dt><dd>{{ s.stock_theorique }}</dd>
              @if (s.stock_theorique_source != null) {
                <dt>{{ s.stock_cible != null || s.ancienne_agence ? 'Théorique banque' : 'Théorique du fichier' }}</dt><dd>{{ s.stock_theorique_source }}</dd>
              }
              <dt>Stock physique</dt><dd>{{ s.stock_physique ?? '—' }}</dd>
              <dt>Écart</dt><dd><span class="inv-ecart" [attr.data-signe]="ton(s.ecart)">{{ s.ecart == null ? '—' : signe(s.ecart) }}</span></dd>
              @if (s.stock_cible != null) {
                <dt>Stock retenu (banque)</dt><dd>{{ s.stock_cible }}</dd>
                <dt>Ajustement de stock</dt><dd><span class="inv-ecart" [attr.data-signe]="ton(s.ajustement_prevu)">{{ signe(s.ajustement_prevu) }}</span></dd>
                <dt>Écart à régulariser</dt><dd>{{ s.ecart_a_regulariser ? signe(s.ecart_a_regulariser) + ' — non intégré au stock' : '—' }}</dd>
              }
              <dt>Écart %</dt><dd>{{ s.ecart == null ? '—' : pourcentage(s.ecart_pourcentage) }}</dd>
              <dt>Compté par</dt><dd>{{ s.compte_par_nom || '—' }}</dd>
              <dt>Compté le</dt><dd>{{ (s.compte_at | date: 'dd/MM/yyyy HH:mm') || '—' }}</dd>
            </dl>

            @if (s.donnees_source; as src) {
              <div>
                <h3 class="inv-section-title">Référence banque (historique, non rejoué)</h3>
                <dl>
                  @for (c of champsSource; track c.cle) {
                    @if (src[c.cle] != null && src[c.cle] !== '') {
                      <dt>{{ c.label }}</dt><dd>{{ src[c.cle] }}</dd>
                    }
                  }
                </dl>
              </div>
            }

            @if (saisieOuverte()) {
              <div>
                <h3 class="inv-section-title">Commentaire</h3>
                <textarea rows="3" maxlength="255" [value]="commentaire()" (input)="commentaire.set($any($event.target).value)"></textarea>
                <div style="display:flex;gap:.45rem;flex-wrap:wrap;margin-top:.5rem">
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="enCours() || commentaire() === (s.observation || '')" (click)="sauverCommentaire(s)"><mat-icon>save</mat-icon> Enregistrer</button>
                  @if (s.statut_comptage === 'EXCLU') {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="enCours()" (click)="exclure(s, false)"><mat-icon>undo</mat-icon> Réintégrer au comptage</button>
                  } @else {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="enCours()" (click)="exclure(s, true)"><mat-icon>block</mat-icon> Exclure du comptage</button>
                  }
                  @if (s.statut_comptage === 'COMPTE') {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="enCours()" (click)="effacer(s)"><mat-icon>backspace</mat-icon> Effacer le comptage</button>
                  }
                  @if (peutRetirer(s)) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="enCours()" (click)="retirer(s)"><mat-icon>delete</mat-icon> Retirer</button>
                  }
                </div>
              </div>
            } @else if (s.observation) {
              <div><h3 class="inv-section-title">Commentaire</h3><p style="margin:0">{{ s.observation }}</p></div>
            }

            <div>
              <h3 class="inv-section-title">Historique de la ligne</h3>
              <ul class="inv-timeline">
                @for (h of historiqueLigne(); track h.id) {
                  <li>
                    <strong>{{ actionLabel(h.action) }}</strong>
                    <small>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }} · {{ h.user_nom || 'Système' }}{{ resumeAudit(h) }}</small>
                  </li>
                } @empty {
                  <li><small>Aucune modification enregistrée.</small></li>
                }
              </ul>
            </div>
          </div>
        </aside>
      }

      @if (validation(); as v) {
        <div class="bea-mg__backdrop" (click)="validation.set(null)" role="presentation"></div>
        <div class="bea-mg__modal" role="dialog" aria-modal="true" aria-label="Valider l’inventaire">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Validation</p>
              <h2>Valider {{ inv()?.reference }}</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="validation.set(null)" title="Fermer"><mat-icon>close</mat-icon></button>
          </header>
          <div class="bea-mg__modal-body">
            <div class="inv-resume">
              <div><span>À compter</span><strong>{{ v.a_compter }}</strong></div>
              <div><span>Comptés</span><strong>{{ v.comptes }}</strong></div>
              <div [attr.data-ton]="v.non_comptes ? 'bad' : null"><span>Non comptés</span><strong>{{ v.non_comptes }}</strong></div>
              <div><span>Exclus</span><strong>{{ v.exclus }}</strong></div>
              <div [attr.data-ton]="v.ecarts ? 'warn' : null"><span>Écarts</span><strong>{{ v.ecarts }}</strong></div>
              <div><span>Écart net</span><strong>{{ signe(v.ecart_net) }}</strong></div>
            </div>
            <ul class="inv-msgs">
              @if (v.message) {
                <li data-ton="bad"><mat-icon>error</mat-icon><span>{{ v.message }}</span></li>
              }
              @if (v.mouvements_depuis) {
                <li data-ton="warn"><mat-icon>warning</mat-icon><span>{{ v.mouvements_depuis }} mouvement(s) enregistrés depuis la photo du théorique.</span></li>
              }
              <li data-ton="info"><mat-icon>lock</mat-icon><span>Après validation, les comptages sont verrouillés. Les ajustements de stock ({{ v.ecarts_negatifs }} négatif(s), {{ v.ecarts_positifs }} positif(s)) seront générés dans une étape séparée.</span></li>
            </ul>
            @if (!v.peut_valider && v.peut_forcer) {
              <label style="display:grid;gap:.3rem;font-size:.85rem">
                <span><input type="checkbox" [checked]="forcer()" (change)="forcer.set($any($event.target).checked)" /> Forcer la validation malgré les articles non comptés (ils ne seront pas ajustés)</span>
                @if (forcer()) {
                  <textarea rows="2" maxlength="2000" placeholder="Motif du forçage (obligatoire)" [value]="motifForcage()" (input)="motifForcage.set($any($event.target).value)"></textarea>
                }
              </label>
            }
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="validation.set(null)">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="enCours() || !(v.peut_valider || (forcer() && motifForcage().trim()))" (click)="valider()">
              <mat-icon>verified</mat-icon> Valider l’inventaire
            </button>
          </footer>
        </div>
      }

      @if (editionOuverte() && inv(); as d) {
        <div class="bea-mg__backdrop" (click)="editionOuverte.set(false)" role="presentation"></div>
        <div class="bea-mg__modal" role="dialog" aria-modal="true" aria-label="Modifier l’inventaire">
          <header class="bea-mg__modal-head">
            <div><p class="bea-stock-page__kicker">Modification</p><h2>{{ d.reference }}</h2></div>
            <button type="button" class="bea-mg__icon-btn" (click)="editionOuverte.set(false)" title="Fermer"><mat-icon>close</mat-icon></button>
          </header>
          <form [formGroup]="edition" (ngSubmit)="enregistrerEdition()">
            <div class="bea-mg__modal-body">
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">Libellé<input formControlName="libelle" maxlength="255" /></label>
                @if (d.statut === 'BROUILLON') {
                  <label>Date d’inventaire<input type="date" formControlName="date_debut" /></label>
                  <label>Agence
                    <select formControlName="agence_id">
                      <option value="">Toutes agences</option>
                      @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
                    </select>
                  </label>
                  <label class="bea-mg__span2">Famille
                    <select formControlName="famille_id">
                      <option value="">Toutes familles</option>
                      @for (f of familles(); track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
                    </select>
                  </label>
                }
                <label class="bea-mg__span2">Responsable<input formControlName="responsable_nom" maxlength="160" /></label>
                <label class="bea-mg__span2">Observations<textarea formControlName="observation" rows="3"></textarea></label>
              </div>
              <ul class="inv-msgs">
                <li data-ton="info"><mat-icon>info</mat-icon><span>
                  @if (d.statut === 'BROUILLON') {
                    Changer la date ou le périmètre recalcule la photo du stock théorique (aucun comptage n’est encore saisi).
                  } @else {
                    Comptage commencé : la date et le périmètre sont figés.
                  }
                </span></li>
              </ul>
            </div>
            <footer class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="editionOuverte.set(false)">Annuler</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="edition.invalid || edition.pristine || enCours()"><mat-icon>save</mat-icon> Enregistrer</button>
            </footer>
          </form>
        </div>
      }

      @if (ajoutOuvert()) {
        <div class="bea-mg__backdrop" (click)="ajoutOuvert.set(false)" role="presentation"></div>
        <div class="bea-mg__modal" role="dialog" aria-modal="true" aria-label="Ajouter un article">
          <header class="bea-mg__modal-head">
            <div><p class="bea-stock-page__kicker">Ajout manuel</p><h2>Ajouter un article à l’inventaire</h2></div>
            <button type="button" class="bea-mg__icon-btn" (click)="ajoutOuvert.set(false)" title="Fermer"><mat-icon>close</mat-icon></button>
          </header>
          <div class="bea-mg__modal-body">
            <div class="bea-mg__grid bea-mg__grid--1">
              <label>Article
                <select [value]="articleAjout()" (change)="articleAjout.set($any($event.target).value)">
                  <option value="">— choisir —</option>
                  @for (a of articles(); track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.designation }}</option> }
                </select>
              </label>
            </div>
            <ul class="inv-msgs"><li data-ton="info"><mat-icon>info</mat-icon><span>Le stock théorique de l’article est figé à la date de l’inventaire.</span></li></ul>
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ajoutOuvert.set(false)">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!articleAjout() || enCours()" (click)="ajouterArticle()"><mat-icon>add</mat-icon> Ajouter</button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class StockInventaireDetailComponent implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  private readonly alertes = inject(StockAlertesWatcherService);

  readonly kpis = KPIS;
  readonly taille = 50;
  readonly msgVerrou = MSG_VERROU;
  readonly signe = signe;
  readonly pourcentage = pourcentage;

  readonly inv = signal<Inventaire | null>(null);
  readonly lignes = signal<InventaireLigne[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly filtre = signal<LigneFiltre>('');
  readonly tri = signal<{ col: string; sens: 'asc' | 'desc' }>({ col: 'ordre', sens: 'asc' });
  readonly chargementLignes = signal(false);
  readonly familles = signal<RefOption[]>([]);
  readonly agences = signal<RefOption[]>([]);
  readonly articles = signal<ArticleOption[]>([]);
  readonly historique = signal<InventaireHistorique[]>([]);
  readonly ajustements = signal<Ajustement[]>([]);
  readonly rappro = signal<Rapprochement | null>(null);
  readonly meta = computed(() => this.inv()?.import_meta?.rapprochement ?? null);
  readonly nbControlesOk = computed(() => this.rappro()?.controles.filter((c) => c.ok).length ?? 0);
  readonly champsSource = CHAMPS_SOURCE;
  readonly enCours = signal(false);

  readonly brouillons = signal<Partial<Record<string, string>>>({});
  readonly etats = signal<Partial<Record<string, EtatSaisie>>>({});
  private readonly enregistrements = new Set<string>();
  private readonly timers = new Map<string, ReturnType<typeof setTimeout>>();

  readonly selection = signal<InventaireLigne | null>(null);
  readonly historiqueLigne = signal<InventaireHistorique[]>([]);
  readonly commentaire = signal('');

  readonly validation = signal<ValidationPreview | null>(null);
  readonly forcer = signal(false);
  readonly motifForcage = signal('');

  readonly editionOuverte = signal(false);
  readonly ajoutOuvert = signal(false);
  readonly articleAjout = signal('');

  private readonly saisies = viewChildren<ElementRef<HTMLInputElement>>('saisie');

  readonly recherche = this.fb.nonNullable.group({ q: '', famille_id: '' });
  readonly edition = this.fb.nonNullable.group({
    libelle: ['', Validators.required],
    date_debut: '',
    agence_id: '',
    famille_id: '',
    responsable_nom: '',
    observation: '',
  });

  readonly verrouille = computed(() => {
    const d = this.inv();
    return !!d && VERROUILLES.has(d.statut);
  });
  readonly saisieOuverte = computed(() => {
    const d = this.inv();
    if (!d) return false;
    if (d.statut === 'BROUILLON' || d.statut === 'EN_COURS') return this.peut('saisie') || this.peut('validation');
    if (d.statut === 'A_CONTROLER') return this.peut('validation') || this.peut('gestion');
    return false;
  });
  readonly peutExporter = computed(() => this.peut('export'));
  readonly peutModifier = computed(() => {
    const d = this.inv();
    if (!d || this.verrouille()) return false;
    return d.statut === 'A_CONTROLER' ? this.peut('validation') || this.peut('gestion') : this.peut('saisie');
  });
  readonly peutAnnuler = computed(() => {
    const d = this.inv();
    return !!d && this.peut('gestion') && ['BROUILLON', 'EN_COURS', 'A_CONTROLER', 'VALIDE'].includes(d.statut) && !d.nb_ajustements;
  });
  readonly peutSupprimer = computed(() => {
    const d = this.inv();
    return !!d && this.peut('gestion') && (d.statut === 'BROUILLON' || d.statut === 'ANNULE') && !d.nb_ajustements;
  });

  readonly hasUnsavedChanges = unsavedChanges(
    () =>
      Object.keys(this.brouillons()).length > 0 ||
      this.enregistrements.size > 0 ||
      (this.editionOuverte() && this.edition.dirty),
  );

  private readonly rechargeLignes$ = new Subject<void>();

  constructor() {
    this.recherche.valueChanges.pipe(debounceTime(300), takeUntilDestroyed()).subscribe(() => {
      this.page.set(1);
      this.chargerLignes();
    });
    this.rechargeLignes$.pipe(debounceTime(150), takeUntilDestroyed()).subscribe(() => this.chargerLignes());
  }

  ngOnInit(): void {
    this.api.get<RefOption[]>('/mg/stock/familles').subscribe({ next: (f) => this.familles.set(f) });
    this.api.get<RefOption[]>('/mg/stock/agences').subscribe({ next: (a) => this.agences.set(a) });
    this.charger();
    this.chargerLignes();
    this.chargerHistorique();
  }

  peut(cle: keyof typeof PERM): boolean {
    return aPermission(this.auth.user(), PERM[cle]);
  }

  statutLabel(s: InventaireStatut): string {
    return STATUT_LABELS[s] ?? s;
  }

  statutIcon(s: InventaireStatut): string {
    return STATUT_ICONS[s] ?? 'help';
  }

  ligneLabel(s: LigneStatut): string {
    return LIGNE_LABELS[s] ?? s;
  }

  actionLabel(a: string): string {
    return ACTION_LABELS[a] ?? a;
  }

  ton(n: number | null | undefined): string {
    if (n == null) return '';
    return n < 0 ? 'moins' : n > 0 ? 'plus' : 'zero';
  }

  resumeAudit(h: InventaireHistorique): string {
    const a = h.after ?? {};
    const b = h.before ?? {};
    if (h.action === 'saisie_physique') {
      const avant = b['stock_physique'] ?? '—';
      const apres = a['stock_physique'] ?? '—';
      const statut = a['statut_comptage'] === 'EXCLU' ? ' (exclu)' : '';
      return ` · ${avant} → ${apres}${a['ecart'] != null ? ` (écart ${signe(a['ecart'] as number)})` : ''}${statut}`;
    }
    if (a['motif']) return ` · motif : ${a['motif']}`;
    if (h.action === 'rapprochement') {
      return ` · stock ${a['stock_avant']} → ${a['stock_apres']} (${signe(a['variation'] as number)}, ${a['ajustements']} ajustement(s)) · contrôle ${a['controle']}`;
    }
    if (h.action === 'chargement_reference') return ` · ${a['fichier'] ?? ''} · comptage du ${a['date_comptage'] ?? '—'}`;
    if (h.action === 'generer_ajustements' && a['ajustements'] != null) return ` · ${a['ajustements']} mouvement(s)`;
    if (h.action === 'import_excel' && a['fichier']) return ` · ${a['fichier']}`;
    return '';
  }

  charger(): void {
    this.api.get<Inventaire>(`/mg/stock/inventaires/${this.id()}`).subscribe({
      next: (inv) => {
        this.inv.set(inv);
        if (inv.nb_ajustements) this.chargerAjustements();
        if (inv.stats.rapprochement) this.chargerRapprochement();
      },
      error: () => {
        this.feedback.error({ title: 'Inventaire introuvable' });
        this.router.navigate(['/stock-fournitures/inventaires']);
      },
    });
  }

  chargerLignes(): void {
    const v = this.recherche.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.taille,
      tri: this.tri().col,
      sens: this.tri().sens,
    };
    if (v.q.trim()) params['q'] = v.q.trim();
    if (v.famille_id) params['famille_id'] = v.famille_id;
    if (this.filtre()) params['filtre'] = this.filtre();
    this.chargementLignes.set(true);
    this.api.get<Paginated<InventaireLigne>>(`/mg/stock/inventaires/${this.id()}/lignes`, params).subscribe({
      next: (r) => {
        this.lignes.set(r.items);
        this.total.set(r.total);
        this.chargementLignes.set(false);
      },
      error: () => {
        this.chargementLignes.set(false);
        this.feedback.error({ title: 'Chargement des lignes impossible' });
      },
    });
  }

  chargerHistorique(): void {
    this.api
      .get<InventaireHistorique[]>(`/mg/stock/inventaires/${this.id()}/historique`)
      .subscribe({ next: (h) => this.historique.set(h) });
  }

  chargerAjustements(): void {
    this.api
      .get<Ajustement[]>(`/mg/stock/inventaires/${this.id()}/ajustements`)
      .subscribe({ next: (a) => this.ajustements.set(a) });
  }

  chargerRapprochement(): void {
    this.api
      .get<Rapprochement>(`/mg/stock/inventaires/${this.id()}/rapprochement`)
      .subscribe({ next: (r) => this.rappro.set(r) });
  }

  nombre(n: number | null | undefined): string {
    return n == null ? '—' : Number(n).toLocaleString('fr-FR');
  }

  choisirReference(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    const url = `/mg/stock/inventaires/${this.id()}/reference`;
    this.feedback
      .run(() => this.api.upload<ReferenceAnalyse>(`${url}/analyse`, file), {
        loading: 'Analyse de la référence…',
        busy: this.enCours,
        errorTitle: 'Référence illisible',
        success: () => null,
      })
      .subscribe((a) => {
        if (a.bloquant) {
          this.feedback.error({
            title: 'Référence refusée — aucune donnée modifiée',
            message: a.anomalies.slice(0, 8).join('\n') + (a.anomalies.length > 8 ? `\n… ${a.anomalies.length - 8} autre(s)` : ''),
          });
          return;
        }
        const c = a.calcul;
        this.feedback
          .run(() => this.api.upload<{ inventaire: Inventaire }>(url, file), {
            confirm: {
              title: 'Charger la référence banque',
              message:
                `${c['references']} références (${c['agence_actuelle']} agence actuelle, ${c['ancienne_agence']} ancienne agence). ` +
                `Stock système ${this.nombre(c['stock_systeme'])} → stock retenu ${this.nombre(c['stock_final'])} ` +
                `(${c['nb_mouvements']} ajustement(s), ${signe(c['variation'])}). Physique ${this.nombre(c['stock_physique'])}.`,
              hint:
                (a.registre_ecarts.length
                  ? `Écart(s) à régulariser conservés sans mouvement : ${a.registre_ecarts.map((e) => `${e.code} ${signe(e.ecart)}`).join(', ')}. `
                  : '') + 'Les comptages de l’inventaire sont remplacés par ceux de la banque ; aucun mouvement n’est créé à cette étape.',
              confirmLabel: 'Charger',
              tone: 'warn',
              icon: 'account_balance',
            },
            loading: 'Chargement de la référence…',
            busy: this.enCours,
            errorTitle: 'Chargement refusé',
            success: () => ({ title: 'Référence banque chargée', details: [{ label: 'Fichier', value: a.fichier }] }),
          })
          .subscribe((r) => this.apresTransition(r.inventaire));
      });
  }

  choisirFiltre(f: LigneFiltre): void {
    this.filtre.set(this.filtre() === f && f !== '' ? '' : f);
    this.page.set(1);
    this.chargerLignes();
  }

  trier(col: string): void {
    const t = this.tri();
    this.tri.set({ col, sens: t.col === col && t.sens === 'asc' ? 'desc' : 'asc' });
    this.chargerLignes();
  }

  iconeTri(col: string): string {
    const t = this.tri();
    if (t.col !== col) return 'unfold_more';
    return t.sens === 'asc' ? 'arrow_upward' : 'arrow_downward';
  }

  allerPage(p: number): void {
    this.page.set(p);
    this.chargerLignes();
  }

  /* ---------------- saisie rapide ---------------- */

  taper(l: InventaireLigne, event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    this.brouillons.update((b) => ({ ...b, [l.id]: val }));
    if (this.etats()[l.id] === 'erreur') this.setEtat(l.id, null);
  }

  annulerFrappe(l: InventaireLigne, event: Event): void {
    const input = event.target as HTMLInputElement;
    input.value = l.stock_physique == null ? '' : String(l.stock_physique);
    this.retirerBrouillon(l.id);
    this.setEtat(l.id, null);
    input.blur();
  }

  enregistrer(l: InventaireLigne, index: number, suivant: boolean): void {
    const brut = this.brouillons()[l.id];
    if (suivant) this.focusLigne(index + 1);
    if (brut === undefined) return;
    const texte = brut.trim();
    const actuel = l.stock_physique == null ? '' : String(l.stock_physique);
    if (texte === actuel) {
      this.retirerBrouillon(l.id);
      return;
    }
    let body: Record<string, unknown>;
    if (texte === '') {
      body = { effacer: true };
    } else {
      const n = Number(texte);
      if (!Number.isInteger(n) || n < 0) {
        this.setEtat(l.id, 'erreur');
        this.feedback.warning({ title: 'Quantité invalide', message: `${l.article_code} : saisissez un entier positif ou nul.` });
        return;
      }
      body = { stock_physique: n };
    }
    if (this.enregistrements.has(l.id)) return;
    this.enregistrements.add(l.id);
    this.setEtat(l.id, 'saving');
    this.api.patch<SaveOut>(`/mg/stock/inventaires/${this.id()}/lignes/${l.id}`, body).subscribe({
      next: (r) => {
        this.enregistrements.delete(l.id);
        if ((this.brouillons()[l.id] ?? '').trim() === texte) this.retirerBrouillon(l.id);
        this.appliquerSauvegarde(r);
        this.setEtat(l.id, 'ok');
        const t = setTimeout(() => this.setEtat(l.id, null), 2200);
        clearTimeout(this.timers.get(l.id));
        this.timers.set(l.id, t);
      },
      error: (err) => {
        this.enregistrements.delete(l.id);
        this.setEtat(l.id, 'erreur');
        const detail = err?.error?.message || err?.error?.detail?.message || 'Enregistrement impossible.';
        this.feedback.error({ title: `Saisie refusée — ${l.article_code}`, message: `${detail}\nVotre saisie est conservée à l’écran.`, requestId: err?.error?.request_id });
        if (err?.status === 409) this.charger();
      },
    });
  }

  private appliquerSauvegarde(r: SaveOut): void {
    this.lignes.update((ls) => ls.map((x) => (x.id === r.ligne.id ? r.ligne : x)));
    if (this.selection()?.id === r.ligne.id) this.selection.set(r.ligne);
    this.inv.update((d) => (d ? { ...d, stats: r.stats, statut: r.statut } : d));
  }

  private focusLigne(index: number): void {
    const cible = this.saisies().find((e) => Number(e.nativeElement.dataset['index']) === index);
    if (cible) {
      cible.nativeElement.focus();
      cible.nativeElement.select();
    } else if (index >= this.lignes().length && this.page() * this.taille < this.total()) {
      this.feedback.info({ title: 'Fin de la page', message: 'Passez à la page suivante pour continuer la saisie.' });
    }
  }

  private retirerBrouillon(id: string): void {
    this.brouillons.update((b) => {
      const { [id]: _, ...reste } = b;
      return reste;
    });
  }

  private setEtat(id: string, etat: EtatSaisie | null): void {
    this.etats.update((e) => {
      const next = { ...e };
      if (etat) next[id] = etat;
      else delete next[id];
      return next;
    });
  }

  /* ---------------- panneau ligne ---------------- */

  ouvrirLigne(l: InventaireLigne): void {
    this.selection.set(l);
    this.commentaire.set(l.observation ?? '');
    this.historiqueLigne.set([]);
    this.api
      .get<{ ligne: InventaireLigne; historique: InventaireHistorique[] }>(`/mg/stock/inventaires/${this.id()}/lignes/${l.id}`)
      .subscribe({
        next: (r) => {
          this.selection.set(r.ligne);
          this.historiqueLigne.set(r.historique);
        },
      });
  }

  fermerLigne(): void {
    this.selection.set(null);
  }

  private patchLigne(l: InventaireLigne, body: Record<string, unknown>, titre: string): void {
    this.feedback
      .run(() => this.api.patch<SaveOut>(`/mg/stock/inventaires/${this.id()}/lignes/${l.id}`, body), {
        loading: 'Enregistrement…',
        busy: this.enCours,
        errorTitle: 'Modification refusée',
        success: { title: titre, details: [{ label: 'Article', value: l.article_code ?? '' }] },
      })
      .subscribe((r) => {
        this.appliquerSauvegarde(r);
        this.commentaire.set(r.ligne.observation ?? '');
        this.ouvrirLigne(r.ligne);
        this.rechargeLignes$.next();
      });
  }

  sauverCommentaire(l: InventaireLigne): void {
    this.patchLigne(l, { commentaire: this.commentaire() }, 'Commentaire enregistré');
  }

  exclure(l: InventaireLigne, exclure: boolean): void {
    this.patchLigne(l, { exclure }, exclure ? 'Article exclu du comptage' : 'Article réintégré');
  }

  effacer(l: InventaireLigne): void {
    this.feedback
      .confirm({ action: 'suppression', title: 'Effacer le comptage', message: `Effacer le stock physique saisi pour ${l.article_code} ?`, hint: 'L’article redeviendra « non compté ».' })
      .subscribe((ok) => ok && this.patchLigne(l, { effacer: true }, 'Comptage effacé'));
  }

  peutRetirer(l: InventaireLigne): boolean {
    const d = this.inv();
    if (!d || !this.peut('saisie')) return false;
    return d.statut === 'BROUILLON' || (d.statut === 'EN_COURS' && l.ajout_manuel);
  }

  retirer(l: InventaireLigne): void {
    this.feedback
      .run(() => this.api.delete<void>(`/mg/stock/inventaires/${this.id()}/lignes/${l.id}`), {
        confirm: { action: 'suppression', message: `Retirer ${l.article_code} — ${l.article_designation} de l’inventaire ?` },
        loading: 'Suppression…',
        busy: this.enCours,
        errorTitle: 'Suppression refusée',
        success: { title: 'Article retiré de l’inventaire' },
      })
      .subscribe(() => {
        this.fermerLigne();
        this.charger();
        this.chargerLignes();
      });
  }

  ouvrirAjout(): void {
    this.articleAjout.set('');
    this.ajoutOuvert.set(true);
    if (!this.articles().length) {
      this.api.get<Paginated<ArticleOption>>('/mg/stock/articles', { size: 500 }).subscribe({ next: (r) => this.articles.set(r.items) });
    }
  }

  ajouterArticle(): void {
    const articleId = this.articleAjout();
    if (!articleId) return;
    this.feedback
      .run(() => this.api.post<InventaireLigne>(`/mg/stock/inventaires/${this.id()}/lignes`, { article_id: articleId }), {
        loading: 'Ajout…',
        busy: this.enCours,
        errorTitle: 'Ajout refusé',
        success: (l) => ({ title: 'Article ajouté', details: [{ label: 'Article', value: l.article_code ?? '' }, { label: 'Théorique', value: String(l.stock_theorique) }] }),
      })
      .subscribe(() => {
        this.ajoutOuvert.set(false);
        this.charger();
        this.chargerLignes();
      });
  }

  /* ---------------- workflow ---------------- */

  private apresTransition(inv: Inventaire): void {
    this.inv.set(inv);
    this.brouillons.set({});
    this.etats.set({});
    this.chargerLignes();
    this.chargerHistorique();
    if (inv.nb_ajustements) this.chargerAjustements();
    if (inv.stats.rapprochement) this.chargerRapprochement();
    this.alertes.refresh(true);
  }

  private post(action: string, extra: Record<string, unknown> = {}): Observable<Inventaire> {
    return this.api.post<Inventaire>(`/mg/stock/inventaires/${this.id()}/transition`, { action, ...extra });
  }

  private succes(titre: string) {
    return (inv: Inventaire) => ({
      title: titre,
      details: [
        { label: 'Référence', value: inv.reference },
        { label: 'Statut', value: this.statutLabel(inv.statut) },
      ],
    });
  }

  transition(action: 'demarrer'): void {
    this.feedback
      .run(() => this.post(action), { loading: 'Démarrage…', busy: this.enCours, errorTitle: 'Action refusée', success: this.succes('Comptage démarré') })
      .subscribe((inv) => this.apresTransition(inv));
  }

  soumettre(): void {
    const d = this.inv();
    if (!d) return;
    if (Object.keys(this.brouillons()).length) {
      this.feedback.warning({ title: 'Saisies en attente', message: 'Validez ou annulez les quantités en cours de frappe avant de soumettre.' });
      return;
    }
    this.feedback
      .run(() => this.post('soumettre'), {
        confirm: {
          action: 'soumission',
          message: `Soumettre ${d.reference} au contrôle ?`,
          hint: d.stats.non_comptes
            ? `${d.stats.non_comptes} article(s) ne sont pas encore comptés : la validation sera bloquée tant qu’ils ne le sont pas.`
            : 'Tous les articles sont comptés. Le valideur pourra contrôler puis valider.',
        },
        loading: 'Soumission…',
        busy: this.enCours,
        errorTitle: 'Soumission refusée',
        success: this.succes('Inventaire soumis au contrôle'),
      })
      .subscribe((inv) => this.apresTransition(inv));
  }

  reprendre(): void {
    this.feedback
      .runWithReason((motif) => this.post('reprendre', { motif }), {
        reason: {
          title: 'Renvoyer en comptage',
          message: 'L’inventaire repassera « En cours » pour correction des comptages.',
          reasonLabel: 'Motif',
          required: true,
          confirmLabel: 'Renvoyer',
          tone: 'warn',
          icon: 'undo',
        },
        loading: 'Renvoi…',
        busy: this.enCours,
        errorTitle: 'Action refusée',
        success: this.succes('Inventaire renvoyé en comptage'),
      })
      .subscribe((inv) => this.apresTransition(inv));
  }

  ouvrirValidation(): void {
    this.forcer.set(false);
    this.motifForcage.set('');
    this.feedback
      .run(() => this.api.get<ValidationPreview>(`/mg/stock/inventaires/${this.id()}/validation`), {
        busy: this.enCours,
        errorTitle: 'Aperçu de validation indisponible',
        success: () => null,
      })
      .subscribe((v) => this.validation.set(v));
  }

  valider(): void {
    const v = this.validation();
    if (!v) return;
    const forcer = !v.peut_valider && this.forcer();
    this.feedback
      .run(() => this.post('valider', forcer ? { forcer: true, motif: this.motifForcage().trim() } : {}), {
        loading: 'Validation…',
        busy: this.enCours,
        errorTitle: 'Validation refusée',
        success: this.succes(forcer ? 'Inventaire validé (forcé)' : 'Inventaire validé'),
      })
      .subscribe((inv) => {
        this.validation.set(null);
        this.apresTransition(inv);
      });
  }

  genererAjustements(): void {
    const d = this.inv();
    if (!d) return;
    const s = d.stats;
    this.feedback
      .run(() => this.post('generer_ajustements'), {
        confirm: {
          title: 'Générer les ajustements de stock',
          message: `Créer ${s.ajustements_prevus} mouvement(s) d’ajustement pour ${d.reference} (variation ${signe(s.ajustement_net)}) ?`,
          hint: s.rapprochement
            ? `Le stock BEA DIGITAL passera de ${this.nombre(s.total_systeme)} au stock retenu par la banque (${this.nombre(s.total_retenu)}). ` +
              (s.ecart_a_regulariser ? `L’écart physique ${signe(s.ecart_a_regulariser)} reste à régulariser, sans mouvement. ` : '') +
              'Les articles d’ancienne agence sont archivés sans mouvement. Opération unique et irréversible.'
            : 'Chaque article en écart reçoit un mouvement AJUSTEMENT égal à l’écart constaté (physique − théorique). Opération unique et irréversible.',
          confirmLabel: 'Générer',
          tone: 'warn',
          icon: 'published_with_changes',
        },
        loading: 'Génération des ajustements…',
        busy: this.enCours,
        idempotent: true,
        errorTitle: 'Génération refusée',
        success: this.succes('Ajustements générés'),
      })
      .subscribe((inv) => this.apresTransition(inv));
  }

  archiver(): void {
    const d = this.inv();
    if (!d) return;
    this.feedback
      .run(() => this.post('archiver'), {
        confirm: { action: 'archivage', message: `Archiver ${d.reference} ?`, hint: 'L’inventaire restera consultable et exportable.' },
        loading: 'Archivage…',
        busy: this.enCours,
        errorTitle: 'Archivage refusé',
        success: this.succes('Inventaire archivé'),
      })
      .subscribe((inv) => this.apresTransition(inv));
  }

  annuler(): void {
    const d = this.inv();
    if (!d) return;
    this.feedback
      .runWithReason((motif) => this.post('annuler', { motif }), {
        reason: {
          title: `Annuler ${d.reference}`,
          message: 'L’inventaire restera consultable au statut « Annulé ». Aucun ajustement ne sera généré.',
          reasonLabel: 'Motif d’annulation',
          required: true,
          confirmLabel: 'Annuler l’inventaire',
          tone: 'danger',
          icon: 'block',
        },
        loading: 'Annulation…',
        busy: this.enCours,
        errorTitle: 'Annulation refusée',
        success: this.succes('Inventaire annulé'),
      })
      .subscribe((inv) => this.apresTransition(inv));
  }

  supprimer(): void {
    const d = this.inv();
    if (!d) return;
    this.feedback
      .run(() => this.api.delete<void>(`/mg/stock/inventaires/${d.id}`), {
        confirm: { action: 'suppression', message: `Supprimer définitivement ${d.reference} de la liste ?`, hint: 'Les comptages saisis seront perdus.' },
        loading: 'Suppression…',
        busy: this.enCours,
        errorTitle: 'Suppression refusée',
        success: { title: 'Inventaire supprimé', details: [{ label: 'Référence', value: d.reference }] },
      })
      .subscribe(() => this.router.navigate(['/stock-fournitures/inventaires']));
  }

  ouvrirEdition(): void {
    const d = this.inv();
    if (!d) return;
    this.edition.reset({
      libelle: d.libelle,
      date_debut: d.date_debut,
      agence_id: d.agence_id ?? '',
      famille_id: d.famille_id ?? '',
      responsable_nom: d.responsable_nom ?? '',
      observation: d.observation ?? '',
    });
    this.editionOuverte.set(true);
  }

  enregistrerEdition(): void {
    const d = this.inv();
    if (!d || this.edition.invalid) return;
    const v = this.edition.getRawValue();
    const body: Record<string, unknown> = {
      libelle: v.libelle.trim(),
      responsable_nom: v.responsable_nom.trim() || null,
      observation: v.observation.trim() || null,
    };
    if (d.statut === 'BROUILLON') {
      body['date_debut'] = v.date_debut;
      body['agence_id'] = v.agence_id || null;
      body['famille_id'] = v.famille_id || null;
    }
    this.feedback
      .run(() => this.api.patch<Inventaire>(`/mg/stock/inventaires/${d.id}`, body), {
        loading: 'Enregistrement…',
        busy: this.enCours,
        errorTitle: 'Modification refusée',
        errorHint: 'Vos saisies ont été conservées.',
        success: { title: 'Inventaire modifié', details: [{ label: 'Référence', value: d.reference }] },
      })
      .subscribe((inv) => {
        this.edition.markAsPristine();
        this.editionOuverte.set(false);
        this.apresTransition(inv);
      });
  }

  exporter(format: 'xlsx' | 'pdf'): void {
    const d = this.inv();
    if (!d) return;
    this.feedback
      .run(() => this.api.download(`/mg/stock/inventaires/${d.id}/export`, { format }), {
        loading: `Export ${format.toUpperCase()}…`,
        errorTitle: 'Export impossible',
        success: () => null,
      })
      .subscribe((blob) => downloadBlob(blob, `inventaire-${d.reference}.${format}`));
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.validation()) this.validation.set(null);
    else if (this.ajoutOuvert()) this.ajoutOuvert.set(false);
    else if (this.editionOuverte()) this.editionOuverte.set(false);
    else if (this.selection()) this.fermerLigne();
  }
}
