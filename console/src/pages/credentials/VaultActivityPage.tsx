/**
 * Vault activity, the second tab of Secrets and credentials: how each connected source's run tokens
 * ended, and what of the vault's own audit log reached the ledger.
 *
 * **What moved to Credentials, and why.** Until 2026-09-29 this screen was the Secrets vault: the
 * seal, the application token's policies, a table of provider slots and a table of connector slots
 * with their vault paths first, then the leases and the shipping. The Credentials page now lists
 * every slot the install declares, five kinds rather than two, with the seal, the policies and the
 * live-read sentence above them, so the seal card, the token card and both slot tables would have
 * been the same facts twice. What is left is the vault's activity, which is this page's own.
 *
 * `docs/screens.html` does not draw the vault. The lease tallies are for the sources this reader may
 * be told are connected, with no count of any other, and a count the API could not take is its
 * sentence and never nought. There is no control here: opening a sealed vault is three people at a
 * terminal, and a value is written on Credentials.
 *
 * Task ids: M31.3.2.1, M31.3.2.2, M31.3.2.3, M31.3.2.4, M31.3.2.5, M31.3.2.6, M38.4.1.3, M27.16.1
 */

import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import type { GridColumn } from "../../components/gridFeatures";
import { GridTable } from "../../components/kit/GridTable";
import { BY_THE_INSTALL, EmptyList, Fact, FactList, Note, PageHeader, SectionCard } from "../../components/kit";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";
import { CREDENTIALS_ADDRESS } from "./credentialRows";
import { SOMETHING_DID_NOT_WORK } from "../Overview";
import { VAULT_API_PATH, readVault, type LeaseRow } from "../vaultQuery";

export const VAULT_HEADING = "Vault activity";
export const VAULT_LEDE =
  "How each connected source's run tokens ended, and what of the vault's own audit log reached the audit ledger. No key is ever shown.";
export const CREDENTIALS_LINK = "The vault's state and every slot are on Credentials.";

export const READING_VAULT = "Reading the vault.";
export const NOTHING_SHIPPED_YET = "Nothing shipped in the last 24 hours";
export const NO_LEASES = "No connector run held a lease in the last 24 hours.";

/** How each source's run tokens ended. The figures sit on the right, as a column of numbers should. */
const LEASE_COLUMNS: GridColumn<LeaseRow>[] = [
  {
    id: "connector",
    header: "Source",
    cell: ({ row }) => row.original.connector,
    meta: { headerClassName: "py-1.5 pr-3 font-medium", cellClassName: "py-1.5 pr-3 text-ink" },
  },
  ...(
    [
      ["issued", "Issued", "issued"],
      ["revoked", "Revoked at the end", "revoked"],
      ["expired", "Expired first", "expired"],
      ["not_revoked", "Not revoked", "not_revoked"],
    ] as const
  ).map(
    ([id, header, field], at): GridColumn<LeaseRow> => ({
      id,
      header,
      cell: ({ row }) => row.original[field],
      meta: {
        headerClassName: `py-1.5 text-right font-medium${at === 3 ? "" : " pr-3"}`,
        cellClassName: `py-1.5 text-right tabular-nums${at === 3 ? "" : " pr-3"}`,
      },
    }),
  ),
];

function when(stamp: string): string {
  return new Date(stamp).toISOString().replace("T", " ").slice(0, 16) + " UTC";
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
      <SectionCard title="Connector run leases" footer={<Note>{page.leases_told}</Note>}>
        {page.leases === null || page.leases === undefined ? null : page.leases.length === 0 ? (
          <EmptyList
            compact
            title={NO_LEASES}
            adds="A lease is recorded each time a connector run takes one."
            by={BY_THE_INSTALL}
          />
        ) : (
          <div className="overflow-x-auto">
            <GridTable
              label="Leases"
              className="w-full min-w-[20rem] border-collapse text-[13px]"
              headRowClassName="border-b border-line text-left text-[11px] text-dim"
              rowClassName={() => "border-b border-line last:border-b-0"}
              columns={LEASE_COLUMNS}
              rows={page.leases}
              rowId={(row) => row.connector}
            />
          </div>
        )}
      </SectionCard>

      <SectionCard title="The vault's audit log" footer={<Note>{audit.told}</Note>}>
        {audit.entries === null || audit.entries === undefined ? null : (
          <div aria-label="Audit shipping" role="group">
            <FactList>
              <Fact label="Entries shipped">{audit.entries}</Fact>
              <Fact label="Of which refused">{audit.refused}</Fact>
              <Fact label="Last shipped">{audit.last_shipped_at ? when(audit.last_shipped_at) : NOTHING_SHIPPED_YET}</Fact>
            </FactList>
          </div>
        )}
      </SectionCard>
    </>
  );
}

export function Vault() {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: "Credentials", to: CREDENTIALS_ADDRESS }, { label: VAULT_HEADING }]}
        title={VAULT_HEADING}
        lede={VAULT_LEDE}
      />
      <Note>
        <Link to={CREDENTIALS_ADDRESS} className="text-acc-text underline-offset-4 hover:underline">
          {CREDENTIALS_LINK}
        </Link>
      </Note>
      <VaultBody />
    </div>
  );
}
