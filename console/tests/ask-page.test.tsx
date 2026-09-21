/**
 * Asking a question in the console and reading the answer, which is the one screen that
 * proves an install end to end.
 *
 * **Driven through the application's own route table**, signed in through the real session
 * modules, against a stand-in API that answers `POST /api/v1/answer` with the frames
 * `brain.gate.streaming` encodes, as `tests/approvals-page.test.tsx` drives the queue. The
 * frames are built here the way the encoder builds them, one `data:` field per line, because
 * the property that matters most about the transport is what happens to a value with a blank
 * line in it.
 *
 * **The refusal is the route's own, not one somebody typed.** `NOT_FOUND_TEXT` is read out of
 * `brain.gate.abstain`, which is the string `PUBLIC_TEXT` maps both `NOT_ENTITLED` and
 * `NOTHING_RETRIEVED` to by identity. So the refusal this page is shown is the refusal the
 * lane would send, and the assertion that the page adds nothing to it is an assertion about
 * the real sentence.
 *
 * **"The same code draws both" is asserted as markup and not as a reading of the source.** A
 * refusal stream and an answer stream carrying the same sentence render byte for byte, with
 * the sentence substituted, which is a claim no branch on the text or on the citations can
 * survive. Reading the page for the absence of an `if` would be satisfied by a ternary.
 *
 * **The question is asked with a value that could not occur anywhere else**, so "it is not in
 * the URL" is asserted over every address the console touched rather than over the one
 * somebody thought to check.
 *
 * Task ids: M42.6.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { ANSWER_EVENTS, EVENT_STREAM, eventIn, framesIn } from "../src/api/events";
import { NOT_FOUND_MESSAGE } from "../src/api/errors";
import { NO_REFERENCE_CAME_BACK } from "../src/ui/FailureNotice";
import {
  ASK_ADDRESS,
  ASK_HEADING,
  ASK_LABEL,
  BASED_ON,
  NOTHING_ASKED_YET,
  PROGRESS_LABEL,
  QUESTION_LABEL,
} from "../src/pages/Ask";
import {
  ANSWER_API_PATH,
  askBody,
  MAX_QUESTION_CHARS,
  NOTHING_ASKED,
  withEvent,
} from "../src/pages/askQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { consoleRules, declared, inherited, pixels } from "./support/cascade";
import { parseCss, type CssRule } from "./support/css";
import {
  declaredParameterNames,
  declaredPropertySchema,
  declaredPropertyNames,
  declaredRequestBodySchema,
} from "./support/openapi";
import {
  backendAbstentionText,
  backendEventStream,
  backendPublicMessages,
  backendStepLabels,
  backendStreamEvents,
} from "./support/python";
import { consoleSourcePaths, staticImportGraph } from "./support/typescript";
import { readConsoleFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const ANSWER_API = "/api/v1/answer";
const ANSWER_ROUTE = "/api/v1/answer";
const SHEET = "src/styles/app.css";

/** The narrowest phone this page is held to, in CSS pixels. */
const PHONE_WIDTH_PX = 360;
/** The smallest tap target, in CSS pixels. */
const TAP_TARGET_PX = 44;

/**
 * A question with a value in it that occurs nowhere else in this repository, so that looking
 * for it in every address the console touched is a search that can only find this question.
 */
const QUESTION = "what is the balance on CANARY-QUESTION-8fd41c";

/** A value with nowhere to break, which is what an identifier from a system of record is. */
const UNBROKEN = `UNBROKEN${"x".repeat(72)}`;

/**
 * One frame, built the way `brain.gate.streaming.encode` builds one: the event name, then one
 * `data:` field per line of the value, then the blank line that ends it.
 */
function frame(name: string, data: string): string {
  return [`event: ${name}`, ...data.split("\n").map((line) => `data: ${line}`)].join("\n") + "\n\n";
}

/** A stream somebody else pushes frames into, as a `Response` the stand-in API can answer. */
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

/** The console on the ask screen, with the stand-in API answering whatever the test hands it. */
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

