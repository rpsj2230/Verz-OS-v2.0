/**
 * The Knowledge, Learning and Memory screens: what each draws, what each refuses to draw, and
 * what each says instead.
 *
 * All three stand on a store that is empty on every install today, so the failures worth testing
 * are the ones that look like the design working. A Verified column blank on every row looks like
 * SCREEN 7 and says nobody verified anything; a figure of zero learnt looks like SCREEN 8 and says
 * the system learnt nothing; an Undo button looks like the design and is refused every time it is
 * pressed. Each of those is asserted against over the rendered page.
 *
 * **What the API sends is compared with the Python models, not with this file's copy of them.**
 * `tests/support/python.ts` reads the field names out of `brain.estate_routes`, and the bounds a
 * request must respect are read out of the API's own document, so a field added to a response or a
 * bound tightened on a route fails here rather than being dropped or refused in silence.
 *
 * **The pages are rendered directly**, inside a router holding only their own paths, because the
 * route table and the navigation are wired by a separate change. The phone cases for these three
 * pages are written up for `tests/phone-width.test.tsx` beside that wiring.
 *
 * Task ids: M27.7.20, M27.7.21, M27.7.22
 */

import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import {
  CONTROLS_NOT_OFFERED,
  GROUPING_WITHHELD,
  Knowledge,
  MORE_ITEMS,
  NARROWS_THIS_PAGE,
  NOT_MEASURED,
  NO_ITEMS,
  NO_MATCH,
  ONLY_EXISTENCE_AND_REACH,
} from "../src/pages/Knowledge";
import {
  KNOWLEDGE_API_PATH,
  readKnowledgePage,
  type LibraryRow,
} from "../src/pages/knowledgeQuery";
import {
  DECIDE_NOT_OFFERED,
  FIGURES_ARE_OF_WHAT_YOU_CAN_SEE,
  KEEP_IT,
  Learning,
  PROMOTE_NOT_OFFERED,
  TIER_THREE_WITHHELD,
  UNDONE,
  UNDO_LABEL,
  WHERE_UNDO_IS_OFFERED,
} from "../src/pages/Learning";
import {
  LEARNING_API_PATH,
  UNDO_API_PATH,
  consideredSentence as reviewConsideredSentence,
  learnedRecently,
  readLearningPage,
} from "../src/pages/learningQuery";
import {
  EDIT_NOT_OFFERED,
  HOW_TO_READ_THE_HISTORY,
  Memory,
  NOTHING_TO_READ,
  ONE_PERSON_AT_A_TIME,
  consideredSentence,
} from "../src/pages/Memory";
import {
  MEMORY_API_PATH,
  REFERENCE_CHARS,
  SUBJECT_PARAMETER,
  kilobytes,
  memoryAddress,
  memoryApiPath,
  readMemoryPage,
  referenceProblem,
} from "../src/pages/memoryQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterSchema } from "./support/openapi";
import { backendModelFields } from "./support/python";

const ROUTES = "src/brain/estate_routes.py";
const API = "/api/v1";

/** A value that appears nowhere else, so a dropped one cannot be covered by another. */
function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
}

function libraryBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    items: [
      { item_id: "doc-web-sentinel", level: "department" },
      { item_id: "doc-company-sentinel", level: "company" },
      { item_id: "doc-mine-sentinel", level: "personal" },
    ],
    next_cursor: null,
    total: null,
    truncated: false,
    departments: ["sales", "web"],
    staleness: null,
    only_existence_and_reach_are_shown: true,
    freshness_and_use_are_not_measured: true,
    ...over,
  };
}

function learningBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    basis: "everyone",
    as_of: "2019-03-06T09:00:00Z",
    tier_one: [],
    tier_two: [],
    tier_three: [],
    tiers: [
      { tier: 0, changes: ["session_context"] },
      { tier: 1, changes: ["preference", sentinel("tier-one-change")] },
      { tier: 2, changes: ["fast_path_rule"] },
      { tier: 3, changes: ["scope_widening"] },
    ],
    considered: 500,
    undo_says: { superseded: sentinel("undo-supersedes"), demoted: sentinel("undo-demotes") },
    staleness: null,
    ...over,
  };
}

