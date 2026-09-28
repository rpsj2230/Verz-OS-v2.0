/**
 * The Tools screen: every tool drawn with what it needs and does, the switches this reader may
 * throw and no others, a confirmed switch posted to the place it names and then re-read, and the
 * facts about what a switch is said only while the API says them.
 *
 * Mounted on its own at its address. The shapes are read from `brain.tool_routes` itself, so a
 * renamed field fails here.
 *
 * Task ids: M12.1.3, M12.3.8, M12.4.3
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  A_SWITCH_ONLY_NARROWS,
  EFFECT_SENTENCES,
  KEEP_IT,
  NO_LONGER_OFFERED,
  OFF_FOR_THE_INSTALL,
  SENSITIVE_EFFECT_SENTENCES,
  SWITCH_OFF_FOR_THE_INSTALL,
  SWITCH_ON_FOR_THE_INSTALL,
  THE_ASKER_IS_NEVER_TOLD,
  TOOLS_API_PATH,
  TOOLS_PATH,
  UNREADABLE_ANSWER,
} from "../src/pages/toolsQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";

const LIST = `GET /api/v1${TOOLS_API_PATH}`;
const SWITCH = `POST /api/v1${TOOLS_API_PATH}/drive.delete_file/switch`;
const ROUTES = "src/brain/tool_routes.py";

function stop(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    department: null,
    switched_off_by: "u_admin",
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

describe("what the Tools screen draws", () => {
  test("a tool with the capability it needs, its effect in words, and the owner's sensitive effect", async () => {
    // What breaks if this is deleted: a tool listed without saying what a person must hold for it
    // or whether a call to it can be taken back, which is the owner's Tools screen with its two
    // facts missing.
    const { container } = await toolsPage({ [LIST]: () => json(page()) });
    const text = container.textContent ?? "";
    expect(text).toContain("drive.delete_file");
    expect(text).toContain("write:file.body");
    expect(text).toContain("Irreversible");
    expect(text).toContain(EFFECT_SENTENCES["irreversible"]);
    expect(text).toContain(SENSITIVE_EFFECT_SENTENCES["deletion"]);
    expect(text).toContain(A_SWITCH_ONLY_NARROWS);
    expect(text).toContain(THE_ASKER_IS_NEVER_TOLD);
  });

  test("a stopped tool says where and by whom, and a tool no longer registered cannot be switched", async () => {
    // What breaks if this is deleted: a switched-off tool drawn as on, or a button on a tool no
    // process offers, which writes a stop nothing reads.
    const { container } = await toolsPage({
      [LIST]: () =>
        json(page({}, { off_for_install: stop(), stopped_for: [stop({ department: "web" })], registered: false })),
    });
    const text = container.textContent ?? "";
    expect(text).toContain(OFF_FOR_THE_INSTALL);
    expect(text).toContain("Stopped for web");
    expect(text).toContain("Switched off for the install by u_admin");
    expect(text).toContain(NO_LONGER_OFFERED);
    expect(button(container, SWITCH_ON_FOR_THE_INSTALL).disabled).toBe(true);
  });

  test("a department's reader is offered their own department and not the install", async () => {
    // What breaks if this is deleted: a department administrator shown a switch for the whole
    // install, which the API refuses after they have filled in a reason.
    const { container } = await toolsPage({
      [LIST]: () => json(page({ may_switch_install: false, departments: ["web"] })),
    });
    const labels = [...container.querySelectorAll("button")].map((one) => one.textContent ?? "");
    expect(labels).toContain("Stop for web");
    expect(labels).not.toContain(SWITCH_OFF_FOR_THE_INSTALL);
  });

  test("a refusal is the API's sentence with its reference, and an unreadable answer says so", async () => {
    // What breaks if this is deleted: a refused reader shown an empty catalogue, which reads as an
    // install with no tools rather than a request that was refused.
    const refused = await toolsPage({
      [LIST]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    });
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.container.textContent).toContain("TRACE-SENTINEL");

    const unreadable = await toolsPage({ [LIST]: () => json({ tools: "no" }) });
    expect(unreadable.container.textContent).toContain(UNREADABLE_ANSWER);
  });
});

describe("switching a tool", () => {
  test("is confirmed, posted for the place it names with the note typed, and re-read", async () => {
    // What breaks if this is deleted: a switch sent without confirmation, sent for the wrong place,
    // or a page that goes on drawing the old state after the database changed.
    let off = false;
    const { container, sent } = await toolsPage({
      [LIST]: () => json(page({}, { off_for_install: off ? stop() : null })),
      [SWITCH]: (body) => {
        off = !(body as { on: boolean }).on;
        return json({ tool: tool({ off_for_install: off ? stop() : null }), changed: true });
      },
    });

    fireEvent.click(button(container, SWITCH_OFF_FOR_THE_INSTALL));
    fireEvent.click(button(container, KEEP_IT));
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);

    fireEvent.click(button(container, SWITCH_OFF_FOR_THE_INSTALL));
    fireEvent.change(container.querySelector("textarea[name='reason']") as HTMLTextAreaElement, {
      target: { value: "the vendor reported a fault" },
    });
    const confirm = [...container.querySelectorAll(".confirm button")].find(
      (one) => one.textContent === SWITCH_OFF_FOR_THE_INSTALL,
    );
    fireEvent.click(confirm as HTMLButtonElement);

    await waitFor(() => {
      expect(container.textContent).toContain("is switched off for the install");
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { on: false, department: null, reason: "the vendor reported a fault" },
    ]);
    expect(sent.filter((one) => one.method === "GET").length).toBeGreaterThanOrEqual(2);
    expect(container.textContent).toContain(OFF_FOR_THE_INSTALL);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.tool_routes` that the page goes on
    // reading, which renders as an empty sentence in production.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "ToolsPage").sort());
    expect(Object.keys(tool()).sort()).toEqual(backendModelFields(ROUTES, "CatalogueToolView").sort());
    expect(Object.keys(stop()).sort()).toEqual(backendModelFields(ROUTES, "ToolStopView").sort());
  });
});
