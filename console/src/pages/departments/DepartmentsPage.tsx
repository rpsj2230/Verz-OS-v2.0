/**
 * The Departments and teams list, on the shared page kit: every department this reader may see,
 * with its lead and its teams, and the people in no recorded department under it.
 *
 * **No headcount.** Every list here is narrowed to the reader, so a number of people beside a
 * department would say how many they were not shown; the API's own sentence says so and the page
 * draws names, never figures. A department with nobody the reader may see reads like an empty one.
 *
 * **Created, renamed and retired from here, each presentation only** (M27.11.1). The API says whether
 * this reader may create and retire departments (`may_found`) and rename each one (`shapeable`), and
 * every route asks its own question whatever was drawn. A short name says its form before submit; a
 * rename and a retirement ask first; a department under live grants is refused in the API's one
 * sentence (M27.15.22). A department created here is grantable at once: its scope is created with it,
 * and the grant form's scopes are the Scopes screen's live answer.
 *
 * Removed from the old screen: the principal id printed beside every person, the Scopes card (scopes
 * are created, renamed and retired on the Scopes tab of Roles and permissions, and listed on each
 * department's page), the four paragraphs about who may change what, and the crumb spelled as text.
 *
 * **The departments a staff source names are offered above the list** (M27.7.4, since 2026-09-29), to
 * the same readers who may create a department, as one confirmed act: see `SourceDepartments.tsx`.
 *
 * Task ids: M27.11.1, M27.15.22, M27.16.1, M27.7.4
 */

