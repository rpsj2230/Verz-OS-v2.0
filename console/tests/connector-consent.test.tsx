/**
 * Consenting to a source at its vendor: the "Connect with" step after connecting, and the page the
 * vendor sends the person back to.
 *
 * The failures worth testing are where the person is sent and what is handed back. The step must
 * send the person to the address the API answered, having asked with this console's own consent
 * page; a source that does not consent by OAuth must not get the step at all; and the return page
 * must hand the answer over exactly once, because the state is single use on the server and a
 * second hand-over is told the consent is not theirs. Every path and name is held against the
 * Python routes and the API document rather than against this console's own copy.
 *
 * Task ids: M11.8.6
 */

import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, test, vi } from "vitest";
import * as client from "../src/api/client";
import { CONSENT_LATER, ConnectSource, connectLabel } from "../src/components/ConnectSource";
import { MyAccounts } from "../src/components/MyAccounts";
import {
  CONSENT_CALLBACK_API_PATH,
  CONSENT_RETURN_PATH,
  MY_ACCOUNTS_API_PATH,
  callbackPath,
  connectMyAccountLabel,
  connectWithLabel,
  consentPath,
  myConsentPath,
  returnAddress,
  vendorAnswer,
} from "../src/pages/connectors/consentAtVendor";
import { ConnectorConsent, GO_TO_MY_WORKSPACE, GO_TO_SOURCE, MY_WORKSPACE_PAGE } from "../src/pages/ConnectorConsent";
import type { Connectable } from "../src/pages/connectorsQuery";
import { declaredQueryParameters, declaredRequestBodySchema, declaredPropertyNames, declaredResponseSchema } from "./support/openapi";
import { backendModelFields } from "./support/python";
import { extractOne, readConsoleFile, readRepoFile } from "./support/repo";

const ROUTES = "src/brain/connector_routes.py";
const VENDOR_PAGE = "https://login.vendor.example/authorize?state=S";

afterEach(() => {
  vi.restoreAllMocks();
});

function aSource(consentWith: string): Connectable {
  return {
    name: "xero",
    label: "Xero",
    settings: [{ name: "tenant_id", label: "Organisation id", hint: "", max_chars: 200, blank: "Fill it in." }],
    credential_label: "Client secret",
    credential_hint: "",
    credential_shape: "key",
    credential_max_chars: 1000,
    may_connect: true,
    steps: [],
    writes: [],
    consent_with: consentWith,
    consent_told: consentWith ? "You will be sent to the vendor." : "",
  };
}

function ok<T>(data: T): Awaited<ReturnType<typeof client.request<T>>> {
  return { ok: true, status: 200, data } as Awaited<ReturnType<typeof client.request<T>>>;
}

async function connect(source: Connectable, onConnected: (told: string) => void): Promise<void> {
  render(
    <ConnectSource source={source} confirmation="Connect it." keyMaxChars={1000} keyBlank="Fill it in." onConnected={onConnected} />,
  );
  fireEvent.change(screen.getByLabelText("Organisation id"), { target: { value: "T-1" } });
  fireEvent.change(screen.getByLabelText("Client secret"), { target: { value: "SECRET-1" } });
  fireEvent.click(screen.getByRole("button", { name: connectLabel(source) }));
  const buttons = await screen.findAllByRole("button", { name: connectLabel(source) });
  await act(async () => {
    fireEvent.click(buttons[buttons.length - 1]!);
  });
}

