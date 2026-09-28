/**
 * One department's page on the shared kit: its name, lead and teams in the header, and three views at
 * addresses of their own: Overview (the lead and the people), Teams (each team and who is in it), and
 * Scopes (the scopes that name it).
 *
 * **The department is the list route's row for its short name**, asked with `filter=slug:<slug>`, so
 * the page shows exactly what the list would show this reader and nothing a second route decided. A
 * department this reader may not see and one that does not exist are the same empty answer, and the
 * page says one sentence for both.
 *
 * **Every act is the Departments route's own, confirmed where it replaces or ends something**:
 * rename and retire the department (the header), create, rename and retire a team and place people in
 * it or take them out (Teams), appoint or stand down the lead (Overview), and rename or retire a scope
 * that names it (Scopes). Each control is presentation only, from what the API said this reader may
 * do; each route asks its own question about the rows as they stand.
 *
 * **No figure of people.** The header counts teams, which are the department's structure and shown
 * whole; it never counts people, because the people listed are narrowed to the reader.
 *
 * Task ids: M27.11.1, M27.15.22, M27.16.1
 */

import { Building2, LayoutDashboard, Network, ShieldCheck, UserPlus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  DetailHeader,
  DetailPage,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  PageHeader,
  SectionCard,
  StatCard,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { scopeLines } from "../scopeText";
import { personAddress } from "../people/peopleQuery";
import { StandingPill } from "../people/pills";
import {
  DEPARTMENTS_ADDRESS,
  DEPARTMENT_VIEWS,
  DEPARTMENT_VIEW_LABELS,
  departmentAddress,
  departmentIn,
  offersScopeRetirement,
  oneDepartmentApiPath,
  peopleOf,
  readOrganisation,
  readScopes,
  scopesNamingApiPath,
  type DepartmentRow,
  type DepartmentView,
} from "./departmentsQuery";
import { DEPARTMENTS_HEADING } from "./DepartmentsPage";
import {
  AddMemberDrawer,
  NewScopeDrawer,
  NewTeamDrawer,
  PlacementControl,
  RenameDrawer,
  RetireControl,
  type Target,
} from "./StructureDrawers";

export const VIEWS_LABEL = "Department views";
export const LOADING_DEPARTMENT = "Loading this department.";
export const NO_SUCH_DEPARTMENT = "No department to show";
export const NO_SUCH_DEPARTMENT_DESCRIPTION = "There is no department you may see with this address. The list shows every department you may see.";

const VIEW_ICONS: Readonly<Record<DepartmentView, typeof LayoutDashboard>> = {
  overview: LayoutDashboard,
  teams: Network,
  scopes: ShieldCheck,
};

function Overview({
  department,
  mayOrganise,
  onWritten,
}: {
  readonly department: DepartmentRow;
  readonly mayOrganise: boolean;
  readonly onWritten: () => void;
}) {
  const people = peopleOf(department);
  const lead = department.lead ?? null;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title="Lead"
        lede="Who leads it, appointed by somebody else. A lead confers nothing."
        action={
          lead !== null && mayOrganise ? (
            <PlacementControl
              act={{ kind: "stand_down", department: department.slug, departmentName: department.name, person: lead.display_name }}
              label="Stand down"
              onWritten={onWritten}
            />
          ) : undefined
        }
      >
        {lead === null ? (
          <p className="m-0 text-[13px] text-dim">No lead you may see is recorded.</p>
        ) : (
          <Link to={personAddress(lead.principal_id)} className="text-[13px] font-medium text-ink underline-offset-4 hover:underline">
            {lead.display_name}
          </Link>
        )}
      </SectionCard>
      <SectionCard title="People" lede="Everybody in it you may see, in its teams or not.">
        {people.length === 0 ? (
          <p className="m-0 text-[13px] text-dim">Nobody you may see is listed in this department.</p>
        ) : (
          <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
            {people.map((one) => (
              <li key={one.principal_id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-[13px]">
                <span className="flex items-center gap-2">
                  <Link to={personAddress(one.principal_id)} className="text-ink underline-offset-4 hover:underline">
                    {one.display_name}
                  </Link>
                  {one.disabled ? <StandingPill standing="disabled" /> : null}
                </span>
                {mayOrganise && !one.disabled && lead?.principal_id !== one.principal_id ? (
                  <PlacementControl
                    act={{
                      kind: "appoint",
                      department: department.slug,
                      departmentName: department.name,
                      principalId: one.principal_id,
                      person: one.display_name,
                    }}
                    label="Make lead"
                    onWritten={onWritten}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
      <Advanced>
        <FactList>
          <Fact label="Short name">
            <code className="font-mono text-[12px]">{department.slug}</code>
          </Fact>
        </FactList>
      </Advanced>
    </div>
  );
}

function Teams({
  department,
  mayOrganise,
  retiringTeam,
  onWritten,
}: {
  readonly department: DepartmentRow;
  readonly mayOrganise: boolean;
  readonly retiringTeam: string;
  readonly onWritten: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<Target | null>(null);
  const [adding, setAdding] = useState<{ slug: string; name: string } | null>(null);
  const shapeable = department.shapeable === true;
  const everybody = peopleOf(department).filter((one) => !one.disabled);
  const addingTo = adding === null ? undefined : department.teams.find((one) => one.slug === adding.slug);
  const inTeam = new Set((addingTo?.members ?? []).map((one) => one.principal_id));

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title="Teams"
        lede="A team is where somebody sits. Placing somebody in one changes nobody's access."
        action={
          shapeable ? (
            <Button
              size="sm"
              onClick={() => {
                setCreating(true);
              }}
            >
              New team
            </Button>
          ) : undefined
        }
      >
        {department.teams.length === 0 ? (
          <EmptyState
            title="No teams"
            description="A team appears here once somebody who may shape this department creates one."
            icon={<Network aria-hidden />}
          />
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {department.teams.map((team) => (
              <li key={team.slug} className="rounded-md border border-line">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
                  <span className="text-[13.5px] font-medium text-ink">{team.name}</span>
                  <span className="flex flex-wrap items-center gap-1.5">
                    {mayOrganise ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setAdding({ slug: team.slug, name: team.name });
                        }}
                      >
                        <UserPlus aria-hidden /> Add
                      </Button>
                    ) : null}
                    {shapeable ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setRenaming({ kind: "team", department: department.slug, slug: team.slug, name: team.name });
                        }}
                      >
                        Rename
                      </Button>
                    ) : null}
                    {shapeable ? (
                      <RetireControl
                        target={{ kind: "team", department: department.slug, slug: team.slug, name: team.name }}
                        consequence={retiringTeam}
                        onWritten={onWritten}
                      />
                    ) : null}
                  </span>
                </div>
                {(team.members ?? []).length === 0 ? (
                  <p className="m-0 px-3 py-2 text-[13px] text-dim">Nobody you may see is in this team.</p>
                ) : (
                  <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
                    {(team.members ?? []).map((one) => (
                      <li key={one.principal_id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 text-[13px]">
                        <Link to={personAddress(one.principal_id)} className="text-ink underline-offset-4 hover:underline">
                          {one.display_name}
                        </Link>
                        {mayOrganise ? (
                          <PlacementControl
                            act={{
                              kind: "leave",
                              department: department.slug,
                              team: team.slug,
                              teamName: team.name,
                              principalId: one.principal_id,
                              person: one.display_name,
                            }}
                            label="Take out"
                            onWritten={onWritten}
                          />
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
      <NewTeamDrawer open={creating} onOpenChange={setCreating} department={department.slug} departmentName={department.name} onWritten={onWritten} />
      <RenameDrawer
        target={renaming}
        onOpenChange={(open) => {
          if (!open) {
            setRenaming(null);
          }
        }}
        onWritten={onWritten}
      />
      <AddMemberDrawer
        open={adding !== null}
        onOpenChange={(open) => {
          if (!open) {
            setAdding(null);
          }
        }}
        department={department.slug}
        team={adding?.slug ?? ""}
        teamName={adding?.name ?? ""}
        candidates={everybody.filter((one) => !inTeam.has(one.principal_id))}
        onWritten={onWritten}
      />
    </div>
  );
}

function Scopes({
  department,
  mayDrawScopes,
  retiringScope,
}: {
  readonly department: DepartmentRow;
  readonly mayDrawScopes: boolean;
  readonly retiringScope: string;
}) {
  const [version, setVersion] = useState(0);
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<Target | null>(null);
  const answer = useResource<unknown>(scopesNamingApiPath(department.slug), version);
  const scopes = readScopes(answer.data).scopes;
  const written = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label="Loading the scopes that name it." rows={2} />;
  } else if (scopes.length === 0) {
    body = <p className="m-0 text-[13px] text-dim">No scope you may see names this department.</p>;
  } else {
    body = (
      <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
        {scopes.map((one) => (
          <li key={one.slug} className="flex flex-wrap items-start justify-between gap-2 py-2 text-[13px]">
            <span className="flex min-w-0 flex-col">
              <span className="font-medium text-ink">{one.label}</span>
              <span className="text-[12px] text-dim [overflow-wrap:anywhere]">{scopeLines(one.scope).join("; ") || "Everything"}</span>
            </span>
            {mayDrawScopes ? (
              <span className="flex flex-wrap items-center gap-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setRenaming({ kind: "scope", slug: one.slug, name: one.label, scope: one.scope });
                  }}
                >
                  Rename
                </Button>
                {offersScopeRetirement(one) ? (
                  <RetireControl target={{ kind: "scope", slug: one.slug, name: one.label, scope: one.scope }} consequence={retiringScope} onWritten={written} />
                ) : null}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <SectionCard
      title="Scopes"
      lede="The named boundaries a grant can carry that reach this department."
      action={
        mayDrawScopes ? (
          <Button
            size="sm"
            onClick={() => {
              setCreating(true);
            }}
          >
            New scope
          </Button>
        ) : undefined
      }
    >
      {body}
      <NewScopeDrawer open={creating} onOpenChange={setCreating} fixedDepartment={department.slug} onWritten={written} />
      <RenameDrawer
        target={renaming}
        onOpenChange={(open) => {
          if (!open) {
            setRenaming(null);
          }
        }}
        onWritten={written}
      />
    </SectionCard>
  );
}

function DepartmentAnswer({ slug, view }: { readonly slug: string; readonly view: DepartmentView }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(oneDepartmentApiPath(slug), version);
  const organisation = useMemo(() => readOrganisation(answer.data), [answer.data]);
  const department = useMemo(() => departmentIn(answer.data, slug), [answer.data, slug]);
  const [renaming, setRenaming] = useState<Target | null>(null);
  const written = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    return <LoadingState label={LOADING_DEPARTMENT} />;
  }
  if (department === null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader crumbs={[{ label: DEPARTMENTS_HEADING, to: DEPARTMENTS_ADDRESS }, { label: NO_SUCH_DEPARTMENT }]} title={NO_SUCH_DEPARTMENT} />
        <EmptyState title="Nothing at this address" description={NO_SUCH_DEPARTMENT_DESCRIPTION} icon={<Building2 aria-hidden />} />
      </div>
    );
  }
  const views: DetailView[] = DEPARTMENT_VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: DEPARTMENT_VIEW_LABELS[one], to: departmentAddress(slug, one), icon: <Icon aria-hidden /> };
  });
  const target: Target = { kind: "department", slug: department.slug, name: department.name };

  return (
    <DetailPage
      crumbs={[{ label: DEPARTMENTS_HEADING, to: DEPARTMENTS_ADDRESS }, { label: department.name }]}
      header={
        <DetailHeader
          name={department.name}
          headingId="department-heading"
          actions={
            <>
              {department.shapeable === true ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="min-h-11 sm:min-h-8"
                  onClick={() => {
                    setRenaming(target);
                  }}
                >
                  Rename
                </Button>
              ) : null}
              {organisation.mayFound ? (
                <RetireControl target={target} consequence={organisation.retiringDepartment} onWritten={written} />
              ) : null}
            </>
          }
          figures={
            <KpiStrip label="This department at a glance" count={2}>
              <StatCard label="Lead" value={department.lead?.display_name ?? "None you may see"} />
              <StatCard
                label="Teams"
                value={String(department.teams.length)}
                sub={department.teams.length === 0 ? undefined : department.teams.map((one) => one.name).join(", ")}
              />
            </KpiStrip>
          }
        />
      }
      switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
    >
      {view === "overview" ? <Overview department={department} mayOrganise={organisation.mayOrganise} onWritten={written} /> : null}
      {view === "teams" ? (
        <Teams department={department} mayOrganise={organisation.mayOrganise} retiringTeam={organisation.retiringTeam} onWritten={written} />
      ) : null}
      {view === "scopes" ? (
        <Scopes department={department} mayDrawScopes={organisation.mayDrawScopes} retiringScope={organisation.retiringScope} />
      ) : null}
      <RenameDrawer
        target={renaming}
        onOpenChange={(open) => {
          if (!open) {
            setRenaming(null);
          }
        }}
        onWritten={written}
      />
    </DetailPage>
  );
}

export function DepartmentDetailPage({ slug, view }: { readonly slug: string; readonly view: DepartmentView }) {
  return (
    <div data-slot="department-page" className="min-w-0">
      <DepartmentAnswer key={slug} slug={slug} view={view} />
    </div>
  );
}