function aTierOne(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    memory_id: "m-one-sentinel",
    change: "preference",
    control_writes: "demoted",
    learned_at: "2019-03-05T09:00:00Z",
    in_effect: true,
    undo_offered: false,
    ...over,
  };
}

function memoryBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    subject_id: "u_subject",
    curated: [
      {
        memory_id: "m_stated",
        statement: sentinel("stated"),
        confidence: 0.98,
        formed_at: "2019-03-05T09:00:00Z",
      },
    ],
    extracted: [
      {
        memory_id: "m_inferred",
        statement: sentinel("inferred"),
        confidence: 0.61,
        formed_at: "2019-03-04T09:00:00Z",
      },
    ],
    history: [
      {
        memory_id: "m_inferred",
        replaced_id: null,
        at: "2019-03-04T09:00:00Z",
        diff: [],
        trigger: null,
        correction: null,
      },
      {
        memory_id: "m_stated",
        replaced_id: null,
        at: "2019-03-05T09:00:00Z",
        diff: [],
        trigger: null,
        correction: null,
      },
    ],
    considered_per_kind: 200,
    staleness: null,
    edit_is_not_writable: true,
    ...over,
  };
}

/** A stand-in API answering one path with one body, or with a refusal. */
function answering(path: string, body: unknown, status = 200): FakeIdp {
  return fakeIdentityProvider({
    api(url) {
      if (!new URL(url, "https://console.test").pathname.endsWith(`${API}${path}`)) {
        return null;
      }
      return new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    },
  });
}

/** Mount one page at one address, against a stand-in API, and wait for it to settle. */
async function mount(address: string, idp: FakeIdp): Promise<HTMLElement> {
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { container } = render(
    <MemoryRouter initialEntries={[address]}>
      <Routes>
        <Route path="/library" element={<Knowledge />} />
        <Route path="/learning" element={<Learning />} />
        <Route path="/memory" element={<Memory />} />
        <Route path="/memory/:subject" element={<Memory />} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return container;
}

function text(container: HTMLElement): string {
  return container.textContent ?? "";
}

function headers(container: HTMLElement): string[] {
  return [...container.querySelectorAll("th")].map((one) => one.textContent ?? "");
}

/** Every write the page sent to the API, with its body. */
function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, "https://console.test").pathname.startsWith("/api/"))
    .map((call) => ({
      path: new URL(call.url, "https://console.test").pathname,
      body: call.init?.body === undefined ? undefined : (JSON.parse(String(call.init.body)) as unknown),
    }));
}

function button(scope: ParentNode, name: string): HTMLButtonElement {
  const found = [...scope.querySelectorAll("button")].find(
    (one) => one.textContent === name || one.getAttribute("aria-label")?.startsWith(name),
  );
  if (!found) {
    throw new Error(`no button named ${name}`);
  }
  return found as HTMLButtonElement;
}

function confirmPanel(container: HTMLElement): HTMLElement {
  const found = container.querySelector(".confirm");
  if (!found) {
    throw new Error("no confirmation is open");
  }
  return found as HTMLElement;
}

// --- Knowledge -----------------------------------------------------------------------------------

