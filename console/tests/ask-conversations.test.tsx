/**
 * A person's conversations on Ask: a follow-up continues the thread the answer was kept in, the
 * conversations are listed wherever each was asked, searched by the person's own words, and one is
 * reopened with what the API sent of it.
 *
 * **Driven through the application's own route table**, signed in through the real session modules,
 * against a stand-in API answering `POST /api/v1/answer` with a stream and the `x-thread-id` header
 * `brain.api_routes.THREAD_HEADER` names, and `GET /api/v1/threads...` with the bodies
 * `brain.thread_routes` declares. The header's name is read out of the Python source, so a rename
 * there fails here.
 *
 * A wrong answer is marked with a kind and no words, at `POST /api/v1/threads/{id}/corrections`,
 * whose kinds are the API schema's own, and a reopened thread says so in words.
 *
 * Task ids: M9.1.1, M9.1.2, M9.1.3, M9.2.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { EVENT_STREAM } from "../src/api/events";
import {
  ASK_ADDRESS,
  ASK_LABEL,
  CONTINUING,
  CONVERSATIONS_HEADING,
  MARK_WRONG,
  MARKED_WRONG,
  NEW_CONVERSATION,
  NOT_MARKED,
  NOTHING_FOUND_IN_CONVERSATIONS,
  SEARCH_LABEL,
  WAS_IT_WRONG,
} from "../src/pages/Ask";
import {
  correctionPath,
  CORRECTION_PREFIX,
  CORRECTION_WORDS,
  THREAD_HEADER,
  THREAD_SEARCH_API_PATH,
  THREADS_API_PATH,
  threadPath,
} from "../src/pages/threadsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { readRepoFile } from "./support/repo";

const ORIGIN = "https://console.test";
const API = "/api/v1";
const THREAD = "3a0f5c2e-1b4d-4e6f-8a9b-0c1d2e3f4a5b";
const LARK_THREAD = "9f8e7d6c-5b4a-4938-8271-605f4e3d2c1b";
const QUESTION = "what does the handover checklist say";

function frame(name: string, data: string): string {
  return `event: ${name}\ndata: ${data}\n\n`;
}

const FRAMES = [frame("step", "Reading your question"), frame("text", "It says to sign it."), frame("done", "")].join("");

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const LISTED = {
  items: [
    { thread_id: THREAD, title: "what does the handover checklist say", last_at: "2999-01-02T09:00:00+00:00", last_channel: "console" },
    { thread_id: LARK_THREAD, title: "who signs the checklist", last_at: "2999-01-01T09:00:00+00:00", last_channel: "lark" },
  ],
};

const REOPENED = {
  thread_id: LARK_THREAD,
  title: "who signs the checklist",
  messages: [
    { role: "user", at: "2999-01-01T09:00:00+00:00", channel: "lark", body: "who signs the checklist" },
    { role: "assistant", at: "2999-01-01T09:00:01+00:00", channel: "lark", body: "The client signs it." },
    { role: "system", at: "2999-01-01T09:00:02+00:00", channel: "console", body: "correction:stale" },
  ],
};

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
}

async function askScreen(threads: unknown = LISTED, correcting = 201): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const address = new URL(url, ORIGIN);
      if (address.pathname === `${API}${correctionPath(THREAD)}` && init?.method === "POST") {
        const sent = JSON.parse(String(init.body ?? "null")) as { kind?: string } | null;
        return correcting === 201
          ? json({ kind: sent?.kind ?? "", at: "2999-01-02T09:00:05+00:00" }, 201)
          : json({ message: "I could not find that.", trace_id: "t" }, correcting);
      }
      if (address.pathname === `${API}/answer`) {
        return new Response(FRAMES, {
          status: 200,
          headers: { "content-type": EVENT_STREAM, [THREAD_HEADER]: THREAD },
        });
      }
      if (address.pathname === `${API}${THREADS_API_PATH}`) {
        return json(threads);
      }
      if (address.pathname === `${API}${THREAD_SEARCH_API_PATH}`) {
        return json(address.searchParams.get("q") === "signs" ? { items: [LISTED.items[1]] } : { items: [] });
      }
      if (address.pathname === `${API}${threadPath(LARK_THREAD)}`) {
        return json(REOPENED);
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp, path: ASK_ADDRESS });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [ASK_ADDRESS] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, idp };
}

function ask(container: HTMLElement, question: string): void {
  fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: question } });
  const button = [...container.querySelectorAll("button")].find((one) => one.textContent === ASK_LABEL);
  fireEvent.click(button as HTMLButtonElement);
}

function bodies(idp: FakeIdp): unknown[] {
  return idp.calls
    .filter((call) => new URL(call.url, ORIGIN).pathname === `${API}/answer`)
    .map((call) => JSON.parse(String(call.init?.body ?? "null")) as unknown);
}

function button(container: HTMLElement, name: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find((one) => one.textContent === name);
  if (found === undefined) {
    throw new Error(`no ${name} button`);
  }
  return found;
}

describe("a conversation on Ask", () => {
  test("the header the page reads is the one the route names", () => {
    // What breaks if this is deleted: the route renames its header and every follow-up starts a new
    // conversation, with every test here still green against a stand-in using the old name.
    const source = readRepoFile("src/brain/api_routes.py");
    expect(source).toMatch(new RegExp(`THREAD_HEADER: Final = "${THREAD_HEADER}"`));
  });

  test("a follow-up continues the thread the answer was kept in, and a new conversation sends none", async () => {
    // What breaks if this is deleted: every question on Ask starts a thread of its own, so a
    // follow-up is never one conversation, or the page can never start a fresh one (M9.1.1).
    const { container, idp } = await askScreen();
    ask(container, QUESTION);
    await waitFor(() => expect(container.textContent).toContain(CONTINUING));
    ask(container, "and who signs it");
    await waitFor(() => expect(bodies(idp)).toHaveLength(2));
    expect(bodies(idp)[0]).toEqual({ question: QUESTION });
    expect(bodies(idp)[1]).toEqual({ question: "and who signs it", thread: THREAD });

    fireEvent.click(button(container, NEW_CONVERSATION));
    expect(container.textContent).not.toContain(CONTINUING);
  });

  test("the conversations are listed wherever each was asked, and one begun in Lark reopens and continues on the web", async () => {
    // What breaks if this is deleted: a thread begun in a chat is invisible on the web, or reopening
    // it does not make the next question continue it (M9.1.2).
    const { container, idp } = await askScreen();
    const panel = await waitFor(() => {
      const heading = [...container.querySelectorAll("h2")].find((one) => one.textContent === CONVERSATIONS_HEADING);
      if (heading === undefined) {
        throw new Error("the conversations have not arrived");
      }
      return heading.parentElement as HTMLElement;
    });
    expect(panel.textContent).toContain("in Lark");
    expect(panel.textContent).toContain("on the web");

    fireEvent.click(within(panel).getByRole("button", { name: "who signs the checklist" }));
    await waitFor(() => expect(container.textContent).toContain("The client signs it."));
    ask(container, "when is it due");
    await waitFor(() => expect(bodies(idp)).toHaveLength(1));
    expect(bodies(idp)[0]).toEqual({ question: "when is it due", thread: LARK_THREAD });
  });

  test("a search asks for the person's own words and lists what it found, or says nothing held them", async () => {
    // What breaks if this is deleted: a person cannot find an earlier conversation by what they asked
    // (M9.1.3), or a search that found nothing reads as an empty page.
    const { container, idp } = await askScreen();
    const search = await waitFor(() => {
      const found = container.querySelector<HTMLInputElement>('input[type="search"]');
      if (found === null) {
        throw new Error("the search has not arrived");
      }
      return found;
    });
    fireEvent.change(search, { target: { value: "signs" } });
    fireEvent.click(button(container, SEARCH_LABEL));
    await waitFor(() => {
      const asked = idp.calls.map((call) => new URL(call.url, ORIGIN)).filter((url) => url.pathname === `${API}${THREAD_SEARCH_API_PATH}`);
      expect(asked.map((url) => url.searchParams.get("q"))).toEqual(["signs"]);
    });
    await waitFor(() => {
      const listed = [...container.querySelectorAll(".ask__threads button")].map((one) => one.textContent);
      expect(listed).toEqual(["who signs the checklist"]);
    });

    fireEvent.change(search, { target: { value: "nothing like it" } });
    fireEvent.click(button(container, SEARCH_LABEL));
    await waitFor(() => expect(container.textContent).toContain(NOTHING_FOUND_IN_CONVERSATIONS));
  });

  test("a person with no conversations is shown no panel", async () => {
    // The positive sibling of the list: nothing to list draws nothing, rather than an empty heading.
    const { container } = await askScreen({ items: [] });
    await waitFor(() => expect(container.querySelector("h1")).not.toBeNull());
    expect(container.textContent).not.toContain(CONVERSATIONS_HEADING);
  });

  test("the prefix the page reads a correction note by is the one the store writes", () => {
    // What breaks if this is deleted: the store renames its prefix and a reopened thread shows the
    // raw note, with every test here still green against a stand-in using the old one.
    const source = readRepoFile("src/brain/chat/thread_store.py");
    expect(source).toMatch(new RegExp(`CORRECTION_PREFIX: Final = "${CORRECTION_PREFIX}"`));
  });

  test("an answer kept in a conversation is marked wrong with a kind and no words", async () => {
    // What breaks if this is deleted: a person has no way to say an answer was wrong, so the
    // learning signal never hears it (M9.2.4), or the page sends words the route refuses.
    const { container, idp } = await askScreen();
    ask(container, QUESTION);
    await waitFor(() => expect(container.textContent).toContain(WAS_IT_WRONG));
    const kinds = container.querySelector<HTMLSelectElement>("select#ask-correction");
    expect(container.querySelector('label[for="ask-correction"]')?.textContent).toBe(WAS_IT_WRONG);
    expect([...(kinds?.options ?? [])].map((one) => one.textContent)).toEqual(Object.values(CORRECTION_WORDS));
    fireEvent.change(kinds as HTMLSelectElement, { target: { value: "missing" } });
    fireEvent.click(button(container, MARK_WRONG));
    await waitFor(() => expect(container.textContent).toContain(MARKED_WRONG));
    const sent = idp.calls.filter((call) => new URL(call.url, ORIGIN).pathname === `${API}${correctionPath(THREAD)}`);
    expect(sent.map((call) => [call.init?.method, JSON.parse(String(call.init?.body ?? "null"))])).toEqual([
      ["POST", { kind: "missing" }],
    ]);
    expect(button(container, MARK_WRONG).disabled).toBe(true);
  });

  test("a mark the route refuses says nothing was changed", async () => {
    // The refusal's sibling: a thread that is not the person's, or holds no answer, is the route's
    // 404, and the page says it could not be marked rather than that it was.
    const { container } = await askScreen(LISTED, 404);
    ask(container, QUESTION);
    await waitFor(() => expect(container.textContent).toContain(WAS_IT_WRONG));
    fireEvent.click(button(container, MARK_WRONG));
    await waitFor(() => expect(container.textContent).toContain(NOT_MARKED));
    expect(container.textContent).not.toContain(MARKED_WRONG);
  });

  test("no answer on the page, no mark to make", async () => {
    // What breaks if this is deleted: the control is drawn before anything was answered, and marks
    // whatever the thread last held rather than the answer the person is reading.
    const { container } = await askScreen();
    await waitFor(() => expect(container.querySelector("h1")).not.toBeNull());
    expect(container.textContent).not.toContain(WAS_IT_WRONG);
  });

  test("a reopened thread says in words which kind an answer was marked", async () => {
    // What breaks if this is deleted: a correction note reads as `correction:stale` to the person
    // who made it.
    const { container } = await askScreen();
    const panel = await waitFor(() => {
      const heading = [...container.querySelectorAll("h2")].find((one) => one.textContent === CONVERSATIONS_HEADING);
      if (heading === undefined) {
        throw new Error("the conversations have not arrived");
      }
      return heading.parentElement as HTMLElement;
    });
    fireEvent.click(within(panel).getByRole("button", { name: "who signs the checklist" }));
    await waitFor(() => expect(container.textContent).toContain(CORRECTION_WORDS.stale));
    expect(container.textContent).not.toContain("correction:stale");
  });
});
