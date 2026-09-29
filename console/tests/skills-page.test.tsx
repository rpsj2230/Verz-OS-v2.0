/**
 * The Skills module on the shared page kit: the searchable library, one skill's Dashboard, Profile
 * and About, and every act on a skill, asserted over the rendered page and over what was sent.
 *
 * **Reachable means through the application's own route table.** Every test mounts `routes` from
 * `src/App.tsx` on a memory router, signed in through the real session modules and answered by a
 * stand-in API, so a test passes only if the address resolves.
 *
 * **Every control is drawn from what the API sent, and every one that changes something is
 * confirmed before it sends.** So the refusals worth testing are the controls that must not be drawn
 * (Add for a reader who may not add) and the writes that must not go before the confirmation; each
 * has a sibling where the control is drawn and the write goes.
 *
 * **The shapes are the API's.** Every field the page reads is compared with the Python model that
 * sends it, and every path it sends to with the API document.
 *
 * Task ids: M27.16.1, M27.11.8, M27.15.55, M27.15.56, M42.6.4, M12.2.2, M12.3.2, M12.4.13,
 * M12.3.4, M12.3.1, M12.4.11
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_RECORDED, UNAVAILABLE_MARK } from "../src/components/kit";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import { SKILLS_HEADING } from "../src/pages/Skills";
import { HISTORY_ELSEWHERE } from "../src/pages/skills/SkillAbout";
import { LAST_USED_LABEL, NOT_USED, RUNS_LABEL } from "../src/pages/skills/SkillDashboard";
import { NO_SUCH_SKILL } from "../src/pages/skills/SkillDetailPage";
import {
  ADD_EXAMPLE,
  ANSWER_EVERY_EXAMPLE,
  BEHAVED,
  DID_NOT_BEHAVE,
  EXAMPLE_EXPECTED_LABEL,
  EXAMPLE_TASK_LABEL,
  PACKAGE_FORMAT,
  RECORD_REHEARSAL,
  SAVE_VERSION,
} from "../src/pages/skills/SkillForms";
import { RETIRE, REINSTATE, DETACH, APPROVE, EXPORT, REHEARSE, REJECT } from "../src/pages/skills/SkillProfile";
import { queueWords, readLibraryRows } from "../src/pages/skills/SkillsPage";
import { REVIEW_PILL, UNAVAILABLE } from "../src/pages/skills/skillActions";
import { readHistory, readSkillDetail } from "../src/pages/skills/skillDetailQuery";
import {
  detachPath,
  exportsPath,
  LIBRARY_API_PATH,
  MAX_PACKAGE_BYTES,
  rehearsalsPath,
  reinstatementPath,
  retirementPath,
  reviewPath,
  skillAddress,
} from "../src/pages/skillsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { apiDocument, declaredParameterSchema, declaredPropertyNames, declaredRequestBodySchema, declaredQueryParameters } from "./support/openapi";
import { backendEnumMembers, backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { extractOne, readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const API = "/api/v1";
const ROUTES = "src/brain/skill_routes.py";
const DIGEST = "a".repeat(64);
const OLDER = "b".repeat(64);
const NAME = "hosting-expiry";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Skill");
}, 60_000);

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly query: string;
  readonly body: unknown;
}

type Answers = Readonly<Record<string, Answer | ((body: unknown) => Answer)>>;

/** Mount the application's own route table at one address, answering `METHOD /api/v1/...`. */
async function consoleAt(path: string, answers: Answers): Promise<{ container: HTMLElement; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const parsed = new URL(url, CONSOLE_ORIGIN);
      const method = (init?.method ?? "GET").toUpperCase();
      const found = answers[`${method} ${parsed.pathname}`];
      if (found === undefined) {
        return null;
      }
      const body: unknown = typeof init?.body === "string" && init.body !== "" ? JSON.parse(init.body) : null;
      sent.push({ method, path: parsed.pathname, query: parsed.search, body });
      const answer = typeof found === "function" ? found(body) : found;
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
  await settled(container);
  return { container, sent };
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
}

