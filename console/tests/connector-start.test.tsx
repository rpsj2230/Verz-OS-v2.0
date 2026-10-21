/**
 * The line over the Connectors list that says which source to start with (M34.1.1.1): drawn while
 * nothing is connected and the API suggests one, and drawn in no other case.
 *
 * Task ids: M34.1.1.1
 */

import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

const asked = vi.fn();
vi.mock("../src/api/client", () => ({ request: (path: string) => asked(path) }));

import { readStart, START_API_PATH } from "../src/pages/adoptionCoverageQuery";
import { ConnectorStart, START_BECAUSE, START_WITH } from "../src/pages/connectors/ConnectorStart";

beforeEach(() => {
  asked.mockReset();
});

describe("the suggestion", () => {
  test("is drawn, with its reason, while nothing is connected and the API names a source", async () => {
    // What breaks if this is deleted: the card is never drawn and a new install is left to guess
    // where to start, or it is drawn without saying why, which is a recommendation nobody can weigh.
    asked.mockResolvedValue({ ok: true, data: { source: "hubspot", label: "HubSpot" } });
    const page = render(<ConnectorStart connectedAny={false} />);
    await waitFor(() => expect(page.container.textContent).toContain(`${START_WITH} HubSpot.`));
    expect(page.container.textContent).toContain(START_BECAUSE);
    expect(asked).toHaveBeenCalledWith(START_API_PATH);
  });

  test("is not drawn, and not asked for, once something is connected", () => {
    // What breaks if this is deleted: a line about where to start stays on the page after somebody
    // has started, and the route is asked for on every visit by installs that no longer need it.
    const page = render(<ConnectorStart connectedAny={true} />);
    expect(page.container.textContent).toBe("");
    expect(asked).not.toHaveBeenCalled();
  });

  test("is not drawn when the API suggests nothing or does not answer", async () => {
    // What breaks if this is deleted: a documents-only install is told to start with nothing, or a
    // failed read leaves a broken card, where saying nothing is better than recommending uploads.
    asked.mockResolvedValue({ ok: true, data: { source: null, label: null } });
    const none = render(<ConnectorStart connectedAny={false} />);
    await waitFor(() => expect(asked).toHaveBeenCalled());
    expect(none.container.textContent).toBe("");
    none.unmount();
    asked.mockReset();
    asked.mockResolvedValue({ ok: false, failure: { kind: "refused" } });
    const failed = render(<ConnectorStart connectedAny={false} />);
    await waitFor(() => expect(asked).toHaveBeenCalled());
    expect(failed.container.textContent).toBe("");
  });

  test("a body that is not the route's shape suggests nothing", () => {
    // What breaks if this is deleted: a body of another shape draws a card naming nothing.
    expect(readStart(null)).toBeUndefined();
    expect(readStart({ source: "" })).toBeUndefined();
    expect(readStart({ source: "xero" })).toEqual({ source: "xero", label: "xero" });
  });
});
