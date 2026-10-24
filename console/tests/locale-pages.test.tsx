/**
 * The three pages a person reads most, drawn in the language the install served: that Chinese
 * appears where it is wired, that English is what every page and test sees when nothing is served,
 * and that the switch lists each language in its own words.
 *
 * Each page keeps its words in exported constants that its own tests import, so the evidence is
 * the constants after a language is served and the pages' own functions that build a sentence from
 * a blank, a date or a sum of money. Task ids: M35.1.1.1, M35.1.1.2
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { readConsoleFile } from "./support/repo";

interface Served {
  readonly locales: readonly { readonly tag: string; readonly messages: Record<string, string> }[];
}

const served = (JSON.parse(readConsoleFile("tests/fixtures/console-locale.json")) as { served: Served }).served;
const chinese = served.locales.find((one) => one.tag === "zh-Hans")?.messages ?? {};

function serve(tag: string, extra: Record<string, unknown> = {}): void {
  window.localStorage.setItem("brain.locale", tag);
  (globalThis as Record<string, unknown>).__BRAIN_CONFIG__ = { locale: { ...served, ...extra } };
}

beforeEach(() => {
  vi.resetModules();
  window.localStorage.clear();
});
afterEach(() => {
  delete (globalThis as Record<string, unknown>).__BRAIN_CONFIG__;
  window.localStorage.clear();
  document.documentElement.removeAttribute("lang");
  vi.resetModules();
});

describe("with Chinese chosen", () => {
  test("Approvals, My workspace and Ask draw the catalogue's Chinese for their words", async () => {
    // What breaks if this is deleted: the catalogue is served and no page looks words up in it, so
    // a person who chose Chinese is shown English under a Chinese switch.
    serve("zh-Hans");
    const approvals = await import("../src/pages/approvals/ApprovalsPage");
    const card = await import("../src/pages/approvals/ApprovalCard");
    const workspace = await import("../src/pages/MyWorkspace");
    const ask = await import("../src/pages/Ask");
    const start = await import("../src/pages/AskStart");

    expect(approvals.APPROVALS_HEADING).toBe(chinese["console.approvals.approvals_heading"]);
    expect(card.APPROVE_LABEL).toBe(chinese["console.approvals.approve_label"]);
    expect(card.TAKE_OVER_CONSEQUENCE).toBe(chinese["console.approvals.take_over_consequence"]);
    expect(workspace.WORKSPACE_HEADING).toBe(chinese["console.workspace.workspace_heading"]);
    expect(ask.ASK_HEADING).toBe(chinese["console.ask.ask_heading"]);
    expect(start.START_TASK).toBe(chinese["console.ask.start_task"]);
    for (const word of [approvals.APPROVALS_HEADING, card.APPROVE_LABEL, workspace.WORKSPACE_HEADING, ask.ASK_HEADING]) {
      expect(word).toMatch(/[一-鿿]/);
    }
  });

  test("a sum spent and a citation's date are written by the install's rules in Chinese", async () => {
    // What breaks if this is deleted: the sentence is translated and its figures are still written
    // as the browser's region writes them, in an order and with separators the install never chose.
    serve("zh-Hans", { currency: "SGD" });
    const { spentOf } = await import("../src/pages/myWorkspaceQuery");
    const { freshnessWords } = await import("../src/pages/askQuery");

    expect(
      spentOf({ period: "month", ceiling_minor: 400000, spent_minor: 179900, headroom_minor: 220100, alerts_crossed: [] }),
    ).toBe("已用 1,799.00 SGD，共 4,000.00 SGD，45%");
    expect(
      freshnessWords({
        kind: "document",
        freshnessText: "Current",
        readAt: "2026-09-08T06:30:00Z",
      } as Parameters<typeof freshnessWords>[0]),
    ).toBe("Current，更新于 2026年09月08日");
  });

  test("the language switch names each language in its own words and marks the one in use", async () => {
    // What breaks if this is deleted: a switch listing Chinese in English is readable only by
    // somebody who already found the language they wanted.
    serve("zh-Hans");
    const { LanguageChoice } = await import("../src/locale/LanguageChoice");

    render(<LanguageChoice />);

    expect(screen.getAllByRole("option").map((one) => one.textContent)).toEqual(["English", "简体中文"]);
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("zh-Hans");
    expect(screen.getByLabelText(chinese["console.shell.language_label"] ?? "")).toBeTruthy();
  });
});

describe("with nothing served", () => {
  test("the pages' constants are their English and the switch is not drawn", async () => {
    // What breaks if this is deleted: every page and every test that names a constant reads
    // different words the day the catalogue arrives, or a one-language install is offered a choice
    // of one.
    const card = await import("../src/pages/approvals/ApprovalCard");
    const { LanguageChoice } = await import("../src/locale/LanguageChoice");

    expect(card.APPROVE_LABEL).toBe("Approve");
    const { container } = render(<LanguageChoice />);
    expect(container.innerHTML).toBe("");
  });
});

describe("with English the only language served", () => {
  test("no switch is drawn", async () => {
    // What breaks if this is deleted: an install offering one language has a control that changes
    // nothing.
    serve("en", { locales: served.locales.slice(0, 1) });
    const { LanguageChoice } = await import("../src/locale/LanguageChoice");

    const { container } = render(<LanguageChoice />);

    expect(container.innerHTML).toBe("");
  });
});
