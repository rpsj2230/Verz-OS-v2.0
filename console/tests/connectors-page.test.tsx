/**
 * The connectors screen in the browser, and the four ways it could reassure somebody wrongly.
 *
 * This is the screen the owner of a fresh install opens to find out what his system has access
 * to, so the failures worth testing are not layout failures. They are: an empty table drawn where
 * nothing looked, a credential or a vault path appearing on a row, a control offered for
 * something this build cannot do, and a figure drawn for today's use that nothing measured.
 *
 * **The columns are compared with the Python model rather than with themselves.**
 * `tests/support/python.ts` reads the field names out of `brain.connector_routes`, so a field
 * added to the response and drawn nowhere fails here, which is the only moment anybody decides
 * what to do with it. Compared against this console's own constants the test would be green for
 * every value those constants could hold.
 *
 * **The phone case lives in `tests/phone-width.test.tsx` and the notice cases live here.** That
 * file waits for `[role="status"]` to go away before it measures and `ui/Notice.tsx` carries that
 * role, so the two states on this screen that draw a notice can never settle there.
 *
 * Task ids: M42.6.5
 */

import { MemoryRouter } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { Connectors, WHAT_WE_COPY } from "../src/pages/Connectors";
import {
  CONNECTORS_LABEL,
  CONNECTORS_PATH,
  NOT_PROBED,
  TRUST_COLUMNS,
  TRUST_DETAIL,
  stateOf,
  type Trust,
} from "../src/pages/connectorsQuery";
import { STATE_TONES } from "../src/ui/Status";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { backendModelFields } from "./support/python";
import { readConsoleFile, readRepoFile } from "./support/repo";

const ROUTES = "src/brain/connector_routes.py";
const API_PATH = "/api/v1/connectors";

/** A value that appears nowhere else, so a dropped one cannot be covered by another. */
function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
}

/** The vault path a real binding carries, which must never reach this console. */
const VAULT_PATH = "database/creds/sentinel_binding";

function aRow(over: Partial<Trust> = {}): Trust {
  return {
    name: "laravel",
    wiring: "database",
    credential: sentinel("credential-sentence"),
    budget: sentinel("ceiling-sentence"),
    projected_fields: 9,
    checked_at: "2019-03-04T09:00:00Z",
    health: "ok",
    lifecycle: "enabled",
    serving: true,
    version: "1.0.0",
    reaches: sentinel("reaches"),
    access: sentinel("access"),
    permission_sync: sentinel("sync"),
    ...over,
  };
}

function aBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    connectors: [aRow()],
    unread: "",
    connecting: sentinel("connecting"),
    copy_policy: [
      { what: sentinel("copied-thing"), verdict: "projected", why: sentinel("copied-why") },
      { what: sentinel("never-thing"), verdict: "never", why: sentinel("never-why") },
    ],
    budget_unread: sentinel("no-numerator"),
    may_connect: false,
    ...over,
  };
}

/** Mount the page against a stand-in API and wait for the request to settle. */
async function pageAnswering(body: unknown): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url) {
      if (!url.endsWith(API_PATH)) {
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
  const { container } = render(
    <MemoryRouter>
      <Connectors />
    </MemoryRouter>,
  );
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("not arrived");
    }
    if (container.querySelector(".note[role='status']")) {
      throw new Error("still loading");
    }
  });
  return container;
}

// --- what this page agrees with the API about ---------------------------------------------------

describe("what this page agrees with the API about", () => {
  test("every field the API sends about a connector is drawn somewhere", () => {
    // What breaks if this is deleted: a field added to the row model arrives and is dropped
    // silently, which on this screen means a fact about what a source may do to a client's
    // system that nobody sees. The names come out of the Python source, so this compares two
    // documents rather than a list against a copy of itself.
    const drawn = [
      ...TRUST_COLUMNS.map((one) => one.field),
      ...TRUST_DETAIL.map((one) => one.field),
    ];

    expect([...drawn].sort()).toEqual(backendModelFields(ROUTES, "TrustView").sort());
  });

  test("no sentence this screen shows can choose a colour", () => {
    // What breaks if this is deleted: somebody adds a word from one of these sentences to the
    // one table in this console where a value picks a tone, and a connector that may write to a
    // client's finance system renders green. `ui/Status.tsx`'s table is the connector health
    // vocabulary and nothing else, and the state column is the only column that reaches it.
    expect(Object.keys(STATE_TONES)).not.toContain(NOT_PROBED);
    for (const word of ["read_only", "write", "none", "predicate", "delegated"]) {
      expect(Object.keys(STATE_TONES)).not.toContain(word);
    }
  });

  test("nothing on this screen reads a total, a count or a numerator off a response", () => {
    // What breaks if this is deleted: the page grows "showing 3 of 14", which on the one screen
    // whose subject is reach is the disclosure by subtraction with every value correct, or it
    // grows a progress bar whose numerator nothing measured. Asserted over the source, because
    // the failure is a field being read at all.
    for (const source of ["src/pages/connectorsQuery.ts", "src/pages/Connectors.tsx"]) {
      const text = readConsoleFile(source);
      expect(text, source).not.toMatch(/\.total\b/);
      expect(text, source).not.toMatch(/\.truncated\b/);
      expect(text, source).not.toMatch(/\.used\b/);
    }
  });

  test("the shell offers this screen under the label the design names, in Operate", () => {
    // What breaks if this is deleted: the entry drifts to the registry's title, "Connector
    // health", and `brain.ops.console_design.navigation_gaps` starts reporting Connectors as a
    // screen the design names and the console does not offer, which is true of a screen that
    // exists and cannot be found by somebody following the design. Both the address and the
    // label are asserted against the shell's own source, because that sweep reads it.
    const shell = readConsoleFile("src/layout/Shell.tsx");
    expect(shell).toContain(`{ to: "${CONNECTORS_PATH}", label: "${CONNECTORS_LABEL}" }`);
    // Above the Govern group, which is where the design puts Operate.
    expect(shell.indexOf(CONNECTORS_PATH)).toBeLessThan(shell.indexOf('label: "Roles"'));
  });

  test("this console has no field a credential could be typed into", () => {
    // What breaks if this is deleted: somebody adds the obvious control. A credential typed into
    // a browser has nowhere to go: nothing in this system writes one into the vault at runtime,
    // so the field would either be sent to an endpoint that does not exist or be held in a form
    // whose only effect is that it was typed. Asserted as the absence of an input element and of
    // a password type in the page's own source.
    const text = readConsoleFile("src/pages/Connectors.tsx");
    expect(text).not.toMatch(/<input/);
    expect(text).not.toMatch(/type="password"/);
    expect(text).not.toMatch(/<form/);
  });
});

