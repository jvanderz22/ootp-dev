/**
 * Round-trips the ranked-table's `RankedQuery` through the `/class/:name` URL
 * query string so a filtered / sorted view survives a reload and can be
 * shared. Only non-default state is written; everything else is omitted to keep
 * the URL short. The table loads infinitely (see `RANKED_PAGE_SIZE`), so scroll
 * depth isn't part of this state — a reload always starts from the first batch.
 *
 * Params:
 *   view      modeled | batting | pitching   (omitted when modeled)
 *   q         search text
 *   pos       comma-separated positions
 *   bats      comma-separated batting hands (Right | Left | Switch)
 *   throws    comma-separated throwing hands (Right | Left | Switch)
 *   team      comma-separated drafting teams
 *   undrafted 1  — "hide drafted" is on
 *   sort      field, `-` prefix for descending (omitted at the view default)
 *   f         numeric filters: `field~min~max`, comma-separated, blank side = open
 */
import { Params } from '@angular/router';

import { ClassView, NumericFilter, RankedQuery } from './api.types';
import { DEFAULT_SORT, FILTERABLE_FIELDS } from './ranked-columns';

const VIEWS: ClassView[] = ['modeled', 'batting', 'pitching'];

export function queryToParams(q: RankedQuery): Params {
  const p: Params = {};
  if (q.view !== 'modeled') p['view'] = q.view;
  if (q.search.trim()) p['q'] = q.search.trim();
  if (q.positions.length) p['pos'] = q.positions.join(',');
  if (q.batHands.length) p['bats'] = q.batHands.join(',');
  if (q.throwHands.length) p['throws'] = q.throwHands.join(',');
  if (q.teams.length) p['team'] = q.teams.join(',');
  if (q.hideDrafted) p['undrafted'] = '1';

  const dflt = DEFAULT_SORT[q.view];
  if (q.sortField && !(q.sortField === dflt.field && q.sortOrder === dflt.order)) {
    p['sort'] = (q.sortOrder === -1 ? '-' : '') + q.sortField;
  }

  const f = q.numericFilters.filter((x) => x.field && (x.min != null || x.max != null));
  if (f.length) {
    p['f'] = f.map((x) => `${x.field}~${x.min ?? ''}~${x.max ?? ''}`).join(',');
  }
  return p;
}

/** ParamMap-like: just the `get` we need, so callers can pass a snapshot map. */
interface Readable {
  get(key: string): string | null;
}

export function paramsToQuery(pm: Readable): RankedQuery {
  const raw = pm.get('view') as ClassView | null;
  const view: ClassView = raw && VIEWS.includes(raw) ? raw : 'modeled';
  const dflt = DEFAULT_SORT[view];

  let sortField: string | null = dflt.field;
  let sortOrder: 1 | -1 = dflt.order;
  const s = pm.get('sort');
  if (s) {
    sortOrder = s.startsWith('-') ? -1 : 1;
    sortField = s.replace(/^-/, '');
  }

  const numericFilters = (pm.get('f') ?? '')
    .split(',')
    .filter(Boolean)
    .map((tok): NumericFilter => {
      const [field, min, max] = tok.split('~');
      const meta = FILTERABLE_FIELDS.find((x) => x.field === field);
      return {
        field,
        label: meta?.label ?? field,
        min: min ? Number(min) : null,
        max: max ? Number(max) : null,
      };
    })
    .filter((x) => x.field && (x.min != null || x.max != null));

  return {
    view,
    search: pm.get('q') ?? '',
    positions: (pm.get('pos') ?? '').split(',').filter(Boolean),
    batHands: (pm.get('bats') ?? '').split(',').filter(Boolean),
    throwHands: (pm.get('throws') ?? '').split(',').filter(Boolean),
    teams: (pm.get('team') ?? '').split(',').filter(Boolean),
    hideDrafted: pm.get('undrafted') === '1',
    numericFilters,
    sortField,
    sortOrder,
  };
}
