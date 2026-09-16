/**
 * The Skills screen: what it draws, what it refuses to draw, and what it says instead.
 *
 * This is SCREEN 6 of `docs/screens.html` built as far as the API can answer it, so the
 * failures worth testing are the ones that look like the design working. A blank Source column
 * looks like the specification and says nobody has recorded a source; an Approve button looks
 * like the specification and is refused every time it is pressed. Both are asserted against
 * here, over the rendered page rather than over a constant this file agrees with itself about.
 *
 * **Nothing around the library may count anything.** The listing is filtered per caller, so a
 * number is the subtraction `CLAUDE.md` forbids. The queue's counts are the exception and they
 * are the API's own, computed over exactly the entries listed beneath them, so the assertion is
 * that a digit on the page belongs to the queue and to nothing else.
 *
 * **The route's bounds are read out of the API's own document**, not compared with a second
 * constant here: a console asking for a page size a route refuses is a 422 on every load.
 *
 * **The real route table is mounted**, which is `routing.test.tsx`'s rule: the skill name is a
 * path segment, so the route is half of what is under test, and a test declaring its own route
 * would be testing the copy.
 *
 * Task ids: M42.6.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  ASSIGNMENT_IS_NOT_WRITABLE,
  DRIFT_IS_PINNED_BY_DESIGN,
  NOTHING_IS_RECORDED_AS_WAITING,
  NO_DRIFT,
  NO_SKILLS,
  NO_SUCH_SKILL,
  REVIEW_IS_NOT_RECORDED,
  queueCount,
} from "../src/pages/Skills";
import {
  SKILLS_PAGE_SIZE,
  driftingRows,
  readSkillsPage,
  skillAddress,
  skillIn,
  skillsApiPath,
  type SkillLibraryRow,
} from "../src/pages/skillsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterSchema, declaredQueryParameters } from "./support/openapi";

const SKILLS_OPERATION = "/api/v1/skills";
const CONSOLE_ORIGIN = "https://console.test";
const DIGEST_ONE = "a".repeat(64);
const DIGEST_TWO = "b".repeat(64);

interface QueueRow {
  name: string;
  waiting_since: string;
  changed: string[];
  stale: boolean;
}

/** One page of skills in the shape `brain.skill_routes.SkillsPage` serialises. */
function skillsPage(
  items: { name: string; pinned_by: { agent_id: string; digest: string }[]; versions_differ?: boolean }[],
  extra: { queue?: QueueRow[]; truncated?: boolean } = {},
): unknown {
  const queue = extra.queue ?? [];
  return {
    items: items.map((one) => ({
      name: one.name,
      pinned_by: one.pinned_by,
      versions_differ: one.versions_differ ?? false,
    })),
    next_cursor: null,
    total: null,
    truncated: extra.truncated ?? false,
    queue: {
      entries: queue,
      waiting: queue.length,
      edits: queue.filter((one) => one.changed.length > 0).length,
      stale: queue.filter((one) => one.stale).length,
    },
    review_is_not_recorded: true,
    assignment_is_not_writable: true,
  };
}

/** Mount the application's own route table at one address, against a stand-in API. */
async function consoleAt(
  path: string,
  body: unknown,
): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      if (!url.includes(SKILLS_OPERATION)) {
        return null;
      }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return { container, idp };
}

/** Every digit the page rendered, so a count outside the queue is a failure. */
function digitsOn(container: HTMLElement): string[] {
  return (container.querySelector(".page")?.textContent ?? "").match(/\d+/g) ?? [];
}

describe("what the skills screen asks for", () => {
  test("the listing sends only a query parameter the route declares", async () => {
    // What breaks if this is deleted: a parameter the API ignores. FastAPI drops an undeclared
    // query parameter without a word, so a console sending `rows` would get the route's default
    // page and read it as the page it asked for. The declared names come from the API's own
    // document rather than from this console's spelling.
    const declared = new Set(declaredQueryParameters(SKILLS_OPERATION, "get"));
    const { idp } = await consoleAt("/skills", skillsPage([]));

    const asked = idp.urls
      .filter((url) => url.includes(SKILLS_OPERATION))
      .flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);

    expect(asked.length).toBeGreaterThan(0);
    expect(asked.filter((name) => !declared.has(name))).toEqual([]);
  });

  test("the page size this console asks for is one the route will answer", async () => {
    // What breaks if this is deleted: every load of this screen becomes a 422, which reaches a
    // person as "Something went wrong." The bound is read off the route's own parameter.
    const limit = declaredParameterSchema(SKILLS_OPERATION, "get", "limit");

    expect(SKILLS_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(SKILLS_PAGE_SIZE).toBeGreaterThanOrEqual(limit["minimum"] as number);
    expect(skillsApiPath()).toBe(`/skills?limit=${String(SKILLS_PAGE_SIZE)}`);
  });

  test("an address this screen builds always stays inside the console", () => {
    // What breaks if this is deleted: an open redirect. GHSA-wrjc-x8rr-h8h6 is an open redirect
    // via a backslash reaching `<Link>`, it covers every react-router this project can install,
    // and a skill name arrives from the API, so the defence has to be here. What holds it up is
    // the literal `/skills/` prefix rather than the encoding.
    const hostile = ["\\\\evil.example", "//evil.example", "/\\evil.example", "http://evil.example", ".."];

    for (const name of hostile) {
      const address = skillAddress(name);
      expect(address.startsWith("/skills/")).toBe(true);
      expect(address.includes("evil.example") && !address.includes("%")).toBe(false);
    }
  });
});

