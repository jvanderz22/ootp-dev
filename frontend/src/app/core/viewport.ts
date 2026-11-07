import { Injectable, signal } from '@angular/core';

/** Phone width. Matches the `max-width: 640px` media queries in the
 *  stylesheets, so script-driven and CSS-driven layout switch together. */
export const NARROW_VIEWPORT_QUERY = '(max-width: 640px)';

/** Whether the viewport is phone-width - for the layout switches CSS can't make
 *  on its own (a popover becoming a bottom sheet, an inline row expansion
 *  becoming a full-screen panel). */
@Injectable({ providedIn: 'root' })
export class Viewport {
  private readonly _narrow = signal(false);
  readonly narrow = this._narrow.asReadonly();

  constructor() {
    const mq = window.matchMedia(NARROW_VIEWPORT_QUERY);
    this._narrow.set(mq.matches);
    mq.addEventListener('change', (e) => this._narrow.set(e.matches));
  }
}
