/**
 * What an agent's Profile offers beside its tools: who else can find it, whether it learns, which
 * of its skills no run uses, and the channels it could answer on with each one's state.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that records
 * every request, as `agent-capabilities.test.tsx` mounts it, so a deleted route or reader fails here.
 *
 * **Every refusal has a sibling proving the thing works.** A reader the audience route tells nothing
 * is drawn no row, and the same row is drawn when it is sent; a blank reason sends nothing and a
 * given one sends the pause; a skill nothing stops is not described, and a stopped one is, in the
 * API's sentence.
 *
 * Task ids: M27.11.12, M27.11.13, M27.11.14, M27.15.32
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  A_PERSONS_ID,
  ALSO_OFFERED_TO,
  CHOOSE_A_DEPARTMENT,
  NOT_OFFERED_FURTHER,
  OFFER_IT_TO,
  OFFER_LABEL,
  OFFER_QUESTION,
  WITHDRAW_QUESTION,
} from "../src/pages/agents/AgentAudience";
import { CONNECTORS_ON_THE_ROW } from "../src/pages/agents/AgentCapabilities";
import {
  LEARNING_NOT_CHANGED,
  LEARNING_OFF,
  LEARNING_ON,
  LEARNING_SWITCH_LABEL,
  PAUSE_QUESTION,
  REASON_NEEDED,
  RESUME_QUESTION,
} from "../src/pages/agents/AgentLearning";
import { agentAudienceApiPath, agentOfferApiPath, agentWithdrawApiPath, offerBody, readAudience } from "../src/pages/agents/agentAudienceQuery";
import { agentCapabilitiesApiPath, readAgentCapabilities } from "../src/pages/agents/agentCapabilitiesQuery";
import { agentLearningApiPath, learningBody, readLearning } from "../src/pages/agents/agentLearningQuery";
import { agentStatsApiPath } from "../src/pages/agents/agentStats";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredPropertyNames, declaredProperty, declaredRequestBodySchema, declaredResponseSchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";
const PROFILE = `/agents/${AGENT}/profile`;
const DIGEST = "a".repeat(64);

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

function audienceWire(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    agent_id: AGENT,
    level: "department",
    department: "sales",
    owner_id: "p_steward_one",
    names_shown: true,
    departments: ["support"],
    people: ["p_colleague"],
    may_change: true,
    refusal: null,
    department_choices: ["sales", "support", "web"],
    words: "An offer only makes the agent appear and start for them.",
    ...extra,
  };
}

const AUDIENCE_API = `/api/v1${agentAudienceApiPath(AGENT)}`;
const OFFER_API = `/api/v1${agentOfferApiPath(AGENT)}`;
const WITHDRAW_API = `/api/v1${agentWithdrawApiPath(AGENT)}`;
const LEARNING_API = `/api/v1${agentLearningApiPath(AGENT)}`;

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

function base(extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`/api/v1${agentStatsApiPath(AGENT)}`]: { body: { agent_id: AGENT, periods: [], unrecorded: [] } },
    "/api/v1/routing/rungs": { body: { items: [], next_cursor: null, truncated: false } },
    ...extra,
  };
}

/** The writes the page sent to the API, leaving out the identity provider's own token requests. */
function apiPosts(idp: FakeIdp): FakeIdp["calls"] {
  return idp.calls.filter((one) => one.init?.method === "POST" && one.url.includes("/api/v1/"));
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

function dialogNow(): HTMLElement {
  const found = document.querySelector<HTMLElement>('[role="alertdialog"]');
  if (found === null) {
    throw new Error("no confirmation is open");
  }
  return found;
}

async function press(label: string | RegExp, within_: HTMLElement | Document = document): Promise<void> {
  const target = within(within_ instanceof Document ? within_.body : within_).getByRole("button", { name: label });
  await act(async () => {
    fireEvent.click(target);
  });
}

// ------------------------------------------------------------------- who else can find it
describe("who else can find the agent", () => {
  test("the steward sees the departments and people beside the level and withdraws one through a confirmation", async () => {
    // What breaks if this is deleted: M27.11.13's remove. The rows missing, a withdrawal sent with no
    // confirmation naming who loses the agent, or a body that names something other than the row.
    const mounted = await consoleAt(
      PROFILE,
      base({
        [AUDIENCE_API]: { body: audienceWire() },
        [`POST ${WITHDRAW_API}`]: { body: audienceWire({ departments: [] }) },
      }),
    );
    const card = await drawn(mounted.container, "agent-audience");
    expect(card.textContent).toContain("support department");
    expect(card.textContent).toContain("p_colleague");
    await press("Withdraw this agent from the support department");
    expect(apiPosts(mounted.idp)).toHaveLength(0);
    expect(dialogNow().textContent).toContain(WITHDRAW_QUESTION("the support department"));
    await press("Withdraw it", dialogNow());
    await waitFor(() => {
      expect(apiPosts(mounted.idp)).toHaveLength(1);
    });
    const posted = apiPosts(mounted.idp)[0];
    expect(posted?.url).toContain(WITHDRAW_API);
    expect(JSON.parse(String(posted?.init?.body))).toEqual({ kind: "department", value: "support" });
  });

  test("a department is offered by choosing it, a person by typing their id, and each is confirmed first", async () => {
    // What breaks if this is deleted: M27.11.13's add. An offer sent without the confirmation, a
    // blank sent at all, or a body naming the wrong kind.
    const mounted = await consoleAt(
      PROFILE,
      base({
        [AUDIENCE_API]: { body: audienceWire({ departments: [], people: [] }) },
        [`POST ${OFFER_API}`]: { body: audienceWire({ departments: ["web"], people: [] }) },
      }),
    );
    const card = await drawn(mounted.container, "agent-audience");
    expect(card.textContent).toContain(NOT_OFFERED_FURTHER);
    // Asked again after each write, so the row is found again each time rather than held.
    const offerRow = async (): Promise<HTMLElement> =>
      (await waitFor(() => {
        const found = [...mounted.container.querySelectorAll("[data-slot=fact]")].find((one) => one.textContent?.startsWith(OFFER_IT_TO));
        if (found === undefined) {
          throw new Error("no offer row");
        }
        return found;
      })) as HTMLElement;
    const row = await offerRow();
    const offer = within(row).getByRole("button", { name: OFFER_LABEL }) as HTMLButtonElement;
    expect(offer.disabled).toBe(true);
    const department = within(row).getByLabelText(CHOOSE_A_DEPARTMENT) as HTMLSelectElement;
    await act(async () => {
      fireEvent.change(department, { target: { value: "web" } });
    });
    expect(offer.disabled).toBe(false);
    await press(OFFER_LABEL, row);
    expect(apiPosts(mounted.idp)).toHaveLength(0);
    expect(dialogNow().textContent).toContain(OFFER_QUESTION("the web department"));
    await press("Offer it", dialogNow());
    await waitFor(() => {
      expect(apiPosts(mounted.idp)).toHaveLength(1);
    });
    expect(JSON.parse(String(apiPosts(mounted.idp)[0]?.init?.body))).toEqual({ kind: "department", value: "web" });

    // A person: the kind changes, the field is a typed id, and a name with a space cannot be sent.
    const again = await offerRow();
    await act(async () => {
      fireEvent.change(within(again).getByLabelText("A department or a person"), { target: { value: "person" } });
    });
    const typed = within(again).getByLabelText(A_PERSONS_ID) as HTMLInputElement;
    await act(async () => {
      fireEvent.change(typed, { target: { value: "two words" } });
    });
    expect((within(again).getByRole("button", { name: OFFER_LABEL }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      fireEvent.change(typed, { target: { value: "p_new_person" } });
    });
    await press(OFFER_LABEL, again);
    await press("Offer it", dialogNow());
    await waitFor(() => {
      expect(apiPosts(mounted.idp)).toHaveLength(2);
    });
    expect(JSON.parse(String(apiPosts(mounted.idp)[1]?.init?.body))).toEqual({ kind: "person", value: "p_new_person" });
  });

  test("a refusal is the route's own sentence, and nothing is said to have changed", async () => {
    // What breaks if this is deleted: a 409 drawn as done, so an administrator believes a department
    // was given an agent the install had refused to offer it.
    const sentence = "Nothing was changed: that is not a department on this install.";
    const mounted = await consoleAt(
      PROFILE,
      base({
        [AUDIENCE_API]: { body: audienceWire() },
        [`POST ${WITHDRAW_API}`]: { status: 409, body: { outcome: "refused", sentence } },
      }),
    );
    await drawn(mounted.container, "agent-audience");
    await press("Withdraw this agent from the support department");
    await press("Withdraw it", dialogNow());
    await waitFor(() => {
      expect(mounted.container.textContent).toContain(sentence);
    });
  });

  test("a reader sent no names is drawn no row and no control, and the same rows appear when they are sent", async () => {
    // What breaks if this is deleted: a row saying nobody else was named, which is a statement a
    // reader who answers for nothing was never told, so DENIED and ABSENT stop being one answer.
    const quiet = await consoleAt(
      PROFILE,
      base({
        [AUDIENCE_API]: { body: audienceWire({ names_shown: false, departments: [], people: [], may_change: false, department_choices: [] }) },
      }),
    );
    await waitFor(() => {
      expect(quiet.container.querySelector('[data-slot="agent-profile"]')).not.toBeNull();
    });
    expect(quiet.container.textContent).not.toContain(ALSO_OFFERED_TO);
    expect(quiet.container.textContent).not.toContain(OFFER_IT_TO);
    expect(quiet.container.querySelector('[data-slot="agent-audience"]')).toBeNull();
    const told = await consoleAt(PROFILE, base({ [AUDIENCE_API]: { body: audienceWire({ may_change: false, department_choices: [] }) } }));
    await drawn(told.container, "agent-audience");
    expect(told.container.textContent).toContain(ALSO_OFFERED_TO);
  });

  test("a holder who may not change the offers is told why in the route's sentence, with no control", async () => {
    // What breaks if this is deleted: a control drawn for an agent that takes no offer, or a refusal
    // left to the press, which is a button that agrees to something and then says no.
    const why = "Nothing was changed: offering an agent to more departments and people is not switched on for this company yet.";
    const mounted = await consoleAt(
      PROFILE,
      base({ [AUDIENCE_API]: { body: audienceWire({ may_change: false, refusal: why, department_choices: [] }) } }),
    );
    await drawn(mounted.container, "agent-audience");
    expect(mounted.container.textContent).toContain(why);
    expect(mounted.container.textContent).not.toContain(OFFER_IT_TO);
    expect(within(mounted.container).queryByRole("button", { name: /Withdraw this agent from/ })).toBeNull();
  });

  test("the audience is read as sent, and a body missing its required parts reads as absent", () => {
    // What breaks if this is deleted: a card drawn from half a body, which is an audience described
    // with its steward missing.
    for (const noise of [null, [], "audience", 7, { agent_id: "x" }]) {
      expect(readAudience(noise)).toBeNull();
    }
    const read = readAudience(audienceWire());
    expect(read?.departments).toEqual(["support"]);
    expect(read?.mayChange).toBe(true);
    expect(read?.refusal).toBeUndefined();
    expect(offerBody("person", "  p_x  ")).toEqual({ kind: "person", value: "p_x" });
  });

  test("the audience routes and the fields read are the ones the API document declares", () => {
    // What breaks if this is deleted: a field renamed on one side and read as absent on the other,
    // so the card goes quiet and nothing fails.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const wanted of ["/api/v1/agents/{agent_id}/audience", "/api/v1/agents/{agent_id}/audience/additions", "/api/v1/agents/{agent_id}/audience/removals"]) {
      expect(paths).toContain(wanted);
    }
    const declared = declaredPropertyNames(declaredResponseSchema("/api/v1/agents/{agent_id}/audience", "get"));
    for (const field of Object.keys(audienceWire())) {
      expect(declared, field).toContain(field);
    }
    const asked = declaredPropertyNames(declaredRequestBodySchema("/api/v1/agents/{agent_id}/audience/additions", "post"));
    expect(asked).toEqual(Object.keys(offerBody("person", "x")).sort());
  });
});

// ------------------------------------------------------------------------ learning
describe("the learning switch", () => {
  test("it reads on, pausing needs a reason and is confirmed, and the pause is sent with that reason", async () => {
    // What breaks if this is deleted: M27.11.14's switch. A pause with no reason sent, a pause sent
    // with no confirmation, or a switch that reads the opposite of what the route said.
    const mounted = await consoleAt(
      PROFILE,
      base({
        [LEARNING_API]: { body: { agent_id: AGENT, paused: false } },
        [`POST ${LEARNING_API}`]: { body: { agent_id: AGENT, paused: true } },
      }),
    );
    const area = await drawn(mounted.container, "agent-learning-switch");
    expect(area.textContent).toContain(LEARNING_ON);
    const toggle = within(area as HTMLElement).getByRole("switch", { name: LEARNING_SWITCH_LABEL });
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    await act(async () => {
      fireEvent.click(toggle);
    });
    expect(apiPosts(mounted.idp)).toHaveLength(0);
    expect(dialogNow().textContent).toContain(PAUSE_QUESTION("Quote Helper"));
    // Blank: said beside the field, and nothing is sent.
    await press("Pause it", dialogNow());
    expect(dialogNow().textContent).toContain(REASON_NEEDED);
    expect(apiPosts(mounted.idp)).toHaveLength(0);
    await act(async () => {
      fireEvent.change(within(dialogNow()).getByLabelText("Why"), { target: { value: "a wrong lesson" } });
    });
    await press("Pause it", dialogNow());
    await waitFor(() => {
      expect(apiPosts(mounted.idp)).toHaveLength(1);
    });
    const posted = apiPosts(mounted.idp)[0];
    expect(posted?.url).toContain(LEARNING_API);
    expect(JSON.parse(String(posted?.init?.body))).toEqual({ paused: true, reason: "a wrong lesson" });
  });

  test("a paused agent reads paused and is resumed through its own confirmation with a reason", async () => {
    // What breaks if this is deleted: the way back. A pause nothing in the page can undo.
    const mounted = await consoleAt(
      PROFILE,
      base({
        [LEARNING_API]: { body: { agent_id: AGENT, paused: true } },
        [`POST ${LEARNING_API}`]: { body: { agent_id: AGENT, paused: false } },
      }),
    );
    const area = await drawn(mounted.container, "agent-learning-switch");
    expect(area.textContent).toContain(LEARNING_OFF);
    const toggle = within(area as HTMLElement).getByRole("switch", { name: LEARNING_SWITCH_LABEL });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    await act(async () => {
      fireEvent.click(toggle);
    });
    expect(dialogNow().textContent).toContain(RESUME_QUESTION("Quote Helper"));
    await act(async () => {
      fireEvent.change(within(dialogNow()).getByLabelText("Why"), { target: { value: "fixed at source" } });
    });
    await press("Resume it", dialogNow());
    await waitFor(() => {
      expect(apiPosts(mounted.idp)).toHaveLength(1);
    });
    expect(JSON.parse(String(apiPosts(mounted.idp)[0]?.init?.body))).toEqual({ paused: false, reason: "fixed at source" });
  });

  test("a reader the route refuses is drawn no switch, and a refusal on the write is said", async () => {
    // What breaks if this is deleted: a switch drawn for somebody who may not press it, or a state of
    // "on" inferred from a 404, which tells them learning is running when they were told nothing.
    const refused = await consoleAt(PROFILE, base({ [LEARNING_API]: { status: 404, body: { message: "No such agent." } } }));
    await waitFor(() => {
      expect(refused.container.querySelector('[data-slot="agent-profile"]')).not.toBeNull();
    });
    expect(refused.container.querySelector('[data-slot="agent-learning-switch"]')).toBeNull();
    expect(refused.container.textContent).not.toContain(LEARNING_ON);

    const failing = await consoleAt(
      PROFILE,
      base({
        [LEARNING_API]: { body: { agent_id: AGENT, paused: false } },
        [`POST ${LEARNING_API}`]: { status: 404, body: { message: "No agent is answerable for this caller." } },
      }),
    );
    const area = await drawn(failing.container, "agent-learning-switch");
    await act(async () => {
      fireEvent.click(within(area as HTMLElement).getByRole("switch", { name: LEARNING_SWITCH_LABEL }));
    });
    await act(async () => {
      fireEvent.change(within(dialogNow()).getByLabelText("Why"), { target: { value: "x" } });
    });
    await press("Pause it", dialogNow());
    await waitFor(() => {
      expect(failing.container.textContent).toContain(LEARNING_NOT_CHANGED);
    });
    expect(area.textContent).toContain(LEARNING_ON);
  });

  test("the switch reads and sends exactly the fields the API document declares", () => {
    // What breaks if this is deleted: a renamed field read as absent, so the switch reads on for an
    // agent that is paused.
    const declared = declaredPropertyNames(declaredResponseSchema("/api/v1/agents/{agent_id}/learning", "get"));
    expect(declared).toEqual(["agent_id", "paused"]);
    expect(declaredPropertyNames(declaredRequestBodySchema("/api/v1/agents/{agent_id}/learning", "post"))).toEqual(
      Object.keys(learningBody(true, " why ")).sort(),
    );
    expect(readLearning({ agent_id: "x", paused: true })).toEqual({ agentId: "x", paused: true });
    for (const noise of [null, [], { agent_id: "x" }, { agent_id: "", paused: true }, { paused: true }]) {
      expect(readLearning(noise)).toBeNull();
    }
    expect(learningBody(true, " why ")).toEqual({ paused: true, reason: "why" });
  });
});

// ----------------------------------------------------------------- skills and the rest
function detail(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    agent_id: AGENT,
    availability: { level: "department", department: "sales", owner_id: "p_steward_one", reader_is_included: true, words: "Discovery, not access." },
    connectors: [],
    skills: [
      { name: "quote-draft", digest: DIGEST, version: "1.2.0", source: "upload", review: "approved", runs: 7, detachable: true },
      {
        name: "waiting-skill",
        digest: "b".repeat(64),
        version: "0.1.0",
        source: "upload",
        review: "pending",
        runs: 0,
        detachable: true,
        not_used_because: "A person has not reviewed this skill yet, so no run uses it.",
      },
    ],
    unused_skills: [],
    usage_basis: "everyone",
    skills_editable: true,
    offers: [],
    computer_use: { offered: false, sentence: "Not offered. No desktop runner." },
    ...extra,
  };
}

