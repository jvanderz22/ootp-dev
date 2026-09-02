import {
  ApplicationConfig,
  inject,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideApollo } from 'apollo-angular';
import { HttpLink } from 'apollo-angular/http';
import { ApolloLink, InMemoryCache } from '@apollo/client';
import { setContext } from '@apollo/client/link/context';
import extractFiles from 'extract-files/extractFiles.mjs';
import isExtractableFile from 'extract-files/isExtractableFile.mjs';

import { routes } from './app.routes';
import { authInterceptor, AuthService } from './core/auth';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideApollo(() => {
      const httpLink = inject(HttpLink);
      const auth = inject(AuthService);
      const authLink = setContext(() => {
        const token = auth.header();
        return token ? { headers: { Authorization: token } } : {};
      });
      return {
        cache: new InMemoryCache(),
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
