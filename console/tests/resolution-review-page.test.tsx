/**
 * Possible duplicates: each pair drawn by name with where it came from, why it is here and what
 * matches; a decision confirmed with a reason and posted, then the queue read again; a blank reason
 * said beside the box and never sent; somebody else's decision said in the API's sentence; an empty
 * queue said in a sentence; and nothing on the page counting what the reader was not shown.
 *
 * Under the queue, how pairs are weighed: the weights in use said in words, a waiting fit drawn as
 * its moves with the ones that change what reviewers are told apart, its promote confirmed and
 * posted with the version shown, a fit that moved said in the API's sentence, and no figure.
 *
 * Mounted on its own at its address. The shapes and vocabularies are read from
 * `brain.resolution_routes`, `brain.tables.resolution_review` and `brain.resolution.guardrails`, so
 * a renamed field, a new origin or a new evidence band fails here rather than on an install.
 *
 * Task ids: M14.6.4, M14.8.5, M14.4.4, M14.8.3
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ALREADY_ONE,
  BANDS,
  CALIBRATED_IN_FORCE,
  CROSSINGS_LABEL,
  DECLARED_IN_FORCE,
  driftSentence,
  KEEP_CURRENT_WEIGHTS,
  NEW_WEIGHTS_IN_FORCE,
  NEW_WEIGHTS_WAITING,
  NO_CROSSINGS,
  NOTHING_NEW,
  OTHER_CHANGES_LABEL,
  otherChanges,
  PROMOTE_WEIGHTS_API_PATH,
  readWeights,
  USE_NEW_WEIGHTS,
  WEIGHTS_API_PATH,
  WEIGHTS_UNREADABLE,
  type WeightsBody,
  decisionApiPath,
  decidedSentence,
  DIFFERENT,
  DUPLICATES_PATH,
  JOINED,
  KEEP_WAITING,
  KEPT_APART,
  LONGEST_REASON,
  NOTHING_WAITING,
  readDecided,
  readQueue,
  REASON_LABEL,
  REASON_MISSING,
  REASON_TOO_LONG,
  reasonProblem,
  REVIEW_API_PATH,
  SAME,
  sentence,
  strengthSummary,
  UNMEASURED,
  UNREADABLE_ANSWER,
  waitingSentence,
  whereFrom,
  WHY_BY_ORIGIN,
  whyWords,
  type ReviewCard,
} from "../src/pages/resolutionReviewQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendEnumMembers, backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { readRepoFile } from "./support/repo";

beforeAll(() => {
  installRadixStubs();
});

const ROUTES = "src/brain/resolution_routes.py";
const ITEM = "rev_aaaabbbbccccddddeeeeffff00001111";
const QUEUE = `GET /api/v1${REVIEW_API_PATH}`;
const DECIDE = `POST /api/v1${decisionApiPath(ITEM)}`;
const WEIGHTS = `GET /api/v1${WEIGHTS_API_PATH}`;
const PROMOTE = `POST /api/v1${PROMOTE_WEIGHTS_API_PATH}`;
/** A fit's version, with figures in it, so a version drawn outside Advanced is a digit on the card. */
const FIT = "fit_20190304t120000";
const CROSSING = "uen moved from weak to decisive";
const SECOND_CROSSING = "name_exact moved from supporting to strong";
const STAYED = "email stayed weak";

function weights(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    in_force: "declared",
    calibrated: false,
    candidate: FIT,
    lines: [STAYED, SECOND_CROSSING, CROSSING],
    crossings: [CROSSING, SECOND_CROSSING],
    ...overrides,
  };
}

/** Nothing waiting, which is what every test about the queue alone is answered with. */
const NOTHING_WAITING_FIT = weights({ candidate: null, lines: [], crossings: [] });

function record(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { source: "hubspot", entity: "hubspot_company", label: "Acme Pte Ltd", ...overrides };
}

function card(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    item_id: ITEM,
    left: record(),
    right: record({ source: "xero", entity: "contact", label: "ACME PTE. LTD." }),
    lines: ["registration number agreed, and on its own is very nearly conclusive"],
    why: "MATCHER-REASON-SENTINEL",
    origin: "held",
    state: "open",
    raised_at: "2019-03-04T09:00:00Z",
    weight_version: "WEIGHTS-SENTINEL",
    calibrated: false,
    ...overrides,
  };
}