describe("the Knowledge screen", () => {
  test("every field the API sends about the library is read", () => {
    // What breaks if this is deleted: a field added to the page model arrives and is dropped by
    // `readKnowledgePage`, which on this screen is a sentence about what the library cannot say
    // that nobody sees. The names come out of the Python source.
    const read = [
      "truncated",
      "departments",
      "staleness",
      "only_existence_and_reach_are_shown",
      "freshness_and_use_are_not_measured",
    ];

    expect(backendModelFields(ROUTES, "LibraryPage").sort()).toEqual([...read].sort());
    expect(backendModelFields(ROUTES, "LibraryRowView").sort()).toEqual(["item_id", "level"]);
  });

  test("the page asks for no more items than the route admits", () => {
    // What breaks if this is deleted: every load of this screen becomes a 422, which reaches a
    // person as the least useful sentence this console has. Read off the route's own parameter.
    const limit = declaredParameterSchema(`${API}${KNOWLEDGE_API_PATH}`, "get", "limit");

    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(LIST_PAGE_SIZE).toBeGreaterThanOrEqual(limit["minimum"] as number);
  });

  test("draws every item with its level, and says in words which of the design's columns are absent", async () => {
    // What breaks if this is deleted: the table can lose a row or a level, or grow Dept, Owner and
    // Verified columns drawn blank, which read as a library nobody owns and nobody has verified.
    const container = await mount("/library", answering(KNOWLEDGE_API_PATH, libraryBody()));

    expect(headers(container)).toEqual(["Item", "Visible to"]);
    for (const id of ["doc-web-sentinel", "doc-company-sentinel", "doc-mine-sentinel"]) {
      expect(text(container)).toContain(id);
    }
    expect(text(container)).toContain(ONLY_EXISTENCE_AND_REACH);
    expect(text(container)).toContain(NOT_MEASURED);
    expect(text(container)).toContain(CONTROLS_NOT_OFFERED);
    expect(text(container)).toContain(NARROWS_THIS_PAGE);
  });

  test("offers no Upload or Export control, and no button of any kind", async () => {
    // What breaks if this is deleted: a control the design draws is added with nothing behind it,
    // and a person pressing Upload is refused for a reason that reads as their own permissions.
    const container = await mount("/library", answering(KNOWLEDGE_API_PATH, libraryBody()));

    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  test("the counts are of the rows shown: three items, one of them company-wide, across two departments", async () => {
    // What breaks if this is deleted: a figure computed from something other than the rows on the
    // page, and the one available to compute it from is a total, which is the subtraction.
    const container = await mount("/library", answering(KNOWLEDGE_API_PATH, libraryBody()));
    const glance = container.querySelector('[aria-label="Knowledge at a glance"]');

    expect(glance?.textContent).toContain("3items listed below, from 2 departments you can see");
    expect(glance?.textContent).toContain("1listed below and visible to everyone");
    expect(glance?.textContent ?? "").not.toMatch(/\bof\b/);
  });

  test("a withheld grouping is a sentence and a permitted one lists the departments", async () => {
    // What breaks if this is deleted: null drawn as an empty list, which says the company has no
    // departments with documents, or a short list drawn under a heading meaning all of them.
    const withheld = await mount(
      "/library",
      answering(KNOWLEDGE_API_PATH, libraryBody({ departments: null })),
    );
    expect(text(withheld)).toContain(GROUPING_WITHHELD);
    expect(text(withheld)).not.toContain("from 2 departments");

    const listed = await mount("/library", answering(KNOWLEDGE_API_PATH, libraryBody()));
    const names = [...listed.querySelectorAll('[aria-label="Departments with items you may know exist"] li')];
    expect(names.map((one) => one.textContent)).toEqual(["sales", "web"]);
  });

  test("an empty library, a page with no match and a full page are three different sentences", async () => {
    // What breaks if this is deleted: an empty library and a search matching nothing collapse into
    // one sentence, and a full page stops saying that the search narrows only what it holds.
    const empty = await mount("/library", answering(KNOWLEDGE_API_PATH, libraryBody({ items: [] })));
    expect(text(empty)).toContain(NO_ITEMS);

    // The stand-in answers a search with nothing, as the route would for a reference nobody holds.
    const full = await mount(
      "/library",
      fakeIdentityProvider({
        api(url) {
          const asked = new URL(url, "https://console.test");
          if (!asked.pathname.endsWith(`${API}${KNOWLEDGE_API_PATH}`)) {
            return null;
          }
          const body = asked.searchParams.has("q") ? libraryBody({ items: [], truncated: true }) : libraryBody({ truncated: true });
          return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
        },
      }),
    );
    expect(text(full)).toContain(MORE_ITEMS);
    const search = full.querySelector('input[type="search"]') as HTMLInputElement;
    fireEvent.change(search, { target: { value: "nothing-matches-this" } });
    await waitFor(() => {
      expect(text(full)).toContain(NO_MATCH);
    });
  });

  test("a refusal is the API's own sentence and nothing else", async () => {
    // What breaks if this is deleted: a 404 explained as a permission problem, which tells a caller
    // the screen exists and they are not allowed it.
    const container = await mount(
      "/library",
      answering(KNOWLEDGE_API_PATH, { message: sentinel("refusal"), trace_id: "t-1" }, 404),
    );

    expect(text(container)).toContain(sentinel("refusal"));
    expect(container.querySelector("table")).toBeNull();
  });

  test("an unreadable body keeps both sentences about what the library cannot say", () => {
    // What breaks if this is deleted: a response in an unexpected shape drops the sentences exactly
    // when the console understands least, and the page draws an empty library with no explanation.
    const page = readKnowledgePage("not a page");

    expect(page.items).toEqual([]);
    expect(page.onlyExistenceAndReachAreShown).toBe(true);
    expect(page.freshnessAndUseAreNotMeasured).toBe(true);
    expect(page.departments).toBeNull();
  });
});

// --- Learning ------------------------------------------------------------------------------------

describe("the Learning screen", () => {
  test("every field the API sends about the review is read", () => {
    // What breaks if this is deleted: a field added to the review arrives and is dropped.
    const read = [
      "basis",
      "as_of",
      "tier_one",
      "tier_two",
      "tier_three",
      "tiers",
      "considered",
      "undo_says",
      "staleness",
    ];

    expect(backendModelFields(ROUTES, "LearningReviewView").sort()).toEqual([...read].sort());
  });

  test("the figures count the rows the API sent and say that is what they count", async () => {
    // What breaks if this is deleted: a figure read as the company's when it is a count of what this
    // reader was shown, which the API narrowed before sending, or a figure computed from something
    // other than the rows on the page.
    const container = await mount(
      "/learning",
      answering(LEARNING_API_PATH, learningBody({ tier_one: [aTierOne()], tier_three: [] })),
    );
    const glance = container.querySelector('[aria-label="Learning at a glance"]');

    expect(text(container)).toContain(FIGURES_ARE_OF_WHAT_YOU_CAN_SEE);
    expect(glance?.textContent ?? "").toContain("Applied automatically1");
    expect(text(container)).toContain(reviewConsideredSentence(500));
  });

  test("no promote or decide control is drawn, and undo is drawn only on a row the API offers it on", async () => {
    // What breaks if this is deleted: an undo button on every row, which the server refuses for a
    // reader without the authority, or promote and decide buttons that write nothing anywhere.
    const container = await mount(
      "/learning",
      answering(
        LEARNING_API_PATH,
        learningBody({
          tier_one: [
            aTierOne({ memory_id: "m-offered", undo_offered: true }),
            aTierOne({ memory_id: "m-not-offered" }),
            aTierOne({ memory_id: "m-undone", in_effect: false }),
          ],
        }),
      ),
    );

    expect([...container.querySelectorAll("button")].map((one) => one.getAttribute("aria-label"))).toEqual([
      `${UNDO_LABEL} m-offered`,
    ]);
    expect(text(container)).toContain(UNDONE);
    expect(text(container)).toContain(WHERE_UNDO_IS_OFFERED);
    expect(text(container)).toContain(PROMOTE_NOT_OFFERED);
    expect(text(container)).toContain(DECIDE_NOT_OFFERED);
  });

  test("undoing is confirmed in the API's words, keeping it sends nothing, and the review is read again", async () => {
    // What breaks if this is deleted: an undo with no second step, a confirmation that does not say
    // what the undo will write, or a page that goes on showing the change as applied after it was
    // undone.
    let undone = false;
    const idp = fakeIdentityProvider({
      api(url, init) {
        const path = new URL(url, "https://console.test").pathname;
        const ok = (body: unknown) =>
          new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
        if (path.endsWith(`${API}${UNDO_API_PATH}`) && init?.method === "POST") {
          undone = true;
          return ok({
            memory_id: "m-one-sentinel",
            took_effect: true,
            correction: "superseded",
            at: "2019-03-06T09:00:00Z",
            told: sentinel("undone-told"),
          });
        }
        if (path.endsWith(`${API}${LEARNING_API_PATH}`)) {
          return ok(
            learningBody({
              tier_one: [
                aTierOne({ control_writes: "superseded", in_effect: !undone, undo_offered: !undone }),
              ],
            }),
          );
        }
        return null;
      },
    });
    const container = await mount("/learning", idp);

    fireEvent.click(button(container, UNDO_LABEL));
    expect(confirmPanel(container).textContent).toContain(sentinel("undo-supersedes"));
    fireEvent.click(button(confirmPanel(container), KEEP_IT));
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(container, UNDO_LABEL));
    fireEvent.click(button(confirmPanel(container), UNDO_LABEL));
    await waitFor(() => {
      expect(text(container)).toContain(sentinel("undone-told"));
    });
    expect(posts(idp)).toEqual([{ path: `${API}${UNDO_API_PATH}`, body: { memory_id: "m-one-sentinel" } }]);
    await waitFor(() => {
      expect(text(container)).toContain(UNDONE);
    });
    expect(container.querySelectorAll("tbody button")).toHaveLength(0);
  });

  test("tier three withheld is a different sentence from tier three empty", async () => {
    // What breaks if this is deleted: null drawn as an empty tier, which tells a reader who may not
    // know where gated changes went that none went anywhere.
    const withheld = await mount(
      "/learning",
      answering(LEARNING_API_PATH, learningBody({ basis: "own", tier_three: null })),
    );
    // Read under the tier's own heading, because the figures card says the same sentence and a
    // page-wide search would be satisfied by that copy while the tier itself said something else.
    const heading = [...withheld.querySelectorAll("h3")].find((one) =>
      (one.textContent ?? "").startsWith("Tier three"),
    );
    expect(heading?.nextElementSibling?.textContent).toBe(TIER_THREE_WITHHELD);
    expect(text(withheld)).not.toContain(DECIDE_NOT_OFFERED);

    const open = await mount("/learning", answering(LEARNING_API_PATH, learningBody()));
    expect(text(open)).not.toContain(TIER_THREE_WITHHELD);
  });

  test("recorded learnings are three tables, one per tier, never one list with a tier column", async () => {
    // What breaks if this is deleted: the design's single table comes back, and a change that has
    // already happened sits beside a proposal waiting for a person under one set of controls.
    const container = await mount(
      "/learning",
      answering(
        LEARNING_API_PATH,
        learningBody({
          tier_one: [aTierOne()],
          tier_two: [
            {
              memory_id: "m-two-sentinel",
              change: "fast_path_rule",
              evidence: ["reasked"],
              promote_ready: false,
              learned_at: "2019-02-01T09:00:00Z",
            },
          ],
          tier_three: [{ memory_id: "m-three-sentinel", department: "web", back_to: "agent:a/learning" }],
        }),
      ),
    );
    const tables = [...container.querySelectorAll("table")];

    expect(tables).toHaveLength(3);
    expect(tables[0]?.textContent).toContain("m-one-sentinel");
    expect(tables[0]?.textContent).not.toContain("m-two-sentinel");
    expect(tables[1]?.textContent).toContain("m-two-sentinel");
    expect(tables[2]?.textContent).toContain("m-three-sentinel");
    expect(headers(container)).not.toContain("Tier");
  });

  test("the four-tier card lists the change kinds the API puts at each tier", async () => {
    // What breaks if this is deleted: the card drawn from this file's own idea of the tiers, and a
    // change the server gates listed under a tier that applies by itself.
    const container = await mount("/learning", answering(LEARNING_API_PATH, learningBody()));
    const card = container.querySelector('[aria-label="The four tiers"]');

    expect(card?.textContent).toContain(sentinel("tier-one-change"));
    expect(card?.textContent).toContain("scope_widening");
  });

  test("recent means the seven days before the API's own instant, over tiers one and two", () => {
    // What breaks if this is deleted: the window read off this browser's clock, so the same review
    // counts differently on two machines, or a learning from last month counted as this week's.
    const page = readLearningPage(
      learningBody({
        tier_one: [
          aTierOne({ memory_id: "a", learned_at: "2019-03-05T09:00:00Z" }),
          aTierOne({ memory_id: "b", learned_at: "2019-02-20T09:00:00Z" }),
        ],
      }),
    );

    expect(learnedRecently(page)).toBe(1);
  });
});

// --- Memory --------------------------------------------------------------------------------------

describe("the Memory screen", () => {
  test("every field the API sends about a person's memory is read", () => {
    // What breaks if this is deleted: a field added to the view arrives and is dropped.
    const read = [
      "subject_id",
      "curated",
      "extracted",
      "history",
      "considered_per_kind",
      "staleness",
      "edit_is_not_writable",
    ];

    expect(backendModelFields(ROUTES, "SubjectMemoryView").sort()).toEqual([...read].sort());
  });

  test("the reference is checked against the route's own bound before anything is asked", () => {
    // What breaks if this is deleted: a reference the route refuses is sent anyway, and a person is
    // answered with a 422 instead of being told what to fix.
    const subject = declaredParameterSchema(`${API}${MEMORY_API_PATH}`, "get", SUBJECT_PARAMETER);

    expect(subject["maxLength"]).toBe(REFERENCE_CHARS);
    expect(referenceProblem("")).not.toBeNull();
    expect(referenceProblem("u one")).not.toBeNull();
    expect(referenceProblem("u".repeat(REFERENCE_CHARS + 1))).not.toBeNull();
    expect(referenceProblem("u".repeat(REFERENCE_CHARS))).toBeNull();
    expect(referenceProblem("u_subject")).toBeNull();
  });

  test("with nobody named it asks the API nothing and says memory is read one person at a time", async () => {
    // What breaks if this is deleted: the bare screen asking for everybody's memory, which is the
    // directory of people the decision behind this screen refuses to be.
    const idp = answering(MEMORY_API_PATH, memoryBody());
    const container = await mount("/memory", idp);

    expect(text(container)).toContain(ONE_PERSON_AT_A_TIME);
    expect(idp.urls.some((url) => url.includes(MEMORY_API_PATH))).toBe(false);
  });

  test("a reference that fails the check is explained and never sent", async () => {
    // What breaks if this is deleted: the form navigates on anything typed and the API's refusal
    // is the only thing a person reads.
    const idp = answering(MEMORY_API_PATH, memoryBody());
    const container = await mount("/memory", idp);
    const input = container.querySelector("#memory-subject") as HTMLInputElement;

    fireEvent.change(input, { target: { value: "two words" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(text(container)).toContain(referenceProblem("two words") ?? "");
    expect(idp.urls.some((url) => url.includes(MEMORY_API_PATH))).toBe(false);
  });

  test("a person's memory is the design's card, both halves in their own words, and the history", async () => {
    // What breaks if this is deleted: the statements, the split between what a person stated and
    // what the system inferred, or the history can go missing, which is the opaque store this
    // screen exists to open.
    const idp = answering(MEMORY_API_PATH, memoryBody());
    const container = await mount("/memory/u_subject", idp);

    expect(idp.urls.some((url) => url.includes(`${MEMORY_API_PATH}?${SUBJECT_PARAMETER}=u_subject`))).toBe(true);
    const curated = container.querySelector('[aria-label="Curated"]');
    const extracted = container.querySelector('[aria-label="Extracted from conversations"]');
    expect(curated?.textContent).toContain(sentinel("stated"));
    expect(curated?.textContent).not.toContain(sentinel("inferred"));
    expect(extracted?.textContent).toContain(sentinel("inferred"));
    expect(text(container)).toContain(HOW_TO_READ_THE_HISTORY);
    expect(text(container)).toContain(EDIT_NOT_OFFERED);
    expect(text(container)).toContain(consideredSentence(200));
    expect(headers(container)).toEqual(["When", "Memory", "Replaced", "What changed", "Why"]);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(text(container)).not.toContain(NOTHING_TO_READ);
  });

  test("a revision that carries a diff draws each line of it, and a memory put back is a step of its own", async () => {
    // What breaks if this is deleted: the diff the design says every revision has is dropped, or two
    // steps about the same memory, its forming and its being put back, collapse into one row.
    const container = await mount(
      "/memory/u_subject",
      answering(
        MEMORY_API_PATH,
        memoryBody({
          history: [
            {
              memory_id: "m_old",
              replaced_id: null,
              at: "2019-03-04T09:00:00Z",
              diff: [],
              trigger: null,
              correction: null,
            },
            {
              memory_id: "m_new",
              replaced_id: "m_old",
              at: "2019-03-05T09:00:00Z",
              diff: ["-Retainer ends in June", "+Retainer ends in September"],
              trigger: "contradicted",
              correction: "superseded",
            },
            {
              memory_id: "m_old",
              replaced_id: "m_new",
              at: "2019-03-06T09:00:00Z",
              diff: ["-Retainer ends in September", "+Retainer ends in June"],
              trigger: "rejected",
              correction: "superseded",
            },
          ],
        }),
      ),
    );

    expect(text(container)).toContain("+Retainer ends in September");
    expect(text(container)).toContain("superseded, contradicted");
    expect(text(container)).toContain("superseded, rejected");
    expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
  });

  test("a person with nothing readable is one sentence, whatever the reason", async () => {
    // What breaks if this is deleted: an empty answer drawn as two blank halves, or drawn in a way
    // that differs from a person nobody remembers, which the API took care to make identical.
    const container = await mount(
      "/memory/u_subject",
      answering(MEMORY_API_PATH, memoryBody({ curated: [], extracted: [], history: [] })),
    );

    expect(text(container)).toContain(NOTHING_TO_READ);
    expect(container.querySelector("table")).toBeNull();
  });

  test("addresses and requests keep a typed reference inside the console and inside its parameter", () => {
    // What breaks if this is deleted: an open redirect through a backslash reaching `useNavigate`,
    // GHSA-wrjc-x8rr-h8h6, or a reference with an ampersand turning into a second parameter.
    expect(memoryAddress("\\evil.example")).toBe("/memory/%5Cevil.example");
    expect(memoryApiPath("a&b=c")).toBe(`${MEMORY_API_PATH}?${SUBJECT_PARAMETER}=a%26b%3Dc`);
  });

  test("the card's sizes are the bytes of the statements shown", () => {
    // What breaks if this is deleted: a size computed in characters rather than bytes, which is
    // wrong for every statement written in a script that is not Latin.
    const page = readMemoryPage(memoryBody(), "u_subject");
    const oneKilobyte = [{ memory_id: "m", statement: "é".repeat(512), confidence: 1, formed_at: "" }];

    expect(kilobytes(oneKilobyte)).toBe("1.0");
    expect(page.consideredPerKind).toBe(200);
  });
});
