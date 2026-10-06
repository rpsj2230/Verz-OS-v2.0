/**
 * The page case for `/connector-consent`, where a vendor sends a person back after a consent:
 * mounted with no answer in its address, which is the one way it asks nothing. With an answer it
 * hands it over once, which `tests/connector-consent.test.tsx` holds. `support/pageCases.ts`
 * collects this file by its name and says what a case is for.
 *
 * Task ids: M11.8.6
 */

import type { PageCase } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/connector-consent": { address: "/connector-consent", signedIn: true, drawsValues: false, answers: {} },
};