describe("the paths and names are the API's own", () => {
  test("the consent paths and the return page are the ones the Python routes serve", () => {
    const routes = readRepoFile(ROUTES);
    expect(extractOne(routes, /^CONSENT_CALLBACK_PATH: Final = CONNECTORS_PATH \+ "([^"]+)"$/m, "the callback path")).toBe(
      CONSENT_CALLBACK_API_PATH.replace("/connectors", ""),
    );
    expect(extractOne(routes, /^CONSENT_PATH: Final = CONNECTORS_PATH \+ "([^"]+)"$/m, "the start path")).toBe(
      consentPath("{connector}").replace("/connectors", "").replace("%7Bconnector%7D", "{connector}"),
    );
    const oauth = readRepoFile("src/brain/connectors/oauth.py");
    expect(extractOne(oauth, /^CONSENT_RETURN_PATH: Final = "([^"]+)"$/m, "the return page")).toBe(CONSENT_RETURN_PATH);
    expect(readConsoleFile("src/pages/ConnectorConsent.route.tsx")).toContain(`path: "${CONSENT_RETURN_PATH.slice(1)}"`);
  });

  test("what the console sends and reads are fields the API declares", () => {
    const start = declaredRequestBodySchema("/api/v1/connectors/{connector}/consent", "post");
    expect(declaredPropertyNames(start)).toEqual(["return_address"]);
    expect(declaredQueryParameters(`/api/v1${CONSENT_CALLBACK_API_PATH}`, "get")).toEqual(
      expect.arrayContaining(["state", "code", "error"]),
    );
    const answered = declaredPropertyNames(declaredResponseSchema(`/api/v1${CONSENT_CALLBACK_API_PATH}`, "get"));
    expect(answered).toEqual(backendModelFields(ROUTES, "ConsentAnsweredView").sort());
    expect(backendModelFields(ROUTES, "ConnectableView")).toEqual(expect.arrayContaining(["consent_with", "consent_told"]));
  });

  test("the vendor's answer is read from the address and handed on with nothing else", () => {
    const answer = vendorAnswer("?state=S1&code=C1&session_state=x");
    expect(answer).toEqual({ state: "S1", code: "C1", error: "" });
    expect(callbackPath(answer)).toBe(`${CONSENT_CALLBACK_API_PATH}?state=S1&code=C1`);
    expect(callbackPath(vendorAnswer("?state=S2&error=access_denied"))).toBe(
      `${CONSENT_CALLBACK_API_PATH}?state=S2&error=access_denied`,
    );
    expect(returnAddress("https://console.example")).toBe(`https://console.example${CONSENT_RETURN_PATH}`);
  });
});

describe("the Connect with step", () => {
  test("a source consented to by OAuth is sent to the vendor's page once it is connected", async () => {
    const asked: Array<[string, unknown]> = [];
    vi.spyOn(client, "request").mockImplementation(async (path: string, options?: client.RequestOptions) => {
      asked.push([path, options?.body]);
      return path.endsWith("/consent") ? ok({ connector: "xero", address: VENDOR_PAGE }) : ok({ told: "Connected." });
    });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, origin: "https://console.example" });
    const told = vi.fn();
    await connect(aSource("Xero"), told);
    const go = await screen.findByRole("button", { name: connectWithLabel("Xero") });
    expect(screen.getByRole("button", { name: CONSENT_LATER })).toBeTruthy();
    await act(async () => {
      fireEvent.click(go);
    });
    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(VENDOR_PAGE);
    });
    expect(asked[1]).toEqual([consentPath("xero"), { return_address: `https://console.example${CONSENT_RETURN_PATH}` }]);
    expect(told).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  test("a source that does not consent by OAuth is connected with no step after it", async () => {
    vi.spyOn(client, "request").mockResolvedValue(ok({ told: "Connected." }));
    const told = vi.fn();
    await connect(aSource(""), told);
    await waitFor(() => {
      expect(told).toHaveBeenCalledWith("Connected.");
    });
    expect(screen.queryByRole("button", { name: connectWithLabel("Xero") })).toBeNull();
  });
});

describe("the page the vendor sends the person back to", () => {
  test("hands the answer over once, says what it came to and offers the source's page", async () => {
    const spy = vi.spyOn(client, "request").mockResolvedValue(
      ok({ connector: "xero", kept: true, told: "Consent kept.", back_to: "/connectors/xero" }),
    );
    const router = createMemoryRouter([{ path: CONSENT_RETURN_PATH, element: <ConnectorConsent /> }], {
      initialEntries: [`${CONSENT_RETURN_PATH}?state=ONCE-1&code=C1`],
    });
    render(
      <StrictMode>
        <RouterProvider router={router} />
      </StrictMode>,
    );
    expect(await screen.findByText("Consent kept.")).toBeTruthy();
    expect(screen.getByRole("link", { name: GO_TO_SOURCE }).getAttribute("href")).toBe("/connectors/xero");
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(`${CONSENT_CALLBACK_API_PATH}?state=ONCE-1&code=C1`);
    expect(router.state.location.search).toBe("");
  });
});

