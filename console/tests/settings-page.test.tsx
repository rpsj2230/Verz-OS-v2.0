/**
 * The Settings screen: every group drawn with its values and where each came from, branding saved
 * and the stored answer redrawn, and a refusal shown as the API's own sentence.
 *
 * The shapes are read from `brain.settings_routes` itself, so a renamed field fails here.
 *
 * Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  BY_WORDS,
  LEAVING_HEADING,
  SAVE,
  SAVED,
  SETTINGS_API_PATH,
  SETTINGS_PATH,
  SOURCE_WORDS,
  UNREADABLE_SETTINGS,
} from "../src/pages/settingsQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { button, json, mountPage, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";

const READ = `GET /api/v1${SETTINGS_API_PATH}`;
const SAVE_NAME = `PUT /api/v1${SETTINGS_API_PATH}/INSTALL_COMPANY_NAME`;
const ROUTES = "src/brain/settings_routes.py";

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "INSTALL_COMPANY_NAME",
    meaning: "MEANING-SENTENCE",
    value: "Northwind Trading",
    source: "saved",
    default: "Your Company",
    required: false,
    editable: true,
    applies: "APPLIES-SENTENCE",
    read_by: ["brain.console_static"],
    ...overrides,
  };
}

function page(company: string = "Northwind Trading"): Record<string, unknown> {
  return {
    groups: [
      {
        group: "branding",
        title: "Branding",
        editable: true,
        changed_elsewhere: "",
        settings: [row({ value: company })],
      },
      {
        group: "identity",
        title: "Identity provider",
        editable: false,
        changed_elsewhere: "ELSEWHERE-SENTENCE",
        settings: [
          row({
            name: "INSTALL_OIDC_ISSUER",
            value: "",
            source: "missing",
            default: "",
            required: true,
            editable: false,
          }),
        ],
      },
    ],
    findings: ["FINDING-SENTENCE"],
    profile: "PROFILE-SENTENCE",
    starter: {
      roles: ["super_admin", "member"],
      packs: ["starter"],
      scopes: ["company"],
      furnished: true,
      agent_templates: ["maintenance"],
      agents_installed: false,
      agents_told: "AGENTS-SENTENCE",
    },
    credentials: "CREDENTIALS-SENTENCE",
    editable_because: "EDITABLE-SENTENCE",
    leaving: {
      told: "LEAVING-SENTENCE",
      steps: [leavingStep(), leavingStep({ what: "identity_realm", kind: "part", holds: "", by: "operator" })],
      backup_retention_days: 35,
      procedure: "docs/install/handover.md",
      commands: ["python -m brain.ops.handover_run certify <dir>"],
    },
  };
}

function leavingStep(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { what: "audit", kind: "store", holds: "HOLDS-SENTENCE", by: "command", how: "HOW-SENTENCE", ...overrides };
}

async function settingsPage(answers: Record<string, Answer>) {
  return mountPage(
    SETTINGS_PATH,
    async () => {
      const { Settings } = await import("../src/pages/Settings");
      return <Settings />;
    },
    answers,
  );
}

describe("what the Settings screen draws", () => {
  test("each value with where it came from, a missing identity value said as not set, and the starter set", async () => {
    // What breaks if this is deleted: a value drawn with no word about whether anybody chose it,
    // and a required issuer nobody set drawn as an empty field, which reads as configured.
    const { container } = await settingsPage({ [READ]: () => json(page()) });

    const text = container.textContent ?? "";
    expect(text).toContain("INSTALL_OIDC_ISSUER");
    expect(text).toContain(SOURCE_WORDS.missing);
    expect(text).toContain(SOURCE_WORDS.saved);
    expect(text).toContain("ELSEWHERE-SENTENCE");
    expect(text).toContain("FINDING-SENTENCE");
    expect(text).toContain("AGENTS-SENTENCE");
    expect(text).toContain("CREDENTIALS-SENTENCE");
    expect(text).toContain("brain.console_static");
    expect((container.querySelector('input[name="INSTALL_COMPANY_NAME"]') as HTMLInputElement).value).toBe(
      "Northwind Trading",
    );
    expect(container.querySelector('input[name="INSTALL_OIDC_ISSUER"]')).toBeNull();
  });

  test("the handover of this install: every step, who removes it, the backup days and the command", async () => {
    // What breaks if this is deleted: the leaving card drops a step, hides who has to remove a part
    // by hand, or grows a button, and an owner reads a procedure that is not the one that runs.
    const { container } = await settingsPage({ [READ]: () => json(page()) });

    const text = container.textContent ?? "";
    expect(text).toContain(LEAVING_HEADING);
    expect(text).toContain("LEAVING-SENTENCE");
    expect(text).toContain("identity_realm");
    expect(text).toContain("HOLDS-SENTENCE");
    expect(text).toContain(BY_WORDS.command);
    expect(text).toContain(BY_WORDS.operator);
    expect(text).toContain("35 days");
    expect(text).toContain("python -m brain.ops.handover_run certify <dir>");
    const card = container.querySelector('[aria-labelledby="settings-leaving"]') as HTMLElement;
    expect(card.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(card.querySelector("button")).toBeNull();
  });

  test("a refusal is the API's sentence with its reference, and an unreadable answer says so", async () => {
    // What breaks if this is deleted: a refused reader shown an empty screen, which reads as an
    // install with nothing configured rather than a request that was refused.
    const refused = await settingsPage({
      [READ]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    });
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.container.textContent).toContain("TRACE-SENTINEL");

    const unreadable = await settingsPage({ [READ]: () => json({ groups: "no" }) });
    expect(unreadable.container.textContent).toContain(UNREADABLE_SETTINGS);
  });

  test("the fields this console reads are the ones the API declares", () => {
    // What breaks if this is deleted: the API renames a field and the screen draws undefined.
    expect(backendModelFields(ROUTES, "SettingRowView")).toEqual(Object.keys(row()));
    expect(backendModelFields(ROUTES, "SettingsPage")).toEqual(Object.keys(page()));
    expect(backendModelFields(ROUTES, "LeavingView")).toEqual(Object.keys(page().leaving as object));
    expect(backendModelFields(ROUTES, "LeavingStepView")).toEqual(Object.keys(leavingStep()));
  });
});

describe("saving branding", () => {
  test("sends what was typed and draws what the API stored", async () => {
    // What breaks if this is deleted: a save that sends the old value, or a page that goes on
    // drawing what was typed rather than what the database holds.
    const { container, sent } = await settingsPage({
      [READ]: () => json(page()),
      [SAVE_NAME]: (body) => json(page(`${(body as { value: string }).value} Ltd`)),
    });

    const input = container.querySelector('input[name="INSTALL_COMPANY_NAME"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Contoso" } });
    fireEvent.click(button(container, SAVE));

    await waitFor(() => {
      expect(container.textContent).toContain(SAVED);
    });
    expect(sent.filter((one) => one.method === "PUT").map((one) => one.body)).toEqual([{ value: "Contoso" }]);
    expect((container.querySelector('input[name="INSTALL_COMPANY_NAME"]') as HTMLInputElement).value).toBe(
      "Contoso Ltd",
    );
  });
});
