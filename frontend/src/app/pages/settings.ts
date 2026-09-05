import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../core/api';
import { ClassStore } from '../core/class-store';
import { LeagueStore } from '../core/league-store';
import { League } from '../core/api.types';

interface LeagueDraft {
  id: string | null;
  name: string;
  leagueUrl: string;
  defaultLid: number | null;
  classNames: Set<string>;
}

function emptyDraft(): LeagueDraft {
  return { id: null, name: '', leagueUrl: '', defaultLid: null, classNames: new Set() };
}

type SettingsTab = 'leagues' | 'classes' | 'cookie';

@Component({
  selector: 'app-settings',
  imports: [FormsModule],
  template: `
    <h1>Settings</h1>

    <nav class="tabs">
      <button type="button" [class.active]="tab() === 'leagues'" (click)="tab.set('leagues')">
        Leagues
      </button>
      <button type="button" [class.active]="tab() === 'classes'" (click)="tab.set('classes')">
        Draft classes
        @if (unmappedCount() > 0) { <span class="badge">{{ unmappedCount() }}</span> }
      </button>
      <button type="button" [class.active]="tab() === 'cookie'" (click)="tab.set('cookie')">
        Session cookie
      </button>
    </nav>

    @if (tab() === 'leagues') {
      <section class="block">
        <h2>Leagues</h2>
        <p class="muted">
          Each league has its own StatsPlus home URL. “Refresh drafted” for a class
          calls <code>&lt;that league’s URL&gt;/api/draftv2/</code>. Assign classes to a
          league here, on the Draft classes tab, or from the class menu.
        </p>

        @if (leagueStore.leagues().length === 0) {
          <p class="muted">No leagues yet.</p>
        }
        <div class="leagues">
          @for (l of leagueStore.leagues(); track l.id) {
            <div class="card league">
              <div class="league-head">
                <b>{{ l.name }}</b>
                <span class="spacer"></span>
                <button type="button" (click)="edit(l)" [disabled]="busy()">Edit</button>
                <button type="button" class="danger" (click)="remove(l)" [disabled]="busy()">
                  Delete
                </button>
              </div>
              <div class="muted small">
                {{ l.leagueUrl || 'no URL set' }}
                @if (l.defaultLid != null) { · lid {{ l.defaultLid }} }
              </div>
              <div class="chips">
                @for (c of l.classNames; track c) { <span class="chip">{{ c }}</span> }
                @if (l.classNames.length === 0) { <span class="muted small">no classes</span> }
              </div>
            </div>
          }
        </div>

        @if (draft(); as d) {
          <form class="card" (submit)="saveLeague($event)">
            <h3>{{ d.id ? 'Edit league' : 'New league' }}</h3>
            <label>
              Name
              <input name="lname" [(ngModel)]="d.name" required autocomplete="off" />
            </label>
            <label>
              League URL
              <input
                name="lurl"
                [(ngModel)]="d.leagueUrl"
                placeholder="https://statsplus.net/yfmlb/"
              />
              <small class="muted">
                A full URL (<code>https://statsplus.net/yfmlb/</code>,
                <code>https://atl-01.statsplus.net/wbf/</code>) or a bare slug
                (<code>yfmlb</code>).
              </small>
            </label>
            <label>
              Default league id — <code>lid</code>, only for associations with multiple drafts (optional)
              <input name="llid" type="number" [(ngModel)]="d.defaultLid" />
            </label>
            <fieldset>
              <legend>Classes in this league</legend>
              @if (classStore.classes().length === 0) {
                <small class="muted">No classes uploaded yet.</small>
              }
              @for (c of classStore.classes(); track c.name) {
                <label class="row">
                  <input
                    type="checkbox"
                    [checked]="d.classNames.has(c.name)"
                    (change)="toggleClass(d, c.name, $any($event.target).checked)"
                  />
                  {{ c.name }}
                </label>
              }
            </fieldset>

            @if (leagueMsg()) { <p [class.error]="leagueErr()">{{ leagueMsg() }}</p> }
            <div class="row">
              <button class="primary" type="submit" [disabled]="busy() || !d.name.trim()">
                {{ busy() ? 'Saving…' : 'Save league' }}
              </button>
              <button type="button" (click)="draft.set(null)" [disabled]="busy()">Cancel</button>
            </div>
          </form>
        } @else {
          <button type="button" (click)="startNew()">Add league</button>
        }
      </section>
    }

    @if (tab() === 'classes') {
      <section class="block">
        <h2>Draft classes</h2>
        <p class="muted">
          Pick which league each uploaded draft class belongs to. Unassigned
          classes don’t appear under any league and can’t use “Refresh drafted”.
        </p>

        @if (classStore.classes().length === 0) {
          <p class="muted">No draft classes uploaded yet.</p>
        } @else if (leagueStore.leagues().length === 0) {
          <p class="muted">Add a league first, then map classes to it.</p>
        } @else {
          @if (unmappedCount() === 0) {
            <p class="muted small">Every draft class is assigned to a league.</p>
          }
          <div class="maprows">
            @for (c of sortedClasses(); track c.name) {
              <div class="maprow" [class.unmapped]="!c.leagueId">
                <span class="cname">{{ c.name }}</span>
                <span class="muted small">{{ c.playerCount }} players</span>
                <span class="spacer"></span>
                <select
                  [value]="c.leagueId ?? ''"
                  [disabled]="assigning() === c.name"
                  (change)="mapClass(c.name, $any($event.target).value)"
                >
                  <option value="">— unassigned —</option>
                  @for (l of leagueStore.leagues(); track l.id) {
                    <option [value]="l.id">{{ l.name }}</option>
                  }
                </select>
              </div>
            }
          </div>
          @if (classMsg()) { <p [class.error]="classErr()">{{ classMsg() }}</p> }
        }
      </section>
    }

    @if (tab() === 'cookie') {
      <section class="block">
        <h2>Session cookie</h2>
        <form class="card" (submit)="save($event)">
          <small class="muted">
            StatsPlus has no API key. Log into your league in a browser, open
            DevTools → Application → Cookies → <code>https://statsplus.net</code>, and
            paste the two values below. They expire after a while — re-paste when
            “Refresh drafted” reports an auth error.
          </small>

          <label>
            sessionid {{ hasSessionid() ? '— stored; leave blank to keep it' : '' }}
            <input name="sessionid" [(ngModel)]="sessionid" placeholder="paste the sessionid value" />
          </label>
          <label>
            csrftoken {{ hasCsrftoken() ? '— stored; leave blank to keep it' : '' }}
            <input name="csrftoken" [(ngModel)]="csrftoken" placeholder="paste the csrftoken value" />
          </label>

          @if (message()) { <p [class.error]="isError()">{{ message() }}</p> }
          <button class="primary" type="submit" [disabled]="busy()">
            {{ busy() ? 'Saving…' : 'Save' }}
          </button>
        </form>
      </section>
    }
  `,
  styles: `
    .tabs {
      display: flex;
      gap: 4px;
      margin: 12px 0 20px;
      border-bottom: 1px solid var(--border);
    }
    .tabs button {
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      padding: 8px 14px;
      cursor: pointer;
      color: var(--muted, #666);
      font: inherit;
    }
    .tabs button.active {
      color: var(--text);
      border-bottom-color: var(--accent);
      font-weight: 600;
    }
    .badge {
      display: inline-block;
      margin-left: 6px;
      min-width: 18px;
      padding: 0 5px;
      border-radius: 9px;
      background: var(--accent);
      color: #fff;
      font-size: 11px;
      line-height: 18px;
      text-align: center;
    }
    .block { max-width: 620px; margin-bottom: 32px; }
    form { display: flex; flex-direction: column; gap: 14px; }
    label { display: flex; flex-direction: column; gap: 5px; }
    label.row { flex-direction: row; align-items: center; gap: 8px; }
    .row { display: flex; align-items: center; gap: 10px; }
    .spacer { flex: 1; }
    .small { font-size: 12px; }
    fieldset {
      display: flex;
      flex-direction: column;
      gap: 8px;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
    }
    legend { padding: 0 6px; font-weight: 600; }
    small { line-height: 1.4; }
    code { background: var(--bg-elev-2); padding: 1px 4px; border-radius: 4px; }
    .leagues { display: flex; flex-direction: column; gap: 10px; margin: 10px 0; }
    .league-head { display: flex; align-items: center; gap: 8px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .chip {
      background: var(--bg-elev-2);
      border-radius: 12px;
      padding: 2px 10px;
      font-size: 12px;
    }
    .maprows { display: flex; flex-direction: column; gap: 6px; margin: 10px 0; }
    .maprow {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    .maprow.unmapped { border-color: var(--accent); }
    .maprow .cname { font-weight: 600; }
  `,
})
export class SettingsPage implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly leagueStore = inject(LeagueStore);
  protected readonly classStore = inject(ClassStore);

  protected readonly tab = signal<SettingsTab>('leagues');

  protected sessionid = '';
  protected csrftoken = '';
  protected readonly hasSessionid = signal(false);
  protected readonly hasCsrftoken = signal(false);
  protected readonly busy = signal(false);
  protected readonly message = signal<string | null>(null);
  protected readonly isError = signal(false);

  protected readonly draft = signal<LeagueDraft | null>(null);
  protected readonly leagueMsg = signal<string | null>(null);
  protected readonly leagueErr = signal(false);

  protected readonly assigning = signal<string | null>(null);
  protected readonly classMsg = signal<string | null>(null);
  protected readonly classErr = signal(false);

  protected readonly unmappedCount = computed(
    () => this.classStore.classes().filter((c) => !c.leagueId).length,
  );

  /** Unmapped classes first, then alphabetical. */
  protected readonly sortedClasses = computed(() =>
    [...this.classStore.classes()].sort((a, b) => {
      const am = a.leagueId ? 1 : 0;
      const bm = b.leagueId ? 1 : 0;
      return am - bm || a.name.localeCompare(b.name);
    }),
  );

  async ngOnInit(): Promise<void> {
    void this.leagueStore.reload();
    void this.classStore.reload();
    try {
      const s = await this.api.settings();
      this.hasSessionid.set(s.hasSessionid);
      this.hasCsrftoken.set(s.hasCsrftoken);
    } catch (e) {
      this.isError.set(true);
      this.message.set((e as Error).message);
    }
  }

  // -------------------------------------------------------------- leagues
  protected startNew(): void {
    this.leagueMsg.set(null);
    this.draft.set(emptyDraft());
  }

  protected edit(l: League): void {
    this.leagueMsg.set(null);
    this.draft.set({
      id: l.id,
      name: l.name,
      leagueUrl: l.leagueUrl ?? '',
      defaultLid: l.defaultLid,
      classNames: new Set(l.classNames),
    });
  }

  protected toggleClass(d: LeagueDraft, name: string, on: boolean): void {
    if (on) d.classNames.add(name);
    else d.classNames.delete(name);
  }

  protected async saveLeague(ev: Event): Promise<void> {
    ev.preventDefault();
    const d = this.draft();
    if (!d || !d.name.trim()) return;
    this.busy.set(true);
    this.leagueMsg.set(null);
    this.leagueErr.set(false);
    const input = {
      name: d.name.trim(),
      leagueUrl: d.leagueUrl.trim(),
      defaultLid: d.defaultLid ? Number(d.defaultLid) : null,
      classNames: [...d.classNames],
    };
    try {
      if (d.id) await this.api.updateLeague({ id: d.id, ...input });
      else await this.api.createLeague(input);
      await Promise.all([this.leagueStore.reload(), this.classStore.reload()]);
      this.draft.set(null);
    } catch (e) {
      this.leagueErr.set(true);
      this.leagueMsg.set((e as Error).message);
    } finally {
      this.busy.set(false);
    }
  }

  protected async remove(l: League): Promise<void> {
    if (!confirm(`Delete league "${l.name}"? Its classes are kept but unassigned.`)) return;
    this.busy.set(true);
    this.leagueMsg.set(null);
    this.leagueErr.set(false);
    try {
      await this.api.deleteLeague(l.id);
      await Promise.all([this.leagueStore.reload(), this.classStore.reload()]);
      if (this.draft()?.id === l.id) this.draft.set(null);
    } catch (e) {
      this.leagueErr.set(true);
      this.leagueMsg.set((e as Error).message);
    } finally {
      this.busy.set(false);
    }
  }

  // -------------------------------------------------------------- class mapping
  protected async mapClass(name: string, leagueId: string): Promise<void> {
    this.assigning.set(name);
    this.classMsg.set(null);
    this.classErr.set(false);
    try {
      await this.api.setClassLeague(name, leagueId || null);
      await Promise.all([this.classStore.reload(), this.leagueStore.reload()]);
    } catch (e) {
      this.classErr.set(true);
      this.classMsg.set((e as Error).message);
    } finally {
      this.assigning.set(null);
    }
  }

  // -------------------------------------------------------------- cookies
  async save(ev: Event): Promise<void> {
    ev.preventDefault();
    this.busy.set(true);
    this.message.set(null);
    this.isError.set(false);
    try {
      const s = await this.api.updateSettings({
        sessionid: this.sessionid.trim() || undefined,
        csrftoken: this.csrftoken.trim() || undefined,
      });
      this.hasSessionid.set(s.hasSessionid);
      this.hasCsrftoken.set(s.hasCsrftoken);
      this.sessionid = '';
      this.csrftoken = '';
      this.message.set('Saved.');
    } catch (e) {
      this.isError.set(true);
      this.message.set((e as Error).message);
    } finally {
      this.busy.set(false);
    }
  }
}
