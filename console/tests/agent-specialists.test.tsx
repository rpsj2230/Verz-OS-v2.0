/**
 * An agent's Specialists card: the agents a coordinating agent may hand a subtask to, allowing and
 * taking one off, the fan-out switch, and asking it to split a request and reading how that went.
 * The shapes are read from `brain.coordination_routes` itself, so a renamed field fails here.
 *
 * Task ids: M18.5.1, M18.6.2
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ALLOW_IT,
  ASK_IT,
  CHOOSE_A_SPECIALIST,
  FAN_OUT_LABEL,
  GRANT_FAN_OUT_QUESTION,
  NO_SPECIALISTS,
  WITHDRAW_QUESTION,
} from "../src/pages/agents/AgentSpecialists";
import {
  agentCalleeRemovalsApiPath,
  agentCalleesApiPath,
  agentCoordinationApiPath,
  agentFanOutApiPath,
  childWords,
  COORDINATED_RUNS_API_PATH,
  modeWords,
  whyWords,
} from "../src/pages/agents/agentSpecialistsQuery";
import { ROSTER_API_PATH } from "../src/pages/agentsQuery";
import { json, mountPage, type Answer, type Mounted } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const AGENT = "quote-helper";
const VIEW = `GET /api/v1${agentCoordinationApiPath(AGENT)}`;
const ALLOW = `POST /api/v1${agentCalleesApiPath(AGENT)}`;
const WITHDRAW = `POST /api/v1${agentCalleeRemovalsApiPath(AGENT)}`;
const FAN = `POST /api/v1${agentFanOutApiPath(AGENT)}`;
const ASK = `POST /api/v1${COORDINATED_RUNS_API_PATH}`;
const ROSTER = `GET /api/v1${ROSTER_API_PATH}`;
const ROUTES = "src/brain/coordination_routes.py";
const ORCHESTRATION = "src/brain/orchestration_routes.py";

function view(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    agent_id: AGENT,
    names_shown: true,
    callees: [{ agent_id: "pricing", display_name: "Pricing desk" }],
    fan_out_enabled: false,
    may_change: true,
    switched_on: true,
    words: "WORDS-OF-THE-ROUTE",
    ...overrides,
  };
}

function roster(): Record<string, unknown> {
  return {
    items: [
      { agent_id: AGENT, display_name: "Quote helper" },
      { agent_id: "pricing", display_name: "Pricing desk" },
      { agent_id: "legal", display_name: "Legal reader" },
    ],
    truncated: false,
  };
}

function merged(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    values: { price: { total: "4200" } },
    reports: [{ subtask_id: "price", minor: 1200, seconds: 2.5 }],
    total_minor: 1200,
    currency: "SGD",
    complete: true,
    notice: "",
    ...overrides,
  };
}

function ran(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: "coordinated-1",
    mode: "sequential",
    why: ["fan_out_not_enabled"],
    gate: null,
    children: [{ subtask_id: "price", callee_id: "pricing", depth: 1, status: "delivered", seconds: 2.5 }],
    merged: merged(),
    cost_note: "COST-NOTE",
    ...overrides,
  };
}

async function card(answers: Record<string, Answer>): Promise<Mounted> {
  return mountPage(
    "/card",
    async () => {
      const { AgentSpecialists } = await import("../src/pages/agents/AgentSpecialists");
      return (
        <>
          <h1>Card</h1>
          <AgentSpecialists agentId={AGENT} name="Quote helper" />
        </>
      );
    },
    { [VIEW]: () => json(view()), [ROSTER]: () => json(roster()), ...answers },
  );
}

function posts(mounted: Mounted): { readonly path: string; readonly body: unknown }[] {
  return mounted.sent.filter((one) => one.method === "POST").map((one) => ({ path: one.path, body: one.body }));
}

describe("what the specialists card draws", () => {
  test("the specialists by their names, what a link is, and only the agents not yet allowed to choose from", async () => {
    // What breaks if this is deleted: ids drawn where names were sent, the route's sentence about what a
    // link confers dropped, or the coordinator offered itself or a specialist it already has.
    const { container } = await card({});
    expect(container.textContent).toContain("Pricing desk");
    expect(container.textContent).toContain("WORDS-OF-THE-ROUTE");
    const options = [...container.querySelectorAll("option")].map((one) => one.textContent);
    expect(options).toContain("Legal reader");
    expect(options).not.toContain("Pricing desk");
    expect(options).not.toContain("Quote helper");
  });

  test("an agent with none says how one is allowed, and a reader told no names is drawn no card", async () => {
    // What breaks if this is deleted: an empty card with no way forward, or a heading over nothing for
    // somebody who is not told what the agent may call.
    const empty = await card({ [VIEW]: () => json(view({ callees: [] })) });
    expect(empty.container.textContent).toContain(NO_SPECIALISTS);
    expect(empty.container.querySelector(`textarea`)).toBeNull();
    const hidden = await card({ [VIEW]: () => json(view({ names_shown: false, callees: [], may_change: false })) });
    expect(hidden.container.textContent).not.toContain("Specialists");
  });

  test("while the switch is off the ask is disabled and the server's own sentence is drawn", async () => {
    // What breaks if this is deleted: an ask the route refuses with a sentence the card never shows.
    const { container } = await card({ [VIEW]: () => json(view({ switched_on: false })) });
    await waitFor(() => {
      expect(container.textContent).toContain("handing a request between agents is switched off on this install");
    });
    fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "Quote a renewal" } });
    expect(within(container).getByRole("button", { name: ASK_IT }).hasAttribute("disabled")).toBe(true);
  });
});

describe("what the card sends", () => {
  test("an agent chosen is allowed, and the specialist named is withdrawn only after a confirmation", async () => {
    // What breaks if this is deleted: a link to another agent than the one chosen, or a specialist
    // removed on one press.
    const mounted = await card({ [ALLOW]: () => json(view()), [WITHDRAW]: () => json(view({ callees: [] })) });
    fireEvent.change(within(mounted.container).getByLabelText(CHOOSE_A_SPECIALIST), { target: { value: "legal" } });
    await act(async () => {
      fireEvent.click(within(mounted.container).getByRole("button", { name: ALLOW_IT }));
    });
    await waitFor(() => {
      expect(posts(mounted)).toEqual([{ path: `/api/v1${agentCalleesApiPath(AGENT)}`, body: { callee_id: "legal" } }]);
    });
    fireEvent.click(within(mounted.container).getByRole("button", { name: "Stop handing Pricing desk subtasks" }));
    const asking = await screen.findByRole("alertdialog", { name: WITHDRAW_QUESTION("Pricing desk") });
    expect(posts(mounted)).toHaveLength(1);
    await act(async () => {
      fireEvent.click(within(asking).getByRole("button", { name: "Withdraw it" }));
    });
    await waitFor(() => {
      expect(posts(mounted)[1]).toEqual({ path: `/api/v1${agentCalleeRemovalsApiPath(AGENT)}`, body: { callee_id: "pricing" } });
    });
  });

  test("running specialists together is asked for through a confirmation that says what it costs", async () => {
    // What breaks if this is deleted: a switch that spends the install's parallel room on one press.
    const mounted = await card({ [FAN]: () => json(view({ fan_out_enabled: true })) });
    fireEvent.click(within(mounted.container).getByLabelText(FAN_OUT_LABEL));
    const asking = await screen.findByRole("alertdialog", { name: GRANT_FAN_OUT_QUESTION("Quote helper") });
    expect(asking.textContent).toContain("costs more");
    expect(posts(mounted)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(asking).getByRole("button", { name: "Allow it" }));
    });
    await waitFor(() => {
      expect(posts(mounted)).toEqual([{ path: `/api/v1${agentFanOutApiPath(AGENT)}`, body: { enabled: true } }]);
    });
  });

  test("a request is sent as typed to the coordinator, and the plan, the children and the result are drawn", async () => {
    // What breaks if this is deleted: a request altered on the way, a run drawn as a bare word, a
    // missing specialist hidden, or a cost drawn without saying it is an estimate.
    const mounted = await card({ [ASK]: () => json(ran()) });
    fireEvent.change(mounted.container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "  Quote a renewal  " } });
    await act(async () => {
      fireEvent.click(within(mounted.container).getByRole("button", { name: ASK_IT }));
    });
    await waitFor(() => {
      expect(mounted.container.textContent).toContain(modeWords("sequential"));
    });
    const text = mounted.container.textContent ?? "";
    expect(text).toContain(whyWords("fan_out_not_enabled"));
    expect(text).toContain("handed to pricing");
    expect(text).toContain(childWords("delivered"));
    expect(text).toContain("total: 4200");
    expect(text).toContain("COST-NOTE");
    expect(text).toContain("Every specialist returned what it promised.");
    expect(posts(mounted)).toEqual([{ path: `/api/v1${COORDINATED_RUNS_API_PATH}`, body: { coordinator_id: AGENT, ask: "Quote a renewal" } }]);
  });

  test("a gap is stated and a refusal is the route's own sentence", async () => {
    // What breaks if this is deleted: a specialist that was turned away drawn as if it delivered, or a
    // refused request drawn as a success.
    const gap = await card({
      [ASK]: () =>
        json(
          ran({
            children: [{ subtask_id: "price", callee_id: "pricing", depth: 1, status: "refused", seconds: 0 }],
            merged: merged({ values: {}, complete: false, notice: "price: pricing could not be asked." }),
          }),
        ),
    });
    fireEvent.change(gap.container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "Quote" } });
    await act(async () => {
      fireEvent.click(within(gap.container).getByRole("button", { name: ASK_IT }));
    });
    await waitFor(() => {
      expect(gap.container.textContent).toContain("price: pricing could not be asked.");
    });
    expect(gap.container.textContent).toContain(childWords("refused"));
    expect(gap.container.textContent).not.toContain("Every specialist returned what it promised.");

    const refused = await card({ [ASK]: () => json({ outcome: "refused", sentence: "Nothing was started: no specialist is allowed here." }, 409) });
    fireEvent.change(refused.container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "Quote" } });
    await act(async () => {
      fireEvent.click(within(refused.container).getByRole("button", { name: ASK_IT }));
    });
    await screen.findByText("Nothing was started: no specialist is allowed here.");
  });
});

describe("the shapes", () => {
  test("every field the card reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.coordination_routes` that the card goes
    // on reading, which draws as an empty sentence in production.
    expect(Object.keys(view()).sort()).toEqual(backendModelFields(ROUTES, "CoordinationView").sort());
    expect(Object.keys(ran()).sort()).toEqual(backendModelFields(ROUTES, "CoordinationRunView").sort());
    expect(Object.keys(merged()).sort()).toEqual(backendModelFields(ORCHESTRATION, "MergedView").sort());
  });
});
