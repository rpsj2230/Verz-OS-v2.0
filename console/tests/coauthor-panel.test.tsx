/**
 * The co-author on a draft's Write step: asking, seeing each change as before and after, and taking
 * the ones the author ticks.
 *
 * Mounted through the application's own route table and answered by a stand-in API that records every
 * request. What is held: asking is confirmed and says where the words go before they go; nothing is
 * ticked for the author and taking waits for a tick; taking sends the proposal as drawn with exactly
 * the paths ticked; a refusal is the API's own sentence; and dropping the suggestions sends nothing.
 *
 * Task ids: M20.1.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { draftAddress } from "../src/pages/agents/agentDraftsQuery";
import {
  ASK_CONSEQUENCE,
  ASK_NEEDED,
  ASK_QUESTION,
  readSuggestion,
  suggestApiPath,
  suggestedWords,
  TAKE_QUESTION,
  takeApiPath,
  takeBody,
} from "../src/pages/agents/agentCoauthorQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";
import { readConsoleFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const DRAFT_ID = "44444444-4444-4444-8444-444444444444";
const FORM = JSON.parse(readConsoleFile("tests/fixtures/manifest-form.json")) as unknown;

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/AgentDraft");
}, 60_000);

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

function aDraft(): Record<string, unknown> {
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
    channels: [],
    channels_note: "x",
  };
}

function suggestionWire(): Record<string, unknown> {
  return {
    revision: 2,
    base_digest: "d".repeat(64),
    hunks: [
      { path: "persona", where: "Instructions", before: JSON.stringify("Answer briefly."), after: JSON.stringify("Answer in one short sentence.") },
      { path: "identity.summary", where: "Name and summary, summary", before: null, after: JSON.stringify("Reads invoices.") },
    ],
    dropped: [{ path: "authority.capabilities", message: "The co-author may not change what an agent may reach." }],
    note: "A suggestion is not a change until you take it.",
  };
}

async function writeStep(answers: Readonly<Record<string, Answer>>): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const answer = answers[`${init?.method ?? "GET"} ${new URL(url, CONSOLE_ORIGIN).pathname}`];
      return answer === undefined
        ? null
        : new Response(JSON.stringify(answer.body), { status: answer.status ?? 200, headers: { "content-type": "application/json" } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [draftAddress(DRAFT_ID, "write")] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector('[data-slot="coauthor"]')) {
      throw new Error("the co-author has not arrived");
    }
  });
  return { container, idp };
}

function answers(extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`GET /api/v1/agent-drafts/${DRAFT_ID}`]: { body: aDraft() },
    "GET /api/v1/builder/form": { body: FORM },
    ...extra,
  };
}

function posts(idp: FakeIdp): { readonly path: string; readonly body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/v1/"))
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: JSON.parse(String(call.init?.body ?? "null")) }));
}

async function confirmIn(question: string, label: string): Promise<void> {
  const dialog = await screen.findByRole("alertdialog");
  expect(within(dialog).getByText(question)).toBeDefined();
  await act(async () => {
    fireEvent.click(within(dialog).getByRole("button", { name: label }));
  });
}

async function askFor(container: HTMLElement, words: string): Promise<void> {
  await act(async () => {
    fireEvent.change(container.querySelector('[data-slot="coauthor"] textarea') as Element, { target: { value: words } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  });
}

describe("the co-author on the Write step", () => {
  test("a blank request says what is needed and sends nothing, and a request is confirmed with where the words go", async () => {
    // What breaks if this is deleted: a model call made with a blank request, or one made without
    // the author being told that their draft is sent to a provider.
    const { container, idp } = await writeStep(answers({ [`POST /api/v1${suggestApiPath(DRAFT_ID)}`]: { body: suggestionWire() } }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    });
    expect(container.textContent).toContain(ASK_NEEDED);
    expect(posts(idp)).toEqual([]);

    await askFor(container, "make the instructions shorter");
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(ASK_QUESTION)).toBeDefined();
    expect(within(dialog).getByText(ASK_CONSEQUENCE)).toBeDefined();
    expect(posts(idp)).toEqual([]);
    await confirmIn(ASK_QUESTION, "Ask");
    expect(posts(idp)).toEqual([
      { path: `/api/v1${suggestApiPath(DRAFT_ID)}`, body: { revision: 2, ask: "make the instructions shorter" } },
    ]);
  });

  test("each change is drawn before and after and unticked, and what could not be proposed is said", async () => {
    // What breaks if this is deleted: a change chosen for the author, a change drawn without what it
    // replaces, or a refused change that disappears without a word.
    const { container } = await writeStep(answers({ [`POST /api/v1${suggestApiPath(DRAFT_ID)}`]: { body: suggestionWire() } }));
    await askFor(container, "shorter");
    await confirmIn(ASK_QUESTION, "Ask");
    const panel = await waitFor(() => {
      const found = container.querySelector('[data-slot="coauthor-suggestion"]');
      if (found === null) {
        throw new Error("no suggestion yet");
      }
      return found as HTMLElement;
    });
    const boxes = [...panel.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')];
    expect(boxes).toHaveLength(2);
    expect(boxes.every((one) => !one.checked)).toBe(true);
    expect(panel.textContent).toContain("Answer briefly.");
    expect(panel.textContent).toContain("Answer in one short sentence.");
    expect(panel.textContent).toContain("Instructions");
    expect(panel.textContent).toContain("The co-author may not change what an agent may reach.");
    expect(screen.getByRole("button", { name: "Take the chosen changes" }).hasAttribute("disabled")).toBe(true);
  });

  test("taking sends the proposal as it was drawn with exactly the ticked paths, and only after a confirmation", async () => {
    // What breaks if this is deleted: taking all of a proposal, or taking without asking, or a
    // proposal sent back altered from the one the API drew.
    const { container, idp } = await writeStep(
      answers({
        [`POST /api/v1${suggestApiPath(DRAFT_ID)}`]: { body: suggestionWire() },
        [`POST /api/v1${takeApiPath(DRAFT_ID)}`]: { body: { revision: 3, state: "draft", problems: [] } },
      }),
    );
    await askFor(container, "shorter");
    await confirmIn(ASK_QUESTION, "Ask");
    const panel = await waitFor(() => {
      const found = container.querySelector('[data-slot="coauthor-suggestion"]');
      if (found === null) {
        throw new Error("no suggestion yet");
      }
      return found as HTMLElement;
    });
    await act(async () => {
      fireEvent.click(panel.querySelectorAll('input[type="checkbox"]')[0] as Element);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Take the chosen changes" }));
    });
    expect(posts(idp)).toHaveLength(1);
    await confirmIn(TAKE_QUESTION, "Take the chosen changes");

    const sent = posts(idp)[1];
    expect(sent?.path).toBe(`/api/v1${takeApiPath(DRAFT_ID)}`);
    expect(sent?.body).toEqual({
      revision: 2,
      base_digest: "d".repeat(64),
      hunks: [
        { path: "persona", before: JSON.stringify("Answer briefly."), after: JSON.stringify("Answer in one short sentence.") },
        { path: "identity.summary", before: null, after: JSON.stringify("Reads invoices.") },
      ],
      take: ["persona"],
    });
    await waitFor(() => {
      expect(container.querySelector('[data-slot="coauthor-suggestion"]')).toBeNull();
    });
  });

  test("a refusal is the API's own sentence and nothing is drawn as a suggestion", async () => {
    // What breaks if this is deleted: a 409 drawn as success, or a sentence nobody sent.
    const sentence = "This draft was saved again after you opened it, so nothing was saved.";
    const { container, idp } = await writeStep(
      answers({
        [`POST /api/v1${suggestApiPath(DRAFT_ID)}`]: { status: 409, body: { outcome: "moved", sentence } },
      }),
    );
    await askFor(container, "shorter");
    await confirmIn(ASK_QUESTION, "Ask");
    await waitFor(() => {
      expect(container.textContent).toContain(sentence);
    });
    expect(container.querySelector('[data-slot="coauthor-suggestion"]')).toBeNull();
    expect(posts(idp)).toHaveLength(1);
  });

  test("dropping the suggestions removes them and sends nothing, because rejecting writes nothing", async () => {
    // What breaks if this is deleted: a drop that writes, or suggestions that stay after the author
    // has said no to them.
    const { container, idp } = await writeStep(answers({ [`POST /api/v1${suggestApiPath(DRAFT_ID)}`]: { body: suggestionWire() } }));
    await askFor(container, "shorter");
    await confirmIn(ASK_QUESTION, "Ask");
    await waitFor(() => {
      expect(container.querySelector('[data-slot="coauthor-suggestion"]')).not.toBeNull();
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Drop these suggestions" }));
    });
    expect(container.querySelector('[data-slot="coauthor-suggestion"]')).toBeNull();
    expect(posts(idp)).toHaveLength(1);
  });

  test("the routes are declared, a half-sent suggestion is left out, and values read as words", () => {
    // What breaks if this is deleted: a path spelled differently from the route, a change with no
    // value treated as a proposal, or a value drawn as raw JSON.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toEqual(
      expect.arrayContaining(["/api/v1/agent-drafts/{draft_id}/suggestions", "/api/v1/agent-drafts/{draft_id}/suggestions/take"]),
    );
    const read = readSuggestion({ ...suggestionWire(), hunks: [{ path: "persona" }, ...(suggestionWire()["hunks"] as unknown[])] });
    expect(read?.changes.map((one) => one.path)).toEqual(["persona", "identity.summary"]);
    expect(readSuggestion({ revision: 2 })).toBeNull();
    expect(takeBody(read as NonNullable<typeof read>, ["persona"])["take"]).toEqual(["persona"]);
    expect(suggestedWords(JSON.stringify(["a", "b"]))).toBe("a, b");
    expect(suggestedWords(null)).toBe("nothing");
    expect(suggestedWords(JSON.stringify(""))).toBe("nothing");
  });
});