/** Type a question in and press the button, which is what the keyboard does to a submit. */
function ask(container: HTMLElement, question: string): void {
  const field = container.querySelector("textarea");
  if (!field) {
    throw new Error("No question field was rendered.");
  }
  fireEvent.change(field, { target: { value: question } });
  const button = [...container.querySelectorAll("button")].find(
    (one) => one.textContent === ASK_LABEL,
  );
  if (!button) {
    throw new Error("No ask button was rendered.");
  }
  fireEvent.click(button);
}

/** Every request the console made to the answer route, with its method and parsed body. */
function asked(idp: FakeIdp): { method: string; body: unknown; accept: unknown }[] {
  return idp.calls
    .filter((call) => new URL(call.url, CONSOLE_ORIGIN).pathname === ANSWER_API)
    .map((call) => ({
      method: String(call.init?.method ?? "GET"),
      body: JSON.parse(String(call.init?.body ?? "null")) as unknown,
      accept: (call.init?.headers as Record<string, string> | undefined)?.["accept"],
    }));
}

/** The frames an answer to one question is, as the lane sends them. */
function answerFrames(text: string, citations: readonly string[] = []): string {
  return [
    frame("step", "Reading your question"),
    frame("step", "Checking what you are able to see"),
    ...citations.map((one) => frame("citation", one)),
    frame("text", text),
    frame("done", ""),
  ].join("");
}

function whole(frames: string): () => Response {
  return () =>
    new Response(frames, { status: 200, headers: { "content-type": EVENT_STREAM } });
}

/** The text of one piece of markup, for the digit checks. */
function textOf(markup: string): string {
  const holder = document.createElement("div");
  holder.innerHTML = markup;
  return holder.textContent ?? "";
}

/** The one rule for a class outside any at-rule. Throws when there is none, or more than one. */
function baseRule(rules: readonly CssRule[], className: string): CssRule {
  const found = rules.filter(
    (rule) =>
      rule.atRule === "" &&
      rule.selector.split(",").some((one) => new RegExp(`\\.${className}(?![\\w-])`).test(one)),
  );
  if (found.length !== 1) {
    throw new Error(`Expected one base rule for .${className}, found ${found.length}.`);
  }
  return found[0] as CssRule;
}

// --------------------------------------------------------------- what comes off the wire

describe("reading an event stream", () => {
  test("the names this console will draw are the API's five, and a sixth reaches nothing", () => {
    // What breaks if this is deleted: a console that renders whatever event name arrives,
    // which is the reasoning member `brain.gate.streaming.Event` exists to refuse, arriving
    // from the other end. The five are compared with the Python enum, both ways, and a name
    // outside them parses to nothing rather than to a frame with an unknown label.
    expect([...ANSWER_EVENTS].sort()).toEqual([...backendStreamEvents()].sort());

    for (const forbidden of ["reasoning", "thinking", "plan", "tool_input", "scratchpad"]) {
      expect(eventIn(frame(forbidden, "a model talking to itself"))).toBeNull();
    }
    expect(eventIn(frame("text", "an answer"))).toEqual({ name: "text", data: "an answer" });
  });

  test("a blank line inside a value survives, so a cached answer keeps the sentence saying its age", () => {
    // What breaks if this is deleted: the sentence after `answer_cache.AGE_SEPARATOR`, which
    // is two newlines, silently dropped by a reader that took the first `data:` field or
    // joined them with a space. That is the omission `AgeNotSurfacedError` exists to prevent,
    // arriving through the client instead. The encoder writes one field per line and this
    // reads them back the same way.
    const aged = "The balance is 400.\n\nThis was asked a moment ago.";

    expect(eventIn(frame("text", aged))).toEqual({ name: "text", data: aged });
  });

  test("a carriage return is one line break and half of one is not a frame boundary", () => {
    // What breaks if this is deleted: a CRLF read as two breaks, which ends a frame in the
    // middle of its own data, and a chunk that ends between the two halves of one doing the
    // same thing. This repository writes CRLF by accident often enough to have a note about
    // it in CLAUDE.md.
    expect(eventIn("event: text\r\ndata: one\r\ndata: two")).toEqual({
      name: "text",
      data: "one\ntwo",
    });

    const split = framesIn("event: text\r\ndata: one\r");
    expect(split.frames).toEqual([]);
    expect(framesIn(split.rest + "\ndata: two\r\n\r\n").frames.map(eventIn)).toEqual([
      { name: "text", data: "one\ntwo" },
    ]);
  });

  test("an id on a frame is kept nowhere, so knowing a string is never a way to be served an answer", () => {
    // What breaks if this is deleted: a reader that keeps `Last-Event-ID` and reconnects with
    // it, which is the resumption token `encode` has no parameter for. The event that comes
    // out carries a name and data and has no third field to hold one.
    const withId = "event: text\nid: 42\nretry: 3000\ndata: an answer\n\n";
    const event = eventIn(withId);

    expect(event).toEqual({ name: "text", data: "an answer" });
    expect(Object.keys(event ?? {}).sort()).toEqual(["data", "name"]);
  });

  test("a heartbeat is traffic and not a frame anybody draws", () => {
    // What breaks if this is deleted: the comment frame a proxy counts as traffic rendered as
    // an empty step, so an idle stream draws a row every ten seconds.
    expect(framesIn(": still working\n\n").frames.map(eventIn)).toEqual([null]);
  });

  test("the media type asked for is the one the route serves", () => {
    // What breaks if this is deleted: a console that sends `accept: application/json` for an
    // event stream, which is the header every other call in this file sends and the one that
    // makes this route's body one long string. Held against the route's own constant.
    expect(EVENT_STREAM).toBe(backendEventStream());
  });
});

