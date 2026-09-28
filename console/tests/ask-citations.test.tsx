/**
 * What an answer on Ask stands on, as a person sees it: every citation a link to what it names,
 * how fresh it is, a verified document's badge, and the document itself open at the passage.
 *
 * **Driven through the application's own route table**, signed in through the real session
 * modules, against a stand-in API answering `POST /api/v1/answer` with the frames
 * `brain.gate.streaming.AnswerStream.evidence` writes and `GET /api/v1/knowledge/documents/...` with
 * the body `brain.cited_document_routes.CitedDocument` declares, as `tests/ask-page.test.tsx` does.
 * The citation fields are the ones `brain.gate.provenance.Evidence.view` writes, read out of the
 * Python source, so a key renamed there fails here rather than drawing a blank.
 *
 * Task ids: M8.1.1, M8.1.2, M8.1.3, M7.4.7, M11.4.9
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { EVENT_STREAM } from "../src/api/events";
import { NOT_FOUND_MESSAGE } from "../src/api/errors";
import { ASK_ADDRESS, ASK_LABEL } from "../src/pages/Ask";
import {
  citationAddress,
  freshnessWords,
  readCitation,
  recordsAddressOf,
} from "../src/pages/askQuery";
import {
  anchorOf,
  CITED_HERE,
  CITED_PASSAGE_GONE,
  CITED_PASSAGE_NOT_SHOWN,
  citedDocumentAddress,
  MORE_THAN_SHOWN,
  UNTITLED,
} from "../src/pages/citedDocumentQuery";
import { recordsAddress } from "../src/pages/recordsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { extractOne, readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const ANSWER_API = "/api/v1/answer";
const DOCUMENT_API = "/api/v1/knowledge/documents/doc_handbook";
const QUESTION = "how much annual leave do we get";

/** The freshness words the API sends, read from `brain.gate.provenance.FRESHNESS_TEXT`. */
function freshnessText(state: "LIVE" | "AGEING" | "STALE" | "UNSTATED"): string {
  return extractOne(
    readRepoFile("src/brain/gate/provenance.py"),
    new RegExp(`^ {8}Freshness\\.${state}: "([^"]*)",$`, "m"),
    `FRESHNESS_TEXT[${state}] in brain.gate.provenance`,
  );
}

/** The stale sentence an answer's text carries, from `brain.gate.provenance.STALENESS_TEXT`. */
function staleSentence(): string {
  return extractOne(
    readRepoFile("src/brain/gate/provenance.py"),
    /^ {8}Freshness\.STALE: "([^"]*)",$/m,
    "STALENESS_TEXT[STALE] in brain.gate.provenance",
  );
}

/** Every key `Evidence.view` writes, read from its body: the dict's keys and the `update` names. */
function backendCitationKeys(): string[] {
  const body = extractOne(
    readRepoFile("src/brain/gate/provenance.py"),
    /^ {4}def view\(self\) -> dict\[str, str\]:\n([\s\S]*?)^ {4}@property$/m,
    "Evidence.view in brain.gate.provenance",
  );
  const keys = [
    ...[...body.matchAll(/^ {12}"(\w+)": /gm)].map((one) => one[1] ?? ""),
    ...[...body.matchAll(/^ {16}(\w+)=/gm)].map((one) => one[1] ?? ""),
  ];
  if (keys.length === 0) {
    throw new Error("Parsed no citation keys from Evidence.view; the parser is stale.");
  }
  return keys;
}

/** A citation frame's data, keys sorted, as `AnswerStream.evidence` writes it. */
function evidence(fields: Record<string, string>): string {
  const sorted = Object.fromEntries(Object.entries(fields).sort(([a], [b]) => a.localeCompare(b)));
  return JSON.stringify(sorted);
}

const RECORD = evidence({
  kind: "record",
  label: "client c_447: hours_remaining from laravel",
  source: "laravel",
  entity: "client",
  record_id: "c_447",
  field: "hours_remaining",
  freshness: "stale",
  freshness_text: freshnessText("STALE"),
  read_at: "2019-03-02T09:00:00+00:00",
  badge: "",
  badge_state: "",
});

const DOCUMENT = evidence({
  kind: "document",
  label: "Handbook, section Leave from knowledge",
  source: "knowledge",
  document_id: "doc_handbook",
  title: "Handbook",
  where: "section Leave",
  anchor: "chunk=doc_handbook.0002",
  freshness: "live",
  freshness_text: freshnessText("LIVE"),
  read_at: "2019-02-20T09:00:00+00:00",
  badge: "verified by p_steward on 2019-02-21",
  badge_state: "verified",
});

function frame(name: string, data: string): string {
  return [`event: ${name}`, ...data.split("\n").map((line) => `data: ${line}`)].join("\n") + "\n\n";
}

function answerFrames(text: string, citations: readonly string[]): string {
  return [
    frame("step", "Reading your question"),
    ...citations.map((one) => frame("citation", one)),
    frame("text", text),
    frame("done", ""),
  ].join("");
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-trace-id": "trace-cited" },
  });
}

