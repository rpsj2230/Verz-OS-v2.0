/**
 * The page cases for `/signed-out`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { SIGNED_OUT_PATH } from "../../../src/auth/constants";
import type { PageCase } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  [SIGNED_OUT_PATH]: { address: SIGNED_OUT_PATH, signedIn: false, drawsValues: false, answers: {} },
};
