/**
 * The template catalogue on the shared page kit: the list, one template's page, and installing a
 * published version as a new agent.
 *
 * **Reachable means through the application's own route table**, as the other module tests mount
 * it, so a test passes only if the address resolves.
 *
 * The failures worth testing: a count of installs appearing, a principal id in page text, an
 * install sent without its confirmation or with a digest the page did not read, a built-in
 * template offered an install it cannot have, and "coming soon" said of a route that has arrived.
 *
 * Task ids: M27.8.6, M27.11.7, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NO_INSTALLABLE_VERSION } from "../src/pages/agent-templates/AgentTemplateDetailPage";
import { ACT_LABELS, originWords, UNAVAILABLE } from "../src/pages/agent-templates/templateActions";
import { NO_TEMPLATES } from "../src/pages/AgentTemplates";
import { readTemplates } from "../src/pages/agentTemplatesQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredPropertyNames, declaredResponseSchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const DIGEST = "d".repeat(64);
const PUBLISHER = "u_publisher_sentinel";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/AgentTemplate");
}, 60_000);

function card(templateId: string, displayName: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return { template_id: templateId, version: 2, display_name: displayName, summary: `${displayName} summary`, published_by: "system", origin: "built_in", ...over };
}

function detail(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    entry: card("pricing_desk", "Pricing desk", { origin: "published", version: 3, published_by: PUBLISHER }),
    persona: "PERSONA-SENTENCE",
    tier: "main",
    skills: ["quote_writer"],
    connectors: ["xero"],
    tools: ["xero.read_invoices"],
    capabilities: ["read:invoice"],
    leash: [{ target: "ticket.update_status", rung: "shadow" }],
    max_side_effect: "write",
    golden_cases: 4,
    ...over,
  };
}

const LIST = { items: [card("pricing_desk", "Pricing desk", { origin: "published" }), card("tester", "Tester")], next_cursor: null, total: null, truncated: false };

async function consoleAt(path: string, gets: Readonly<Record<string, { status?: number; body: unknown }>> = {}): Promise<{ container: HTMLElement; idp: FakeIdp; router: ReturnType<typeof createMemoryRouter> }> {
  const answers: Record<string, { status?: number; body: unknown }> = {
    "/api/v1/agent-templates": { body: LIST },
    "/api/v1/agent-templates/pricing_desk": { body: detail() },
    "/api/v1/agent-templates/pricing_desk/versions/3": {
      body: { template_id: "pricing_desk", version: 3, display_name: "Pricing desk", summary: null, content_digest: DIGEST, starts: "STARTS-SENTENCE", unavailable: null },
    },
    ...gets,
  };
  const idp = fakeIdentityProvider({
    api(url, init) {
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
      if (init?.method === "POST") {
        return reply({ agent: { agent_id: "pricing_desk_1", display_name: "Pricing desk", state: "disabled", owner_id: "u_admin", effective_hash: null, may_change: true, may_install: true, acts: [] }, leash: [] }, 201);
      }
      const answer = answers[pathname];
      return answer === undefined ? null : reply(answer.body, answer.status ?? 200);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
  return { container, idp, router };
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: JSON.parse(String(call.init?.body)) as unknown }));
}

function outsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

describe("what this module agrees with the API about", () => {
  test("no act called coming soon has a route, and the gallery sends no install count", () => {
    // What breaks if this is deleted: "coming soon" said about withdrawing after its route lands,
    // or a count of installs added to the gallery, which counts agents the reader may not see.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [one, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), one).toEqual([]);
    }
    expect(UNAVAILABLE.withdraw.retiredBy.test("/api/v1/agent-templates/{template_id}/versions/{version}/withdraw")).toBe(true);
    expect(paths).toContain("/api/v1/agent-templates/{template_id}");
    const gallery = declaredPropertyNames(declaredResponseSchema("/api/v1/agent-templates", "get"));
    expect(gallery.filter((name) => /count|installed/.test(name))).toEqual([]);
  });
});

describe("the catalogue", () => {
  test("lists each template by name with where it came from, and no publisher id", async () => {
    // What breaks if this is deleted: the gallery unreachable, or a principal id in page text.
    const { container } = await consoleAt("/agent-templates");
    const text = container.textContent ?? "";
    expect(text).toContain("Pricing desk");
    expect(text).toContain(originWords("published"));
    expect(text).toContain(originWords("built_in"));
    expect(text).not.toContain("system");
    expect(container.querySelector("[data-unavailable]")?.textContent).toContain(ACT_LABELS.author);
  });

  test("an empty catalogue is one sentence with no number, and a body that is not a gallery draws no list", async () => {
    // What breaks if this is deleted: an empty gallery drawn from a body that said nothing.
    const empty = await consoleAt("/agent-templates", { "/api/v1/agent-templates": { body: { items: [], next_cursor: null, total: null, truncated: false } } });
    expect(empty.container.textContent).toContain(NO_TEMPLATES);
    expect(empty.container.textContent).not.toMatch(/\d/);
    for (const unreadable of [null, [], {}, { items: "tester" }]) {
      expect(readTemplates(unreadable)).toBeNull();
    }
  });

  test("a card missing a required field or repeated is not drawn, and an unknown origin renders as itself", () => {
    // What breaks if this is deleted: a card with no version, which nothing could be pinned to.
    const answer = readTemplates({
      items: [card("tester", "Tester"), card("tester", "Again"), { ...card("nv", "No version"), version: null }, { ...card("no", "No origin"), origin: "" }],
    });
    expect(answer?.cards.map((one) => one.templateId)).toEqual(["tester"]);
    expect(originWords("something_else")).toBe("something_else");
  });
});

describe("one template's page", () => {
  test("says what an install would ask for, with the publisher only in Advanced", async () => {
    // What breaks if this is deleted: the page describing nothing an install carries, or a
    // principal id in page text.
    const { container } = await consoleAt("/agent-templates/pricing_desk");
    const text = outsideAdvanced(container);
    expect(container.querySelector("h1")?.textContent).toBe("Pricing desk");
    for (const one of ["quote_writer", "xero", "xero.read_invoices", "read:invoice", "PERSONA-SENTENCE", "STARTS-SENTENCE"]) {
      expect(text).toContain(one);
    }
    expect(text).not.toContain(PUBLISHER);
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain(PUBLISHER);
    expect(container.querySelector("[data-unavailable]")?.textContent).toContain(ACT_LABELS.withdraw);
  });

  test("installing sends the digest the page read, only from its confirmation, and opens the new agent", async () => {
    // What breaks if this is deleted: an install of a version the person did not see, or one sent
    // from a single press.
    const { idp, router } = await consoleAt("/agent-templates/pricing_desk");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: ACT_LABELS.install }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("STARTS-SENTENCE");
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: ACT_LABELS.install }));
    });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/agents/pricing_desk_1");
    });
    expect(posts(idp)).toEqual([
      { path: "/api/v1/agent-templates/pricing_desk/versions/3/install", body: { expected_digest: DIGEST, for_department: false } },
    ]);
  });

  test("a template with no installable version offers no install, in one sentence whatever the reason", async () => {
    // What breaks if this is deleted: an install button on a built-in template, which cannot be
    // installed, or a sentence telling a refused reader apart from a missing version.
    const { container } = await consoleAt("/agent-templates/pricing_desk", {
      "/api/v1/agent-templates/pricing_desk/versions/3": { status: 404, body: { message: "I could not find that.", trace_id: "T" } },
    });
    expect(container.textContent).toContain(NO_INSTALLABLE_VERSION);
    expect(screen.queryByRole("button", { name: ACT_LABELS.install })).toBeNull();
  });
});
