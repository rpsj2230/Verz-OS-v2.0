/**
 * The People list, on the shared page kit: every person in the directory this reader may be shown,
 * with their department, whether they can sign in, whether their last sign-in carried a second
 * factor, and the packs they hold.
 *
 * **Every person, grant or none.** The list this replaces was built from grant rows, so somebody who
 * held nothing was on no list and could not be granted anything. `GET /govern/directory` is every
 * person `brain.console.organisation.nameable` lets this reader see, and a row opens the person's
 * page, where they are granted.
 *
 * **Nothing here decides who is listed, and nothing counts.** The API narrows before it pages, and
 * the page draws what arrived in the order it arrived. A second factor, a last sign-in and packs are
 * drawn only when sent; an empty cell reads the same whether nothing was recorded or this reader may
 * not be told, because a word there would say which.
 *
 * **One bulk act, and it is the route's.** Selecting people offers "Grant to selected", which is one
 * grant written for each or for none (`/govern/grants/several`), confirmed with everybody named.
 * Export reads and changes nothing.
 *
 * **Added by hand only where no staff source brings people in** (M27.15.19). The API says whether
 * this reader may add somebody here (`may_add`); a person added holds nothing, and is then linked
 * to a sign-in, placed and granted like anybody else.
 *
 * **What to tell somebody whose account the staff sync made** is under the list when a staff list
 * is read, with a way to copy it (`AccountReady`): nobody is sent anything (needs-rupash 115).
 *
 * **The data steward card stays under the list**: a grant of a data read begins with the steward,
 * and an install set up before the setup wizard named one names them here.
 *
 * Removed from the old screen: principal ids in the list and the page heading, the "subjects" and
 * "principal:" vocabulary, the paragraph explaining how the page resolves an address, and the
 * duplicate grant forms under the list (they are on the person's Grants view).
 *
 * Task ids: M27.11.2, M27.15.19, M27.16.1, M1.6.16
 */

