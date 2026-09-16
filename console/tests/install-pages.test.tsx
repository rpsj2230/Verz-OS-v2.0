/**
 * The five install screens in the browser, and the three rules they exist to keep.
 *
 * These are the screens somebody opens because something is wrong, or because they are about to
 * tell a client that nothing is, and then they stop looking. So the failures worth writing tests
 * for here are not layout failures, they are the four ways a screen reassures somebody it should
 * not have: a value whose source label was dropped, a blank where an unknown fact should say
 * why, an empty list rendered where nothing looked, and a tick drawn over a verdict whose
 * conditions this browser cannot check.
 *
 * **Every list of columns here is compared with the Python model rather than with itself.**
 * `tests/support/python.ts` reads the field names out of `brain.install_routes`, so a field
 * added to a response and not to a page fails here, which is the only moment anybody will decide
 * what to do with it. Compared against the console's own constants these tests would be green
 * for every value those constants could hold.
 *
 * **The phone cases and the notice cases are split between two files on purpose.**
 * `tests/phone-width.test.tsx` mounts every registered route and waits for `[role="status"]` to
 * go away before it measures, and `ui/Notice.tsx` carries that role, so the two states on these
 * screens that draw a notice can never settle there. They are held here instead, with the
 * structural half of the phone rule asserted on the rendered tree: both tables sit inside a
 * `.grid__scroll`, which is what stops a row of identifiers taking the navigation off the side
 * of a phone.
 *
 * Task ids: M27.7.25, M27.7.27, M42.3.9
 *
 * M27.7.26 is the recovery screen and is deliberately not claimed here or in the commit:
 * the screen is built and openable, and what it shows on every install today is the
 * sentence saying nothing on this process can read the backup bucket. A screen that is
 * reachable and cannot answer is not the leaf.
 */

import { MemoryRouter } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  CEILING_COLUMNS,
  CONNECTION_COLUMNS,
  INSTALL_SECTIONS,
  THROTTLE_COLUMNS,
} from "../src/pages/installQuery";
import { NO_RELEASE_NAMED, READ_ITS_NOTES } from "../src/pages/Updates";
import { STATE_TONES } from "../src/ui/Status";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { backendEnumMembers, backendModelFields } from "./support/python";
import { readConsoleFile } from "./support/repo";

const ROUTES = "src/brain/install_routes.py";

/** A value that appears nowhere else, so a dropped one cannot be covered by another. */
function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
}

