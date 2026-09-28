/**
 * The page cases for `/first-run` and `/first-run/staff-list`: the address each is mounted at and
 * what the stand-in API answers it with. `support/pageCases.ts` collects this file by its name and
 * says what a case is for.
 *
 * Task ids: none
 */

import { RETURN_PATH as STAFF_LIST_RETURN_PATH } from "../../../src/setup/staffList";
import { FIRST_RUN_PATH } from "../../../src/setup/wizard";
import type { PageCase } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  [FIRST_RUN_PATH]: { address: FIRST_RUN_PATH, signedIn: false, drawsValues: false, answers: {} },
  [STAFF_LIST_RETURN_PATH]: {
    address: `${STAFF_LIST_RETURN_PATH}?code=X&state=Y`,
    signedIn: false,
    drawsValues: false,
    answers: {},
  },
};
