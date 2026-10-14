/**
 * Dictation on Ask (M40.7.3): the browser's own speech recognition, and nothing sent to us.
 *
 * **The recogniser is a fake the test drives**, because jsdom has none and because what is under
 * test is what the console does with what a recogniser says and fails with. The pure half
 * (`askDictationCore.ts`) is tested directly; the page half is driven through the application's
 * own route table, signed in through the real session modules, with a stand-in API that records
 * every request so that "nothing is sent to our side" is asserted on requests and not on a
 * comment.
 *
 * Task ids: M40.7.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { EVENT_STREAM } from "../src/api/events";
import { ASK_ADDRESS, ASK_LABEL } from "../src/pages/Ask";
import {
  DICTATE_LABEL,
  DICTATION_PRIVACY,
  DICTATION_PROBLEMS,
  NO_DICTATION_HERE,
} from "../src/pages/AskDictation";
import {
  appendSpoken,
  findRecognition,
  problemOf,
  startDictation,
  type DictationHandlers,
  type Problem,
  type Recognition,
  type RecognitionErrorEvent,
  type RecognitionEvent,
} from "../src/pages/askDictationCore";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const ORIGIN = "https://console.test";
const API = "/api/v1";

/** One thing a recogniser reports: a phrase, finished or still being guessed. */
interface Phrase {
  readonly text: string;
  readonly final: boolean;
}

/** A recogniser that does nothing until the test says what it heard. */
class FakeRecognition implements Recognition {
  static made: FakeRecognition[] = [];
  lang = "";
  continuous = false;
  interimResults = true;
  onresult: ((event: RecognitionEvent) => void) | null = null;
  onerror: ((event: RecognitionErrorEvent) => void) | null = null;
  onend: (() => void) | null = null;
  started = 0;
  stopped = 0;
  aborted = 0;
  refuseToStart = false;

  constructor() {
    FakeRecognition.made.push(this);
  }

  start(): void {
    this.started += 1;
    if (this.refuseToStart) {
      throw new Error("already started");
    }
  }

  stop(): void {
    this.stopped += 1;
    this.onend?.();
  }

  abort(): void {
    this.aborted += 1;
  }

  /** Report these phrases as one result event, the first at `from` in the running list. */
  say(phrases: readonly Phrase[], from = 0): void {
    const results = phrases.map((one) => ({
      isFinal: one.final,
      length: 1,
      0: { transcript: one.text },
    }));
    this.onresult?.({ resultIndex: from, results: Object.assign(results, { length: results.length }) });
  }

  fail(code: string): void {
    this.onerror?.({ error: code });
    this.onend?.();
  }
}

function lastRecognition(): FakeRecognition {
  const found = FakeRecognition.made.at(-1);
  if (found === undefined) {
    throw new Error("no recogniser was made");
  }
  return found;
}

function install(name: "SpeechRecognition" | "webkitSpeechRecognition" = "SpeechRecognition"): void {
  Object.defineProperty(window, name, { configurable: true, writable: true, value: FakeRecognition });
}

afterEach(() => {
  FakeRecognition.made = [];
  Reflect.deleteProperty(window, "SpeechRecognition");
  Reflect.deleteProperty(window, "webkitSpeechRecognition");
  vi.restoreAllMocks();
});

const NO_HANDLERS: DictationHandlers = { onSpoken: () => undefined, onProblem: () => undefined, onEnd: () => undefined };

// ------------------------------------------------------------------------------ the pure half

describe("finding the browser's recogniser", () => {
  test("the standard name and the prefixed one are both found, and a scope with neither gives none", () => {
    // What breaks if this is deleted: dictation offered in no browser, or in only one of the two
    // families that carry it, with every page test below passing because they install the standard one.
    expect(findRecognition({ SpeechRecognition: FakeRecognition })).toBe(FakeRecognition);
    expect(findRecognition({ webkitSpeechRecognition: FakeRecognition })).toBe(FakeRecognition);
    expect(findRecognition({})).toBeNull();
    expect(findRecognition({ SpeechRecognition: "not a constructor" })).toBeNull();
  });
});