describe("a person's own account, connected from My workspace", () => {
  test("the paths are the ones the Python routes serve, and the answer's fields are the API's", () => {
    const routes = readRepoFile(ROUTES);
    expect(extractOne(routes, /^MY_ACCOUNTS_PATH: Final = "([^"]+)"$/m, "the accounts path")).toBe(MY_ACCOUNTS_API_PATH);
    expect(extractOne(routes, /^MY_CONSENT_PATH: Final = MY_ACCOUNTS_PATH \+ "([^"]+)"$/m, "the own consent path")).toBe(
      myConsentPath("{connector}").replace(MY_ACCOUNTS_API_PATH, "").replace("%7Bconnector%7D", "{connector}"),
    );
    expect(extractOne(routes, /^MY_WORKSPACE_PAGE: Final = "([^"]+)"$/m, "where it sends a person on")).toBe(MY_WORKSPACE_PAGE);
    const listed = declaredPropertyNames(declaredResponseSchema(`/api/v1${MY_ACCOUNTS_API_PATH}`, "get"));
    expect(listed).toEqual(["accounts", "told"]);
    expect(backendModelFields(ROUTES, "MyAccountView")).toEqual(
      expect.arrayContaining(["connector", "label", "connected", "told"]),
    );
    const start = declaredRequestBodySchema("/api/v1/me/accounts/{connector}/consent", "post");
    expect(declaredPropertyNames(start)).toEqual(["return_address"]);
  });

  test("a source the person may connect is listed and its button sends them to the vendor", async () => {
    const asked: Array<[string, unknown]> = [];
    vi.spyOn(client, "request").mockImplementation(async (path: string, options?: client.RequestOptions) => {
      asked.push([path, options?.body]);
      if (path === MY_ACCOUNTS_API_PATH) {
        return ok({
          accounts: [{ connector: "xero", label: "Xero", connected: false, told: "" }],
          told: "Read only for your own questions.",
        });
      }
      return ok({ connector: "xero", address: VENDOR_PAGE });
    });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, origin: "https://console.example" });
    render(<MyAccounts />);
    const go = await screen.findByRole("button", { name: connectMyAccountLabel("Xero") });
    expect(screen.getByText(/Not connected\./)).toBeTruthy();
    await act(async () => {
      fireEvent.click(go);
    });
    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(VENDOR_PAGE);
    });
    expect(asked.at(-1)).toEqual([myConsentPath("xero"), { return_address: `https://console.example${CONSENT_RETURN_PATH}` }]);
    vi.unstubAllGlobals();
  });

  test("a person with no source to connect is told so and offered no button", async () => {
    vi.spyOn(client, "request").mockResolvedValue(ok({ accounts: [], told: "Read only for your own questions." }));
    render(<MyAccounts />);
    expect(await screen.findByText(/No source here is connected by each person/)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  test("the return page sends a person's own consent on to My workspace", async () => {
    vi.spyOn(client, "request").mockResolvedValue(
      ok({ connector: "xero", kept: true, told: "Your account is connected.", back_to: MY_WORKSPACE_PAGE }),
    );
    const router = createMemoryRouter([{ path: CONSENT_RETURN_PATH, element: <ConnectorConsent /> }], {
      initialEntries: [`${CONSENT_RETURN_PATH}?state=OWN-1&code=C1`],
    });
    render(<RouterProvider router={router} />);
    expect(await screen.findByText("Your account is connected.")).toBeTruthy();
    expect(screen.getByRole("link", { name: GO_TO_MY_WORKSPACE }).getAttribute("href")).toBe(MY_WORKSPACE_PAGE);
  });
});
