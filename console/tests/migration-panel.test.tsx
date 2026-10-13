/**
 * The migration panel on the Features page: the three documents with where each stands and what is
 * outstanding, saving one from pasted JSON, and reporting a cutover complete.
 *
 * Mounted through the Features page, because that is where the panel is drawn. The shapes are read
 * from `brain.migration_routes` itself, so a renamed field fails here.
 *
 * Task ids: M37.1.1.1, M37.1.3.2, M37.1.4.1, M37.7.5
 */

import { act, fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { FEATURES_API_PATH, FEATURES_PATH } from "../src/pages/featuresQuery";
import {
  COMPLETE_PATH,
  MIGRATION_API_PATH,
  NOT_JSON,
  NOTHING_REACHES_IT,
  NOTHING_SAVED,
  REPORT_COMPLETE,
  SWITCHED_OFF,
} from "../src/pages/migrationQuery";
import { button, json, mountPage, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const FEATURES = `GET /api/v1${FEATURES_API_PATH}`;
const READ = `GET /api/v1${MIGRATION_API_PATH}`;
const SAVE_REGISTER = `PUT /api/v1${MIGRATION_API_PATH}/register`;
const COMPLETE = `POST /api/v1${COMPLETE_PATH}`;
const ROUTES = "src/brain/migration_routes.py";

const SAVED = { by: "u_admin", at: "2019-06-01T00:00:00Z" };

function register(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { saved: null, document: null, agreed: false, gaps: [], ...overrides };
}

function period(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    saved: null,
    document: null,
    may_cut_over: false,
    gaps: [],
    disagreements: [],
    unreviewed: [],
    only_one_answered: [],
    ...overrides,
  };
}

function cutover(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    saved: null,
    document: null,
    gaps: [],
    acts_outstanding: [],
    may_report_complete: false,
    reported_complete: null,
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    register: register(),
    parallel: period(),
    cutover: cutover(),
    workspace_is_on: true,
    nothing_reaches_the_old_system: true,
    ...overrides,
  };
}

const FEATURE_LIST = { features: [], components_are_chosen_by_the_profile: true, plugins_have_no_loader: true };

async function featuresPage(answers: Record<string, Answer>) {
  return mountPage(
    FEATURES_PATH,
    async () => {
      const { Features } = await import("../src/pages/Features");
      return <Features />;
    },
    { [FEATURES]: () => json(FEATURE_LIST), ...answers },
  );
}

describe("what the migration panel draws", () => {
  test("nothing saved reads as nothing saved, and that nothing reaches the old system", async () => {
    // What breaks if this is deleted: an empty install shown as a migration that is agreed, or a
    // panel that reads as a connection to the old system.
    const { container } = await featuresPage({ [READ]: () => json(page()) });
    const text = container.textContent ?? "";
    expect(text).toContain(NOTHING_SAVED);
    expect(text).toContain(NOTHING_REACHES_IT);
    expect(text).not.toContain("Every item is decided");
  });

  test("what is outstanding is listed as the API computed it", async () => {
    // What breaks if this is deleted: gaps hidden behind a green chip.
    const { container } = await featuresPage({
      [READ]: () =>
        json(
          page({
            register: register({ saved: SAVED, gaps: ["prompt_1: catalogued and nothing decided"] }),
            parallel: period({ saved: SAVED, gaps: ["days running: 1"], unreviewed: ["q_differ"] }),
            cutover: cutover({ saved: SAVED, acts_outstanding: ["M37.2.6.1: every grant withdrawn"] }),
          }),
        ),
    });
    const text = container.textContent ?? "";
    expect(text).toContain("prompt_1: catalogued and nothing decided");
    expect(text).toContain("Unreviewed disagreement: q_differ");
    expect(text).toContain("M37.2.6.1: every grant withdrawn");
    expect(text).toContain("act(s) with a security consequence are unrecorded");
  });

  test("a cutover that was reported complete says by whom", async () => {
    // What breaks if this is deleted: a completion drawn as a pending act.
    const { container } = await featuresPage({
      [READ]: () =>
        json(page({ cutover: cutover({ saved: SAVED, may_report_complete: true, reported_complete: SAVED }) })),
    });
    expect(container.textContent).toContain("Reported complete by u_admin.");
  });

  test("the switch being off says so and offers no form", async () => {
    // What breaks if this is deleted: a form the route will refuse.
    const { container } = await featuresPage({ [READ]: () => json(page({ workspace_is_on: false })) });
    expect(container.textContent).toContain(SWITCHED_OFF);
    expect(container.querySelector("#migration-register")).toBeNull();
  });
});