function queue(cards: Record<string, unknown>[] = [card()], counts: Record<string, number> = {}): Record<string, unknown> {
  return {
    cards,
    by_strongest: { decisive: cards.length, strong: 0, supporting: 0, weak: 0, against: 0, ...counts },
  };
}

async function duplicatesPage(answers: Record<string, Answer>) {
  return mountPage(
    DUPLICATES_PATH,
    async () => {
      const { ResolutionReview } = await import("../src/pages/ResolutionReview");
      return <ResolutionReview />;
    },
    { [WEIGHTS]: () => json(NOTHING_WAITING_FIT), ...answers },
  );
}

/** The weights section, which is what the tests below read. */
function weightsSection(container: HTMLElement): HTMLElement {
  const found = container.querySelector<HTMLElement>('[data-slot="weights-section"]');
  if (found === null) {
    throw new Error("no weights section on the page");
  }
  return found;
}

/** The section's text as a person reads it: Advanced and any drawn date taken out. */
function readableSection(container: HTMLElement): string {
  const copy = weightsSection(container).cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"], time').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

async function useNewWeights(container: HTMLElement): Promise<HTMLElement> {
  fireEvent.click(button(weightsSection(container), USE_NEW_WEIGHTS));
  const dialog = await screen.findByRole("alertdialog");
  await act(async () => {
    fireEvent.click(within(dialog).getByRole("button", { name: USE_NEW_WEIGHTS }));
  });
  return dialog;
}

/** The page's text with the Advanced section taken out, which is what a person reads. */
function readable(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

async function openAndConfirm(container: HTMLElement, label: string, reason: string): Promise<HTMLElement> {
  fireEvent.click(button(container, label));
  const dialog = await screen.findByRole("alertdialog");
  fireEvent.change(within(dialog).getByLabelText(REASON_LABEL), { target: { value: reason } });
  await act(async () => {
    fireEvent.click(within(dialog).getByRole("button", { name: label }));
  });
  return dialog;
}

describe("what the Possible duplicates screen draws", () => {
  test("a pair by its two names and where each came from, why it is here in words, and its evidence", async () => {
    // What breaks if this is deleted: a pair drawn without the two records' names or systems, which
    // asks somebody to decide whether two things are one without saying which two.
    const { container } = await duplicatesPage({ [QUEUE]: () => json(queue()) });

    const text = readable(container);
    expect(text).toContain("Acme Pte Ltd");
    expect(text).toContain("ACME PTE. LTD.");
    expect(text).toContain("a company in Hubspot");
    expect(text).toContain("a contact in Xero");
    expect(text).toContain(WHY_BY_ORIGIN["held"]);
    expect(text).toContain("Registration number agreed, and on its own is very nearly conclusive.");
    expect(text).toContain(UNMEASURED);
    expect(text).toContain(waitingSentence(1));
    // The matcher's own reason, the identifier and the weight table are for a support request.
    expect(text).not.toContain("MATCHER-REASON-SENTINEL");
    expect(text).not.toContain(ITEM);
    expect(text).not.toContain("WEIGHTS-SENTINEL");
    const advanced = container.querySelector('[data-slot="advanced"]')?.textContent ?? "";
    expect(advanced).toContain("MATCHER-REASON-SENTINEL");
    expect(advanced).toContain(ITEM);
  });

  test("an empty queue is a sentence, a refusal is the API's, and an unreadable answer says so", async () => {
    // What breaks if this is deleted: an empty queue drawn as a blank page, which reads as a screen
    // that failed; or a refused reader shown an empty queue, which reads as nothing to do.
    const empty = await duplicatesPage({ [QUEUE]: () => json(queue([])) });
    expect(empty.container.textContent).toContain(NOTHING_WAITING);

    const refused = await duplicatesPage({
      [QUEUE]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    });
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.container.textContent).toContain("TRACE-SENTINEL");
    expect(refused.container.textContent).not.toContain(NOTHING_WAITING);

    const unreadable = await duplicatesPage({ [QUEUE]: () => json({ cards: "no" }) });
    expect(unreadable.container.textContent).toContain(UNREADABLE_ANSWER);
  });

  test("the only figures drawn are counts of the pairs on the page", async () => {
    // What breaks if this is deleted: a figure that counts more than the reader was shown, which
    // tells them how many pairs exist whose records they may not see.
    const two = [card(), card({ item_id: "rev_second", left: record({ label: "Beta" }), right: record({ label: "Gamma" }) })];
    const { container } = await duplicatesPage({ [QUEUE]: () => json(queue(two, { decisive: 1, strong: 1 })) });

    const summary = container.querySelector('[data-slot="pairs-summary"]')?.textContent ?? "";
    expect(summary).toBe(`${waitingSentence(2)} ${strengthSummary({ decisive: 1, strong: 1 }) ?? ""}`);
    // Take out the counts above and the day each pair has waited since: nothing else is a figure.
    const copy = container.cloneNode(true) as HTMLElement;
    copy.querySelectorAll('[data-slot="advanced"], [data-slot="pairs-summary"], [data-slot="pair-waiting"]').forEach((one) => {
      one.remove();
    });
    expect(copy.textContent ?? "").not.toMatch(/\d/);
  });
});

describe("deciding a pair", () => {
  test("is confirmed with a reason in a sentence, posted with it, and the queue is read again", async () => {
    // What breaks if this is deleted: a merge sent without its reason, sent as the wrong decision,
    // or a page that goes on drawing a pair the database has closed.
    let open = true;
    const { container, sent } = await duplicatesPage({
      [QUEUE]: () => json(queue(open ? [card()] : [])),
      [DECIDE]: () => {
        open = false;
        return json({ item_id: ITEM, state: "merged", merged: true });
      },
    });

    fireEvent.click(button(container, SAME));
    const first = await screen.findByRole("alertdialog");
    await act(async () => {
      fireEvent.click(within(first).getByRole("button", { name: KEEP_WAITING }));
    });
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);

    await openAndConfirm(container, SAME, "  Same registration number and the same office address.  ");

    await waitFor(() => {
      expect(container.textContent).toContain(JOINED);
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST")).toEqual([
      {
        method: "POST",
        path: `/api/v1${decisionApiPath(ITEM)}`,
        body: { decision: "merge", reason: "Same registration number and the same office address." },
      },
    ]);
    expect(sent.filter((one) => one.method === "GET").length).toBeGreaterThanOrEqual(2);
    expect(container.textContent).toContain(NOTHING_WAITING);
  });

  test("a rejection posts reject, and a blank reason is said beside the box and never sent", async () => {
    // What breaks if this is deleted: a decision sent with no reason, which the API refuses after
    // the person agreed to it; or "These are different" sent as a merge.
    const { container, sent } = await duplicatesPage({
      [QUEUE]: () => json(queue()),
      [DECIDE]: () => json({ item_id: ITEM, state: "rejected", merged: false }),
    });

    const dialog = await openAndConfirm(container, DIFFERENT, "   ");
    expect(dialog.textContent).toContain(REASON_MISSING);
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);

    fireEvent.change(within(dialog).getByLabelText(REASON_LABEL), { target: { value: "Two different clients with one name." } });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: DIFFERENT }));
    });
    await waitFor(() => {
      expect(container.textContent).toContain(KEPT_APART);
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { decision: "reject", reason: "Two different clients with one name." },
    ]);
  });

  test("a pair somebody else decided first is said in the API's sentence and the queue is read again", async () => {
    // What breaks if this is deleted: a 409 drawn as the generic "more than one match" fallback, or
    // the decided pair left on the page with its buttons, inviting a second decision.
    let decided = false;
    const { container, sent } = await duplicatesPage({
      [QUEUE]: () => json(queue(decided ? [] : [card()])),
      [DECIDE]: () => {
        decided = true;
        return json({ outcome: "decided", sentence: "SOMEBODY-DECIDED-SENTINEL" }, 409);
      },
    });

    await openAndConfirm(container, SAME, "Same registration number.");
    await waitFor(() => {
      expect(container.textContent).toContain("SOMEBODY-DECIDED-SENTINEL");
    });
    await settled(container);
    expect(container.textContent).not.toContain(JOINED);
    expect(container.textContent).toContain(NOTHING_WAITING);
    expect(sent.filter((one) => one.method === "GET").length).toBeGreaterThanOrEqual(2);
  });

  test("any other refusal stays in the confirmation with the API's sentence", async () => {
    // What breaks if this is deleted: a refused decision that closes the dialog and says nothing,
    // which reads as a decision recorded.
    const { container } = await duplicatesPage({
      [QUEUE]: () => json(queue()),
      [DECIDE]: () => json({ message: "I could not find that.", trace_id: "REFUSED-SENTINEL" }, 404),
    });

    const dialog = await openAndConfirm(container, SAME, "Same registration number.");
    await waitFor(() => {
      expect(dialog.textContent).toContain("REFUSED-SENTINEL");
    });
    expect(container.textContent).not.toContain(JOINED);
  });
});

