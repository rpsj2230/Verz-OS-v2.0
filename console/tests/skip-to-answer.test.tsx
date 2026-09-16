/**
 * The skip-to-answer control on the ask screen, driven from the keyboard and read the way a
 * screen reader reads it.
 *
 * **Keyboard means native controls and focus, and both are asserted on what rendered.** jsdom
 * does not turn Enter or Space into a click, which a browser does for every `button` without
 * anybody writing a handler, so the property worth asserting is the one
 * `tests/keyboard-access.test.tsx` asserts for the frame: the control is a native button, in
 * document order, with no tabindex, and pressing it moves `document.activeElement`. A test that
 * dispatched a keydown and a handler that listened for one would both be satisfied by a div.
 *
 * **Screen reader means the accessibility tree and live regions, not text.** The control and
 * the answer are found by role and accessible name through `@testing-library/dom`, which
 * computes names the way assistive technology does, so an `aria-label` on the wrong element or
 * a name supplied only by a CSS class fails here. And the answer is checked for every live
 * region around it, because a region that announced the answer as it streamed is exactly what
 * `brain.locale.A_LIVE_REGION_ON_A_STREAM_READS_THE_ANSWER_LETTER_BY_LETTER` refuses.
 *
 * **Driven through the application's own route table**, signed in through the real session
 * modules, against the stand-in API `tests/ask-page.test.tsx` uses, with frames built the way
 * `brain.gate.streaming.encode` builds them.
 *
 * Task ids: M35.2.1.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { EVENT_STREAM } from "../src/api/events";
import {
  ANSWER_LABEL,
  ASK_ADDRESS,
  ASK_LABEL,
  SKIP_TO_ANSWER,
} from "../src/pages/Ask";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { consoleRules, declared, pixels } from "./support/cascade";
import { backendAbstentionText } from "./support/python";
import { extractOne, readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const ANSWER_API = "/api/v1/answer";

/** The narrowest phone the console is held to, and the smallest tap target, in CSS pixels. */
const PHONE_WIDTH_PX = 360;
const TAP_TARGET_PX = 44;

const QUESTION = "what is the balance on SKIP-QUESTION-3be07a";
const ANSWER = "The balance is 400.";

/** Enough citations that reaching the answer in document order is a real walk. */
const CITATIONS = [
  "client a: balance from s",
  "client b: owner from s",
  "client c: renewal from s",
  "client d: hours from s",
];

/** Every way an element can be a live region, which is every way the answer could be read aloud as it grows. */
const LIVE = '[aria-live], [role="status"], [role="alert"], [role="log"], [role="marquee"], [role="timer"]';

function frame(name: string, data: string): string {
  return [`event: ${name}`, ...data.split("\n").map((line) => `data: ${line}`)].join("\n") + "\n\n";
}

function answerFrames(text: string, citations: readonly string[] = []): string {
  return [
    frame("step", "Reading your question"),
    ...citations.map((one) => frame("citation", one)),
    frame("text", text),
    frame("done", ""),
  ].join("");
}

function whole(frames: string): () => Response {
  return () => new Response(frames, { status: 200, headers: { "content-type": EVENT_STREAM } });
}

interface Pushed {
  readonly response: Response;
  push(text: string): void;
  close(): void;
}

function pushedStream(): Pushed {
  const encoder = new TextEncoder();
  let control: ReadableStreamDefaultController<Uint8Array> | null = null;
  const stream = new ReadableStream<Uint8Array>({
    start(one) {
      control = one;
    },
  });
  return {
    response: new Response(stream, { status: 200, headers: { "content-type": EVENT_STREAM } }),
    push(text) {
      control?.enqueue(encoder.encode(text));
    },
    close() {
      control?.close();
    },
  };
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly router: ReturnType<typeof createMemoryRouter>;
}

async function askScreen(answer: () => Response): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url) {
      return new URL(url, CONSOLE_ORIGIN).pathname === ANSWER_API ? answer() : null;
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
  return { container, idp, router };
}

function page(container: HTMLElement): HTMLElement {
  const found = container.querySelector<HTMLElement>("article.page");
  if (!found) {
    throw new Error("No page was rendered.");
  }
  return found;
}

