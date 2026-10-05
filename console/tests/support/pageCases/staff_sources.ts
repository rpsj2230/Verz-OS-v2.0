/**
 * The page cases for `/staff_sources`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { LARK_GUIDE, type PageCase, STAFF_RUNS, UNBROKEN } from "../pageFixtures";

/** One staff source whose setting names and whose meaning are both unbreakable tokens. */
const STAFF_SOURCES = {
  options: [
    {
      name: UNBROKEN,
      meaning: UNBROKEN,
      reads_a_list: true,
      needs: [UNBROKEN],
      unsupplied: [UNBROKEN],
      chosen: true,
    },
  ],
  // Ready, with no refusal, and that is the loop's constraint rather than the screen's: a
  // refusal is drawn in a `Notice`, `Notice` carries `role="status"`, and `mount` reads that as
  // a page still asking. The values this test is about are the identifier-shaped ones, which
  // are the name, the setting names and the meaning; a refusal is a sentence with spaces in it.
  // What a refusal draws is held in `tests/staff-sources-page.test.tsx`.
  selection: {
    name: UNBROKEN,
    meaning: UNBROKEN,
    reads_a_list: true,
    unsupplied: [UNBROKEN],
    refusal: "",
    ready: true,
  },
  how_to_choose: UNBROKEN,
};

/**
 * One guide for connecting a staff source, whose title, steps and help are unbreakable tokens.
 * The reader may connect; the form is in a drawer, which `tests/staff-sources-page.test.tsx` opens.
 */
const STAFF_SOURCE_GUIDES = {
  guides: [
    {
      source: "lark",
      title: UNBROKEN,
      where: UNBROKEN,
      steps: [UNBROKEN],
      fields: [
        { key: "location", label: "Platform", help: UNBROKEN, secret: false, example: "larksuite.com" },
        { key: "app_id", label: "App ID", help: UNBROKEN, secret: false, example: "cli_a" },
        { key: "app_secret", label: "App Secret", help: UNBROKEN, secret: true, example: "" },
      ],
      connectable: true,
      unavailable: "",
      chosen: true,
    },
  ],
  may_connect: true,
  schedule: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Staff sources. The unbreakable token is a setting name and a source's meaning, which are
  // the two values on this screen with nowhere to wrap: a setting name is an identifier and a
  // meaning is a paragraph the API wrote. The trial is not answered here, because it is asked
  // for by a button this loop does not press; what it draws once a plan arrives is held to the
  // same rules in `tests/staff-sources-page.test.tsx`.
  "/staff_sources": {
    address: "/staff_sources",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/staff_sources": STAFF_SOURCES,
      "/api/v1/govern/staff_sources/guides": STAFF_SOURCE_GUIDES,
      // The nightly sync's three reads, each carrying the unbroken token where a value is drawn.
      "/api/v1/govern/staff_sources/runs": STAFF_RUNS,
      // Sync now, for a reader who may press it, with no run waiting.
      "/api/v1/govern/staff_sources/sync": {
        may_sync: true,
        last_run_at: "2999-03-02T02:00:00Z",
        next_run_at: "2999-03-03T02:00:00Z",
        requested_at: null,
        waiting: false,
        told: "",
      },
      // Lark with its staff list on, so the page draws Lark's card with the runs above.
      "/api/v1/connectors/lark-app": LARK_GUIDE,
      "/api/v1/govern/staff_sources/credential": {
        slot: "connector_keys/staff_source",
        held: true,
        set_at: null,
        vault: "ready",
        told: "The secrets vault answered.",
        form: UNBROKEN,
      },
      "/api/v1/govern/staff_sources/transfers": {
        transfers: [{ agent_id: UNBROKEN, display_name: UNBROKEN, owner_id: UNBROKEN, running: false }],
      },
    },
  },
};
