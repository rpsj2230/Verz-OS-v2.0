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
  EVERY_ROW,
  KNOWLEDGE_API_PATH,
  KNOWLEDGE_PAGE_SIZE,
  knowledgeApiPath,
  narrowed,
  readKnowledgePage,
  type LibraryRow,
} from "../src/pages/knowledgeQuery";
import {
  DECIDE_NOT_OFFERED,
  LEARNINGS_ARE_NOT_RECORDED,
  Learning,
  NOT_RECORDED,
  PROMOTE_NOT_OFFERED,
  TIER_THREE_WITHHELD,
  UNDO_NOT_OFFERED,
} from "../src/pages/Learning";
import { LEARNING_API_PATH, learnedRecently, readLearningPage } from "../src/pages/learningQuery";
import {
  EDIT_NOT_OFFERED,
  Memory,
  NOTHING_TO_READ,
  NO_DIFFS_YET,
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
    learnings_are_not_recorded: true,
    undo_is_not_writable: true,
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
    corrections_are_not_recorded: true,
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

    expect(KNOWLEDGE_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(KNOWLEDGE_PAGE_SIZE).toBeGreaterThanOrEqual(limit["minimum"] as number);
    expect(knowledgeApiPath()).toBe(`/govern/library?limit=${String(KNOWLEDGE_PAGE_SIZE)}`);
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

    expect(glance?.textContent).toContain("3items you can see, across 2 departments");
    expect(glance?.textContent).toContain("1visible to everyone");
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
    expect(text(withheld)).not.toContain("across 2 departments");

    const listed = await mount("/library", answering(KNOWLEDGE_API_PATH, libraryBody()));
    const names = [...listed.querySelectorAll('[aria-label="Departments with items on this page"] li')];
    expect(names.map((one) => one.textContent)).toEqual(["sales", "web"]);
  });

  test("an empty library, a page with no match and a full page are three different sentences", async () => {
    // What breaks if this is deleted: an empty library and a search matching nothing collapse into
    // one sentence, and a full page stops saying that the search narrows only what it holds.
    const empty = await mount("/library", answering(KNOWLEDGE_API_PATH, libraryBody({ items: [] })));
    expect(text(empty)).toContain(NO_ITEMS);

    const full = await mount("/library", answering(KNOWLEDGE_API_PATH, libraryBody({ truncated: true })));
    expect(text(full)).toContain(MORE_ITEMS);
    const search = full.querySelector("#knowledge-search") as HTMLInputElement;
    fireEvent.change(search, { target: { value: "nothing-matches-this" } });
    expect(text(full)).toContain(NO_MATCH);
    expect(text(full)).not.toContain(NO_ITEMS);
  });

  test("search, level and order narrow and sort only the rows the page holds", () => {
    // What breaks if this is deleted: the filter can drop the level test or the sort can stop being
    // stable, and a person reading the narrowed table reads the wrong items as the matching ones.
    const rows: LibraryRow[] = [
      { item_id: "b-web", level: "department" },
      { item_id: "a-mine", level: "personal" },
      { item_id: "c-all", level: "company" },
    ];

    expect(narrowed(rows, EVERY_ROW).map((one) => one.item_id)).toEqual(["a-mine", "b-web", "c-all"]);
    expect(narrowed(rows, { ...EVERY_ROW, sort: "level" }).map((one) => one.item_id)).toEqual([
      "c-all",
      "b-web",
      "a-mine",
    ]);
    expect(narrowed(rows, { ...EVERY_ROW, level: "company" }).map((one) => one.item_id)).toEqual(["c-all"]);
    expect(narrowed(rows, { ...EVERY_ROW, search: "WEB" }).map((one) => one.item_id)).toEqual(["b-web"]);
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
      "learnings_are_not_recorded",
      "undo_is_not_writable",
    ];

    expect(backendModelFields(ROUTES, "LearningReviewView").sort()).toEqual([...read].sort());
  });

  test("while nothing is recorded every figure is a sentence and no digit is drawn for one", async () => {
    // What breaks if this is deleted: four zeroes, which read as a system that learnt nothing and
    // has nothing waiting on anybody, which nothing on this install measured.
    const container = await mount("/learning", answering(LEARNING_API_PATH, learningBody()));
    const glance = container.querySelector('[aria-label="Learning at a glance"]');

    expect(text(container)).toContain(LEARNINGS_ARE_NOT_RECORDED);
    expect(glance?.textContent ?? "").toContain(NOT_RECORDED);
    expect((glance?.textContent ?? "").replace("last 7 days", "")).not.toMatch(/\d/);
  });

  test("no undo, promote or decide control is drawn, and each is a sentence where the design draws it", async () => {
    // What breaks if this is deleted: a button beside a tier-one row that writes nothing anywhere,
    // which docs/admin-console.md calls worse than no control at all.
    const container = await mount("/learning", answering(LEARNING_API_PATH, learningBody()));

    expect(container.querySelectorAll("button")).toHaveLength(0);
    expect(text(container)).toContain(UNDO_NOT_OFFERED);
    expect(text(container)).toContain(PROMOTE_NOT_OFFERED);
    expect(text(container)).toContain(DECIDE_NOT_OFFERED);
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
          learnings_are_not_recorded: false,
          tier_one: [
            {
              memory_id: "m-one-sentinel",
              change: "preference",
              control_writes: "demoted",
              learned_at: "2019-03-05T09:00:00Z",
            },
          ],
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
    expect(text(container)).not.toContain(LEARNINGS_ARE_NOT_RECORDED);
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
        learnings_are_not_recorded: false,
        tier_one: [
          { memory_id: "a", change: "preference", control_writes: "demoted", learned_at: "2019-03-05T09:00:00Z" },
          { memory_id: "b", change: "preference", control_writes: "demoted", learned_at: "2019-02-20T09:00:00Z" },
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
      "corrections_are_not_recorded",
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
    expect(text(container)).toContain(NO_DIFFS_YET);
    expect(text(container)).toContain(EDIT_NOT_OFFERED);
    expect(text(container)).toContain(consideredSentence(200));
    expect(headers(container)).toEqual(["When", "Memory", "Replaced", "What changed", "Why"]);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(text(container)).not.toContain(NOTHING_TO_READ);
  });

  test("a revision that carries a diff draws each line of it", async () => {
    // What breaks if this is deleted: the day corrections are recorded, the diff the design says
    // every revision has is dropped by the page that was built before there was one.
    const container = await mount(
      "/memory/u_subject",
      answering(
        MEMORY_API_PATH,
        memoryBody({
          corrections_are_not_recorded: false,
          history: [
            {
              memory_id: "m_new",
              replaced_id: "m_old",
              at: "2019-03-05T09:00:00Z",
              diff: ["-Retainer ends in June", "+Retainer ends in September"],
              trigger: "contradicted",
              correction: "superseded",
            },
          ],
        }),
      ),
    );

    expect(text(container)).toContain("+Retainer ends in September");
    expect(text(container)).toContain("superseded, contradicted");
    expect(text(container)).not.toContain(NO_DIFFS_YET);
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