function askButton(container: HTMLElement): HTMLButtonElement {
  const found = [...page(container).querySelectorAll("button")].find(
    (one) => one.textContent === ASK_LABEL,
  );
  if (!found) {
    throw new Error("No ask button was rendered.");
  }
  return found;
}

/** Type a question and press Ask, focusing the button first as a keyboard reader would have. */
function askFromTheKeyboard(container: HTMLElement, question: string): void {
  const field = page(container).querySelector("textarea");
  if (!field) {
    throw new Error("No question field was rendered.");
  }
  fireEvent.change(field, { target: { value: question } });
  const button = askButton(container);
  button.focus();
  fireEvent.click(button);
}

/** Type a question and press Ask with a pointer, which leaves focus where it was. */
function askWithAPointer(container: HTMLElement, question: string): void {
  const field = page(container).querySelector("textarea") as HTMLTextAreaElement;
  fireEvent.change(field, { target: { value: question } });
  fireEvent.click(askButton(container));
}

/** Everything the tab key would stop on inside the page, in document order. */
function tabStops(root: HTMLElement): HTMLElement[] {
  return [
    ...root.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [tabindex]"),
  ].filter((one) => one.getAttribute("tabindex") !== "-1");
}

function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

async function answerArrived(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    expect(page(container).querySelector(".ask__answer")).not.toBeNull();
    // The steps are drawn while the answer is being made, so their absence is the page
    // saying the stream has finished.
    expect(page(container).querySelector(".ask__steps")).toBeNull();
  });
}

// ----------------------------------------------------------------------------- the control

