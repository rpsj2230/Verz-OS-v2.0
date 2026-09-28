/**
 * Service accounts on the shared page kit: every integration the signed-in person has registered,
 * each with its capabilities, its live keys and when it stops working.
 *
 * **Every account on this page is the reader's own.** The route answers the caller's accounts and
 * no one else's, and nothing sent from here could name another owner, so the list has no owner
 * column and no filter by person. See `serviceAccountsQuery.AN_ACCOUNT_IS_ALWAYS_THE_CALLERS_OWN`.
 *
 * **Names, not identifiers, in the table.** An account is named by its label and its id sits under
 * it in small type, because an integration's configuration quotes the id; a key's handle is on the
 * account's own page. The two paragraphs the API sends about reach and ownership are one sentence
 * in the header and one in the register drawer, not two panels under the list.
 *
 * **What the old page drew that this one does not**: the second table of every live key across
 * every account (keys are on each account's page), the inline register and issue forms (now
 * drawers, each saying what its fields accept), and "this list came back full" (the list pages
 * with Show more).
 *
 * Task ids: M27.11.5, M27.15.26, M27.16.1
 */

import { KeyRound, MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { Chip, ListPage, Note, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { accountName, readAccounts, SERVICE_ACCOUNTS_API_PATH, SERVICE_ACCOUNTS_LABEL, when, type AccountRow } from "../serviceAccountsQuery";
import { EndingDialog, IssueKeyDrawer, RegisterDrawer, type Ending } from "./AccountActs";
import { ACT_LABELS, NOT_HELD_MARK } from "./serviceAccountActions";

export const ACCOUNTS_LEDE =
  "Integrations that call this system with a key. Each acts at your reach, narrowed to what it lists, and stops when you lose that reach.";
export const READING_ACCOUNTS = "Reading your service accounts.";
export const NO_ACCOUNTS = "No service accounts yet";
export const NO_ACCOUNTS_DESCRIPTION = "An account appears here once you register one for an integration.";
export const ACCOUNTS_LIST_LABEL = "Your service accounts";
export const FILTERS_LABEL = "Narrow the accounts";
export const SEARCH_HINT = "Search by name or ID";

export const ACCOUNT_COLUMN = "Account";
export const CAPABILITIES_COLUMN = "Capabilities";
export const KEYS_COLUMN = "Live keys";
export const ENDS_COLUMN = "Stops working";
export const CREATED_COLUMN = "Registered";

/** Where one account's page is. */
export function accountAddress(clientId: string): string {
  return `/service-accounts/${encodeURIComponent(clientId)}`;
}

/** The rows out of the listing's body: an account is drawn only with its id, once. */
export function readAccountRows(payload: unknown): readonly AccountRow[] {
  const body = readAccounts(payload);
  if (body === null) {
    return [];
  }
  const seen = new Set<string>();
  return body.items.filter((one) => {
    if (typeof one.client_id !== "string" || one.client_id === "" || seen.has(one.client_id)) {
      return false;
    }
    seen.add(one.client_id);
    return true;
  });
}

/** The filter the route declares, over capabilities on rows drawn. */
export const ACCOUNT_FILTERS: readonly FilterChoice<AccountRow>[] = [
  { column: "ceiling", label: "Capability", everything: "Every capability", read: (row) => row.ceiling },
];

/** The orders the route declares. Empty is its own, newest first. */
export const ACCOUNT_SORTS: readonly SortChoice[] = [
  { value: "", label: "Newest first" },
  { value: "label", label: "Name" },
  { value: "client_id", label: "Account ID" },
  { value: "lapses_at", label: "Soonest to stop working" },
];

type Open = { readonly act: "register" } | { readonly act: "issue"; readonly account: AccountRow };

function RowMenu({
  row,
  onIssue,
  onRetire,
}: {
  readonly row: AccountRow;
  readonly onIssue: (row: AccountRow) => void;
  readonly onRetire: (row: AccountRow) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${accountName(row)}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem asChild>
          <Link to={accountAddress(row.client_id)}>{ACT_LABELS.open}</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            onIssue(row);
          }}
        >
          {ACT_LABELS.issue}
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => {
            onRetire(row);
          }}
        >
          {ACT_LABELS.retire}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ServiceAccountsPage() {
  const navigate = useNavigate();
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState<Open | null>(null);
  const [ending, setEnding] = useState<Ending | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const listing = useListing<AccountRow>(SERVICE_ACCOUNTS_API_PATH, { choices: ACCOUNT_FILTERS, version });
  const rows = useMemo(() => readAccountRows(listing.body), [listing.body]);
  const again = useCallback((sentence: string | null) => {
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);

  const columns: readonly EntityColumn<AccountRow>[] = [
    {
      id: "name",
      header: ACCOUNT_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[12rem] flex-col">
          <Link
            to={accountAddress(row.client_id)}
            className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline"
          >
            {accountName(row)}
          </Link>
          {row.label.trim() === "" ? null : <span className="font-mono text-[11.5px] text-dim">{row.client_id}</span>}
        </span>
      ),
      text: (row) => accountName(row),
    },
    {
      id: "ceiling",
      header: CAPABILITIES_COLUMN,
      cell: (row) => (
        <span className="flex flex-wrap gap-1">
          {row.ceiling.map((one) => (
            <Chip key={one} mono>
              {row.not_held_now.includes(one) ? `${one} ${NOT_HELD_MARK}` : one}
            </Chip>
          ))}
        </span>
      ),
      text: (row) => row.ceiling.join("; "),
    },
    {
      id: "keys",
      header: KEYS_COLUMN,
      align: "end",
      cell: (row) => <span className="font-mono text-[12px] tabular-nums">{String(row.keys.length)}</span>,
      text: (row) => String(row.keys.length),
    },
    {
      id: "ends",
      header: ENDS_COLUMN,
      cell: (row) => <span className="font-mono text-[12px]">{when(row.lapses_at)}</span>,
      text: (row) => when(row.lapses_at),
    },
    {
      id: "created",
      header: CREATED_COLUMN,
      hidden: true,
      cell: (row) => <span className="font-mono text-[12px]">{when(row.created_at)}</span>,
      text: (row) => when(row.created_at),
    },
  ];

  const register = (
    <Button
      className="min-h-11 sm:min-h-8"
      size="sm"
      onClick={() => {
        setOpen({ act: "register" });
      }}
    >
      <Plus aria-hidden />
      {ACT_LABELS.register}
    </Button>
  );

  return (
    <ListPage
      crumbs={[{ label: SERVICE_ACCOUNTS_LABEL }]}
      title={SERVICE_ACCOUNTS_LABEL}
      lede={ACCOUNTS_LEDE}
      primary={register}
      notice={
        <>
          {told === null ? null : (
            <div role="status">
              <Note kind="works">{told}</Note>
            </div>
          )}
          {open?.act === "register" ? (
            <RegisterDrawer
              onClose={() => {
                setOpen(null);
              }}
              onDone={(clientId, sentence) => {
                setOpen(null);
                navigate(accountAddress(clientId), { state: { told: sentence } });
              }}
            />
          ) : null}
          {open?.act === "issue" ? (
            <IssueKeyDrawer
              account={open.account}
              onClose={() => {
                setOpen(null);
              }}
              onDone={() => {
                setOpen(null);
                again(null);
              }}
            />
          ) : null}
          <EndingDialog
            ending={ending}
            onClose={() => {
              setEnding(null);
            }}
            onDone={(_, sentence) => {
              setEnding(null);
              again(sentence);
            }}
          />
        </>
      }
      listing={listing}
      rows={rows}
      filtersLabel={FILTERS_LABEL}
      choices={ACCOUNT_FILTERS}
      sorts={ACCOUNT_SORTS}
      searchHint={SEARCH_HINT}
      caption={ACCOUNTS_LIST_LABEL}
      columns={columns}
      rowId={(row) => row.client_id}
      rowLabel={(row) => accountName(row)}
      rowActions={(row) => (
        <RowMenu
          row={row}
          onIssue={(account) => {
            setTold(null);
            setOpen({ act: "issue", account });
          }}
          onRetire={(account) => {
            setTold(null);
            setEnding({ kind: "retire", account });
          }}
        />
      )}
      exportName="service-accounts"
      loading={READING_ACCOUNTS}
      emptyTitle={NO_ACCOUNTS}
      emptyDescription={NO_ACCOUNTS_DESCRIPTION}
      emptyIcon={<KeyRound aria-hidden />}
      emptyAction={register}
    />
  );
}
