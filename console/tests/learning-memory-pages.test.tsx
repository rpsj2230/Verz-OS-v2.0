/**
 * Learning and Memory on the page kit: the review one tier per view, each learning in a drawer, the
 * undo confirmed in the API's words, promote and decide drawn as not built yet, and one person's
 * memory chosen by name, read statement by statement and change by change.
 *
 * Reached through the application's own route table, signed in through the real session modules and
 * answered by a stand-in API, so a test passes only if the address resolves. The failures worth
 * testing look like the pages working: a figure of zero learnt that says the system learnt nothing,
 * an Undo button the server refuses every time, a promote control that writes nothing, a memory id
 * drawn where a person reads, and a list of whose memory exists.
 *
 * **What the API sends is compared with the Python models, not with this file's copy of them**, and
 * the bounds a request must respect are read out of the API's own document.
 *
 * Task ids: M27.7.21, M27.7.22, M27.16.1, M16.6.8, M16.5.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { UNAVAILABLE_MARK } from "../src/components/kit";
import { UNAVAILABLE } from "../src/pages/learning/learningActions";
import { KEEP_IT, TIER_THREE_WITHHELD, UNDO_LABEL, UNDONE } from "../src/pages/learning/LearningPage";
import {
  LEARNING_API_PATH,
  LEARNING_SETTINGS,
  LEARNING_SETTINGS_API_PATH,
  UNDO_API_PATH,
  consideredSentence,
  learnedRecently,
  readLearningPage,
} from "../src/pages/learningQuery";
import { NOTHING_TO_READ_DESCRIPTION } from "../src/pages/memory/MemoryDetailPage";
import { CHOOSE_HEADING } from "../src/pages/memory/MemoryPage";
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
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { apiDocument, declaredParameterSchema } from "./support/openapi";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

const ROUTES = "src/brain/estate_routes.py";
const API = "/api/v1";
const CONSOLE_ORIGIN = "https://console.test";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Learning");
  await import("../src/pages/Memory");
}, 60_000);

/** A value that appears nowhere else, so a dropped one cannot be covered by another. */
function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
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
      { tier: 1, changes: ["preference", "tier_one_sentinel"] },
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

function aTierTwo(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    memory_id: "m-two-sentinel",
    change: "fast_path_rule",
    evidence: ["repeated_question"],
    promote_ready: false,
    learned_at: "2019-03-05T09:00:00Z",
    ...over,
  };
}

function memoryBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    subject_id: "u_subject",
    curated: [{ memory_id: "m_stated", statement: sentinel("stated"), confidence: 0.98, formed_at: "2019-03-05T09:00:00Z" }],
    extracted: [{ memory_id: "m_inferred", statement: sentinel("inferred"), confidence: 0.61, formed_at: "2019-03-04T09:00:00Z" }],
    history: [
      { memory_id: "m_inferred", replaced_id: null, at: "2019-03-04T09:00:00Z", diff: [], trigger: null, correction: null },
      { memory_id: "m_stated", replaced_id: null, at: "2019-03-05T09:00:00Z", diff: [], trigger: null, correction: null },
    ],
    considered_per_kind: 200,
    staleness: null,
    edit_is_not_writable: true,
    ...over,
  };
}

/** The person's own page in the directory, which names them. */
const THE_PERSON = {
  person: { principal_id: "u_subject", display_name: "Priya Raman", standing: "live", packs: [] },
  placements: {},
  held: [],
};

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (path: string, method: string, body: unknown) => Response | null;

async function consoleAt(address: string, answer: Answer): Promise<{ container: HTMLElement; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const where = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null;
      sent.push({ method, path: where, body });
      return answer(where, method, body);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [address] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("main h1") || container.querySelector('main [data-slot="loading-state"]')) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, sent };
}

function reviewing(review: Record<string, unknown>, onUndo?: () => Response): Answer {
  return (path, method) => {
    if (path === `${API}${UNDO_API_PATH}` && method === "POST") {
      return onUndo?.() ?? null;
    }
    return path === `${API}${LEARNING_API_PATH}` ? json(review) : null;
  };
}

function mainText(container: HTMLElement): string {
  return container.querySelector("main")?.textContent ?? "";
}

function button(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find(
    (one) => one.textContent?.trim() === name || one.getAttribute("aria-label")?.startsWith(name),
  );
  if (found === undefined) {
    throw new Error(`No button reading ${name}.`);
  }
  return found;
}

