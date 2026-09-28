/**
 * The Settings screen on the page kit: every group drawn with its values and where each came from,
 * a value saved and returned to its default through a confirmation, the stored answer redrawn, and a
 * refusal shown as the API's own sentence. Identifiers stay in the Advanced section.
 *
 * The shapes are read from `brain.settings_routes` itself, so a renamed field fails here.
 *
 * Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1, M27.12.7, M27.16.1
 */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  BY_WORDS,
  FORMATS,
  KEEP_SAVED,
  KEEP_SETTING,
  LEAVING_HEADING,
  NOT_SET_YET,
  RETURN_TO_DEFAULT,
  RETURNED,
  SAVE,
  SAVE_CHANGE,
  SAVED,
  SETTINGS_API_PATH,
  SETTINGS_PATH,
  SOURCE_WORDS,
  UNREADABLE_SETTINGS,
} from "../src/pages/settingsQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { button, json, mountPage, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const READ = `GET /api/v1${SETTINGS_API_PATH}`;
const SAVE_NAME = `PUT /api/v1${SETTINGS_API_PATH}/INSTALL_COMPANY_NAME`;
const DEFAULT_NAME = `POST /api/v1${SETTINGS_API_PATH}/INSTALL_COMPANY_NAME/default`;
const ROUTES = "src/brain/settings_routes.py";

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "INSTALL_COMPANY_NAME",
    label: "Company name",
    meaning: "MEANING-SENTENCE",
    value: "Northwind Trading",
    source: "saved",
    default: "Your Company",
    required: false,
    editable: true,
    read_only_because: "",
    applies: "APPLIES-SENTENCE",
    read_by: ["brain.console_static"],
    without_saved: "Your Company",
    without_saved_source: "default",
    ...overrides,
  };
}

