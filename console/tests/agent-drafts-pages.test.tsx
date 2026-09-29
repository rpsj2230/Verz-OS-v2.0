/**
 * New agent, the drafts list, one draft, Edit as a draft and the waiting publishes on Approvals,
 * each mounted through the application's own route table and answered by a stand-in API.
 *
 * What is held: every write is sent only after a confirmation and carries exactly what the page
 * drew (the version a save was made from, the version a publish names); a refusal is drawn in the
 * API's own sentence; the form is the API's; a list the API did not send is absent rather than
 * drawn empty under a heading; and publishing on an install without a signing key is inert with
 * the API's reason.
 *
 * Task ids: M27.11.6, M27.15.31
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { UNAVAILABLE_MARK } from "../src/components/kit";
import {
  APPROVE_QUESTION,
  CHECK_QUESTION,
  DRAW_QUESTION,
  TOOLS_LIST_LABEL,
  TOOLS_SECTION_HEADING,
  DRAFTS_ADDRESS,
  EDIT_QUESTION,
  NEW_AGENT_ADDRESS,
  PUBLISH_QUESTION,
  SAVE_QUESTION,
  START_SCRATCH_QUESTION,
  START_TEMPLATE_QUESTION,
  draftAddress,
  withSection,
} from "../src/pages/agents/agentDraftsQuery";
import { NO_DRAFTS, WAITING_HEADING } from "../src/pages/agents/DraftsPage";
import {
  APPROVE_LABEL,
  CHECK_LABEL,
  DRAW_LABEL,
  ENTER_SKILL_NAME,
  ENTER_WHEN_TO_USE,
  NO_TOOLS_TO_DRAW,
  OPEN_WRITE_STEP,
  PROCEDURE_DESCRIPTION,
  PROCEDURE_NAME,
  PUBLISH_LABEL,
  ON_THE_WEB_PAGE,
} from "../src/pages/agents/DraftPage";
import { ADD_WORDS } from "../src/components/ProcedureCanvas";
import { ADDABLE_KINDS } from "../src/components/procedure";
import { CHECK_THESE_ANSWERS } from "../src/components/SchemaForm";
import { EDIT_AS_DRAFT } from "../src/pages/agents/AgentDetailPage";
import { SCRATCH_LABEL } from "../src/pages/agents/NewAgentPage";
import { START_LABEL } from "../src/pages/agents/DraftStart";
import { WAITING_PUBLISHES_HEADING } from "../src/pages/agents/WaitingPublishes";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { installRadixStubs } from "./support/radix";
import { readConsoleFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const DRAFT_ID = "44444444-4444-4444-8444-444444444444";
const DRAFT_API = `/api/v1/agent-drafts/${DRAFT_ID}`;
const FORM = JSON.parse(readConsoleFile("tests/fixtures/manifest-form.json")) as unknown;
const NOT_CHANGED_SENTENCE = "This draft was saved again after you opened it, so nothing was saved.";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/AgentDraft");
  await import("../src/pages/Agent");
}, 60_000);

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

/** Answers by method and path: `GET /api/v1/x` or `POST /api/v1/x`. */
type Answers = Readonly<Record<string, Answer>>;

async function consoleAt(path: string, answers: Answers): Promise<{ container: HTMLElement; idp: FakeIdp; router: ReturnType<typeof createMemoryRouter> }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      const answer = answers[`${method} ${new URL(url, CONSOLE_ORIGIN).pathname}`];
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, idp, router };
}

/** Every list's Add words the served form holds, outside a list entry (drawn with nothing in it). */
function addWordsIn(form: unknown): string[] {
  const found: string[] = [];
  const walk = (ui: unknown): void => {
    if (typeof ui !== "object" || ui === null || Array.isArray(ui)) {
      return;
    }
    for (const [key, inner] of Object.entries(ui)) {
      if (key === "ui:options" && typeof inner === "object" && inner !== null && "addLabel" in inner) {
        found.push(String((inner as { addLabel: unknown }).addLabel));
      } else if (key !== "items" && key !== "anyOf") {
        walk(inner);
      }
    }
  };
  for (const one of (form as { sections: { ui: unknown }[] }).sections) {
    walk(one.ui);
  }
  return found;
}

function posts(idp: FakeIdp): { readonly path: string; readonly body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/v1/"))
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: JSON.parse(String(call.init?.body ?? "null")) }));
}

function button(label: string): HTMLButtonElement {
  return screen.getByRole("button", { name: label });
}

