/**
 * The third third of `tests/screen-states.test.tsx`: every page that asks on arrival, dealt into three
 * files so the three hundred mounts run side by side. The rule, the allowlists and the reasons are in
 * `support/screenStateRules.tsx` and the argument for them is in the first file's docstring.
 *
 * Task ids: M27.8.3
 */

import { beforeAll, describe, test } from "vitest";
import { holdsFourSentences, shard } from "./support/screenStateRules";

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
  test.each(shard(2, 3))("%s says loading, empty, unreachable and failed in four different sentences", async (pattern) => {
    // What breaks if this is deleted: a page that draws "That did not work" when the laptop has
    // lost its network, which sends a person to ask an administrator about a fault that is theirs;
    // a page whose empty list is a blank panel that reads as still loading; or a page whose
    // loading sentence is the same as its empty one, so a slow answer reads as nothing there.
    await holdsFourSentences(pattern);
  }, 60_000);
});
