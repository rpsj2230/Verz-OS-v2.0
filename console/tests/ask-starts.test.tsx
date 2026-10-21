/**
 * How a member starts on Ask: a task or an agent, the agent's starters, and a skill to try.
 *
 * Mounted on the whole console at `/ask`, with the stand-in API answering the roster, the starters
 * and the trial route. The failures worth testing look like the page working: a task that names an
 * agent, a starter that asks for the person, a trial that sends a digest the page never checked.
 *
 * Task ids: M40.7.5, M40.7.8, M40.7.2
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, test } from "vitest";
import { ASK_ADDRESS, ASK_LABEL } from "../src/pages/Ask";
import { START_TASK, TALK_TO_AGENT } from "../src/pages/AskStart";
import { STARTERS_HEADING, startersApiPath } from "../src/pages/AskStarters";
import { TRIAL_NEEDS_AN_AGENT, tryApiPath } from "../src/pages/AskTrial";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";

const ORIGIN = "https://console.test";
const DIGEST = "a".repeat(64);
const ROSTER = { items: [{ agent_id: "helper", display_name: "Helper" }], truncated: false };

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}

function stream(): Response {
  const text = 'event: text\ndata: An answer.\n\nevent: done\ndata: \n\n';
  return new Response(text, { status: 200, headers: { "content-type": "text/event-stream" } });
}

async function screen(
  answers: Readonly<Record<string, unknown>>,
  entry = ASK_ADDRESS,
): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      const path = new URL(url, ORIGIN).pathname;
      if (path === "/api/v1/answer") return stream();
      if (path === "/api/v1/agents") return json(ROSTER);
      return path in answers ? json(answers[path]) : null;
    },
  });
  const loaded = await loadConsole({ idp, path: ASK_ADDRESS });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [entry] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) throw new Error("the page has not arrived");
  });
  return { container, idp };
}

function radio(container: HTMLElement, value: string): HTMLInputElement {
  const found = container.querySelector<HTMLInputElement>(`input[name="ask-start"][value="${value}"]`);
  if (!found) throw new Error(`no start choice ${value}`);
  return found;
}

async function rosterArrived(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector('input[name="ask-start"]')) throw new Error("no roster yet");
  });
}

function sent(idp: FakeIdp): unknown[] {
  return idp.calls
    .filter((call) => new URL(call.url, ORIGIN).pathname === "/api/v1/answer")
    .map((call) => (typeof call.init?.body === "string" ? (JSON.parse(call.init.body) as unknown) : null));
}

function ask(container: HTMLElement, question: string): void {
  fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: question } });
  const button = [...container.querySelectorAll("button")].find((one) => one.textContent === ASK_LABEL);
  fireEvent.click(button as HTMLButtonElement);
}

describe("starting a task or talking to an agent", () => {
  test("the page starts as a task, which names no agent, and shows no picker", async () => {
    // What breaks if this is deleted: a default that sends an agent nobody chose, or a picker
    // drawn before the person said they want to talk to one.
    const { container, idp } = await screen({});
    await rosterArrived(container);
    expect(radio(container, "task").checked).toBe(true);
    expect(container.textContent).toContain(START_TASK);
    expect(container.querySelector("select#ask-agent")).toBeNull();
    ask(container, "a task");
    await waitFor(() => {
      expect(sent(idp)).toHaveLength(1);
    });
    expect(sent(idp)[0]).toEqual({ question: "a task" });
  });

  test("choosing to talk to an agent shows the picker, and going back to a task forgets the agent", async () => {
    // What breaks if this is deleted: an agent chosen and then abandoned that still travels with
    // the next task, so the router is never asked.
    const { container, idp } = await screen({});
    await rosterArrived(container);
    fireEvent.click(radio(container, "agent"));
    expect(container.textContent).toContain(TALK_TO_AGENT);
    const picker = container.querySelector("select#ask-agent") as HTMLSelectElement;
    fireEvent.change(picker, { target: { value: "helper" } });
    fireEvent.click(radio(container, "task"));
    expect(container.querySelector("select#ask-agent")).toBeNull();
    ask(container, "back to a task");
    await waitFor(() => {
      expect(sent(idp)).toHaveLength(1);
    });
    expect(sent(idp)[0]).toEqual({ question: "back to a task" });
  });

  test("a person who may call no agent is offered no choice", async () => {
    // What breaks if this is deleted: a choice between two things when there is only one.
    const idp = fakeIdentityProvider({ api: () => null });
    const loaded = await loadConsole({ idp, path: ASK_ADDRESS });
    await signIn(loaded);
    const { routes } = await import("../src/App");
    const router = createMemoryRouter(routes, { initialEntries: [ASK_ADDRESS] });
    const { container } = render(<RouterProvider router={router} />);
    await waitFor(() => {
      if (!container.querySelector("h1")) throw new Error("the page has not arrived");
    });
    expect(container.querySelector('input[name="ask-start"]')).toBeNull();
  });
});

describe("an agent's starter prompts", () => {
  const starters = { prompts: ["First thing to ask?", "Second thing to ask?"] };

  test("pressing a starter puts it in the box and asks nothing", async () => {
    // What breaks if this is deleted: a starter that sends itself, so a person is asked to have
    // asked something they only read.
    const { container, idp } = await screen({ [`/api/v1${startersApiPath("helper")}`]: starters });
    await rosterArrived(container);
    fireEvent.click(radio(container, "agent"));
    fireEvent.change(container.querySelector("select#ask-agent") as HTMLSelectElement, {
      target: { value: "helper" },
    });
    await waitFor(() => {
      expect(container.textContent).toContain(STARTERS_HEADING);
    });
    const button = [...container.querySelectorAll(".ask__starters button")].find(
      (one) => one.textContent === "Second thing to ask?",
    ) as HTMLButtonElement;
    fireEvent.click(button);
    expect((container.querySelector("textarea") as HTMLTextAreaElement).value).toBe("Second thing to ask?");
    expect(sent(idp)).toEqual([]);
  });

  test("an empty list draws nothing, not a sentence about nothing", async () => {
    // What breaks if this is deleted: a line saying there are no starters, which tells a person
    // apart the agent with no examples from the one whose examples they may not run.
    const { container } = await screen({ [`/api/v1${startersApiPath("helper")}`]: { prompts: [] } });
    await rosterArrived(container);
    fireEvent.click(radio(container, "agent"));
    fireEvent.change(container.querySelector("select#ask-agent") as HTMLSelectElement, {
      target: { value: "helper" },
    });
    await new Promise((done) => setTimeout(done, 50));
    expect(container.textContent).not.toContain(STARTERS_HEADING);
  });
});

describe("trying a skill from its card", () => {
  const available = { available: true, name: "hosting-expiry", told: "" };
  const unavailable = { available: false, name: "", told: "THIS-CANNOT-BE-TRIED" };
  const address = `${ASK_ADDRESS}?skill=${DIGEST}`;

  test("a skill that can be tried is named, needs an agent, and its digest travels with the question", async () => {
    // What breaks if this is deleted: a skill tried without an agent to run through, or a digest
    // sent that the page never checked.
    const { container, idp } = await screen({ [`/api/v1${tryApiPath(DIGEST)}`]: available }, address);
    await waitFor(() => {
      expect(container.textContent).toContain("Trying the skill hosting-expiry");
    });
    expect(container.textContent).toContain(TRIAL_NEEDS_AN_AGENT);
    const field = container.querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: "try it" } });
    const button = [...container.querySelectorAll("button")].find(
      (one) => one.textContent === ASK_LABEL,
    ) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    await rosterArrived(container);
    expect(radio(container, "agent").checked).toBe(true);
    fireEvent.change(container.querySelector("select#ask-agent") as HTMLSelectElement, {
      target: { value: "helper" },
    });
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    await waitFor(() => {
      expect(sent(idp)).toHaveLength(1);
    });
    expect(sent(idp)[0]).toEqual({ question: "try it", agent: "helper", try_skill: DIGEST });
  });

  test("submitting the form while a skill waits for its agent sends nothing", async () => {
    // What breaks if this is deleted: the disabled button is the only thing stopping a skill
    // from being tried with no agent to run through, and a form can be submitted without it.
    const { container, idp } = await screen({ [`/api/v1${tryApiPath(DIGEST)}`]: available }, address);
    await waitFor(() => {
      expect(container.textContent).toContain("Trying the skill hosting-expiry");
    });
    fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "try it" } });
    fireEvent.submit(container.querySelector("form.ask__form") as HTMLFormElement);
    await new Promise((done) => setTimeout(done, 50));
    expect(sent(idp)).toEqual([]);
  });

  test("a skill that cannot be tried says one sentence and the question goes as any other", async () => {
    // What breaks if this is deleted: a digest sent for a skill the install refused, or a banner
    // that names a skill nobody approved.
    const { container, idp } = await screen({ [`/api/v1${tryApiPath(DIGEST)}`]: unavailable }, address);
    await waitFor(() => {
      expect(container.textContent).toContain("THIS-CANNOT-BE-TRIED");
    });
    expect(container.textContent).not.toContain("Trying the skill");
    ask(container, "an ordinary question");
    await waitFor(() => {
      expect(sent(idp)).toHaveLength(1);
    });
    expect(sent(idp)[0]).toEqual({ question: "an ordinary question" });
  });
});
