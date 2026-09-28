/**
 * The Scopes tab of Roles and permissions, on the shared page kit: every named boundary a grant can
 * carry that this reader may see, and the acts that create, rename and retire one (M27.11.1).
 *
 * **A scope is shown whole or not at all, predicate included**, in words (`scopeText`), for
 * `govern_surfaces.A_SCOPE_NAME_IS_THE_PREDICATE_SPELLED_IN_WORDS`' reason; the short name, which is
 * how grants name it, is a column the reader may show.
 *
 * **Renaming changes the name people read and never the short name** (M27.11.1 could not close
 * without it). The route takes the name the page showed with the new one and refuses in a sentence if
 * somebody changed it since; it is recorded in the audit trail as a rename. Retiring asks first, keeps
 * every grant over the scope, and is not offered for a department's own scope or the company-wide one,
 * which the route refuses in its own sentence whatever was drawn.
 *
 * **Each control is presentation only**, from `may_draw_scopes` on the Departments route, and each
 * route asks the scope authority over the scope's own predicate. Moved here from the Departments
 * screen, whose Scopes card it replaces.
 *
 * Task ids: M27.11.1, M27.7.4, M27.16.1
 */

import { MoreHorizontal, Plus, ShieldCheck } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useResource } from "../../api/useResource";
import { useListing } from "../../components/useListing";
import { ListPage, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { SCOPE_FILTERS, SCOPE_SORTS, SCOPES_API_PATH, type ScopeRowView } from "../governQuery";
import { scopeLines } from "../scopeText";
import { departmentChoicesApiPath, offersScopeRetirement, readOrganisation } from "../departments/departmentsQuery";
import { NewScopeDrawer, RenameDrawer, RetireDialog, type Target } from "../departments/StructureDrawers";
import { ROLES_HEADING } from "./RolesPage";

export const SCOPES_CRUMB = "Scopes";
export const SCOPES_LEDE = "The named boundaries a grant can carry: a department, a set of them, a team, or the whole company.";
export const NO_SCOPES = "No scopes to show";
export const NO_SCOPES_DESCRIPTION =
  "A department's own scope appears when the department is created, and a named scope when somebody who holds the scope authority creates one here.";
export const NEW_SCOPE = "New scope";

function words(row: ScopeRowView): string {
  const lines = scopeLines(row.scope);
  return lines.length === 0 ? "Everything in the company" : lines.join("; ");
}

function targetOf(row: ScopeRowView): Target {
  return { kind: "scope", slug: row.slug, name: row.label, scope: row.scope };
}

export function ScopesPage() {
  const [version, setVersion] = useState(0);
  const listing = useListing<ScopeRowView>(SCOPES_API_PATH, { choices: SCOPE_FILTERS, version });
  const rows = useMemo(() => {
    const items = (listing.body as { items?: unknown } | null)?.items;
    return Array.isArray(items) ? (items as ScopeRowView[]).filter((one) => typeof one.slug === "string" && typeof one.label === "string") : [];
  }, [listing.body]);
  // Whether this reader holds the scope authority anywhere is the Departments route's flag; the
  // routes ask it properly about each scope whatever this drew.
  const organisation = useResource<unknown>(departmentChoicesApiPath());
  const facts = readOrganisation(organisation.data);
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<Target | null>(null);
  const [retiring, setRetiring] = useState<Target | null>(null);
  const written = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);

  const columns: readonly EntityColumn<ScopeRowView>[] = [
    { id: "label", header: "Scope", hideable: false, cell: (row) => <span className="font-medium text-ink">{row.label}</span>, text: (row) => row.label },
    { id: "reaches", header: "Reaches", cell: (row) => <span className="[overflow-wrap:anywhere]">{words(row)}</span>, text: words },
    {
      id: "kind",
      header: "Kind",
      cell: (row) => (row.is_department ? "A department's own" : "Named"),
      text: (row) => (row.is_department ? "A department's own" : "Named"),
    },
    { id: "slug", header: "Short name", hidden: true, cell: (row) => <code className="font-mono text-[12px]">{row.slug}</code>, text: (row) => row.slug },
  ];

  return (
    <>
      <ListPage
        crumbs={[{ label: ROLES_HEADING }, { label: SCOPES_CRUMB }]}
        title={SCOPES_CRUMB}
        lede={SCOPES_LEDE}
        primary={
          facts.mayDrawScopes ? (
            <Button
              className="min-h-11 sm:min-h-9"
              onClick={() => {
                setCreating(true);
              }}
            >
              <Plus aria-hidden /> {NEW_SCOPE}
            </Button>
          ) : undefined
        }
        listing={listing}
        rows={rows}
        filtersLabel="Narrow the scopes"
        choices={SCOPE_FILTERS}
        sorts={SCOPE_SORTS}
        searchHint="Search scopes"
        caption="Scopes you may see"
        columns={columns}
        rowId={(row) => row.slug}
        rowLabel={(row) => row.label}
        rowActions={
          facts.mayDrawScopes
            ? (row) => (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.label}`}>
                      <MoreHorizontal aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-44">
                    <DropdownMenuItem
                      onSelect={() => {
                        setRenaming(targetOf(row));
                      }}
                    >
                      Rename
                    </DropdownMenuItem>
                    {offersScopeRetirement({ slug: row.slug, label: row.label, isDepartment: row.is_department, scope: row.scope }) ? (
                      <DropdownMenuItem
                        onSelect={() => {
                          setRetiring(targetOf(row));
                        }}
                      >
                        Retire
                      </DropdownMenuItem>
                    ) : null}
                  </DropdownMenuContent>
                </DropdownMenu>
              )
            : undefined
        }
        exportName="scopes"
        loading="Loading scopes."
        emptyTitle={NO_SCOPES}
        emptyDescription={NO_SCOPES_DESCRIPTION}
        emptyIcon={<ShieldCheck aria-hidden />}
      />
      <NewScopeDrawer open={creating} onOpenChange={setCreating} onWritten={written} />
      <RenameDrawer
        target={renaming}
        onOpenChange={(open) => {
          if (!open) {
            setRenaming(null);
          }
        }}
        onWritten={written}
      />
      <RetireDialog
        target={retiring}
        consequence={facts.retiringScope}
        onClose={() => {
          setRetiring(null);
        }}
        onWritten={written}
      />
    </>
  );
}
