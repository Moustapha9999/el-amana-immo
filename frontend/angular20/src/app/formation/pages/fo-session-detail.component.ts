import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable } from 'rxjs';
import { ApiErrorInfo, describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { FoDonutComponent } from '../formation-charts';
import { FormationUiComponent } from '../formation-ui.component';
import {
  FO_BASE, FeuilleSignee, FeuillesSession, JournalLigne, Page, Participant, Presence, Session, correspond, dateFr, dateHeureFr, initiales, jourMois, statutAffiche, taux, telecharger,
} from '../formation.models';
import { FormationStore } from '../formation.store';
import { FoEmployePickerComponent } from '../shared/fo-employe-picker.component';

type Action = 'cloturer' | 'rouvrir' | 'annuler' | 'retablir' | 'archiver' | 'desarchiver';

@Component({
  selector: 'bea-fo-session-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, FormationUiComponent, FoDonutComponent, FoEmployePickerComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <button type="button" class="bea-fo-back" (click)="router.navigate(['/formation/sessions'])"><mat-icon>arrow_back</mat-icon> Formations</button>

      @if (!s()) {
        <div class="bea-fo-hero"><span class="bea-fx-skel bea-fx-skel--box" style="width:4.6rem;height:5rem"></span>
          <div style="flex:1"><span class="bea-fx-skel bea-fx-skel--title"></span><span class="bea-fx-skel bea-fx-skel--line"></span></div></div>
        <div class="bea-fx-kpis">@for (i of [1, 2, 3, 4, 5]; track i) { <span class="bea-fx-skel bea-fx-skel--kpi"></span> }</div>
        <span class="bea-fx-skel bea-fx-skel--chart"></span>
      } @else {
        @let f = s()!;
        <section class="bea-fo-hero">
          <span class="bea-fo-date bea-fo-date--lg" [class.bea-fo-date--warn]="f.a_saisir" [class.bea-fo-date--muted]="f.statut === 'ANNULEE' || f.statut === 'ARCHIVEE'">
            <b>{{ jm(f.date_session).jour }}</b><span>{{ jm(f.date_session).mois }} {{ jm(f.date_session).annee }}</span>
          </span>
          <div class="bea-fo-hero__main">
            <div style="display:flex;flex-wrap:wrap;gap:0.4rem;align-items:center">
              <span class="bea-mg__code">{{ f.reference }}</span>
              <span class="bea-fo-badge" [attr.data-s]="st(f).code">{{ st(f).label }}</span>
              @if (f.source === 'IMPORT') { <span class="bea-fo-tag bea-fo-tag--muted"><mat-icon style="font-size:0.9rem;width:0.9rem;height:0.9rem">upload_file</mat-icon> Import Excel</span> }
            </div>
            <h1>{{ f.intitule || f.theme_libelle }}</h1>
            <div class="bea-fo-hero__meta">
              @if (f.intitule) { <span><mat-icon>category</mat-icon>{{ f.theme_libelle }}</span> }
              <span><mat-icon>place</mat-icon>{{ f.lieu?.libelle || '—' }}</span>
              <span><mat-icon>record_voice_over</mat-icon>{{ f.formateur_libelle || '—' }}</span>
              <span><mat-icon>calendar_today</mat-icon>{{ dateFr(f.date_session) }}</span>
            </div>
          </div>
          <div class="bea-fo-hero__actions">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="feuille('pdf')" [disabled]="telechargement()"><mat-icon>picture_as_pdf</mat-icon> Feuille PDF</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="feuille('xlsx')" [disabled]="telechargement()"><mat-icon>grid_on</mat-icon> Feuille Excel</button>
            @if (f.actions.modifier) {
              <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/formation/sessions', f.id, 'modifier']"><mat-icon>edit</mat-icon> Modifier</a>
            }
            @if (f.actions.cloturer) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="statut('cloturer')" [disabled]="busy()"><mat-icon>task_alt</mat-icon> Clôturer</button>
            }
            @if (f.actions.rouvrir) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="statut('rouvrir')" [disabled]="busy()"><mat-icon>lock_open</mat-icon> Rouvrir</button>
            }
            @if (f.actions.archiver) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="statut('archiver')" [disabled]="busy()"><mat-icon>inventory_2</mat-icon> Archiver</button>
            }
            @if (f.actions.desarchiver) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="statut('desarchiver')" [disabled]="busy()"><mat-icon>unarchive</mat-icon> Désarchiver</button>
            }
            @if (f.actions.retablir) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="statut('retablir')" [disabled]="busy()"><mat-icon>restore</mat-icon> Rétablir</button>
            }
            @if (f.actions.annuler) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" style="color:#b91c1c" (click)="statut('annuler')" [disabled]="busy()"><mat-icon>event_busy</mat-icon> Annuler</button>
            }
            @if (f.actions.supprimer) {
              <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer définitivement" (click)="supprimer()" [disabled]="busy()"><mat-icon>delete</mat-icon></button>
            }
          </div>
        </section>

        @if (f.statut === 'ANNULEE' && f.motif_annulation) {
          <div class="bea-fo-note bea-fo-note--danger"><mat-icon>event_busy</mat-icon><span><strong>Formation annulée.</strong> Motif : {{ f.motif_annulation }}</span></div>
        }
        @if (f.a_saisir && !saisie()) {
          <div class="bea-fo-note"><mat-icon>edit_calendar</mat-icon>
            <span style="flex:1"><strong>La formation a eu lieu :</strong> saisissez les présences (PRÉSENT / ABSENT) pour chaque participant.</span>
            @if (f.actions.saisir_presences) { <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="demarrerSaisie()"><mat-icon>fact_check</mat-icon> Saisir les présences</button> }
          </div>
        }
        @if (f.statut === 'REALISEE' && f.actions.cloturer) {
          <div class="bea-fo-note bea-fo-note--info"><mat-icon>info</mat-icon><span>Toutes les présences sont saisies. Clôturez la formation pour la verrouiller.</span></div>
        }
        @if ((f.statut === 'REALISEE' || f.statut === 'CLOTUREE') && feuilles()?.items?.length === 0) {
          <div class="bea-fo-note"><mat-icon>draw</mat-icon>
            <span style="flex:1"><strong>Feuille de présence signée manquante.</strong> Déposez le scan signé pour archiver la preuve dans la GED.</span>
            @if (feuilles()!.actions.deposer) { <a class="bea-mg__btn bea-mg__btn--ghost" href="#feuille-signee" (click)="allerFeuille($event)"><mat-icon>upload_file</mat-icon> Déposer</a> }
          </div>
        }
        @if (f.a_venir) {
          <div class="bea-fo-note bea-fo-note--info"><mat-icon>event_upcoming</mat-icon><span>Formation à venir : imprimez la feuille de présence à faire signer le jour J. La saisie des présences sera possible à partir du {{ dateFr(f.date_session) }}.</span></div>
        }

        <div class="bea-fx-kpis">
          <div class="bea-fx-kpi"><mat-icon>groups</mat-icon><p>Participants</p><strong>{{ stats().participants }}</strong><small>convoqué(s)</small></div>
          <div class="bea-fx-kpi" data-tone="ok"><mat-icon>how_to_reg</mat-icon><p>Présents</p><strong>{{ stats().presents }}</strong><small>&nbsp;</small></div>
          <div class="bea-fx-kpi" data-tone="danger"><mat-icon>person_off</mat-icon><p>Absents</p><strong>{{ stats().absents }}</strong><small>&nbsp;</small></div>
          <div class="bea-fx-kpi" data-tone="warn"><mat-icon>pending</mat-icon><p>Non saisis</p><strong>{{ stats().non_saisis }}</strong><small>&nbsp;</small></div>
          <div class="bea-fx-kpi" data-tone="brand"><mat-icon>percent</mat-icon><p>Taux de présence</p><strong>{{ taux(stats().taux_presence) }}</strong>
            <span class="bea-fo-progress" style="margin-top:0.35rem">
              <i class="is-p" [style.width.%]="pct(stats().presents)"></i><i class="is-a" [style.width.%]="pct(stats().absents)"></i>
            </span>
          </div>
        </div>

        <nav class="bea-ct-tabs" style="margin-bottom:0.9rem">
          <button type="button" [class.is-on]="onglet() === 'participants'" (click)="onglet.set('participants')"><mat-icon>groups</mat-icon> Participants &amp; présences <span class="bea-fx-count">{{ f.stats.participants }}</span></button>
          <button type="button" [class.is-on]="onglet() === 'historique'" (click)="ouvrirHistorique()"><mat-icon>history</mat-icon> Historique</button>
        </nav>

        @if (onglet() === 'participants') {
          <div class="bea-fo-grid">
            <section class="bea-mg__panel bea-fo-span2" style="grid-column: span 2">
              <div class="bea-mg__panel-top">
                <div><h2>{{ saisie() ? 'Saisie des présences' : 'Liste des participants' }}</h2>
                  <p class="bea-fo-panel-sub">{{ saisie() ? 'Cliquez PRÉSENT ou ABSENT pour chaque participant, puis enregistrez.' : 'Présence : PRÉSENT ou ABSENT uniquement.' }}</p></div>
                <div class="bea-fo-panel-top-actions">
                  <label class="bea-mg__field" style="min-width:12rem"><mat-icon>search</mat-icon><input type="search" placeholder="Filtrer…" [value]="filtre()" (input)="filtre.set($any($event.target).value)" /></label>
                  @if (saisie()) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="tous('PRESENT')"><mat-icon>done_all</mat-icon> Tous présents</button>
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="tous('ABSENT')"><mat-icon>remove_done</mat-icon> Tous absents</button>
                  } @else {
                    @if (f.actions.saisir_presences) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="demarrerSaisie()"><mat-icon>fact_check</mat-icon> {{ f.stats.presents + f.stats.absents ? 'Modifier les présences' : 'Saisir les présences' }}</button>
                    }
                    @if (f.actions.participants) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ajoutOuvert.set(true)"><mat-icon>person_add</mat-icon> Ajouter</button>
                    }
                  }
                </div>
              </div>
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table bea-fo-table">
                  <thead><tr><th style="width:3rem">N°</th><th>Nom et prénom</th><th>Fonction</th><th>Entité</th><th>Périmètre</th><th style="width:15rem">Présence</th>@if (!saisie() && f.actions.retirer_participants) {<th></th>}</tr></thead>
                  <tbody>
                    @for (p of visibles(); track p.id; let i = $index) {
                      <tr class="bea-fx-row-in" [style.--i]="i < 25 ? i : 0" [class.is-muted]="!p.employe_actif">
                        <td>{{ p.n }}</td>
                        <td>
                          <a class="bea-fo-person" [routerLink]="['/formation/employes', p.employe_id]" style="text-decoration:none">
                            <span class="bea-fo-avatar">{{ ini(p.nom_complet) }}</span>
                            <span><strong>{{ p.nom_complet }}</strong>@if (!p.employe_actif) {<small>désactivé</small>}</span>
                          </a>
                        </td>
                        <td>{{ p.fonction || '—' }}</td>
                        <td>{{ p.entite || '—' }}</td>
                        <td>{{ p.perimetre || '—' }}</td>
                        <td>
                          @if (saisie()) {
                            <span class="bea-fo-presence" role="radiogroup" [attr.aria-label]="'Présence de ' + p.nom_complet">
                              <button type="button" [class.is-p]="valeur(p) === 'PRESENT'" (click)="marquer(p, 'PRESENT')"><mat-icon>check</mat-icon> PRÉSENT</button>
                              <button type="button" [class.is-a]="valeur(p) === 'ABSENT'" (click)="marquer(p, 'ABSENT')"><mat-icon>close</mat-icon> ABSENT</button>
                            </span>
                          } @else {
                            <span class="bea-fo-badge" [attr.data-s]="p.presence ?? 'NON_SAISI'">{{ p.presence === 'PRESENT' ? 'PRÉSENT' : p.presence === 'ABSENT' ? 'ABSENT' : 'Non saisi' }}</span>
                          }
                        </td>
                        @if (!saisie() && f.actions.retirer_participants) {
                          <td class="is-c"><button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Retirer de la formation" (click)="retirer(p)"><mat-icon>person_remove</mat-icon></button></td>
                        }
                      </tr>
                    } @empty {
                      <tr><td colspan="7"><div class="bea-fo-empty"><mat-icon>group_off</mat-icon><strong>Aucun participant</strong>
                        @if (f.actions.participants) { <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ajoutOuvert.set(true)"><mat-icon>person_add</mat-icon> Ajouter des participants</button> }
                      </div></td></tr>
                    }
                  </tbody>
                </table>
              </div>
            </section>
            <div class="bea-fo-side">
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Répartition</h2></div>
              <bea-fo-donut [parts]="parts()" [centre]="taux(stats().taux_presence)" unite="présence" />
              <dl class="bea-fo-dl" style="border-top:1px solid #eef2f7">
                <dt>Créée le</dt><dd>{{ dh(f.created_at) }}</dd>
                <dt>Présences saisies</dt><dd>{{ dh(f.presences_saisies_le) }}</dd>
                @if (f.cloturee_le) { <dt>Clôturée le</dt><dd>{{ dh(f.cloturee_le) }}</dd> }
                @if (f.observations) { <dt>Observations</dt><dd>{{ f.observations }}</dd> }
              </dl>
            </section>
            <section class="bea-mg__panel" id="feuille-signee">
              <div class="bea-mg__panel-top">
                <div><h2>Feuille de présence signée</h2><p class="bea-fo-panel-sub">Archivée dans la GED, rattachée à {{ f.reference }}</p></div>
                <span class="bea-mg__count">{{ feuilles()?.items?.length ?? 0 }}</span>
              </div>
              <div class="bea-fo-docs">
                @if (!feuilles()) {
                  <span class="bea-fx-skel bea-fx-skel--line"></span><span class="bea-fx-skel bea-fx-skel--line"></span>
                } @else {
                  @let fs = feuilles()!;
                  @for (d of fs.items; track d.id; let i = $index) {
                    <div class="bea-fo-doc" [style.--i]="i" [attr.data-k]="estPdf(d) ? 'pdf' : 'img'">
                      <mat-icon>{{ estPdf(d) ? 'picture_as_pdf' : 'image' }}</mat-icon>
                      <span class="bea-fo-doc__txt">
                        <strong [title]="d.filename">{{ d.filename }}</strong>
                        <small>{{ poids(d.size_bytes) }} · {{ dh(d.created_at) }}@if (d.uploaded_by) { · {{ d.uploaded_by }} }</small>
                      </span>
                      <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="ouvrirFeuille(d)" [disabled]="telechargement()"><mat-icon>download</mat-icon></button>
                      @if (fs.actions.retirer) {
                        <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Retirer" (click)="retirerFeuille(d)" [disabled]="depot()"><mat-icon>delete</mat-icon></button>
                      }
                    </div>
                  } @empty {
                    @if (!f.a_venir && f.statut !== 'ANNULEE') {
                      <p class="bea-fo-docs__empty"><mat-icon>warning_amber</mat-icon> Aucune feuille signée déposée.</p>
                    } @else {
                      <p class="bea-fo-hint" style="margin:0">{{ f.a_venir ? 'Le dépôt sera possible une fois la formation passée.' : 'Aucune feuille déposée.' }}</p>
                    }
                  }
                  @if (fs.items.length) {
                    <span class="bea-fo-docs__ok"><mat-icon>verified</mat-icon> Preuve de présence archivée</span>
                  }
                  @if (fs.actions.deposer) {
                    <label class="bea-fo-drop" [class.is-over]="survolFeuille()" [class.is-busy]="depot()"
                           (dragover)="$event.preventDefault(); survolFeuille.set(true)" (dragleave)="survolFeuille.set(false)" (drop)="deposerFeuille($event)">
                      <input type="file" accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff" hidden [disabled]="depot()" (change)="choisirFeuille($any($event.target))" />
                      @if (depot()) {
                        <mat-icon class="bea-fo-spin">progress_activity</mat-icon><strong>Dépôt en cours…</strong>
                      } @else {
                        <mat-icon>upload_file</mat-icon>
                        <strong>{{ fs.items.length ? 'Ajouter une page / un scan' : 'Déposer la feuille signée' }}</strong>
                        <span>PDF ou scan (JPG, PNG, TIF) — 25 Mo max</span>
                      }
                    </label>
                  } @else if (f.statut === 'CLOTUREE' && fs.items.length) {
                    <p class="bea-fo-hint" style="margin:0">Formation clôturée : les pièces sont figées (rouvrir pour corriger).</p>
                  }
                }
              </div>
            </section>
            </div>
          </div>

          @if (saisie()) {
            <div class="bea-fo-saisie-bar">
              <span><strong>{{ nbModifs() }}</strong> modification(s) · {{ stats().presents }} présent(s), {{ stats().absents }} absent(s), {{ stats().non_saisis }} non saisi(s)</span>
              <span style="display:flex;gap:0.5rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="annulerSaisie()">Annuler</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !nbModifs()" (click)="enregistrerPresences()"><mat-icon>save</mat-icon> Enregistrer les présences</button>
              </span>
            </div>
          }
        } @else {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Historique des actions</h2><span class="bea-mg__count">{{ historique()?.length ?? 0 }}</span></div>
            @if (!historique()) {
              <div class="bea-fo-pad">@for (i of [1, 2, 3]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }</div>
            } @else {
              <ul class="bea-fo-timeline">
                @for (h of historique(); track h.id; let i = $index) {
                  <li [style.--i]="i" [attr.data-k]="cleAction(h.action)">
                    <div class="bea-fo-timeline__head"><strong>{{ h.libelle }}</strong><small>{{ dh(h.date) }} · {{ h.utilisateur }}</small></div>
                    @if (resume(h)) { <p>{{ resume(h) }}</p> }
                  </li>
                } @empty {
                  <li>Aucune action enregistrée.</li>
                }
              </ul>
            }
          </section>
        }
      }
    </div>

    @if (ajoutOuvert() && s()) {
      <div class="bea-mg__backdrop" (click)="fermerAjout()"></div>
      <div class="bea-mg__modal bea-ct-modal bea-fo-modal-wide" role="dialog" aria-modal="true">
        <header class="bea-ct-modal__head">
          <h2><mat-icon>person_add</mat-icon> Ajouter des participants</h2>
          <button type="button" class="bea-ct-view__close" (click)="fermerAjout()" aria-label="Fermer"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-ct-modal__body">
          <bea-fo-employe-picker [(selection)]="ajouts" [exclus]="inscrits()" />
        </div>
        <footer class="bea-ct-modal__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerAjout()">Annuler</button>
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!ajouts().length || busy()" (click)="ajouterParticipants()">
            <mat-icon>check</mat-icon> Ajouter {{ ajouts().length || '' }} participant(s)
          </button>
        </footer>
      </div>
    }
  `,
})
export class FoSessionDetailComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly store = inject(FormationStore);
  readonly router = inject(Router);

  readonly dateFr = dateFr;
  readonly dh = dateHeureFr;
  readonly taux = taux;
  readonly jm = jourMois;
  readonly ini = initiales;
  readonly st = statutAffiche;

  readonly s = signal<Session | null>(null);
  readonly busy = signal(false);
  readonly telechargement = signal(false);
  readonly onglet = signal<'participants' | 'historique'>('participants');
  readonly historique = signal<JournalLigne[] | null>(null);
  readonly saisie = signal(false);
  readonly brouillon = signal<Record<string, Presence>>({});
  readonly filtre = signal('');
  readonly ajoutOuvert = signal(false);
  readonly ajouts = signal<string[]>([]);
  readonly feuilles = signal<FeuillesSession | null>(null);
  readonly depot = signal(false);
  readonly survolFeuille = signal(false);

  readonly participants = computed(() => this.s()?.participants ?? []);
  readonly inscrits = computed(() => this.participants().map((p) => p.employe_id));
  readonly visibles = computed(() => {
    const q = this.filtre().trim();
    return q ? this.participants().filter((p) => correspond(`${p.nom_complet} ${p.entite ?? ''} ${p.fonction ?? ''}`, q)) : this.participants();
  });
  readonly nbModifs = computed(() => {
    const b = this.brouillon();
    return this.participants().filter((p) => p.id in b && b[p.id] !== p.presence).length;
  });
  readonly stats = computed(() => {
    const ps = this.participants();
    let pr = 0;
    let ab = 0;
    for (const p of ps) {
      const v = this.valeur(p);
      if (v === 'PRESENT') pr++;
      else if (v === 'ABSENT') ab++;
    }
    return { participants: ps.length, presents: pr, absents: ab, non_saisis: ps.length - pr - ab, taux_presence: pr + ab ? Math.round((pr * 1000) / (pr + ab)) / 10 : null };
  });
  readonly parts = computed(() => [
    { label: 'Présents', value: this.stats().presents, color: '#15803d' },
    { label: 'Absents', value: this.stats().absents, color: '#dc2626' },
    { label: 'Non saisis', value: this.stats().non_saisis, color: '#cbd5e1' },
  ]);

  readonly hasUnsavedChanges = unsavedChanges(() => this.saisie() && this.nbModifs() > 0 && !this.busy());

  ngOnInit(): void {
    this.store.charger();
    this.route.paramMap.subscribe((pm) => {
      const id = pm.get('id');
      if (id) this.charger(id, this.route.snapshot.queryParamMap.get('saisie') === '1');
    });
  }

  private charger(id: string, saisie = false): void {
    this.api.get<Session>(`${FO_BASE}/sessions/${id}`).subscribe({
      next: (s) => {
        this.majSession(s);
        if (saisie && s.actions.saisir_presences) this.demarrerSaisie();
      },
      error: (e) => {
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Formation introuvable'));
        void this.router.navigate(['/formation/sessions']);
      },
    });
  }

  private majSession(s: Session): void {
    if (this.s()?.id !== s.id) this.feuilles.set(null);
    this.s.set(s);
    this.historique.set(null);
    if (this.onglet() === 'historique') this.ouvrirHistorique();
    this.chargerFeuilles(s.id);
  }

  private chargerFeuilles(id: string): void {
    this.api.get<FeuillesSession>(`${FO_BASE}/sessions/${id}/documents`).subscribe({
      next: (r) => this.feuilles.set(r),
      error: () => this.feuilles.set({ items: [], actions: { deposer: false, retirer: false } }),
    });
  }

  estPdf(d: FeuilleSignee): boolean {
    return d.mime_type === 'application/pdf' || /\.pdf$/i.test(d.filename);
  }

  poids(octets: number): string {
    if (octets < 1024) return `${octets} o`;
    if (octets < 1024 * 1024) return `${Math.round(octets / 1024)} Ko`;
    return `${(octets / 1024 / 1024).toFixed(1).replace('.', ',')} Mo`;
  }

  allerFeuille(e: Event): void {
    e.preventDefault();
    document.getElementById('feuille-signee')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  deposerFeuille(e: DragEvent): void {
    e.preventDefault();
    this.survolFeuille.set(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) this.envoyerFeuille(f);
  }

  choisirFeuille(input: HTMLInputElement): void {
    const f = input.files?.[0];
    input.value = '';
    if (f) this.envoyerFeuille(f);
  }

  private envoyerFeuille(fichier: File): void {
    const s = this.s()!;
    if (!/\.(pdf|jpe?g|png|tiff?)$/i.test(fichier.name)) {
      this.feedback.warning({ title: 'Format non pris en charge', message: 'Déposez un PDF ou une image scannée (JPG, PNG, TIF).' });
      return;
    }
    if (fichier.size > 25 * 1024 * 1024) {
      this.feedback.warning({ title: 'Fichier trop volumineux', message: '25 Mo maximum.' });
      return;
    }
    this.feedback
      .run(() => this.api.upload<FeuillesSession>(`${FO_BASE}/sessions/${s.id}/documents`, fichier), {
        busy: this.depot,
        loading: 'Dépôt de la feuille signée…',
        success: { title: 'Feuille signée archivée', message: `${fichier.name} — rattachée à ${s.reference} dans la GED` },
        errorTitle: 'Dépôt impossible',
        retry: false,
      })
      .subscribe((r) => {
        this.feuilles.set(r);
        this.historique.set(null);
      });
  }

  retirerFeuille(d: FeuilleSignee): void {
    const s = this.s()!;
    this.feedback
      .runWithReason((motif) => this.api.post<FeuillesSession>(`${FO_BASE}/sessions/${s.id}/documents/${d.id}/retrait`, { motif }), {
        reason: {
          title: 'Retirer la feuille signée',
          message: d.filename,
          hint: 'Le document passe à la corbeille GED ; le retrait est tracé dans l’historique.',
          reasonLabel: 'Motif du retrait', required: true, maxLength: 1000, tone: 'danger', confirmLabel: 'Retirer',
        },
        busy: this.depot,
        loading: 'Retrait…',
        success: { title: 'Feuille retirée', message: d.filename },
        errorTitle: 'Retrait impossible',
      })
      .subscribe((r) => {
        this.feuilles.set(r);
        this.historique.set(null);
      });
  }

  ouvrirFeuille(d: FeuilleSignee): void {
    const s = this.s()!;
    this.telechargement.set(true);
    this.api.download(`${FO_BASE}/sessions/${s.id}/documents/${d.id}/fichier`).subscribe({
      next: (b) => {
        this.telechargement.set(false);
        telecharger(b, d.filename);
      },
      error: (e) => {
        this.telechargement.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Téléchargement impossible'));
      },
    });
  }

  private recharger(): void {
    const s = this.s();
    if (s) this.charger(s.id);
  }

  private surErreur = (e: ApiErrorInfo): void => {
    if (e.code === 'CONFLIT_REVISION') this.recharger();
  };

  pct(n: number): number {
    const t = this.stats().participants;
    return t ? (n / t) * 100 : 0;
  }

  valeur(p: Participant): Presence {
    const b = this.brouillon();
    return this.saisie() && p.id in b ? b[p.id]! : p.presence;
  }

  demarrerSaisie(): void {
    this.brouillon.set({});
    this.saisie.set(true);
    this.onglet.set('participants');
  }

  annulerSaisie(): void {
    if (!this.nbModifs()) {
      this.saisie.set(false);
      return;
    }
    this.feedback
      .confirm({ action: 'annulation', title: 'Abandonner la saisie ?', message: 'Les présences modifiées ne seront pas enregistrées.' })
      .subscribe((ok) => {
        if (ok) {
          this.brouillon.set({});
          this.saisie.set(false);
        }
      });
  }

  marquer(p: Participant, v: 'PRESENT' | 'ABSENT'): void {
    this.brouillon.set({ ...this.brouillon(), [p.id]: v });
  }

  tous(v: 'PRESENT' | 'ABSENT'): void {
    const b = { ...this.brouillon() };
    for (const p of this.visibles()) b[p.id] = v;
    this.brouillon.set(b);
  }

  enregistrerPresences(): void {
    const s = this.s()!;
    const b = this.brouillon();
    const presences: Record<string, Presence> = {};
    let existantes = 0;
    for (const p of this.participants()) {
      if (p.id in b && b[p.id] !== p.presence) {
        presences[p.id] = b[p.id]!;
        if (p.presence) existantes++;
      }
    }
    const appel = (motif: string | null) => this.api.put<Session>(`${FO_BASE}/sessions/${s.id}/presences`, { revision: s.revision, presences, motif });
    const options = {
      busy: this.busy,
      loading: 'Enregistrement des présences…',
      success: (r: Session) => ({
        title: 'Présences enregistrées',
        details: [
          { label: 'Présents', value: String(r.stats.presents) },
          { label: 'Absents', value: String(r.stats.absents) },
          { label: 'Statut', value: r.statut_libelle },
        ],
      }),
      errorTitle: "Échec de l'enregistrement des présences",
      errorHint: 'Votre saisie est conservée.',
      onError: this.surErreur,
    };
    const fin = (r: Session) => {
      this.saisie.set(false);
      this.brouillon.set({});
      this.majSession(r);
    };
    if (existantes) {
      this.feedback
        .runWithReason((motif) => appel(motif), {
          ...options,
          reason: {
            title: 'Modifier des présences déjà saisies',
            message: `${existantes} présence(s) déjà enregistrée(s) vont changer.`,
            hint: 'Le motif est conservé dans l’historique de la formation.',
            reasonLabel: 'Motif de la correction',
            required: true,
            maxLength: 1000,
            confirmLabel: 'Enregistrer',
          },
        })
        .subscribe(fin);
    } else {
      this.feedback.run(() => appel(null), options).subscribe(fin);
    }
  }

  statut(action: Action): void {
    const s = this.s()!;
    const appel = (motif: string | null) => this.api.post<Session>(`${FO_BASE}/sessions/${s.id}/statut`, { revision: s.revision, action, motif });
    const libelles: Record<Action, string> = {
      cloturer: 'Formation clôturée', rouvrir: 'Formation rouverte', annuler: 'Formation annulée',
      retablir: 'Formation rétablie', archiver: 'Formation archivée', desarchiver: 'Formation désarchivée',
    };
    const base = {
      busy: this.busy,
      loading: 'Mise à jour…',
      success: (r: Session) => ({ title: libelles[action], details: [{ label: 'Référence', value: r.reference }, { label: 'Statut', value: r.statut_libelle }] }),
      errorTitle: 'Action impossible',
      onError: this.surErreur,
    };
    let flux: Observable<Session>;
    if (action === 'annuler' || action === 'rouvrir') {
      flux = this.feedback.runWithReason((m) => appel(m), {
        ...base,
        reason: action === 'annuler'
          ? { title: 'Annuler la formation', message: `${s.reference} — ${s.theme_libelle}`, hint: 'La formation reste consultable (statut ANNULÉE) et peut être rétablie.', reasonLabel: "Motif de l'annulation", required: true, maxLength: 1000, tone: 'danger', confirmLabel: 'Annuler la formation', cancelLabel: 'Retour' }
          : { title: 'Rouvrir la formation', message: `${s.reference} redevient modifiable.`, hint: 'La réouverture est tracée.', reasonLabel: 'Motif de la réouverture', required: true, maxLength: 1000, confirmLabel: 'Rouvrir' },
      });
    } else {
      const confirmations = {
        cloturer: { action: 'cloture' as const, message: `Clôturer ${s.reference} ? Les présences seront verrouillées.`, hint: 'Une réouverture reste possible avec motif.' },
        retablir: { action: 'restauration' as const, message: `Rétablir ${s.reference} au statut planifiée ?` },
        archiver: { action: 'archivage' as const, message: `Archiver ${s.reference} ?`, hint: 'Elle reste consultable dans l’onglet Archivées et dans le reporting.' },
        desarchiver: { action: 'restauration' as const, message: `Désarchiver ${s.reference} ?` },
      };
      flux = this.feedback.run(() => appel(null), { ...base, confirm: confirmations[action] });
    }
    flux.subscribe((r) => this.majSession(r));
  }

  supprimer(): void {
    const s = this.s()!;
    const n = s.stats.participants;
    const saisies = s.stats.presents + s.stats.absents;
    this.feedback
      .runWithReason((motif) => this.api.post<void>(`${FO_BASE}/sessions/${s.id}/supprimer`, { motif }), {
        reason: {
          title: 'Supprimer définitivement',
          message: `${s.reference} (${s.statut_libelle.toLowerCase()}) — ${n} participant(s)${saisies ? `, ${saisies} présence(s) saisie(s)` : ''}.`,
          hint: 'Suppression irréversible : participants et présences sont effacés, les feuilles signées passent à la corbeille GED. Le détail est conservé dans le journal d’audit.',
          reasonLabel: 'Motif de la suppression', required: true, maxLength: 1000, tone: 'danger', confirmLabel: 'Supprimer',
        },
        busy: this.busy,
        loading: 'Suppression…',
        success: { title: 'Formation supprimée', message: s.reference },
        errorTitle: 'Suppression impossible',
      })
      .subscribe(() => void this.router.navigate(['/formation/sessions']));
  }

  retirer(p: Participant): void {
    const s = this.s()!;
    const appel = (motif: string | null) =>
      this.api.post<Session>(`${FO_BASE}/sessions/${s.id}/participants/${p.id}/retrait`, { revision: s.revision, motif });
    const base = {
      busy: this.busy,
      loading: 'Retrait…',
      success: { title: 'Participant retiré', message: p.nom_complet },
      errorTitle: 'Retrait impossible',
      onError: this.surErreur,
    };
    const flux = p.presence
      ? this.feedback.runWithReason((m) => appel(m), {
          ...base,
          reason: { title: 'Retirer un participant', message: `${p.nom_complet} a une présence saisie (${p.presence}).`, reasonLabel: 'Motif du retrait', required: true, maxLength: 1000, tone: 'danger', confirmLabel: 'Retirer' },
        })
      : this.feedback.run(() => appel(null), { ...base, confirm: { action: 'suppression', title: 'Retirer le participant', message: `Retirer ${p.nom_complet} de la formation ?` } });
    flux.subscribe((r) => this.majSession(r));
  }

  fermerAjout(): void {
    this.ajoutOuvert.set(false);
    this.ajouts.set([]);
  }

  ajouterParticipants(): void {
    const s = this.s()!;
    const ids = this.ajouts();
    this.feedback
      .run(() => this.api.post<Session>(`${FO_BASE}/sessions/${s.id}/participants`, { revision: s.revision, employe_ids: ids }), {
        busy: this.busy,
        loading: 'Ajout des participants…',
        success: { title: 'Participants ajoutés', message: `${ids.length} employé(s) convoqué(s)` },
        errorTitle: "Échec de l'ajout",
        onError: this.surErreur,
      })
      .subscribe((r) => {
        this.fermerAjout();
        this.majSession(r);
      });
  }

  feuille(format: 'pdf' | 'xlsx'): void {
    const s = this.s()!;
    this.telechargement.set(true);
    this.api.download(`${FO_BASE}/sessions/${s.id}/feuille-presence`, { format }).subscribe({
      next: (b) => {
        this.telechargement.set(false);
        telecharger(b, `Feuille_presence_${s.reference}.${format}`);
      },
      error: (e) => {
        this.telechargement.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Téléchargement impossible'));
      },
    });
  }

  ouvrirHistorique(): void {
    this.onglet.set('historique');
    const s = this.s();
    if (!s || this.historique()) return;
    this.api.get<Page<JournalLigne>>(`${FO_BASE}/sessions/${s.id}/historique`).subscribe({
      next: (p) => this.historique.set(p.items),
      error: () => this.historique.set([]),
    });
  }

  cleAction(a: string): string {
    if (a.includes('cancel')) return 'cancel';
    if (a.includes('delete') || a.includes('remove')) return 'delete';
    if (a.includes('close')) return 'close';
    if (a.includes('presence')) return 'attendance';
    return 'other';
  }

  resume(h: JournalLigne): string {
    const a = h.apres ?? {};
    const parts: string[] = [];
    if (typeof a['motif'] === 'string' && a['motif']) parts.push(`Motif : ${a['motif']}`);
    if (typeof a['statut'] === 'string' && h.action !== 'formation.presence.update') parts.push(`Statut : ${a['statut']}`);
    if (typeof a['ajoutes'] === 'number') parts.push(`${a['ajoutes']} participant(s) ajouté(s)`);
    if (h.action === 'formation.participant.remove' && h.avant && typeof h.avant['employe'] === 'string') parts.push(`Participant : ${h.avant['employe']}`);
    if (h.action === 'formation.presence.update') {
      const n = Object.keys(a).filter((k) => k !== 'motif' && k !== 'statut').length;
      parts.unshift(`${n} présence(s) modifiée(s)`);
    }
    const fichier = a['fichier'] ?? h.avant?.['fichier'];
    if (typeof fichier === 'string') parts.unshift(`Fichier : ${fichier}`);
    if (typeof a['document'] === 'string') parts.push(a['document'] === 'feuille_presence' ? 'Feuille de présence' : 'Rapport');
    return parts.join(' · ');
  }
}