const HANDBOOK = {
  document_id: "doc_handbook",
  title: "Handbook",
  passages: [
    { chunk_id: "doc_handbook.0001", section: "Booking", text: "Leave is booked ahead.", updated_at: "" },
    {
      chunk_id: "doc_handbook.0002",
      section: "Leave",
      text: "Annual leave is twenty five days a year.",
      updated_at: "",
    },
  ],
  truncated: false,
};

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly router: ReturnType<typeof createMemoryRouter>;
}

/** The console at `path`, with the stand-in API answering the answer and the document routes. */
async function mounted(path: string, frames: string, document: () => Response): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url) {
      const at = new URL(url, CONSOLE_ORIGIN).pathname;
      if (at === ANSWER_API) {
        return new Response(frames, { status: 200, headers: { "content-type": EVENT_STREAM } });
      }
      return at === DOCUMENT_API ? document() : null;
    },
  });
  const loaded = await loadConsole({ idp, path });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") && !container.querySelector(".notice")) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, idp, router };
}

async function asked(frames: string, document: () => Response = () => json(HANDBOOK)): Promise<Mounted> {
  const at = await mounted(ASK_ADDRESS, frames, document);
  const field = at.container.querySelector("textarea") as HTMLTextAreaElement;
  fireEvent.change(field, { target: { value: QUESTION } });
  const button = [...at.container.querySelectorAll("button")].find((one) => one.textContent === ASK_LABEL);
  fireEvent.click(button as HTMLButtonElement);
  await waitFor(() => {
    if (!at.container.querySelector(".ask__answer")) {
      throw new Error("no answer yet");
    }
  });
  return at;
}

function sources(container: HTMLElement): HTMLLIElement[] {
  return [...container.querySelectorAll<HTMLLIElement>(".ask__sources li")];
}

// ------------------------------------------------------------------ the fields on the wire

describe("a citation as the API sends it", () => {
  test("every field this console reads is one the API writes", () => {
    // What breaks if this is deleted: a key renamed in `Evidence.view` and not here, which draws
    // every citation unlinked and undated with nothing failing. Each key the Python body writes is
    // given a value and every field of the view must come back holding one.
    const keys = backendCitationKeys();
    const sent = Object.fromEntries(keys.map((key) => [key, `value-of-${key}`]));
    const view = readCitation(JSON.stringify(sent));

    for (const [name, value] of Object.entries(view)) {
      expect(value, `${name} is read from a key Evidence.view does not write`).not.toBe("");
    }
  });

  test("a frame that carried a sentence is drawn as that sentence and linked nowhere", () => {
    // What breaks if this is deleted: a citation from a sender that writes the rendered sentence,
    // which `AnswerStream.citation` still does, dropped because it was not an object.
    const view = readCitation("client 1: balance from s, as of 2019-03-04T09:00:00Z");

    expect(view.label).toBe("client 1: balance from s, as of 2019-03-04T09:00:00Z");
    expect(citationAddress(view)).toBeNull();
    expect(freshnessWords(view)).toBe("");
  });

  test("a record leads to its entity's rows at the Records screen's own address", () => {
    // What breaks if this is deleted: a record link built here drifting from the route table, so
    // following a citation lands on the console's not-found page.
    expect(citationAddress(readCitation(RECORD))).toBe(recordsAddressOf("client"));
    expect(recordsAddressOf("client")).toBe(recordsAddress("client", 1).split("?")[0]);
  });

  test("a document leads to the passage, which travels in the fragment and nowhere else", () => {
    // What breaks if this is deleted: the chunk put in a path or a query, where a request log
    // keeps it, or a link that opens the document and not the place in it.
    const address = citationAddress(readCitation(DOCUMENT));

    expect(address).toBe("/ask/documents/doc_handbook#chunk=doc_handbook.0002");
    expect(address).toBe(citedDocumentAddress("doc_handbook", "chunk=doc_handbook.0002"));
    expect(anchorOf("#chunk=doc_handbook.0002&page=4")).toBe("doc_handbook.0002");
    expect(anchorOf("#page=4")).toBe("");
    expect(citedDocumentAddress("doc a/b", "")).toBe("/ask/documents/doc%20a%2Fb");
  });

  test("an undated read is the API's words and no date", () => {
    // What breaks if this is deleted: "read time not stated, read Invalid Date".
    const undated = readCitation(
      evidence({ kind: "record", label: "x", freshness: "unstated", freshness_text: freshnessText("UNSTATED"), read_at: "" }),
    );

    expect(freshnessWords(undated)).toBe(freshnessText("UNSTATED"));
  });
});

// ------------------------------------------------------------------------ on the page

