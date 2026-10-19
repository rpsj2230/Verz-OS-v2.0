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
 * **Installing is a stepped wizard whose draft survives leaving the page**, so the install is walked
 * here step by step, and the draft is read back out of the flow memory as the page keeps it: per
 * person, in this tab only, never a secret, removed on install, on starting again and on sign-out.
 *
 * Task ids: M27.8.6, M27.11.7, M27.16.1, M27.15.68
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  CHANNELS_STEP,
  CHECK_STEP,
  DRAFT_IS_KEPT,
  FIND_STEP,
  NAME_STEP,
  NO_INSTALLABLE_VERSION,
  PICKED_UP_WHERE_YOU_WERE,
  START_AGAIN,
  installDraftKey,
} from "../src/pages/agent-templates/AgentTemplateDetailPage";
import { ACT_LABELS, originWords } from "../src/pages/agent-templates/templateActions";
import { NO_TEMPLATES } from "../src/pages/AgentTemplates";
import { readTemplates } from "../src/pages/agentTemplatesQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredPropertyNames, declaredResponseSchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";
import { noRouteRetires, retiringPattern } from "./support/explanations";

const CONSOLE_ORIGIN = "https://console.test";
const DIGEST = "d".repeat(64);
const PUBLISHER = "u_publisher_sentinel";
const INSTALLER = "u_installer_sentinel";

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
    "/api/v1/me": { body: { principal_id: INSTALLER, display_name: "Installer", assurance: "strong", channel: "web", ent_hash: "f".repeat(64), withheld_verbs: [], second_factor_needed: false } },
    "/api/v1/agent-templates": { body: LIST },
    "/api/v1/agent-templates/pricing_desk": { body: detail() },
    "/api/v1/agent-templates/pricing_desk/versions/3": {
      body: { template_id: "pricing_desk", version: 3, display_name: "Pricing desk", summary: null, content_digest: DIGEST, starts: "STARTS-SENTENCE", unavailable: null,
        channels: [
          { name: "console", label: "Web console" },
          { name: "lark", label: "Lark" },
        ],
        channels_note: "NO-CHANNEL-SENTENCE",
      },
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

/** Press Next from the first step to the one that asks where the agent answers. */
async function walkToChannels(): Promise<void> {
  await screen.findByRole("heading", { name: NAME_STEP });
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("heading", { name: FIND_STEP });
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("heading", { name: CHANNELS_STEP });
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
    noRouteRetires(["template.author", "template.withdraw"]);
    expect(retiringPattern("template.withdraw").test("/api/v1/agent-templates/{template_id}/versions/{version}/withdraw")).toBe(true);
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
    // from a single press, or one sent by walking the steps with Next.
    const { idp, router } = await consoleAt("/agent-templates/pricing_desk");

    await walkToChannels();
    const boxes = await screen.findAllByRole("checkbox", { name: /Web console|Lark/ });
    expect(boxes.map((one) => (one as HTMLInputElement).checked)).toEqual([false, false]);
    expect(document.body.textContent).toContain("NO-CHANNEL-SENTENCE");
    fireEvent.click(screen.getByRole("checkbox", { name: "Web console" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(posts(idp)).toEqual([]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
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
      {
        path: "/api/v1/agent-templates/pricing_desk/versions/3/install",
        body: { expected_digest: DIGEST, for_department: false, channels: ["console"] },
      },
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

describe("the install is a stepped wizard whose draft survives leaving the page", () => {
  test("it asks one thing at a time, in order, and the last step is the one that installs", async () => {
    // What breaks if this is deleted: the install drawn as one long form again, or a last step with
    // no summary of what is about to be installed, or Next installing on its own.
    await consoleAt("/agent-templates/pricing_desk");
    await screen.findByRole("heading", { name: NAME_STEP });
    expect(screen.getByText("Step 1 of 4")).toBeTruthy();
    expect(screen.queryByRole("button", { name: ACT_LABELS.install })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { name: FIND_STEP });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { name: CHANNELS_STEP });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { name: CHECK_STEP });
    expect(screen.getByText("Step 4 of 4")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
    expect(screen.getByRole("button", { name: ACT_LABELS.install })).toBeTruthy();
    expect(document.body.textContent).toContain("Nowhere yet");
  });

  test("a version that offers no channel has no step for them", async () => {
    // What breaks if this is deleted: an empty "Where it answers" step with nothing on it.
    await consoleAt("/agent-templates/pricing_desk", {
      "/api/v1/agent-templates/pricing_desk/versions/3": {
        body: { template_id: "pricing_desk", version: 3, display_name: "Pricing desk", summary: null, content_digest: DIGEST, starts: "STARTS-SENTENCE", unavailable: null, channels: [], channels_note: "" },
      },
    });
    await screen.findByRole("heading", { name: NAME_STEP });
    expect(screen.getByText("Step 1 of 3")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: CHANNELS_STEP })).toBeNull();
  });

  test("leaving the page and coming back finds the step and the answers, and Start again clears them", async () => {
    // What breaks if this is deleted: the owner's ask for this wizard, that a draft survives leaving
    // the page. Somebody who goes to check a name elsewhere would find an empty form on their return.
    const { router } = await consoleAt("/agent-templates/pricing_desk");
    await screen.findByRole("heading", { name: NAME_STEP });
    fireEvent.change(screen.getByLabelText("Name of the new agent"), { target: { value: "My pricing desk" } });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { name: FIND_STEP });
    fireEvent.click(screen.getByRole("checkbox", { name: "For my department" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { name: CHANNELS_STEP });
    fireEvent.click(screen.getByRole("checkbox", { name: "Lark" }));

    await act(async () => {
      await router.navigate("/agent-templates");
    });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: CHANNELS_STEP })).toBeNull();
    });
    await act(async () => {
      await router.navigate("/agent-templates/pricing_desk");
    });
    await screen.findByRole("heading", { name: CHANNELS_STEP });
    expect((screen.getByRole("checkbox", { name: "Lark" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: "Web console" }) as HTMLInputElement).checked).toBe(false);
    expect(document.body.textContent).toContain(PICKED_UP_WHERE_YOU_WERE);
    expect(document.body.textContent).toContain(DRAFT_IS_KEPT);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    await screen.findByRole("heading", { name: FIND_STEP });
    expect((screen.getByRole("checkbox", { name: "For my department" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    await screen.findByRole("heading", { name: NAME_STEP });
    expect((screen.getByLabelText("Name of the new agent") as HTMLInputElement).value).toBe("My pricing desk");

    fireEvent.click(screen.getByRole("button", { name: START_AGAIN }));
    await screen.findByRole("heading", { name: NAME_STEP });
    expect((screen.getByLabelText("Name of the new agent") as HTMLInputElement).value).toBe("Pricing desk");
    expect((await memory()).recallFlow(installDraftKey(INSTALLER, "pricing_desk", 3))).toBeUndefined();
  });

  test("the draft is kept under the person and holds a name, a tick and some channels and nothing else", async () => {
    // What breaks if this is deleted: a draft that anybody in the tab could be handed, or one that
    // grows a field a credential could be put in. Read out of the memory exactly as the page wrote it.
    await consoleAt("/agent-templates/pricing_desk");
    await screen.findByRole("heading", { name: NAME_STEP });
    fireEvent.change(screen.getByLabelText("Name of the new agent"), { target: { value: "Kept name" } });
    const kept = (await memory()).recallFlow<Record<string, unknown>>(installDraftKey(INSTALLER, "pricing_desk", 3));
    expect(Object.keys(kept ?? {}).sort()).toEqual(["at", "channels", "forDepartment", "name"]);
    expect(kept).toMatchObject({ name: "Kept name", at: 0, forDepartment: false, channels: [] });
    // Another person's key is another entry, and nobody's key is no entry at all.
    expect((await memory()).recallFlow(installDraftKey("somebody-else", "pricing_desk", 3))).toBeUndefined();
    expect(installDraftKey(null, "pricing_desk", 3)).toBeNull();
    expect(installDraftKey(INSTALLER, "pricing_desk", 3)).not.toBe(installDraftKey(INSTALLER, "pricing_desk", 4));
  });

  test("installing removes the draft, and so does signing out", async () => {
    // What breaks if this is deleted: a finished install that reopens half way, or what one person
    // typed still in memory when the next sits down in the same tab.
    const first = await consoleAt("/agent-templates/pricing_desk");
    await walkToChannels();
    fireEvent.click(screen.getByRole("checkbox", { name: "Web console" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect((await memory()).recallFlow(installDraftKey(INSTALLER, "pricing_desk", 3))).toBeDefined();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: ACT_LABELS.install }));
    });
    const dialog = await screen.findByRole("alertdialog");
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: ACT_LABELS.install }));
    });
    await waitFor(() => {
      expect(first.router.state.location.pathname).toBe("/agents/pricing_desk_1");
    });
    expect((await memory()).recallFlow(installDraftKey(INSTALLER, "pricing_desk", 3))).toBeUndefined();

    await act(async () => {
      await first.router.navigate("/agent-templates/pricing_desk");
    });
    await screen.findByRole("heading", { name: NAME_STEP });
    fireEvent.change(screen.getByLabelText("Name of the new agent"), { target: { value: "Half typed" } });
    expect((await memory()).recallFlow(installDraftKey(INSTALLER, "pricing_desk", 3))).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect((await memory()).recallFlow(installDraftKey(INSTALLER, "pricing_desk", 3))).toBeUndefined();
  });
});

/** The flow memory as the page under test sees it: sign-in resets the module registry. */
async function memory(): Promise<typeof import("../src/components/kit/flowMemory")> {
  return import("../src/components/kit/flowMemory");
}
