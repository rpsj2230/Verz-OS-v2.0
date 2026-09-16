/**
 * The Automations tab: the gallery an agent's workspace draws, and the one confirmed install.
 *
 * **Reachable means through the application's own route table.** The whole console is mounted at
 * the agent page's address on a memory router over `routes` from `src/App.tsx`, signed in through
 * the real session modules and answered by a stand-in API, as `tests/agent-page.test.tsx` mounts
 * the workspace. A test that rendered the gallery component on its own would pass with the tab
 * never wired to it.
 *
 * **What the server decides is not re-tested here.** The route recomputes the preview and refuses
 * a confirmation that does not match, which `tests/unit/test_automation_gallery_routes.py` proves.
 * What is proved here is the half a browser owns: nothing is written before the second press, the
 * second press sends the API's own digest and nothing else, a refusal is shown in the API's words,
 * the keyboard gets back to where it was, and the gallery is not asked for on every tab change.
 *
 * **The reader is checked against the routes' declared schemas**, read off the generated document
 * rather than off a copy written here, so a renamed field is a red test rather than a gallery
 * that silently draws nothing.
 *
 * Task ids: M39.6.1.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  CANNOT_INSTALL_HERE,
  GALLERY_HEADING,
  GUARDS_LABEL,
  INSTALL_LABEL,
  INSTALLED_TITLE,
  KEEP_LABEL,
  NOT_INSTALLED,
  REACH_LABEL,
  REACHES_NOTHING,
  RUNS_AS_LABEL,
  SCHEDULE_LABEL,
  START_LABEL,
  installedAsSentence,
  installedSentence,
  installQuestion,
  scheduleSentence,
} from "../src/components/AutomationGallery";
import {
  installBody,
  readGallery,
  readNotInstalled,
  readPreview,
} from "../src/pages/automationGalleryQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import {
  declaredProperty,
  declaredPropertyNames,
  declaredRequestBodySchema,
  declaredResponseSchema,
} from "./support/openapi";

const CONSOLE_ORIGIN = "https://console.test";
const WORKSPACE = "/api/v1/agents/quote-helper/workspace";
const GALLERY = "/api/v1/agents/quote-helper/automation-templates";
const PREVIEW = "/api/v1/agents/quote-helper/automation-templates/weekly_work_summary/preview";
const INSTALL = "/api/v1/agents/quote-helper/automations";

const DIGEST = "c".repeat(64);

beforeAll(async () => {
  await import("../src/pages/Agent");
}, 60_000);

// ------------------------------------------------------------------------------- fixtures

function workspaceWire(): Record<string, unknown> {
  return {
    agent: { agent_id: "quote-helper", display_name: "Quote Helper", owner_id: "steward-one" },
    tabs: [
      { tab: "automations", label: "Automations", purpose: "What this agent runs on a schedule." },
      { tab: "settings", label: "Settings", purpose: "The agent's own decisions." },
    ],
    composition: [],
  };
}

function card(
  templateId: string,
  name: string,
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    template_id: templateId,
    version: 1,
    name,
    summary: `What ${templateId} is for.`,
    schedule: "every Friday at 15:00 UTC",
    installed_as: null,
    installable: true,
    ...extra,
  };
}

function galleryWire(installedAs: string | null = null): Record<string, unknown> {
  return {
    items: [
      card("unanswered_questions", "I list the questions I could not answer this week", {
        installable: false,
      }),
      card("weekly_work_summary", "I write you a summary of my week's work", {
        installed_as: installedAs,
      }),
    ],
    installing: "Installing writes the automation. Nothing runs it yet.",
  };
}

function previewWire(reach: readonly string[] = ["read:client.name"]): Record<string, unknown> {
  return {
    agent_id: "quote-helper",
    template_id: "weekly_work_summary",
    version: 1,
    name: "I write you a summary of my week's work",
    summary: "What weekly_work_summary is for.",
    schedule: "every Friday at 15:00 UTC",
    runs_as: "u_admin",
    runs_as_name: "Admin Person",
    starts_paused: true,
    paused_because: "It starts paused, and somebody other than you starts it.",
    reach,
    reach_rule: "It reaches what you may reach that this agent also allows.",
    guards: "Without it nobody learns what this agent did.",
    installing: "Installing writes the automation. Nothing runs it yet.",
    confirmation: DIGEST,
  };
}

interface Stand {
  readonly idp: FakeIdp;
  readonly sent: { readonly method: string; readonly path: string; readonly body: unknown }[];
}

type Handler = (body: unknown) => { readonly status?: number; readonly body: unknown };

/** The whole console at one address, signed in, answering `METHOD path` keys and nothing else. */
async function consoleAt(
  address: string,
  handlers: Record<string, Handler>,
): Promise<Stand & { readonly container: HTMLElement }> {
  const sent: Stand["sent"] = [];
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
        headers: { "content-type": "application/json", "x-trace-id": "trace-gallery" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [address] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector(".agent-header h2")) {
      throw new Error("the workspace has not arrived");
    }
  });
  return { container, idp, sent };
}