async function confirmIn(question: string, label: string): Promise<void> {
  const dialog = await screen.findByRole("alertdialog");
  expect(within(dialog).getByText(question)).toBeDefined();
  await act(async () => {
    fireEvent.click(within(dialog).getByRole("button", { name: label }));
  });
}

function aDraft(overrides: Readonly<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    draft_id: DRAFT_ID,
    agent_id: "invoice_helper_ab12cd",
    name: "Invoice helper",
    kind: "new",
    state: "draft",
    revision: 2,
    saved_at: "2019-03-04T09:00:00Z",
    document: {
      identity: { template_id: "invoice_helper_ab12cd", version: 1, published_by: "u_admin", display_name: "Invoice helper", summary: "" },
      persona: "Answer briefly.",
      tier: "main",
      skills: [],
      authority: { scope: { clauses: [] }, capabilities: [], allowed_tools: [], required_tools: [] },
      connectors: [],
      guardrails: { max_side_effect: "none", leash: [] },
      golden_set: [],
      placeholders: [],
    },
    problems: [],
    acts: [],
    yours: true,
    waiting_on_you: false,
    widened: [],
    drawable_tools: [],
    publish_unavailable: null,
    ...overrides,
  };
}

// ------------------------------------------------------------------------------ New agent
describe("New agent", () => {
  test("starting from scratch is confirmed, sends an empty start and lands on the draft", async () => {
    // What breaks if this is deleted: a New agent that makes a draft on one press with nothing said
    // first, or one that makes it and leaves the person on a page that does not show it.
    const { idp, router } = await consoleAt(NEW_AGENT_ADDRESS, {
      "GET /api/v1/agent-templates": { body: { items: [], next_cursor: null, truncated: false } },
      "POST /api/v1/agent-drafts": { status: 201, body: aDraft() },
      [`GET ${DRAFT_API}`]: { body: aDraft() },
      "GET /api/v1/builder/form": { body: FORM },
    });
    fireEvent.click(button(SCRATCH_LABEL));
    expect(posts(idp)).toEqual([]);
    await confirmIn(START_SCRATCH_QUESTION, START_LABEL);

    expect(posts(idp)).toEqual([{ path: "/api/v1/agent-drafts", body: {} }]);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(draftAddress(DRAFT_ID));
    });
  });

  test("starting from a template names it in the question and sends its id", async () => {
    // What breaks if this is deleted: a template start that sends no id, so every template start
    // becomes a blank draft, or one that starts a draft of a template the person did not choose.
    const { idp } = await consoleAt(NEW_AGENT_ADDRESS, {
      "GET /api/v1/agent-templates": {
        body: { items: [{ template_id: "support_ticket_agent", version: 1, display_name: "Support tickets", published_by: "system", origin: "built_in" }] },
      },
      "POST /api/v1/agent-drafts": { status: 201, body: aDraft() },
      [`GET ${DRAFT_API}`]: { body: aDraft() },
      "GET /api/v1/builder/form": { body: FORM },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start from this: Support tickets/ }));
    await confirmIn(START_TEMPLATE_QUESTION("Support tickets"), START_LABEL);

    expect(posts(idp)).toEqual([{ path: "/api/v1/agent-drafts", body: { template_id: "support_ticket_agent" } }]);
  });
});

// ------------------------------------------------------------------------------ the list
describe("the drafts list", () => {
  test("draws the reader's drafts with their state, and no waiting heading when nothing waits", async () => {
    // What breaks if this is deleted: a waiting heading over nothing, which says publishes exist the
    // reader may not see, or states drawn as the API's bare words.
    const { container } = await consoleAt(DRAFTS_ADDRESS, {
      "GET /api/v1/agent-drafts": {
        body: {
          items: [{ draft_id: DRAFT_ID, agent_id: "a_1", name: "Invoice helper", kind: "new", state: "waiting", revision: 2 }],
          waiting_for_you: [],
        },
      },
    });
    expect(container.textContent).toContain("Waiting for a second approver");
    expect(container.textContent).not.toContain(WAITING_HEADING);
    const link = [...container.querySelectorAll("a")].find((one) => one.textContent === "Invoice helper");
    expect(link?.getAttribute("href")).toBe(draftAddress(DRAFT_ID));
  });

  test("an empty list says how a draft is started, and a waiting list is drawn when it is sent", async () => {
    // What breaks if this is deleted: a blank panel that reads as still loading, or a queue of
    // publishes the second person never sees.
    const { container } = await consoleAt(DRAFTS_ADDRESS, {
      "GET /api/v1/agent-drafts": {
        body: {
          items: [],
          waiting_for_you: [{ draft_id: DRAFT_ID, agent_id: "a_1", name: "Invoice helper", kind: "new", state: "waiting", revision: 2 }],
        },
      },
    });
    expect(container.textContent).toContain(NO_DRAFTS);
    expect(container.textContent).toContain(WAITING_HEADING);
  });
});