describe("the skip-to-answer control", () => {
  test("once an answer is drawn, the first tab stop past the form is the control, ahead of what the answer stands on", async () => {
    // What breaks if this is deleted: the control moved below the citations, where a keyboard
    // reader reaches it after walking the list it exists to skip, or rendered as something
    // that is not in the tab order at all. Before anything is asked there is nothing to skip
    // to, so nothing is offered: a control that goes nowhere is worse than none.
    const { container } = await askScreen(whole(answerFrames(ANSWER, CITATIONS)));
    expect(within(page(container)).queryByRole("button", { name: SKIP_TO_ANSWER })).toBeNull();

    askWithAPointer(container, QUESTION);
    await answerArrived(container);

    const skip = within(page(container)).getByRole("button", { name: SKIP_TO_ANSWER });
    expect(tabStops(page(container)).map((one) => one.tagName)).toEqual([
      "TEXTAREA",
      "BUTTON",
      "BUTTON",
    ]);
    expect(tabStops(page(container))[2]).toBe(skip);
    expect(skip.tagName).toBe("BUTTON");
    expect(skip.getAttribute("type")).toBe("button");
    expect(skip.getAttribute("tabindex")).toBeNull();

    const provenance = page(container).querySelector(".ask__provenance") as Element;
    const answer = page(container).querySelector(".ask__answer") as Element;
    expect(provenance.querySelectorAll("li")).toHaveLength(CITATIONS.length);
    expect(precedes(page(container).querySelector("form") as Element, skip)).toBe(true);
    expect(precedes(skip, provenance)).toBe(true);
    expect(precedes(provenance, answer)).toBe(true);
  });

  test("pressing it puts focus on the answer, which a screen reader names and the tab key never stops on", async () => {
    // What breaks if this is deleted: a control that scrolls and leaves focus where it was, so
    // the next Tab goes back into the citations; or an answer made reachable by giving it a
    // zero tabindex, which adds a stop to the order the control exists to shorten; or a
    // focused region with no name, which a screen reader announces as nothing. Pressing it
    // asks nothing and writes nothing into the address, not even a fragment.
    const { container, idp, router } = await askScreen(whole(answerFrames(ANSWER, CITATIONS)));
    askWithAPointer(container, QUESTION);
    await answerArrived(container);
    const requestsBefore = idp.calls.length;

    fireEvent.click(within(page(container)).getByRole("button", { name: SKIP_TO_ANSWER }));

    const region = within(page(container)).getByRole("region", { name: ANSWER_LABEL });
    expect(document.activeElement).toBe(region);
    expect(region.getAttribute("tabindex")).toBe("-1");
    expect(region.querySelector(".ask__answer")?.textContent).toBe(ANSWER);
    expect(region.querySelector(".ask__sources")).toBeNull();

    expect(idp.calls.length).toBe(requestsBefore);
    expect(router.state.location.pathname).toBe(ASK_ADDRESS);
    expect(router.state.location.search).toBe("");
    expect(router.state.location.hash).toBe("");
  });

  test("the answer it reaches is not a live region and sits inside none, so it is read once, when the reader chooses", async () => {
    // What breaks if this is deleted: an `aria-live` put on the answer so that a screen reader
    // "knows it arrived", which reads a streamed answer letter by letter and restarts on every
    // piece. The control is the reader's way to the answer, and it only works as that if
    // nothing else is already reading the answer at them. Checked while the answer is still
    // growing, because that is when a live region does its damage.
    const pushed = pushedStream();
    const { container } = await askScreen(() => pushed.response);
    askWithAPointer(container, QUESTION);
    pushed.push(frame("step", "Reading your question"));
    pushed.push(frame("text", ANSWER));

    await waitFor(() => {
      expect(page(container).querySelector(".ask__answer")).not.toBeNull();
    });
    const region = within(page(container)).getByRole("region", { name: ANSWER_LABEL });
    expect(region.closest(LIVE)).toBeNull();
    expect(region.querySelectorAll(LIVE)).toHaveLength(0);
    // Offered while the answer is still being made, because the reader may want it now.
    expect(within(page(container)).getByRole("button", { name: SKIP_TO_ANSWER })).toBeTruthy();

    pushed.push(frame("done", ""));
    pushed.close();
    await answerArrived(container);
  });

  test("a refusal and a stream that failed are offered the same control, and it reaches their sentence", async () => {
    // What breaks if this is deleted: a control offered only when something was cited, which
    // is a mark on the page for "this one was answered" beside a refusal that is meant to read
    // like any other answer. The refusal is the lane's own sentence. A stream that ended in an
    // error frame is reached the same way, because its sentence is what the reader waited for.
    const refusal = backendAbstentionText();
    const refused = await askScreen(whole(answerFrames(refusal)));
    askWithAPointer(refused.container, QUESTION);
    await answerArrived(refused.container);

    fireEvent.click(within(page(refused.container)).getByRole("button", { name: SKIP_TO_ANSWER }));
    const region = within(page(refused.container)).getByRole("region", { name: ANSWER_LABEL });
    expect(document.activeElement).toBe(region);
    expect(region.querySelector(".ask__answer")?.textContent).toBe(refusal);

    const failing = await askScreen(
      whole([frame("step", "Reading your question"), frame("error", "That did not finish.")].join("")),
    );
    askWithAPointer(failing.container, QUESTION);
    await waitFor(() => {
      expect(page(failing.container).querySelector(".ask__steps")).toBeNull();
      expect(page(failing.container).querySelector(".notice__body")).not.toBeNull();
    });
    fireEvent.click(within(page(failing.container)).getByRole("button", { name: SKIP_TO_ANSWER }));
    const failed = within(page(failing.container)).getByRole("region", { name: ANSWER_LABEL });
    expect(document.activeElement).toBe(failed);
    expect(failed.querySelector(".notice__body")?.textContent).toBe("That did not finish.");
  });

  test("a request the API refused before any stream offers no control, because there is nothing to skip", async () => {
    // What breaks if this is deleted: a skip control beside a failure notice that has no steps
    // and no citations above it, which is a control that moves focus a few pixels and says it
    // took the reader to an answer that does not exist. The positive cases are above.
    const { container } = await askScreen(
      () =>
        new Response(JSON.stringify({ message: "It did not work." }), {
          status: 500,
          headers: { "content-type": "application/json" },
        }),
    );
    askWithAPointer(container, QUESTION);

    await waitFor(() => {
      expect(page(container).querySelector(".notice__body")).not.toBeNull();
    });
    expect(within(page(container)).queryByRole("button", { name: SKIP_TO_ANSWER })).toBeNull();
    expect(within(page(container)).queryByRole("region", { name: ANSWER_LABEL })).toBeNull();
  });
});

// ------------------------------------------------------------------------------ focus

