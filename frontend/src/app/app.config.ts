import {
  ApplicationConfig,
  inject,
  provideBrowserGlobalErrorListeners,
  provideEnvironmentInitializer,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { providePrimeNG } from 'primeng/config';
import Aura from '@primeuix/themes/aura';
import { provideApollo } from 'apollo-angular';
import { HttpLink } from 'apollo-angular/http';
import { ApolloLink, InMemoryCache } from '@apollo/client';
import { setContext } from '@apollo/client/link/context';
import extractFiles from 'extract-files/extractFiles.mjs';
import isExtractableFile from 'extract-files/isExtractableFile.mjs';

import { routes } from './app.routes';
import { authInterceptor, AuthService } from './core/auth';
import { KeepaliveService } from './core/keepalive';
import { PRIMENG_LICENSE_KEY } from './core/primeng-license';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    providePrimeNG({
      license: PRIMENG_LICENSE_KEY,
      theme: {
        preset: Aura,
        options: {
          darkModeSelector: 'system',
          cssLayer: { name: 'primeng', order: 'theme, base, primeng' },
        },
      },
    }),
    provideHttpClient(withInterceptors([authInterceptor])),
    // Eagerly start the backend keep-alive pinger.
    provideEnvironmentInitializer(() => inject(KeepaliveService)),
    provideApollo(() => {
      const httpLink = inject(HttpLink);
      const auth = inject(AuthService);
      const authLink = setContext(() => {
        const token = auth.header();
        return token ? { headers: { Authorization: token } } : {};
      });
      return {
        cache: new InMemoryCache({
          typePolicies: {
            // One paginated slice at a time per class; network-only refetches
            // always overwrite, so collapse the per-args cache entries.
            Query: { fields: { rankedPlayers: { keyArgs: ['name'], merge: true } } },
          },
        }),
        link: ApolloLink.from([
          authLink,
          httpLink.create({
            uri: '/graphql/',
            extractFiles: (body) => extractFiles(body, isExtractableFile),
          }),
        ]),
        defaultOptions: {
          watchQuery: { fetchPolicy: 'network-only' },
          query: { fetchPolicy: 'network-only' },
        },
      };
    }),
  ],
};
