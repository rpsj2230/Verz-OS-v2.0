/**
 * The Secrets vault: whether the vault is open, which slots hold a key, how each connected source's
 * run tokens ended, how a replaced key reaches every process, and what reached the audit ledger.
 *
 * `docs/screens.html` does not draw the vault. The screen takes the Storage screen's shape and says
 * in the API's words what it could and could not read: the seal first, because a sealed vault makes
 * every slot unknown and the person reading needs to know it is sealed rather than silent; each slot
 * as held, defined and empty, empty or not known, never its value; the lease tallies for the
 * sources this reader may be told are connected, with no count of any other; and the shipping of the
 * vault's own log. There is no control here: keys are written on the Models and Connectors screens,
 * and opening a sealed vault is three people at a terminal, which the seal's sentence says.
 *
 * Task ids: M31.3.2.1, M31.3.2.2, M31.3.2.3, M31.3.2.4, M31.3.2.5, M31.3.2.6, M38.4.1.3
 */

import { useResource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import {
  VAULT_API_PATH,
  readVault,
  sealInWords,
  slotInWords,
  tokenInWords,
  type VaultSlot,
} from "./vaultQuery";

export const VAULT_HEADING = "Secrets vault";
export const VAULT_CRUMB = "Install › Secrets vault";
export const VAULT_LEDE =
  "Whether the vault is open, which slots hold a key and when each was written, how each " +
  "connector run's token ended, and what reached the audit ledger. No key is ever shown.";

export const READING_VAULT = "Reading the vault.";
export const NEVER_WRITTEN = "Not written";
export const NOTHING_SHIPPED_YET = "Nothing shipped in the last 24 hours";
export const NO_LEASES = "No connector run held a lease in the last 24 hours.";

function when(stamp: string | null | undefined): string {
  return stamp ? new Date(stamp).toISOString().replace("T", " ").slice(0, 16) + " UTC" : NEVER_WRITTEN;
}

function SlotTable({ label, slots, scopes }: { label: string; slots: readonly VaultSlot[]; scopes: boolean }) {
  return (
    <div className="grid__scroll">
      <table className="grid__table" aria-label={label}>
        <thead>
          <tr>
            <th scope="col">Slot</th>
            <th scope="col">For</th>
            <th scope="col">Holds</th>
            <th scope="col">Written</th>
            {scopes ? <th scope="col">Scopes to ask for</th> : null}
            {scopes ? <th scope="col">Never ask for</th> : null}
          </tr>
        </thead>
        <tbody>
          {slots.map((slot) => (
            <tr key={slot.slot}>
              <td>
                <code>{slot.slot}</code>
              </td>
              <td>{slot.description}</td>
              <td>{slotInWords(slot)}</td>
              <td>{slot.state === "held" ? when(slot.set_at) : "-"}</td>
              {scopes ? <td>{slot.request.join("; ")}</td> : null}
              {scopes ? <td>{slot.refuse.join("; ")}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VaultBody() {
  const answer = useResource<unknown>(VAULT_API_PATH);
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_VAULT}
      </p>
    );
  }
  const page = readVault(answer.data);
  if (page === null) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK}>
        <p>The answer about the vault was not in a shape this screen can read.</p>
      </Notice>
    );
  }
  const audit = page.audit;
  return (
    <>
      <section className="card" aria-label="The seal">
        <h2>The vault</h2>
        <dl className="fields">
          <div className="fields__row">
            <dt>State</dt>
            <dd>{sealInWords(page.seal)}</dd>
          </div>
        </dl>
        <p className="note">{page.told}</p>
        {page.slots_unread ? <p className="note">{page.slots_unread}</p> : null}
      </section>

      <section className="card" aria-label="This process's token">
        <h2>This process's token</h2>
        <dl className="fields">
          <div className="fields__row">
            <dt>Policy</dt>
            <dd>{tokenInWords(page.token_policy)}</dd>
          </div>
          <div className="fields__row">
            <dt>Carries</dt>
            <dd>{page.token_policies.length ? page.token_policies.join(", ") : "-"}</dd>
          </div>
        </dl>
        <p className="note">{page.token_told}</p>
      </section>

      <section className="card">
        <h2>Model provider keys</h2>
        <SlotTable label="Provider slots" slots={page.providers} scopes={false} />
        <p className="note">{page.rotation}</p>
      </section>

      <section className="card">
        <h2>Connected sources' keys</h2>
        <SlotTable label="Connector slots" slots={page.connectors} scopes />
      </section>

      <section className="card">
        <h2>Connector run leases</h2>
        {page.leases === null ? null : page.leases.length === 0 ? (
          <p className="note">{NO_LEASES}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table" aria-label="Leases">
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Issued</th>
                  <th scope="col">Revoked at the end</th>
                  <th scope="col">Expired first</th>
                  <th scope="col">Not revoked</th>
                </tr>
              </thead>
              <tbody>
                {page.leases.map((row) => (
                  <tr key={row.connector}>
                    <td>
                      <code>{row.connector}</code>
                    </td>
                    <td>{row.issued}</td>
                    <td>{row.revoked}</td>
                    <td>{row.expired}</td>
                    <td>{row.not_revoked}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="note">{page.leases_told}</p>
      </section>

      <section className="card">
        <h2>The vault's audit log</h2>
        {audit.entries === null || audit.entries === undefined ? null : (
          <dl className="fields" aria-label="Audit shipping">
            <div className="fields__row">
              <dt>Entries shipped</dt>
              <dd>{audit.entries}</dd>
            </div>
            <div className="fields__row">
              <dt>Of which refused</dt>
              <dd>{audit.refused}</dd>
            </div>
            <div className="fields__row">
              <dt>Last shipped</dt>
              <dd>{audit.last_shipped_at ? when(audit.last_shipped_at) : NOTHING_SHIPPED_YET}</dd>
            </div>
          </dl>
        )}
        <p className="note">{audit.told}</p>
      </section>
    </>
  );
}

export function Vault() {
  return (
    <article className="page">
      <p className="note">{VAULT_CRUMB}</p>
      <h1>{VAULT_HEADING}</h1>
      <p className="lede">{VAULT_LEDE}</p>
      <VaultBody />
    </article>
  );
}
