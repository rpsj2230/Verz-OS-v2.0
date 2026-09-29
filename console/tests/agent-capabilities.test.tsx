/**
 * One agent's Profile drawn from its capability detail: connectors with their icons, health and the
 * fields they project, skills with their version, review and runs and the library's offers, the
 * knowledge the agent draws on as a predicate, who can find it, and a preview of one person's run.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that records
 * every request, as `agent-page.test.tsx` mounts it, so a deleted route or reader fails here.
 *
 * **Every absence has a sibling**: a block the detail did not send is not drawn, and the same block
 * is drawn when it is sent; an offer that may only be reviewed carries no attach button.
 *
 * Task ids: M39.2.1.1, M39.2.1.3, M39.2.1.4, M39.2.1.5, M39.2.2.1, M39.2.2.2, M39.2.2.3, M39.2.2.4
 * Task ids: M39.2.3.1, M39.2.3.3, M39.2.3.4, M39.3.1.1, M39.3.1.3, M39.3.1.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ADD_SKILL, CONNECTORS_ON_THE_ROW, KNOWLEDGE_HEADING, PREVIEW_NEEDED, monogram } from "../src/pages/agents/AgentCapabilities";
import { agentCapabilitiesApiPath, agentPreviewApiPath, readAgentCapabilities, skillAssignApiPath } from "../src/pages/agents/agentCapabilitiesQuery";
import { agentStatsApiPath } from "../src/pages/agents/agentStats";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";
const PROFILE = `/agents/${AGENT}/profile`;
const DIGEST_A = "a".repeat(64);
const DIGEST_B = "b".repeat(64);
const DIGEST_C = "c".repeat(64);

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

// ------------------------------------------------------------------------------- fixtures

function workspaceWire(): unknown {
  return {
    agent: {
      agent_id: AGENT,
      display_name: "Quote Helper",
      owner_id: "p_steward_one",
      owner_name: "Steward One",
      state: "enabled",
      created_at: "2019-03-01T09:00:00Z",
    },
    tabs: [{ tab: "settings", label: "settings", purpose: "Settings." }],
    composition: [],
    skills: [],
    connectors: { shown: [], overflow: 0 },
    channels: [],
    headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false },
    profile: {
      tier: "main",
      model_pin_provider: null,
      model_pin_model: null,
      audience_level: "department",
      ceiling: {
        rows: "price lists in the sales department",
        reads: [],
        reads_locked: false,
        tools: "It can read a price list.",
        largest_effect: "It reads and changes nothing.",
        max_side_effect: "none",
      },
      tools: [],
      leash: [],
    },
  };
}

function connectors(count: number): unknown[] {
  return Array.from({ length: count }, (_, n) => ({
    source: `source${String(n)}`,
    presence: n === 1 ? "requested" : "attached",
    projects: n === 0 ? ["ticket.subject", "ticket.status"] : [],
    health: n === 0 ? "degraded" : null,
    checked_at: n === 0 ? "2019-03-04T09:00:00Z" : null,
  }));
}

function detailWire(extra: Record<string, unknown> = {}): unknown {
  return {
    agent_id: AGENT,
    availability: {
      level: "department",
      department: "sales",
      owner_id: "p_steward_one",
      reader_is_included: true,
      words: "Who can find and start an agent is not what it may reach.",
    },
    connectors: connectors(CONNECTORS_ON_THE_ROW + 2),
    skills: [
      { name: "quote-draft", digest: DIGEST_A, version: "1.2.0", source: "upload", review: "approved", runs: 7, detachable: true },
      { name: "shipped-skill", digest: DIGEST_B, version: null, source: null, review: null, runs: 0, detachable: false },
    ],
    unused_skills: ["shipped-skill"],
    usage_basis: "everyone",
    skills_editable: true,
    offers: [
      { name: "spare-skill", version: "2.0.0", digest: DIGEST_C, review: "approved", control: "attach", route: "" },
      { name: "waiting-skill", version: "0.1.0", digest: "d".repeat(64), review: "pending", control: "review", route: "/skills/waiting-skill" },
    ],
    knowledge: { clauses: [{ field: "department", op: "eq", value: "sales" }], matched: 5, verified: 3, stale: 1, unverified: 1, at_least: false },
    ...extra,
  };
}

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
}

async function consoleAt(path: string, answers: Readonly<Record<string, Answer>>): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const answer = answers[`${method} ${pathname}`] ?? (method === "GET" ? answers[pathname] : undefined);
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200, headers: { "content-type": "application/json" } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector('[data-slot="agent-profile"]')) {
      throw new Error("the Profile has not arrived");
    }
  });
  return { container, idp };
}

/** The writes the page sent to the API, leaving out the identity provider's own token requests. */
function apiPosts(idp: FakeIdp): FakeIdp["calls"] {
  return idp.calls.filter((one) => one.init?.method === "POST" && one.url.includes("/api/v1/"));
}

