import { ChangeDetectionStrategy, Component, DestroyRef, HostListener, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { Subject, debounceTime } from 'rxjs';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { FactureDrawerComponent } from './facture-drawer.component';
import { FactureFormComponent } from './facture-form.component';
import { FxSparkComponent } from './facturation-charts';
import {
  FX_BASE,
  FactureDetail,
  MOIS_COURTS,
  PointRow,
  PointSynthese,
  TYPE_POINT_ICONS,
  TYPE_POINT_LABELS,
  annees,
  dateFr,
  fxStatut,
  fxTone,
  nettoyer,
  pct,
} from './facturation.models';
import { FacturationStore } from './facturation.store';
import { RowMenu, RowMenuComponent, RowMenuItem } from '../contrats-echeances/shared/row-menu';
import { PagerComponent, TableState } from '../contrats-echeances/shared/table-state';

interface LigneImport {
  reference: string;
  normalisee: string;
  compteur: string | null;
  nom_source: string;
  nom: string;
  type_point: string;
  feuille: string;
  cellule: string;
  statut: string;
  agence_id: string | null;
  agence_libelle: string | null;
  score: number | null;
  point_existant: { code: string | null; nom: string; id?: string; cellule?: string } | null;
  inclure: boolean;
}

interface ApercuImport {
  fichier: string;
  fournisseur: string;
  feuilles: string[];
  lignes: LigneImport[];
  resume: Record<string, number>;
  avertissements: string[];
}

interface ResultatImport {
  nb_crees: number;
  ignores: number;
  existants: number;
  doublons_fichier: number;
  suivi_depuis: string;
  crees: { id: string; code: string; nom: string; reference: string }[];
}

@Component({
  selector: 'bea-fx-points',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, MontantPipe, FxSparkComponent, FactureDrawerComponent, FactureFormComponent, RowMenuComponent, PagerComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances · Factures</p>
          <h1>Points de facturation</h1>
          <p class="bea-ct-head__sub">Chaque site facturé (agence, siège, PDV Amanty…) identifié par sa référence fournisseur. Un point déjà facturé n'est jamais supprimé : il est désactivé.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap().manage) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirImport()"><mat-icon>upload_file</mat-icon> Importer (Excel SOMELEC)</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="editer(null)"><mat-icon>add_location_alt</mat-icon> Nouveau point</button>
          }
        </div>
      </header>

      <div class="bea-fx-chips">
        @for (t of typesResume(); track t.code) {
          <button type="button" class="bea-fx-chip" [class.is-active]="filtres.controls.type.value === t.code" (click)="filtrerType(t.code)">
            <mat-icon>{{ t.icon }}</mat-icon> {{ t.label }} <strong>{{ t.nb }}</strong>
          </button>
        }
      </div>

      <form class="bea-mg__search bea-ct-filters bea-fx-filters" [formGroup]="filtres">
        <label class="bea-mg__field bea-fx-q">Recherche
          <span class="bea-fx-q__box"><mat-icon>search</mat-icon>
            <input formControlName="q" type="search" placeholder="Nom, code PF-, référence SOMELEC, compteur…" (input)="saisie$.next()" />
          </span>
        </label>
        <label class="bea-mg__field">Fournisseur
          <select formControlName="supplier_id" (change)="charger()">
            <option value="">Tous</option>
            @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
          </select>
        </label>
        @if (!store.config()?.agence_scope) {
          <label class="bea-mg__field">Agence
            <select formControlName="agency_id" (change)="charger()">
              <option value="">Toutes</option>
              @for (a of store.ref()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
            </select>
          </label>
        }
        <label class="bea-mg__field">Statut
          <select formControlName="statut" (change)="charger()">
            <option value="">Tous</option>
            <option value="ACTIF">Actifs</option>
            <option value="INACTIF">Inactifs</option>
          </select>
        </label>
        <label class="bea-mg__field">Année
          <select formControlName="year" (change)="charger()">
            @for (a of annees; track a) { <option [ngValue]="a">{{ a }}</option> }
          </select>
        </label>
      </form>

      <div class="bea-mg__panel bea-ct-panel">
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-fx-table">
            <thead>
              <tr>
                <th>Code</th><th>Point</th><th>Référence</th><th>Fournisseur</th><th>Agence</th>
                <th>Périodicité</th><th>Dernière facture</th><th class="is-num">Total {{ filtres.controls.year.value }}</th><th>Statut</th><th class="is-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @if (points() === null) {
                @for (i of [1, 2, 3, 4, 5]; track i) { <tr><td colspan="10"><span class="bea-fx-skel bea-fx-skel--line"></span></td></tr> }
              } @else {
                @for (p of tPoints.lignes(); track p.id; let i = $index) {
                  <tr class="bea-fx-row" [class.is-active]="pointId() === p.id" [class.is-muted]="p.statut !== 'ACTIF'" [style.animation-delay.ms]="i < 20 ? i * 15 : 0" (click)="ouvrir(p.id)">
                    <td><strong class="bea-fx-ref">{{ p.code }}</strong></td>
                    <td><span class="bea-fx-site"><mat-icon>{{ icone(p.type_point) }}</mat-icon> {{ p.nom }}</span><small class="bea-fx-sub">{{ p.type_point_label }}</small></td>
                    <td><code class="bea-fx-code">{{ p.reference_fournisseur }}</code>@if (p.compteur) { <small class="bea-fx-sub">Compteur {{ p.compteur }}</small> }</td>
                    <td>{{ p.fournisseur || '—' }}</td>
                    <td>{{ p.agence || '—' }}</td>
                    <td>{{ periodicite(p.periodicite) }}</td>
                    <td>{{ p.derniere_periode_label || 'Aucune' }}</td>
                    <td class="is-num">{{ p.total_annee | montant }} <small class="bea-fx-sub">{{ p.nb_factures }} fact.</small></td>
                    <td><span class="bea-ct-badge" [attr.data-tone]="tone(p.statut)">{{ statut(p.statut) }}</span></td>
                    <td class="is-nowrap" (click)="$event.stopPropagation()">
                      <span class="bea-row-actions">
                        <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="ouvrir(p.id)"><mat-icon>visibility</mat-icon></button>
                        @if (store.cap().manage) {
                          <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editer(p)"><mat-icon>edit</mat-icon></button>
                        }
                        @if (store.cap().create && p.statut === 'ACTIF') {
                          <button type="button" class="bea-mg__icon-btn" title="Saisir une facture" (click)="saisirPour(p)"><mat-icon>post_add</mat-icon></button>
                        }
                        <button type="button" class="bea-mg__icon-btn" title="Plus d'actions" aria-haspopup="menu" (click)="menuPoint($event, p)"><mat-icon>more_vert</mat-icon></button>
                      </span>
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="10">
                    <div class="bea-ct-empty">
                      <mat-icon>location_off</mat-icon>
                      <p>Aucun point de facturation.</p>
                      @if (store.cap().manage) { <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirImport()"><mat-icon>upload_file</mat-icon> Importer le fichier SOMELEC</button> }
                    </div>
                  </td></tr>
                }
              }
            </tbody>
          </table>
        </div>
        <bea-pager [etat]="tPoints" />
      </div>
    </section>
    <bea-row-menu [menu]="rowMenu" />

    @if (pointId()) {
      <div class="bea-fx-drawer__backdrop" (click)="fermer()"></div>
      <aside class="bea-fx-drawer" role="dialog" aria-label="Fiche point de facturation">
        @if (synthese(); as s) {
          <header class="bea-fx-drawer__head">
            <div>
              <p class="bea-ct-view__kicker">{{ s.code }} · {{ s.type_point_label }}</p>
              <h2>{{ s.nom }}</h2>
              <p class="bea-fx-drawer__meta">
                <span class="bea-ct-badge" [attr.data-tone]="tone(s.statut)">{{ statut(s.statut) }}</span>
                <code class="bea-fx-code">{{ s.reference_fournisseur }}</code> {{ s.fournisseur }}{{ s.agence ? ' · ' + s.agence : '' }}
              </p>
            </div>
            <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
          </header>

          <div class="bea-fx-drawer__actions">
            @if (store.cap().create && s.statut === 'ACTIF') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="saisir(s, null)"><mat-icon>post_add</mat-icon> Saisir une facture</button>
            }
            <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="base + '/factures'" [queryParams]="{ pdv_id: s.id, inclure_historique: true }"><mat-icon>receipt_long</mat-icon> Factures</a>
            @if (store.cap().manage) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="editer(s)"><mat-icon>edit</mat-icon> Modifier</button>
              @if (s.statut === 'ACTIF') {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="desactiver(s)"><mat-icon>pause_circle</mat-icon> Désactiver</button>
              } @else {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="activer(s)"><mat-icon>play_circle</mat-icon> Réactiver</button>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--danger" (click)="supprimer(s)"><mat-icon>delete</mat-icon></button>
            }
          </div>

          <div class="bea-fx-drawer__body">
            <div class="bea-fx-mini">
              <div><span>Total {{ s.annee }}</span><strong>{{ s.total_annee | montant }}</strong></div>
              <div><span>N-1</span><strong>{{ s.total_n1 | montant }}</strong><small [class.bea-ct-neg]="(s.variation_n1_pct ?? 0) > 0">{{ pct(s.variation_n1_pct) }}</small></div>
              <div><span>Moyenne 6 dernières</span><strong>{{ s.moyenne_6 === null ? '—' : (s.moyenne_6 | montant) }}</strong></div>
              <div><span>Reste à payer</span><strong class="bea-ct-neg">{{ s.reste_a_payer | montant }}</strong></div>
            </div>

            <h3 class="bea-fx-h3"><mat-icon>show_chart</mat-icon> Tendance {{ s.annee }} <small>(pointillé : {{ s.annee - 1 }})</small></h3>
            <bea-fx-spark [values]="s.mensuel" [n1]="s.mensuel_n1" />

            <div class="bea-fx-months">
              @for (m of mois(s); track m.mois) {
                <button type="button" class="bea-fx-month" [attr.data-etat]="m.etat" [disabled]="m.etat === 'futur' || (m.etat !== 'ok' && !store.cap().create)"
                  (click)="m.facture ? ouvrirFacture(m.facture) : saisir(s, m.mois)" [title]="m.titre">
                  <span>{{ m.label }}</span>
                  <strong>{{ m.texte }}</strong>
                </button>
              }
            </div>

            <dl class="bea-fx-dl">
              <dt>Périodicité</dt><dd>{{ periodicite(s.periodicite) }}</dd>
              <dt>Type de facture</dt><dd>{{ store.typeFacture(s.type_facture) || '—' }}</dd>
              <dt>Suivi depuis</dt><dd>{{ date(s.date_debut) }}</dd>
              @if (s.date_fin) { <dt>Fin</dt><dd>{{ date(s.date_fin) }}</dd> }
              <dt>Contrat</dt><dd>@if (s.contrat; as c) { <a class="bea-ct-link" [routerLink]="'/contrats-echeances/' + c.id">{{ c.reference }} — {{ c.titre }}</a> } @else { — }</dd>
              @if (s.adresse) { <dt>Adresse</dt><dd>{{ s.adresse }}</dd> }
              @if (s.telephone) { <dt>Téléphone</dt><dd>{{ s.telephone }}</dd> }
              @if (s.description) { <dt>Notes</dt><dd>{{ s.description }}</dd> }
            </dl>

            <h3 class="bea-fx-h3"><mat-icon>receipt_long</mat-icon> Factures</h3>
            <ul class="bea-ct-dash__list">
              @for (r of s.factures; track r.id) {
                <li><a (click)="ouvrirFacture(r.id)">
                  <span class="bea-ct-dash__date"><strong>{{ r.periode_label || date(r.date_facture) }}</strong><small>{{ r.reference }}</small></span>
                  <span class="bea-ct-dash__amount">{{ r.montant_a_payer === null ? 'Non saisi' : (r.montant_a_payer | montant) }}</span>
                  <span class="bea-ct-badge" [attr.data-tone]="tone(r.statut_affiche)">{{ statut(r.statut_affiche) }}</span>
                </a></li>
              } @empty { <li class="bea-ct-dash__none">Aucune facture pour ce point.</li> }
            </ul>

            <h3 class="bea-fx-h3"><mat-icon>history</mat-icon> Historique</h3>
            <ol class="bea-fx-timeline">
              @for (e of s.historique; track e.id) {
                <li><span class="bea-fx-timeline__dot"></span><div><strong>{{ e.message || e.action }}</strong><small>{{ e.user_nom || 'Système' }} · {{ date(e.created_at) }}</small></div></li>
              } @empty { <li class="bea-ct-dash__none">Aucun événement.</li> }
            </ol>
          </div>
        } @else {
          <div class="bea-fx-drawer__body">
            <span class="bea-fx-skel bea-fx-skel--title"></span>
            <span class="bea-fx-skel bea-fx-skel--kpi"></span>
            <span class="bea-fx-skel bea-fx-skel--chart"></span>
          </div>
        }
      </aside>
    }

    @if (formPoint()) {
      <div class="bea-mg__backdrop bea-fx-over" (click)="fermerForm()"></div>
        <form class="bea-mg__modal bea-mg__modal--lg bea-ct-modal bea-fx-over" role="dialog" aria-modal="true" [formGroup]="pointForm" (ngSubmit)="enregistrerPoint()">
          <div class="bea-ct-modal__head">
            <h2><mat-icon>add_location_alt</mat-icon> {{ edition() ? 'Modifier ' + edition()!.code : 'Nouveau point de facturation' }}</h2>
            <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerForm()"><mat-icon>close</mat-icon></button>
          </div>
          <div class="bea-ct-modal__body bea-ct-grid">
            <label class="bea-mg__field">Type de site *
              <select formControlName="type_point">
                @for (t of store.config()?.types_point ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Nom *<input formControlName="nom" maxlength="255" placeholder="Ex. Agence Route NDB" /></label>
            <label class="bea-mg__field">Fournisseur *
              <select formControlName="fournisseur_id">
                <option value="">— Choisir —</option>
                @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Profil de facturation
              <select formControlName="profil_id">
                <option value="">— Aucun —</option>
                @for (pr of profilsFournisseur(); track pr.id) { <option [value]="pr.id">{{ pr.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Référence fournisseur *<input formControlName="reference_fournisseur" maxlength="80" placeholder="Ex. 363215238221" /></label>
            <label class="bea-mg__field">Compteur<input formControlName="compteur" maxlength="40" /></label>
            <label class="bea-mg__field">Agence de rattachement
              <select formControlName="agence_id">
                <option value="">— Aucune —</option>
                @for (a of store.ref()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Contrat
              <select formControlName="contrat_id">
                <option value="">— Aucun —</option>
                @for (c of contratsFournisseur(); track c.id) { <option [value]="c.id">{{ c.reference }} — {{ c.titre }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Type de facture
              <select formControlName="type_facture">
                <option value="">— Non précisé —</option>
                @for (t of store.config()?.types_facture ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Périodicité
              <select formControlName="periodicite">
                @for (p of store.config()?.periodicites ?? []; track p) { <option [value]="p">{{ periodicite(p) }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Suivi depuis<input type="date" formControlName="date_debut" /></label>
            <label class="bea-mg__field">Date de fin<input type="date" formControlName="date_fin" /></label>
            <label class="bea-mg__field bea-ct-span2">Adresse<textarea formControlName="adresse" rows="2"></textarea></label>
            <label class="bea-mg__field">Téléphone<input formControlName="telephone" maxlength="40" inputmode="tel" placeholder="+222 …" /></label>
            <label class="bea-mg__field bea-ct-span2">Notes<textarea formControlName="description" rows="2"></textarea></label>
            <p class="bea-ct-help bea-ct-span2"><mat-icon>info</mat-icon> La référence fournisseur est unique par fournisseur (contrôle anti-doublon côté serveur).</p>
          </div>
          <div class="bea-ct-modal__foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerForm()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="pointForm.invalid || busy()"><mat-icon>save</mat-icon> Enregistrer</button>
          </div>
        </form>
    }

    @if (importOuvert()) {
      <div class="bea-mg__backdrop bea-fx-over" (click)="fermerImport()"></div>
        <div class="bea-mg__modal bea-ct-modal bea-fx-over bea-fx-modal--wide" role="dialog" aria-modal="true" aria-label="Import des points de facturation">
          <div class="bea-ct-modal__head">
            <h2><mat-icon>upload_file</mat-icon> Import des points de facturation</h2>
            <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerImport()"><mat-icon>close</mat-icon></button>
          </div>
          <ol class="bea-fx-steps">
            <li [class.is-active]="etape() === 1" [class.is-done]="etape() > 1">Fichier</li>
            <li [class.is-active]="etape() === 2" [class.is-done]="etape() > 2">Contrôle</li>
            <li [class.is-active]="etape() === 3">Résultat</li>
          </ol>
          <div class="bea-ct-modal__body">
            @switch (etape()) {
              @case (1) {
                <div class="bea-ct-grid">
                  <label class="bea-mg__field">Fournisseur *
                    <select [value]="importFournisseur()" (change)="importFournisseur.set($any($event.target).value)">
                      <option value="">— Choisir —</option>
                      @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
                    </select>
                  </label>
                  <div class="bea-mg__field">Fichier Excel (.xlsx) *
                    <label class="bea-fx-dropzone" [class.is-over]="survol()" (dragover)="$event.preventDefault(); survol.set(true)" (dragleave)="survol.set(false)" (drop)="deposer($event)">
                      <input type="file" hidden accept=".xlsx,.xlsm" (change)="choisirFichier($event)" />
                      <mat-icon>cloud_upload</mat-icon>
                      <span>{{ fichier()?.name || 'Glissez le fichier ici ou cliquez pour parcourir' }}</span>
                    </label>
                  </div>
                </div>
                <p class="bea-ct-help"><mat-icon>verified_user</mat-icon> Seuls les points (sites + références) sont créés. Aucun montant n'est importé : les montants viendront des factures réelles. Les références déjà connues et les doublons du fichier sont ignorés.</p>
              }
              @case (2) {
                @if (apercu(); as a) {
                  <div class="bea-fx-mini">
                    <div><span>Références uniques</span><strong>{{ a.resume['references_uniques'] }}</strong></div>
                    <div><span>Nouvelles</span><strong>{{ a.resume['nouveaux'] }}</strong></div>
                    <div><span>Déjà existantes</span><strong>{{ a.resume['existants'] }}</strong></div>
                    <div><span>Doublons fichier</span><strong>{{ a.resume['doublons_fichier'] }}</strong></div>
                    <div><span>Agences / sièges / PDV</span><strong>{{ a.resume['agences'] }} / {{ a.resume['sieges'] }} / {{ a.resume['pdv'] }}</strong></div>
                  </div>
                  @for (w of a.avertissements; track $index) { <p class="bea-ct-help"><mat-icon>info</mat-icon> {{ w }}</p> }
                  <div class="bea-fx-import-opts">
                    <label class="bea-mg__field">Suivi depuis<input type="date" [value]="suiviDepuis()" (change)="suiviDepuis.set($any($event.target).value)" /></label>
                    <label class="bea-mg__field">Périodicité
                      <select [value]="importPeriodicite()" (change)="importPeriodicite.set($any($event.target).value)">
                        @for (p of store.config()?.periodicites ?? []; track p) { <option [value]="p">{{ periodicite(p) }}</option> }
                      </select>
                    </label>
                    <label class="bea-mg__field">Type de facture
                      <select [value]="importType()" (change)="importType.set($any($event.target).value)">
                        <option value="">— Non précisé —</option>
                        @for (t of store.config()?.types_facture ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
                      </select>
                    </label>
                  </div>
                  <div class="bea-mg__table-wrap bea-fx-import-table">
                    <table class="bea-mg__table">
                      <thead><tr><th><input type="checkbox" [checked]="toutInclus()" (change)="toutInclure($any($event.target).checked)" aria-label="Tout inclure" /></th><th>Référence</th><th>Nom du point</th><th>Type</th><th>Agence</th><th>Source</th><th>État</th></tr></thead>
                      <tbody>
                        @for (l of a.lignes; track l.normalisee + l.cellule) {
                          <tr [class.is-muted]="l.statut !== 'NOUVEAU' || !l.inclure">
                            <td>@if (l.statut === 'NOUVEAU') { <input type="checkbox" [checked]="l.inclure" (change)="modifierLigne(l, 'inclure', $any($event.target).checked)" /> }</td>
                            <td><code class="bea-fx-code">{{ l.reference }}</code></td>
                            <td>
                              @if (l.statut === 'NOUVEAU') { <input class="bea-fx-cell" [value]="l.nom" maxlength="255" (change)="modifierLigne(l, 'nom', $any($event.target).value)" /> }
                              @else { {{ l.point_existant?.nom || l.nom }} }
                            </td>
                            <td>
                              @if (l.statut === 'NOUVEAU') {
                                <select class="bea-fx-cell" [value]="l.type_point" (change)="modifierLigne(l, 'type_point', $any($event.target).value)">
                                  @for (t of store.config()?.types_point ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
                                </select>
                              } @else { {{ typeLabel(l.type_point) }} }
                            </td>
                            <td>
                              @if (l.statut === 'NOUVEAU') {
                                <select class="bea-fx-cell" [value]="l.agence_id ?? ''" (change)="modifierLigne(l, 'agence_id', $any($event.target).value || null)">
                                  <option value="">— Aucune —</option>
                                  @for (ag of store.ref()?.agences ?? []; track ag.id) { <option [value]="ag.id">{{ ag.libelle }}</option> }
                                </select>
                              } @else { {{ l.agence_libelle || '—' }} }
                            </td>
                            <td><small class="bea-fx-sub">{{ l.feuille }}!{{ l.cellule }} · {{ l.nom_source }}</small></td>
                            <td>
                              <span class="bea-ct-badge" [attr.data-tone]="tone(l.statut)">{{ statut(l.statut) }}</span>
                              @if (l.point_existant?.code) { <small class="bea-fx-sub">{{ l.point_existant!.code }}</small> }
                            </td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              }
              @case (3) {
                @if (resultat(); as r) {
                  <div class="bea-ct-empty bea-fx-success">
                    <mat-icon>task_alt</mat-icon>
                    <p><strong>{{ r.nb_crees }}</strong> point(s) créé(s) · {{ r.existants }} déjà existant(s) · {{ r.doublons_fichier }} doublon(s) ignoré(s) · {{ r.ignores }} exclu(s).</p>
                    <p class="bea-fx-sub">Suivi des factures manquantes à partir du {{ date(r.suivi_depuis) }}.</p>
                  </div>
                  <ul class="bea-fx-import-done">
                    @for (c of r.crees; track c.id) { <li><strong>{{ c.code }}</strong> {{ c.nom }} <code class="bea-fx-code">{{ c.reference }}</code></li> }
                  </ul>
                }
              }
            }
          </div>
          <div class="bea-ct-modal__foot">
            @switch (etape()) {
              @case (1) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerImport()">Annuler</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!fichier() || !importFournisseur() || busy()" (click)="previsualiser()"><mat-icon>preview</mat-icon> Analyser le fichier</button>
              }
              @case (2) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="etape.set(1)"><mat-icon>arrow_back</mat-icon> Retour</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!nbACreer() || busy()" (click)="confirmerImport()"><mat-icon>add_location_alt</mat-icon> Créer {{ nbACreer() }} point(s)</button>
              }
              @case (3) {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="fermerImport()">Terminer</button>
              }
            }
          </div>
        </div>
    }

    @if (factureId(); as id) {
      <bea-fx-facture-drawer [factureId]="id" (closed)="factureId.set(null)" (changed)="rafraichir()" />
    }
    @if (saisie(); as p) {
      <bea-fx-facture-form [preset]="p" (saved)="apresSaisie($event)" (closed)="saisie.set(null)" />
    }
  `,
})
export class FacturationPointsComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly base = FX_BASE;
  readonly annees = annees();
  readonly points = signal<PointRow[] | null>(null);
  readonly pointId = signal<string | null>(null);
  readonly synthese = signal<PointSynthese | null>(null);
  readonly factureId = signal<string | null>(null);
  readonly saisie = signal<{ point_facturation_id: string; annee?: number; mois?: number } | null>(null);
  readonly formPoint = signal(false);
  readonly edition = signal<PointRow | null>(null);
  readonly busy = signal(false);
  readonly saisie$ = new Subject<void>();
  readonly rowMenu = new RowMenu();
  readonly tPoints = new TableState<PointRow>(() => this.points() ?? [], {});

  readonly importOuvert = signal(false);
  readonly etape = signal(1);
  readonly fichier = signal<File | null>(null);
  readonly importFournisseur = signal('');
  readonly apercu = signal<ApercuImport | null>(null);
  readonly resultat = signal<ResultatImport | null>(null);
  readonly suiviDepuis = signal('');
  readonly importPeriodicite = signal('MENSUEL');
  readonly importType = signal('');
  readonly survol = signal(false);

  private readonly drawer = viewChild(FactureDrawerComponent);
  private readonly factureForm = viewChild(FactureFormComponent);

  readonly filtres = this.fb.nonNullable.group({
    q: [''],
    supplier_id: [''],
    agency_id: [''],
    statut: [''],
    type: [''],
    year: [new Date().getFullYear()],
  });

  readonly pointForm = this.fb.nonNullable.group({
    type_point: ['AGENCE', Validators.required],
    nom: ['', [Validators.required, Validators.maxLength(255)]],
    fournisseur_id: ['', Validators.required],
    profil_id: [''],
    reference_fournisseur: ['', [Validators.required, Validators.maxLength(80)]],
    compteur: [''],
    agence_id: [''],
    contrat_id: [''],
    type_facture: [''],
    periodicite: ['MENSUEL'],
    date_debut: [''],
    date_fin: [''],
    adresse: [''],
    telephone: [''],
    description: [''],
  });

  private readonly pointDirty = unsavedChanges(() => this.formPoint() && this.pointForm.dirty, () => this.pointForm);
  readonly hasUnsavedChanges = () =>
    this.pointDirty() || (this.importOuvert() && this.etape() === 2) || !!this.factureForm()?.isDirty() || !!this.drawer()?.dirty();

  private readonly fournisseurForm = signal('');
  readonly profilsFournisseur = computed(() => {
    const f = this.fournisseurForm();
    return (this.store.ref()?.profils ?? []).filter((p) => p.actif && (!f || p.fournisseur_id === f));
  });

  readonly contratsFournisseur = computed(() => {
    const f = this.fournisseurForm();
    return (this.store.ref()?.contrats ?? []).filter((c) => !f || !c.fournisseur_id || c.fournisseur_id === f);
  });

  readonly typesResume = computed(() => {
    const rows = this.points() ?? [];
    const out = [{ code: '', label: 'Tous', icon: 'apps', nb: rows.length }];
    for (const t of this.store.config()?.types_point ?? []) {
      out.push({ code: t.code, label: t.libelle, icon: TYPE_POINT_ICONS[t.code] ?? 'place', nb: rows.filter((r) => r.type_point === t.code).length });
    }
    return out;
  });

  readonly nbACreer = computed(() => (this.apercu()?.lignes ?? []).filter((l) => l.statut === 'NOUVEAU' && l.inclure).length);
  readonly toutInclus = computed(() => (this.apercu()?.lignes ?? []).filter((l) => l.statut === 'NOUVEAU').every((l) => l.inclure));

  ngOnInit(): void {
    this.store.charger();
    this.saisie$.pipe(debounceTime(300), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.charger());
    this.pointForm.controls.fournisseur_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => {
      this.fournisseurForm.set(v);
      const pr = (this.store.ref()?.profils ?? []).find((p) => p.id === this.pointForm.controls.profil_id.value);
      if (pr && pr.fournisseur_id !== v) this.pointForm.controls.profil_id.setValue('');
    });
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((m) => {
      const id = m.get('point');
      if (id !== this.pointId()) {
        this.pointId.set(id);
        if (id) this.chargerSynthese(id);
      }
    });
    this.charger();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.factureId() || this.saisie() || this.formPoint() || this.importOuvert()) return;
    if (this.pointId()) this.fermer();
  }

  charger(): void {
    const v = this.filtres.getRawValue();
    this.api.get<PointRow[]>('/mg/points-facturation', nettoyer({ ...v, type: '' })).subscribe({
      next: (rows) => this.points.set(v.type ? rows.filter((r) => r.type_point === v.type) : rows),
      error: (e) => {
        this.points.set([]);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Points de facturation indisponibles'));
      },
    });
  }

  filtrerType(code: string): void {
    this.filtres.controls.type.setValue(code);
    this.charger();
  }

  ouvrir(id: string): void {
    this.router.navigate([], { queryParams: { point: id }, queryParamsHandling: 'merge', replaceUrl: true });
  }

  fermer(): void {
    this.router.navigate([], { queryParams: { point: null }, queryParamsHandling: 'merge', replaceUrl: true });
    this.synthese.set(null);
  }

  private chargerSynthese(id: string): void {
    this.synthese.set(null);
    this.api.get<PointSynthese>(`/mg/points-facturation/${id}`, { year: this.filtres.controls.year.value }).subscribe({
      next: (s) => this.synthese.set(s),
      error: (e) => {
        this.fermer();
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Point introuvable'));
      },
    });
  }

  rafraichir(): void {
    this.charger();
    const id = this.pointId();
    if (id) this.chargerSynthese(id);
  }

  mois(s: PointSynthese): { mois: number; label: string; etat: string; texte: string; titre: string; facture: string | null }[] {
    const today = new Date();
    const debut = s.date_debut ? new Date(s.date_debut) : null;
    return MOIS_COURTS.map((label, i) => {
      const mois = i + 1;
      const f = s.factures.find((r) => r.annee === s.annee && r.mois === mois && r.statut !== 'ANNULEE');
      const fin = new Date(s.annee, mois, 0);
      const futur = new Date(s.annee, i, 1) > today;
      const suivi = s.statut === 'ACTIF' && s.periodicite === 'MENSUEL' && (!debut || fin >= debut);
      if (f) {
        return { mois, label, etat: 'ok', texte: f.montant_a_payer === null ? 'Saisie' : this.court(f.montant_a_payer), titre: `${f.reference} — ${fxStatut(f.statut_affiche)}`, facture: f.id };
      }
      if (futur) return { mois, label, etat: 'futur', texte: '', titre: 'À venir', facture: null };
      if (suivi && fin < today) return { mois, label, etat: 'manquante', texte: 'Manquante', titre: 'Facture manquante — cliquer pour saisir', facture: null };
      return { mois, label, etat: 'vide', texte: '—', titre: 'Aucune facture — cliquer pour saisir', facture: null };
    });
  }

  private court(v: number): string {
    return v >= 1000 ? `${Math.round(v / 1000).toLocaleString('fr-FR')} k` : v.toLocaleString('fr-FR');
  }

  saisir(s: PointSynthese, mois: number | null): void {
    if (!this.store.cap().create) return;
    this.saisie.set({ point_facturation_id: s.id, annee: s.annee, ...(mois ? { mois } : {}) });
  }

  apresSaisie(f: FactureDetail): void {
    this.saisie.set(null);
    this.rafraichir();
    this.factureId.set(f.id);
  }

  ouvrirFacture(id: string): void {
    this.factureId.set(id);
  }

  editer(p: PointRow | null): void {
    this.edition.set(p);
    this.pointForm.reset({
      type_point: p?.type_point ?? 'AGENCE',
      nom: p?.nom ?? '',
      fournisseur_id: p?.fournisseur_id ?? (this.store.ref()?.fournisseurs.length === 1 ? this.store.ref()!.fournisseurs[0].id : ''),
      profil_id: p?.profil_id ?? '',
      reference_fournisseur: p?.reference_fournisseur ?? '',
      compteur: p?.compteur ?? '',
      agence_id: p?.agence_id ?? '',
      contrat_id: p?.contrat_id ?? '',
      type_facture: p?.type_facture ?? '',
      periodicite: p?.periodicite ?? 'MENSUEL',
      date_debut: p?.date_debut ?? '',
      date_fin: p?.date_fin ?? '',
      adresse: p?.adresse ?? '',
      telephone: p?.telephone ?? '',
      description: p?.description ?? '',
    });
    this.fournisseurForm.set(this.pointForm.controls.fournisseur_id.value);
    this.formPoint.set(true);
  }

  fermerForm(): void {
    this.formPoint.set(false);
    this.pointForm.markAsPristine();
  }

  enregistrerPoint(): void {
    if (this.pointForm.invalid) return;
    const v = this.pointForm.getRawValue();
    const body: Record<string, unknown> = { ...v };
    for (const k of ['profil_id', 'compteur', 'agence_id', 'contrat_id', 'type_facture', 'date_debut', 'date_fin', 'adresse', 'telephone', 'description']) {
      if (body[k] === '') body[k] = null;
    }
    const p = this.edition();
    this.feedback
      .run(() => (p ? this.api.patch<PointRow>(`/mg/points-facturation/${p.id}`, body) : this.api.post<PointRow>('/mg/points-facturation', body)), {
        loading: 'Enregistrement…',
        busy: this.busy,
        idempotent: !p,
        errorTitle: 'Point non enregistré',
        errorHint: 'Vos saisies ont été conservées.',
        success: (r) => ({ title: p ? 'Point modifié' : 'Point créé', message: `${r.code} — ${r.nom}` }),
      })
      .subscribe((r) => {
        this.pointForm.markAsPristine();
        this.formPoint.set(false);
        this.store.rechargerRef();
        this.charger();
        if (p && this.pointId() === p.id) this.chargerSynthese(p.id);
        else this.ouvrir(r.id);
      });
  }

  saisirPour(p: PointRow): void {
    if (!this.store.cap().create) return;
    this.saisie.set({ point_facturation_id: p.id, annee: this.filtres.controls.year.value });
  }

  menuPoint(ev: MouseEvent, p: PointRow): void {
    const items: RowMenuItem[] = [
      { icone: 'receipt_long', label: 'Factures du point', action: () => void this.router.navigate([this.base, 'liste'], { queryParams: { pdv_id: p.id } }) },
      { icone: 'history', label: 'Historique', action: () => this.ouvrir(p.id) },
    ];
    if (this.store.cap().manage) {
      items.push(
        p.statut === 'ACTIF'
          ? { icone: 'pause_circle', label: 'Désactiver', action: () => this.desactiver(p) }
          : { icone: 'play_circle', label: 'Réactiver', action: () => this.activer(p) },
        { icone: 'delete', label: p.nb_factures ? 'Retirer (désactivation)' : 'Supprimer', danger: true, action: () => this.supprimer(p) },
      );
    }
    this.rowMenu.ouvrir(ev, items);
  }

  desactiver(s: PointRow): void {
    this.feedback
      .runWithReason((motif) => this.api.post(`/mg/points-facturation/${s.id}/desactiver`, { motif }), {
        reason: {
          title: `Désactiver ${s.code}`,
          message: 'Le point ne sera plus suivi (factures manquantes). Son historique est conservé.',
          reasonLabel: 'Motif',
          required: false,
          tone: 'warn',
          confirmLabel: 'Désactiver',
        },
        loading: 'Désactivation…',
        errorTitle: 'Désactivation impossible',
        success: { title: 'Point désactivé', message: s.nom },
      })
      .subscribe(() => this.apresStatut());
  }

  activer(s: PointRow): void {
    this.feedback
      .run(() => this.api.post(`/mg/points-facturation/${s.id}/activer`, {}), {
        confirm: { title: `Réactiver ${s.code} ?`, message: 'Le suivi des factures reprendra pour ce point.', confirmLabel: 'Réactiver', tone: 'primary' },
        loading: 'Réactivation…',
        errorTitle: 'Réactivation impossible',
        success: { title: 'Point réactivé', message: s.nom },
      })
      .subscribe(() => this.apresStatut());
  }

  supprimer(s: PointRow): void {
    const facture = s.nb_factures > 0;
    this.feedback
      .run(() => this.api.delete<{ supprime: boolean; desactive: boolean }>(`/mg/points-facturation/${s.id}`), {
        confirm: {
          title: facture ? `Retirer ${s.code} ?` : `Supprimer ${s.code} ?`,
          message: facture
            ? 'Ce point possède des factures : il sera désactivé, pas supprimé, pour préserver l’historique financier.'
            : 'Aucune facture n’est rattachée : le point sera supprimé (suppression logique, tracée).',
          confirmLabel: facture ? 'Désactiver' : 'Supprimer',
          tone: 'danger',
        },
        loading: 'Traitement…',
        errorTitle: 'Opération impossible',
        success: (r) => ({ title: r.supprime ? 'Point supprimé' : 'Point désactivé', message: s.nom }),
      })
      .subscribe((r) => {
        this.store.rechargerRef();
        if (r.supprime) {
          if (this.pointId() === s.id) this.fermer();
          this.charger();
        } else {
          this.apresStatut();
        }
      });
  }

  private apresStatut(): void {
    this.store.rechargerRef();
    this.rafraichir();
  }

  ouvrirImport(): void {
    const fr = this.store.ref()?.fournisseurs ?? [];
    const somelec = fr.find((f) => /somelec/i.test(f.libelle));
    this.importFournisseur.set(somelec?.id ?? (fr.length === 1 ? fr[0].id : ''));
    const d = new Date();
    d.setDate(1);
    d.setMonth(d.getMonth() - 1);
    this.suiviDepuis.set(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`);
    this.fichier.set(null);
    this.apercu.set(null);
    this.resultat.set(null);
    this.etape.set(1);
    this.importOuvert.set(true);
  }

  fermerImport(): void {
    const termine = this.etape() === 3;
    this.importOuvert.set(false);
    if (termine) {
      this.store.rechargerRef();
      this.charger();
    }
  }

  choisirFichier(e: Event): void {
    const input = e.target as HTMLInputElement;
    this.fichier.set(input.files?.[0] ?? null);
    input.value = '';
  }

  deposer(e: DragEvent): void {
    e.preventDefault();
    this.survol.set(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) this.fichier.set(f);
  }

  previsualiser(): void {
    const f = this.fichier();
    if (!f) return;
    this.feedback
      .run(() => this.api.upload<ApercuImport>('/mg/points-facturation/import/preview', f, { fournisseur_id: this.importFournisseur() }), {
        loading: 'Analyse du fichier…',
        busy: this.busy,
        errorTitle: 'Fichier non exploitable',
        success: (a) => ({ title: 'Analyse terminée', message: `${a.resume['nouveaux']} nouvelle(s) référence(s) sur ${a.resume['references_uniques']}.` }),
      })
      .subscribe((a) => {
        this.apercu.set({ ...a, lignes: a.lignes.map((l) => ({ ...l, inclure: l.statut === 'NOUVEAU' })) });
        this.etape.set(2);
      });
  }

  modifierLigne(l: LigneImport, champ: 'inclure' | 'nom' | 'type_point' | 'agence_id', valeur: unknown): void {
    const a = this.apercu();
    if (!a) return;
    this.apercu.set({ ...a, lignes: a.lignes.map((x) => (x === l ? { ...x, [champ]: valeur } : x)) });
  }

  toutInclure(v: boolean): void {
    const a = this.apercu();
    if (!a) return;
    this.apercu.set({ ...a, lignes: a.lignes.map((x) => (x.statut === 'NOUVEAU' ? { ...x, inclure: v } : x)) });
  }

  confirmerImport(): void {
    const f = this.fichier();
    const a = this.apercu();
    if (!f || !a) return;
    const choix = a.lignes
      .filter((l) => l.statut === 'NOUVEAU')
      .map((l) => ({ normalisee: l.normalisee, inclure: l.inclure, nom: l.nom, type_point: l.type_point, agence_id: l.agence_id }));
    this.feedback
      .run(
        () =>
          this.api.upload<ResultatImport>('/mg/points-facturation/import/confirm', f, {
            fournisseur_id: this.importFournisseur(),
            choix: JSON.stringify(choix),
            suivi_depuis: this.suiviDepuis(),
            periodicite: this.importPeriodicite(),
            type_facture: this.importType(),
          }),
        {
          confirm: {
            title: `Créer ${this.nbACreer()} point(s) de facturation ?`,
            message: 'Aucun montant ne sera importé. Les références existantes et les doublons sont ignorés.',
            confirmLabel: 'Créer',
            tone: 'primary',
          },
          loading: 'Création des points…',
          busy: this.busy,
          idempotent: true,
          errorTitle: 'Import refusé',
          success: (r) => ({ title: 'Import terminé', message: `${r.nb_crees} point(s) créé(s).` }),
        },
      )
      .subscribe((r) => {
        this.resultat.set(r);
        this.etape.set(3);
      });
  }

  icone(type: string): string {
    return TYPE_POINT_ICONS[type] ?? 'place';
  }

  typeLabel(type: string): string {
    return TYPE_POINT_LABELS[type] ?? type;
  }

  periodicite(p: string): string {
    return ({ MENSUEL: 'Mensuelle', BIMESTRIEL: 'Bimestrielle', TRIMESTRIEL: 'Trimestrielle', SEMESTRIEL: 'Semestrielle', ANNUEL: 'Annuelle', PONCTUEL: 'Ponctuelle' } as Record<string, string>)[p] ?? p;
  }

  statut(code: string | null | undefined): string {
    return fxStatut(code);
  }

  tone(code: string | null | undefined): string {
    return fxTone(code);
  }

  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }

  pct(v: number | null | undefined): string {
    return pct(v);
  }
}