describe("how pairs are weighed", () => {
  test("a waiting fit is drawn as its moves in words, the ones that change what reviewers are told apart", async () => {
    // What breaks if this is deleted: a waiting fit drawn without the moves a reviewer is approving,
    // or with a band crossing mixed into the rest, which is the line the approval is for.
    const { container } = await duplicatesPage({ [WEIGHTS]: () => json(weights()) });

    const text = readableSection(container);
    expect(text).toContain(DECLARED_IN_FORCE);
    expect(text).toContain(NEW_WEIGHTS_WAITING);
    const crossings = weightsSection(container).querySelector('[data-slot="weights-crossings"]');
    expect(crossings?.textContent ?? "").toContain(CROSSINGS_LABEL);
    expect([...(crossings?.querySelectorAll("li") ?? [])].map((one) => one.textContent)).toEqual([
      "Uen moved from weak to decisive.",
      "Name exact moved from supporting to strong.",
    ]);
    const others = weightsSection(container).querySelector('[data-slot="weights-other-lines"]');
    expect(text).toContain(OTHER_CHANGES_LABEL);
    expect([...(others?.querySelectorAll("li") ?? [])].map((one) => one.textContent)).toEqual(["Email stayed weak."]);
    expect(button(weightsSection(container), USE_NEW_WEIGHTS)).toBeDefined();
    // The versions are for a support request, and nowhere else.
    expect(text).not.toContain(FIT);
    const advanced = weightsSection(container).querySelector('[data-slot="advanced"]')?.textContent ?? "";
    expect(advanced).toContain(FIT);
    expect(advanced).toContain("declared");
  });

  test("a fit with no crossing says so, nothing waiting is a sentence with no action, and approved weights say whose", async () => {
    // What breaks if this is deleted: an empty section when the weekly check found nothing, which
    // reads as a screen that failed, or approved weights described as the product's own.
    const quiet = await duplicatesPage({ [WEIGHTS]: () => json(weights({ crossings: [], lines: [STAYED] })) });
    expect(readableSection(quiet.container)).toContain(NO_CROSSINGS);
    expect(readableSection(quiet.container)).not.toContain(CROSSINGS_LABEL);

    const idle = await duplicatesPage({
      [WEIGHTS]: () => json(weights({ in_force: FIT, calibrated: true, candidate: null, lines: [], crossings: [] })),
    });
    const text = readableSection(idle.container);
    expect(text).toContain(CALIBRATED_IN_FORCE);
    expect(text).toContain(NOTHING_NEW);
    expect(text).not.toContain(DECLARED_IN_FORCE);
    expect(text).not.toContain(NEW_WEIGHTS_WAITING);
    expect(() => button(weightsSection(idle.container), USE_NEW_WEIGHTS)).toThrow();

    const unreadable = await duplicatesPage({ [WEIGHTS]: () => json({ in_force: "declared" }) });
    expect(readableSection(unreadable.container)).toContain(WEIGHTS_UNREADABLE);
  });

  test("using the new weights is confirmed, posts the version shown, and the section is read again", async () => {
    // What breaks if this is deleted: weights put in use without a confirmation, a promote posting
    // a version other than the one the reviewer read, or a card still offering a fit now in use.
    let promoted = false;
    const { container, sent } = await duplicatesPage({
      [WEIGHTS]: () =>
        json(promoted ? weights({ in_force: FIT, calibrated: true, candidate: null, lines: [], crossings: [] }) : weights()),
      [PROMOTE]: () => {
        promoted = true;
        return json(weights({ in_force: FIT, calibrated: true, candidate: null, lines: [], crossings: [] }));
      },
    });

    fireEvent.click(button(weightsSection(container), USE_NEW_WEIGHTS));
    const first = await screen.findByRole("alertdialog");
    await act(async () => {
      fireEvent.click(within(first).getByRole("button", { name: KEEP_CURRENT_WEIGHTS }));
    });
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);

    await useNewWeights(container);
    await waitFor(() => {
      expect(readableSection(container)).toContain(NEW_WEIGHTS_IN_FORCE);
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST")).toEqual([
      { method: "POST", path: `/api/v1${PROMOTE_WEIGHTS_API_PATH}`, body: { version: FIT } },
    ]);
    expect(sent.filter((one) => one.method === "GET" && one.path === `/api/v1${WEIGHTS_API_PATH}`)).toHaveLength(2);
    expect(readableSection(container)).toContain(CALIBRATED_IN_FORCE);
    expect(readableSection(container)).toContain(NOTHING_NEW);
  });

  test("a fit that is no longer waiting is said in the API's sentence and the section is read again", async () => {
    // What breaks if this is deleted: a 409 drawn as a generic failure, or the card left offering
    // a fit that a newer one or somebody else's approval has replaced.
    let moved = false;
    const { container, sent } = await duplicatesPage({
      [WEIGHTS]: () => json(moved ? weights({ candidate: "fit_newer" }) : weights()),
      [PROMOTE]: () => {
        moved = true;
        return json({ outcome: "moved", sentence: "FIT-MOVED-SENTINEL" }, 409);
      },
    });

    await useNewWeights(container);
    await waitFor(() => {
      expect(readableSection(container)).toContain("FIT-MOVED-SENTINEL");
    });
    await settled(container);
    expect(readableSection(container)).not.toContain(NEW_WEIGHTS_IN_FORCE);
    expect(sent.filter((one) => one.method === "GET" && one.path === `/api/v1${WEIGHTS_API_PATH}`)).toHaveLength(2);
    expect(weightsSection(container).querySelector('[data-slot="advanced"]')?.textContent ?? "").toContain("fit_newer");
  });

  test("any other refusal of the promote stays in the confirmation with the API's sentence", async () => {
    // What breaks if this is deleted: a refused promote that closes the dialog and says nothing,
    // which reads as the new weights put in use.
    const { container } = await duplicatesPage({
      [WEIGHTS]: () => json(weights()),
      [PROMOTE]: () => json({ message: "I could not find that.", trace_id: "PROMOTE-REFUSED-SENTINEL" }, 404),
    });

    const dialog = await useNewWeights(container);
    await waitFor(() => {
      expect(dialog.textContent).toContain("PROMOTE-REFUSED-SENTINEL");
    });
    expect(container.textContent).not.toContain(NEW_WEIGHTS_IN_FORCE);
  });

  test("nothing in the section is a figure, whether a fit is waiting or not", async () => {
    // What breaks if this is deleted: a count of the pairs a fit was measured on, a weight, or a
    // version string drawn on the card, each a figure about records the reader may not see.
    for (const answer of [weights(), weights({ in_force: FIT, calibrated: true, candidate: null, lines: [], crossings: [] })]) {
      const { container } = await duplicatesPage({ [WEIGHTS]: () => json(answer) });
      const text = readableSection(container);
      expect(text.length).toBeGreaterThan(0);
      expect(text).not.toMatch(/\d/);
    }
  });
});

