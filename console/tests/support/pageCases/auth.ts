/**
 * The page cases for `/auth/callback`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { CALLBACK_PATH } from "../../../src/auth/constants";
import type { PageCase } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  [CALLBACK_PATH]: {
    address: `${CALLBACK_PATH}?code=X&state=Y`,
    signedIn: false,
    drawsValues: false,
    answers: {},
  },
};