describe("what was spoken is added after what was typed", () => {
  test("one space joins them, none is doubled, and nothing spoken changes nothing typed", () => {
    // What breaks if this is deleted: words run together, doubled spaces, or an empty phrase that
    // rewrites the field the person is editing.
    expect(appendSpoken("Where is", "the handover")).toBe("Where is the handover");
    expect(appendSpoken("Where is ", "the handover")).toBe("Where is the handover");
    expect(appendSpoken("Where is\n", "the handover")).toBe("Where is\nthe handover");
    expect(appendSpoken("", "  the handover ")).toBe("the handover");
    expect(appendSpoken("Where is", "   ")).toBe("Where is");
  });

  test("the result is cut at the field's own limit, which a value set from code is not held to", () => {
    // What breaks if this is deleted: a long dictation fills the field past the length the route
    // accepts, and Ask is then disabled with no reason the person can see.
    expect(appendSpoken("abc", "defgh", 6)).toBe("abc de");
    expect(appendSpoken("abc", "defgh", 5)).toBe("abc d");
    expect(appendSpoken("abc", "defgh", 9)).toBe("abc defgh");
    expect(appendSpoken("abc", "d")).toBe("abc d");
  });
});

describe("why listening failed", () => {
  test("each code the browser reports maps to the kind the page has a sentence for", () => {
    // What breaks if this is deleted: a blocked microphone reported as a fault, or a stop the page
    // asked for reported as a problem.
    const expected: Record<string, Problem | null> = {
      aborted: null,
      "not-allowed": "denied",
      "service-not-allowed": "denied",
      "audio-capture": "no-microphone",
      "no-speech": "nothing-heard",
      "language-not-supported": "language",
      network: "failed",
      "something-new": "failed",
    };
    for (const [code, kind] of Object.entries(expected)) {
      expect(problemOf(code), code).toBe(kind);
    }
  });
});

describe("listening", () => {
  test("it asks for the browser's language and for finished phrases only", () => {
    // What breaks if this is deleted: a tag compiled into the product, or interim guesses that
    // rewrite the field while the person edits it.
    vi.spyOn(navigator, "language", "get").mockReturnValue("fr-CA");
    startDictation(FakeRecognition, navigator.language, NO_HANDLERS);
    const heard = lastRecognition();
    expect(heard.lang).toBe("fr-CA");
    expect(heard.interimResults).toBe(false);
    expect(heard.continuous).toBe(true);
    expect(heard.started).toBe(1);
  });

  test("only finished phrases are delivered, trimmed, from the index the event names", () => {
    // What breaks if this is deleted: a half-heard phrase is appended and then heard again whole,
    // or a phrase already delivered is delivered again on every later event.
    const spoken: string[] = [];
    startDictation(FakeRecognition, "en", { ...NO_HANDLERS, onSpoken: (words) => spoken.push(words) });
    const heard = lastRecognition();
    heard.say([{ text: " open the file ", final: true }, { text: "and then", final: false }]);
    expect(spoken).toEqual(["open the file"]);
    heard.say(
      [
        { text: "open the file", final: true },
        { text: "and then close it", final: true },
      ],
      1,
    );
    expect(spoken).toEqual(["open the file", "and then close it"]);
    heard.say([{ text: "   ", final: true }]);
    expect(spoken).toHaveLength(2);
  });

  test("an aborted listening delivers nothing and ends nothing", () => {
    // What breaks if this is deleted: a phrase heard after the question was sent lands in a field
    // nobody is looking at, and the page is told listening ended when it already knows.
    const calls: string[] = [];
    const listening = startDictation(FakeRecognition, "en", {
      onSpoken: (words) => calls.push(`spoken ${words}`),
      onProblem: (problem) => calls.push(`problem ${problem}`),
      onEnd: () => calls.push("end"),
    });
    const heard = lastRecognition();
    listening.abort();
    heard.say([{ text: "too late", final: true }]);
    heard.fail("no-speech");
    expect(heard.aborted).toBe(1);
    expect(calls).toEqual([]);
  });

  test("a browser that refuses to start is a problem and an end, and never an exception", () => {
    // What breaks if this is deleted: pressing the button in a browser that throws on start breaks
    // the page, or leaves the button pressed with nothing listening.
    const calls: string[] = [];
    class Refusing extends FakeRecognition {
      override refuseToStart = true;
    }
    expect(() =>
      startDictation(Refusing, "en", {
        onSpoken: () => undefined,
        onProblem: (problem) => calls.push(`problem ${problem}`),
        onEnd: () => calls.push("end"),
      }),
    ).not.toThrow();
    expect(calls).toEqual(["problem failed", "end"]);
  });

  test("a whole dictation makes no network request of any kind", () => {
    // What breaks if this is deleted: dictation quietly gains a route, a vendor or a beacon, which
    // is the design the owner decided against (item 220 B).
    const fetched = vi.spyOn(globalThis, "fetch");
    const opened = vi.fn();
    vi.stubGlobal("XMLHttpRequest", opened);
    vi.stubGlobal("WebSocket", opened);
    const beacon = vi.fn();
    Object.defineProperty(navigator, "sendBeacon", { configurable: true, value: beacon });
    try {
      const listening = startDictation(FakeRecognition, "en", NO_HANDLERS);
      lastRecognition().say([{ text: "hello", final: true }]);
      lastRecognition().fail("no-speech");
      listening.stop();
    } finally {
      vi.unstubAllGlobals();
      Reflect.deleteProperty(navigator, "sendBeacon");
    }
    expect(fetched).not.toHaveBeenCalled();
    expect(opened).not.toHaveBeenCalled();
    expect(beacon).not.toHaveBeenCalled();
  });
});