function answers(detail: unknown = detailWire(), extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`/api/v1${agentCapabilitiesApiPath(AGENT)}`]: { body: detail },
    [`/api/v1${agentStatsApiPath(AGENT)}`]: { body: { agent_id: AGENT, periods: [], unrecorded: [] } },
    "/api/v1/routing/rungs": { body: { items: [], next_cursor: null, truncated: false } },
    ...extra,
  };
}

async function drawn(container: HTMLElement, slot: string): Promise<Element> {
  return waitFor(() => {
    const found = container.querySelector(`[data-slot="${slot}"]`);
    if (found === null) {
      throw new Error(`nothing drawn at ${slot}`);
    }
    return found;
  });
}

// ------------------------------------------------------------------------------ connectors

describe("connectors", () => {
  test("each connector is drawn with its own monogram, the row holds five and the rest open as the reader's own", async () => {
    // What breaks if this is deleted: M39.2.1.1's icons and overflow, or an overflow that opens
    // something other than the rows it counted.
    const mounted = await consoleAt(PROFILE, answers());
    const row = await drawn(mounted.container, "connector-detail");
    expect(row.querySelectorAll('[data-slot="chip"]').length).toBe(CONNECTORS_ON_THE_ROW);
    expect(row.textContent).toContain(monogram("source0"));
    const more = [...row.querySelectorAll("button")].find((one) => one.textContent === "2 more") as Element;
    await act(async () => {
      fireEvent.click(more);
    });
    expect(row.querySelectorAll('[data-slot="chip"]').length).toBe(CONNECTORS_ON_THE_ROW + 2);
  });

  test("a requested connector says so, a probed one carries the Connectors page's health, and fields are listed", async () => {
    // What breaks if this is deleted: M39.2.1.4's requested state, M39.2.1.5's inherited health and
    // M39.2.1.3's projected fields, each of which is sent and could be dropped on the way.
    const mounted = await consoleAt(PROFILE, answers());
    const row = await drawn(mounted.container, "connector-detail");
    expect(row.textContent).toContain("source1 · requested");
    expect(row.textContent).toContain("source0 · Degraded");
    expect((await drawn(mounted.container, "connector-fields")).textContent).toContain("ticket.subject, ticket.status");
  });
});

// ------------------------------------------------------------------------------ skills