/** One version as `brain.skill_routes.LibrarySkillView` serialises it. */
function version(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    digest: DIGEST,
    name: NAME,
    version: "1.1.0",
    description: "Use when a client asks whether their domain is close to renewal",
    source: "upload",
    source_location: "SKILL.md",
    submitted_by: "u_importer",
    submitted_at: "2019-03-05T09:00:00Z",
    review: "approved",
    reviewer: "u_reviewer",
    reviewed_at: "2019-03-05T10:00:00Z",
    tools: [{ name: "crm.read_client", capability: "read:client.name" }],
    capabilities: ["read:client.name"],
    unregistered_tools: [],
    body: "Look up the domain, then open a ticket.",
    reviewable: false,
    assignable: true,
    source_commit: null,
    source_path: null,
    edited_from: null,
    self_decided: false,
    categories: ["hosting"],
    diff: null,
    markdown: "---\nname: hosting-expiry\n---\n",
    editable: true,
    retired: false,
    retired_at: null,
    retired_by: null,
    retirable: true,
    submitted_by_name: "Iris Importer",
    reviewer_name: "Rex Reviewer",
    scripts: [],
    examples: [],
    rehearsal: null,
    awaits_rehearsal: false,
    approval_needs: null,
    rehearsable: false,
    exportable: false,
    ...overrides,
  };
}

/** What the API says a version with examples still needs, as `approval_needs` sends it. */
const NEEDS_A_REHEARSAL = "hosting-expiry 1.1.0 has not been rehearsed against its example tasks with every one behaving as expected.";

/** What it says of a version with no example tasks at all. */
const NEEDS_EXAMPLES = "hosting-expiry 1.1.0 has no example tasks. Add it again as a .zip holding its SKILL.md and an examples.json.";

/** A waiting version carrying a script and two example tasks, not yet rehearsed (M12.3.4). */
function waitingWithExamples(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return version({
    review: "pending",
    reviewer: null,
    reviewed_at: null,
    reviewer_name: null,
    reviewable: true,
    assignable: false,
    scripts: [{ path: "scripts/check.py", sha256: "c".repeat(64), text: "print('checked')", is_text: true }],
    examples: [
      { task: "A client asks when their domain expires", expected: "Names the expiry date" },
      { task: "A client asks twice", expected: "Answers the same way twice" },
    ],
    awaits_rehearsal: true,
    approval_needs: NEEDS_A_REHEARSAL,
    rehearsable: true,
    ...overrides,
  });
}

/** The Skills page's answer, as `brain.skill_routes.SkillsPage` serialises it. */
function skillsPage(library: Record<string, unknown>[], pins: Record<string, unknown>[] = []): Record<string, unknown> {
  return {
    items: pins.length === 0 ? [] : [{ name: NAME, pinned_by: pins, versions_differ: false, categories: ["hosting"] }],
    next_cursor: null,
    total: null,
    truncated: false,
    queue: { entries: [], waiting: 0, edits: 0, stale: 0 },
    library,
    library_truncated: false,
    agents: [{ agent_id: "company_desk", display_name: "Company Desk" }],
    may_add: true,
    registry_is_absent: false,
    categories: ["hosting"],
  };
}

const PIN = {
  agent_id: "company_desk",
  digest: DIGEST,
  display_name: "Company Desk",
  assigned_at: "2019-03-06T09:00:00Z",
  assigned_by: "Alex Admin",
};

/** The library listing, as `brain.skill_routes.SkillLibraryPage` serialises it. */
function libraryPage(rows: Record<string, unknown>[], extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    items: rows,
    next_cursor: null,
    total: null,
    queue: { entries: [], waiting: 2, edits: 1, stale: 0 },
    library_truncated: false,
    truncated: false,
    may_add: true,
    categories: ["hosting", "billing"],
    ...extra,
  };
}

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    digest: DIGEST,
    name: NAME,
    version: "1.1.0",
    description: "Use when a client asks whether their domain is close to renewal",
    review: "approved",
    retired: false,
    categories: ["hosting"],
    agents_running: 3,
    source: "upload",
    submitted_at: "2019-03-05T09:00:00Z",
    ...overrides,
  };
}

function pressed(label: string, root: ParentNode = document.body): HTMLButtonElement {
  const found = [...root.querySelectorAll<HTMLButtonElement>("button")].find(
    (one) => one.textContent?.trim() === label || (one.getAttribute("aria-label") ?? "").startsWith(label),
  );
  if (found === undefined) {
    throw new Error(`No button named ${label}.`);
  }
  fireEvent.click(found);
  return found;
}

function dialog(): HTMLElement {
  const found = document.querySelector<HTMLElement>('[data-slot="confirm-dialog"]');
  if (found === null) {
    throw new Error("No confirmation is open.");
  }
  return found;
}

// ------------------------------------------------------------------------ what it asks and sends

