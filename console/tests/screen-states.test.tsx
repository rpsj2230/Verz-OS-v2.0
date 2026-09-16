/**
 * Every page the console registers says loading, empty, unreachable and failed in four different
 * sentences, and none of the four is a blank panel.
 *
 * `docs/admin-console.md` asks for this in one line: loading, empty and failure states are
 * written, and an empty list and an unreachable source are different sentences. Every page test
 * in this directory holds some of that for its own page, and none of them could say whether the
 * next page would, so on 2026-09-17 the rule was measured over the whole route table. Thirty-two of
 * its sixty-two addresses drew the same heading for a laptop that had lost its network and for an
 * API that answered with a fault, seven drew nothing at all for an empty answer, and Staff sources
 * said there were no sources while it was still loading and again when its request had failed.
 *
 * **How a state is produced.** `support/screenStates.tsx` answers every request a page makes by
 * holding it open for ever (loading), refusing to be reached (unreachable), answering 500 with a
 * sentence of its own (failed), or answering with the page's usual body from `support/pageCases.ts`
 * with every list in it emptied (empty). The same body unemptied is the page with rows, which is the
 * fifth reading and the one an empty sentence has to be different from.
 *
 * **What counts as a different sentence.** A sentence here is the whole text of an element that
 * holds text of its own. The API's own message and the transport's are removed first, along with
 * the reference, because they are the words a page was handed rather than the words it wrote: a
 * page drawing `That did not work` over both failures would otherwise pass on the strength of two
 * messages it did not choose. Each state must then draw at least one sentence that no other
 * reading of the same page draws. For the empty state that sentence must be at least three words,
 * because an emptied page drawing a `0` where it drew a `7` has changed and has not said anything.
 *
 * **Where the rest of it is.** The rule itself and the pages excused from part of it, each with its
 * reason, are in `support/screenStateRules.tsx`, and the pages are dealt into this file,
 * `screen-states-second.test.tsx` and `screen-states-third.test.tsx`, because five mounts of sixty
 * pages in one file took a minute.
 *
 * **What this does not decide.** Which words a page uses, whether a 404 is worded as the API
 * worded it, and whether the failure headings are the same across pages: those are
 * `api/errors.A_404_IS_NOT_AN_EXPLANATION` and the page tests. Only that the four are told apart.
 *
 * Task ids: M27.8.3
 */

import { beforeAll, describe, expect, test } from "vitest";
import { loadConsole } from "./support/auth";
import { PAGES } from "./support/pageCases";
import {
  ACTS,
  ASKING,
  ASKS_NOTHING_ON_ARRIVAL,
  NO_EMPTY_SENTENCE,
  emptyAnswers,
  holdsFourSentences,
  shard,
} from "./support/screenStateRules";
import { mountIn, patternsOf } from "./support/screenStates";

/** Every split page is transformed once, before anything is timed. */
beforeAll(async () => {
  await import("../src/pages/Records");
  await import("../src/pages/Matrix");
  await import("../src/pages/Classification");
  await import("../src/pages/Agent");
  await import("../src/pages/Approvals");
  await import("../src/pages/People");
}, 120_000);

describe("loading, empty, unreachable and failed on every registered page", () => {
  test("every route the console registers is a case, and every page excused for asking nothing is named with a reason", async () => {
    // What breaks if this is deleted: a page added to `App.tsx` that nobody held to the four
    // sentences, because the tests below loop over the page cases rather than over the route
    // table. And a reason that has gone stale: an excused page that has started asking would sit
    // on the list for ever with its states unread.
    await loadConsole();
    const { routes } = await import("../src/App");
    expect(patternsOf(routes).sort()).toEqual(Object.keys(PAGES).sort());
    for (const [pattern, reason] of Object.entries(ASKS_NOTHING_ON_ARRIVAL)) {
      expect(PAGES[pattern], pattern).toBeDefined();
      expect(reason.split(" ").length, `${pattern} is excused without a reason`).toBeGreaterThan(5);
    }
    for (const pattern of Object.keys(ACTS)) {
      expect(ASKING, pattern).toContain(pattern);
    }
    for (const [pattern, reason] of Object.entries(NO_EMPTY_SENTENCE)) {
      expect(emptyAnswers(pattern), `${pattern} has no list, so there is nothing to excuse`).not.toBeNull();
      expect(reason.split(" ").length, `${pattern} is excused without a reason`).toBeGreaterThan(5);
    }
  }, 30_000);

  test.each(Object.keys(ASKS_NOTHING_ON_ARRIVAL))("%s sends no request when it is opened", async (pattern) => {
    // What breaks if this is deleted: the excuse list becomes a way to leave a page out. Every
    // page on it is opened against an API that fails everything, and it must not have asked.
    const page = PAGES[pattern];
    if (page === undefined) {
      throw new Error(`${pattern} has no page case.`);
    }
    const mounted = await mountIn(pattern, page.address, { kind: "failed" });
    expect(mounted.sent).toEqual([]);
  }, 30_000);

  test.each(shard(0, 3))("%s says loading, empty, unreachable and failed in four different sentences", async (pattern) => {
    // What breaks if this is deleted: a page that draws "That did not work" when the laptop has
    // lost its network, which sends a person to ask an administrator about a fault that is theirs;
    // a page whose empty list is a blank panel that reads as still loading; or a page whose
    // loading sentence is the same as its empty one, so a slow answer reads as nothing there.
    await holdsFourSentences(pattern);
  }, 60_000);
});