describe("saving a document", () => {
  test("text that is not JSON is told so and nothing is sent", async () => {
    // What breaks if this is deleted: a half-typed document put, or silence.
    const { container, sent } = await featuresPage({ [READ]: () => json(page()) });
    fireEvent.change(container.querySelector("#migration-register") as HTMLTextAreaElement, {
      target: { value: "{no" },
    });
    await act(async () => {
      fireEvent.click(button(container, "Save what the old system holds"));
    });
    expect(container.textContent).toContain(NOT_JSON);
    expect(sent.filter((one) => one.method === "PUT")).toHaveLength(0);
  });

  test("a document is put as typed, to the register's address, and the page is read again", async () => {
    // What breaks if this is deleted: a document altered on the way or saved to another record.
    const { container, sent } = await featuresPage({
      [READ]: () => json(page()),
      [SAVE_REGISTER]: () => json(register({ saved: SAVED, agreed: true })),
    });
    fireEvent.change(container.querySelector("#migration-register") as HTMLTextAreaElement, {
      target: { value: '{"surveyed": []}' },
    });
    await act(async () => {
      fireEvent.click(button(container, "Save what the old system holds"));
    });
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "PUT").map((one) => one.body)).toEqual([{ surveyed: [] }]);
    });
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "GET" && one.path.includes("migration")).length).toBeGreaterThanOrEqual(2);
    });
  });

  test("a refusal is the API's sentence", async () => {
    // What breaks if this is deleted: a refusal replaced by a console sentence that says less.
    const { container } = await featuresPage({
      [READ]: () => json(page()),
      [SAVE_REGISTER]: () => json({ message: "REFUSED-BY-THE-REGISTER", trace_id: "T-1" }, 404),
    });
    fireEvent.change(container.querySelector("#migration-register") as HTMLTextAreaElement, { target: { value: "{}" } });
    await act(async () => {
      fireEvent.click(button(container, "Save what the old system holds"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("REFUSED-BY-THE-REGISTER");
    });
  });
});

describe("reporting a cutover complete", () => {
  test("is offered only once a cutover is saved and sends nothing until pressed", async () => {
    // What breaks if this is deleted: a completion button over a record nobody saved.
    const none = await featuresPage({ [READ]: () => json(page()) });
    expect([...none.container.querySelectorAll("button")].some((one) => (one.textContent ?? "").includes(REPORT_COMPLETE))).toBe(
      false,
    );
    const saved = await featuresPage({ [READ]: () => json(page({ cutover: cutover({ saved: SAVED }) })) });
    expect(button(saved.container, REPORT_COMPLETE)).toBeTruthy();
    expect(saved.sent.filter((one) => one.method === "POST")).toHaveLength(0);
  });

  test("the refusal that names the unrecorded acts is shown as the API wrote it", async () => {
    // What breaks if this is deleted: a refused completion shown as a generic failure.
    const { container } = await featuresPage({
      [READ]: () => json(page({ cutover: cutover({ saved: SAVED }) })),
      [COMPLETE]: () => json({ message: "M37.2.6.1 IS UNRECORDED", trace_id: "T-2" }, 404),
    });
    await act(async () => {
      fireEvent.click(button(container, REPORT_COMPLETE));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("M37.2.6.1 IS UNRECORDED");
    });
  });
});

describe("the shapes", () => {
  test("every field the panel reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.migration_routes` that the panel
    // goes on reading, which renders as an empty sentence in production.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "WorkspacePage").sort());
    expect(Object.keys(register()).sort()).toEqual(backendModelFields(ROUTES, "RegisterView").sort());
    expect(Object.keys(period()).sort()).toEqual(backendModelFields(ROUTES, "ParallelView").sort());
    expect(Object.keys(cutover()).sort()).toEqual(backendModelFields(ROUTES, "CutoverView").sort());
  });
});
