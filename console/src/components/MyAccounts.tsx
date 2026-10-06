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
  returnAddress,
  type ConsentStarted,
  type MyAccount,
  type MyAccounts as MyAccountsBody,
} from "../pages/connectors/consentAtVendor";
import { FailureNotice } from "../ui/FailureNotice";

export const READING_MY_ACCOUNTS = "Reading which of your accounts you may connect.";
export const NO_MY_ACCOUNTS = "No source here is connected by each person with their own account.";
export const NOT_SENT = "The vendor was not asked";

function myStatus(row: MyAccount): string {
  if (row.connected === null) {
    return row.told;
  }
  return row.connected ? "Connected." : "Not connected.";
}

export function MyAccounts() {
  const answer = useResource<MyAccountsBody>(MY_ACCOUNTS_API_PATH);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

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
    return <p className="note">{NO_MY_ACCOUNTS}</p>;
  }
  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} title={NOT_SENT} />}
      <ul aria-label="Your own accounts">
        {answer.data.accounts.map((row) => (
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
          </li>
        ))}
      </ul>
      <p className="hint note">{answer.data.told}</p>
    </>
  );
}