// ------------------------------------------------------------------ asking and reading

describe("asking a question", () => {
  test("a question is asked and its answer is read, with what it stands on above it", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page that draws
    // nothing. One question, typed and pressed, produces one POST and the answer on the
    // screen, with the citations the route sent rendered as it rendered them and in its
    // order.
    const citations = [
      `client ${UNBROKEN}: balance from a-system-of-record, as of 2019-03-04T09:00:00Z`,
      `client ${UNBROKEN}: owner from a-system-of-record, as of 2019-03-04T09:00:00Z`,
    ];
    const { container, idp } = await askScreen(whole(answerFrames("The balance is 400.", citations)));

    ask(container, QUESTION);

    await waitFor(() => {
      expect(page(container).querySelector(".ask__answer")?.textContent).toBe(
        "The balance is 400.",
      );
    });
    expect(page(container).querySelector(".ask__provenance h2")?.textContent).toBe(BASED_ON);
    expect([...page(container).querySelectorAll(".ask__sources li")].map((one) => one.textContent)).toEqual(
      citations,
    );
    expect(asked(idp)).toEqual([
      { method: "POST", body: { question: QUESTION }, accept: EVENT_STREAM },
    ]);
    expect(page(container).textContent).not.toContain(NOTHING_ASKED_YET);
  });

  test("the steps on the screen are the frames the API sent, and they go when the answer is here", async () => {
    // What breaks if this is deleted: a progress bar this console animated, or a list of
    // steps left under a finished answer as decoration. The frames are pushed one at a time,
    // so what is on the screen between them is observable: the labels the API sent, in its
    // order, inside a live region, and nothing afterwards.
    const pushed = pushedStream();
    const { container } = await askScreen(() => pushed.response);

    ask(container, QUESTION);
    pushed.push(frame("step", "Reading your question"));
    pushed.push(frame("step", "Checking what you are able to see"));

    await waitFor(() => {
      const live = page(container).querySelector('[role="status"]');
      expect([...(live?.querySelectorAll("li") ?? [])].map((one) => one.textContent)).toEqual([
        "Reading your question",
        "Checking what you are able to see",
      ]);
      expect(live?.getAttribute("aria-label")).toBe(PROGRESS_LABEL);
    });

    pushed.push(frame("text", "The balance is 400."));
    pushed.push(frame("done", ""));
    pushed.close();

    await waitFor(() => {
      expect(page(container).querySelector(".ask__answer")?.textContent).toBe(
        "The balance is 400.",
      );
    });
    expect(page(container).querySelector('[role="status"]')).toBeNull();
    expect(page(container).querySelector(".ask__steps")).toBeNull();
  });

  test("this console holds no copy of the API's progress labels", async () => {
    // What breaks if this is deleted: a vocabulary copied into the bundle, which is a seventh
    // sentence nobody held to the checks the Python side runs over the six, and which would
    // be shown when the route sent something else. Every label is read from
    // `brain.gate.streaming.STEP_LABELS` and looked for in every source file this console
    // ships.
    const labels = backendStepLabels();
    expect(labels.length).toBeGreaterThan(1);

    const holding = consoleSourcePaths("src")
      .map((path) => ({ path, text: readConsoleFile(path) }))
      .filter((file) => labels.some((label) => file.text.includes(label)))
      .map((file) => file.path);

    expect(holding).toEqual([]);
  });

  test("an answer is asked again by asking again, and the address never changes", async () => {
    // What breaks if this is deleted: a question in the address bar, in browser history and
    // in the proxy's access log, which is the whole reason this route is a POST. The address
    // is checked after the answer has arrived, so a page that navigated to record what it
    // asked would fail here rather than in a reading of the source.
    const { container, router, idp } = await askScreen(whole(answerFrames("The balance is 400.")));

    ask(container, QUESTION);
    await waitFor(() => {
      expect(page(container).querySelector(".ask__answer")).not.toBeNull();
    });

    expect(router.state.location.pathname).toBe(ASK_ADDRESS);
    expect(router.state.location.search).toBe("");
    for (const url of idp.urls) {
      expect(url, "the question reached an address").not.toContain("CANARY-QUESTION");
      expect(decodeURIComponent(url)).not.toContain("balance");
    }
  });

  test("the question can only travel in a body, because the route declares nowhere else to put it", () => {
    // What breaks if this is deleted: a query parameter or a path segment added later and
    // used by a console that already had somewhere to put a question. The route's own
    // document is read: the question and the optional agent the person picked are the body's
    // only properties, no query parameter and no path parameter, and the bound the field holds is
    // the document's bound rather than a number copied here.
    expect(ANSWER_API_PATH).toBe("/answer");
    expect(declaredPropertyNames(declaredRequestBodySchema(ANSWER_ROUTE, "post"))).toEqual([
      "agent",
      "question",
    ]);
    expect(declaredParameterNames(ANSWER_ROUTE, "post", "query")).toEqual([]);
    expect(declaredParameterNames(ANSWER_ROUTE, "post", "path")).toEqual([]);

    const field = declaredPropertySchema(ANSWER_ROUTE, "post", "question");
    expect(MAX_QUESTION_CHARS).toBe(field["maxLength"]);
    expect(askBody("x".repeat(MAX_QUESTION_CHARS))).toEqual({
      question: "x".repeat(MAX_QUESTION_CHARS),
    });
    expect(askBody("x".repeat(MAX_QUESTION_CHARS + 1))).toBeNull();
    expect(askBody("   ")).toBeNull();
    expect(askBody(`  ${QUESTION}  `)).toEqual({ question: QUESTION });
  });

  test("a question the route would refuse is not sent at all", async () => {
    // What breaks if this is deleted: a round trip spent to be told what this console already
    // knew, and a button that looks as though it did something. Nothing is asked and the
    // screen still says nothing has been asked.
    const { container, idp } = await askScreen(whole(answerFrames("never reached")));

    ask(container, "   ");

    expect(asked(idp)).toEqual([]);
    expect(page(container).textContent).toContain(NOTHING_ASKED_YET);
  });
});