describe("skills", () => {
  test("a chip carries the version, the review and the runs, and a template's own skill carries only its name", async () => {
    // What breaks if this is deleted: M39.2.2.1's version and review, and M39.2.2.4's runs, which
    // are the pruning signal.
    const mounted = await consoleAt(PROFILE, answers());
    const chips = [...(await drawn(mounted.container, "skill-detail")).querySelectorAll('[data-slot="skill-chip"]')];
    expect(chips[0]?.textContent).toContain("1.2.0");
    expect(chips[0]?.textContent).toContain("Approved");
    expect(chips[0]?.textContent).toContain("7 runs");
    expect(chips[1]?.querySelector('[data-slot="review-pill"]')).toBeNull();
    expect(mounted.container.textContent).toContain("Not used in that time: shipped-skill.");
  });

  test("an approved library skill is offered to attach, confirmed first, and an unreviewed one only as a link to its review", async () => {
    // What breaks if this is deleted: M39.2.2.2 and M39.2.2.3, an unreviewed skill one press from an
    // agent, or an attach sent without the confirmation naming it.
    const mounted = await consoleAt(PROFILE, {
      ...answers(),
      [`POST /api/v1${skillAssignApiPath(DIGEST_C)}`]: { body: { agent_id: AGENT } },
    });
    const detail = await drawn(mounted.container, "skill-detail");
    const opener = [...detail.querySelectorAll("button")].find((one) => one.textContent?.includes(ADD_SKILL)) as Element;
    await act(async () => {
      fireEvent.click(opener);
    });
    const offers = await drawn(mounted.container, "skill-offers");
    const [spare, waiting] = [...offers.querySelectorAll("li")];
    expect(waiting?.querySelector("button")).toBeNull();
    expect(waiting?.querySelector("a")?.getAttribute("href")).toBe("/skills/waiting-skill");
    await act(async () => {
      fireEvent.click(spare?.querySelector("button") as Element);
    });
    expect(apiPosts(mounted.idp)[0]).toBeUndefined();
    const dialog = document.querySelector('[role="alertdialog"]') as Element;
    expect(dialog.textContent).toContain("spare-skill 2.0.0");
    await act(async () => {
      fireEvent.click([...dialog.querySelectorAll("button")].find((one) => one.textContent === "Attach") as Element);
    });
    const posted = apiPosts(mounted.idp)[0];
    expect(posted?.url).toContain(skillAssignApiPath(DIGEST_C));
    expect(JSON.parse(String(posted?.init?.body))).toEqual({ agent_id: AGENT });
  });

  test("a reader the detail sends no skills is shown no skill block and no offers", async () => {
    // The sibling: a block with a heading and nothing under it is a count of hidden things.
    const mounted = await consoleAt(PROFILE, answers(detailWire({ skills: [], offers: [], unused_skills: [], connectors: [] })));
    await drawn(mounted.container, "agent-profile");
    expect(mounted.container.querySelector('[data-slot="skill-detail"]')).toBeNull();
  });
});

// ------------------------------------------------------------------------------ knowledge and who

describe("knowledge and availability", () => {
  test("knowledge is drawn as the predicate in words, with the reader's own counts", async () => {
    // What breaks if this is deleted: M39.2.3.1's predicate, M39.2.3.3's preview count and
    // M39.2.3.4's coverage and staleness.
    const mounted = await consoleAt(PROFILE, answers());
    expect((await drawn(mounted.container, "knowledge-predicate")).textContent).toBe("It draws on documents in the sales department.");
    const slice = await drawn(mounted.container, "knowledge-slice");
    expect([...slice.querySelectorAll("dd")].map((one) => one.textContent)).toEqual(["5", "3", "1", "1"]);
  });

  test("with no knowledge sent there is no Knowledge card, and a reader outside the audience is told so", async () => {
    // The siblings: the card is drawn only from what was sent, and M39.3.1.1's audience answer
    // reaches the reader in both directions.
    const outside = detailWire({
      knowledge: null,
      availability: { level: "department", department: "sales", owner_id: "p", reader_is_included: false, words: "x" },
    });
    const mounted = await consoleAt(PROFILE, answers(outside));
    await drawn(mounted.container, "connector-detail");
    expect([...mounted.container.querySelectorAll("h2, h3")].map((one) => one.textContent)).not.toContain(KNOWLEDGE_HEADING);
    expect(mounted.container.textContent).toContain("You are not among the people who can find it.");
  });

  test("a reader in the audience is told they can find it, beside the sentence that finding it gives no access", async () => {
    // What breaks if this is deleted: M39.3.1.3's sentence, or the audience answer, dropped.
    const mounted = await consoleAt(PROFILE, answers());
    await drawn(mounted.container, "connector-detail");
    expect(mounted.container.textContent).toContain("You can find and start it.");
    expect(mounted.container.textContent).toContain("This never gives anybody access to more information.");
  });
});