describe("what the Skills module asks for and sends", () => {
  test("the list asks the library route with parameters it declares and a page size it answers", async () => {
    // What breaks if this is deleted: a parameter the API ignores, read as the narrowing it asked for.
    const declared = new Set(declaredQueryParameters(`${API}${LIBRARY_API_PATH}`, "get"));
    const limit = declaredParameterSchema(`${API}${LIBRARY_API_PATH}`, "get", "limit");
    const { sent } = await consoleAt("/skills", { [`GET ${API}${LIBRARY_API_PATH}`]: { body: libraryPage([row()]) } });

    const asked = sent.filter((one) => one.path === `${API}${LIBRARY_API_PATH}`);
    expect(asked.length).toBeGreaterThan(0);
    expect([...new URLSearchParams(asked[0]?.query).keys()].filter((name) => !declared.has(name))).toEqual([]);
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
  });

  test("every field the pages read is a field the routes declare", () => {
    // What breaks if this is deleted: a renamed field the page goes on reading as empty.
    expect(Object.keys(version()).sort()).toEqual(backendModelFields(ROUTES, "LibrarySkillView").sort());
    expect(Object.keys(row()).sort()).toEqual(backendModelFields(ROUTES, "SkillVersionRowView").sort());
    expect(Object.keys(readLibraryRows({ items: [row()] })[0] ?? {}).sort()).toEqual(Object.keys(row()).sort());
    expect(Object.keys(PIN).sort()).toEqual(backendModelFields(ROUTES, "SkillPinView").sort());
    expect(declaredPropertyNames(declaredRequestBodySchema(`${API}/skills/{digest}/detachments`, "post"))).toEqual(["agent_id"]);
    expect(detachPath(DIGEST)).toBe(`/skills/${DIGEST}/detachments`);
    expect(retirementPath(DIGEST)).toBe(`/skills/${DIGEST}/retirement`);
    expect(reinstatementPath(DIGEST)).toBe(`/skills/${DIGEST}/reinstatement`);
  });

  test("the largest package is the API's figure and every review state has a pill", () => {
    // What breaks if this is deleted: a package the form lets through that the API refuses, or a
    // state drawn as its code.
    const kibibytes = extractOne(readRepoFile("src/brain/console/skill_library.py"), /^MAX_PACKAGE_BYTES: Final = (\d+) \* 1024$/m, "the bound");
    expect(Number(kibibytes) * 1024).toBe(MAX_PACKAGE_BYTES);
    expect(Object.keys(REVIEW_PILL).sort()).toEqual(Object.values(backendEnumMembers("src/brain/console/agent_tabs.py", "Review")).sort());
  });

  test("no act the pages call coming soon has a route in the API document", () => {
    // What breaks if this is deleted: "coming soon" said about an act that has arrived. The positive
    // sibling is that the pattern matches the path it is written for.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    expect(UNAVAILABLE.tryOut.retiredBy.test("/api/v1/skills/{digest}/rehearsal")).toBe(true);
  });

  test("an address this module builds stays inside the console", () => {
    // What breaks if this is deleted: an open redirect through a skill name the API sent.
    for (const name of ["\\\\evil.example", "//evil.example", "http://evil.example"]) {
      expect(skillAddress(name).startsWith("/skills/")).toBe(true);
      expect(skillAddress(name).includes("//")).toBe(false);
    }
  });
});

// --------------------------------------------------------------------------------- the list

