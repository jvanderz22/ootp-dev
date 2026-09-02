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

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly _header = signal<string | null>(read());
  readonly authorized = this._header.asReadonly();

  header(): string | null {
    return this._header();
  }

  login(username: string, password: string): void {
    const token = 'Basic ' + btoa(`${username}:${password}`);
    sessionStorage.setItem(STORAGE_KEY, token);
    this._header.set(token);
  }

  logout(): void {
    sessionStorage.removeItem(STORAGE_KEY);
    this._header.set(null);
  }
}

function read(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
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
