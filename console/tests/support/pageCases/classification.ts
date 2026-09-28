/**
 * The page cases for `/classification`, `/classification/:entity` and
 * `/classification/:entity/:column`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const CLASSIFICATION = {
  entity: "price_list",
  columns: [
    {
      column: "cost",
      required_capability: "read:price_list.cost",
      classification: "confidential",
      derived_from: [UNBROKEN],
    },
  ],
  epoch: "EPOCH-SENTINEL",
  editable: true,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/classification": { address: "/classification", signedIn: true, drawsValues: false, answers: {} },
  "/classification/:entity": {
    address: "/classification/price_list",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/classifications/price_list": CLASSIFICATION },
  },
  "/classification/:entity/:column": {
    address: "/classification/price_list/cost",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/classifications/price_list": CLASSIFICATION },
  },
};