// ------------------------------------------------------------------------------ the preview

describe("the preview", () => {
  test("the preview says what it takes, refuses a blank without sending, and draws the person's run", async () => {
    // What breaks if this is deleted: M39.3.1.4's preview never reaching the page, or a blank sent.
    const preview = { person_id: "p_one", person_name: "Person One", tools: [{ name: "local.read_price_list", description: "Read a price list" }], rung: "shadow", notice: "" };
    const mounted = await consoleAt(PROFILE, { ...answers(), [`POST /api/v1${agentPreviewApiPath(AGENT)}`]: { body: preview } });
    const block = await drawn(mounted.container, "agent-preview");
    const form = block.querySelector("form") as HTMLFormElement;
    await act(async () => {
      fireEvent.submit(form);
    });
    expect(block.querySelector('[role="alert"]')?.textContent).toBe(PREVIEW_NEEDED);
    expect(apiPosts(mounted.idp)[0]).toBeUndefined();
    await act(async () => {
      fireEvent.change(form.querySelector("input") as Element, { target: { value: "p_one" } });
      fireEvent.submit(form);
    });
    const result = await drawn(mounted.container, "preview-result");
    expect(result.textContent).toContain("Person One's run would be handed 1 action, held at Shadow.");
    expect(result.textContent).toContain("Read a price list");
  });

  test("a run that would not start is the one sentence, and a refusal is the API's", async () => {
    // The siblings: nothing reached, and a previewer the API refuses, each in the API's words.
    const nothing = { person_id: "p_two", tools: [], rung: null, notice: "This person's run of this agent would return nothing." };
    const mounted = await consoleAt(PROFILE, { ...answers(), [`POST /api/v1${agentPreviewApiPath(AGENT)}`]: { body: nothing } });
    const block = await drawn(mounted.container, "agent-preview");
    const form = block.querySelector("form") as HTMLFormElement;
    await act(async () => {
      fireEvent.change(form.querySelector("input") as Element, { target: { value: "p_two" } });
      fireEvent.submit(form);
    });
    expect((await drawn(mounted.container, "preview-result")).textContent).toBe("This person's run of this agent would return nothing.");

    const refused = await consoleAt(PROFILE, { ...answers(), [`POST /api/v1${agentPreviewApiPath(AGENT)}`]: { status: 404, body: { message: "I could not find that." } } });
    const again = await drawn(refused.container, "agent-preview");
    const second = again.querySelector("form") as HTMLFormElement;
    await act(async () => {
      fireEvent.change(second.querySelector("input") as Element, { target: { value: "p_two" } });
      fireEvent.submit(second);
    });
    await waitFor(() => {
      expect(again.querySelector('[role="alert"]')?.textContent).toBe("I could not find that.");
    });
  });
});

// ------------------------------------------------------------------------------ the reader

describe("the reader", () => {
  test("every route the page asks is declared, and a body missing its required parts reads as absent", () => {
    // What breaks if this is deleted: a path spelled differently from the route, or a chip drawn
    // from a half-sent row.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toEqual(expect.arrayContaining(["/api/v1/agents/{agent_id}/capabilities", "/api/v1/agents/{agent_id}/preview"]));
    const read = readAgentCapabilities({ connectors: [{ source: "x" }, { source: "y", presence: "attached", health: "ok" }], skills: [{ name: "a" }] });
    expect(read?.connectors).toEqual([{ source: "y", presence: "attached", projects: [] }]);
    expect(read?.skills).toEqual([]);
    expect(readAgentCapabilities("nothing")).toBeNull();
  });
});