import { Building2, MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useListing } from "../../components/useListing";
import { Chip, ListPage, SectionCard, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { personAddress } from "../people/peopleQuery";
import {
  DEPARTMENTS_API_PATH,
  DEPARTMENT_FILTERS,
  DEPARTMENT_SORTS,
  departmentAddress,
  readOrganisation,
  type DepartmentRow,
} from "./departmentsQuery";
import { SourceDepartments } from "./SourceDepartments";
import { NewDepartmentDrawer, RenameDrawer, RetireDialog, type Target } from "./StructureDrawers";

export const DEPARTMENTS_HEADING = "Departments and teams";
export const DEPARTMENTS_LEDE = "Every department you may see, who leads it and the teams inside it. Open one for its people and scopes.";
export const LOADING_DEPARTMENTS = "Loading departments.";
export const NO_DEPARTMENTS = "No departments to show";
export const NO_DEPARTMENTS_DESCRIPTION =
  "A department appears here once somebody who governs the whole company creates it here, one at a time or from the names your staff source uses.";
export const DEPARTMENTS_LIST_LABEL = "Departments you may see";
export const FILTERS_LABEL = "Narrow the departments";
export const SEARCH_HINT = "Search departments, teams or people";
export const NEW_DEPARTMENT = "New department";
export const UNPLACED_HEADING = "Not in a recorded department";

function RowMenu({
  row,
  mayFound,
  onRename,
  onRetire,
}: {
  readonly row: DepartmentRow;
  readonly mayFound: boolean;
  readonly onRename: (target: Target) => void;
  readonly onRetire: (target: Target) => void;
}) {
  const target: Target = { kind: "department", slug: row.slug, name: row.name };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.name}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuItem asChild>
          <Link to={departmentAddress(row.slug)}>Open</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to={departmentAddress(row.slug, "teams")}>Teams</Link>
        </DropdownMenuItem>
        {row.shapeable === true ? (
          <DropdownMenuItem
            onSelect={() => {
              onRename(target);
            }}
          >
            Rename
          </DropdownMenuItem>
        ) : null}
        {mayFound ? (
          <DropdownMenuItem
            onSelect={() => {
              onRetire(target);
            }}
          >
            Retire
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function DepartmentsPage() {
  const navigate = useNavigate();
  const [version, setVersion] = useState(0);
  const listing = useListing<DepartmentRow>(DEPARTMENTS_API_PATH, { choices: DEPARTMENT_FILTERS, version });
  const organisation = useMemo(() => readOrganisation(listing.body), [listing.body]);
  const rows = organisation.departments;
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<Target | null>(null);
  const [retiring, setRetiring] = useState<Target | null>(null);
  const written = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);

  const columns: readonly EntityColumn<DepartmentRow>[] = [
    {
      id: "name",
      header: "Department",
      hideable: false,
      cell: (row) => (
        <Link to={departmentAddress(row.slug)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
          {row.name}
        </Link>
      ),
      text: (row) => row.name,
    },
    {
      id: "lead",
      header: "Lead",
      cell: (row) =>
        row.lead === null || row.lead === undefined ? null : (
          <Link to={personAddress(row.lead.principal_id)} className="text-ink underline-offset-4 hover:underline">
            {row.lead.display_name}
          </Link>
        ),
      text: (row) => row.lead?.display_name ?? "",
    },
    {
      id: "teams",
      header: "Teams",
      cell: (row) =>
        row.teams.length === 0 ? null : (
          <span className="flex flex-wrap gap-1">
            {row.teams.map((one) => (
              <Chip key={one.slug}>{one.name}</Chip>
            ))}
          </span>
        ),
      text: (row) => row.teams.map((one) => one.name).join("; "),
    },
    {
      id: "slug",
      header: "Short name",
      hidden: true,
      cell: (row) => <code className="font-mono text-[12px]">{row.slug}</code>,
      text: (row) => row.slug,
    },
  ];

  return (
    <>
      <ListPage
        crumbs={[{ label: DEPARTMENTS_HEADING }]}
        title={DEPARTMENTS_HEADING}
        lede={DEPARTMENTS_LEDE}
        primary={
          organisation.mayFound ? (
            <Button
              className="min-h-11 sm:min-h-9"
              onClick={() => {
                setCreating(true);
              }}
            >
              <Plus aria-hidden /> {NEW_DEPARTMENT}
            </Button>
          ) : undefined
        }
        notice={organisation.mayFound ? <SourceDepartments version={version} onWritten={written} /> : undefined}
        listing={listing}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={DEPARTMENT_FILTERS}
        sorts={DEPARTMENT_SORTS}
        searchHint={SEARCH_HINT}
        caption={DEPARTMENTS_LIST_LABEL}
        columns={columns}
        rowId={(row) => row.slug}
        rowLabel={(row) => row.name}
        rowActions={(row) => (
          <RowMenu row={row} mayFound={organisation.mayFound} onRename={setRenaming} onRetire={setRetiring} />
        )}
        exportName="departments"
        loading={LOADING_DEPARTMENTS}
        emptyTitle={NO_DEPARTMENTS}
        emptyDescription={NO_DEPARTMENTS_DESCRIPTION}
        emptyIcon={<Building2 aria-hidden />}
        footer={
          organisation.unplaced.length === 0 ? undefined : (
            <SectionCard title={UNPLACED_HEADING} lede="People you may see whose department is none, or one no recorded department carries.">
              <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-[13px]">
                {organisation.unplaced.map((one) => (
                  <li key={one.principal_id}>
                    <Link to={personAddress(one.principal_id)} className="text-ink underline-offset-4 hover:underline">
                      {one.display_name}
                    </Link>
                  </li>
                ))}
              </ul>
            </SectionCard>
          )
        }
      />
      <NewDepartmentDrawer
        open={creating}
        onOpenChange={setCreating}
        onWritten={(slug) => {
          written();
          void navigate(departmentAddress(slug));
        }}
      />
      <RetireDialog
        target={retiring}
        consequence={organisation.retiringDepartment}
        onClose={() => {
          setRetiring(null);
        }}
        onWritten={written}
      />
      <RenameDrawer
        target={renaming}
        onOpenChange={(open) => {
          if (!open) {
            setRenaming(null);
          }
        }}
        onWritten={written}
      />
    </>
  );
}