// ------------------------------------------------------------------------- refusals

describe("a refusal", () => {
  test("a refusal is the lane's own sentence, drawn by the code that draws an answer", async () => {
    // What breaks if this is deleted: a console that recognises a refusal and says something
    // about it, which is the DENIED and ABSENT distinction rebuilt in the friendliest
    // available voice. The two streams differ only in the sentence the text frame carries, so
    // the markup must differ only in that sentence: any branch on the text, on its length or
    // on there being no citations fails here.
    const refusal = backendAbstentionText();
    const ordinary = "The balance is 400.";
    expect(refusal).toBeTruthy();

    const refused = await askScreen(whole(answerFrames(refusal)));
    ask(refused.container, QUESTION);
    await waitFor(() => {
      expect(refused.container.querySelector(".ask__answer")).not.toBeNull();
    });
    const refusedMarkup = page(refused.container).innerHTML;

    const answered = await askScreen(whole(answerFrames(ordinary)));
    ask(answered.container, QUESTION);
    await waitFor(() => {
      expect(answered.container.querySelector(".ask__answer")).not.toBeNull();
    });

    expect(refusedMarkup).toContain(refusal);
    expect(refusedMarkup.split(refusal).join(ordinary)).toBe(page(answered.container).innerHTML);

    // And the other half, because the two streams above differ only in their sentence and a
    // branch that treated both the same way would be invisible to the comparison. What came
    // back with the answer must not change the answer either: a sentence added when nothing
    // was cited is the same disclosure by the one signal a refusal really does carry, and it
    // was a mutation that survived the comparison above until this was written.
    const cited = await askScreen(whole(answerFrames(refusal, ["client 1: balance from s"])));
    ask(cited.container, QUESTION);
    await waitFor(() => {
      expect(cited.container.querySelector(".ask__answer")).not.toBeNull();
    });

    expect(cited.container.querySelector(".ask__answer")?.outerHTML).toBe(
      refused.container.querySelector(".ask__answer")?.outerHTML,
    );
  });

  test("nothing beside a refusal explains it, and nothing on the page is a figure", async () => {
    // What breaks if this is deleted: "you may not have permission to see this", which turns
    // one sentence back into two answers, or a count of the records that were read, the
    // sources searched or the citations withheld. Two things are exempt from the digit check
    // and neither is the console's: the answer's own text, because an answer legitimately
    // carries figures, and the field holding what this person typed. Everything the console
    // drew around them is not exempt.
    const refusal = backendAbstentionText();
    const { container } = await askScreen(whole(answerFrames(refusal)));

    ask(container, QUESTION);
    await waitFor(() => {
      expect(container.querySelector(".ask__answer")).not.toBeNull();
    });

    const drawn = page(container);
    const around = drawn.cloneNode(true) as HTMLElement;
    around.querySelectorAll(".ask__answer, .ask__form").forEach((one) => one.remove());
    expect(textOf(around.innerHTML)).not.toMatch(/\d/);
    for (const wording of [/permission/i, /denied/i, /not allowed/i, /you may not/i, /access/i]) {
      expect(drawn.textContent ?? "").not.toMatch(wording);
    }
  });

  test("an answer with more sources behind it says no more than one with fewer", async () => {
    // What breaks if this is deleted: "based on 7 records", which is a count taken behind a
    // permission predicate and therefore a statement about what the reader was not shown. Two
    // answers differing only in how many citations came back must draw the same markup apart
    // from the rows themselves, and neither may carry a figure. The field holding what this
    // person typed is taken out with the rows, because what they typed is theirs.
    const many = ["a: one from s", "b: two from s", "c: three from s", "d: four from s"];
    const few = ["a: one from s"];

    const drawn: string[] = [];
    for (const citations of [few, many]) {
      const mounted = await askScreen(whole(answerFrames("An answer.", citations)));
      ask(mounted.container, QUESTION);
      await waitFor(() => {
        expect(mounted.container.querySelector(".ask__answer")).not.toBeNull();
      });
      const around = page(mounted.container).cloneNode(true) as HTMLElement;
      around.querySelectorAll(".ask__sources, .ask__form").forEach((one) => one.remove());
      drawn.push(around.innerHTML);
    }

    expect(drawn[0]).toBe(drawn[1]);
    expect(textOf(drawn[0] ?? "")).not.toMatch(/\d/);
  });

  test("an error frame is the sentence it carried, and nothing follows it", () => {
    // What breaks if this is deleted: a diagnostic rendered as an answer, or an answer
    // rendered after the stream has said it failed. The reducer is the whole of what decides
    // this, so it is asserted on the reducer as well as through the page.
    const failed = withEvent(withEvent(NOTHING_ASKED, { name: "error", data: "I could not do that." }), {
      name: "text",
      data: "a chunk that arrived after the failure",
    });

    expect(failed.failed).toBe("I could not do that.");
    expect(failed.answer).toBe("");

    const closed = withEvent(withEvent(NOTHING_ASKED, { name: "done", data: "" }), {
      name: "text",
      data: "a chunk after done",
    });
    expect(closed.answer).toBe("");
  });
});