async function galleryDrawn(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector('[aria-label="Automation templates"] li')) {
      throw new Error("the gallery has not arrived");
    }
  });
}

function asked(stand: Stand, method: string, path: string): number {
  return stand.sent.filter((one) => one.method === method && one.path === path).length;
}

function button(container: HTMLElement, label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll<HTMLButtonElement>("button")].find(
    (one) => one.getAttribute("aria-label") === label || one.textContent === label,
  );
  if (!found) {
    throw new Error(`No button labelled ${label}.`);
  }
  return found;
}

/** A button inside the open confirmation, which is the only place its two labels are unambiguous. */
function choice(container: HTMLElement, label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll<HTMLButtonElement>("section.confirm button")].find(
    (one) => one.textContent === label,
  );
  if (!found) {
    throw new Error(`No choice labelled ${label} in an open confirmation.`);
  }
  return found;
}

function tabButton(container: HTMLElement, label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
    (one) => one.textContent === label,
  );
  if (!found) {
    throw new Error(`No tab labelled ${label}.`);
  }
  return found;
}

const ANSWERING: Record<string, Handler> = {
  [`GET ${WORKSPACE}`]: () => ({ body: workspaceWire() }),
  [`GET ${GALLERY}`]: () => ({ body: galleryWire() }),
  [`GET ${PREVIEW}`]: () => ({ body: previewWire() }),
};

// ------------------------------------------------------------------------------- the gallery

describe("the gallery on the Automations tab", () => {
  test("every template the API sent is drawn in its order, with its schedule and what it offers this reader", async () => {
    // What breaks if this is deleted: a gallery that reaches the tab and draws nothing, or
    // draws an Install control for a reader the API said may not install, or hides that the
    // reader already has one.
    const stand = await consoleAt("/agents/quote-helper/automations", {
      ...ANSWERING,
      [`GET ${GALLERY}`]: () => ({ body: galleryWire("auto_mine") }),
    });
    await galleryDrawn(stand.container);
    const cards = [...stand.container.querySelectorAll('[aria-label="Automation templates"] > ul > li')];

    expect(stand.container.querySelector("h3")?.textContent).toBe(GALLERY_HEADING);
    expect(stand.container.textContent).toContain("Installing writes the automation. Nothing runs it yet.");
    expect(cards.map((one) => one.querySelector("h4")?.textContent)).toEqual([
      "I list the questions I could not answer this week",
      "I write you a summary of my week's work",
    ]);
    expect(cards[0]?.textContent).toContain(scheduleSentence("every Friday at 15:00 UTC"));
    expect(cards[0]?.textContent).toContain(CANNOT_INSTALL_HERE);
    expect(cards[0]?.querySelector("button")).toBeNull();
    expect(cards[1]?.textContent).toContain(installedAsSentence("auto_mine"));
    expect(cards[1]?.querySelector("button")).toBeNull();
  });

  test("the gallery is asked for when its tab is first shown and never for moving between tabs", async () => {
    // What breaks if this is deleted: a gallery fetched inside the panel, which the workspace
    // rebuilds on every tab change, so holding an arrow key is a request per step; or a gallery
    // asked for by everybody who opens an agent and never looks at its automations.
    const stand = await consoleAt("/agents/quote-helper/settings", ANSWERING);

    expect(asked(stand, "GET", GALLERY)).toBe(0);
    fireEvent.click(tabButton(stand.container, "Automations"));
    await galleryDrawn(stand.container);
    fireEvent.click(tabButton(stand.container, "Settings"));
    fireEvent.click(tabButton(stand.container, "Automations"));
    await galleryDrawn(stand.container);

    expect(asked(stand, "GET", GALLERY)).toBe(1);
  });

  test("a refused gallery is the API's own sentence and reference, and draws no card", async () => {
    // What breaks if this is deleted: a refusal explained in the console's words, which would be
    // a second sentence for the one 404 the route gives a missing agent and a hidden one alike.
    const stand = await consoleAt("/agents/quote-helper/automations", {
      ...ANSWERING,
      [`GET ${GALLERY}`]: () => ({
        status: 404,
        body: { message: "I could not find that.", outcome: "absent", trace_id: "trace-gallery" },
      }),
    });
    await waitFor(() => {
      expect(stand.container.textContent).toContain("I could not find that.");
    });

    expect(stand.container.textContent).toContain("trace-gallery");
    expect(stand.container.querySelector('[aria-label="Automation templates"]')).toBeNull();
  });
});