// --- what the screen draws ----------------------------------------------------------------------

describe("the connectors screen", () => {
  test("every source the API sent reaches the table with its sentences under it", async () => {
    // What breaks if this is deleted: the positive case goes untested, and every assertion below
    // about what must not appear is satisfied by a page that draws nothing at all.
    const container = await pageAnswering(aBody());

    expect(container.textContent).toContain("laravel");
    expect(container.textContent).toContain(sentinel("reaches"));
    expect(container.textContent).toContain(sentinel("access"));
    expect(container.textContent).toContain(sentinel("sync"));
    expect(container.textContent).toContain(sentinel("credential-sentence"));
    // The design's wording where the design gives some: the projected column reads as a number
    // of fields and the copy card carries SCREEN 9's own heading, read out of the design file so
    // a drift in either direction fails here.
    expect(container.textContent).toContain("9 fields");
    expect(readRepoFile("docs/screens.html")).toContain(WHAT_WE_COPY);
    expect(container.textContent).toContain(WHAT_WE_COPY);
    // The copy policy is served by the API and drawn whole, both halves of it.
    expect(container.textContent).toContain(sentinel("copied-why"));
    expect(container.textContent).toContain(sentinel("never-why"));
  });

  test("a source nothing has probed shows a word rather than a blank", async () => {
    // What breaks if this is deleted: an empty state cell, which reads as nothing being wrong
    // with a source nobody has reached. The word is one `ui/Status.tsx` does not recognise, so
    // it renders in the quietest tone, which is right: an unprobed source is not an incident.
    expect(stateOf(aRow({ health: "" }))).toBe(NOT_PROBED);
    const container = await pageAnswering(aBody({ connectors: [aRow({ health: "" })] }));

    expect(container.textContent).toContain(NOT_PROBED);
  });

  test("nothing looked and nothing installed are drawn differently", async () => {
    // What breaks if this is deleted: an install where nothing on the server holds a record of
    // what is connected renders as an install that reads no outside data, which is the
    // reassuring answer to the question this screen exists to answer honestly. Both states draw
    // no rows, so a page that treated them alike would render the second as the first.
    const unread = await pageAnswering(
      aBody({ connectors: null, unread: sentinel("nothing-looked") }),
    );
    const empty = await pageAnswering(aBody({ connectors: [] }));

    expect(unread.textContent).toContain(sentinel("nothing-looked"));
    expect(unread.querySelector("table")).toBeNull();
    expect(empty.textContent).not.toContain(sentinel("nothing-looked"));
    expect(empty.querySelector(".note")?.textContent).toBeTruthy();
  });

  test("the ceiling column carries the API's reason for having no figure for today", async () => {
    // What breaks if this is deleted: the column reads as the whole answer, and somebody plans a
    // backfill believing the screen would have shown them how much of the allowance was already
    // spent. The design asks for that figure and this install cannot measure it.
    const container = await pageAnswering(aBody());

    expect(container.textContent).toContain(sentinel("no-numerator"));
  });

  test("the screen says what connecting involves and offers no control for it", async () => {
    // What breaks if this is deleted: the screen looks finished. It has no add button, so
    // without the sentence a reader is left to conclude that connecting a source is something
    // this console simply does not mention.
    const container = await pageAnswering(aBody({ may_connect: true }));

    expect(container.textContent).toContain(sentinel("connecting"));
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
  });

  test("this console asks for no field that could hold a vault path or a secret", async () => {
    // What breaks if this is deleted: somebody adds `path` or `secret` to the row model and a
    // column for it here, which is how a vault path reaches a screenshot in a support chat. The
    // page draws exactly the fields the Python model declares and the first test in this file
    // holds those two lists equal, so this is the half that says what may not be in either.
    const fields = backendModelFields(ROUTES, "TrustView");
    for (const forbidden of ["path", "secret", "vault_path", "token", "key"]) {
      expect(fields).not.toContain(forbidden);
    }
    // And nothing in this console's own source names one, so a column could not be added here
    // without the assertion above going red first.
    const text = readConsoleFile("src/pages/connectorsQuery.ts");
    expect(text).not.toMatch(/"(path|secret|token|vault_path)"/);
    const container = await pageAnswering(aBody());
    expect(container.textContent).not.toContain(VAULT_PATH);
  });
});