// ------------------------------------------------------------ a request that never streamed

describe("a request the API refused", () => {
  test("a failure is the API's own sentence and its reference, through the console's one mapping", async () => {
    // What breaks if this is deleted: a page that explains a failure in its own words, or one
    // that draws an empty answer over it. The sentence is the one the Python side sends, and
    // the reference is the header every response carries.
    const sentence = backendPublicMessages()["FAILED"];
    expect(sentence).toBeTruthy();

    const { container } = await askScreen(
      () =>
        new Response(JSON.stringify({ message: sentence }), {
          status: 500,
          headers: { "content-type": "application/json", "x-trace-id": "trace-ask" },
        }),
    );

    ask(container, QUESTION);

    await waitFor(() => {
      expect(container.querySelector(".notice__body")?.textContent).toBe(sentence);
    });
    expect(container.querySelector(".notice__trace code")?.textContent).toBe("trace-ask");
    expect(page(container).querySelector(".ask__answer")).toBeNull();
    expect(page(container).querySelector(".ask__provenance")).toBeNull();
  });

  test("a refusal with no body falls back to the API's own words and says nothing about which kind it was", async () => {
    // What breaks if this is deleted: "not found" written here, which is the console's own
    // wording for the one status this API spends a taxonomy making ambiguous. The fallback is
    // the sentence copied from `brain.core.errors`, which is the same for denied and absent.
    // Where a reference would be, the notice says none came back rather than drawing one or
    // leaving a gap: see `ui/FailureNotice.A_FAILURE_WITHOUT_ITS_REFERENCE_IS_A_DEAD_END`.
    const { container } = await askScreen(() => new Response("", { status: 404 }));

    ask(container, QUESTION);

    await waitFor(() => {
      expect(container.querySelector(".notice__body > p")?.textContent).toBe(NOT_FOUND_MESSAGE);
    });
    expect(container.querySelector(".notice__trace")?.textContent).toBe(NO_REFERENCE_CAME_BACK);
    expect(container.querySelector(".notice__trace code")).toBeNull();
  });
});

