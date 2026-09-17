/**
 * The second third of `tests/screen-states.test.tsx`: every page that asks on arrival, dealt into three
 * files so the three hundred mounts run side by side. The rule, the allowlists and the reasons are in
 * `support/screenStateRules.tsx` and the argument for them is in the first file's docstring.
 *
 * Task ids: M27.8.3, M27.8.5
 */

import { beforeAll, describe, test } from "vitest";
import {
  asksForASecondFactor,
  holdsFourSentences,
  saysNoReferenceCameBack,
  shard,
} from "./support/screenStateRules";

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
  test.each(shard(1, 3))("%s says loading, empty, unreachable and failed in four different sentences", async (pattern) => {
    // What breaks if this is deleted: a page that draws "That did not work" when the laptop has
    // lost its network, which sends a person to ask an administrator about a fault that is theirs;
    // a page whose empty list is a blank panel that reads as still loading; or a page whose
    // loading sentence is the same as its empty one, so a slow answer reads as nothing there.
    await holdsFourSentences(pattern);
  }, 60_000);
});

describe("what a failure says about itself on every registered page", () => {
  test.each(shard(1, 3))("%s says no reference came back when a proxy answered without one", async (pattern) => {
    // What breaks if this is deleted: the screen the staging install showed on 2026-09-17, a
    // heading over "Something went wrong." and nothing a person could quote, on any page that draws
    // a failure through a notice of its own rather than through `ui/FailureNotice.tsx`.
    await saysNoReferenceCameBack(pattern);
  }, 60_000);

  test.each(shard(1, 3))("%s shows the API's sentence and a way to sign in again when a second factor is needed", async (pattern) => {
    // What breaks if this is deleted: a person signed in without their second factor told "I could
    // not find that" about work they hold, or told the right sentence with no way to act on it, on
    // any page that words a 404 itself. The failed state in the test above is the sibling that
    // proves the control is not drawn for every failure.
    await asksForASecondFactor(pattern);
  }, 60_000);
});
