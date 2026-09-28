/**
 * The page cases for `/models`, `/models/:provider` and `/models/:provider/:view`: the address each
 * is mounted at and what the stand-in API answers it with. `support/pageCases.ts` collects this
 * file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, PROVIDERS_ANSWER, UNBROKEN } from "../pageFixtures";

/** One provider's figures: what it answered, with failures and cost named as not recorded. */
const PROVIDER_STATS = {
  provider: UNBROKEN,
  days: 30,
  answered: 12,
  failures: null,
  cost_minor: null,
  unrecorded: [
    { figure: "failures", why: UNBROKEN },
    { figure: "model_cost", why: UNBROKEN },
  ],
};

/** A provider's history: one entry under its own subject, switched off by a person named by id. */
const PROVIDER_HISTORY = {
  items: [
    {
      at: "2019-03-04T09:00:00Z",
      action: "setting",
      actor_id: UNBROKEN,
      subject_kind: "setting",
      subject_id: `provider.${UNBROKEN}`,
      details: { change: "switched_off" },
    },
  ],
  next_cursor: null,
  order: "newest",
  actions: ["setting"],
  subject_kinds: ["setting"],
  actors: [UNBROKEN],
};

const MODELS_AND_HEALTH = {
  "/api/v1/models/providers": PROVIDERS_ANSWER,
  // One model priced and one not, so both the figures and the unpriced sentence are drawn.
  "/api/v1/models/prices": {
    currency: "SGD",
    models: [
      {
        provider: UNBROKEN,
        model: UNBROKEN,
        on_ladder: true,
        input_minor_per_million: "300",
        output_minor_per_million: "1500",
        currency: "SGD",
        costed: true,
      },
      {
        provider: "anthropic",
        model: UNBROKEN,
        on_ladder: false,
        input_minor_per_million: null,
        output_minor_per_million: null,
        currency: null,
        costed: false,
      },
    ],
  },
};

/** One provider's page: the providers answer narrowed by the route, its figures and its history. */
const PROVIDER_PAGE = {
  "/api/v1/models/providers": PROVIDERS_ANSWER,
  [`/api/v1/models/providers/${UNBROKEN}/stats`]: PROVIDER_STATS,
  "/api/v1/audit": PROVIDER_HISTORY,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/models": {
    address: "/models",
    signedIn: true,
    drawsValues: true,
    answers: MODELS_AND_HEALTH,
  },
  // One provider's Dashboard and its Profile, whose key and terms forms are drawn for this reader.
  "/models/:provider": {
    address: `/models/${UNBROKEN}`,
    signedIn: true,
    drawsValues: true,
    answers: PROVIDER_PAGE,
  },
  "/models/:provider/:view": {
    address: `/models/${UNBROKEN}/profile`,
    signedIn: true,
    drawsValues: true,
    answers: PROVIDER_PAGE,
  },
};