// ------------------------------------------------------------------------------ the page

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: string;
}

async function askScreen(): Promise<{
  container: HTMLElement;
  unmount: () => void;
  sent: Sent[];
}> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const address = new URL(url, ORIGIN);
      sent.push({
        method: init?.method ?? "GET",
        path: address.pathname,
        body: typeof init?.body === "string" ? init.body : "",
      });
      if (address.pathname === `${API}/answer`) {
        return new Response("event: text\ndata: Done.\n\nevent: done\ndata: \n\n", {
          status: 200,
          headers: { "content-type": EVENT_STREAM },
        });
      }
      if (address.pathname === `${API}/threads`) {
        return new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp, path: ASK_ADDRESS });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [ASK_ADDRESS] });
  const { container, unmount } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("form.ask__form")) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, unmount, sent };
}

function field(container: HTMLElement): HTMLTextAreaElement {
  const found = container.querySelector<HTMLTextAreaElement>("textarea.ask__question");
  if (found === null) {
    throw new Error("no question field");
  }
  return found;
}

function dictate(container: HTMLElement): HTMLButtonElement {
  return within(container).getByRole("button", { name: DICTATE_LABEL });
}

function status(container: HTMLElement): string {
  return container.querySelector(".ask__dictation-status")?.textContent ?? "";
}

function press(container: HTMLElement): void {
  fireEvent.click(dictate(container));
}

function speak(phrases: readonly Phrase[]): void {
  act(() => {
    lastRecognition().say(phrases);
  });
}

