/**
 * The Credentials list, built on the shared page kit: every secret the install declares a vault slot
 * for, with what it belongs to, whether a value is held, when it was last set, and whether an
 * environment variable outranks it, under the vault's own state.
 *
 * **One list for five kinds.** A model provider's key, the mail relay's password, the object store's
 * key pair, each connected source's key and each channel's secret, in that order, from
 * `GET /api/v1/credentials` (`brain.credential_routes`). Until this page, each lived on a different
 * screen or on none, and "which secrets does this install hold" had no answer short of a shell.
 *
 * **Nothing here ever holds a value.** The rows say held, when and by what; a value is written on a
 * slot's own page through a field that keeps it out of React (`SetValueForm.tsx`), and no answer
 * this page reads has a field that could carry one.
 *
 * **Names, not paths.** A row is its holder's name and its kind; the vault path is how the system
 * names the slot and is on the slot's page under Advanced. The old Secrets vault screen drew both
 * slot tables with their paths as the first column, and duplicated the seal on a second card.
 *
 * Task ids: M27.11.10, M27.15.50, M27.16.1
 */

import { KeyRound, MoreHorizontal } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { ListPage, NOT_RECORDED, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import {
  CREDENTIALS_API_PATH,
  credentialAddress,
  kindWords,
  readCredentialRows,
  readVaultOverview,
  stateWords,
  whenWords,
  type CredentialRow,
} from "./credentialRows";
import { OutrankedPill, StatePill, VaultCard } from "./parts";

export const CREDENTIALS_HEADING = "Credentials";
export const CREDENTIALS_LEDE =
  "Every secret this install keeps in its vault, and when each was last set. A value is written here and never shown again.";
export const LOADING_CREDENTIALS = "Loading the credentials.";
export const NO_CREDENTIALS = "No credentials to show";
export const NO_CREDENTIALS_DESCRIPTION =
  "A slot appears here for every model provider, source and channel this release declares.";
export const CREDENTIALS_LIST_LABEL = "Credentials";
export const FILTERS_LABEL = "Narrow the credentials";
export const SEARCH_HINT = "Search credentials";

export const HOLDER_COLUMN = "Belongs to";
export const KIND_COLUMN = "Kind";
export const STATE_COLUMN = "Value";
export const SET_COLUMN = "Last set";
export const OUTRANKED_COLUMN = "Environment";
export const SET_OR_REPLACE = "Set or replace";
export const OPEN = "Open";

/** Said in the Environment column when nothing outranks the slot. */
export const NOT_OUTRANKED = "Not set there";

export const CREDENTIAL_FILTERS: readonly FilterChoice<CredentialRow>[] = [
  { column: "kind", label: KIND_COLUMN, everything: "Any kind", read: (row) => row.kind, describe: kindWords },
  { column: "state", label: STATE_COLUMN, everything: "Held or not", read: (row) => row.state, describe: stateWords },
];

export const CREDENTIAL_SORTS: readonly SortChoice[] = [
  { value: "", label: "Kind" },
  { value: "holder", label: "Name" },
  { value: "-set_at", label: "Last set" },
];

function RowMenu({ row }: { readonly row: CredentialRow }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.holder}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuItem asChild>
          <Link to={credentialAddress(row.slot)}>{OPEN}</Link>
        </DropdownMenuItem>
        {row.writable ? (
          <DropdownMenuItem asChild>
            <Link to={`${credentialAddress(row.slot)}/profile`}>{SET_OR_REPLACE}</Link>
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem disabled className="flex-col items-start gap-0.5">
            <span>{SET_OR_REPLACE}</span>
            <span className="text-[11px] leading-snug text-dim">{row.writeTold}</span>
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function CredentialsPage() {
  const listing = useListing<CredentialRow>(CREDENTIALS_API_PATH, { choices: CREDENTIAL_FILTERS });
  const rows = useMemo(() => readCredentialRows(listing.body), [listing.body]);
  const vault = useMemo(() => readVaultOverview(listing.body), [listing.body]);

  const columns: readonly EntityColumn<CredentialRow>[] = [
    {
      id: "holder",
      header: HOLDER_COLUMN,
      hideable: false,
      cell: (row) => (
        <Link
          to={credentialAddress(row.slot)}
          className="min-w-[10rem] font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline"
        >
          {row.holder}
        </Link>
      ),
      text: (row) => row.holder,
    },
    {
      id: "kind",
      header: KIND_COLUMN,
      cell: (row) => <span className="text-[12.5px] text-body">{kindWords(row.kind)}</span>,
      text: (row) => kindWords(row.kind),
    },
    {
      id: "state",
      header: STATE_COLUMN,
      cell: (row) => <StatePill state={row.state} />,
      text: (row) => stateWords(row.state),
    },
    {
      id: "set_at",
      header: SET_COLUMN,
      cell: (row) =>
        row.setAt === undefined ? (
          <span className="text-[12px] text-dim">{row.state === "held" ? NOT_RECORDED : "-"}</span>
        ) : (
          <span className="font-mono text-[12px] text-ink tabular-nums">{whenWords(row.setAt)}</span>
        ),
      text: (row) => whenWords(row.setAt) ?? "",
    },
    {
      id: "outranked",
      header: OUTRANKED_COLUMN,
      cell: (row) =>
        row.outrankedBy === undefined ? (
          row.kind === "provider" ? <span className="text-[12px] text-dim">{NOT_OUTRANKED}</span> : null
        ) : (
          <OutrankedPill variable={row.outrankedBy} />
        ),
      text: (row) => row.outrankedBy ?? "",
    },
  ];

  return (
    <ListPage
      crumbs={[{ label: CREDENTIALS_HEADING }]}
      title={CREDENTIALS_HEADING}
      lede={CREDENTIALS_LEDE}
      notice={vault === null ? undefined : <VaultCard vault={vault} />}
      listing={listing}
      rows={rows}
      filtersLabel={FILTERS_LABEL}
      choices={CREDENTIAL_FILTERS}
      sorts={CREDENTIAL_SORTS}
      searchHint={SEARCH_HINT}
      caption={CREDENTIALS_LIST_LABEL}
      columns={columns}
      rowId={(row) => row.slot}
      rowLabel={(row) => row.holder}
      rowActions={(row) => <RowMenu row={row} />}
      exportName="credentials"
      loading={LOADING_CREDENTIALS}
      emptyTitle={NO_CREDENTIALS}
      emptyDescription={NO_CREDENTIALS_DESCRIPTION}
      emptyIcon={<KeyRound aria-hidden />}
    />
  );
}