// ------------------------------------------------------------------------------- the install

describe("the one confirmed install", () => {
  async function confirming() {
    const stand = await consoleAt("/agents/quote-helper/automations", {
      ...ANSWERING,
      [`POST ${INSTALL}`]: () => ({
        status: 201,
        body: { automation_id: "auto_new", name: "I write you a summary of my week's work" },
      }),
    });
    await galleryDrawn(stand.container);
    fireEvent.click(button(stand.container, `${INSTALL_LABEL}: I write you a summary of my week's work`));
    await waitFor(() => {
      expect(stand.container.textContent).toContain(installQuestion("I write you a summary of my week's work"));
    });
    return stand;
  }

  test("Install shows who it runs as, when, how it starts, what it reaches and what breaks, and writes nothing", async () => {
    // What breaks if this is deleted: a first press that installs, or a confirmation that leaves
    // out the principal, the paused start or the reach, which are the facts the digest the
    // server checks was computed over.
    const stand = await confirming();
    const facts = stand.container.querySelector('[aria-label="What installing it would do"]');
    const text = facts?.textContent ?? "";

    expect(asked(stand, "GET", PREVIEW)).toBe(1);
    expect(asked(stand, "POST", INSTALL)).toBe(0);
    for (const label of [RUNS_AS_LABEL, SCHEDULE_LABEL, START_LABEL, REACH_LABEL, GUARDS_LABEL]) {
      expect(text).toContain(label);
    }
    expect(text).toContain("Admin Person");
    expect(text).toContain("u_admin");
    expect(text).toContain("It starts paused, and somebody other than you starts it.");
    expect(facts?.querySelector("code:not(:first-child), li code")?.textContent).toBe("read:client.name");
    expect(stand.container.textContent).toContain("It reaches what you may reach that this agent also allows.");
    expect(document.activeElement?.textContent).toBe(KEEP_LABEL);
  });

  test("confirming sends the template and the API's own digest and nothing else, then asks for the gallery again", async () => {
    // What breaks if this is deleted: an install body carrying a principal, a reach or a digest
    // the console computed, or a gallery left showing the card as not installed after the write.
    const stand = await confirming();

    await act(async () => {
      fireEvent.click(choice(stand.container, INSTALL_LABEL));
    });
    await waitFor(() => {
      expect(stand.container.textContent).toContain(
        installedSentence("I write you a summary of my week's work", "auto_new"),
      );
    });
    const posted = stand.sent.filter((one) => one.method === "POST");

    expect(posted).toEqual([
      {
        method: "POST",
        path: INSTALL,
        body: { template_id: "weekly_work_summary", confirmation: DIGEST },
      },
    ]);
    expect(stand.container.textContent).toContain(INSTALLED_TITLE);
    await waitFor(() => {
      expect(asked(stand, "GET", GALLERY)).toBe(2);
    });
  });

  test("Escape and Not now write nothing and put focus back on the Install button that opened it", async () => {
    // What breaks if this is deleted: a keyboard user dropped at the top of the document after
    // declining, or a decline that still sends the install.
    const stand = await confirming();
    const panel = stand.container.querySelector("section.confirm");

    fireEvent.keyDown(panel as Element, { key: "Escape" });
    await waitFor(() => {
      expect(document.activeElement?.getAttribute("aria-label")).toBe(
        `${INSTALL_LABEL}: I write you a summary of my week's work`,
      );
    });
    fireEvent.click(button(stand.container, `${INSTALL_LABEL}: I write you a summary of my week's work`));
    await waitFor(() => {
      expect(stand.container.querySelector("section.confirm")).not.toBeNull();
    });
    fireEvent.click(choice(stand.container, KEEP_LABEL));

    expect(stand.container.querySelector("section.confirm")).toBeNull();
    expect(asked(stand, "POST", INSTALL)).toBe(0);
  });

  test("a refused install is shown in the API's sentence and nothing is claimed as installed", async () => {
    // What breaks if this is deleted: a stale confirmation, or a second install of the same thing,
    // reported as a success, or reported in words the API did not write.
    const stand = await consoleAt("/agents/quote-helper/automations", {
      ...ANSWERING,
      [`POST ${INSTALL}`]: () => ({
        status: 409,
        body: { outcome: "unconfirmed", sentence: "Look again and confirm.", automation_id: null },
      }),
    });
    await galleryDrawn(stand.container);
    fireEvent.click(button(stand.container, `${INSTALL_LABEL}: I write you a summary of my week's work`));
    await waitFor(() => {
      expect(stand.container.querySelector("section.confirm")).not.toBeNull();
    });
    await act(async () => {
      fireEvent.click(choice(stand.container, INSTALL_LABEL));
    });
    await waitFor(() => {
      expect(stand.container.textContent).toContain("Look again and confirm.");
    });

    const titles = [...stand.container.querySelectorAll(".notice__title")].map((one) => one.textContent);
    expect(titles).toEqual([NOT_INSTALLED]);
    expect(stand.container.textContent).not.toContain("is installed as");
    expect(asked(stand, "GET", GALLERY)).toBe(1);
  });
});