describe("focus when the answer is finished", () => {
  test("a keyboard reader who pressed Ask is handed focus on the control when the answer is finished, and not before", async () => {
    // What breaks if this is deleted: the form disables its own controls while the answer is
    // made, so a keyboard reader is left focused on nothing and a screen reader user hears
    // nothing when it finishes. Handing focus to the control is both the way back and the one
    // announcement a finished answer gets, which is its accessible name. Not before the end:
    // moving focus while frames are still arriving would announce a half-made answer.
    const pushed = pushedStream();
    const { container } = await askScreen(() => pushed.response);

    askFromTheKeyboard(container, QUESTION);
    pushed.push(frame("step", "Reading your question"));
    pushed.push(frame("text", ANSWER));
    await waitFor(() => {
      expect(page(container).querySelector(".ask__answer")).not.toBeNull();
    });
    const skip = within(page(container)).getByRole("button", { name: SKIP_TO_ANSWER });
    expect(document.activeElement).not.toBe(skip);

    pushed.push(frame("done", ""));
    pushed.close();

    await waitFor(() => {
      expect(document.activeElement).toBe(skip);
    });
    expect(document.activeElement?.getAttribute("type")).toBe("button");
    expect(within(page(container)).getByRole("button", { name: SKIP_TO_ANSWER })).toBe(
      document.activeElement,
    );
  });

  test("a reader who moved focus somewhere else while waiting is left where they went", async () => {
    // What breaks if this is deleted: focus taken back from the navigation, or from anything
    // else the reader chose while the answer was being made, which is the page deciding for
    // them what they read next. The sibling above is the case where moving focus is right.
    const pushed = pushedStream();
    const { container } = await askScreen(() => pushed.response);

    askFromTheKeyboard(container, QUESTION);
    pushed.push(frame("step", "Reading your question"));
    const elsewhere = container.querySelector<HTMLAnchorElement>("nav a");
    if (!elsewhere) {
      throw new Error("No navigation link was rendered to move focus to.");
    }
    elsewhere.focus();
    expect(document.activeElement).toBe(elsewhere);

    pushed.push(frame("text", ANSWER));
    pushed.push(frame("done", ""));
    pushed.close();
    await answerArrived(container);

    expect(document.activeElement).toBe(elsewhere);
  });

  test("a reader who asked with a pointer is not moved either, because the page took nothing from them", async () => {
    // What breaks if this is deleted: focus moved on every completion, which scrolls a page
    // somebody is reading with a mouse and announces a control to nobody who lost anything.
    const { container } = await askScreen(whole(answerFrames(ANSWER, CITATIONS)));
    const before = document.activeElement;

    askWithAPointer(container, QUESTION);
    await answerArrived(container);

    expect(document.activeElement).toBe(before);
    expect(within(page(container)).getByRole("button", { name: SKIP_TO_ANSWER })).not.toBe(
      document.activeElement,
    );
  });
});

// ------------------------------------------------------------------ words and a phone

describe("the control's words and size", () => {
  test("its words are the catalogue's, so the translated interface names the same control", () => {
    // What breaks if this is deleted: the console's label edited on its own, so the Simplified
    // Chinese entry `brain.locale` carries under `answer.skip_to` describes a control that is
    // now called something else. The English entry is read out of the Python catalogue.
    const locale = readRepoFile("src/brain/locale.py");
    const english = extractOne(
      locale,
      /^ {4}"answer\.skip_to": \{"en": "([^"]+)", "zh-Hans": "[^"]+"\},$/m,
      "answer.skip_to in brain.locale.MESSAGES",
    );

    expect(SKIP_TO_ANSWER).toBe(english);
  });

  test("it is a thumb tall on a phone", async () => {
    // What breaks if this is deleted: a control a cursor can hit and a thumb cannot, on the
    // screen where the citations push the answer furthest below the fold. Read for the
    // rendered element at phone width, so a rule for a class nothing renders cannot pass it.
    const { container } = await askScreen(whole(answerFrames(ANSWER, CITATIONS)));
    askWithAPointer(container, QUESTION);
    await answerArrived(container);

    const skip = within(page(container)).getByRole("button", { name: SKIP_TO_ANSWER });
    const height = pixels(declared(skip, "min-height", consoleRules(), PHONE_WIDTH_PX) ?? "");
    expect(height).toBeGreaterThanOrEqual(TAP_TARGET_PX);
  });
});
