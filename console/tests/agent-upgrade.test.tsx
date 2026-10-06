/**
 * An agent's newer template version on its Profile: the changes it brings, an answer for every one
 * this install had made, and an upgrade or a decline, each confirmed and each sent with what the page
 * drew.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that records
 * every request, as `agent-memory.test.tsx` mounts it.
 *
 * Task ids: M13.4.2, M13.4.3, M13.4.4, M13.4.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { viewAddress } from "../src/pages/agents/AgentDetailPage";
import { ANSWER_EVERY_CONFLICT, agentUpgradeAcceptApiPath, agentUpgradeApiPath, agentUpgradeDeclineApiPath, hasAnOffer, readUpgrade, valueWords } from "../src/pages/agents/agentUpgradeQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";
const ADDRESS = viewAddress(AGENT, "profile");
const HASH = "a".repeat(64);

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

function workspaceWire(): unknown {
  return {
    agent: { agent_id: AGENT, display_name: "Quote Helper", owner_id: "p_steward", created_at: "2019-03-01T09:00:00Z" },
    tabs: ["settings"].map((tab) => ({ tab, label: tab, purpose: "x" })),
    composition: [],
    skills: [],
    connectors: { shown: [], overflow: 0 },
    channels: [],
    headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false },
  };
}

function reviewWire(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    agent_id: AGENT,
    display_name: "Quote Helper",
    badge: "available",
    from_version: 2,
    to_version: 3,
    expected_hash: HASH,
    conflicts: [
      {
        path: "persona",
        where: "Instructions",
        was: "Answer briefly.",
        now: "Answer in full sentences.",
        local: "Answer briefly, and name the invoice.",
        owner: { source: "instance", set_by: "p_steward", set_at: "2019-03-02T09:00:00Z" },
      },
    ],
    updates: [
      { path: "tier", where: "Model", was: "main", now: "heavy", sealed: false },
      { path: "guardrails.max_side_effect", where: "Supervision", was: "none", now: "draft", sealed: true },
    ],
    accept_unavailable: null,
    nothing: null,
    ...extra,
  };
}

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

async function consoleAt(answers: Readonly<Record<string, Answer>>): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const answer = answers[`${method} ${pathname}`] ?? (method === "GET" ? answers[pathname] : undefined);
      return answer === undefined
        ? null
        : new Response(JSON.stringify(answer.body), { status: answer.status ?? 200, headers: { "content-type": "application/json" } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [ADDRESS] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector('[data-slot="section-card"]')) {
      throw new Error("the Profile has not arrived");
    }
  });
  return { container, idp };
}

function answers(upgrade: Answer, extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`/api/v1${agentUpgradeApiPath(AGENT)}`]: upgrade,
    ...extra,
  };
}

function posts(idp: FakeIdp): FakeIdp["calls"] {
  return idp.calls.filter((one) => one.init?.method === "POST" && one.url.includes("/api/v1/"));
}

function card(container: HTMLElement): HTMLElement | null {
  return [...container.querySelectorAll<HTMLElement>('[data-slot="section-card"]')].find((one) =>
    (one.textContent ?? "").includes("A newer version of this agent's template"),
  ) ?? null;
}

function button(within: ParentNode, label: string): HTMLButtonElement {
  return [...within.querySelectorAll("button")].find((one) => one.textContent === label) as HTMLButtonElement;
}

async function waitForCard(container: HTMLElement): Promise<HTMLElement> {
  return waitFor(() => {
    const found = card(container);
    if (found === null) {
      throw new Error("the upgrade card has not arrived");
    }
    return found;
  });
}

async function confirm(label: string): Promise<void> {
  const dialog = await waitFor(() => {
    const found = document.querySelector('[role="alertdialog"]');
    if (found === null) {
      throw new Error("no confirmation opened");
    }
    return found;
  });
  await act(async () => {
    fireEvent.click([...dialog.querySelectorAll("button")].find((one) => one.textContent === label) as Element);
  });
}

describe("a newer version on the Profile", () => {
  test("it draws the three columns of a conflict and what else changes, marking what only the publisher sets", async () => {
    // What breaks if this is deleted: a conflict drawn without the value set here, or a change an
    // install can never override drawn like any other.
    const { container } = await consoleAt(answers({ body: reviewWire() }));
    const shown = await waitForCard(container);
    const text = shown.textContent ?? "";
    expect(text).toContain("Version 2 is running. Version 3 is on offer.");
    expect(text).toContain("Answer briefly.");
    expect(text).toContain("Answer in full sentences.");
    expect(text).toContain("Answer briefly, and name the invoice.");
    expect(text).toContain("Model");
    expect(text).toContain("set by the publisher");
    expect(shown.querySelectorAll('input[type="radio"]')).toHaveLength(2);
  });

  test("a version nobody has said no to is a badge in the header, and one somebody turned away is not", async () => {
    // What breaks if this is deleted: M13.4.2's badge never drawn, or drawn for a version the page
    // was told not to nag about.
    const available = await consoleAt(answers({ body: reviewWire() }));
    await waitForCard(available.container);
    expect(available.container.querySelector('[data-slot="upgrade-pill"]')?.textContent).toBe("Version 3 available");
    const declined = await consoleAt(answers({ body: reviewWire({ badge: "declined" }) }));
    const shown = await waitForCard(declined.container);
    expect(shown.textContent).toContain("You said no to it before.");
    expect(declined.container.querySelector('[data-slot="upgrade-pill"]')).toBeNull();
  });

  test("the upgrade waits until every conflict has an answer, says why, and sends the answers with what was drawn", async () => {
    // What breaks if this is deleted: an upgrade pressed with a conflict decided by default, or sent
    // without the version and digest the page was drawn against.
    const { container, idp } = await consoleAt(
      answers({ body: reviewWire() }, { [`POST /api/v1${agentUpgradeAcceptApiPath(AGENT)}`]: { body: { agent_id: AGENT, outcome: "upgraded" } } }),
    );
    const shown = await waitForCard(container);
    expect(button(shown, "Upgrade").disabled).toBe(true);
    expect(shown.textContent).toContain(ANSWER_EVERY_CONFLICT);
    await act(async () => {
      fireEvent.click(shown.querySelectorAll('input[type="radio"]')[1] as Element);
    });
    expect(button(shown, "Upgrade").disabled).toBe(false);
    await act(async () => {
      fireEvent.click(button(shown, "Upgrade"));
    });
    expect(posts(idp)).toEqual([]);
    await confirm("Upgrade");
    const [sent] = posts(idp);
    expect(sent?.url).toContain(agentUpgradeAcceptApiPath(AGENT));
    expect(JSON.parse(String(sent?.init?.body))).toEqual({
      to_version: 3,
      expected_hash: HASH,
      resolutions: { persona: "take_template" },
    });
  });

  test("a version the API says cannot be accepted shows its sentence, cannot be upgraded to, and can still be turned down", async () => {
    // What breaks if this is deleted: an upgrade offered for a version the API refuses, or a
    // version that cannot be accepted that cannot be declined either.
    const refusal = "This version holds an action at a higher rung than this agent is on.";
    const { container, idp } = await consoleAt(
      answers(
        { body: reviewWire({ accept_unavailable: refusal }) },
        { [`POST /api/v1${agentUpgradeDeclineApiPath(AGENT)}`]: { body: { agent_id: AGENT, outcome: "declined" } } },
      ),
    );
    const shown = await waitForCard(container);
    expect(shown.textContent).toContain(refusal);
    await act(async () => {
      fireEvent.click(shown.querySelectorAll('input[type="radio"]')[0] as Element);
    });
    expect(button(shown, "Upgrade").disabled).toBe(true);
    expect(button(shown, "Not this version").disabled).toBe(false);
    await act(async () => {
      fireEvent.click(button(shown, "Not this version"));
    });
    expect(posts(idp)).toEqual([]);
    await confirm("Not this version");
    const [sent] = posts(idp);
    expect(sent?.url).toContain(agentUpgradeDeclineApiPath(AGENT));
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ to_version: 3, expected_hash: HASH });
  });

  test("a stale page is told in the API's own sentence and nothing else is claimed", async () => {
    // What breaks if this is deleted: a 409 drawn as a success, or as a sentence nobody sent.
    const sentence = "This agent, or the version on offer, changed after you opened it, so nothing was changed.";
    const { container } = await consoleAt(
      answers(
        { body: reviewWire({ conflicts: [] }) },
        { [`POST /api/v1${agentUpgradeAcceptApiPath(AGENT)}`]: { status: 409, body: { outcome: "moved", sentence } } },
      ),
    );
    const shown = await waitForCard(container);
    await act(async () => {
      fireEvent.click(button(shown, "Upgrade"));
    });
    await confirm("Upgrade");
    await waitFor(() => {
      expect(container.textContent).toContain(sentence);
    });
    expect(container.textContent).not.toContain("Upgraded");
  });

  test("an agent on the newest version, a declined one the reader may not act on, and one with no install draw no card", async () => {
    // What breaks if this is deleted: a card for an agent with nothing to upgrade, or a sentence
    // that tells a reader who may not act that an agent exists.
    for (const upgrade of [
      { body: reviewWire({ badge: "current", to_version: null, expected_hash: null, conflicts: [], updates: [] }) },
      { status: 404, body: { message: "no agent is answerable for this caller", outcome: "absent" } },
      { body: reviewWire({ badge: "current", from_version: 1, to_version: null, expected_hash: null, conflicts: [], updates: [], nothing: "no install" }) },
    ]) {
      const { container } = await consoleAt(answers(upgrade));
      expect(card(container)).toBeNull();
      expect(container.textContent).not.toContain("A newer version of this agent's template");
    }
  });

  test("the routes the card asks are declared, and a half-sent review is left out", () => {
    // What breaks if this is deleted: a path spelled differently from the route, or a review with
    // no version to name treated as an offer.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toEqual(
      expect.arrayContaining([
        "/api/v1/agents/{agent_id}/upgrade",
        "/api/v1/agents/{agent_id}/upgrade/accept",
        "/api/v1/agents/{agent_id}/upgrade/decline",
      ]),
    );
    expect(readUpgrade({ agent_id: AGENT })).toBeNull();
    expect(hasAnOffer(readUpgrade(reviewWire({ badge: "current", to_version: null, expected_hash: null })))).toBe(false);
    expect(hasAnOffer(readUpgrade(reviewWire()))).toBe(true);
    expect(valueWords(["a", "b"])).toBe("a, b");
    expect(valueWords("")).toBe("nothing");
  });
});