// ------------------------------------------------------------------------------- the readers

describe("reading what the API sends", () => {
  test("the readers name exactly the fields the routes declare", () => {
    // What breaks if this is deleted: a route that renames a field, and a gallery that draws a
    // card with a gap or a confirmation that reads no digest, with every test above green because
    // their stand-in spelled the old name.
    const gallery = declaredResponseSchema("/api/v1/agents/{agent_id}/automation-templates", "get");
    // `declaredProperty` follows an array's item reference, so this is one card's schema.
    const items = declaredProperty(gallery, "items");
    const shown = declaredResponseSchema(
      "/api/v1/agents/{agent_id}/automation-templates/{template_id}/preview",
      "get",
    );
    const installed = declaredResponseSchema("/api/v1/agents/{agent_id}/automations", "post", "201");
    const asking = declaredRequestBodySchema("/api/v1/agents/{agent_id}/automations", "post");

    expect(declaredPropertyNames(gallery)).toEqual(["installing", "items"]);
    expect(declaredPropertyNames(items)).toEqual(Object.keys(card("x_y_z", "I do a thing well")).sort());
    expect(declaredPropertyNames(shown)).toEqual(Object.keys(previewWire()).sort());
    expect(declaredPropertyNames(installed)).toEqual(
      expect.arrayContaining(["automation_id", "name"]),
    );
    expect(declaredPropertyNames(asking)).toEqual(
      Object.keys(installBody(readPreview(previewWire())!)).sort(),
    );
  });

  test("a card or a preview missing a fact the person relies on is not drawn at all", () => {
    // What breaks if this is deleted: a confirmation panel with a fact left out, which is a person
    // agreeing to something they were not shown, or a digest that is not one sent back as if it
    // were. The sibling is the whole preview reading back.
    const whole = readPreview(previewWire());
    const { schedule: _dropped, ...noSchedule } = card("weekly_work_summary", "I write you a summary");

    expect(whole?.confirmation).toBe(DIGEST);
    expect(readPreview({ ...previewWire(), confirmation: "yes" })).toBeNull();
    expect(readPreview({ ...previewWire(), runs_as: "" })).toBeNull();
    expect(readPreview({ ...previewWire(), reach: [1] })).toBeNull();
    expect(readPreview({ ...previewWire(), starts_paused: "true" })).toBeNull();
    expect(readPreview(previewWire([]))?.reach).toEqual([]);
    expect(readGallery({ items: [noSchedule], installing: "x" })?.cards).toEqual([]);
    expect(readGallery({ items: [] })).toBeNull();
    expect(readNotInstalled({ outcome: "unconfirmed" })).toBeNull();
    expect(REACHES_NOTHING).toContain("Nothing");
  });
});