import { MoreHorizontal, UserPlus, Users } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useListing } from "../../components/useListing";
import { DataStewardCard } from "../../components/DataStewardCard";
import { Chip, ListPage, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { dayWords } from "../access/formParts";
import { AccountReady } from "./AccountReady";
import { AddPersonDrawer, SeveralDrawer } from "./GrantDrawers";
import { SecondFactorPill, StaffStatusPill, StandingPill } from "./pills";
import {
  DIRECTORY_API_PATH,
  PEOPLE_FILTERS,
  PEOPLE_SORTS,
  personAddress,
  readDirectoryFacts,
  readPeople,
  type PersonRow,
  EMPLOYMENT_TYPE_WORDS,
  STAFF_STATUS_WORDS,
} from "./peopleQuery";

export const PEOPLE_HEADING = "People";
export const PEOPLE_LEDE = "Everybody in the directory you may see. Open a person to see and change what they hold.";
export const LOADING_PEOPLE = "Loading people.";
export const NO_PEOPLE = "No people to show";
export const NO_PEOPLE_DESCRIPTION =
  "People arrive from the staff source or the identity provider when they are added there, and on an install with no staff source an administrator adds them here.";
export const PEOPLE_LIST_LABEL = "People you may see";
export const FILTERS_LABEL = "Narrow the people";
export const SEARCH_HINT = "Search by name or department";

export const ADD_PERSON_LABEL = "Add person";
export const GRANT_SELECTED = "Grant to selected";

export const NAME_COLUMN = "Name";
export const DEPARTMENT_COLUMN = "Department";
export const STANDING_COLUMN = "Standing";
export const STAFF_STATUS_COLUMN = "On the staff list";
export const EMPLOYMENT_TYPE_COLUMN = "Employment type";
export const SECOND_FACTOR_COLUMN = "Second factor";
export const PACKS_COLUMN = "Packs";
export const LAST_SIGN_IN_COLUMN = "Last sign-in";

function departmentOf(row: PersonRow): string | undefined {
  return row.departmentName ?? row.department;
}

function RowMenu({ row }: { readonly row: PersonRow }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.displayName}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem asChild>
          <Link to={personAddress(row.principalId)}>Open</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to={personAddress(row.principalId, "grants")}>Grants</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to={personAddress(row.principalId, "access")}>What they can reach</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function PeoplePage() {
  const navigate = useNavigate();
  const [version, setVersion] = useState(0);
  const listing = useListing<PersonRow>(DIRECTORY_API_PATH, { choices: PEOPLE_FILTERS, version });
  const rows = useMemo(() => readPeople(listing.body), [listing.body]);
  const facts = useMemo(() => readDirectoryFacts(listing.body), [listing.body]);
  const [adding, setAdding] = useState(false);
  const [granting, setGranting] = useState<readonly PersonRow[] | null>(null);
  const [cleared, setCleared] = useState<(() => void) | null>(null);

  const written = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);

  // The department names the rows carry, for the department filter's words.
  const departments = useMemo(() => {
    const found = new Map<string, string>();
    for (const row of rows) {
      if (row.department !== undefined) {
        found.set(row.department, row.departmentName ?? row.department);
      }
    }
    return [...found].map(([slug, name]) => ({ slug, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [rows]);

  // The department filter sends a short name and shows the name the rows carry for it.
  const choices = useMemo(
    () => PEOPLE_FILTERS.map((one) => (one.column === "department" ? { ...one, describe: (value: string) => departments.find((d) => d.slug === value)?.name ?? value } : one)),
    [departments],
  );

  const columns: readonly EntityColumn<PersonRow>[] = [
    {
      id: "name",
      header: NAME_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[11rem] flex-col">
          <Link to={personAddress(row.principalId)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
            {row.displayName}
          </Link>
          {row.employment === undefined || row.employment === "staff" ? null : (
            <span className="text-[12px] text-dim capitalize">{row.employment}</span>
          )}
        </span>
      ),
      text: (row) => row.displayName,
    },
    {
      id: "department",
      header: DEPARTMENT_COLUMN,
      cell: (row) => departmentOf(row) ?? null,
      text: (row) => departmentOf(row) ?? "",
    },
    {
      id: "standing",
      header: STANDING_COLUMN,
      cell: (row) => <StandingPill standing={row.standing} />,
      text: (row) => (row.standing === "disabled" ? "Disabled" : "Live"),
    },
    {
      id: "staff_status",
      header: STAFF_STATUS_COLUMN,
      cell: (row) => (row.staffStatus === undefined ? null : <StaffStatusPill status={row.staffStatus} />),
      text: (row) => (row.staffStatus === undefined ? "" : (STAFF_STATUS_WORDS[row.staffStatus] ?? row.staffStatus)),
    },
    {
      id: "employment_type",
      header: EMPLOYMENT_TYPE_COLUMN,
      cell: (row) => (row.employmentType === undefined ? null : (EMPLOYMENT_TYPE_WORDS[row.employmentType] ?? row.employmentType)),
      text: (row) => (row.employmentType === undefined ? "" : (EMPLOYMENT_TYPE_WORDS[row.employmentType] ?? row.employmentType)),
    },
    {
      id: "second_factor",
      header: SECOND_FACTOR_COLUMN,
      cell: (row) => (row.secondFactor === undefined ? null : <SecondFactorPill seen={row.secondFactor} />),
      text: (row) => (row.secondFactor === undefined ? "" : row.secondFactor ? "Seen" : "Not seen"),
    },
    {
      id: "packs",
      header: PACKS_COLUMN,
      cell: (row) =>
        row.packs.length === 0 ? null : (
          <span className="flex flex-wrap gap-1">
            {row.packs.map((one) => (
              <Chip key={one} mono>
                {one}
              </Chip>
            ))}
          </span>
        ),
      text: (row) => row.packs.join("; "),
    },
    {
      id: "last_sign_in",
      header: LAST_SIGN_IN_COLUMN,
      hidden: true,
      cell: (row) => (row.lastSignedInAt === undefined ? null : dayWords(row.lastSignedInAt)),
      text: (row) => row.lastSignedInAt ?? "",
    },
  ];

  return (
    <>
      <ListPage
        crumbs={[{ label: PEOPLE_HEADING }]}
        title={PEOPLE_HEADING}
        lede={PEOPLE_LEDE}
        primary={
          facts.mayAdd ? (
            <Button
              className="min-h-11 sm:min-h-9"
              onClick={() => {
                setAdding(true);
              }}
            >
              <UserPlus aria-hidden /> {ADD_PERSON_LABEL}
            </Button>
          ) : undefined
        }
        listing={listing}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={choices}
        sorts={PEOPLE_SORTS}
        searchHint={SEARCH_HINT}
        caption={PEOPLE_LIST_LABEL}
        columns={columns}
        rowId={(row) => row.principalId}
        rowLabel={(row) => row.displayName}
        rowActions={(row) => <RowMenu row={row} />}
        bulkActions={
          facts.editable
            ? (selected, clear) => (
                <Button
                  size="sm"
                  onClick={() => {
                    setGranting(selected);
                    setCleared(() => clear);
                  }}
                >
                  {GRANT_SELECTED}
                </Button>
              )
            : undefined
        }
        exportName="people"
        loading={LOADING_PEOPLE}
        emptyTitle={NO_PEOPLE}
        emptyDescription={NO_PEOPLE_DESCRIPTION}
        emptyIcon={<Users aria-hidden />}
        footer={
          <>
            {facts.accountReady === undefined ? null : <AccountReady sentence={facts.accountReady} />}
            <DataStewardCard />
          </>
        }
      />
      <SeveralDrawer
        open={granting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setGranting(null);
          }
        }}
        chosen={granting ?? []}
        onWritten={() => {
          cleared?.();
          written();
        }}
      />
      <AddPersonDrawer
        open={adding}
        onOpenChange={setAdding}
        adding={facts.adding}
        onWritten={(principalId) => {
          written();
          if (principalId !== null) {
            void navigate(personAddress(principalId));
          }
        }}
      />
    </>
  );
}
