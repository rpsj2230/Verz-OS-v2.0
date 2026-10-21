/**
 * A person's own accounts at a source's vendor, in My workspace: which they may connect, whether
 * each is connected, and the button that sends them to the vendor to connect one.
 *
 * `brain.connector_routes` answers `GET /me/accounts` for the person asking and nobody else: a source
 * is listed only where they hold its reader capability in the department the connection answers to,
 * so a source they may not read is absent exactly as one nobody connected is. Pressing "Connect my
 * <vendor> account" holds a consent for them alone and sends this tab to the vendor's own page, where
 * they sign in to their own account; the vendor sends them back to `pages/ConnectorConsent.tsx`,
 * which sends them on here. What they consent to is read only for their own questions. See
 * `pages/connectors/consentAtVendor.ts`.
 *
 * Task ids: M11.8.6
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import {
  MY_ACCOUNTS_API_PATH,
  connectMyAccountLabel,
  myConsentPath,
  myDisconnectPath,
  returnAddress,
  type ConsentStarted,
  type MyAccount,
  type MyAccounts as MyAccountsBody,
  type MyDisconnected,
} from "../pages/connectors/consentAtVendor";
import { FailureNotice } from "../ui/FailureNotice";
import { ConfirmDialog } from "./kit";
import { EmptyList } from "./kit/states";

export const READING_MY_ACCOUNTS = "Reading which of your accounts you may connect.";
export const NO_MY_ACCOUNTS = "No source here is connected by each person with their own account.";
export const NOT_SENT = "The vendor was not asked";
export const NOT_DISCONNECTED = "Your account was not disconnected";
export const KEEP_IT = "Keep it connected";

/** The department's own connections are listed and have no control here (M40.5.1.4). */
export const INHERITED_LABEL = "Provided by your department";

export function disconnectMyAccountLabel(vendor: string): string {
  return `Disconnect my ${vendor} account`;
}

/** What pressing it will do, said before it is done: the token is revoked, not just forgotten. */
export function disconnectConsequence(vendor: string): string {
  return (
    `This asks ${vendor} to revoke the access it gave this install to your account, then removes ` +
    "the copy this install holds. Anything that used it stops working for you until you connect again."
  );
}

function myStatus(row: MyAccount): string {
  if (row.connected === null) {
    return row.told;
  }
  return row.connected ? "Connected." : "Not connected.";
}

export function MyAccounts() {
  const [version, setVersion] = useState(0);
  const answer = useResource<MyAccountsBody>(MY_ACCOUNTS_API_PATH, version);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [disconnecting, setDisconnecting] = useState<MyAccount | null>(null);
  const [said, setSaid] = useState("");

  const connect = useCallback((row: MyAccount) => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const body = { return_address: returnAddress(window.location.origin) };
      const result = await request<ConsentStarted>(myConsentPath(row.connector), { method: "POST", body });
      if (!result.ok) {
        setBusy(false);
        setFailure(result.failure);
        return;
      }
      // To the vendor's own page, in this tab. See `pages/connectors/consentAtVendor.ts`.
      window.location.assign(result.data.address);
    })();
  }, []);

  const disconnect = useCallback(
    (row: MyAccount) => {
      setBusy(true);
      setFailure(null);
      setSaid("");
      void (async () => {
        const result = await request<MyDisconnected>(myDisconnectPath(row.connector), { method: "POST" });
        setBusy(false);
        setDisconnecting(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setSaid(result.data.told);
        setVersion((one) => one + 1);
      })();
    },
    [],
  );

  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.data === null) {
    return (
      <p className="note" role="status">
        {READING_MY_ACCOUNTS}
      </p>
    );
  }
  if (answer.data.accounts.length === 0) {
    return (
      <EmptyList
        compact
        title={NO_MY_ACCOUNTS}
        adds="A source is listed once an administrator connects one that each person connects with their own account."
        by={["connector_admin", "super_admin"]}
      />
    );
  }
  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} title={NOT_SENT} />}
      {said === "" ? null : (
        <p className="note" role="status">
          {said}
        </p>
      )}
      <ul aria-label="Your own accounts">
        {answer.data.accounts.map((row) =>
          row.provenance === "department" ? (
            <li key={row.connector}>
              {row.label}: {INHERITED_LABEL}. <span className="note">{row.told}</span>
            </li>
          ) : (
            <li key={row.connector}>
              {row.label}: {myStatus(row)}{" "}
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => {
                  connect(row);
                }}
              >
                {connectMyAccountLabel(row.label)}
              </button>
              {row.disconnectable ? (
                <button
                  type="button"
                  className="button"
                  disabled={busy}
                  onClick={() => {
                    setDisconnecting(row);
                  }}
                >
                  {disconnectMyAccountLabel(row.label)}
                </button>
              ) : null}
            </li>
          ),
        )}
      </ul>
      <p className="note">{answer.data.told}</p>
      <ConfirmDialog
        open={disconnecting !== null}
        question={disconnecting === null ? "" : `${disconnectMyAccountLabel(disconnecting.label)}?`}
        consequence={disconnecting === null ? "" : disconnectConsequence(disconnecting.label)}
        confirmLabel="Disconnect"
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={() => {
          if (disconnecting !== null) {
            disconnect(disconnecting);
          }
        }}
        onCancel={() => {
          setDisconnecting(null);
        }}
      />
    </>
  );
}
