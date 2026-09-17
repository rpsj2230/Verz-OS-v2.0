/**
 * The Keycloak realm, read as the fact it is.
 *
 * `src/auth/constants.ts` says of itself: "where this file and that file disagree, that
 * file is the fact and this one is the bug". This module is how a test can say the same
 * thing. Everything here reads `ops/keycloak/realm-export.json`, which is outside the
 * console and is the artefact an administrator imports.
 */

import { readRepoFile } from "./repo";

export interface RealmClient {
  readonly clientId: string;
  readonly publicClient?: boolean;
  readonly standardFlowEnabled?: boolean;
  readonly implicitFlowEnabled?: boolean;
  readonly directAccessGrantsEnabled?: boolean;
  readonly redirectUris?: string[];
  readonly defaultClientScopes?: string[];
  readonly optionalClientScopes?: string[];
  readonly attributes?: Record<string, string>;
}

export interface Realm {
  readonly accessTokenLifespan?: number;
  readonly revokeRefreshToken?: boolean;
  readonly refreshTokenMaxReuse?: number;
  readonly clients?: RealmClient[];
  readonly clientScopes?: { name: string }[];
}

export function realm(): Realm {
  return JSON.parse(readRepoFile("ops/keycloak/realm-export.json")) as Realm;
}

/**
 * Keycloak's own self-service clients, which every realm has whether or not the file names them.
 *
 * Their ids are Keycloak's constants (`Constants.ACCOUNT_MANAGEMENT_CLIENT_ID` and
 * `ACCOUNT_CONSOLE_CLIENT_ID`), not choices of this product. The realm export declares them
 * because an import that declares client scopes gives the Account Console no roles mapper, so
 * it refused every person with 403 until the file carried one (measured on staging,
 * 2026-09-17). Both are public standard-flow clients by Keycloak's design, and counting them
 * as the console's would make every test below fail for a client the console never uses.
 * They are excluded by their fixed ids, and nothing else is: a third public client of the
 * product's own still makes `browserClient` refuse.
 */
export const KEYCLOAKS_OWN_ACCOUNT_CLIENTS: readonly string[] = ["account", "account-console"];

/**
 * The one browser client, found by what makes it one rather than by name.
 *
 * Looking it up by `brain-console` would mean the client id was compared with itself, and
 * the console's own constant is exactly what several tests are checking.
 */
export function browserClient(): RealmClient {
  const candidates = (realm().clients ?? []).filter(
    (client) =>
      client.publicClient === true &&
      client.standardFlowEnabled === true &&
      !KEYCLOAKS_OWN_ACCOUNT_CLIENTS.includes(client.clientId),
  );
  if (candidates.length !== 1) {
    throw new Error(
      `The realm has ${candidates.length} public standard-flow clients. This console is ` +
        "written for exactly one, so a second is a decision somebody has to make rather " +
        "than a test to loosen.",
    );
  }
  return candidates[0] as RealmClient;
}

/** Every client scope the realm defines. Anything else cannot be asked for. */
export function clientScopeNames(): string[] {
  return (realm().clientScopes ?? []).map((scope) => scope.name);
}

/** The path half of a registered URI. The origin comes from wherever this is served. */
export function pathOf(uri: string): string {
  return new URL(uri).pathname;
}
