import { Injectable, signal } from '@angular/core';

/** The ranking engines the server keeps runs for (see ranking_engine.py). */
export const RANKING_ENGINES = ['v2', 'legacy'] as const;
export type RankingEngine = (typeof RANKING_ENGINES)[number];
export const DEFAULT_ENGINE: RankingEngine = 'v2';

/** Every GraphQL request and download names the engine in this header. */
export const ENGINE_HEADER = 'X-Ranking-Engine';

const STORAGE_KEY = 'ootp-ranking-engine';

/** Which ranking engine the app shows - the top-bar toggle. Remembered per
 *  browser, so legacy and v2 can be compared side by side in two tabs. */
@Injectable({ providedIn: 'root' })
export class EngineService {
  private readonly _engine = signal<RankingEngine>(read());
  readonly engine = this._engine.asReadonly();

  /** Switch engines. Every page holds rows from the engine it loaded with, so
   *  the page reloads (its table state lives in the URL). */
  set(engine: RankingEngine): void {
    if (engine === this._engine()) return;
    try {
      localStorage.setItem(STORAGE_KEY, engine);
    } catch {
      // storage blocked: the switch still applies to this page load
    }
    this._engine.set(engine);
    location.reload();
  }
}

function read(): RankingEngine {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return (RANKING_ENGINES as readonly string[]).includes(stored ?? '')
      ? (stored as RankingEngine)
      : DEFAULT_ENGINE;
  } catch {
    return DEFAULT_ENGINE;
  }
}