describe("dictation on the Ask page", () => {
  test("a browser with no recogniser is told so in a sentence, offered no dead button, and can still type", async () => {
    // What breaks if this is deleted: a button that does nothing in a browser that cannot listen,
    // which reads as a broken page, or a page that cannot be used at all without one.
    const { container } = await askScreen();

    expect(container.textContent).toContain(NO_DICTATION_HERE);
    expect(within(container).queryByRole("button", { name: DICTATE_LABEL })).toBeNull();
    fireEvent.change(field(container), { target: { value: "typed instead" } });
    expect(field(container).value).toBe("typed instead");
  });

  test("the prefixed recogniser is used when it is the only one", async () => {
    // What breaks if this is deleted: dictation absent in browsers that carry only the prefixed name.
    install("webkitSpeechRecognition");
    const { container } = await askScreen();

    expect(dictate(container).getAttribute("aria-pressed")).toBe("false");
    expect(container.textContent).not.toContain(NO_DICTATION_HERE);
  });

  test("the button is a pressed toggle that listens in the browser's language and says what it is doing", async () => {
    // What breaks if this is deleted: a control a screen reader cannot tell is on, a hard-coded
    // language, or a button that sits silent while the microphone is open.
    vi.spyOn(navigator, "language", "get").mockReturnValue("de-CH");
    install();
    const { container } = await askScreen();
    const button = dictate(container);
    expect(button.getAttribute("type")).toBe("button");
    expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(status(container)).toBe("");

    press(container);

    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(lastRecognition().lang).toBe("de-CH");
    expect(lastRecognition().started).toBe(1);
    expect(status(container)).toContain("Listening");
    expect(container.querySelector(".ask__dictation-status")?.getAttribute("role")).toBe("status");
  });

  test("what is spoken is appended after what was typed and stays editable", async () => {
    // What breaks if this is deleted: dictation replaces the question, discards what was typed,
    // or writes text the person cannot then correct.
    install();
    const { container } = await askScreen();
    fireEvent.change(field(container), { target: { value: "Where is" } });
    press(container);

    speak([{ text: "the handover note", final: true }]);
    expect(field(container).value).toBe("Where is the handover note");

    fireEvent.change(field(container), { target: { value: "Where is the signed handover note" } });
    act(() => {
      lastRecognition().say(
        [
          { text: "the handover note", final: true },
          { text: "for site four", final: true },
        ],
        1,
      );
    });
    expect(field(container).value).toBe("Where is the signed handover note for site four");
  });

  test("pressing the button again stops listening and says the words are in the box", async () => {
    // What breaks if this is deleted: no way to stop listening, or a stop that leaves the button
    // pressed and the microphone's state a mystery.
    install();
    const { container } = await askScreen();
    press(container);
    speak([{ text: "hello there", final: true }]);

    press(container);

    expect(lastRecognition().stopped).toBe(1);
    expect(dictate(container).getAttribute("aria-pressed")).toBe("false");
    expect(status(container)).toContain("Your words are in the question box");
  });

  test("a blocked microphone is told how to allow it, in words, and names no code", async () => {
    // What breaks if this is deleted: 'not-allowed' shown to a person who then has no idea where
    // the setting is.
    install();
    const { container } = await askScreen();
    press(container);

    act(() => {
      lastRecognition().fail("not-allowed");
    });

    expect(status(container)).toBe(DICTATION_PROBLEMS.denied);
    expect(status(container)).toMatch(/Microphone to Allow/);
    expect(status(container)).not.toContain("not-allowed");
    expect(dictate(container).getAttribute("aria-pressed")).toBe("false");
  });

  test("each other way listening fails has its own sentence, and a stop the page asked for has none", async () => {
    // What breaks if this is deleted: every failure reads the same, or a deliberate stop is shown
    // to the person as an error.
    install();
    const { container } = await askScreen();
    const wanted: Record<string, Problem> = {
      "audio-capture": "no-microphone",
      "no-speech": "nothing-heard",
      "language-not-supported": "language",
      network: "failed",
    };
    for (const [code, kind] of Object.entries(wanted)) {
      press(container);
      act(() => {
        lastRecognition().fail(code);
      });
      expect(status(container), code).toBe(DICTATION_PROBLEMS[kind]);
    }
    press(container);
    act(() => {
      lastRecognition().onerror?.({ error: "aborted" });
      lastRecognition().onend?.();
    });
    expect(status(container)).toBe("");
  });

  test("sending the question stops listening, and a phrase heard afterwards is dropped", async () => {
    // What breaks if this is deleted: the microphone stays open while the answer is made, and
    // words that arrive after the question was sent are appended to a question nobody will see.
    install();
    const { container, sent } = await askScreen();
    fireEvent.change(field(container), { target: { value: "what does it say" } });
    press(container);
    const heard = lastRecognition();

    fireEvent.click(within(container).getByRole("button", { name: ASK_LABEL }));
    await waitFor(() => {
      if (!sent.some((one) => one.path === `${API}/answer`)) {
        throw new Error("the question was not sent");
      }
    });

    expect(heard.aborted).toBe(1);
    act(() => {
      heard.say([{ text: "and also this", final: true }]);
    });
    expect(field(container).value).toBe("what does it say");
    expect(dictate(container).getAttribute("aria-pressed")).toBe("false");
  });

  test("leaving the page stops listening", async () => {
    // What breaks if this is deleted: a microphone left open on a page that has gone.
    install();
    const { container, unmount } = await askScreen();
    press(container);
    const heard = lastRecognition();

    unmount();

    expect(heard.aborted).toBe(1);
  });

  test("dictating sends nothing to the server, and the page says so", async () => {
    // What breaks if this is deleted: dictation gains a request to our side, which the owner
    // decided against (item 220 B), with every other test here passing.
    install();
    const { container, sent } = await askScreen();
    const before = sent.length;

    press(container);
    speak([{ text: "a spoken question", final: true }]);
    press(container);
    act(() => {
      lastRecognition().fail("network");
    });

    expect(sent.slice(before)).toEqual([]);
    expect(container.textContent).toContain(DICTATION_PRIVACY);
  });

  test("the control sits straight after the field it fills, ahead of the narrowing pickers", async () => {
    // What breaks if this is deleted: the control moved below the pickers, where a keyboard reader
    // reaches it after walking past the field it fills, or into the form's submit order.
    install();
    const { container } = await askScreen();

    const form = container.querySelector("form.ask__form") as HTMLFormElement;
    const stops = [...form.querySelectorAll<HTMLElement>("textarea, select, button")].map((one) => one.tagName);
    expect(stops.slice(0, 3)).toEqual(["TEXTAREA", "BUTTON", "SELECT"]);
    expect(form.querySelectorAll('button[type="submit"]')).toHaveLength(1);
    expect(dictate(container).getAttribute("type")).toBe("button");
    const target = form.querySelector(".ask__dictate");
    expect(target).not.toBeNull();
  });
});