describe("the library list", () => {
  test("draws each version with its state, categories and agents, and the queue's own words", async () => {
    // What breaks if this is deleted: the list drawing nothing and every refusal below passing.
    const { container } = await consoleAt("/skills", {
      [`GET ${API}${LIBRARY_API_PATH}`]: { body: libraryPage([row(), row({ digest: OLDER, version: "1.0.0", review: "pending", retired: true, agents_running: 0 })]) },
    });

    expect(container.querySelector("h1")?.textContent).toBe(SKILLS_HEADING);
    const table = container.querySelector('[data-slot="entity-table"]');
    expect(table?.textContent).toContain("1.1.0");
    expect(table?.textContent).toContain("Waiting for review");
    expect(table?.textContent).toContain("Retired");
    expect(container.textContent).toContain(queueWords(2, 1, 0));
    expect(queueWords(2, 1, 0)).toContain("1 of them an edit");
    expect(container.textContent).not.toMatch(/\bof \d+\b/);
  });

  test("a state filter and a category chip each ask the route again with that filter", async () => {
    // What breaks if this is deleted: a filter applied in the browser over whatever arrived.
    const { container, sent } = await consoleAt("/skills", { [`GET ${API}${LIBRARY_API_PATH}`]: { body: libraryPage([row()]) } });

    pressed("billing", container);
    await waitFor(() => {
      expect(sent.some((one) => new URLSearchParams(one.query).getAll("filter").includes("categories:billing"))).toBe(true);
    });
    const state = [...container.querySelectorAll("select")].find((one) => one.labels?.[0]?.textContent === "State");
    fireEvent.change(state as HTMLSelectElement, { target: { value: "approved" } });
    await waitFor(() => {
      expect(sent.some((one) => new URLSearchParams(one.query).getAll("filter").includes("review:approved"))).toBe(true);
    });
  });

  test("adding is offered only to a reader who may add, says its format first and posts a checked paste", async () => {
    // What breaks if this is deleted: an Add button every press of which is refused, or a form
    // that says what it accepts only after refusing it.
    const refused = await consoleAt("/skills", { [`GET ${API}${LIBRARY_API_PATH}`]: { body: libraryPage([row()], { may_add: false }) } });
    expect([...refused.container.querySelectorAll("button")].some((one) => one.textContent?.includes("Add a skill"))).toBe(false);
    refused.container.remove();

    const { container, sent } = await consoleAt("/skills", {
      [`GET ${API}${LIBRARY_API_PATH}`]: { body: libraryPage([row()]) },
      [`POST ${API}/skills`]: { status: 201, body: version({ review: "pending" }) },
    });
    pressed("Add a skill", container);
    await waitFor(() => {
      expect(document.body.textContent).toContain(PACKAGE_FORMAT);
    });
    const add = [...document.querySelectorAll<HTMLButtonElement>("button")].find((one) => one.textContent === "Add to the library");
    expect(add?.disabled).toBe(true);
    fireEvent.change(document.getElementById("skills-paste") as HTMLTextAreaElement, { target: { value: "---\nname: x\n---\n" } });
    expect(add?.disabled).toBe(false);
    fireEvent.click(add as HTMLButtonElement);
    await waitFor(() => {
      expect(sent.some((one) => one.method === "POST" && one.path === `${API}/skills`)).toBe(true);
    });
    await waitFor(() => {
      expect(sent.filter((one) => one.path === `${API}${LIBRARY_API_PATH}`).length).toBeGreaterThan(1);
    });
  });
});

// ------------------------------------------------------------------------------- one skill

function skillAnswers(library: Record<string, unknown>[], pins: Record<string, unknown>[], more: Answers = {}): Answers {
  return { [`GET ${API}/skills`]: { body: skillsPage(library, pins) }, ...more };
}

