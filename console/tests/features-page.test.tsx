/**
 * The Features screen: every feature drawn with its sentences, a switch that is confirmed and then
 * re-read, and the things it cannot switch said only while the API says them.
 *
 * Mounted on its own at its address, because the route table is a shared file this change does not
 * edit. The shapes are read from `brain.feature_routes` itself, so a renamed field fails here.
 *
 * Task ids: none
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  COMPONENTS_ARE_CHOSEN_BY_THE_PROFILE,
  FEATURES_API_PATH,
  FEATURES_PATH,
  KEEP_IT,
  NEVER_CHANGED,
  PLUGINS_HAVE_NO_LOADER,
  SWITCH_ON,
  UNREADABLE_ANSWER,
} from "../src/pages/featuresQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";

const LIST = `GET /api/v1${FEATURES_API_PATH}`;
const SWITCH = `POST /api/v1${FEATURES_API_PATH}/schedule_control`;
const ROUTES = "src/brain/feature_routes.py";

function feature(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "schedule_control",
    title: "Pause and run scheduled jobs from the console",
    what: "WHAT-SENTENCE",
    while_off: "WHILE-OFF-SENTENCE",
    on: false,
    read_by: ["brain.jobs_routes:pause_job"],
    changed_by: null,
    changed_at: null,
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}, one: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    features: [feature(one)],
    components_are_chosen_by_the_profile: true,
    plugins_have_no_loader: true,
    every_change_is_in_the_audit_trail: true,
    ...overrides,
  };
}

async function featuresPage(answers: Record<string, Answer>) {
  return mountPage(
    FEATURES_PATH,
    async () => {
      const { Features } = await import("../src/pages/Features");
      return <Features />;
    },
    answers,
  );
}

describe("what the Features screen draws", () => {
  test("a feature with its sentences, who reads it, and that nobody has switched it", async () => {
    // What breaks if this is deleted: a switch drawn without saying what it does or what reads it,
    // which is a control a person turns on trust.
    const { container } = await featuresPage({ [LIST]: () => json(page()) });

    const text = container.textContent ?? "";
    expect(text).toContain("WHAT-SENTENCE");
    expect(text).toContain("WHILE-OFF-SENTENCE");
    expect(text).toContain("brain.jobs_routes:pause_job");
    expect(text).toContain(NEVER_CHANGED);
    expect(text).toContain(COMPONENTS_ARE_CHOSEN_BY_THE_PROFILE);
    expect(text).toContain(PLUGINS_HAVE_NO_LOADER);
  });

  test("the facts about what cannot be switched leave when the API stops sending them", async () => {
    // What breaks if this is deleted: the page goes on saying plugins cannot be switched after a
    // loader exists.
    const { container } = await featuresPage({
      [LIST]: () =>
        json(
          page({
            components_are_chosen_by_the_profile: false,
            plugins_have_no_loader: false,
            every_change_is_in_the_audit_trail: false,
          }),
        ),
    });

    expect(container.textContent).not.toContain(PLUGINS_HAVE_NO_LOADER);
    expect(container.textContent).not.toContain(COMPONENTS_ARE_CHOSEN_BY_THE_PROFILE);
  });

  test("a refusal is the API's sentence with its reference, and an unreadable answer says so", async () => {
    // What breaks if this is deleted: a refused reader shown an empty list, which reads as a
    // product with no features rather than a request that was refused.
    const refused = await featuresPage({
      [LIST]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    });
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.container.textContent).toContain("TRACE-SENTINEL");

    const unreadable = await featuresPage({ [LIST]: () => json({ features: "no" }) });
    expect(unreadable.container.textContent).toContain(UNREADABLE_ANSWER);
  });
});

describe("switching a feature", () => {
  test("is confirmed with the product's sentence, posted as the opposite of what was drawn, and re-read", async () => {
    // What breaks if this is deleted: a switch sent without confirmation, sent the wrong way, or
    // a page that goes on drawing the old state after the database changed.
    let on = false;
    const { container, sent } = await featuresPage({
      [LIST]: () => json(page({}, { on, changed_by: on ? "u_admin" : null })),
      [SWITCH]: (body) => {
        on = (body as { on: boolean }).on;
        return json(feature({ on, changed_by: "u_admin", changed_at: "2019-03-04T09:00:00Z" }));
      },
    });

    fireEvent.click(button(container, SWITCH_ON));
    expect(container.textContent).toContain("WHAT-SENTENCE");
    fireEvent.click(button(container, KEEP_IT));
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);

    fireEvent.click(button(container, SWITCH_ON));
    const confirm = [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === SWITCH_ON);
    fireEvent.click(confirm as HTMLButtonElement);

    await waitFor(() => {
      expect(container.textContent).toContain("is now switched on");
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([{ on: true }]);
    expect(sent.filter((one) => one.method === "GET").length).toBeGreaterThanOrEqual(2);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.feature_routes` that the page goes
    // on reading, which renders as an empty sentence in production.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "FeaturesPage").sort());
    expect(Object.keys(feature()).sort()).toEqual(backendModelFields(ROUTES, "FeatureView").sort());
  });
});
