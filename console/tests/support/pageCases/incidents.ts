/**
 * The page cases for `/incidents`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const INCIDENTS = {
  items: [
    {
      subject: UNBROKEN,
      state: "down",
      since: "2019-03-04T09:00:00Z",
      blocks: [UNBROKEN],
      blocks_unknown: "",
    },
  ],
  unread: "",
  told: UNBROKEN,
};

const SYSTEM_HEALTH = {
  as_of: "2019-03-04T09:00:00Z",
  status: "ok",
  parts: [{ name: "database", state: "ready", gates: true, said: UNBROKEN }],
  worker: { state: "ready", last_seen: "2019-03-04T08:59:00Z", said: UNBROKEN },
  vault: { name: "vault", state: "not_configured", gates: false, said: UNBROKEN },
  object_store: { name: "object_store", state: "unknown", gates: false, said: UNBROKEN },
  breakers: null,
  breakers_said: UNBROKEN,
  guarantees: [
    { control: "retention_sweep", guards: UNBROKEN, held: false, because: "behind", said: UNBROKEN },
  ],
  guarantees_said: "",
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Incidents. The list of degraded sources scrolls; what each blocks and the sentence wrap.
  "/incidents": {
    address: "/incidents",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/console/incidents": INCIDENTS, "/api/v1/console/system-health": SYSTEM_HEALTH },
  },
};
