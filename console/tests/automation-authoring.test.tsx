/**
 * New automation on the Automations tab: the form, the review with its rehearsal, and the one
 * confirmed write.
 *
 * Mounted through the application's own route table, as `tests/automation-gallery.test.tsx` is, so
 * a component the tab never draws cannot pass. What the server decides (who may, what is fit, what
 * the digest covers) is `tests/unit/test_automation_authoring_routes.py`'s. What is proved here is
 * the half a browser owns: nothing is drawn while the install has the feature off, nothing is sent
 * before the second press, the second press carries the API's own digest, the refusal's every
 * sentence is shown, and the readers match the routes' declared schemas.
 *
 * Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.3, M39.9.2.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NEW_AUTOMATION, REVIEW, SAVE, SAVED_TITLE } from "../src/pages/agents/AutomationAuthoring";
import {
  draftBody,
  readAuthoringOptions,
  readAuthoringPreview,
  readRefusal,
  startDraft,
} from "../src/pages/automationAuthoringQuery";
import { readAgentAutomations } from "../src/pages/agentAutomationsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { declaredPropertyNames, declaredRequestBodySchema, declaredResponseSchema } from "./support/openapi";

const CONSOLE_ORIGIN = "https://console.test";
const WORKSPACE = "/api/v1/agents/quote-helper/workspace";
const OPTIONS = "/api/v1/agents/quote-helper/automation-authoring";
const PREVIEW = `${OPTIONS}/preview`;
const CREATE = "/api/v1/agents/quote-helper/automations/authored";
const LIST = "/api/v1/agents/quote-helper/automations";
const GALLERY = "/api/v1/agents/quote-helper/automation-templates";

const DIGEST = "d".repeat(64);

beforeAll(async () => {
  await import("../src/pages/Agent");
  await import("../src/App");
}, 60_000);

function optionsWire(enabled = true): Record<string, unknown> {
  return {
    enabled,
    templates: enabled
      ? [
          {
            template_id: "unanswered_questions",
            name: "I list the questions I could not answer this week",
            summary: "Every question this agent answered with nothing.",
            guards: "Without it a gap in what this agent draws on is found one person at a time.",
            every: "week",
            hour_utc: 8,
            weekday: 0,
          },
        ]
      : [],
    triggers: enabled
      ? [
          { kind: "schedule", label: "On a schedule", fires: true, not_offered: null },
          { kind: "connector_event", label: "When something changes in a connected source", fires: false, not_offered: null },
          { kind: "webhook", label: "When another system calls it", fires: false, not_offered: "Not offered. An automation here starts on a schedule or when a connected source reports a change, and nothing starts work from outside." },
        ]
      : [],
    fields: enabled
      ? [
          {
            key: "freshdesk.ticket.due_by",
            label: "ticket due by (freshdesk)",
            shape: "timestamp",
            ops: [{ op: "is_over", label: "is more than ... days ago", in_days: true }],
          },
        ]
      : [],
    tools: enabled ? ["search_tickets"] : [],
    connectors: enabled ? ["freshdesk"] : [],
    starts_paused: "It starts paused, and somebody other than you has to start it.",
    writes_wait: "Anything it would write waits for a person to decide.",
  };
}

function previewWire(): Record<string, unknown> {
  return {
    agent_id: "quote-helper",
    from_template: null,
    name: "I check each morning whether any ticket is overdue",
    instruction: "Tell me which tickets are overdue.",
    guards: "Without it an overdue ticket is found when the client chases.",
    task: "automation.instruction",
    trigger: "Runs every weekday at 09:00 UTC",
    fires: true,
    nothing_fires: null,
    condition: "only when the ticket due by (freshdesk) is more than 7 days ago",
    tools: ["search_tickets"],
    runs_as: "u_admin",
    runs_as_name: "Admin Person",
    reach: ["read:client.name"],
    starts_paused: "It starts paused, and somebody other than you has to start it.",
    writes_wait: "Anything it would write waits for a person to decide.",
    rehearsal: [
      { at: "2031-03-13T09:00:00Z", condition: "cannot_tell", says: "Whether the condition held cannot be told. Nothing was read, written or sent." },
    ],
    rehearsal_rule: "A rehearsal makes no model call and reads no record.",
    confirmation: DIGEST,
  };
}

type Handler = (body: unknown) => { readonly status?: number; readonly body: unknown };

async function consoleAt(handlers: Record<string, Handler>) {
  const sent: { readonly method: string; readonly path: string; readonly body: unknown }[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      const handler = handlers[`${method} ${path}`];
      if (handler === undefined) {
        return null;
      }
      const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : null;
      sent.push({ method, path, body });
      const answer = handler(body);
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json", "x-trace-id": "trace-authoring" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/agents/quote-helper/automations"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector('[data-slot="detail-header"] h1')) {
      throw new Error("the workspace has not arrived");
    }
  });
  return { container, sent };
}

const ANSWERING: Record<string, Handler> = {
  [`GET ${WORKSPACE}`]: () => ({
    body: {
      agent: { agent_id: "quote-helper", display_name: "Quote Helper", owner_id: "steward-one" },
      tabs: [{ tab: "automations", label: "Automations", purpose: "What this agent runs on a schedule." }],
      composition: [],
    },
  }),
  [`GET ${LIST}`]: () => ({ body: { items: [], result_rule: "Only whom it ran as sees it." } }),
  [`GET ${GALLERY}`]: () => ({ body: { items: [], installing: "Nothing runs yet." } }),
  [`GET ${OPTIONS}`]: () => ({ body: optionsWire() }),
  [`POST ${PREVIEW}`]: () => ({ body: previewWire() }),
};

function button(container: HTMLElement, label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll<HTMLButtonElement>("button")].find(
    (one) => one.textContent === label || one.getAttribute("aria-label") === label,
  );
  if (!found) {
    throw new Error(`No button labelled ${label}.`);
  }
  return found;
}

async function formOpen(handlers: Record<string, Handler>) {
  const stand = await consoleAt(handlers);
  await waitFor(() => {
    button(stand.container, NEW_AUTOMATION);
  });
  fireEvent.click(button(stand.container, NEW_AUTOMATION));
  return stand;
}

function write(container: HTMLElement, name: string, value: string): void {
  const control = container.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(`[name="${name}"]`);
  if (!control) {
    throw new Error(`No control named ${name}.`);
  }
  fireEvent.change(control, { target: { value } });
}

describe("New automation", () => {
  test("an install that has not switched it on draws no control for it", async () => {
    // What breaks if this is deleted: a New automation button on every install, whose first
    // press is refused, which is the control that reaches nothing.
    const stand = await consoleAt({ ...ANSWERING, [`GET ${OPTIONS}`]: () => ({ body: optionsWire(false) }) });
    await waitFor(() => {
      expect(stand.sent.some((one) => one.path === OPTIONS)).toBe(true);
    });

    expect([...stand.container.querySelectorAll("button")].some((one) => one.textContent === NEW_AUTOMATION)).toBe(false);
  });

  test("the form offers only what the API offered and nothing is sent until it is reviewed", async () => {
    // What breaks if this is deleted: a form drawn from a list written here, or one that sends
    // on the first press.
    const stand = await formOpen(ANSWERING);
    const text = stand.container.textContent ?? "";

    expect(text).toContain("On a schedule");
    expect(text).toContain("When something changes in a connected source");
    expect(text).toContain("ticket due by (freshdesk)");
    expect(text).toContain("search_tickets");
    expect(stand.container.querySelector('[name="start"]')?.textContent).toContain("I list the questions I could not answer");
    expect(stand.sent.filter((one) => one.method === "POST")).toEqual([]);
  });

  test("a template start fills the words, a change trigger says it is switched off, and a webhook is listed as not offered", async () => {
    // What breaks if this is deleted: a template that leaves the form empty, a change trigger that
    // looks live on an install that has not switched it on, or a webhook that can be chosen.
    const stand = await formOpen(ANSWERING);

    write(stand.container, "start", "unanswered_questions");
    expect((stand.container.querySelector('[name="name"]') as HTMLInputElement).value).toBe(
      "I list the questions I could not answer this week",
    );
    write(stand.container, "trigger", "connector_event");
    expect(stand.container.textContent).toContain("Starting on a change is switched off on this install");
    const webhook = stand.container.querySelector('[name="trigger"] option[value="webhook"]') as HTMLOptionElement;
    expect(webhook.disabled).toBe(true);
    expect(webhook.textContent).toContain("(not offered)");
    const change = stand.container.querySelector('[name="trigger"] option[value="connector_event"]') as HTMLOptionElement;
    expect(change.disabled).toBe(false);
  });

  test("Review sends what was written, shows the terms and the rehearsal, and Save sends the API's digest", async () => {
    // What breaks if this is deleted: a review that writes, a save without the digest, or a
    // console that computes its own digest.
    const stand = await formOpen({
      ...ANSWERING,
      [`POST ${CREATE}`]: () => ({ status: 201, body: { automation_id: "auto_new", name: "I check each morning whether any ticket is overdue", starts_paused: "It starts paused." } }),
    });
    write(stand.container, "name", "I check each morning whether any ticket is overdue");
    write(stand.container, "instruction", "Tell me which tickets are overdue.");
    write(stand.container, "guards", "Without it an overdue ticket is found when the client chases.");
    write(stand.container, "condition-field", "freshdesk.ticket.due_by");
    write(stand.container, "condition-value", "7");
    fireEvent.click(stand.container.querySelector('input[type="checkbox"]') as HTMLElement);
    fireEvent.click(button(stand.container, REVIEW));
    await waitFor(() => {
      expect(stand.container.querySelector('[data-slot="authoring-rehearsal"]')).not.toBeNull();
    });

    const preview = stand.sent.find((one) => one.path === PREVIEW);
    expect(preview?.body).toMatchObject({
      name: "I check each morning whether any ticket is overdue",
      trigger: { kind: "schedule", cadence: { every: "weekday", hour_utc: 9 } },
      condition: { field: "freshdesk.ticket.due_by", op: "is_over", value: "7" },
      tools: ["search_tickets"],
    });
    expect(stand.sent.filter((one) => one.path === CREATE)).toEqual([]);
    expect(stand.container.textContent).toContain("Whether the condition held cannot be told");
    expect(stand.container.textContent).toContain("Admin Person");

    fireEvent.click(button(stand.container, SAVE));
    await waitFor(() => {
      expect(stand.container.textContent).toContain(SAVED_TITLE);
    });
    const written = stand.sent.find((one) => one.path === CREATE);
    expect(written?.body).toMatchObject({ confirmation: DIGEST, tools: ["search_tickets"] });
    expect(Object.keys(written?.body as object).sort()).toEqual(
      ["condition", "confirmation", "guards", "instruction", "name", "tools", "trigger"].sort(),
    );
  });

  test("a refusal of what was written shows every sentence and sends no write", async () => {
    // What breaks if this is deleted: a form corrected one error at a time, or a refusal the
    // person cannot read.
    const stand = await formOpen({
      ...ANSWERING,
      [`POST ${PREVIEW}`]: () => ({
        status: 422,
        body: { outcome: "refused", sentences: ["This agent may not use send_email.", "Say what goes wrong if this does not run."] },
      }),
    });
    fireEvent.click(button(stand.container, REVIEW));
    await waitFor(() => {
      expect(stand.container.querySelector('[data-slot="authoring-findings"]')).not.toBeNull();
    });

    expect(stand.container.textContent).toContain("This agent may not use send_email.");
    expect(stand.container.textContent).toContain("Say what goes wrong if this does not run.");
    expect(stand.sent.filter((one) => one.path === CREATE)).toEqual([]);
  });
});

describe("the readers", () => {
  test("a preview missing a fact the person confirms is refused whole, and a bad digest is refused", () => {
    // What breaks if this is deleted: a confirmation panel with a fact left out, over a digest
    // computed on the whole of it.
    expect(readAuthoringPreview(previewWire())).not.toBeNull();
    for (const key of ["name", "instruction", "trigger", "runs_as", "reach", "rehearsal", "confirmation"]) {
      const wire = previewWire();
      delete wire[key];
      expect(readAuthoringPreview(wire)).toBeNull();
    }
    expect(readAuthoringPreview({ ...previewWire(), confirmation: "short" })).toBeNull();
  });

  test("the options, the refusal and the body are read as the API sends them", () => {
    // What breaks if this is deleted: a renamed field draws a form with nothing in it.
    expect(readAuthoringOptions(optionsWire(false))).toMatchObject({ enabled: false, templates: [], fields: [] });
    expect(readAuthoringOptions(optionsWire())?.fields[0]?.ops[0]?.inDays).toBe(true);
    expect(readAuthoringOptions({ enabled: "yes" })).toBeNull();
    expect(readRefusal({ outcome: "refused", sentences: ["one"] })).toEqual(["one"]);
    expect(readRefusal({ outcome: "refused", sentences: [] })).toBeNull();
    expect(readRefusal({ outcome: "other", sentences: ["one"] })).toBeNull();
    const weekly = { ...startDraft(undefined), every: "week" as const, weekday: 4 };
    expect(draftBody(weekly)["trigger"]).toEqual({ kind: "schedule", cadence: { every: "week", hour_utc: 9, weekday: 4 } });
    expect(draftBody({ ...startDraft(undefined), kind: "webhook", source: " hook " })["trigger"]).toEqual({ kind: "webhook", source: "hook" });
  });

  test("a listed automation carries what a person wrote, in the API's words, or nothing", () => {
    // What breaks if this is deleted: the card cannot say when it runs and only when, or draws a
    // half-read block for an automation installed as it was.
    const item = {
      automation_id: "auto_w",
      name: "I check each morning whether any ticket is overdue",
      runs_as: "u_admin",
      runs_as_name: "Admin Person",
      schedule: "Runs every day at 07:00 UTC",
      next_run_at: null,
      paused_because: "Installed and not started yet.",
      last_run: null,
      authored: {
        trigger: "Runs every day at 07:00 UTC",
        fires: true,
        condition: "only when the ticket due by (freshdesk) is more than 7 days ago",
        instruction: "Tell me which tickets are overdue.",
        tools: ["search_tickets"],
        from_template: null,
        writes_wait: "Anything it would write waits for a person.",
      },
    };
    const read = readAgentAutomations({ items: [item, { ...item, automation_id: "auto_x", authored: { trigger: "x" } }], result_rule: "r" });

    expect(read?.items[0]?.authored).toEqual({
      trigger: "Runs every day at 07:00 UTC",
      fires: true,
      condition: "only when the ticket due by (freshdesk) is more than 7 days ago",
      instruction: "Tell me which tickets are overdue.",
      tools: ["search_tickets"],
      writesWait: "Anything it would write waits for a person.",
    });
    expect(read?.items[1]?.authored).toBeUndefined();
  });

  test("the readers match the routes' declared schemas", () => {
    // What breaks if this is deleted: a field renamed in the API that the console silently drops.
    const options = declaredResponseSchema("/api/v1/agents/{agent_id}/automation-authoring", "get");
    const shown = declaredResponseSchema("/api/v1/agents/{agent_id}/automation-authoring/preview", "post");
    const asking = declaredRequestBodySchema("/api/v1/agents/{agent_id}/automation-authoring/preview", "post");
    const writing = declaredRequestBodySchema("/api/v1/agents/{agent_id}/automations/authored", "post");

    expect(declaredPropertyNames(options)).toEqual(Object.keys(optionsWire()).sort());
    expect(declaredPropertyNames(shown)).toEqual(Object.keys(previewWire()).sort());
    expect(declaredPropertyNames(asking)).toEqual(["condition", "guards", "instruction", "name", "template_id", "tools", "trigger"]);
    expect(declaredPropertyNames(writing)).toEqual([...declaredPropertyNames(asking), "confirmation"].sort());
  });
});