// ------------------------------------------------------------------------------ one draft
describe("one draft", () => {
  test("a section saved is confirmed and sends the whole draft with it merged in, from the version shown", async () => {
    // What breaks if this is deleted: a save that sends only the section, which the API would keep as
    // the whole draft, or one that names no version, so a second tab's save is buried in silence.
    const { container, idp } = await consoleAt(draftAddress(DRAFT_ID), {
      [`GET ${DRAFT_API}`]: { body: aDraft() },
      "GET /api/v1/builder/form": { body: FORM },
      [`POST ${DRAFT_API}/revisions`]: { body: { revision: 3, state: "draft", problems: [] } },
    });
    const persona = container.querySelector<HTMLElement>('section[data-section="persona"] form');
    expect(persona).not.toBeNull();
    await act(async () => {
      fireEvent.submit(persona as HTMLFormElement);
    });
    await confirmIn(SAVE_QUESTION("Instructions"), "Save");

    const [sent] = posts(idp);
    expect(sent?.path).toBe(`${DRAFT_API}/revisions`);
    const body = sent?.body as { document: Record<string, unknown>; base: number };
    expect(body.base).toBe(2);
    expect(body.document["identity"]).toEqual((aDraft()["document"] as Record<string, unknown>)["identity"]);
    expect(body.document["persona"]).toBe("Answer briefly.");
  });

  test("a refused save says the API's sentence", async () => {
    // What breaks if this is deleted: a stale save drawn as a failure with nothing to act on, or as
    // saved.
    await consoleAt(draftAddress(DRAFT_ID), {
      [`GET ${DRAFT_API}`]: { body: aDraft() },
      "GET /api/v1/builder/form": { body: FORM },
      [`POST ${DRAFT_API}/revisions`]: { status: 409, body: { outcome: "moved", sentence: NOT_CHANGED_SENTENCE } },
    });
    const persona = document.querySelector<HTMLElement>('section[data-section="persona"] form');
    await act(async () => {
      fireEvent.submit(persona as HTMLFormElement);
    });
    await confirmIn(SAVE_QUESTION("Instructions"), "Save");
    await waitFor(() => {
      expect(document.body.textContent).toContain(NOT_CHANGED_SENTENCE);
    });
  });

  test("on the Write step every list's Add button is found by its name, and a tool added is saved with the draft", async () => {
    // What breaks if this is deleted: the defect found on the owner's install on 2026-09-29. Every Add
    // button on this step was Bootstrap markup the kit's reset drew at 0 by 0 pixels, so no tool could
    // be allowed and the Procedure step could never be used. Each of the nine lists' buttons is found
    // by the name the served form gives it, and the tool list's is pressed, typed into and saved.
    const { idp } = await consoleAt(draftAddress(DRAFT_ID, "write"), {
      [`GET ${DRAFT_API}`]: { body: aDraft() },
      "GET /api/v1/builder/form": { body: FORM },
      [`POST ${DRAFT_API}/revisions`]: { body: { revision: 3, state: "draft", problems: [] } },
    });
    const names = addWordsIn(FORM);
    expect(names).toHaveLength(9);
    for (const name of names) {
      expect(screen.getByRole("button", { name }).getAttribute("data-slot"), name).toBe("button");
    }

    fireEvent.click(screen.getByRole("button", { name: "Add a tool it may use" }));
    fireEvent.change(screen.getByLabelText("Tool 1"), { target: { value: "helpdesk.read_ticket" } });
    fireEvent.click(screen.getByRole("button", { name: "Save tools and permissions" }));
    await confirmIn(SAVE_QUESTION(TOOLS_SECTION_HEADING), "Save");

    const [sent] = posts(idp);
    const authority = (sent?.body as { document: Record<string, Record<string, unknown>> }).document["authority"];
    expect(authority?.["allowed_tools"]).toEqual(["helpdesk.read_ticket"]);
    // The knowledge section's half of the same object is kept.
    expect(authority?.["scope"]).toEqual({ clauses: [] });
  });

  test("on the Write step a missing display name is said in plain words, beside the field, and nothing is sent", async () => {
    // What breaks if this is deleted: "must have required property 'Display Name'", the validator's
    // sentence the owner met, or a save sent that the API then refuses. The positive half is the test
    // above, where the same form saves.
    const { container, idp } = await consoleAt(draftAddress(DRAFT_ID, "write"), {
      [`GET ${DRAFT_API}`]: { body: aDraft() },
      "GET /api/v1/builder/form": { body: FORM },
    });
    fireEvent.change(screen.getByLabelText(/^Display name/), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name and summary" }));

    await waitFor(() => {
      expect(document.getElementById("identity_identity_display_name__error")?.textContent).toBe("Enter the display name.");
    });
    const region = container.querySelector('section[data-section="identity"]') as HTMLElement;
    expect(within(region).getByText(CHECK_THESE_ANSWERS)).toBeDefined();
    expect(screen.getByLabelText(/^Display name/).getAttribute("aria-invalid")).toBe("true");
    expect(container.textContent).not.toMatch(/required property|ManifestIdentity|Display Name|Submit/);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("on the Procedure step with no tool allowed, the note sends the person to the section and list the Write step has", async () => {
    // What breaks if this is deleted: the note pointing at "Permissions", which is not a step or a
    // section anywhere, so a person with no tool allowed had nowhere to go. The words are held to the
    // served form, so renaming the section there fails here rather than leaving the note stale.
    const tools = (FORM as { sections: { section: string; title: string; ui: Record<string, Record<string, Record<string, unknown>>> }[] }).sections.find(
      (one) => one.section === "tools",
    );
    expect(tools?.title).toBe(TOOLS_SECTION_HEADING);
    expect(tools?.ui["authority"]?.["allowed_tools"]?.["ui:title"]).toBe(TOOLS_LIST_LABEL);

    const { container } = await consoleAt(draftAddress(DRAFT_ID, "procedure"), { [`GET ${DRAFT_API}`]: { body: aDraft() } });
    expect(container.textContent).toContain(NO_TOOLS_TO_DRAW);
    expect(container.textContent).not.toContain("Permissions first");
    const link = screen.getByRole("link", { name: OPEN_WRITE_STEP });
    expect(link.getAttribute("href")).toBe(draftAddress(DRAFT_ID, "write"));
  });

  test("on the Procedure step each Add button is found by its name, a step is added, and a missing name is said in plain words", async () => {
    // What breaks if this is deleted: a procedure that cannot be drawn, buttons named in the server's
    // vocabulary ("Add tool_call"), or a Write button that will not press and says nothing about why.
    // The sibling at the end is the same form answered, which is confirmed and sent.
    const { idp } = await consoleAt(draftAddress(DRAFT_ID, "procedure"), {
      [`GET ${DRAFT_API}`]: { body: aDraft({ drawable_tools: ["helpdesk.read_ticket"] }) },
      [`POST ${DRAFT_API}/procedure`]: { body: { skill: "---\nname: look-up\n---\n" } },
    });
    for (const kind of ADDABLE_KINDS) {
      expect(screen.getByRole("button", { name: ADD_WORDS[kind] })).toBeDefined();
    }
    fireEvent.click(screen.getByRole("button", { name: ADD_WORDS.tool_call }));
    expect(screen.getByRole("button", { name: "Remove step_1" })).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: DRAW_LABEL }));
    expect(screen.getByText(ENTER_SKILL_NAME)).toBeDefined();
    expect(screen.getByText(ENTER_WHEN_TO_USE)).toBeDefined();
    expect(screen.getByLabelText(PROCEDURE_NAME).getAttribute("aria-invalid")).toBe("true");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(idp)).toEqual([]);

    fireEvent.change(screen.getByLabelText(PROCEDURE_NAME), { target: { value: "look-up" } });
    fireEvent.change(screen.getByLabelText(PROCEDURE_DESCRIPTION), { target: { value: "Use when somebody asks." } });
    expect(screen.queryByText(ENTER_SKILL_NAME)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: DRAW_LABEL }));
    await confirmIn(DRAW_QUESTION, DRAW_LABEL);
    const [sent] = posts(idp);
    expect(sent?.path).toBe(`${DRAFT_API}/procedure`);
    expect(sent?.body).toMatchObject({ name: "look-up", description: "Use when somebody asks." });
  });

  test("a check is confirmed and draws what the API said in its words", async () => {
    // What breaks if this is deleted: a check sent on one press, or a result whose problems are not
    // drawn, so the person presses publish on a draft that cannot pass.
    const { idp } = await consoleAt(draftAddress(DRAFT_ID, "check"), {
      [`GET ${DRAFT_API}`]: { body: aDraft() },
      [`POST ${DRAFT_API}/check`]: {
        body: {
          revision: 2,
          passed: false,
          problems: ["Instructions: this draft needs instructions."],
          missing: [],
          company_details: [],
          widened: ["read:invoice.reference"],
          second_person_needed: true,
        },
      },
    });
    fireEvent.click(button(CHECK_LABEL));
    await confirmIn(CHECK_QUESTION, CHECK_LABEL);
    expect(posts(idp)).toEqual([{ path: `${DRAFT_API}/check`, body: { revision: 2 } }]);
    await waitFor(() => {
      expect(document.body.textContent).toContain("Instructions: this draft needs instructions.");
      expect(document.body.textContent).toContain("read:invoice.reference");
    });
  });

  test("publishing is confirmed and names the version checked and who can find the new agent", async () => {
    // What breaks if this is deleted: a publish of a version the person was not looking at, or of a
    // new agent to an audience nobody chose.
    const { idp } = await consoleAt(draftAddress(DRAFT_ID, "publish"), {
      [`GET ${DRAFT_API}`]: { body: aDraft({ state: "checked" }) },
      [`POST ${DRAFT_API}/publish`]: {
        status: 202,
        body: { state: "waiting", agent_id: "invoice_helper_ab12cd", sentence: "It waits for a second person.", widened: [] },
      },
    });
    fireEvent.click(screen.getByRole("radio", { name: "My department" }));
    fireEvent.click(button(PUBLISH_LABEL));
    await confirmIn(PUBLISH_QUESTION("Invoice helper"), PUBLISH_LABEL);

    expect(posts(idp)).toEqual([{ path: `${DRAFT_API}/publish`, body: { revision: 2, for_department: true, web: true } }]);
    await waitFor(() => {
      expect(document.body.textContent).toContain("It waits for a second person.");
    });
  });

  test("a new agent answers on the web page unless its author unticks it before publishing", async () => {
    // What breaks if this is deleted: M39.2.4.1's create flow, where the web page is ticked where the
    // author can see it and the untick is what the publish carries.
    const { idp } = await consoleAt(draftAddress(DRAFT_ID, "publish"), {
      [`GET ${DRAFT_API}`]: { body: aDraft({ state: "checked" }) },
      [`POST ${DRAFT_API}/publish`]: {
        status: 201,
        body: { state: "published", agent_id: "invoice_helper_ab12cd", sentence: "Published.", widened: [] },
      },
    });
    const web = screen.getByRole("checkbox", { name: ON_THE_WEB_PAGE });
    expect((web as HTMLInputElement).checked).toBe(true);
    fireEvent.click(web);
    fireEvent.click(button(PUBLISH_LABEL));
    await confirmIn(PUBLISH_QUESTION("Invoice helper"), PUBLISH_LABEL);

    expect(posts(idp)).toEqual([{ path: `${DRAFT_API}/publish`, body: { revision: 2, for_department: false, web: false } }]);
  });

  test("on an install that cannot publish, Publish is inert with the API's reason", async () => {
    // What breaks if this is deleted: a Publish button that is pressed and refused every time, which
    // is fake functionality, on every install that holds no template signing key.
    const reason = "Installing and duplicating are unavailable on this install: it holds no template signing key yet.";
    const { container, idp } = await consoleAt(draftAddress(DRAFT_ID, "publish"), {
      [`GET ${DRAFT_API}`]: { body: aDraft({ publish_unavailable: reason }) },
    });
    const inert = container.querySelector<HTMLElement>(`[${UNAVAILABLE_MARK}]`);
    expect(inert?.textContent).toContain(PUBLISH_LABEL);
    expect(document.getElementById(inert?.getAttribute("aria-describedby") ?? "")?.textContent).toBe(reason);
    fireEvent.click(inert as HTMLElement);
    expect(posts(idp)).toEqual([]);
  });

  test("the second person sees what it adds and approves it through a confirmation", async () => {
    // What breaks if this is deleted: M27.15.31's approval reached by nobody, or pressed without the
    // widening in front of the person approving it.
    const { idp } = await consoleAt(draftAddress(DRAFT_ID, "publish"), {
      [`GET ${DRAFT_API}`]: {
        body: aDraft({ state: "waiting", yours: false, waiting_on_you: true, widened: ["read:invoice.reference"] }),
      },
      [`POST ${DRAFT_API}/approve`]: {
        status: 201,
        body: { state: "published", agent_id: "invoice_helper_ab12cd", sentence: "Published.", widened: [] },
      },
    });
    expect(document.body.textContent).toContain("read:invoice.reference");
    fireEvent.click(button(APPROVE_LABEL));
    await confirmIn(APPROVE_QUESTION("Invoice helper"), APPROVE_LABEL);
    expect(posts(idp)).toEqual([{ path: `${DRAFT_API}/approve`, body: { revision: 2 } }]);
  });
});