describe("what the skills screen shows", () => {
  test("a skill is drawn with every agent pinned to it and the bytes each one runs", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page that renders
    // nothing at all. This is the positive case: the name, both agents and both digests.
    const { container } = await consoleAt(
      "/skills",
      skillsPage([
        {
          name: "hosting-expiry",
          pinned_by: [
            { agent_id: "company-desk", digest: DIGEST_ONE },
            { agent_id: "web-helper", digest: DIGEST_ONE },
          ],
        },
      ]),
    );

    expect(container.textContent).toContain("hosting-expiry");
    expect(container.textContent).toContain("company-desk");
    expect(container.textContent).toContain("web-helper");
    expect(container.textContent).toContain(DIGEST_ONE);
  });

  test("no row carries a source, a version, a reviewer or a state, and the page says why", async () => {
    // What breaks if this is deleted: the five columns SCREEN 6 asks for are drawn empty, which
    // says nobody has reviewed anything and every skill is unreviewed. The sentence replaces
    // them, and no row carries a word that would have headed one.
    const { container } = await consoleAt(
      "/skills",
      skillsPage([{ name: "hosting-expiry", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }]),
    );
    // The library's own text rather than the page's: the sentences explaining the absence use
    // the word approved, and a page-wide match would be satisfied by deleting the explanation.
    const library = container.querySelector('[aria-label="Skills in use"]')?.textContent ?? "";

    expect(container.textContent).toContain(REVIEW_IS_NOT_RECORDED);
    expect(library).toContain("hosting-expiry");
    expect(library).not.toMatch(
      /\bapproved\b|\bneeds review\b|\brejected\b|\bunreviewed\b|\bgithub\b|\bstudio\b/i,
    );
  });

  test("the screen offers no control at all and says what cannot be done here", async () => {
    // What breaks if this is deleted: Paste URL, Connect repo, Write in Studio, Approve and
    // Reject arrive as buttons whose every press is refused, because the API declares no write.
    // A sentence saying so is the honest version, and a button is not.
    const { container } = await consoleAt(
      "/skills",
      skillsPage([{ name: "hosting-expiry", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }]),
    );

    // Inside the page rather than the whole document: the shell draws a sign-out button and a
    // theme control, which belong to the frame and are on every screen in this console.
    const page = container.querySelector(".page") as HTMLElement;

    expect(page.querySelectorAll("button")).toHaveLength(0);
    expect(page.querySelector("form")).toBeNull();
    expect(container.textContent).toContain(ASSIGNMENT_IS_NOT_WRITABLE);
  });

  test("an empty library says one sentence, true for every reason it is empty", async () => {
    // What breaks if this is deleted: the page grows two sentences, one for "this company runs
    // no skills" and one for "your agents run none", and the difference between them is a fact
    // about agents this reader was not shown.
    const { container } = await consoleAt("/skills", skillsPage([]));

    expect(container.textContent).toContain(NO_SKILLS);
  });

  test("nothing outside the review queue is a number", async () => {
    // What breaks if this is deleted: a heading saying how many skills there are, which on a
    // listing filtered per caller tells a reader how many they were not shown. The digests are
    // letters here deliberately: a digit inside one would be a number this assertion cannot
    // tell from a count, and allowing for it would leave a hole the shape of the failure.
    const { container } = await consoleAt(
      "/skills",
      skillsPage([{ name: "hosting-expiry", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }], {
        truncated: true,
      }),
    );

    expect(digitsOn(container)).toEqual([]);
  });

  test("a queue entry is listed with the counts computed over exactly those entries", async () => {
    // What breaks if this is deleted: the counts and the list stop being one answer, and a
    // summary over a wider list than the listing is the subtraction that publishes how many
    // skills are waiting that this reader may not read.
    const { container } = await consoleAt(
      "/skills",
      skillsPage([], {
        queue: [
          {
            name: "xero-reconciliation",
            waiting_since: "2019-03-04T09:00:00Z",
            changed: ["body"],
            stale: true,
          },
        ],
      }),
    );

    expect(container.textContent).toContain("xero-reconciliation");
    expect(container.textContent).toContain(queueCount(1, 1, 1));
    expect(container.textContent).not.toContain(NOTHING_IS_RECORDED_AS_WAITING);
  });

  test("an empty queue says nothing is recorded rather than that everything has been read", async () => {
    // What breaks if this is deleted: a reviewer reads a clear queue as a clear queue, when
    // what it means is that this installation stores no submissions at all.
    const { container } = await consoleAt("/skills", skillsPage([]));

    expect(container.textContent).toContain(NOTHING_IS_RECORDED_AS_WAITING);
  });

  test("two agents on different bytes of one skill are listed as drift, and matching ones are not", async () => {
    // What breaks if this is deleted: the drift card SCREEN 6 shows goes quiet, and two agents
    // running two procedures under one name look like one skill.
    const drifting = await consoleAt(
      "/skills",
      skillsPage([
        {
          name: "hosting-expiry",
          pinned_by: [
            { agent_id: "a", digest: DIGEST_ONE },
            { agent_id: "b", digest: DIGEST_TWO },
          ],
          versions_differ: true,
        },
      ]),
    );
    const settled = await consoleAt(
      "/skills",
      skillsPage([{ name: "hosting-expiry", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }]),
    );

    expect(drifting.container.querySelector('[aria-label="Skills whose agents run different bytes"]')).not.toBeNull();
    expect(drifting.container.textContent).toContain(DRIFT_IS_PINNED_BY_DESIGN);
    expect(settled.container.textContent).toContain(NO_DRIFT);
  });

  test("a deep link to a skill this page does not carry says so about the page", async () => {
    // What breaks if this is deleted: the sentence becomes about the company, and "no such
    // skill" told to somebody whose agents do not use it is the oracle a deep link resolved
    // against the page exists to avoid.
    const { container } = await consoleAt(
      `/skills/${encodeURIComponent("quote-format")}`,
      skillsPage([{ name: "hosting-expiry", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }]),
    );

    expect(container.textContent).toContain(NO_SUCH_SKILL);
    expect(container.textContent).not.toMatch(/does not exist|not found|never imported/i);
  });

  test("an open skill draws its own pins and the same request as the bare listing", async () => {
    // What breaks if this is deleted: the deep link becomes a second question asked of the API,
    // which is the route this screen deliberately does not have. The URLs are compared because
    // the request is the thing the API judges.
    const rows = skillsPage([
      { name: "hosting-expiry", pinned_by: [{ agent_id: "company-desk", digest: DIGEST_ONE }] },
    ]);
    const open = await consoleAt(`/skills/${encodeURIComponent("hosting-expiry")}`, rows);
    const bare = await consoleAt("/skills", rows);

    const asked = (idp: FakeIdp) =>
      idp.urls
        .filter((url) => url.includes(SKILLS_OPERATION))
        .map((url) => new URL(url, CONSOLE_ORIGIN).pathname + new URL(url, CONSOLE_ORIGIN).search);

    expect(asked(open.idp)).toEqual(asked(bare.idp));
    expect(open.container.querySelector(".card")?.textContent).toContain("hosting-expiry");
    expect(bare.container.querySelector(".card")).toBeNull();
  });
});