describe("skills and channels", () => {
  test("a skill no run could use is listed with the API's sentence, and one nothing stops is not described", async () => {
    // What breaks if this is deleted: M27.11.12's "says plainly where an assigned skill does not yet
    // change a run". A sentence typed in the page that is false for every skill a run does offer, or
    // one missing for a skill that waits for review.
    const mounted = await consoleAt(PROFILE, base({ [`/api/v1${agentCapabilitiesApiPath(AGENT)}`]: { body: detail() } }));
    const notes = await drawn(mounted.container, "skill-not-used");
    expect(notes.textContent).toContain("waiting-skill");
    expect(notes.textContent).toContain("A person has not reviewed this skill yet, so no run uses it.");
    expect(notes.textContent).not.toContain("quote-draft");
    expect(mounted.container.textContent).not.toContain("changes no answer today");
  });

  test("with every skill unstopped there is no list of stopped ones", async () => {
    // The sibling: a heading over nothing says there was something to list.
    const mounted = await consoleAt(
      PROFILE,
      base({
        [`/api/v1${agentCapabilitiesApiPath(AGENT)}`]: {
          body: detail({ skills: [{ name: "quote-draft", digest: DIGEST, version: "1.2.0", source: "upload", review: "approved", runs: 7, detachable: true }] }),
        },
      }),
    );
    await drawn(mounted.container, "skill-detail");
    expect(mounted.container.querySelector('[data-slot="skill-not-used"]')).toBeNull();
  });

  test("a long list of skills keeps its first five and opens the rest as the reader's own", async () => {
    // What breaks if this is deleted: M27.11.12's overflow list for skills, which pushed a card of a
    // dozen chips down the page.
    const skills = Array.from({ length: CONNECTORS_ON_THE_ROW + 2 }, (_, n) => ({
      name: `skill${String(n)}`,
      digest: String(n).repeat(64).slice(0, 64),
      version: "1.0.0",
      source: "upload",
      review: "approved",
      runs: 0,
      detachable: false,
    }));
    const mounted = await consoleAt(PROFILE, base({ [`/api/v1${agentCapabilitiesApiPath(AGENT)}`]: { body: detail({ skills }) } }));
    const row = await drawn(mounted.container, "skill-detail");
    expect(row.querySelectorAll('[data-slot="skill-chip"]')).toHaveLength(CONNECTORS_ON_THE_ROW);
    await press("2 more", row as HTMLElement);
    expect(row.querySelectorAll('[data-slot="skill-chip"]')).toHaveLength(CONNECTORS_ON_THE_ROW + 2);
  });

  test("the detail reads a skill's sentence and the computer use words as sent, and nothing when they are not", () => {
    // What breaks if this is deleted: M27.15.32's words read off a different field than the API
    // sends, so the page says nothing about computer use while the API says it.
    const read = readAgentCapabilities(detail());
    expect(read?.skills[1]?.notUsedBecause).toBe("A person has not reviewed this skill yet, so no run uses it.");
    expect(read?.skills[0]?.notUsedBecause).toBeUndefined();
    expect(read?.computerUse).toEqual({ offered: false, sentence: "Not offered. No desktop runner." });
    expect(readAgentCapabilities(detail({ computer_use: { offered: "no" } }))?.computerUse).toBeUndefined();
    const view = declaredResponseSchema("/api/v1/agents/{agent_id}/capabilities", "get");
    expect(declaredPropertyNames(view)).toContain("computer_use");
    expect(declaredPropertyNames(declaredProperty(view, "computer_use"))).toEqual(["offered", "sentence"]);
    const skills = declaredProperty(view, "skills");
    expect(declaredPropertyNames(skills)).toContain("not_used_because");
  });
});
