/**
 * The page cases for `/features`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/features": {
    address: "/features",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/features": {
        features: [
          {
            name: "schedule_control",
            title: UNBROKEN,
            what: UNBROKEN,
            while_off: UNBROKEN,
            on: true,
            read_by: [UNBROKEN],
            changed_by: UNBROKEN,
            changed_at: "2019-03-04T09:00:00Z",
          },
        ],
        components_are_chosen_by_the_profile: true,
        plugins_have_no_loader: true,
        every_change_is_in_the_audit_trail: true,
      },
      "/api/v1/migration": {
        inventory: { saved: null, document: null, agreed: false, gaps: [] },
        parallel: {
          saved: null,
          document: null,
          may_cut_over: false,
          gaps: [],
          disagreements: [],
          unreviewed: [],
          only_one_answered: [],
        },
        cutover: {
          saved: null,
          document: null,
          gaps: [],
          acts_outstanding: [],
          may_report_complete: false,
          reported_complete: null,
        },
        workspace_is_on: true,
        nothing_reaches_the_old_system: true,
      },
      "/api/v1/orchestration/rehearsals": {
        decisions: [
          {
            run_id: "rehearsal-1",
            decided_at: "2019-03-04T09:00:00Z",
            decided_by: "u_admin",
            branches: 4,
            depth: 0,
            cost_multiplier: 1,
            speedup: 4,
            largest_share: 0.25,
            evaluated: ["enough_branches"],
            failed: [],
            verdict: "parallel",
          },
        ],
        rehearsal_is_on: true,
        weights_note: UNBROKEN,
      },
      "/api/v1/install/plugins": {
        points: [
          {
            name: "connector",
            leaf: "M29.1.2",
            answer: "plugin",
            tier: "sidecar",
            direction: "produces",
            carries: "code",
            contract: UNBROKEN,
            why: UNBROKEN,
          },
        ],
        plugins: [
          {
            plugin_id: "stand-in",
            version: "1.0.0",
            point: "connector",
            state: "installed",
            since: "2019-03-04T09:00:00Z",
            history: ["1.0.0"],
            requires: [],
            config: [],
            core_min: "0.1.0",
            core_max: "9.0.0",
          },
        ],
        registry_is_on: true,
        no_plugin_is_loaded: true,
        core_version: "0.1.0",
      },
    },
  },
};