/** Mount one page against a stand-in API and wait for the request to settle. */
async function pageAnswering(
  module: string,
  name: string,
  path: string,
  body: unknown,
): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url) {
      if (!url.endsWith(`/api/v1${path}`)) {
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
  const Page = await pageComponent(module, name);
  const { container } = render(
    <MemoryRouter>
      <Page />
    </MemoryRouter>,
  );
  await waitFor(() => {
    if (container.querySelector(".note[role='status']")) {
      throw new Error("still loading");
    }
    if (!container.querySelector("h1")) {
      throw new Error("not arrived");
    }
  });
  return container;
}

/**
 * One page component by name.
 *
 * A switch over static imports rather than a template literal in `import()`, because a dynamic
 * import whose path is assembled from a variable cannot be analysed: the bundler warns, and the
 * module it cannot see is a module `tests/bundle-split.test.ts` cannot see either.
 */
async function pageComponent(module: string, name: string): Promise<() => JSX.Element> {
  const modules: Record<string, () => Promise<Record<string, unknown>>> = {
    Install: () => import("../src/pages/Install"),
    Updates: () => import("../src/pages/Updates"),
    Recovery: () => import("../src/pages/Recovery"),
    Limits: () => import("../src/pages/Limits"),
    Capacity: () => import("../src/pages/Capacity"),
  };
  const loader = modules[module];
  if (loader === undefined) {
    throw new Error(`no page module named ${module}`);
  }
  const found = (await loader())[name];
  if (typeof found !== "function") {
    throw new Error(`${module} exports no ${name}`);
  }
  return found as () => JSX.Element;
}

/** The value shown beside one label, or null when the row is not on the page. */
function valueBeside(container: HTMLElement, label: string): string | null {
  for (const row of container.querySelectorAll(".fields__row")) {
    if (row.querySelector("dt")?.textContent === label) {
      return row.querySelector("dd")?.textContent ?? "";
    }
  }
  return null;
}

// --- the columns are the API's columns --------------------------------------------------------

describe("what these pages agree with the API about", () => {
  test("every column of a ceiling, a throttled row and a connection budget is drawn", () => {
    // What breaks if this is deleted: a field added to one of the three row models arrives and
    // is dropped silently, which is the failure nobody notices. The names come out of the Python
    // source rather than out of this console, so the comparison is between two different
    // documents and not between a list and a copy of itself.
    expect([...CEILING_COLUMNS].sort()).toEqual(backendModelFields(ROUTES, "CeilingView").sort());
    expect([...THROTTLE_COLUMNS].sort()).toEqual(
      backendModelFields(ROUTES, "ThrottleView").sort(),
    );
    expect([...CONNECTION_COLUMNS].sort()).toEqual(
      backendModelFields(ROUTES, "ConnectionView").sort(),
    );
  });

  test("every field of what is running and of the newest release is one the version page draws", () => {
    // What breaks if this is deleted: a field is added to either model, for instance a second
    // address beside `notes`, and reaches the browser without anybody deciding how it is drawn
    // or whether it may be a link. The names come out of the Python source, and the list here is
    // the list the tests below draw with a sentinel each.
    expect(backendModelFields(ROUTES, "RunningView").sort()).toEqual([
      "cannot_say",
      "commit",
      "facts",
      "tag",
    ]);
    expect(backendModelFields(ROUTES, "ToldView").sort()).toEqual(["at", "by", "notes", "tag"]);
  });

  test("no verdict on these screens can choose a colour", () => {
    // What breaks if this is deleted: somebody adds `recoverable: "positive"` to the one table
    // in this console where a value picks a tone, which is a one-line change that reads as
    // completeness and puts a green tick on the screen whose whole argument is that the
    // reassuring answer has conditions a browser cannot check. Both enumerations are read out of
    // the Python source, so a ninth member added there is covered the day it is added.
    const words = [
      ...Object.values(backendEnumMembers("src/brain/console/version_view.py", "Standing")),
      ...Object.values(backendEnumMembers("src/brain/console/recovery_view.py", "Assurance")),
    ];
    expect(words.length).toBeGreaterThan(8);
    for (const word of words) {
      expect(Object.keys(STATE_TONES)).not.toContain(word);
    }
  });

  test("nothing on these screens reads a total or a count off a response", () => {
    // What breaks if this is deleted: a page grows "showing 3 of 47", which is the disclosure by
    // subtraction with every figure on it correct, on the one screen in this group whose rows a
    // reader's grant filters. Asserted over the source rather than over a rendered page, because
    // the failure is a field being read at all: a console that never names `total` cannot render
    // one whatever the API sends.
    const sources = [
      "src/pages/installQuery.ts",
      "src/pages/Install.tsx",
      "src/pages/Updates.tsx",
      "src/pages/Recovery.tsx",
      "src/pages/Limits.tsx",
      "src/pages/Capacity.tsx",
      "src/components/Facts.tsx",
    ];
    for (const source of sources) {
      const text = readConsoleFile(source);
      // The word appears in the prose above `readThrottled` and must not appear as a property
      // read, so the pattern is the access rather than the word. A check a comment can satisfy
      // is not a check.
      expect(text, source).not.toMatch(/\.total\b/);
      expect(text, source).not.toMatch(/\.truncated\b/);
    }
  });
});

// --- this install -----------------------------------------------------------------------------

describe("this install", () => {
  const KNOWN = {
    name: "release",
    source: "measured",
    value: sentinel("release"),
    because: sentinel("commit-note"),
  };
  const UNKNOWN = {
    name: "migration level",
    source: "unknown",
    value: "",
    because: sentinel("nothing-measured"),
  };

  test("every fact the API sent reaches the screen with its source beside it", async () => {
    // What breaks if this is deleted: the source label is dropped as tidying, and the same
    // column then holds a release read from a running image and a head read out of the source
    // tree with nothing between them. The reader came to decide whether to stop investigating.
    const container = await pageAnswering("Install", "Install", "/install", {
      facts: [KNOWN, UNKNOWN],
    });

    expect(valueBeside(container, "release")).toContain(KNOWN.value);
    expect(valueBeside(container, "release")).toContain("measured");
    expect(valueBeside(container, "migration level")).toContain("unknown");
  });

  test("an unknown fact shows the sentence saying why and no placeholder", async () => {
    // What breaks if this is deleted: a renderer supplies a dash, a dash reads as not
    // applicable, and the reader stops. `brain.console.installation.Fact` refuses to carry a
    // value it does not know precisely so that this decision has to be made here, and this is
    // where it is made.
    const container = await pageAnswering("Install", "Install", "/install", {
      facts: [UNKNOWN],
    });

    const row = [...container.querySelectorAll(".fields__row")].find(
      (one) => one.querySelector("dt")?.textContent === "migration level",
    );
    const cell = row?.querySelector("dd");

    expect(cell?.textContent).toContain(UNKNOWN.because);
    // The chip carrying the source word and the sentence, and nothing else. Asserted as the
    // absence of a value element rather than as the absence of the characters a placeholder is
    // usually spelled with, because the list of ways to write one is open and the structure is
    // not: `Facts` renders the value in a bare span and renders no span at all when there is
    // none.
    expect(cell?.querySelector("span:not(.chip)")).toBeNull();
    expect(cell?.textContent).toBe(`${UNKNOWN.source}${UNKNOWN.because}`);
  });
});

// --- version and updates ----------------------------------------------------------------------

describe("version and updates", () => {
  const PANEL = {
    running: {
      tag: "",
      facts: [
        {
          name: "built commit",
          source: "measured",
          value: sentinel("commit"),
          because: sentinel("commit-because"),
        },
      ],
      cannot_say: sentinel("cannot-say"),
      commit: sentinel("commit"),
    },
    told: null,
    unanswered: {
      why: "the release check is switched off",
      detail: sentinel("detail"),
      at: "2019-03-04T09:00:00Z",
    },
    standing: "unknown running",
    says: sentinel("says"),
    what_to_do: sentinel("what-to-do"),
    told_days_ago: null,
    goes_off_after_days: 30,
  };

  test("the standing and both of its sentences are the API's own", async () => {
    // What breaks if this is deleted: the console starts composing a sentence for a standing,
    // which is a second vocabulary for a closed set of eight, out of step with the first within
    // a release, on the screen a client reads before deciding they are patched.
    const container = await pageAnswering("Updates", "Updates", "/install/updates", PANEL);

    expect(container.textContent).toContain(PANEL.standing);
    expect(container.textContent).toContain(PANEL.says);
    expect(container.textContent).toContain(PANEL.what_to_do);
  });

  test("an install that names no release says so and shows both statements it read", async () => {
    // What breaks if this is deleted: the page renders an empty version field, or picks one of
    // the two statements and heads it with a version. That is the common state rather than the
    // odd one, because every install that has never run the update script is in it, and either
    // repair is right about a file and wrong about the containers.
    const container = await pageAnswering("Updates", "Updates", "/install/updates", PANEL);

    expect(container.textContent).toContain(PANEL.running.cannot_say);
    expect(container.textContent).toContain(PANEL.running.facts[0]?.value);
    expect(container.textContent).toContain(PANEL.unanswered.detail);
  });

  test("a telling carries who said so, and it is not dropped for tidiness", async () => {
    // What breaks if this is deleted: the tag renders without its source, and an administrator
    // who read the release notes this morning becomes indistinguishable from a value typed once
    // during setup. `brain.console.version_view.Told` requires `by` for that reason and a page
    // that showed the tag alone would undo it.
    const told = {
      ...PANEL,
      told: { tag: "v1.4.0", at: "2019-03-04T09:00:00Z", by: sentinel("who-said-so"), notes: "" },
      unanswered: null,
      standing: "current",
      told_days_ago: 1,
    };
    const container = await pageAnswering("Updates", "Updates", "/install/updates", told);

    expect(valueBeside(container, "newest release")).toBe("v1.4.0");
    expect(valueBeside(container, "said by")).toBe(sentinel("who-said-so"));
  });

  test("a named release is what is running, with the commit beside it under its own label", async () => {
    // What breaks if this is deleted: the page goes back to showing the tag alone, or shows the
    // commit under the release label, which is the column a client reads as their version
    // filled with something they cannot look up.
    const named = {
      ...PANEL,
      running: { ...PANEL.running, tag: "v1.4.0", cannot_say: "" },
    };
    const container = await pageAnswering("Updates", "Updates", "/install/updates", named);

    expect(valueBeside(container, "release")).toBe("v1.4.0");
    expect(valueBeside(container, "commit")).toBe(sentinel("commit"));
    expect(container.textContent).not.toContain(NO_RELEASE_NAMED);
  });

  test("with no release named, the reason is where the release would be and the commit still shows", async () => {
    // What breaks if this is deleted: an install whose containers run `latest` shows an empty
    // release row, or loses the commit, which is the only statement about what is running that
    // the page has in that state.
    const container = await pageAnswering("Updates", "Updates", "/install/updates", PANEL);

    expect(valueBeside(container, "release")).toBe(
      `${NO_RELEASE_NAMED}${PANEL.running.cannot_say}`,
    );
    expect(valueBeside(container, "commit")).toBe(sentinel("commit"));
  });

  test("an image that reported no commit draws no commit row rather than an empty one", async () => {
    // What breaks if this is deleted: a checkout or an image built without its manifest shows a
    // commit label with nothing beside it, which is the blank `Facts` refuses one card lower, and
    // the sentence saying why the commit is unknown is already in those facts.
    const uncommitted = { ...PANEL, running: { ...PANEL.running, commit: "" } };
    const container = await pageAnswering("Updates", "Updates", "/install/updates", uncommitted);

    expect(valueBeside(container, "commit")).toBeNull();
    expect(valueBeside(container, "release")).toContain(NO_RELEASE_NAMED);
  });

  test("a newer release is named with a link to its notes that tells the release host nothing", async () => {
    // What breaks if this is deleted: the reminder this screen exists for loses the one thing a
    // client acts on, which release and where its notes are, or the link starts sending the
    // console's own address to the host of the release list.
    const notes = "https://releases.example.invalid/v1.5.0";
    const behind = {
      ...PANEL,
      running: { ...PANEL.running, tag: "v1.4.0", cannot_say: "" },
      told: { tag: "v1.5.0", at: "2019-03-04T09:00:00Z", by: sentinel("the-list"), notes },
      unanswered: null,
      standing: "newer release available",
      told_days_ago: 0,
    };
    const container = await pageAnswering("Updates", "Updates", "/install/updates", behind);

    expect(container.textContent).toContain("newer release available");
    expect(valueBeside(container, "newest release")).toBe("v1.5.0");
    const link = [...container.querySelectorAll("a")].find(
      (one) => one.textContent === READ_ITS_NOTES,
    );
    expect(link?.getAttribute("href")).toBe(notes);
    expect(link?.getAttribute("rel")).toContain("noreferrer");
  });

  test("a release the list gave no notes address for draws no link at all", async () => {
    // What breaks if this is deleted: the notes row is drawn with an empty href, which a browser
    // resolves to this page, so the link a client clicks to read the notes reloads the screen.
    const unlinked = {
      ...PANEL,
      running: { ...PANEL.running, tag: "v1.4.0", cannot_say: "" },
      told: { tag: "v1.5.0", at: "2019-03-04T09:00:00Z", by: sentinel("the-list"), notes: "" },
      unanswered: null,
      standing: "newer release available",
      told_days_ago: 0,
    };
    const container = await pageAnswering("Updates", "Updates", "/install/updates", unlinked);

    expect(valueBeside(container, "newest release")).toBe("v1.5.0");
    expect(valueBeside(container, "notes")).toBeNull();
    expect(container.textContent).not.toContain(READ_ITS_NOTES);
  });

  test("a look that has not finished shows the API's instruction and neither a release nor a failure", async () => {
    // What breaks if this is deleted: the first load after a start, which is the load everybody
    // sees, draws an empty card or a stale answer where the page should say to come back in a
    // minute, and that sentence is the API's rather than one this console composes.
    const waiting = {
      ...PANEL,
      running: { ...PANEL.running, tag: "v1.4.0", cannot_say: "" },
      told: null,
      unanswered: null,
      standing: "not checked yet",
      what_to_do: sentinel("come-back-in-a-minute"),
    };
    const container = await pageAnswering("Updates", "Updates", "/install/updates", waiting);
    const card = [...container.querySelectorAll("section.card")].find(
      (one) => one.querySelector("h2")?.textContent === "The newest published release",
    );

    expect(container.textContent).toContain("not checked yet");
    expect(card?.textContent).toBe(
      `The newest published release${sentinel("come-back-in-a-minute")}`,
    );
    expect(valueBeside(container, "newest release")).toBeNull();
  });

  test("a check that failed shows the reason it failed, in the API's words", async () => {
    // What breaks if this is deleted: a failed look is drawn like a look that has not happened,
    // and somebody whose firewall is blocking the list is told to come back in a minute for ever.
    const failed = {
      ...PANEL,
      running: { ...PANEL.running, tag: "v1.4.0", cannot_say: "" },
      unanswered: {
        why: "the release list could not be reached",
        detail: sentinel("timed-out"),
        at: "2019-03-04T09:00:00Z",
      },
      standing: "check failed",
    };
    const container = await pageAnswering("Updates", "Updates", "/install/updates", failed);

    expect(container.textContent).toContain("check failed");
    expect(container.textContent).toContain("the release list could not be reached");
    expect(container.textContent).toContain(sentinel("timed-out"));
    expect(valueBeside(container, "newest release")).toBeNull();
  });
});

// --- backup and recovery ----------------------------------------------------------------------

describe("backup and recovery", () => {
  const COPY = {
    coverage: "database",
    facts: [
      {
        name: "database: newest copy reaches",
        source: "unknown",
        value: "",
        because: sentinel("never-copied"),
      },
    ],
    within_objective: false,
    objective_seconds: 3600,
  };
  const PANEL = {
    panel: {
      profile: "standard",
      copies: [COPY, { ...COPY, coverage: "object store" }],
      last_verified: {
        name: "last verified restore",
        source: "unknown",
        value: "",
        because: sentinel("never-verified"),
      },
      measured_rto_seconds: null,
      assurance: "never verified",
      says: sentinel("assurance-says"),
      what_to_do: sentinel("assurance-do"),
      drill_is_due: true,
      unreadable: [],
    },
    unread: "",
  };

  test("an install nothing looked at says nobody looked and draws no panel", async () => {
    // What breaks if this is deleted: the page falls back to an empty panel, which renders as an
    // install whose backups have never run. That is an alarming word for a fact nobody
    // established, and it would be believed. The assertion is the absence of the coverage rows,
    // not the presence of a sentence, because a sentence above an empty panel is still a panel.
    const container = await pageAnswering("Recovery", "Recovery", "/install/recovery", {
      panel: null,
      unread: sentinel("nobody-looked"),
    });

    expect(container.textContent).toContain(sentinel("nobody-looked"));
    expect(container.querySelectorAll(".fields__row")).toHaveLength(0);
  });

  test("every coverage the API sent gets a row, including one nothing has copied", async () => {
    // What breaks if this is deleted: a page filters out the coverages with no copy, and a
    // reader who counts three rows on a healthy install and two here has been told about the
    // missing one by subtraction. The verdict and the field this screen is named after are both
    // asserted, because they are the two things a reader looks at before deciding.
    const container = await pageAnswering("Recovery", "Recovery", "/install/recovery", PANEL);

    expect(container.textContent).toContain("database");
    expect(container.textContent).toContain("object store");
    expect(container.textContent).toContain(PANEL.panel.assurance);
    expect(container.textContent).toContain(PANEL.panel.says);
    expect(valueBeside(container, "last verified restore")).toContain(sentinel("never-verified"));
  });

  test("an unreadable record is named rather than counted", async () => {
    // What breaks if this is deleted: the page says how many records could not be read, and a
    // reader who is told a number cannot go and look at any of them. The run that falls over is
    // the run whose record is truncated, so the missing one is the one most likely to matter.
    const container = await pageAnswering("Recovery", "Recovery", "/install/recovery", {
      ...PANEL,
      panel: {
        ...PANEL.panel,
        unreadable: [{ where: sentinel("the-file"), why: sentinel("the-reason") }],
      },
    });

    expect(container.textContent).toContain(sentinel("the-file"));
    expect(container.textContent).toContain(sentinel("the-reason"));
  });

  test("a restore time nobody measured has no row where one would be", async () => {
    // What breaks if this is deleted: a null becomes a zero or a dash beside "the last verified
    // restore took", which is a measurement of a restore that never happened, on the panel whose
    // whole subject is telling those two apart.
    const container = await pageAnswering("Recovery", "Recovery", "/install/recovery", PANEL);

    expect(valueBeside(container, "the last verified restore took")).toBeNull();
    expect(valueBeside(container, "a rehearsal is owed")).toBe("true");
  });

  test("how to rehearse is drawn when nothing looked, and no control claims to run one", async () => {
    // What breaks if this is deleted: the rehearsal card drops off the unread shape, which is the
    // shape every install has today, and a reader of that state loses the one thing they can act
    // on; or a button appears beside it, which is a drill control that runs nothing. M30.3.9 asks
    // for one-click, and `brain.install_routes.NO_CONTROL_HERE_RUNS_A_REHEARSAL` is why it is not.
    const container = await pageAnswering("Recovery", "Recovery", "/install/recovery", {
      panel: null,
      unread: sentinel("nobody-looked"),
      rehearsal: {
        every_days: 7,
        copies_kept_days: 35,
        promised_recovery_seconds: 7200,
        manifest_ends: ".manifest.json",
        record_ends: ".drill.json",
        no_control_here: sentinel("no-control"),
      },
    });

    expect(container.textContent).toContain(sentinel("nobody-looked"));
    expect(container.textContent).toContain(sentinel("no-control"));
    expect(valueBeside(container, "a rehearsal is owed every")).toBe("7 days");
    expect(valueBeside(container, "the recovery time this profile promises")).toBe("7200s");
    expect(valueBeside(container, "a rehearsal's record is named ending")).toBe(".drill.json");
    expect(container.querySelectorAll("button, form")).toHaveLength(0);
  });
});

// --- rate limits ------------------------------------------------------------------------------

describe("rate limits", () => {
  const CEILINGS = [{ name: sentinel("xero"), per_day: 5000, raisable: true, derived: true }];

  test("an empty throttling list and an absent one are drawn differently", async () => {
    // What breaks if this is deleted: the two collapse, and the page renders "nothing on this
    // process looked" as "nobody is being throttled". Both draw no rows, so nothing else in this
    // file would notice, and the direction of the mistake is the reassuring one during an
    // incident. The empty case is also the answer a department-scoped reader gets.
    const empty = await pageAnswering("Limits", "Limits", "/install/limits", {
      ceilings: CEILINGS,
      throttled: [],
      unread: "",
    });
    const absent = await pageAnswering("Limits", "Limits", "/install/limits", {
      ceilings: CEILINGS,
      throttled: null,
      unread: sentinel("nothing-enumerates"),
    });

    const { NOBODY_IS_BEHIND_A_CEILING } = await import("../src/pages/Limits");
    expect(empty.textContent).toContain(NOBODY_IS_BEHIND_A_CEILING);
    expect(empty.textContent).not.toContain(sentinel("nothing-enumerates"));
    expect(absent.textContent).toContain(sentinel("nothing-enumerates"));
    expect(absent.textContent).not.toContain(NOBODY_IS_BEHIND_A_CEILING);
  });

  test("a throttled row shows what the API sent and no count of refused requests", async () => {
    // What breaks if this is deleted: somebody adds a refusals column, which is a number beside
    // a person's name describing how their afternoon is going. The assertion is over the cells
    // in the row rather than over the page, so an extra column fails here rather than being
    // invisible among the prose.
    const container = await pageAnswering("Limits", "Limits", "/install/limits", {
      ceilings: CEILINGS,
      throttled: [
        { scope: "principal", subject: sentinel("who"), limit: 60, retry_after_seconds: 12 },
      ],
      unread: "",
    });

    const rows = [...container.querySelectorAll("tbody tr")];
    const throttleRow = rows.find((row) => row.textContent?.includes(sentinel("who")));
    expect(throttleRow?.querySelectorAll("td")).toHaveLength(THROTTLE_COLUMNS.length);
    expect(container.textContent).toContain(sentinel("who"));
  });

  test("both tables sit inside a scrolling container", async () => {
    // What breaks if this is deleted: a row of identifiers takes the document sideways on a
    // phone, and what goes off the edge is the navigation rather than the table.
    // `.grid__table` sets `overflow-wrap: normal` so a column is not split mid-word, which only
    // works when something else is taking the overflow. `tests/phone-width.test.tsx` cannot
    // reach the state below because a notice never stops looking like a page that is still
    // asking, so the structural half is asserted here.
    const container = await pageAnswering("Limits", "Limits", "/install/limits", {
      ceilings: CEILINGS,
      throttled: [
        { scope: "principal", subject: sentinel("who"), limit: 60, retry_after_seconds: 12 },
      ],
      unread: "",
    });

    const tables = [...container.querySelectorAll("table")];
    expect(tables).toHaveLength(2);
    for (const table of tables) {
      expect(table.parentElement?.className).toBe("grid__scroll");
    }
  });
});

// --- capacity ---------------------------------------------------------------------------------

describe("capacity", () => {
  const BODY = {
    memory: {
      profile: "standard",
      host_total_mib: 16000,
      declared_mib: 4000,
      deployed_mib: null,
      breaches: [sentinel("breach")],
      unbudgeted: [sentinel("unbudgeted")],
    },
    connections: [{ database: sentinel("primary"), admissible: 100, demand: 60, headroom: 40 }],
  };

  test("a deployed figure nobody measured has no row where one would be", async () => {
    // What breaks if this is deleted: the row is drawn as zero, or as a copy of the declared
    // figure. The second is worse: two numbers equal by construction read as agreement between
    // independent measurements, and agreement is exactly what somebody opens this screen to
    // check.
    const container = await pageAnswering("Capacity", "Capacity", "/install/capacity", BODY);

    expect(valueBeside(container, "reserved by the compose files")).toBeNull();
    expect(valueBeside(container, "declared by this profile")).toBe("4000 MiB");
  });

  test("a budget finding is drawn in the API's own words", async () => {
    // What breaks if this is deleted: the page rewords a breach, which puts the arithmetic's
    // conclusion in two places, or reduces the findings to a count, which drops the only useful
    // half of a breach, which is which component it is about.
    const container = await pageAnswering("Capacity", "Capacity", "/install/capacity", BODY);

    expect(container.textContent).toContain(sentinel("breach"));
    expect(container.textContent).toContain(sentinel("unbudgeted"));
  });

  test("the connection table shows every database the API sent", async () => {
    // What breaks if this is deleted: a database is dropped from the screen whose whole subject
    // is whether this deployment is about to run out of connections.
    const container = await pageAnswering("Capacity", "Capacity", "/install/capacity", BODY);

    expect(container.textContent).toContain(sentinel("primary"));
    const rows = [...container.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(BODY.connections.length);
  });
});

// --- getting to them without a mouse ----------------------------------------------------------

describe("reaching the install screens from the keyboard", () => {
  test("every install screen is a native link in the shell's navigation", async () => {
    // What breaks if this is deleted: a section is added as a div with a click handler, which is
    // focusable by nothing and announced as nothing, and looks identical in review to the person
    // who wrote it. `scripts/check-boundaries.mjs` refuses the source pattern; this asks the
    // rendered question, which is what actually takes focus.
    const { Shell } = await import("../src/layout/Shell");
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Shell />
      </MemoryRouter>,
    );

    const nav = container.querySelector("nav");
    const links = [...(nav?.querySelectorAll("a") ?? [])];
    const addresses = links.map((link) => link.getAttribute("href"));

    for (const section of INSTALL_SECTIONS) {
      const found = links.find((link) => link.getAttribute("href") === section.to);
      expect(addresses, `${section.to} is not in the navigation`).toContain(section.to);
      expect(found?.tagName).toBe("A");
      expect(found?.textContent).toBe(section.label);
      expect(found?.getAttribute("tabindex")).toBeNull();
    }
  });

  test("the install sections are the screens the API serves and no others", () => {
    // What breaks if this is deleted: a sixth install address is added to the shell with no
    // route behind it, or a route is added with no way to reach it from the menu. Both are
    // invisible: the first renders the console's own not-found page and the second is a screen
    // nobody can open, which is exactly what `brain.ops.console_screens` counts.
    expect(INSTALL_SECTIONS.map((one) => one.to)).toEqual([
      "/install",
      "/updates",
      "/recovery",
      "/limits",
      "/connections",
      // The feature switches, since 2026-09-17: an install-wide setting served by
      // `brain.feature_routes`, so it sits with the other screens about this server.
      "/features",
    ]);
  });
});