describe("one skill's page", () => {
  test("the Dashboard draws the stats route's figures and says an unrecorded figure is not recorded", async () => {
    // What breaks if this is deleted: a run count drawn as nought where nothing counts runs.
    const { container } = await consoleAt(skillAddress(NAME), skillAnswers([version()], [PIN], {
      [`GET ${API}/console/skills/${NAME}/stats`]: {
        body: {
          skill_name: NAME,
          agents_pinned: 4,
          pinned_versions: 2,
          versions: 3,
          periods: [{ range: "30d", since: "2019-02-02T00:00:00Z", until: "2019-03-04T00:00:00Z", versions_added: 1 }],
          unrecorded: [{ figure: "runs", why: "nothing writes one" }],
        },
      },
    }));

    await waitFor(() => {
      expect(container.querySelector('[data-slot="stats-strip"], [data-slot="kpi-strip"][aria-label="This skill\'s figures"]')).not.toBeNull();
    });
    const strip = container.querySelector('[aria-label="This skill\'s figures"]');
    expect(strip?.textContent).toContain("4");
    expect(strip?.textContent).toContain(NOT_RECORDED);
    expect([...(strip?.querySelectorAll("dd") ?? [])].map((one) => one.textContent)).not.toContain("0");
  });

  test("the Dashboard draws the runs that used the skill and its last use, with whose runs they are", async () => {
    // What breaks if this is deleted: the route counts a skill's runs and the page still draws
    // "Not recorded yet", or draws them unlabelled for a reader shown only their own runs, or a
    // month with no run reads as a figure nothing records.
    const answered = (lastUsed: string | null) =>
      consoleAt(skillAddress(NAME), skillAnswers([version()], [PIN], {
        [`GET ${API}/console/skills/${NAME}/stats`]: {
          body: {
            skill_name: NAME,
            agents_pinned: 1,
            pinned_versions: 1,
            versions: 1,
            run_basis: "own",
            last_used: lastUsed,
            at_least: false,
            periods: ["7d", "30d"].map((range) => ({
              range,
              since: "2019-02-02T00:00:00Z",
              until: "2019-03-04T00:00:00Z",
              versions_added: 0,
              runs: range === "30d" ? 271 : 3,
            })),
            unrecorded: [],
          },
        },
      }));
    const card = (container: HTMLElement, label: string) =>
      [...container.querySelectorAll('[aria-label="This skill\'s figures"] [data-slot="stat-card"]')].find(
        (one) => one.querySelector("dt")?.textContent === label,
      );

    const used = await answered("2019-03-03T09:00:00Z");
    await waitFor(() => {
      expect(card(used.container, RUNS_LABEL)?.querySelector("dd")?.textContent).toContain("271");
    });
    expect(card(used.container, RUNS_LABEL)?.textContent).toContain("your runs");
    expect(card(used.container, LAST_USED_LABEL)?.textContent).not.toContain(NOT_RECORDED);
    expect(card(used.container, LAST_USED_LABEL)?.textContent).toContain("Mar");

    const unused = await answered(null);
    await waitFor(() => {
      expect(card(unused.container, LAST_USED_LABEL)?.textContent).toContain(NOT_USED);
    });
  });

  test("the Profile names people and agents, and keeps identifiers in Advanced", async () => {
    // What breaks if this is deleted: principal ids back on the page where names belong.
    const { container } = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([version()], [PIN]));

    const page = container.querySelector('[data-slot="skill-profile"]') as HTMLElement;
    expect(page.textContent).toContain("Iris Importer");
    expect(page.textContent).toContain("Company Desk");
    const advanced = page.querySelector('[data-slot="advanced"]') as HTMLElement;
    const outside = page.textContent?.replace(advanced.textContent ?? "", "") ?? "";
    expect(outside).not.toContain("u_importer");
    expect(outside).not.toContain(DIGEST);
    expect(advanced.textContent).toContain("u_importer");
    expect(page.querySelector(`[${UNAVAILABLE_MARK}]`)?.getAttribute("aria-describedby")).not.toBeNull();
  });

  test("retiring is confirmed, then posted, and the agents still running it are named", async () => {
    // What breaks if this is deleted: a retirement sent on one press, or one that says nothing
    // about the agents that keep running the version (M27.15.56).
    const { container, sent } = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([version()], [PIN], {
      [`POST ${API}/skills/${DIGEST}/retirement`]: {
        body: { digest: DIGEST, name: NAME, version: "1.1.0", retired: true, holding: [{ agent_id: "company_desk", display_name: "Company Desk" }] },
      },
    }));

    pressed(RETIRE, container);
    expect(sent.some((one) => one.method === "POST")).toBe(false);
    fireEvent.click(within(dialog()).getByText(RETIRE));
    await waitFor(() => {
      expect(sent.some((one) => one.method === "POST" && one.path === `${API}/skills/${DIGEST}/retirement`)).toBe(true);
    });
    await waitFor(() => {
      expect(container.textContent).toContain("Still running it until you detach it: Company Desk");
    });
  });

  test("a retired version offers reinstating and no assignment", async () => {
    // What breaks if this is deleted: a retired version still offered to new agents on the page.
    const { container } = await consoleAt(
      `${skillAddress(NAME)}/profile`,
      skillAnswers([version({ retired: true, assignable: false, retired_by: "Alex Admin", retired_at: "2019-03-07T09:00:00Z" })], [PIN]),
    );

    expect([...container.querySelectorAll("button")].some((one) => one.textContent === REINSTATE)).toBe(true);
    expect([...container.querySelectorAll("button")].some((one) => one.textContent === RETIRE)).toBe(false);
    expect(container.querySelector('form[aria-label^="Assign"]')).toBeNull();
    expect(container.textContent).toContain("Alex Admin");
  });

  test("detaching from an agent is confirmed with the agent named, then posted with that agent", async () => {
    // What breaks if this is deleted: a skill taken off a live agent on one press (M27.15.55).
    const { container, sent } = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([version()], [PIN], {
      [`POST ${API}/skills/${DIGEST}/detachments`]: {
        status: 201,
        body: { agent_id: "company_desk", skill_name: NAME, digest: DIGEST, effective_hash: "h" },
      },
    }));

    pressed(`${DETACH} ${NAME} from Company Desk`, container);
    expect(dialog().textContent).toContain("Detach hosting-expiry from Company Desk?");
    fireEvent.click(within(dialog()).getByText(DETACH));
    await waitFor(() => {
      expect(sent.find((one) => one.path === `${API}/skills/${DIGEST}/detachments`)?.body).toEqual({ agent_id: "company_desk" });
    });
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "GET" && one.path === `${API}/skills`).length).toBeGreaterThan(1);
    });
  });

  test("approving is offered only where the API says, and is confirmed before it is posted", async () => {
    // What breaks if this is deleted: a decision sent on one press, or buttons every press of which
    // is refused.
    const shut = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([version({ review: "pending", reviewable: false })], []));
    expect([...shut.container.querySelectorAll("button")].some((one) => one.textContent === APPROVE)).toBe(false);
    shut.container.remove();

    const { container, sent } = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([version({ review: "pending", reviewable: true, assignable: false })], [], {
      [`POST ${API}${reviewPath(DIGEST)}`]: { body: version({ review: "approved" }) },
    }));
    pressed(`${APPROVE} ${NAME}`, container);
    expect(sent.some((one) => one.method === "POST")).toBe(false);
    fireEvent.click(within(dialog()).getByText(APPROVE));
    await waitFor(() => {
      expect(sent.find((one) => one.method === "POST")?.body).toEqual({ decision: "approve" });
    });
  });

  test("a version with examples shows them and its script, and offers Reject and no Approve until rehearsed", async () => {
    // What breaks if this is deleted: an Approve button every press of which is refused, or a
    // script approved by somebody the page never showed its code to (M12.3.4, M12.4.11).
    const { container } = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([waitingWithExamples()], []));

    const page = container.querySelector('[data-slot="skill-profile"]') as HTMLElement;
    expect(page.textContent).toContain("A client asks when their domain expires");
    expect(page.textContent).toContain("Names the expiry date");
    expect(page.textContent).toContain("print('checked')");
    expect(page.textContent).toContain(NEEDS_A_REHEARSAL);
    expect([...page.querySelectorAll("button")].some((one) => one.textContent === APPROVE)).toBe(false);
    expect([...page.querySelectorAll("button")].some((one) => one.textContent === REJECT)).toBe(true);
    const advanced = page.querySelector('[data-slot="advanced"]') as HTMLElement;
    expect(advanced.textContent).toContain("c".repeat(64));

    const rehearsed = await consoleAt(
      `${skillAddress(NAME)}/profile`,
      skillAnswers([waitingWithExamples({ awaits_rehearsal: false, approval_needs: null, rehearsal: { behaved: [true, true], passed: true, rehearsed_at: "2019-03-05T11:00:00Z", rehearsed_by: "u_reviewer", rehearsed_by_name: "Rex Reviewer" } })], []),
    );
    expect(rehearsed.container.textContent).toContain("Rehearsed by Rex Reviewer: every example behaved as expected.");
    expect([...rehearsed.container.querySelectorAll("button")].some((one) => one.textContent === APPROVE)).toBe(true);
  });

  test("an edit opens with the version's examples, and one added is sent with the SKILL.md", async () => {
    // What breaks if this is deleted: an edit that drops the examples it did not show, or a
    // pasted skill that no edit can ever give an example to (M12.3.4).
    const { container, sent } = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([waitingWithExamples({ editable: true })], [], {
      [`POST ${API}/skills/${DIGEST}/versions`]: { status: 201, body: waitingWithExamples({ digest: OLDER, version: "1.2.0" }) },
    }));

    pressed(`Edit ${NAME}`, container);
    const form = container.querySelector<HTMLFormElement>(`form[aria-label^="Edit"]`) as HTMLFormElement;
    const tasks = () => [...form.querySelectorAll<HTMLInputElement>('input[name="examples.task"]')];
    expect(tasks().map((one) => one.value)).toEqual(["A client asks when their domain expires", "A client asks twice"]);
    pressed(ADD_EXAMPLE, form);
    const save = [...form.querySelectorAll("button")].find((one) => one.textContent === SAVE_VERSION) as HTMLButtonElement;
    fireEvent.change(within(form).getByLabelText(`${EXAMPLE_TASK_LABEL} 3`), { target: { value: "  A client asks in French  " } });
    expect(save.disabled).toBe(true);
    expect(form.textContent).toContain("Example 3 needs both a task and what is expected");
    const expected = within(form).getAllByLabelText(EXAMPLE_EXPECTED_LABEL)[2] as HTMLInputElement;
    fireEvent.change(expected, { target: { value: "Answers in French" } });
    expect(save.disabled).toBe(false);
    fireEvent.submit(form);
    await waitFor(() => {
      expect((sent.find((one) => one.method === "POST")?.body as { examples: unknown }).examples).toEqual([
        { task: "A client asks when their domain expires", expected: "Names the expiry date" },
        { task: "A client asks twice", expected: "Answers the same way twice" },
        { task: "A client asks in French", expected: "Answers in French" },
      ]);
    });
    expect(declaredPropertyNames(declaredRequestBodySchema(`${API}/skills/{digest}/versions`, "post")).sort()).toEqual(["content", "examples"]);
  });

  test("a pasted SKILL.md is sent with the example tasks typed beside it, and a blank row is not", async () => {
    // What breaks if this is deleted: the Add form's examples never reaching the route, so a
    // pasted skill lands with none and can never be approved (M12.3.4).
    const { container, sent } = await consoleAt("/skills", {
      [`GET ${API}${LIBRARY_API_PATH}`]: { body: libraryPage([row()]) },
      [`POST ${API}/skills`]: { status: 201, body: version({ review: "pending" }) },
    });
    pressed("Add a skill", container);
    await waitFor(() => {
      expect(document.getElementById("skills-paste")).not.toBeNull();
    });
    fireEvent.change(document.getElementById("skills-paste") as HTMLTextAreaElement, { target: { value: "---\nname: x\n---\n" } });
    fireEvent.change(document.getElementById("skills-add-examples-task-0") as HTMLInputElement, { target: { value: "Asks when it renews" } });
    fireEvent.change(document.getElementById("skills-add-examples-expected-0") as HTMLInputElement, { target: { value: "Names the date" } });
    pressed(ADD_EXAMPLE, document.body);
    fireEvent.click([...document.querySelectorAll<HTMLButtonElement>("button")].find((one) => one.textContent === "Add to the library") as HTMLButtonElement);
    await waitFor(() => {
      expect((sent.find((one) => one.method === "POST")?.body as { examples: unknown }).examples).toEqual([
        { task: "Asks when it renews", expected: "Names the date" },
      ]);
    });
    expect(declaredPropertyNames(declaredRequestBodySchema(`${API}/skills`, "post"))).toContain("examples");
  });

  test("a version with no example tasks draws what it is missing and no Approve or Rehearse", async () => {
    // What breaks if this is deleted: a pasted skill whose Approve is refused on every press, with
    // nothing on the page saying it needs example tasks (M12.3.4).
    const { container } = await consoleAt(
      `${skillAddress(NAME)}/profile`,
      skillAnswers([waitingWithExamples({ examples: [], scripts: [], awaits_rehearsal: false, rehearsable: false, approval_needs: NEEDS_EXAMPLES })], []),
    );

    const page = container.querySelector('[data-slot="skill-profile"]') as HTMLElement;
    expect(page.textContent).toContain(NEEDS_EXAMPLES);
    const buttons = [...page.querySelectorAll("button")].map((one) => one.textContent ?? "");
    expect(buttons.some((one) => one === APPROVE)).toBe(false);
    expect(buttons.some((one) => one.includes(REHEARSE))).toBe(false);
    expect(buttons.some((one) => one === REJECT)).toBe(true);
  });

  test("a rehearsal sends one verdict per example, and only once every example has one", async () => {
    // What breaks if this is deleted: a rehearsal sent with an example nobody answered, recorded
    // as not behaving, or verdicts sent out of the examples' order (M12.3.4).
    const { container, sent } = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([waitingWithExamples()], [], {
      [`POST ${API}${rehearsalsPath(DIGEST)}`]: { status: 201, body: waitingWithExamples({ awaits_rehearsal: false, approval_needs: null }) },
    }));

    pressed(`${REHEARSE} of ${NAME}`, container);
    const form = container.querySelector<HTMLFormElement>(`form[aria-label^="Rehearse"]`) as HTMLFormElement;
    const submit = [...form.querySelectorAll("button")].find((one) => one.textContent === RECORD_REHEARSAL) as HTMLButtonElement;
    expect(form.textContent).toContain(ANSWER_EVERY_EXAMPLE);
    expect(submit.disabled).toBe(true);
    fireEvent.submit(form);
    expect(sent.some((one) => one.method === "POST")).toBe(false);

    const [first, second] = [...form.querySelectorAll("fieldset")];
    fireEvent.click(within(first as HTMLElement).getByLabelText(BEHAVED));
    expect(submit.disabled).toBe(true);
    fireEvent.click(within(second as HTMLElement).getByLabelText(DID_NOT_BEHAVE));
    expect(submit.disabled).toBe(false);
    fireEvent.submit(form);
    await waitFor(() => {
      expect(sent.find((one) => one.method === "POST")?.body).toEqual({ behaved: [true, false] });
    });
    expect(declaredPropertyNames(declaredRequestBodySchema(`${API}/skills/{digest}/rehearsals`, "post"))).toEqual(["behaved"]);
  });

  test("an approved version offers Export package, which posts once and saves the zip it was answered", async () => {
    // What breaks if this is deleted: an export offered for a version nobody approved, or one
    // whose answer the page drops instead of saving (M12.3.1).
    const hidden = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([version()], []));
    expect([...hidden.container.querySelectorAll("button")].some((one) => one.textContent?.includes(EXPORT))).toBe(false);
    hidden.container.remove();

    const saved: string[] = [];
    const click = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
      saved.push(`${this.download} ${this.href.slice(0, 40)}`);
    };
    try {
      const { container, sent } = await consoleAt(`${skillAddress(NAME)}/profile`, skillAnswers([version({ exportable: true })], [], {
        [`POST ${API}${exportsPath(DIGEST)}`]: {
          body: { file_name: `${NAME}-1.1.0.zip`, content: "UEsDBA==", encoding: "base64", name: NAME, version: "1.1.0", digest: DIGEST },
        },
      }));
      pressed(`${EXPORT} ${NAME}`, container);
      await waitFor(() => {
        expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([`${API}${exportsPath(DIGEST)}`]);
      });
      await waitFor(() => {
        expect(saved).toEqual([`${NAME}-1.1.0.zip data:application/zip;base64,UEsDBA==`]);
      });
    } finally {
      HTMLAnchorElement.prototype.click = click;
    }
    expect(backendModelFields(ROUTES, "SkillPackageView").sort()).toEqual(["content", "digest", "encoding", "file_name", "name", "version"]);
  });

  test("the About view reads the history from the ledger, and says where it is kept when refused", async () => {
    // What breaks if this is deleted: a history composed by the page rather than read from the
    // ledger, or a refusal drawn as an empty history.
    const ledger = {
      items: [
        { at: "2019-03-06T09:00:00Z", action: "skill", actor_id: "u_reviewer", subject_kind: "skill", subject_id: NAME, details: { change: "retired", digest: DIGEST } },
        { at: "2019-03-05T09:00:00Z", action: "skill", actor_id: "u_importer", subject_kind: "skill", subject_id: "hosting-expiry-two", details: { change: "imported", digest: OLDER } },
      ],
      next_cursor: null,
      order: "newest",
      actions: [],
      subject_kinds: [],
      actors: [],
    };
    const assigned = { ...ledger, items: [{ at: "2019-03-07T09:00:00Z", action: "compose_change", actor_id: "u_x", subject_kind: "agent", subject_id: "company_desk", details: { part: "skills", reference: "hosting_expiry", direction: "detached", reason_code: "skill_detach" } }] };
    const { container } = await consoleAt(`${skillAddress(NAME)}/about`, skillAnswers([version()], [PIN], {
      [`GET ${API}/audit`]: (body) => ({ body: body === null ? ledger : ledger }),
    }));
    await waitFor(() => {
      expect(container.textContent).toContain("Retired: version 1.1.0 by Rex Reviewer");
    });
    expect(container.textContent).not.toContain("hosting-expiry-two");

    const detail = readSkillDetail(skillsPage([version()], [PIN]), NAME);
    const lines = readHistory([], assigned.items as never, detail as NonNullable<typeof detail>);
    expect(lines.map((one) => one.words)).toEqual(["Detached from Company Desk"]);

    const refused = await consoleAt(`${skillAddress(NAME)}/about`, skillAnswers([version()], [PIN], {
      [`GET ${API}/audit`]: { status: 404, body: { message: "the audit screen is not answerable for this caller" } },
    }));
    await waitFor(() => {
      expect(refused.container.textContent).toContain(HISTORY_ELSEWHERE);
    });
  });

  test("a skill nothing here names draws one sentence, whichever the reason", async () => {
    // What breaks if this is deleted: a hidden skill told apart from a missing one.
    const { container } = await consoleAt(skillAddress("nobody-sees-this"), skillAnswers([version()], [PIN]));

    expect(container.textContent).toContain(NO_SUCH_SKILL);
  });
});