function page(company: string = "Northwind Trading", source: string = "saved"): Record<string, unknown> {
  return {
    groups: [
      {
        group: "company",
        title: "Company and branding",
        editable: true,
        settings: [row({ value: company, source })],
      },
      {
        group: "locale",
        title: "Language, money and time",
        editable: true,
        settings: [
          row({ name: "INSTALL_CURRENCY", label: "Currency", value: "XXX", source: "default", default: "XXX" }),
        ],
      },
      {
        group: "sign_in",
        title: "Sign-in",
        editable: false,
        settings: [
          row({
            name: "INSTALL_OIDC_ISSUER",
            label: "Sign-in address",
            value: "",
            source: "missing",
            default: "",
            required: true,
            editable: false,
            read_only_because: "READ-ONLY-SENTENCE",
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

/** Everything drawn outside the Advanced section, where no identifier may appear. */
function outsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

async function confirmIn(name: string): Promise<void> {
  const dialog = await screen.findByRole("alertdialog");
  fireEvent.click(within(dialog).getByRole("button", { name }));
}

describe("what the Settings screen draws", () => {
  test("each value with where it came from, a missing identity value said as not set, and identifiers only in Advanced", async () => {
    // What breaks if this is deleted: a value drawn with no word about whether anybody chose it,
    // a required issuer nobody set drawn as an empty field, or variable names back in page text.
    const { container } = await settingsPage({ [READ]: () => json(page()) });

    const text = outsideAdvanced(container);
    expect(text).toContain(SOURCE_WORDS.missing);
    expect(text).toContain(SOURCE_WORDS.saved);
    expect(text).toContain("READ-ONLY-SENTENCE");
    expect(text).toContain("Sign-in address");
    expect(text).toContain("FINDING-SENTENCE");
    expect(text).toContain("AGENTS-SENTENCE");
    expect(text).not.toContain("INSTALL_OIDC_ISSUER");
    expect(text).not.toContain("brain.console_static");
    expect(text).not.toContain("super_admin");
    const advanced = container.querySelector('[data-slot="advanced"]')?.textContent ?? "";
    expect(advanced).toContain("INSTALL_OIDC_ISSUER");
    expect(advanced).toContain("brain.console_static");
    expect((container.querySelector('input[name="INSTALL_COMPANY_NAME"]') as HTMLInputElement).value).toBe(
      "Northwind Trading",
    );
    expect(container.querySelector('input[name="INSTALL_OIDC_ISSUER"]')).toBeNull();
  });

  test("every field says what it accepts before anything is sent", async () => {
    // What breaks if this is deleted: a person learns the format only from a refusal.
    const { container } = await settingsPage({ [READ]: () => json(page()) });

    const input = container.querySelector('input[name="INSTALL_CURRENCY"]') as HTMLInputElement;
    const hint = document.getElementById(input.getAttribute("aria-describedby") ?? "");
    expect(hint?.textContent).toBe(FORMATS.INSTALL_CURRENCY);
  });

  test("the handover of this install: every step, who removes it and the backup days, with no control", async () => {
    // What breaks if this is deleted: the leaving card drops a step, hides who has to remove a part
    // by hand, or grows a button, and an owner reads a procedure that is not the one that runs.
    const { container } = await settingsPage({ [READ]: () => json(page()) });

    const card = [...container.querySelectorAll('[data-slot="section-card"]')].find((one) =>
      (one.textContent ?? "").includes(LEAVING_HEADING),
    ) as HTMLElement;
    const text = card.textContent ?? "";
    expect(text).toContain("LEAVING-SENTENCE");
    expect(text).toContain("identity_realm");
    expect(text).toContain("HOLDS-SENTENCE");
    expect(text).toContain(BY_WORDS.command);
    expect(text).toContain(BY_WORDS.operator);
    expect(text).toContain("35 days");
    expect(card.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(card.querySelector("button")).toBeNull();
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain(
      "python -m brain.ops.handover_run certify <dir>",
    );
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
  test("sends what was typed from its confirmation and draws what the API stored", async () => {
    // What breaks if this is deleted: a save that sends the old value or skips the confirmation,
    // or a page that goes on drawing what was typed rather than what the database holds.
    const { container, sent } = await settingsPage({
      [READ]: () => json(page()),
      [SAVE_NAME]: (body) => json(page(`${(body as { value: string }).value} Ltd`)),
    });

    const input = container.querySelector('input[name="INSTALL_COMPANY_NAME"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Contoso" } });
    fireEvent.click(button(container, `${SAVE}: Company name`));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain('Company name becomes "Contoso".');
    expect(sent.filter((one) => one.method === "PUT")).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: KEEP_SETTING }));
    expect(sent.filter((one) => one.method === "PUT")).toEqual([]);
    fireEvent.click(button(container, `${SAVE}: Company name`));
    await confirmIn(SAVE_CHANGE);

    await waitFor(() => {
      expect(container.textContent).toContain(SAVED);
    });
    expect(sent.filter((one) => one.method === "PUT").map((one) => one.body)).toEqual([{ value: "Contoso" }]);
    expect((container.querySelector('input[name="INSTALL_COMPANY_NAME"]') as HTMLInputElement).value).toBe(
      "Contoso Ltd",
    );
  });
});

describe("returning a value to its default", () => {
  test("is offered only where a value is saved, names what it returns to, and sends nothing until confirmed", async () => {
    // What breaks if this is deleted: the only way back to the default is typing it, which saves a
    // row that outranks the environment file for ever; or the act fires from one press.
    const { container, sent } = await settingsPage({
      [READ]: () => json(page()),
      [DEFAULT_NAME]: () => json(page("Your Company", "default")),
    });

    const offered = [...container.querySelectorAll("button")].filter((one) =>
      (one.getAttribute("aria-label") ?? "").startsWith(RETURN_TO_DEFAULT),
    );
    expect(offered.map((one) => one.getAttribute("aria-label"))).toEqual([`${RETURN_TO_DEFAULT}: Company name`]);
    fireEvent.click(offered[0] as HTMLButtonElement);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain('reads "Your Company" from the product default');
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: KEEP_SAVED }));
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);

    fireEvent.click(button(container, `${RETURN_TO_DEFAULT}: Company name`));
    await confirmIn(RETURN_TO_DEFAULT);
    await waitFor(() => {
      expect(container.textContent).toContain(RETURNED);
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([
      `/api/v1${SETTINGS_API_PATH}/INSTALL_COMPANY_NAME/default`,
    ]);
    expect(container.querySelector(`button[aria-label="${RETURN_TO_DEFAULT}: Company name"]`)).toBeNull();
  });
});

describe("the currency and time zone", () => {
  test("a currency nobody chose is never drawn as its code: the field starts empty, and it is saved from its confirmation", async () => {
    // What breaks if this is deleted: the owner reads XXX on the screen where he is meant to set
    // the currency, which is the code he took for a fault on the Models screen.
    const SAVE_CURRENCY = `PUT /api/v1${SETTINGS_API_PATH}/INSTALL_CURRENCY`;
    const { container, sent } = await settingsPage({
      [READ]: () => json(page()),
      [SAVE_CURRENCY]: () => json(page()),
    });

    expect(container.textContent).not.toContain("XXX");
    const input = container.querySelector('input[name="INSTALL_CURRENCY"]') as HTMLInputElement;
    expect(input.value).toBe("");
    fireEvent.change(input, { target: { value: "sgd" } });
    fireEvent.click(button(container, `${SAVE}: Currency`));
    await confirmIn(SAVE_CHANGE);
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "PUT").map((one) => one.body)).toEqual([{ value: "sgd" }]);
    });
    expect(NOT_SET_YET).not.toContain("XXX");
  });
});
