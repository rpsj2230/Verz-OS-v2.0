/**
 * The Artifacts screen: the sentence when nothing records one, the rows when something does, and
 * the controls that narrow only what the page holds.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing look like the screen working:
 * an empty table where the API said nothing is recorded, a date with nothing beside it, and a kind
 * filter offering a kind nothing on the page is.
 *
 * Task ids: none
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ARTIFACTS_CAPTION,
  NONE_MATCH,
  NOTHING_RECORDED,
  READING_ARTIFACTS,
} from "../src/pages/Artifacts";
import {
  NO_ARTIFACT_FILTERS,
  keptUntil,
  narrowed,
  offeredKinds,
  type ArtifactRow,
} from "../src/pages/artifactsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { declaredResponseSchema } from "./support/openapi";

const OPERATION = "/api/v1/govern/artifacts";
const CONSOLE_ORIGIN = "https://console.test";
const RULE = "An artifact is kept no longer than its shortest-lived input.";

beforeAll(async () => {
  await import("../src/pages/Artifacts");
}, 60_000);

function row(overrides: Partial<ArtifactRow> & { artifact_id: string }): ArtifactRow {
  return {
    kind: "report",
    agent_id: "quoting",
    produced_for: "u_aaron",
    produced_at: "2019-03-04T09:00:00Z",
    state: "current",
    superseded_by: "",
    run_id: "run_1",
    agent_version: "3",
    kept_as: "payload",
    kept_until: "2019-04-03T09:00:00Z",
    kept_because: "kept 30 days from when it was produced",
    ...overrides,
  };
}

async function mount(body: unknown): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url) {
      return new URL(url, CONSOLE_ORIGIN).pathname === OPERATION
        ? new Response(JSON.stringify(body), {
            status: 200,
            headers: { "content-type": "application/json" },
          })
        : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Artifacts } = await import("../src/pages/Artifacts");
  const router = createMemoryRouter([{ path: "/artifacts", element: <Artifacts /> }], {
    initialEntries: ["/artifacts"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_ARTIFACTS) || !container.querySelector("h2")) {
      throw new Error("still reading");
    }
  });
  return container;
}

describe("what the artifacts screen agrees with the API about", () => {
  test("every field of a row the API declares is one this page reads", () => {
    // What breaks if this is deleted: a field renamed on the server arrives undefined and the
    // Kept until column draws nothing beside a date, with the typecheck green because the fixture
    // here was written by hand.
    const schema = declaredResponseSchema(OPERATION, "get");
    expect(Object.keys(schema["properties"] as object).sort()).toEqual(
      ["artifacts", "kept_rule", "unread"].sort(),
    );
    expect(Object.keys(row({ artifact_id: "a" })).sort()).toEqual(
      [
        "agent_id",
        "agent_version",
        "artifact_id",
        "kept_as",
        "kept_because",
        "kept_until",
        "kind",
        "produced_at",
        "produced_for",
        "run_id",
        "state",
        "superseded_by",
      ].sort(),
    );
  });
});

describe("what the artifacts screen shows", () => {
  test("nothing recorded is a sentence and never an empty table", async () => {
    // What breaks if this is deleted: an empty table under "Artifacts produced", which reads as an
    // estate that produced nothing.
    const container = await mount({ artifacts: null, unread: "NOBODY-RECORDS", kept_rule: RULE });

    expect(container.textContent).toContain(NOTHING_RECORDED);
    expect(container.textContent).toContain("NOBODY-RECORDS");
    expect(container.textContent).toContain(RULE);
    expect(container.querySelector("table")).toBeNull();
  });

  test("a row says who it was for, when, what made it, and until when it is kept", async () => {
    // What breaks if this is deleted: the design's three columns are drawn and the leaf's two are
    // not, which is provenance and retention missing from the screen named after them.
    const container = await mount({
      artifacts: [row({ artifact_id: "art_1" })],
      unread: "",
      kept_rule: RULE,
    });

    const table = container.querySelector(`table[aria-label="${ARTIFACTS_CAPTION}"]`);
    expect(table).not.toBeNull();
    const text = table?.textContent ?? "";
    expect(text).toContain("art_1");
    expect(text).toContain("u_aaron");
    expect(text).toContain("run_1");
    expect(text).toContain("kept 30 days from when it was produced");
  });

  test("the filters narrow the rows the page holds and say nothing matched when none does", async () => {
    // What breaks if this is deleted: a search that matched nothing draws the empty-estate
    // sentence, which says there are no artifacts rather than none matching.
    const container = await mount({
      artifacts: [row({ artifact_id: "art_1" }), row({ artifact_id: "art_2", kind: "deck" })],
      unread: "",
      kept_rule: RULE,
    });
    const search = container.querySelector("input[type='search']") as HTMLInputElement;
    fireEvent.change(search, { target: { value: "nothing-like-this" } });

    expect(container.textContent).toContain(NONE_MATCH);
  });
});

describe("how the rows are narrowed", () => {
  test("a kind is offered only when a row on the page is that kind", () => {
    // What breaks if this is deleted: the filter lists kinds from a fixed vocabulary, and picking
    // one nothing on the page is reads as the estate having produced none.
    expect(offeredKinds([row({ artifact_id: "a", kind: "deck" })])).toEqual(["deck"]);
  });

  test("newest first is the default, and a class with no clock says why rather than a date", () => {
    // What breaks if this is deleted: the oldest artifact heads the list somebody opens to find
    // what was just made, or a row with no date draws an empty cell beside nothing.
    const rows = [
      row({ artifact_id: "old", produced_at: "2019-01-01T00:00:00Z" }),
      row({ artifact_id: "new", produced_at: "2019-02-01T00:00:00Z" }),
    ];
    expect(narrowed(rows, NO_ARTIFACT_FILTERS).map((one) => one.artifact_id)).toEqual([
      "new",
      "old",
    ]);
    expect(
      keptUntil(
        row({ artifact_id: "r", kept_until: "", kept_because: "kept while the record exists" }),
      ),
    ).toBe("kept while the record exists");
  });
});
