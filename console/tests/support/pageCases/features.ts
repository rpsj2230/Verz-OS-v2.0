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
      "/api/v1/install/browser": {
        targets: [
          {
            name: "books",
            origins: ["https://books.example"],
            api_tools: [],
            surfaces: [],
            bindings: [],
            declared_by: UNBROKEN,
            declared_at: "2019-03-04T09:00:00Z",
          },
        ],
        unreadable: [],
        grants: [],
        declarations_are_on: true,
        most_days: 90,
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
      "/api/v1/orchestration/weighed-plans": {
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
      // The requests split between agents, and the stored workflows and the runs kept: every value a
      // token with nowhere to break.
      "/api/v1/orchestration/coordinated-runs": {
        runs: [
          {
            run_id: UNBROKEN,
            coordinator_id: UNBROKEN,
            started_at: "2019-03-04T09:00:00Z",
            asked_by: UNBROKEN,
            mode: "sequential",
            why: ["gate_declined"],
            children: [
              { subtask_id: UNBROKEN, callee_id: UNBROKEN, depth: 1, reach_hash: "a".repeat(32), status: "delivered", cost_minor: 100, seconds: 1.5 },
            ],
            complete: true,
            total_minor: 100,
            currency: "XXX",
          },
        ],
        switched_on: true,
      },
      "/api/v1/workflows": {
        workflows: [{ workflow_id: UNBROKEN, version: 1, name: UNBROKEN }],
        switched_on: true,
      },
      "/api/v1/workflow-runs": {
        runs: [
          {
            run_id: UNBROKEN,
            workflow_id: UNBROKEN,
            version: 1,
            agent_id: UNBROKEN,
            outcome: "failure",
            failed_step: UNBROKEN,
            steps: [{ step_id: UNBROKEN, status: "failed", cause: "refused", detail: UNBROKEN, attempts: 1, seconds: 0.5 }],
            candidates_opened: [],
            run_by: UNBROKEN,
            started_at: "2019-03-04T09:00:00Z",
          },
        ],
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