describe("citations on the Ask screen", () => {
  test("a record citation is a link to its rows, with how fresh the read was", async () => {
    // What breaks if this is deleted: the positive case every refusal is measured against, and
    // the leaf itself: a record and field named, followable, and dated.
    const { container } = await asked(answerFrames(`37 ${staleSentence()}`, [RECORD]));
    const [row] = sources(container);

    const link = row?.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/records/client");
    expect(link?.textContent).toBe("client c_447: hours_remaining from laravel");
    expect(row?.querySelector(".ask__evidence")?.textContent).toContain(`${freshnessText("STALE")}, read `);
  });

  test("a stale answer says so in its own text, drawn as the answer", async () => {
    // What breaks if this is deleted: the sentence the lane appends dropped or restyled here,
    // which is the one place a reader who opens no citation learns the figure is old.
    const { container } = await asked(answerFrames(`37 ${staleSentence()}`, [RECORD]));

    expect(container.querySelector(".ask__answer")?.textContent).toBe(`37 ${staleSentence()}`);
  });

  test("a document citation links to the passage and carries its verification badge", async () => {
    // What breaks if this is deleted: M8.1.2 and M7.4.7 on the screen, a document named with no way
    // to open it and a steward's verification that nobody sees.
    const { container } = await asked(answerFrames("Twenty five days.", [DOCUMENT]));
    const [row] = sources(container);

    expect(row?.querySelector("a")?.getAttribute("href")).toBe(
      "/ask/documents/doc_handbook#chunk=doc_handbook.0002",
    );
    expect(row?.querySelector(".badge")?.textContent).toBe("verified by p_steward on 2019-02-21");
    expect(row?.querySelector(".ask__evidence")?.textContent).toContain(`${freshnessText("LIVE")}, updated `);
  });

  test("following a document citation opens the document at the passage, marked and focused", async () => {
    // What breaks if this is deleted: a link that opens the top of the document, which leaves the
    // reader hunting for the sentence, or a page whose marked passage a keyboard never reaches.
    const { container, router } = await asked(answerFrames("Twenty five days.", [DOCUMENT]));
    fireEvent.click(sources(container)[0]?.querySelector("a") as HTMLAnchorElement);

    await waitFor(() => {
      expect(container.querySelector(".cited__passage--cited")).not.toBeNull();
    });
    expect(router.state.location.pathname).toBe("/ask/documents/doc_handbook");
    expect(router.state.location.hash).toBe("#chunk=doc_handbook.0002");
    const marked = container.querySelector(".cited__passage--cited") as HTMLElement;
    expect(marked.textContent).toContain("Annual leave is twenty five days a year.");
    expect(marked.textContent).toContain(CITED_HERE);
    expect(marked.getAttribute("aria-current")).toBe("location");
    // Focus is moved by an effect after the passage is drawn, so it is waited for, not assumed.
    await waitFor(() => {
      expect(document.activeElement).toBe(marked);
    });
    expect(container.querySelectorAll(".cited__passage").length).toBe(2);
  });
});

// ---------------------------------------------------------------- the cited document page

describe("the page a document citation opens", () => {
  test("a passage past what the page shows is said, and a passage no longer there is said differently", async () => {
    // What breaks if this is deleted: a marked passage that silently is not there, which reads as
    // the link having worked, and a document cut short with nothing saying so.
    const longer = await mounted("/ask/documents/doc_handbook#chunk=doc_handbook.0099", "", () =>
      json({ ...HANDBOOK, truncated: true }),
    );
    await waitFor(() => {
      expect(longer.container.textContent).toContain(CITED_PASSAGE_NOT_SHOWN);
    });
    expect(longer.container.textContent).toContain(MORE_THAN_SHOWN);

    const gone = await mounted("/ask/documents/doc_handbook#chunk=doc_handbook.0099", "", () => json(HANDBOOK));
    await waitFor(() => {
      expect(gone.container.textContent).toContain(CITED_PASSAGE_GONE);
    });
    expect(gone.container.textContent).not.toContain(MORE_THAN_SHOWN);
  });

  test("a title the reader may not read is not guessed at, and the reference is shown", async () => {
    // What breaks if this is deleted: a heading made up here for a document whose title the API
    // withheld, or a blank heading.
    const { container } = await mounted("/ask/documents/doc_handbook", "", () => json({ ...HANDBOOK, title: "" }));

    await waitFor(() => {
      expect(container.querySelector("h1")?.textContent).toBe(UNTITLED);
    });
    expect(container.querySelector(".page code")?.textContent).toBe("doc_handbook");
  });

  test("a document the reader may not open is the API's sentence and nothing about why", async () => {
    // What breaks if this is deleted: "you do not have access to this document", which tells a
    // person typing references which documents exist.
    const { container } = await mounted("/ask/documents/doc_handbook", "", () =>
      json({ message: NOT_FOUND_MESSAGE, trace_id: "trace-cited" }, 404),
    );

    await waitFor(() => {
      expect(container.querySelector(".notice__body")?.textContent).toContain(NOT_FOUND_MESSAGE);
    });
    const page = container.querySelector("article.page")?.textContent ?? "";
    for (const wording of [/permission/i, /denied/i, /not allowed/i, /access/i]) {
      expect(page).not.toMatch(wording);
    }
  });
});
