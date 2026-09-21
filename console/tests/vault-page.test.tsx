/**
 * The Secrets vault screen: the seal, each slot's state, the connector run leases, rotation, and
 * the shipping of the vault's audit log.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing look like the screen working: a
 * sealed vault drawn as a vault with no keys, a slot the installer defined drawn as missing, a
 * process with no database drawn as zero leases, and a control on a screen whose API offers none.
 *
 * Task ids: M31.3.2.1, M31.3.2.2, M31.3.2.3, M31.3.2.4, M31.3.2.5, M31.3.2.6, M38.4.1.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NO_LEASES, READING_VAULT } from "../src/pages/Vault";
import type { VaultBody } from "../src/pages/vaultQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const SCREEN = "/api/v1/vault";
const CONSOLE_ORIGIN = "https://console.test";
const SEALED = "The secrets vault is sealed, so nothing can read or keep a credential.";
const ROTATION = "Each application process reads every provider slot's metadata once a minute.";
const LEASES_TOLD = "Each attempt mints a run token with a TTL of 15 minutes.";
const AUDIT_TOLD = "The worker ships the vault's audit log into the audit ledger every five minutes.";
const NO_DATABASE = "This process has no database, so no lease can be counted.";

beforeAll(async () => {
  await import("../src/pages/Vault");
}, 60_000);

function vault(overrides: Partial<VaultBody> = {}): VaultBody {
  return {
    seal: "open",
    told: "The secrets vault is open.",
    slots_unread: "",
    token_policy: "own",
    token_policies: ["application", "default"],
    token_told: "This process's token carries the application policy and no other.",
    providers: [
      {
        slot: "providers/anthropic",
        description: "Anthropic API key",
        state: "held",
        set_at: "2019-03-04T09:00:00Z",
        request: [],
        refuse: [],
      },
      { slot: "providers/openai", description: "OpenAI API key", state: "empty", set_at: null, request: [], refuse: [] },
    ],
    connectors: [
      {
        slot: "connector_keys/hubspot",
        description: "The key hubspot issues for this company's connection.",
        state: "defined",
        set_at: null,
        request: ["crm.objects.contacts.read"],
        refuse: ["crm.objects.*.write"],
      },
    ],
    leases: [{ connector: "xero", issued: 8, revoked: 5, expired: 1, not_revoked: 2 }],
    leases_told: LEASES_TOLD,
    lease_ttl_minutes: 15,
    rotation: ROTATION,
    audit: { entries: 12, refused: 3, last_shipped_at: "2019-03-04T09:05:00Z", told: AUDIT_TOLD },
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function mount(answer: (url: URL) => Response | null): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url) {
      return answer(new URL(url, CONSOLE_ORIGIN));
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Vault } = await import("../src/pages/Vault");
  const router = createMemoryRouter([{ path: "/vault", element: <Vault /> }], {
    initialEntries: ["/vault"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_VAULT)) {
      throw new Error("still reading");
    }
  });
  return container;
}

describe("what the secrets vault screen shows", () => {
  test("the seal, each slot's state and when it was written, and a defined slot as defined", async () => {
    // What breaks if this is deleted: the seal drops off the screen an operator opens after a
    // restart, or a slot the installer defined reads as missing.
    const container = await mount((url) => (url.pathname === SCREEN ? json(vault()) : null));
    expect(container.querySelector('[aria-label="The seal"]')?.textContent).toContain("Open");
    const providers = container.querySelector('[aria-label="Provider slots"]')?.textContent ?? "";
    expect(providers).toContain("Holds a key");
    expect(providers).toContain("2019-03-04 09:00 UTC");
    expect(providers).toContain("Empty");
    const connectors = container.querySelector('[aria-label="Connector slots"]')?.textContent ?? "";
    expect(connectors).toContain("Defined, empty");
    expect(connectors).toContain("crm.objects.contacts.read");
    expect(connectors).toContain("crm.objects.*.write");
  });

  test("the policies this process's token carries are named, and a root token is not its own", async () => {
    // What breaks if this is deleted: a root token in BRAIN_VAULT_TOKEN reads as a healthy vault,
    // because nothing on the screen says which policies the token carries.
    const own = await mount((url) => (url.pathname === SCREEN ? json(vault()) : null));
    const ownCard = own.querySelector(`[aria-label="This process's token"]`)?.textContent ?? "";
    expect(ownCard).toContain("Its own policy only");
    expect(ownCard).toContain("application, default");
    const root = await mount((url) =>
      url.pathname === SCREEN
        ? json(vault({ token_policy: "other", token_policies: ["root"], token_told: "mint one" }))
        : null,
    );
    const rootCard = root.querySelector(`[aria-label="This process's token"]`)?.textContent ?? "";
    expect(rootCard).toContain("Not its own policy alone");
    expect(rootCard).toContain("root");
    expect(rootCard).toContain("mint one");
  });

  test("each source's leases are counted by how they ended, with rotation and shipping beside them", async () => {
    // What breaks if this is deleted: a token that lived on after its run is not shown, or the
    // screen stops saying that a replaced key needs no restart.
    const container = await mount((url) => (url.pathname === SCREEN ? json(vault()) : null));
    const leases = container.querySelector('[aria-label="Leases"]')?.textContent ?? "";
    expect(leases).toContain("xero");
    expect(leases).toMatch(/8\s*5\s*1\s*2/);
    expect(container.textContent).toContain(LEASES_TOLD);
    expect(container.textContent).toContain(ROTATION);
    const shipped = container.querySelector('[aria-label="Audit shipping"]')?.textContent ?? "";
    expect(shipped).toContain("12");
    expect(shipped).toContain("3");
    expect(container.textContent).toContain(AUDIT_TOLD);
  });

  test("a sealed vault says so and no lease or count is drawn as zero when none could be taken", async () => {
    // What breaks if this is deleted: a sealed vault reads as a vault with no keys, or an install
    // whose application has no database reads as one whose worker never ran.
    const container = await mount((url) =>
      url.pathname === SCREEN
        ? json(
            vault({
              seal: "sealed",
              told: SEALED,
              leases: null,
              leases_told: NO_DATABASE,
              audit: { entries: null, refused: null, last_shipped_at: null, told: "no database" },
            }),
          )
        : null,
    );
    expect(container.textContent).toContain("Sealed");
    expect(container.textContent).toContain(SEALED);
    expect(container.textContent).toContain(NO_DATABASE);
    expect(container.textContent).not.toContain(NO_LEASES);
    expect(container.querySelector('[aria-label="Leases"]')).toBeNull();
    expect(container.querySelector('[aria-label="Audit shipping"]')).toBeNull();
  });

  test("the screen has no control, and a refusal is the API's message", async () => {
    // What breaks if this is deleted: a button appears on a screen whose API offers no write, or
    // a 404 is drawn as an empty vault.
    const container = await mount((url) => (url.pathname === SCREEN ? json(vault({ leases: [] })) : null));
    expect(container.textContent).toContain(NO_LEASES);
    expect(container.querySelectorAll("button, input, select, progress, meter")).toHaveLength(0);

    const refused = await mount((url) =>
      url.pathname === SCREEN ? json({ message: "I could not find that.", trace_id: "t-1" }, 404) : null,
    );
    expect(refused.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.textContent).toContain("I could not find that.");
    expect(refused.querySelector('[aria-label="Provider slots"]')).toBeNull();
  });
});
