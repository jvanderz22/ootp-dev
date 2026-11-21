import { Injectable, signal, inject } from '@angular/core';
import {
  HttpEvent,
  HttpHandlerFn,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { Router } from '@angular/router';
import { CanActivateFn } from '@angular/router';
import { Observable, tap } from 'rxjs';

const STORAGE_KEY = 'ootp-draft-auth';

/**
 * The Basic-auth header persists in localStorage so it survives new tabs and
 * browser restarts; a 401 from the server (wrong / changed password) clears it.
 * Sign-in and sign-out propagate to other open tabs via the storage event.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly router = inject(Router);
  private readonly _header = signal<string | null>(read());
  readonly authorized = this._header.asReadonly();

  constructor() {
    window.addEventListener('storage', (ev) => {
      if (ev.key !== STORAGE_KEY && ev.key !== null) return;
      const token = read();
      if (token === this._header()) return;
      this._header.set(token);
      if (!token) this.router.navigate(['/login']);
      else if (this.router.url.startsWith('/login')) this.router.navigate(['/']);
    });
  }

  header(): string | null {
    return this._header();
  }

  login(username: string, password: string): void {
    const token = 'Basic ' + btoa(`${username}:${password}`);
    write(token);
    this._header.set(token);
  }

  logout(): void {
    write(null);
    this._header.set(null);
  }
}

function read(): string | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return stored;
    // one-time carry-over from the old per-tab session storage
    const legacy = sessionStorage.getItem(STORAGE_KEY);
    if (legacy) {
      localStorage.setItem(STORAGE_KEY, legacy);
      sessionStorage.removeItem(STORAGE_KEY);
    }
    return legacy;
  } catch {
    return null;
  }
}

function write(token: string | null): void {
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token);
    else localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage blocked (private mode etc.): the in-memory signal still works for this tab
  }
}

export const authInterceptor: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
): Observable<HttpEvent<unknown>> => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const token = auth.header();
  const authReq = token ? req.clone({ setHeaders: { Authorization: token } }) : req;
  return next(authReq).pipe(
    tap({
      error: (err) => {
        if (err?.status === 401) {
          auth.logout();
          router.navigate(['/login']);
        }
      },
    }),
  );
};

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.header()) return true;
  router.navigate(['/login']);
  return false;
};