// ------------------------------------------------------------------ keyboard and phone

describe("the ask screen without a mouse and on a phone", () => {
  test("the field is named, reachable in order, and every control is a native one", async () => {
    // What breaks if this is deleted: a text box with placeholder text instead of a label,
    // which is announced as nothing and disappears as soon as somebody types, or a div acting
    // as a button. The order is the document's, because nothing here sets a tabindex.
    const { container } = await askScreen(whole(answerFrames("An answer.")));

    const label = page(container).querySelector("label");
    const field = page(container).querySelector("textarea");
    expect(label?.textContent).toBe(QUESTION_LABEL);
    expect(label?.getAttribute("for")).toBe(field?.getAttribute("id"));
    expect(field?.getAttribute("id")).toBeTruthy();

    const reachable = [...page(container).querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [tabindex]")];
    expect(reachable.map((one) => one.tagName)).toEqual(["TEXTAREA", "BUTTON"]);
    for (const one of reachable) {
      expect(one.getAttribute("tabindex")).toBeNull();
    }
  });

  test("submitting the form asks the question, which is what the keyboard does to a submit button", async () => {
    // What breaks if this is deleted: a button with a click handler and no form, which a
    // mouse activates and Enter does not. The request is made by submitting the form itself,
    // so nothing about a pointer is involved.
    const { container, idp } = await askScreen(whole(answerFrames("An answer.")));
    const field = page(container).querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: QUESTION } });

    fireEvent.submit(page(container).querySelector("form") as HTMLFormElement);

    await waitFor(() => {
      expect(page(container).querySelector(".ask__answer")).not.toBeNull();
    });
    expect(asked(idp).map((one) => one.body)).toEqual([{ question: QUESTION }]);
  });

  test("the field and the button are a thumb tall, and the answer keeps its own lines", async () => {
    // What breaks if this is deleted: controls a cursor can hit and a thumb cannot, or an
    // answer whose blank lines are collapsed, which runs the sentence saying how old a cached
    // answer is into the answer itself. Each rule is paired with the element that carries its
    // class, because a rule for a class nothing renders is a layout that looks tested.
    const sheet = parseCss(readConsoleFile(SHEET));
    const control = baseRule(sheet, "ask__question");
    expect(pixels(control.declarations["min-height"] ?? "")).toBeGreaterThanOrEqual(TAP_TARGET_PX);
    expect(baseRule(sheet, "ask__answer").declarations["white-space"]).toBe("pre-wrap");
    expect(baseRule(sheet, "ask__steps").declarations["list-style"]).toBe("none");

    const aged = "The balance is 400.\n\nThis was asked a moment ago.";
    const { container } = await askScreen(whole(answerFrames(aged, [`client ${UNBROKEN}: balance from s`])));
    ask(container, QUESTION);
    await waitFor(() => {
      expect(page(container).querySelector(".ask__answer")?.textContent).toBe(aged);
    });

    const rules = consoleRules();
    const answer = page(container).querySelector(".ask__answer") as Element;
    const field = page(container).querySelector("textarea") as Element;
    const button = page(container).querySelector("button.ask__submit") as Element;
    expect(pixels(declared(field, "min-height", rules, PHONE_WIDTH_PX) ?? "")).toBeGreaterThanOrEqual(
      TAP_TARGET_PX,
    );
    expect(pixels(declared(button, "min-height", rules, PHONE_WIDTH_PX) ?? "")).toBeGreaterThanOrEqual(
      TAP_TARGET_PX,
    );
    expect(inherited(answer, "white-space", rules, PHONE_WIDTH_PX)).toBe("pre-wrap");

    // A long identifier in a citation may break inside the screen, which it inherits from the
    // body rule rather than from a rule of its own. The citation is on the page, so this is a
    // claim about something rendered and not about a selector.
    const source = page(container).querySelector(".ask__sources li") as Element;
    expect(source.textContent).toContain(UNBROKEN);
    expect(inherited(source, "overflow-wrap", rules, PHONE_WIDTH_PX)).toBe("anywhere");
  });

  test("asking is in the navigation for everybody, at the address the route table registers", async () => {
    // What breaks if this is deleted: the one screen that proves an install reachable only by
    // typing its address. The link is compared with the route table rather than with a string
    // here, so a route renamed without the menu fails.
    const { container } = await askScreen(whole(answerFrames("An answer.")));
    const nav = [...container.querySelectorAll("nav a")].map((link) => [
      link.textContent ?? "",
      link.getAttribute("href") ?? "",
    ]);

    expect(nav).toContainEqual([ASK_HEADING, ASK_ADDRESS]);
    expect(container.querySelector("h1")?.textContent).toBe(ASK_HEADING);
  });

  test("the ask screen brings neither heavy library into the first response", async () => {
    // What breaks if this is deleted: the table or the form library arriving through this
    // page, which is the split `tests/bundle-split.test.ts` measures. This page is imported by
    // the entry deliberately, so what it may not do is reach either library.
    const reachable = new Set(staticImportGraph("src/pages/Ask.tsx").files);

    expect([...reachable].filter((file) => file.includes("components/DataTable"))).toEqual([]);
    expect([...reachable].filter((file) => file.includes("components/SchemaForm"))).toEqual([]);
  });
});
