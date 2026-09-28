/**
 * The Models and routing module on the shared page kit: the providers list, one provider's page,
 * and the Routing page with the owner's failover matrix.
 *
 * **Reachable means through the application's own route table.** Every test mounts `routes` from
 * `src/App.tsx` on a memory router, signed in through the real session modules and answered by a
 * stand-in API keyed by method and path, and every request the page sends is kept, so a write is
 * proved by what reached the API and when.
 *
 * What each test holds is what the owner asked for on 2026-09-22 and 2026-09-28: plain words and
 * names rather than identifiers, a figure nothing records shown as not recorded rather than nought,
 * every write sent only from its confirmation, and the matrix as his screenshot drew it.
 *
 * Task ids: M27.16.1, M27.15.38, M5.3.3, M5.6.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_RECORDED } from "../src/components/kit";
import { UNAVAILABLE } from "../src/pages/models/modelsActions";
import { LAST_TEST_COLUMN, PROVIDERS_LEDE, readProviderRows } from "../src/pages/models/ProvidersPage";
import { CALLS_LABEL, COST_LABEL, FAILURES_LABEL, NO_SUCH_PROVIDER } from "../src/pages/models/ProviderDetailPage";
import { lastTestWords } from "../src/pages/models/providerWords";
import { FAILOVER_MATRIX, HELD_HEADING } from "../src/pages/models/RoutingPage";
import { matrixLines } from "../src/pages/models/routingWords";
import type { RungRow } from "../src/pages/matrixQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { apiDocument, declaredQueryParameters } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const ORIGIN = "https://console.test";
const PROVIDERS = "/api/v1/models/providers";
const RUNGS = "/api/v1/routing/rungs";
const RUNG_A = "11111111-1111-4111-8111-111111111111";
const RUNG_B = "22222222-2222-4222-8222-222222222222";
const RUNG_H = "33333333-3333-4333-8333-333333333333";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Matrix");
  await import("../src/pages/Provider");
}, 60_000);

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

type Answers = Readonly<Record<string, (body: unknown) => unknown>>;

async function consoleAt(address: string, answers: Answers): Promise<{ container: HTMLElement; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const parsed = new URL(url, ORIGIN);
      const method = (init?.method ?? "GET").toUpperCase();
      const body: unknown = typeof init?.body === "string" && init.body !== "" ? JSON.parse(init.body) : null;
      const answer = answers[`${method} ${parsed.pathname}`];
      if (answer === undefined) {
        return null;
      }
      sent.push({ method, path: `${parsed.pathname}${parsed.search}`, body });
      return new Response(JSON.stringify(answer(body)), { status: 200, headers: { "content-type": "application/json" } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [address] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, sent };
}

function writes(sent: readonly Sent[]): Sent[] {
  return sent.filter((one) => one.method !== "GET");
}

async function confirm(label: string): Promise<void> {
  const dialog = await screen.findByRole("alertdialog");
  fireEvent.click(within(dialog).getByRole("button", { name: label }));
}

function provider(slug: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    listed: 0,
    provider: slug,
    description: `${slug} description`,
    hosted: true,
    switched_on: true,
    switched_by: null,
    switched_at: null,
    key_held: true,
    credential: null,
    registered: null,
    disclosed: [],
    last_check: null,
    ...extra,
  };
}

function step(id: string, tier: string, position: number, slug: string, model: string, role = "primary"): Record<string, unknown> {
  return {
    rung_id: id,
    tier,
    position,
    role,
    deployment_id: `${slug}-${model}`,
    provider: slug,
    model,
    enabled: true,
    answers: true,
    skipped_because: null,
    told: null,
    state: "closed",
    measured: false,
    unhealthy_because: null,
    live_seen: 0,
    live_failed: 0,
  };
}

function plan(providers: readonly Record<string, unknown>[], rungs: readonly Record<string, unknown>[] = []): Record<string, unknown> {
  return {
    profile: "hosted",
    providers,
    rungs,
    exhausted_tiers: [],
    editable: true,
    profile_editable: false,
    vault: null,
    vault_told: null,
    tiers: [],
    residency: [],
    depth_alerts: [],
    next_cursor: null,
  };
}

function rung(id: string, tier: string, position: number, slug: string, model: string, role = "primary"): RungRow {
  return {
    id,
    tier,
    position,
    role,
    scope: { clauses: [] },
    deployment_id: `${slug}-${model}-deployment`,
    provider: slug,
    model,
    attempts: 1,
    timeout_seconds: 12,
    max_concurrency: 4,
    enabled: true,
  };
}

// ------------------------------------------------------------------------------ the providers

describe("the providers list", () => {
  test("each provider is a row by the name a person knows, with on or off, its key, its last test and its models", async () => {
    // What breaks if this is deleted: the owner's list drawn with slugs, a test result nobody reads,
    // or the models column empty for a provider every question uses.
    const { container } = await consoleAt("/models", {
      [`GET ${PROVIDERS}`]: () =>
        plan(
          [
            provider("openai", { last_check: { answered: true, outcome: "answered", model: "gpt-5-mini", at: "2019-03-04T09:00:00Z" } }),
            provider("anthropic", { switched_on: false, key_held: false }),
          ],
          [step(RUNG_A, "main", 0, "openai", "gpt-5-mini")],
        ),
    });

    expect(container.textContent).toContain(PROVIDERS_LEDE);
    const rows = [...container.querySelectorAll('[data-slot="entity-table"] tbody tr')].map((row) => row.textContent ?? "");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain("OpenAI");
    expect(rows[0]).toContain("On");
    expect(rows[0]).toContain("Answered, 4 Mar 2019");
    expect(rows[0]).toContain("gpt-5-mini");
    expect(rows[1]).toContain("Anthropic (Claude)");
    expect(rows[1]).toContain("Off");
    expect(rows[1]).toContain("Not held");
    expect(rows[1]).toContain(lastTestWords(null));
    const links = [...container.querySelectorAll('[data-slot="entity-table"] tbody a')].map((one) => one.getAttribute("href"));
    expect(links).toEqual(["/models/openai", "/models/anthropic"]);
    expect(container.textContent).toContain(LAST_TEST_COLUMN);
  });

  test("a search and a filter are sent to the route as parameters it declares", async () => {
    // What breaks if this is deleted: a search box whose words the route ignores, which is a control
    // that does nothing, the thing the owner asked the console to stop drawing.
    const { container, sent } = await consoleAt("/models", {
      [`GET ${PROVIDERS}`]: () => plan([provider("openai"), provider("moonshot", { switched_on: false })]),
    });
    fireEvent.change(container.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "moon" } });
    await waitFor(() => {
      expect(sent.some((one) => one.path.includes("q=moon"))).toBe(true);
    });
    const names = declaredQueryParameters(PROVIDERS, "get");
    expect(names).toEqual(expect.arrayContaining(["q", "filter", "cursor", "sort", "limit"]));
    for (const one of sent) {
      for (const name of new URL(one.path, ORIGIN).searchParams.keys()) {
        expect(names).toContain(name);
      }
    }
  });

  test("a row the API sends without a provider is not drawn, and a repeated one is drawn once", () => {
    // What breaks if this is deleted: a list keyed on nothing, where a repeated slug draws two rows and
    // a click on either opens the same page.
    expect(readProviderRows(plan([provider("openai"), provider("openai"), provider("")])).map((one) => one.provider)).toEqual(["openai"]);
    expect(readProviderRows({ providers: "nope" })).toEqual([]);
  });

  test("the one act not built yet says so, and its route has not arrived", () => {
    // What breaks if this is deleted: a "coming soon" that outlives the route that makes it work.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    expect(UNAVAILABLE.rename.retiredBy.test("/api/v1/models/providers/{provider}/rename")).toBe(true);
  });
});

// ------------------------------------------------------------------------- one provider's page

const STATS = {
  provider: "openai",
  days: 30,
  calls: 12,
  failures: 1,
  cost_minor: null,
  unrecorded: [{ figure: "model_cost", why: "Nothing on this install records what a model call costs yet." }],
};

describe("one provider's page", () => {
  test("the figures are the stats route's, and the cost nothing records is not recorded rather than nought", async () => {
    // What breaks if this is deleted: a dashboard drawing 0.00 for a cost nothing measured, which
    // says the provider cost nothing.
    const { container } = await consoleAt("/models/openai", {
      [`GET ${PROVIDERS}`]: () => plan([provider("openai")], [step(RUNG_A, "main", 0, "openai", "gpt-5-mini")]),
      [`GET ${PROVIDERS}/openai/stats`]: () => STATS,
    });
    await waitFor(() => {
      expect(container.querySelector('[data-slot="kpi-strip"]')).not.toBeNull();
    });
    const figures = [...container.querySelectorAll('[data-slot="stat-card"]')].map((one) => one.textContent ?? "");
    expect(figures[0]).toContain(CALLS_LABEL);
    expect(figures[0]).toContain("12");
    expect(figures[1]).toContain(FAILURES_LABEL);
    expect(figures[1]).toContain("1");
    expect(figures[2]).toContain(COST_LABEL);
    expect(figures[2]).toContain(NOT_RECORDED);
    expect(figures[2]).not.toMatch(/\b0(\.00)?\b/);
    const views = [...container.querySelectorAll('[data-slot="view-switch"] a')].map((one) => one.getAttribute("href"));
    expect(views).toEqual(["/models/openai", "/models/openai/profile", "/models/openai/about"]);
    expect(container.textContent).toContain("Medium");
  });

  test("turning a provider off is sent only from its confirmation, as PUT on false", async () => {
    // What breaks if this is deleted: one press moving every department's questions away from a
    // provider, with nothing between the press and the write.
    const { container, sent } = await consoleAt("/models/openai", {
      [`GET ${PROVIDERS}`]: () => plan([provider("openai")]),
      [`GET ${PROVIDERS}/openai/stats`]: () => STATS,
      [`PUT ${PROVIDERS}/openai`]: () => plan([provider("openai", { switched_on: false })]),
    });
    fireEvent.click(within(container).getByRole("button", { name: "Turn off" }));
    expect(writes(sent)).toEqual([]);
    await confirm("Turn off");
    await waitFor(() => {
      expect(writes(sent)).toEqual([{ method: "PUT", path: `${PROVIDERS}/openai`, body: { on: false } }]);
    });
  });

  test("an address naming no provider says so, the same whatever the reason", async () => {
    // What breaks if this is deleted: a page that tells a slug that exists from one that does not.
    const { container } = await consoleAt("/models/nobody", {
      [`GET ${PROVIDERS}`]: () => plan([]),
      [`GET ${PROVIDERS}/nobody/stats`]: () => STATS,
    });
    expect(container.textContent).toContain(NO_SUCH_PROVIDER);
  });

  test("terms are sent from their confirmation with what was typed, and a blank region is said first", async () => {
    // What breaks if this is deleted: M5.6.4's terms recorded with a region nobody typed, or sent
    // blank to be refused after the person agreed to it.
    const { container, sent } = await consoleAt("/models/openai/profile", {
      [`GET ${PROVIDERS}`]: () => plan([provider("openai")]),
      [`GET ${PROVIDERS}/openai/stats`]: () => STATS,
      [`PUT ${PROVIDERS}/openai/terms`]: () => plan([provider("openai")]),
    });
    const form = container.querySelector('form[aria-label^="Terms and residency"]') as HTMLFormElement;
    const region = form.querySelector('input[name="processing_region"]') as HTMLInputElement;
    fireEvent.change(region, { target: { value: "" } });
    fireEvent.submit(form);
    expect(container.textContent).toContain("Name the region, or global when none is promised.");
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.change(region, { target: { value: "eu-west-1" } });
    fireEvent.change(form.querySelector('input[name="retention_terms"]') as HTMLInputElement, { target: { value: "Zero retention" } });
    fireEvent.submit(form);
    expect(writes(sent)).toEqual([]);
    await confirm("Save these terms");
    await waitFor(() => {
      expect(writes(sent)).toHaveLength(1);
    });
    const [put] = writes(sent);
    expect(put?.path).toBe(`${PROVIDERS}/openai/terms`);
    expect(put?.body).toMatchObject({ processing_region: "eu-west-1", retention_terms: "Zero retention", residency_class: "global" });
  });

  test("the history names what happened in words, and who acted only under Advanced", async () => {
    // What breaks if this is deleted: the About view drawing principal ids as page text, or a test
    // under the provider's other subject left out of its history.
    const { container } = await consoleAt("/models/openai/about", {
      [`GET ${PROVIDERS}`]: () => plan([provider("openai")]),
      [`GET ${PROVIDERS}/openai/stats`]: () => STATS,
      ["GET /api/v1/audit"]: () => ({
        items: [
          {
            at: "2019-03-04T09:00:00Z",
            action: "setting",
            actor_id: "p_admin_1",
            subject_kind: "setting",
            subject_id: "provider.openai",
            details: { change: "changed", fields: "retention_terms,training_terms" },
          },
          {
            at: "2019-03-03T09:00:00Z",
            action: "setting",
            actor_id: "p_admin_1",
            subject_kind: "setting",
            subject_id: "provider_check.openai",
            details: { change: "set" },
          },
          {
            at: "2019-03-02T09:00:00Z",
            action: "setting",
            actor_id: "p_other",
            subject_kind: "setting",
            subject_id: "provider.openai_proxy",
            details: { change: "switched_off" },
          },
        ],
        next_cursor: null,
        order: "newest",
        actions: [],
        subject_kinds: [],
        actors: [],
      }),
    });
    await waitFor(() => {
      expect(container.textContent).toContain("Changed: retention terms, training terms");
    });
    expect(container.textContent).toContain("Tested");
    expect(container.textContent).not.toContain("Turned off");
    const advanced = container.querySelector('[data-slot="advanced"]') as HTMLElement;
    const outside = (container.textContent ?? "").replace(advanced.textContent ?? "", "");
    expect(outside).not.toContain("p_admin_1");
    expect(advanced.textContent).toContain("p_admin_1");
  });
});

// ------------------------------------------------------------------------------ the routing page

const MATRIX_ROWS = [rung(RUNG_B, "main", 4, "moonshot", "kimi-k3"), rung(RUNG_A, "main", 1, "anthropic", "claude-sonnet-5"), rung(RUNG_H, "heavy", 0, "openai", "gpt-5")];

function matrixAnswers(extra: Answers = {}): Answers {
  return {
    [`GET ${RUNGS}`]: () => ({ items: MATRIX_ROWS, next_cursor: null, total: null, truncated: false, editable: true }),
    [`GET ${PROVIDERS}`]: () =>
      plan(
        [provider("anthropic"), provider("moonshot"), provider("openai")],
        [
          step(RUNG_A, "main", 1, "anthropic", "claude-sonnet-5"),
          step(RUNG_B, "main", 4, "moonshot", "kimi-k3", "cross_provider_failover"),
          step(RUNG_H, "heavy", 0, "openai", "gpt-5"),
        ],
      ),
    ["GET /api/v1/routing/changes"]: () => ({ items: [] }),
    ["GET /api/v1/routing/golden-questions"]: () => ({ items: [] }),
    ["GET /api/v1/routing/golden-questions/askers"]: () => ({ items: [{ id: "p_priya", name: "Priya Shah" }], truncated: false }),
    ...extra,
  };
}

describe("the routing page", () => {
  test("the matrix is the owner's table: each level named once, its steps numbered from 1 by position, in plain words", async () => {
    // What breaks if this is deleted: the screen the owner called very complicated coming back, a
    // step numbered by its stored position, or an id or a word like rung drawn in the table.
    const { container } = await consoleAt("/routing", matrixAnswers());
    const table = [...container.querySelectorAll("table")].find((one) => one.querySelector("caption")?.textContent === FAILOVER_MATRIX);
    expect([...(table?.querySelectorAll("thead th") ?? [])].map((one) => one.textContent).slice(0, 5)).toEqual([
      "Complexity",
      "Step",
      "Provider",
      "Model",
      "Role",
    ]);
    const rows = [...(table?.querySelectorAll("tbody tr") ?? [])].map((row) => [...row.querySelectorAll("td")].slice(0, 5).map((cell) => cell.textContent));
    expect(rows).toEqual([
      ["Simple", "", "No model is set up for this level."],
      ["Medium", "1", "Anthropic (Claude)", "claude-sonnet-5", "default"],
      ["", "2", "Moonshot (Kimi)", "kimi-k3", "next provider"],
      ["Complex", "1", "OpenAI", "gpt-5", "default"],
    ]);
    expect(table?.textContent).not.toContain(RUNG_A);
    expect(container.textContent ?? "").not.toMatch(/\b(rungs?|ladders?|tiers?|lanes?|slots?)\b/i);
  });

  test("a step is moved and retired only from a confirmation, and a held change says why and the way through", async () => {
    // What breaks if this is deleted: M27.15.38's move and retirement sent from a press, or a held
    // move drawn as though it had happened.
    const held = {
      id: "44444444-4444-4444-8444-444444444444",
      kind: "move",
      status: "held",
      rung_id: RUNG_B,
      proposed: { tier: "main", step: 1 },
      failing: [],
      reasons: ["No golden questions are recorded yet."],
      quality_share: null,
      proposed_by: "p_admin_1",
      decided_at: "2019-03-04T09:00:00Z",
      rung: null,
    };
    const { container, sent } = await consoleAt(
      `/routing/${RUNG_B}`,
      matrixAnswers({
        [`POST ${RUNGS}/${RUNG_B}/move`]: () => held,
        [`POST ${RUNGS}/${RUNG_B}/retire`]: () => ({ ...held, kind: "retire" }),
      }),
    );
    const move = container.querySelector('form[aria-label^="Move step 2"]') as HTMLFormElement;
    fireEvent.change(move.querySelector('input[name="step"]') as HTMLInputElement, { target: { value: "1" } });
    fireEvent.submit(move);
    expect(writes(sent)).toEqual([]);
    await confirm("Move it");
    await waitFor(() => {
      expect(writes(sent)).toEqual([{ method: "POST", path: `${RUNGS}/${RUNG_B}/move`, body: { tier: "main", step: 1 } }]);
    });
    await waitFor(() => {
      expect(container.querySelector(`[aria-label="${HELD_HEADING}"]`)).not.toBeNull();
    });
    const panel = container.querySelector(`[aria-label="${HELD_HEADING}"]`) as HTMLElement;
    expect(panel.textContent).toContain("The move was held and the step stays where it was.");
    expect(panel.textContent).toContain("To get a change through:");
    expect(panel.textContent).not.toContain("p_admin_1");

    const retire = [...container.querySelectorAll("button")].find((one) => one.textContent === "Retire") as HTMLButtonElement;
    fireEvent.click(retire);
    await confirm("Retire");
    await waitFor(() => {
      expect(writes(sent).map((one) => one.path)).toContain(`${RUNGS}/${RUNG_B}/retire`);
    });
  });

  test("a golden question is asked as a person chosen by name, and the id the API stores is what is sent", async () => {
    // What breaks if this is deleted: the form asking an owner for a principal id he does not know.
    const { container, sent } = await consoleAt(
      "/routing",
      matrixAnswers({ ["POST /api/v1/routing/golden-questions"]: () => ({ items: [] }) }),
    );
    await waitFor(() => {
      expect(container.querySelector('form[aria-label="Add a golden question"] option[value="p_priya"]')).not.toBeNull();
    });
    const form = container.querySelector('form[aria-label="Add a golden question"]') as HTMLFormElement;
    expect(form.querySelector('option[value="p_priya"]')?.textContent).toBe("Priya Shah");
    fireEvent.change(form.querySelector('input[name="question"]') as HTMLInputElement, { target: { value: "How much leave do we get?" } });
    fireEvent.change(form.querySelector('select[name="asked_as"]') as HTMLSelectElement, { target: { value: "p_priya" } });
    fireEvent.submit(form);
    await confirm("Add this golden question");
    await waitFor(() => {
      expect(writes(sent)).toEqual([
        { method: "POST", path: "/api/v1/routing/golden-questions", body: { question: "How much leave do we get?", asked_as: "p_priya", expect: "answer" } },
      ]);
    });
  });

  test("a level's steps are numbered by position whatever order they arrive in, and the role is the plan's", () => {
    // What breaks if this is deleted: the step after a retired primary still drawn as a failover
    // because the stored role was not derived again, or steps numbered in arrival order.
    const lines = matrixLines(
      [rung(RUNG_B, "main", 7, "moonshot", "kimi-k3", "cross_provider_failover"), rung(RUNG_A, "main", 3, "anthropic", "claude-sonnet-5", "same_provider_failover")],
      [step(RUNG_A, "main", 3, "anthropic", "claude-sonnet-5", "primary")] as never,
      [],
    );
    const main = lines.filter((one) => one.tier === "main");
    expect(main.map((one) => [one.step, one.model, one.role])).toEqual([
      [1, "claude-sonnet-5", "primary"],
      [2, "kimi-k3", "cross_provider_failover"],
    ]);
  });
});