describe("what the query module does with a body", () => {
  test("a body that is not a page still says the two things this install cannot do", () => {
    // What breaks if this is deleted: an unreadable answer drops the sentences exactly when the
    // console understands least, and the page reads as a library with nothing in it.
    const page = readSkillsPage({ unexpected: true });

    expect(page.skills).toEqual([]);
    expect(page.reviewIsNotRecorded).toBe(true);
    expect(page.assignmentIsNotWritable).toBe(true);
  });

  test("the total and the cursor have no path from the payload to a renderer", () => {
    // What breaks if this is deleted: `total` reaches a component and a footer counts the rows
    // a caller was shown, which on a filtered listing is a subtraction.
    const page = readSkillsPage(
      skillsPage([{ name: "a-skill", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }]),
    );

    expect(Object.keys(page).sort()).toEqual(
      [
        "assignmentIsNotWritable",
        "edits",
        "queue",
        "reviewIsNotRecorded",
        "skills",
        "stale",
        "truncated",
        "waiting",
      ].sort(),
    );
  });

  test("a skill is found on the page by its exact name and never by a prefix", () => {
    // What breaks if this is deleted: `/skills/hosting` opens `hosting-expiry`, and a link
    // somebody shares is a link to a different procedure from the one they were reading.
    const rows = [
      { name: "hosting-expiry", pinned_by: [], versions_differ: false },
      { name: "hosting", pinned_by: [], versions_differ: false },
    ] as unknown as SkillLibraryRow[];

    expect(skillIn(rows, "hosting")?.name).toBe("hosting");
    expect(skillIn(rows, "hosting-exp")).toBeNull();
  });

  test("drift is the rows the API marked and never a comparison this console made", () => {
    // What breaks if this is deleted: the console starts deciding what counts as drift by
    // comparing digests itself, which is a second answer to a question the API already
    // answered over rows this browser may not have all of.
    const rows = [
      { name: "a-skill", pinned_by: [], versions_differ: true },
      { name: "b-skill", pinned_by: [], versions_differ: false },
    ] as unknown as SkillLibraryRow[];

    expect(driftingRows(rows).map((one) => one.name)).toEqual(["a-skill"]);
  });
});