// ------------------------------------------------------------------------------ the ways in
describe("the ways in", () => {
  test("Edit as a draft on an agent's page is confirmed and starts a draft of that agent", async () => {
    // What breaks if this is deleted: the Edit as a draft the owner asked for, drawn and inert, or
    // pressed without saying the agent keeps working until the draft is published.
    const { idp, router } = await consoleAt("/agents/quote_helper/profile", {
      "GET /api/v1/agents/quote_helper/workspace": {
        body: {
          agent: { agent_id: "quote_helper", display_name: "Quote Helper", owner_id: "p_1" },
          tabs: [{ tab: "settings", label: "Settings", purpose: "x" }],
          composition: [],
          profile: { tier: "main", audience_level: "personal", tools: [], leash: [] },
        },
      },
      "POST /api/v1/agents/quote_helper/drafts": { status: 201, body: aDraft({ kind: "edit" }) },
      [`GET ${DRAFT_API}`]: { body: aDraft({ kind: "edit" }) },
      "GET /api/v1/builder/form": { body: FORM },
    });
    const menu = screen.getByRole("button", { name: "Agent settings" });
    menu.focus();
    await act(async () => {
      fireEvent.keyDown(menu, { key: "Enter" });
    });
    const item = within(await screen.findByRole("menu")).getByRole("menuitem", { name: EDIT_AS_DRAFT });
    item.focus();
    await act(async () => {
      fireEvent.keyDown(item, { key: "Enter" });
    });
    await confirmIn(EDIT_QUESTION("Quote Helper"), START_LABEL);

    expect(posts(idp)).toEqual([{ path: "/api/v1/agents/quote_helper/drafts", body: {} }]);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(draftAddress(DRAFT_ID));
    });
  });

  test("Approvals lists the publishes waiting for the reader, and nothing for a reader the API refuses", async () => {
    // What breaks if this is deleted: M27.15.31's queue drawn nowhere, or a refusal drawn on the
    // Approvals page for a reader who may not make agents at all.
    const waiting = {
      items: [],
      waiting_for_you: [{ draft_id: DRAFT_ID, agent_id: "a_1", name: "Invoice helper", kind: "new", state: "waiting", revision: 2 }],
    };
    const queue = { items: [], next_cursor: null, truncated: false };
    const shown = await consoleAt("/approvals", {
      "GET /api/v1/approvals": { body: queue },
      "GET /api/v1/agent-drafts": { body: waiting },
    });
    await waitFor(() => {
      expect(shown.container.textContent).toContain(WAITING_PUBLISHES_HEADING);
    });
    const link = [...shown.container.querySelectorAll("a")].find((one) => one.textContent === "Invoice helper");
    expect(link?.getAttribute("href")).toBe(draftAddress(DRAFT_ID, "publish"));
    shown.container.remove();

    const refused = await consoleAt("/approvals", {
      "GET /api/v1/approvals": { body: queue },
      "GET /api/v1/agent-drafts": { status: 404, body: { outcome: "absent", message: "I could not find that." } },
    });
    await waitFor(() => {
      expect(refused.idp.urls.some((url) => url.includes("/agent-drafts"))).toBe(true);
    });
    expect(refused.container.textContent).not.toContain(WAITING_PUBLISHES_HEADING);
    expect(refused.container.textContent).not.toContain("I could not find that.");
  });

  test("the draft that merges a section keeps what another section set", () => {
    // What breaks if this is deleted: the tools section's save wiping the rows the knowledge section
    // set, because both declare part of one object.
    const held = { authority: { scope: { clauses: [{ field: "department" }] }, capabilities: [] }, persona: "a" };
    expect(withSection(held, { authority: { capabilities: [{ value: "read:x" }] } })).toEqual({
      authority: { scope: { clauses: [{ field: "department" }] }, capabilities: [{ value: "read:x" }] },
      persona: "a",
    });
    expect(withSection(held, { persona: "b" })).toEqual({ ...held, persona: "b" });
  });
});
