/**
 * The page cases for `/automations`, `/automations/:automationId` and
 * `/automations/:automationId/:view`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** One automation on the Automations list, every drawn value the unbroken token. */
const AUTOMATION_ROW = {
  automation_id: "auto_one",
  name: `I ${UNBROKEN}`,
  agent_id: "quote_helper",
  agent_name: UNBROKEN,
  owner_name: UNBROKEN,
  schedule: UNBROKEN,
  state: "running",
  next_run_at: "2019-03-11T07:00:00Z",
  last_run_at: "2019-03-04T07:00:00Z",
  last_outcome: "succeeded",
};

/** One automation's page with every change offered, so every control is drawn at a phone's width. */
const AUTOMATION_DETAIL = {
  automation: AUTOMATION_ROW,
  guards: UNBROKEN,
  stopped_because: UNBROKEN,
  cannot_run: UNBROKEN,
  cadence: { every: "week", hour_utc: 7, weekday: 0 },
  installed_by_name: UNBROKEN,
  installed_at: "2019-02-01T09:00:00Z",
  runs: [
    {
      finished_at: "2019-03-04T07:00:00Z",
      outcome: "succeeded",
      reason: UNBROKEN,
      ran_as_name: UNBROKEN,
      reach: "same",
      result: [UNBROKEN],
    },
  ],
  basis: "everyone",
  history: [{ at: "2019-02-01T09:00:00Z", what: UNBROKEN, by_name: UNBROKEN }],
  confirmation: "c".repeat(64),
  may_pause: true,
  may_resume: true,
  resume_becomes: "2019-03-11T07:00:00Z",
  may_reschedule: true,
  may_remove: true,
  may_adopt: true,
  schedule_accepts: UNBROKEN,
  weekdays: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
  confirm_pause: UNBROKEN,
  confirm_resume: UNBROKEN,
  confirm_reschedule: UNBROKEN,
  confirm_remove: UNBROKEN,
  confirm_adopt: UNBROKEN,
  task: UNBROKEN,
  template_id: UNBROKEN,
  owner_id: UNBROKEN,
};

/** One automation's figures as `brain.automations_routes.AutomationStatsView` sends them. */
const AUTOMATION_STATS = {
  automation_id: "auto_one",
  basis: "everyone",
  last_run_at: "2019-03-04T07:00:00Z",
  next_run_at: "2019-03-11T07:00:00Z",
  periods: ["7d", "30d"].map((range) => ({ range, runs: 12, succeeded: 10, failed: 1, refused: 1 })),
  unrecorded: [{ figure: "run_cost", why: UNBROKEN }],
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Automations, the list of every automation a reader may see, on the page kit.
  "/automations": {
    address: "/automations",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/automations": { items: [AUTOMATION_ROW], next_cursor: null },
    },
  },
  // One automation's Dashboard: the automation, with every change offered, and its figures.
  "/automations/:automationId": {
    address: "/automations/auto_one",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/automations/auto_one": AUTOMATION_DETAIL,
      "/api/v1/console/automations/auto_one/stats": AUTOMATION_STATS,
    },
  },
  // The Profile, the view with the most on it: the definition, the schedule, the reach at each run
  // and the Advanced section's identifiers.
  "/automations/:automationId/:view": {
    address: "/automations/auto_one/profile",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/automations/auto_one": AUTOMATION_DETAIL,
    },
  },
};