describe("the query module's readers and words", () => {
  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.resolution_routes` that the page
    // goes on reading, which renders as an empty name or an empty sentence on an install.
    expect(Object.keys(queue()).sort()).toEqual(backendModelFields(ROUTES, "ReviewQueueView").sort());
    expect(Object.keys(card()).sort()).toEqual(backendModelFields(ROUTES, "ReviewCardView").sort());
    expect(Object.keys(record()).sort()).toEqual(backendModelFields(ROUTES, "RecordView").sort());
    expect(backendModelFields(ROUTES, "ReviewDecisionAsked").sort()).toEqual(["decision", "reason"]);
    expect(backendModelFields(ROUTES, "ReviewDecidedView").sort()).toEqual(["item_id", "merged", "state"]);
    expect(Object.keys(weights()).sort()).toEqual(backendModelFields(ROUTES, "WeightsView").sort());
    expect(backendModelFields(ROUTES, "PromoteAsked")).toEqual(["version"]);
  });

  test("the weights' addresses are the route's own", () => {
    // What breaks if this is deleted: a renamed route the section goes on asking, which draws a
    // failure under every queue, or a promote posted to an address that no longer puts anything in use.
    const routes = readRepoFile(ROUTES);
    expect(routes).toContain(`WEIGHTS_PATH: Final = "${WEIGHTS_API_PATH}"`);
    expect(routes).toContain(`PROMOTE_PATH: Final = "${PROMOTE_WEIGHTS_API_PATH}"`);
  });

  test("the reason limit, the decisions, the origins and the bands are the API's own", () => {
    // What breaks if this is deleted: a new origin drawn with the matcher's raw sentence, a new
    // evidence band left out of the summary, or a reason the page accepts and the route refuses.
    const routes = readRepoFile(ROUTES);
    expect(routes).toContain(`reason: str = Field(min_length=1, max_length=${String(LONGEST_REASON)})`);
    expect(routes).toContain('decision: Literal["merge", "reject"]');

    const origins = Object.values(backendEnumMembers("src/brain/tables/resolution_review.py", "ReviewOrigin")).sort();
    expect(Object.keys(WHY_BY_ORIGIN).sort()).toEqual(origins);

    const guardrails = readRepoFile("src/brain/resolution/guardrails.py");
    const opened = guardrails.indexOf("class Strength(enum.IntEnum):");
    const body = guardrails.slice(opened, guardrails.indexOf("\nclass ", opened + 1));
    const bands = [...body.matchAll(/^ {4}([A-Z]+) = (\d+)$/gm)]
      .sort((a, b) => Number(b[2]) - Number(a[2]))
      .map((one) => (one[1] ?? "").toLowerCase());
    expect(bands.length).toBeGreaterThan(0);
    expect(BANDS.map(([band]) => band)).toEqual(bands);
  });

  test("the readers refuse a shape the console does not read and accept the one it does", () => {
    // What breaks if this is deleted: a malformed answer drawn as cards with empty names, or a
    // decision's answer for another pair taken as this one's.
    expect(readQueue(queue())).not.toBeNull();
    expect(readQueue({ cards: [card({ left: "no" })], by_strongest: {} })).toBeNull();
    expect(readQueue({ cards: [card()] })).toBeNull();
    expect(readQueue(null)).toBeNull();
    expect(readDecided({ item_id: ITEM, state: "merged", merged: true }, ITEM)).toEqual({ state: "merged", merged: true });
    expect(readDecided({ item_id: "rev_other", state: "merged", merged: true }, ITEM)).toBeNull();
    expect(readDecided({ item_id: ITEM, state: "merged" }, ITEM)).toBeNull();
    expect(readWeights(weights())).not.toBeNull();
    expect(readWeights(NOTHING_WAITING_FIT)).not.toBeNull();
    expect(readWeights(weights({ candidate: 3 }))).toBeNull();
    expect(readWeights(weights({ lines: [1] }))).toBeNull();
    expect(readWeights(weights({ crossings: "no" }))).toBeNull();
    expect(readWeights(weights({ calibrated: "yes" }))).toBeNull();
    expect(readWeights(null)).toBeNull();
  });

  test("the words a person reads are chosen as the page says", () => {
    // What breaks if this is deleted: a merge that changed nothing said as a join, a blank or
    // overlong reason allowed through, or a record's system named in the system's own spelling.
    expect(decidedSentence("merge", true)).toBe(JOINED);
    expect(decidedSentence("merge", false)).toBe(ALREADY_ONE);
    expect(decidedSentence("reject", false)).toBe(KEPT_APART);
    expect(reasonProblem("  ")).toBe(REASON_MISSING);
    expect(reasonProblem("x".repeat(LONGEST_REASON + 1))).toBe(REASON_TOO_LONG);
    expect(reasonProblem(` ${"x".repeat(LONGEST_REASON)} `)).toBeNull();
    expect(whereFrom({ source: "hubspot", entity: "hubspot_company", label: "" })).toBe("a company in Hubspot");
    expect(whereFrom({ source: "lark_base", entity: "invoice", label: "" })).toBe("an invoice in Lark base");
    expect(sentence("the cascade matched these two")).toBe("The cascade matched these two.");
    expect(whyWords(card({ origin: "unknown-origin", why: "the matcher's words" }) as unknown as ReviewCard)).toBe(
      "The matcher's words.",
    );
    expect(strengthSummary({ decisive: 0, strong: 0, supporting: 0, weak: 0, against: 0 })).toBeNull();
    expect(strengthSummary({ weak: 2, decisive: 1 })).toBe("Best evidence on the pairs below: very nearly certain for 1, weak for 2.");
    expect(driftSentence("name_exact moved from supporting to strong")).toBe("Name exact moved from supporting to strong.");
    expect(otherChanges(weights() as unknown as WeightsBody)).toEqual([STAYED]);
    expect(otherChanges(weights({ crossings: [] }) as unknown as WeightsBody)).toEqual([STAYED, SECOND_CROSSING, CROSSING]);
  });
});
