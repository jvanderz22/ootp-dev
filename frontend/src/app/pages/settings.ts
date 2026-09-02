import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../core/api';

@Component({
  selector: 'app-settings',
  imports: [FormsModule],
  template: `
    <h1>StatsPlus settings</h1>
    <p class="muted">
      Used by “Refresh drafted”, which calls
      <code>&lt;league URL&gt;/api/draftv2/</code> to pull the picks made so far.
    </p>

    <form class="card" (submit)="save($event)">
      <label>
        League URL
        <input
          name="url"
          [(ngModel)]="leagueUrl"
          placeholder="https://statsplus.net/yfmlb/"
        />
        <small class="muted">
          Your league’s StatsPlus home page. A full URL
          (<code>https://statsplus.net/yfmlb/</code>,
          <code>https://atl-01.statsplus.net/wbf/</code>) or a bare slug
          (<code>yfmlb</code>) both work.
        </small>
      </label>

      <fieldset>
        <legend>Session cookie</legend>
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
      </fieldset>

      <label>
        Default league id — <code>lid</code>, only for associations with multiple drafts (optional)
        <input name="lid" type="number" [(ngModel)]="defaultLid" />
      </label>

      @if (message()) { <p [class.error]="isError()">{{ message() }}</p> }
      <button class="primary" type="submit" [disabled]="busy()">
        {{ busy() ? 'Saving…' : 'Save' }}
      </button>
    </form>
  `,
  styles: `
    form { display: flex; flex-direction: column; gap: 16px; max-width: 560px; }
    label { display: flex; flex-direction: column; gap: 5px; }
    fieldset {
      display: flex;
      flex-direction: column;
      gap: 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
    }
    legend { padding: 0 6px; font-weight: 600; }
    small { line-height: 1.4; }
    code { background: var(--bg-elev-2); padding: 1px 4px; border-radius: 4px; }
  `,
})
export class SettingsPage implements OnInit {
  private readonly api = inject(ApiService);

  protected leagueUrl = '';
  protected sessionid = '';
  protected csrftoken = '';
  protected defaultLid: number | null = null;
  protected readonly hasSessionid = signal(false);
  protected readonly hasCsrftoken = signal(false);
  protected readonly busy = signal(false);
  protected readonly message = signal<string | null>(null);
  protected readonly isError = signal(false);

  async ngOnInit(): Promise<void> {
    try {
      const s = await this.api.settings();
      this.leagueUrl = s.leagueUrl ?? '';
      this.defaultLid = s.defaultLid;
      this.hasSessionid.set(s.hasSessionid);
      this.hasCsrftoken.set(s.hasCsrftoken);
    } catch (e) {
      this.isError.set(true);
      this.message.set((e as Error).message);
    }
  }

  async save(ev: Event): Promise<void> {
    ev.preventDefault();
    this.busy.set(true);
    this.message.set(null);
    this.isError.set(false);
    try {
      const s = await this.api.updateSettings({
        leagueUrl: this.leagueUrl.trim(),
        sessionid: this.sessionid.trim() || undefined,
        csrftoken: this.csrftoken.trim() || undefined,
        defaultLid: this.defaultLid ? Number(this.defaultLid) : null,
      });
      this.leagueUrl = s.leagueUrl ?? '';
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
