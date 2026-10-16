import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { UiDialogService } from '../../shared/ui-dialog/ui-dialog.service';
import { Dossier, ImportAnalyse, ImportLigne, ImportTotaux, dateFr, montantFr, telechargerBlob, totauxParDevise } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { STATUT_ID_LIBELLE, STATUT_ID_TON } from './rc-operations-vue.component';

type Mode = 'AJOUT' | 'REMPLACEMENT';
type Filtre = 'TOUTES' | 'ERREUR' | 'AVERTISSEMENT';

/** Import Excel des opérations : modèle, analyse (aperçu groupé client → compte, erreurs, totaux),
 * confirmation ou abandon. Rien n'est enregistré au dossier avant la confirmation. */
@Component({
  selector: 'bea-rc-import',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (!analyse()) {
      <div class="bea-rc-form">
        <p class="bea-rc-hint">Un fichier Excel (.xlsx, 5 Mo au plus), une ligne par opération. Utilisez le modèle du motif du dossier :
          colonnes obligatoires en rouge (<strong>{{ colonnesRequises() }}</strong>). Les erreurs, doublons et totaux par devise s’affichent
          avant toute confirmation ; rien n’est enregistré tant qu’une ligne est en erreur.</p>
        <div class="bea-rc-row">
          <label>Mode
            <select [value]="mode()" (change)="mode.set($any($event.target).value)">
              <option value="AJOUT">Ajouter aux opérations du dossier</option>
              <option value="REMPLACEMENT">Remplacer toutes les opérations du dossier</option>
            </select>
          </label>
          <label>Fichier
            <input type="file" accept=".xlsx" (change)="choisir($event)" />
          </label>
        </div>
        <span class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-rc-dl-btn" [disabled]="busy()" (click)="modele()"><mat-icon>download</mat-icon> Télécharger le modèle</button>
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !fichier()" (click)="analyser()"><mat-icon>fact_check</mat-icon> Analyser le fichier</button>
        </span>
      </div>
    } @else {
      @let a = analyse()!;
      <div class="bea-rc-form">
        <div class="bea-rc-note" [class.bea-rc-note--warn]="a.nb_erreurs > 0">
          <mat-icon>{{ a.nb_erreurs ? 'error' : 'fact_check' }}</mat-icon>
          <span>
            <strong>{{ a.nom_fichier }}</strong> — {{ a.mode === 'REMPLACEMENT' ? 'remplacement des opérations' : 'ajout aux opérations' }} du dossier.<br />
            {{ a.nb_lignes }} ligne(s) : {{ a.nb_valides }} valide(s), {{ a.nb_erreurs }} en erreur, {{ a.nb_avertissements }} avec avertissement.
            @if (a.nb_erreurs) { Corrigez le fichier puis relancez l’import : aucune ligne n’est enregistrée tant qu’une erreur subsiste. }
          </span>
        </div>
        @if (a.fichier_deja_importe?.force) {
          <div class="bea-rc-note bea-rc-note--warn"><mat-icon>content_copy</mat-icon>
            <span>Ce fichier a déjà été importé sur ce dossier : les lignes identiques sont signalées comme doublons.</span></div>
        }
        @if (a.fichier_deja_importe?.autres_dossiers?.length) {
          <div class="bea-rc-note bea-rc-note--warn"><mat-icon>info</mat-icon>
            <span>Le même fichier a déjà été importé sur : {{ a.fichier_deja_importe!.autres_dossiers.join(', ') }}.</span></div>
        }
        @if (a.recapitulatif?.a_completer_avant_transmission?.length) {
          <div class="bea-rc-note"><mat-icon>rule</mat-icon>
            <span>À compléter avant transmission : {{ a.recapitulatif!.a_completer_avant_transmission.join(' ; ') }}</span></div>
        }

        <div class="bea-rc-kpis">
          <div class="bea-rc-kpi"><p>Clients</p><strong>{{ a.nb_clients }}</strong><small>{{ a.multi_clients ? 'regroupement multi-clients' : 'client unique' }}</small></div>
          <div class="bea-rc-kpi"><p>Montant du fichier</p><strong>{{ parDevise(a.totaux) }}</strong><small>lignes valides, par devise</small></div>
          <div class="bea-rc-kpi"><p>À extourner</p><strong>{{ parDevise(a.totaux, 'montant_conteste') }}</strong></div>
          <div class="bea-rc-kpi"><p>Dossier après import</p><strong>{{ a.apres_import.nb }}</strong><small>opérations · {{ parDevise(a.apres_import) }}</small></div>
        </div>

        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Client / compte</th><th>Vérification</th><th class="bea-rc-ops__m">Opérations</th><th class="bea-rc-ops__m">En erreur</th><th class="bea-rc-ops__m">Montant</th><th class="bea-rc-ops__m">Contesté</th></tr></thead>
            <tbody>
              @for (c of a.clients; track c.racine ?? 'aucun') {
                <tr>
                  <td><strong>{{ c.nom || (c.racine ? 'Client ' + c.racine : 'Client non renseigné') }}</strong>
                    @if (c.racine) { <code>{{ c.racine }}</code> }
                    @if (c.principal) { <span class="bea-ct-badge" data-tone="INFO">Principal</span> }
                  </td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="ton(c.statut)">{{ libelle(c.statut) }}</span></td>
                  <td class="bea-rc-ops__m">{{ c.nb }}</td><td class="bea-rc-ops__m">{{ c.nb_erreurs || '' }}</td>
                  <td class="bea-rc-ops__m">{{ parDevise(c) }}</td><td class="bea-rc-ops__m">{{ parDevise(c, 'montant_conteste') }}</td>
                </tr>
                @for (k of c.comptes; track k.compte_reference ?? 'aucun') {
                  <tr>
                    <td [style.padding-left.rem]="2"><span class="bea-rc-muted">└ </span>{{ k.compte_reference ? 'Compte ' + k.compte_reference : 'Compte non renseigné' }}</td>
                    <td><span class="bea-ct-badge" [attr.data-tone]="ton(k.statut)">{{ libelle(k.statut) }}</span></td>
                    <td class="bea-rc-ops__m">{{ k.nb }}</td><td class="bea-rc-ops__m">{{ k.nb_erreurs || '' }}</td>
                    <td class="bea-rc-ops__m">{{ parDevise(k) }}</td><td class="bea-rc-ops__m">{{ parDevise(k, 'montant_conteste') }}</td>
                  </tr>
                }
              }
            </tbody>
          </table>
        </div>

        <div class="bea-rc-pj__chips">
          <button type="button" [class.is-on]="filtre() === 'TOUTES'" (click)="filtre.set('TOUTES')">Toutes <small>{{ a.nb_lignes }}</small></button>
          <button type="button" [class.is-on]="filtre() === 'ERREUR'" (click)="filtre.set('ERREUR')">Erreurs <small>{{ a.nb_erreurs }}</small></button>
          <button type="button" [class.is-on]="filtre() === 'AVERTISSEMENT'" (click)="filtre.set('AVERTISSEMENT')">Avertissements <small>{{ a.nb_avertissements }}</small></button>
          @if (a.nb_erreurs || a.nb_avertissements) {
            <button type="button" (click)="rapport()" [disabled]="busy()"><mat-icon inline>download</mat-icon> Rapport d’erreurs (Excel)</button>
          }
        </div>
        <div class="bea-mg__table-wrap bea-rc-import__lignes">
          <table class="bea-mg__table bea-rc-ops">
            <thead><tr><th class="bea-rc-ops__n">Ligne</th><th>Client</th><th>Compte</th><th>Référence</th><th>Date</th><th>D/C</th><th>Devise</th>
              <th class="bea-rc-ops__m">Montant initial</th><th class="bea-rc-ops__m">À extourner</th><th>Contrôles</th></tr></thead>
            <tbody>
              @for (l of lignes(); track l.ligne) {
                <tr [attr.data-statut]="l.statut">
                  <td class="bea-rc-ops__n">{{ l.ligne }}</td>
                  <td [class.is-invalid]="ko(l, 'client_racine')">{{ l.client_racine ?? '—' }}</td>
                  <td [class.is-invalid]="ko(l, 'compte_reference')">{{ l.compte_reference ?? '—' }}</td>
                  <td [class.is-invalid]="ko(l, 'reference')">{{ l.reference || '—' }}</td>
                  <td [class.is-invalid]="ko(l, 'date_operation')">{{ l.date_operation ? date(l.date_operation) : '—' }}</td>
                  <td [class.is-invalid]="ko(l, 'nature_mouvement')">{{ l.nature_mouvement === 'DEBIT' ? 'D' : l.nature_mouvement === 'CREDIT' ? 'C' : '—' }}</td>
                  <td [class.is-invalid]="ko(l, 'devise')">{{ l.devise ?? '—' }}</td>
                  <td class="bea-rc-ops__m" [class.is-invalid]="ko(l, 'montant')">{{ montant(l.montant, l.devise) }}</td>
                  <td class="bea-rc-ops__m" [class.is-invalid]="ko(l, 'montant_conteste')">{{ l.montant_conteste ? montant(l.montant_conteste, l.devise) : '' }}</td>
                  <td>
                    @for (m of l.erreurs; track $index) { <span class="bea-rc-import__msg bea-rc-import__msg--err">{{ m }}</span> }
                    @for (m of l.avertissements; track $index) { <span class="bea-rc-import__msg bea-rc-import__msg--warn">{{ m }}</span> }
                    @if (l.statut === 'OK') { <span class="bea-rc-hint">OK</span> }
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="10" class="bea-rc-muted">Aucune ligne pour ce filtre.</td></tr>
              }
            </tbody>
          </table>
        </div>

        @if (a.multi_clients) {
          @if (!a.regroupement_autorise) {
            <div class="bea-rc-note bea-rc-note--warn"><mat-icon>block</mat-icon>
              <span>La banque n’autorise pas le regroupement de plusieurs clients dans un même dossier : créez un dossier par client.</span></div>
          } @else {
            <label class="bea-rc-label">Justification du regroupement de {{ a.nb_clients }} clients @if (a.justification_requise) { <em>*</em> }
              <textarea class="bea-rc-input" rows="2" maxlength="4000" [value]="justification()" (input)="justification.set($any($event.target).value)"
                        [placeholder]="a.justification_actuelle ?? 'Ex. même fraude touchant plusieurs clients, opérations liées…'"></textarea>
            </label>
          }
        }
        @if (a.mode === 'REMPLACEMENT' && a.nb_conservees === 0 && dossier().nb_operations) {
          <div class="bea-rc-note bea-rc-note--warn"><mat-icon>warning</mat-icon>
            <span>Les {{ dossier().nb_operations }} opération(s) actuelles du dossier seront remplacées (elles restent dans l’historique).</span></div>
        }
        <span class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="abandonner()"><mat-icon>close</mat-icon> Abandonner</button>
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !confirmable()" (click)="confirmer()">
            <mat-icon>done_all</mat-icon> Confirmer l’import ({{ a.nb_valides }} opération{{ a.nb_valides > 1 ? 's' : '' }})
          </button>
        </span>
      </div>
    }

    @if (historique().length) {
      <div class="bea-rc-pad">
        <p class="bea-rc-hint"><strong>Imports précédents</strong></p>
        <ul class="bea-rc-mini">
          @for (i of historique(); track i.id) {
            <li class="bea-rc-mini__row">
              <span class="bea-ct-badge" [attr.data-tone]="i.statut === 'CONFIRME' ? 'ACTIF' : i.statut === 'ANALYSE' ? 'INFO' : 'SUSPENDU'">{{ statutImport(i.statut) }}</span>
              <span class="bea-rc-mini__obj">{{ i.nom_fichier }} — {{ i.nb_lignes }} ligne(s){{ i.mode === 'REMPLACEMENT' ? ', remplacement' : '' }}</span>
              <small class="bea-rc-hint">{{ date(i.confirme_le ?? i.created_at, true) }} · {{ i.confirme_par ?? i.par ?? '' }}</small>
            </li>
          }
        </ul>
      </div>
    }
  `,
})
export class RcImportComponent {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(UiDialogService);
  readonly store = inject(ReclamationsStore);
  readonly dossier = input.required<Dossier>();
  readonly modifie = output<Dossier>();

  readonly busy = signal(false);
  readonly mode = signal<Mode>('AJOUT');
  readonly fichier = signal<File | null>(null);
  readonly analyse = signal<ImportAnalyse | null>(null);
  readonly filtre = signal<Filtre>('TOUTES');
  readonly justification = signal('');

  readonly historique = computed(() => this.dossier().imports.filter((i) => i.statut !== 'ANALYSE'));
  readonly lignes = computed<ImportLigne[]>(() => {
    const f = this.filtre();
    const l = this.analyse()?.lignes ?? [];
    return f === 'TOUTES' ? l : l.filter((x) => x.statut === f);
  });
  readonly confirmable = computed(() => {
    const a = this.analyse();
    if (!a || a.nb_erreurs || !a.nb_valides) return false;
    if (a.multi_clients && (!a.regroupement_autorise || (a.justification_requise && !this.justification().trim()))) return false;
    return true;
  });

  /** Analyse en attente (ouverte par un autre écran) : reprise à l'affichage du dossier. */
  private readonly vus = new Set<string>();
  private readonly reprise = effect(() => {
    const d = this.dossier();
    const enCours = d.imports.find((i) => i.statut === 'ANALYSE');
    if (!enCours || this.vus.has(enCours.id)) return;
    this.vus.add(enCours.id);
    this.rc.lireImport(d.id, enCours.id).subscribe({
      next: (a) => {
        if (a.statut === 'ANALYSE' && !this.analyse()) this.analyse.set(a);
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Import en attente indisponible')),
    });
  });

  readonly colonnesRequises = computed(() => {
    const regle = this.dossier().regle;
    const libelles = new Map((this.store.config()?.champs_operation ?? []).map((c) => [c.code, c.libelle]));
    return (regle?.champs_requis ?? ['reference', 'montant']).map((c) => libelles.get(c) ?? c).join(', ');
  });

  montant(v: string | null | undefined, devise?: string | null): string {
    return montantFr(v, devise ?? 'MRU');
  }

  parDevise(t: ImportTotaux, champ: 'montant' | 'montant_conteste' = 'montant'): string {
    return t.par_devise ? totauxParDevise(t.par_devise, champ) : montantFr(t[champ], t.devise ?? 'MRU');
  }

  ko(l: ImportLigne, champ: string): boolean {
    return !!l.erreurs_detail?.some((e) => e.champ === champ);
  }

  rapport(): void {
    const a = this.analyse();
    if (!a) return;
    this.feedback
      .run(() => this.rc.rapportImport(this.dossier().id, a.id), {
        busy: this.busy,
        loading: 'Préparation du rapport…',
        success: () => ({ title: 'Rapport téléchargé' }),
        errorTitle: 'Téléchargement refusé',
        retry: false,
      })
      .subscribe((b) => telechargerBlob(b, `rapport-import-${this.dossier().reference}.xlsx`));
  }

  date(iso: string | null, heure = false): string {
    return dateFr(iso, heure);
  }

  libelle(s: keyof typeof STATUT_ID_LIBELLE): string {
    return STATUT_ID_LIBELLE[s] ?? s;
  }

  ton(s: keyof typeof STATUT_ID_TON): string {
    return STATUT_ID_TON[s] ?? 'INFO';
  }

  statutImport(s: string): string {
    return s === 'CONFIRME' ? 'Confirmé' : s === 'ANALYSE' ? 'En attente' : 'Abandonné';
  }

  choisir(e: Event): void {
    this.fichier.set((e.target as HTMLInputElement).files?.[0] ?? null);
  }

  modele(): void {
    this.feedback
      .run(() => this.rc.modeleImport(this.dossier().motif_ref?.id), {
        busy: this.busy,
        loading: 'Préparation du modèle…',
        success: () => ({ title: 'Modèle téléchargé' }),
        errorTitle: 'Téléchargement refusé',
        retry: false,
      })
      .subscribe((b) => telechargerBlob(b, 'modele-import-operations-reclamation.xlsx'));
  }

  analyser(forcer = false): void {
    const f = this.fichier();
    if (!f) return;
    this.busy.set(true);
    this.rc.analyserImport(this.dossier().id, f, this.mode(), forcer).subscribe({
      next: (a) => {
        this.busy.set(false);
        this.vus.add(a.id);
        this.filtre.set(a.nb_erreurs ? 'ERREUR' : 'TOUTES');
        this.justification.set('');
        this.analyse.set(a);
        if (a.nb_erreurs) {
          this.feedback.warning({ title: 'Fichier analysé : erreurs à corriger', message: `${a.nb_erreurs} ligne(s) en erreur sur ${a.nb_lignes}.` });
        } else {
          this.feedback.success({ title: 'Fichier analysé', message: `${a.nb_valides} opération(s) prêtes à être importées. Vérifiez l’aperçu puis confirmez.` });
        }
      },
      error: (e) => {
        this.busy.set(false);
        void describeApiErrorAsync(e).then((info) => {
          if (info.code !== 'FICHIER_DEJA_IMPORTE' || forcer) {
            this.feedback.apiError(info, 'Analyse refusée');
            return;
          }
          // Réimport accidentel : seulement sur choix explicite (tracé dans l'audit).
          this.dialog.confirm({
            title: 'Fichier déjà importé',
            message: 'Ce fichier a déjà été importé sur ce dossier. L’analyser à nouveau ?',
            hint: 'Les lignes déjà présentes seront signalées comme doublons ; rien n’est supprimé.',
            confirmLabel: 'Analyser à nouveau',
            tone: 'warn',
            icon: 'content_copy',
          }).subscribe((ok) => {
            if (ok) this.analyser(true);
          });
        });
      },
    });
  }

  confirmer(): void {
    const a = this.analyse();
    if (!a) return;
    const remplace = a.mode === 'REMPLACEMENT';
    this.feedback
      .run(() => this.rc.confirmerImport(this.dossier().id, a.id, {
        revision: this.dossier().revision,
        justification_regroupement: this.justification().trim() || null,
      }), {
        confirm: {
          title: 'Confirmer l’import',
          message: remplace
            ? `Remplacer les opérations du dossier par les ${a.nb_valides} opération(s) du fichier ?`
            : `Ajouter ${a.nb_valides} opération(s) au dossier ?`,
          confirmLabel: 'Confirmer l’import',
          tone: remplace ? 'warn' : 'success',
        },
        busy: this.busy,
        loading: 'Enregistrement des opérations…',
        success: (d) => ({
          title: 'Import confirmé',
          details: [
            { label: 'Opérations du dossier', value: String(d.nb_operations) },
            { label: 'Montants', value: totauxParDevise(d.par_devise) },
          ],
        }),
        errorTitle: 'Import refusé',
        retry: false,
      })
      .subscribe((d) => {
        this.analyse.set(null);
        this.fichier.set(null);
        this.modifie.emit(d);
      });
  }

  abandonner(): void {
    const a = this.analyse();
    if (!a) return;
    this.feedback
      .run(() => this.rc.abandonnerImport(this.dossier().id, a.id), {
        confirm: { title: 'Abandonner l’import', message: 'Aucune opération ne sera enregistrée. Le fichier reste tracé dans le dossier.', confirmLabel: 'Abandonner', tone: 'warn' },
        busy: this.busy,
        success: () => ({ title: 'Import abandonné' }),
        errorTitle: 'Action refusée',
        retry: false,
      })
      .subscribe(() => {
        this.analyse.set(null);
        this.fichier.set(null);
        this.rc.lire(this.dossier().id).subscribe({ next: (d) => this.modifie.emit(d) });
      });
  }
}
