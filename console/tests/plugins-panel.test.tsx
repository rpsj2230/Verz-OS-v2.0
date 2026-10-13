/**
 * The plugin panel on the Features page: the plugins this install has recorded, the acts each
 * state offers, a manifest recorded from pasted JSON, and the points in Advanced.
 *
 * Mounted through the Features page, because that is where the panel is drawn. The shapes are read
 * from `brain.plugin_routes` itself, so a renamed field fails here.
 *
 * Task ids: M29.2.1, M29.2.2, M29.2.3
 */

import { act, fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { FEATURES_API_PATH, FEATURES_PATH } from "../src/pages/featuresQuery";
import { NOT_JSON, NOT_LOADED, PLUGINS_API_PATH, SWITCHED_OFF, verbPath, verbsFor } from "../src/pages/pluginsQuery";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const FEATURES = `GET /api/v1${FEATURES_API_PATH}`;
const PLUGINS = `GET /api/v1${PLUGINS_API_PATH}`;
const RECORD = `POST /api/v1${PLUGINS_API_PATH}`;
const ROUTES = "src/brain/plugin_routes.py";

function plugin(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    plugin_id: "stand-in",
    version: "1.0.0",
    point: "connector",
    state: "installed",
    since: "2019-03-04T09:00:00Z",
    history: ["1.0.0"],
    requires: ["read:ticket.status"],
    config: [{ name: "STAND_IN_KEY", meaning: "WHAT-THE-KEY-IS", required: true }],
    core_min: "0.1.0",
    core_max: "9.0.0",
    ...overrides,
  };
}

function point(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "connector",
    leaf: "M29.1.2",
    answer: "plugin",
    tier: "sidecar",
    direction: "produces",
    carries: "code",
    contract: "brain.connectors.contract:ConnectorFetch",
    why: "WHY-SENTENCE",
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    points: [point()],
    plugins: [plugin()],
    registry_is_on: true,
    no_plugin_is_loaded: true,
    core_version: "0.1.0",
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

describe("what the plugin panel draws", () => {
  test("a recorded plugin with its state, its point, what it needs and that nothing is loaded", async () => {
    // What breaks if this is deleted: a plugin drawn without its state or without saying that
    // recording it runs nothing, which reads as an extension that is live.
    const { container } = await featuresPage({ [PLUGINS]: () => json(page()) });
    const text = container.textContent ?? "";
    expect(text).toContain("stand-in 1.0.0");
    expect(text).toContain("installed");
    expect(text).toContain("Plugs in at connector");
    expect(text).toContain("read:ticket.status");
    expect(text).toContain("WHAT-THE-KEY-IS");
    expect(text).toContain(NOT_LOADED);
  });

  test("the statement that nothing is loaded and that recording is off leave when the API stops saying them", async () => {
    // What breaks if this is deleted: the panel goes on saying nothing runs after a runner exists,
    // or goes on saying recording is off once it is on.
    const { container } = await featuresPage({
      [PLUGINS]: () => json(page({ no_plugin_is_loaded: false, registry_is_on: true })),
    });
    expect(container.textContent).not.toContain(NOT_LOADED);
    expect(container.textContent).not.toContain(SWITCHED_OFF);
    const off = await featuresPage({ [PLUGINS]: () => json(page({ registry_is_on: false })) });
    expect(off.container.textContent).toContain(SWITCHED_OFF);
    expect(off.container.querySelector("#plugin-manifest")).toBeNull();
  });

  test("the points are in Advanced and not on the page", async () => {
    // What breaks if this is deleted: module paths and contract names drawn for an administrator.
    const { container } = await featuresPage({ [PLUGINS]: () => json(page()) });
    const panel = container.querySelector('[data-slot="plugins-panel"]');
    const copy = panel?.cloneNode(true) as HTMLElement;
    copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
      one.remove();
    });
    expect(copy.textContent).not.toContain("brain.connectors.contract:ConnectorFetch");
    expect(panel?.querySelector('[data-slot="advanced"]')?.textContent).toContain(
      "brain.connectors.contract:ConnectorFetch",
    );
  });
});

describe("what a state offers", () => {
  test("each state offers the lifecycle's own edges and nothing else", () => {
    // What breaks if this is deleted: a button for a move the lifecycle refuses, or no way to
    // remove a plugin that is off.
    expect(verbsFor("installed")).toEqual(["enable"]);
    expect(verbsFor("enabled")).toEqual(["disable"]);
    expect(verbsFor("disabled")).toEqual(["enable", "remove"]);
    expect(verbsFor("absent")).toEqual([]);
  });

  test("an act is posted to the plugin's own address and the list is read again", async () => {
    // What breaks if this is deleted: a switch sent to the wrong plugin or never re-read.
    let state = "installed";
    const { container, sent } = await featuresPage({
      [PLUGINS]: () => json(page({ plugins: [plugin({ state })] })),
      [`POST /api/v1${verbPath("stand-in", "enable")}`]: () => {
        state = "enabled";
        return json(plugin({ state }));
      },
    });
    await act(async () => {
      fireEvent.click(button(container, "Switch on: stand-in"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain('"stand-in" is now switched on.');
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([
      `/api/v1${verbPath("stand-in", "enable")}`,
    ]);
    expect(sent.filter((one) => one.path.startsWith(`/api/v1${PLUGINS_API_PATH}`) && one.method === "GET").length).toBeGreaterThanOrEqual(2);
    expect(button(container, "Switch off: stand-in")).toBeTruthy();
  });
});

describe("recording a manifest", () => {
  test("text that is not JSON is told so and nothing is sent", async () => {
    // What breaks if this is deleted: a half-typed manifest posted, or silence.
    const { container, sent } = await featuresPage({ [PLUGINS]: () => json(page()) });
    const box = container.querySelector<HTMLTextAreaElement>("#plugin-manifest");
    expect(box).not.toBeNull();
    fireEvent.change(box as HTMLTextAreaElement, { target: { value: "{not json" } });
    await act(async () => {
      fireEvent.click(button(container, "Record plugin"));
    });
    expect(container.textContent).toContain(NOT_JSON);
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);
  });

  test("a manifest is posted as the document typed and its refusal is the API's sentence", async () => {
    // What breaks if this is deleted: a manifest altered on the way, or a refusal replaced by
    // a console sentence that says less than the API's.
    const { container, sent } = await featuresPage({
      [PLUGINS]: () => json(page({ plugins: [] })),
      [RECORD]: () => json({ message: "REFUSED-BY-THE-REGISTRY", trace_id: "T-1" }, 404),
    });
    const box = container.querySelector<HTMLTextAreaElement>("#plugin-manifest");
    fireEvent.change(box as HTMLTextAreaElement, { target: { value: '{"plugin_id": "stand-in"}' } });
    await act(async () => {
      fireEvent.click(button(container, "Record plugin"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("REFUSED-BY-THE-REGISTRY");
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { manifest: { plugin_id: "stand-in" } },
    ]);
  });
});

describe("the shapes", () => {
  test("every field the panel reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.plugin_routes` that the panel goes
    // on reading, which renders as an empty sentence in production.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "PluginsPage").sort());
    expect(Object.keys(plugin()).sort()).toEqual(backendModelFields(ROUTES, "PluginView").sort());
    expect(Object.keys(point()).sort()).toEqual(backendModelFields(ROUTES, "PointView").sort());
  });
});
