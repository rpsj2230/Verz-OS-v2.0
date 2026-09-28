/**
 * Tools on the shared page kit: the list of every tool with its status, and a tool's page with what
 * it needs and does, the switches this reader may throw and no others, and a confirmed switch
 * posted to the place it names and then re-read. Who switched a tool off stays in Advanced.
 *
 * Mounted on its own at each address. The shapes are read from `brain.tool_routes` itself, so a
 * renamed field fails here.
 *
 * Task ids: M12.1.3, M12.3.8, M12.4.3, M27.16.1
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  A_SWITCH_ONLY_NARROWS,
  EFFECT_SENTENCES,
  KEEP_IT,
  NO_LONGER_OFFERED,
  SENSITIVE_EFFECT_SENTENCES,
  SWITCH_OFF_FOR_THE_INSTALL,
  SWITCH_ON_FOR_THE_INSTALL,
  TOOLS_API_PATH,
  TOOLS_PATH,
  UNREADABLE_ANSWER,
} from "../src/pages/toolsQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { NO_SUCH_TOOL } from "../src/pages/tools/ToolDetailPage";
import { json, mountPage, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const LIST = `GET /api/v1${TOOLS_API_PATH}`;
const SWITCH = `POST /api/v1${TOOLS_API_PATH}/drive.delete_file/switch`;
const ROUTES = "src/brain/tool_routes.py";

function stop(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    department: null,
    switched_off_by: "u_switcher_sentinel",
    switched_off_at: "2019-03-04T09:00:00Z",
    reason: null,
    ...overrides,
  };
}

function tool(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "drive.delete_file",
    source: "drive",
    description: "DESCRIPTION-SENTENCE",
    entity: "file",
    capability: "write:file.body",
    effect: "irreversible",
    side_effect: "write",
    sensitive_effect: "deletion",
    result_contract: "typed",
    identity_mode: "delegated",
    leash_at_most: "assisted",
    registered: true,
    off_for_install: null,
    stopped_for: [],
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}, one: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    tools: [tool(one)],
    may_switch_install: true,
    departments: ["web"],
    reason_to_switch_on: 12,
    a_switch_only_narrows: true,
    the_asker_is_never_told: true,
    every_change_is_in_the_audit_trail: true,
    ...overrides,
  };
}

async function toolsPage(answers: Record<string, Answer>) {
  return mountPage(
    TOOLS_PATH,
    async () => {
      const { Tools } = await import("../src/pages/Tools");
      return <Tools />;
    },
    answers,
  );
}

async function toolPage(answers: Record<string, Answer>, name = "drive.delete_file") {
  return mountPage(
    `${TOOLS_PATH}/${name}`,
    async () => {
      const { ToolDetailPage } = await import("../src/pages/tools/ToolDetailPage");
      return <ToolDetailPage name={name} />;
    },
    answers,
  );
}

function outsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

describe("the list", () => {
  test("every tool with its source, effect and status, and one sentence about what a switch is", async () => {
    // What breaks if this is deleted: a tool switched off drawn as on, or the list unreachable.
    const { container } = await toolsPage({
      [LIST]: () => json(page({}, { off_for_install: stop(), stopped_for: [stop({ department: "web" })] })),
    });
    const text = container.textContent ?? "";
    expect(text).toContain("drive.delete_file");
    expect(text).toContain("Off for the install");
    expect(text).toContain("Stopped for web");
    expect(text).toContain(A_SWITCH_ONLY_NARROWS);
    expect(text).not.toContain("u_switcher_sentinel");
    expect(container.querySelector('a[href="/tools/drive.delete_file"]')).not.toBeNull();
  });

  test("a refusal is the API's sentence with its reference, and an unreadable answer says so", async () => {
    // What breaks if this is deleted: a refused reader shown an empty list, which reads as an
    // install with no tools.
    const refused = await toolsPage({ [LIST]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404) });
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.container.textContent).toContain("TRACE-SENTINEL");
    const unreadable = await toolsPage({ [LIST]: () => json({ tools: "no" }) });
    expect(unreadable.container.textContent).toContain(UNREADABLE_ANSWER);
  });
});

describe("a tool's page", () => {
  test("what it needs and does in words, with who switched it off only in Advanced", async () => {
    // What breaks if this is deleted: an effect drawn as a code, or a principal id in page text.
    const { container } = await toolPage({ [LIST]: () => json(page({}, { off_for_install: stop({ reason: "NOTE-SENTENCE" }) })) });
    const text = outsideAdvanced(container);
    expect(text).toContain("write:file.body");
    expect(text).toContain(EFFECT_SENTENCES.irreversible);
    expect(text).toContain(SENSITIVE_EFFECT_SENTENCES.deletion);
    expect(text).toContain("NOTE-SENTENCE");
    expect(text).not.toContain("u_switcher_sentinel");
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain("u_switcher_sentinel");
  });

  test("a department's reader is offered their own department and not the install, and a tool no longer registered none", async () => {
    // What breaks if this is deleted: a department admin offered the install's switch, which the
    // route would refuse, or a switch on a tool nothing registers.
    const narrow = await toolPage({ [LIST]: () => json(page({ may_switch_install: false })) });
    const labels = [...narrow.container.querySelectorAll("button")].map((one) => one.getAttribute("aria-label") ?? "");
    expect(labels.some((one) => one.startsWith("Stop for web"))).toBe(true);
    expect(labels.some((one) => one.startsWith(SWITCH_OFF_FOR_THE_INSTALL))).toBe(false);

    const gone = await toolPage({ [LIST]: () => json(page({}, { registered: false })) });
    expect(gone.container.textContent).toContain(NO_LONGER_OFFERED);
    expect([...gone.container.querySelectorAll("button")].filter((one) => (one.getAttribute("aria-label") ?? "").includes("drive.delete_file"))).toEqual([]);
  });

  test("a name the list does not carry says so and draws nothing else", async () => {
    // What breaks if this is deleted: a page drawn for a tool that is not there.
    const { container } = await toolPage({ [LIST]: () => json(page()) }, "nothing.here");
    expect(container.textContent).toContain(NO_SUCH_TOOL);
  });
});

describe("switching a tool", () => {
  test("is confirmed, says what a reason must be before it is sent, posts the place and the note, and re-reads", async () => {
    // What breaks if this is deleted: a switch from one press, a note dropped, or a page that
    // goes on drawing the old state.
    let off = false;
    const { container, sent } = await toolPage({
      [LIST]: () => json(page({}, off ? { off_for_install: stop() } : {})),
      [SWITCH]: () => {
        off = true;
        return json({ tool: tool({ off_for_install: stop() }), changed: true });
      },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: `${SWITCH_OFF_FOR_THE_INSTALL}: drive.delete_file` }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "  a note  " } });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: SWITCH_OFF_FOR_THE_INSTALL }));
    });

    await waitFor(() => {
      expect(container.textContent).toContain("is switched off for the install");
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([{ on: false, department: null, reason: "a note" }]);
    expect(container.textContent).toContain("Off for the install");
    expect(sent.filter((one) => one.method === "GET").length).toBeGreaterThan(1);
  });

  test("starting a tool again says how long its reason must be before anything is sent, and keeping it sends nothing", async () => {
    // What breaks if this is deleted: a person learning the reason's length only from a refusal.
    const { sent } = await toolPage({ [LIST]: () => json(page({}, { off_for_install: stop() })) });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: `${SWITCH_ON_FOR_THE_INSTALL}: drive.delete_file` }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("at least 12 characters");
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: KEEP_IT }));
    });
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: the API renames a field and the page draws undefined.
    expect(backendModelFields(ROUTES, "CatalogueToolView")).toEqual(Object.keys(tool()));
    expect(backendModelFields(ROUTES, "ToolStopView")).toEqual(Object.keys(stop()));
    expect(backendModelFields(ROUTES, "ToolsPage")).toEqual(Object.keys(page()));
  });
});
