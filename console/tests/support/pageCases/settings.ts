/**
 * The page cases for `/settings`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Installation settings and the leaving card. The branding value is drawn in a field, so the
  // unbroken value is the non-editable one and the handover step's sentence.
  "/settings": {
    address: "/settings",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/settings": {
        groups: [
          {
            group: "files",
            title: "Files and storage",
            editable: false,
            settings: [
              {
                name: "INSTALL_OBJECT_STORE_URL",
                label: UNBROKEN,
                meaning: UNBROKEN,
                value: UNBROKEN,
                source: "environment",
                default: "",
                required: false,
                editable: false,
                read_only_because: UNBROKEN,
                applies: UNBROKEN,
                read_by: ["brain.ops.object_store"],
                without_saved: UNBROKEN,
                without_saved_source: "environment",
              },
            ],
          },
        ],
        findings: [],
        profile: UNBROKEN,
        starter: {
          roles: ["member"],
          packs: ["starter"],
          scopes: ["company"],
          furnished: true,
          agent_templates: [],
          agents_installed: false,
          agents_told: UNBROKEN,
        },
        credentials: UNBROKEN,
        editable_because: UNBROKEN,
        leaving: {
          told: UNBROKEN,
          steps: [{ what: "audit", kind: "store", holds: UNBROKEN, by: "command", how: UNBROKEN }],
          backup_retention_days: 35,
          procedure: "docs/install/handover.md",
          commands: ["python -m brain.ops.handover_run certify <dir>"],
        },
      },
    },
  },
};