function dialog(): HTMLElement {
  const found = document.body.querySelector<HTMLElement>('[data-slot="confirm-dialog"]');
  if (found === null) {
    throw new Error("No confirmation is open.");
  }
  return found;
}

function viewLinks(container: HTMLElement): string[] {
  return [...container.querySelectorAll('nav[aria-label="Learning views"] a')].map((one) => one.textContent ?? "");
}

// --- Learning ------------------------------------------------------------------------------------

describe("the Learning page", () => {
  test("every field the API sends about the review is read", () => {
    // What breaks if this is deleted: a field added to the review arrives and is dropped.
    const read = ["basis", "as_of", "tier_one", "tier_two", "tier_three", "tiers", "considered", "undo_says", "staleness", "queue_alarm"];
    expect(backendModelFields(ROUTES, "LearningReviewView").sort()).toEqual([...read].sort());
  });

  test("the figures count the rows the API sent, and the first view is tier one alone", async () => {
    // What breaks if this is deleted: a figure computed from something other than the rows sent, or
    // tier one and tier two drawn in one list whose controls mean different things.
    const { container } = await consoleAt(
      "/learning",
      reviewing(learningBody({ tier_one: [aTierOne(), aTierOne({ memory_id: "m-b" })], tier_two: [aTierTwo({ change: "tier_two_sentinel" })] })),
    );
    const figures = container.querySelector('[aria-label="Learnings you may see"]')?.textContent ?? "";
    expect(figures).toContain("Applied automatically2");
    expect(figures).toContain("In shadow1");
    expect(figures).toContain("Waiting on a person0");
    expect(mainText(container)).toContain("Preference");
    expect(mainText(container)).not.toContain("Tier two sentinel");
    expect(viewLinks(container)).toEqual(["Applied", "Shadow", "Waiting", "About"]);
  });

  test("undo is drawn only on a row the API offers it on and that is still in effect", async () => {
    // What breaks if this is deleted: an undo button on every row, which the server refuses for a
    // reader without the authority, or one on a learning already undone.
    const { container } = await consoleAt(
      "/learning",
      reviewing(
        learningBody({
          tier_one: [
            aTierOne({ memory_id: "m-offered", undo_offered: true, change: "offered_kind" }),
            aTierOne({ memory_id: "m-not-offered", change: "not_offered_kind" }),
            aTierOne({ memory_id: "m-undone", in_effect: false, undo_offered: true, change: "undone_kind" }),
          ],
        }),
      ),
    );
    const undos = [...(container.querySelector("tbody")?.querySelectorAll("button") ?? [])]
      .map((one) => one.getAttribute("aria-label") ?? "")
      .filter((one) => one.startsWith(UNDO_LABEL));
    expect(undos).toEqual([`${UNDO_LABEL} the offered kind learned 5 Mar 2019`]);
    expect(mainText(container)).toContain(UNDONE);
  });

  test("undoing is confirmed in the API's words, keeping it sends nothing, and the review is read again", async () => {
    // What breaks if this is deleted: an undo with no second step, a confirmation that does not say
    // what the undo will write, or a page that goes on showing the change as applied after it went.
    let undone = false;
    const { container, sent } = await consoleAt(
      "/learning",
      (path, method) => {
        if (path === `${API}${UNDO_API_PATH}` && method === "POST") {
          undone = true;
          return json({ memory_id: "m-one-sentinel", took_effect: true, correction: "demoted", at: "2019-03-06T09:00:00Z", told: sentinel("undone-told") });
        }
        return path === `${API}${LEARNING_API_PATH}`
          ? json(learningBody({ tier_one: [aTierOne({ undo_offered: !undone, in_effect: !undone })] }))
          : null;
      },
    );
    const posts = () => sent.filter((one) => one.method === "POST").map((one) => [one.path, one.body]);

    fireEvent.click(button(container.querySelector("tbody") as HTMLElement, UNDO_LABEL));
    expect(dialog().textContent).toContain(sentinel("undo-demotes"));
    fireEvent.click(button(dialog(), KEEP_IT));
    expect(posts()).toEqual([]);

    fireEvent.click(button(container.querySelector("tbody") as HTMLElement, UNDO_LABEL));
    fireEvent.click(button(dialog(), UNDO_LABEL));
    await waitFor(() => {
      expect(mainText(container)).toContain(sentinel("undone-told"));
    });
    expect(posts()).toEqual([[`${API}${UNDO_API_PATH}`, { memory_id: "m-one-sentinel" }]]);
    await waitFor(() => {
      expect(container.querySelector("tbody")?.textContent).toContain(UNDONE);
    });
  });

  test("a learning opens in a drawer, and its memory reference is there under Advanced and nowhere on the page", async () => {
    // What breaks if this is deleted: memory ids back in every table, which the owner found cluttered,
    // or a learning with no way to read its reference for a support request.
    const { container } = await consoleAt("/learning", reviewing(learningBody({ tier_one: [aTierOne()] })));
    expect(mainText(container)).not.toContain("m-one-sentinel");
    fireEvent.click(button(container.querySelector("tbody") as HTMLElement, "Preference"));
    const drawer = await waitFor(() => {
      const found = document.body.querySelector<HTMLElement>('[data-slot="drawer"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    expect(drawer.querySelector('[data-slot="advanced"]')?.textContent).toContain("m-one-sentinel");
    expect(drawer.textContent).toContain(sentinel("undo-demotes"));
  });

  test("promote and decide are drawn as not built yet, inert, and sending nothing", async () => {
    // What breaks if this is deleted: a promote or decide button that writes nothing anywhere, or
    // the acts hidden so the page says the product has no such thing.
    const shadow = await consoleAt("/learning/shadow", reviewing(learningBody({ tier_two: [aTierTwo()] })));
    const promote = shadow.container.querySelector(`[${UNAVAILABLE_MARK}]`);
    expect(promote?.textContent).toBe(UNAVAILABLE.promote.label);
    expect(mainText(shadow.container)).toContain(UNAVAILABLE.promote.reason);
    fireEvent.click(promote as HTMLElement);
    expect(shadow.sent.filter((one) => one.method === "POST")).toEqual([]);

    const waiting = await consoleAt("/learning/waiting", reviewing(learningBody({ tier_three: [{ memory_id: "m3", department: "maintenance", back_to: "a1" }] })));
    expect(waiting.container.querySelector(`[${UNAVAILABLE_MARK}]`)?.textContent).toBe(UNAVAILABLE.decide.label);
    expect(mainText(waiting.container)).toContain("maintenance");
  });

  test("the Waiting view raises the queue's alarm in the API's words when it is raised, and says nothing when it is not", async () => {
    // What breaks if this is deleted: an alarm the API raised over the gated changes waiting is
    // dropped on the way to the page, or one it did not raise is drawn from this console's own count.
    const routed = [{ memory_id: "m3", department: "maintenance", back_to: "a1" }];
    const raised = await consoleAt(
      "/learning/waiting",
      reviewing(learningBody({ tier_three: routed, queue_alarm: { raised: true, says: sentinel("queue-alarm") } })),
    );
    expect(raised.container.querySelector('[data-slot="queue-alarm"]')?.textContent).toBe(sentinel("queue-alarm"));
    expect(raised.container.querySelector('[data-slot="queue-alarm"]')?.getAttribute("role")).toBe("alert");

    const quiet = await consoleAt(
      "/learning/waiting",
      reviewing(learningBody({ tier_three: routed, queue_alarm: { raised: false, says: sentinel("quiet") } })),
    );
    expect(quiet.container.querySelector('[data-slot="queue-alarm"]')).toBeNull();
    expect(mainText(quiet.container)).not.toContain(sentinel("quiet"));
  });

  test("tier three withheld is left out of the switch, and its address says why, which an empty tier does not", async () => {
    // What breaks if this is deleted: a reader who may not be told where gated changes went shown an
    // empty Waiting view, which says none went anywhere.
    const withheld = await consoleAt("/learning/waiting", reviewing(learningBody({ tier_three: null })));
    expect(viewLinks(withheld.container)).toEqual(["Applied", "Shadow", "About"]);
    expect(mainText(withheld.container)).toContain(TIER_THREE_WITHHELD);

    const empty = await consoleAt("/learning/waiting", reviewing(learningBody({ tier_three: [] })));
    expect(viewLinks(empty.container)).toContain("Waiting");
    expect(mainText(empty.container)).not.toContain(TIER_THREE_WITHHELD);
  });

  test("About lists the change kinds the API puts at each tier and the bound on the review", async () => {
    // What breaks if this is deleted: the four-tier card drawn from this console's own idea of the
    // tiers rather than `brain.memory.tiers.BLAST_RADIUS` as the API sends it.
    const { container } = await consoleAt("/learning/about", reviewing(learningBody()));
    expect(mainText(container)).toContain("Tier one sentinel");
    expect(mainText(container)).toContain(consideredSentence(500));
  });

  test("About shows how learning is tuned, and a changed figure is checked, confirmed and sent to the Learning screen's own route", async () => {
    // What breaks if this is deleted: the learning figures sent through the Rate limits route,
    // which refuses them, a figure outside the bounds sent anyway, or no control drawn for the
    // administrator the write admits.
    const label = "Days an inferred memory takes to lose half its weight";
    const settings = (value: number, saved: boolean) => ({
      knobs: [
        { name: "inferred_memory_half_life_days", kind: "learning", label, unit: "days", value, default: 30, lowest: 10, highest: 365, saved, bounds_because: sentinel("bounds") },
      ],
      may_change: true,
      in_force: sentinel("lasts"),
    });
    const settingsPath = `${API}${LEARNING_SETTINGS_API_PATH}`;
    const answer: Answer = (path, method, body) => {
      if (path === settingsPath && method === "GET") {
        return json(settings(30, false));
      }
      if (path === `${settingsPath}/inferred_memory_half_life_days` && method === "PUT") {
        return json(settings(10, true));
      }
      return reviewing(learningBody())(path, method, body);
    };
    const { container, sent } = await consoleAt("/learning/about", answer);
    await waitFor(() => {
      if (!mainText(container).includes(sentinel("lasts"))) {
        throw new Error("the settings have not arrived");
      }
    });
    expect(mainText(container)).toContain(LEARNING_SETTINGS.heading);
    expect(mainText(container)).toContain("30 days");

    fireEvent.click(button(container, `Change: ${label}`));
    const form = container.querySelector(`form[aria-label="${label}"]`) as HTMLFormElement;
    const input = form.querySelector("input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "9" } });
    fireEvent.submit(form);
    expect(document.body.querySelector('[data-slot="confirm-dialog"]')).toBeNull();

    fireEvent.change(input, { target: { value: "10" } });
    fireEvent.submit(form);
    await waitFor(() => dialog());
    fireEvent.click(button(dialog(), "Save the new figure"));
    await waitFor(() => {
      if (!mainText(container).includes(`${label} is now 10 days.`)) {
        throw new Error("the change has not been told");
      }
    });
    expect(sent.filter((one) => one.method === "PUT")).toEqual([
      { method: "PUT", path: `${settingsPath}/inferred_memory_half_life_days`, body: { value: 10 } },
    ]);
  });

  test("an act listed as not built yet has no route in the API document, and each pattern matches its path", () => {
    // What breaks if this is deleted: a page that goes on saying "coming soon" about a route that
    // has landed, so a person is told they cannot do what they can.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    expect(UNAVAILABLE.promote.retiredBy.test("/api/v1/govern/learning/promote")).toBe(true);
    expect(UNAVAILABLE.decide.retiredBy.test("/api/v1/govern/learning/decisions")).toBe(true);
  });

  test("recent means the seven days before the API's own instant, over tiers one and two", () => {
    // What breaks if this is deleted: the window read off this browser's clock, so the same review
    // counts differently on two machines, or a learning from last month counted as this week's.
    const page = readLearningPage(
      learningBody({
        tier_one: [aTierOne({ memory_id: "a", learned_at: "2019-03-05T09:00:00Z" }), aTierOne({ memory_id: "b", learned_at: "2019-02-20T09:00:00Z" })],
      }),
    );
    expect(learnedRecently(page)).toBe(1);
  });
});

// --- Memory --------------------------------------------------------------------------------------

function remembering(body: Record<string, unknown>): Answer {
  return (path) => {
    if (path === `${API}${MEMORY_API_PATH}`) {
      return json(body);
    }
    return path === `${API}/govern/directory/u_subject` ? json(THE_PERSON) : null;
  };
}

describe("the Memory page", () => {
  test("every field the API sends about a person's memory is read", () => {
    // What breaks if this is deleted: a field added to the view arrives and is dropped.
    const read = ["subject_id", "curated", "extracted", "history", "considered_per_kind", "staleness", "edit_is_not_writable"];
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

  test("with nobody named it asks the API nothing and offers a person by name", async () => {
    // What breaks if this is deleted: the bare page asking for everybody's memory, which is the
    // directory of people the decision behind this page refuses to be.
    const { container, sent } = await consoleAt("/memory", remembering(memoryBody()));
    expect(mainText(container)).toContain(CHOOSE_HEADING);
    expect(sent.some((one) => one.path.includes(MEMORY_API_PATH))).toBe(false);
    expect(container.querySelector('[data-slot="person-picker"]')).not.toBeNull();
  });

  test("a reference that fails the check is explained and never sent", async () => {
    // What breaks if this is deleted: a 422 naming a parameter in place of a sentence a person can
    // act on, for an address somebody pasted with a space in it.
    const { container, sent } = await consoleAt("/memory/u%20one", remembering(memoryBody()));
    expect(mainText(container)).toContain(referenceProblem("u one") ?? "");
    expect(sent.some((one) => one.path.includes(MEMORY_API_PATH))).toBe(false);
  });

  test("a person's memory is named, both kinds are one table in their own words, and no memory id is on the page", async () => {
    // What breaks if this is deleted: a person shown as a reference, one kind of memory dropped, or
    // memory ids back in every row.
    const { container } = await consoleAt("/memory/u_subject", remembering(memoryBody()));
    expect(container.querySelector("main h1")?.textContent).toBe("Priya Raman");
    const table = container.querySelector("tbody")?.textContent ?? "";
    expect(table).toContain(sentinel("stated"));
    expect(table).toContain(sentinel("inferred"));
    expect(table).toContain("Stated by a person");
    expect(table).toContain("Extracted from conversations");
    const outsideAdvanced = [...(container.querySelector("main")?.children ?? [])].map((one) => one.textContent ?? "").join(" ");
    expect(outsideAdvanced.replace(container.querySelector('[data-slot="advanced"]')?.textContent ?? "", "")).not.toContain("m_stated");
  });

  test("the history draws each diff line a revision carries, newest first", async () => {
    // What breaks if this is deleted: a replaced memory with its change dropped, or the newest change
    // at the bottom of a long history.
    const { container } = await consoleAt(
      "/memory/u_subject/history",
      remembering(
        memoryBody({
          history: [
            { memory_id: "m_old", replaced_id: null, at: "2019-03-01T09:00:00Z", diff: [], trigger: null, correction: null },
            { memory_id: "m_new", replaced_id: "m_old", at: "2019-03-05T09:00:00Z", diff: ["-said before", "+says now"], trigger: "explicit_correction", correction: "superseded" },
          ],
        }),
      ),
    );
    const rows = [...container.querySelectorAll("tbody tr")].map((one) => one.textContent ?? "");
    expect(rows[0]).toContain("Replaced an earlier memory");
    expect(rows[0]).toContain("-said before");
    expect(rows[0]).toContain("+says now");
    expect(rows[0]).toContain("Explicit correction");
    expect(rows[1]).toContain("Formed");
  });

  test("a person with nothing readable is one sentence, whatever the reason", async () => {
    // What breaks if this is deleted: an empty table for a person whose memories this reader may not
    // recall, which reads differently from a person with none.
    const { container } = await consoleAt("/memory/u_subject", remembering(memoryBody({ curated: [], extracted: [], history: [] })));
    expect(mainText(container)).toContain(NOTHING_TO_READ_DESCRIPTION);
    expect(container.querySelector("tbody")).toBeNull();
  });

  test("addresses and requests keep a typed reference inside the console and inside its parameter", () => {
    // What breaks if this is deleted: an open redirect through a backslash reaching `useNavigate`,
    // GHSA-wrjc-x8rr-h8h6, or a reference with an ampersand turning into a second parameter.
    expect(memoryAddress("\\evil.example")).toBe("/memory/%5Cevil.example");
    expect(memoryApiPath("a&b=c")).toBe(`${MEMORY_API_PATH}?${SUBJECT_PARAMETER}=a%26b%3Dc`);
  });

  test("the sizes are the bytes of the statements shown", () => {
    // What breaks if this is deleted: a size computed in characters rather than bytes, which is
    // wrong for every statement written in a script that is not Latin.
    const page = readMemoryPage(memoryBody(), "u_subject");
    const oneKilobyte = [{ memory_id: "m", statement: "é".repeat(512), confidence: 1, formed_at: "" }];
    expect(kilobytes(oneKilobyte)).toBe("1.0");
    expect(page.consideredPerKind).toBe(200);
  });
});
