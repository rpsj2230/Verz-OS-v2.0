/**
 * Department on the shared page kit: the page somebody who runs a department opens first, with its
 * name and lead in the header and three views at addresses of their own, Dashboard (who is in it,
 * what they asked this week, its agents, its knowledge and what nobody could answer), Profile (name,
 * lead, teams and the scopes that name it, renamed or retired where the reader may) and About (how a
 * department works, and its history).
 *
 * **Every block is another screen's read, narrowed by that screen's route**, which
 * `departmentHome.ts` argues, and each links to the screen it came from. A block whose route answers
 * this reader 404 is left out, as that screen is left out of their menu; any other failure is drawn
 * in the API's words where the block would be, and the other blocks still draw.
 *
 * **Named, never shown by its short name.** The name is the Departments row's when the reader may
 * read it and the People directory's otherwise, and the short name is in Advanced.
 *
 * **No count of people.** The people listed are the ones this reader may see; a figure of them would
 * read as the department's size. The questions figures are Usage's own totals for the department.
 *
 * Removed from the old page: the "Scope" chip of short names, the sentence listing what the design
 * draws and no route serves, the lede explaining where each card came from, and every card's
 * trailing "on this other screen" paragraph (each block's heading links there now).
 *
 * Task ids: M27.7.29, M27.16.1
 */

import { Bot, Building2, FileText, History, Inbox, LayoutDashboard, SearchX, Settings2, Users } from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ApiFailure } from "../../api/errors";
import { useResource, type Resource } from "../../api/useResource";
import {
  Advanced,
  DetailHeader,
  DetailPage,
  EmptyState,
  EntityTable,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  NotOffered,
  PageHeader,
  SectionCard,
  StatCard,
  StatsStrip,
  ViewSwitch,
  type DetailView,
  type EntityColumn,
} from "../../components/kit";
import { listPath, NO_QUESTION } from "../../components/listing";
import { Button } from "../../components/ui/button";
import { NAVIGATION_API_PATH, readNavigation } from "../../layout/navigationQuery";
import { whenWords } from "../access/formParts";
import { PersonName, useNames } from "../access/PersonName";
import { agentAddress } from "../Agents";
import { readRoster, ROSTER_API_PATH } from "../agentsQuery";
import { phraseFor, readLedgerPage, type AuditRow } from "../auditQuery";
import { departmentAddress, departmentIn, oneDepartmentApiPath, readOrganisation, readScopes, scopesNamingApiPath } from "../departments/departmentsQuery";
import { RenameDrawer, RetireControl, type Target } from "../departments/StructureDrawers";
import { documentAddress, readDocRows } from "../knowledge/knowledgeDocuments";
import { DIRECTORY_API_PATH, personAddress, readPeople } from "../people/peopleQuery";
import { readQuestions, QUESTIONS_API_PATH } from "../questionsQuery";
import { readUsage, usageApiPath } from "../usageQuery";
import {
  DEPARTMENT_HEADING,
  DEPARTMENT_HOME_VIEWS,
  DEPARTMENT_HOME_VIEW_LABELS,
  DEPARTMENT_PARAMETER,
  DEPARTMENT_WINDOW_DAYS,
  chosenDepartment,
  departmentDocumentsApiPath,
  departmentHistoryApiPath,
  departmentHomeAddress,
  type DepartmentHomeView,
} from "./departmentHome";

export { DEPARTMENT_HEADING, DEPARTMENT_PATH } from "./departmentHome";

export const VIEWS_LABEL = "Department views";
export const LOADING_DEPARTMENT = "Loading your department.";
export const YOUR_DEPARTMENT = "Your department";
export const NOT_A_DEPARTMENT_CONSOLE = "This page is a department's own";
export const NOT_A_DEPARTMENT_CONSOLE_DESCRIPTION =
  "Somebody who runs a department opens it here. A company administrator opens each department from Departments.";
export const USAGE_HEADING = "Questions this week";
export const PEOPLE_HEADING = "People";
export const AGENTS_HEADING = "Agents";
export const KNOWLEDGE_HEADING = "Knowledge";
export const GAPS_HEADING = "Questions nobody could answer";
export const QUEUES_HEADING = "Your queues";
export const HISTORY_HEADING = "History";
export const NO_PERSON = "Nobody you may see is listed in this department.";
export const NO_AGENT = "No agent is listed for you.";
export const MORE_AGENTS = "There are more agents than are listed here.";
export const NO_DOCUMENT = "No document you may open is filed under this department.";
export const NO_GAP = "There is no gap to show here.";
export const NO_HISTORY = "No change to this department that you may see is recorded.";
export const PROFILE_ELSEWHERE =
  "Its lead, teams and scopes are managed on Departments by somebody who may open it.";
export const HOW_IT_WORKS =
  "A department is where people sit and what a scope can name. Its lead is appointed and confers nothing: what anybody may see comes only from their own grants.";

/** Where each queue a department's administrator works is, and what waits there. Links, no figures. */
const QUEUES: readonly { readonly to: string; readonly label: string; readonly what: string }[] = [
  { to: "/approvals", label: "Approvals", what: "promotions and actions waiting on a decision" },
  { to: "/learning", label: "Learning", what: "what was learned and waits for a person" },
  { to: "/skills", label: "Skills", what: "skills to review" },
  { to: "/solutions", label: "Solutions", what: "answers captured for the knowledge base" },
];

const VIEW_ICONS: Readonly<Record<DepartmentHomeView, ReactNode>> = {
  dashboard: <LayoutDashboard aria-hidden />,
  profile: <Settings2 aria-hidden />,
  about: <History aria-hidden />,
};

/** A 404 is this reader's answer that the block is not theirs; anything else is a failure to show. */
function notTheirs(failure: ApiFailure | null): boolean {
  return failure !== null && failure.status === 404 && !failure.secondFactorNeeded;
}

/** A block over one read: nothing when it is not the reader's, its failure, its loading, or itself. */
function Block({
  title,
  lede,
  icon,
  answer,
  loading,
  children,
}: {
  readonly title: string;
  readonly lede?: ReactNode | undefined;
  readonly icon?: ReactNode | undefined;
  readonly answer: Resource<unknown>;
  readonly loading: string;
  readonly children: () => ReactNode;
}) {
  if (notTheirs(answer.failure)) {
    return null;
  }
  let body: ReactNode;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label={loading} rows={2} />;
  } else {
    body = children();
  }
  return (
    <SectionCard
      title={title}
      lede={lede}
      action={icon === undefined ? undefined : <span className="text-dim [&>svg]:size-4">{icon}</span>}
    >
      {body}
    </SectionCard>
  );
}

const LINK = "text-ink underline-offset-4 hover:underline";

function Dashboard({ slug, people }: { readonly slug: string; readonly people: Resource<unknown> }) {
  const usage = useResource<unknown>(usageApiPath(DEPARTMENT_WINDOW_DAYS));
  const roster = useResource<unknown>(ROSTER_API_PATH);
  const documents = useResource<unknown>(departmentDocumentsApiPath(slug));
  const questions = useResource<unknown>(QUESTIONS_API_PATH);
  const usageBody = usage.data === null ? null : readUsage(usage.data);
  const line = usageBody?.departments?.find((one) => one.department === slug) ?? null;
  const asked = line?.questions ?? usageBody?.questions ?? null;
  const askers = line?.people ?? usageBody?.people?.length ?? null;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {notTheirs(usage.failure) || (usageBody !== null && asked === null) ? null : (
        <StatsStrip label={USAGE_HEADING} busy={usage.data === null && usage.failure === null} failure={usage.failure} count={2}>
          <StatCard
            label={USAGE_HEADING}
            value={asked === null ? undefined : String(asked)}
            link={
              <Link to="/usage" className="text-[12px] font-normal text-acc-text underline-offset-4 hover:underline">
                Usage
              </Link>
            }
          />
          <StatCard label="People who asked" value={askers === null ? undefined : String(askers)} sub={`last ${String(DEPARTMENT_WINDOW_DAYS)} days`} />
        </StatsStrip>
      )}
      <div className="[display:grid] min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
        <Block title={PEOPLE_HEADING} icon={<Users aria-hidden />} answer={people} loading="Loading who is in it.">
          {() => {
            const rows = readPeople(people.data);
            return rows.length === 0 ? (
              <p className="m-0 text-[13px] text-dim">{NO_PERSON}</p>
            ) : (
              <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
                {rows.map((one) => (
                  <li key={one.principalId} className="py-1.5 text-[13px]">
                    <Link to={personAddress(one.principalId)} className={LINK}>
                      {one.displayName}
                    </Link>
                  </li>
                ))}
              </ul>
            );
          }}
        </Block>
        <Block title={AGENTS_HEADING} icon={<Bot aria-hidden />} answer={roster} loading="Loading the agents.">
          {() => {
            const found = readRoster(roster.data);
            return (
              <>
                {found === null || found.entries.length === 0 ? (
                  <p className="m-0 text-[13px] text-dim">{NO_AGENT}</p>
                ) : (
                  <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
                    {found.entries.map((entry) => (
                      <li key={entry.agentId} className="py-1.5 text-[13px]">
                        <Link to={agentAddress(entry.agentId)} className={LINK}>
                          {entry.displayName}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
                {found?.truncated ? <p className="m-0 mt-2 text-[12px] text-dim">{MORE_AGENTS}</p> : null}
              </>
            );
          }}
        </Block>
        <Block title={KNOWLEDGE_HEADING} lede="The newest documents filed under it." icon={<FileText aria-hidden />} answer={documents} loading="Loading its documents.">
          {() => {
            const rows = readDocRows(documents.data);
            return rows.length === 0 ? (
              <p className="m-0 text-[13px] text-dim">{NO_DOCUMENT}</p>
            ) : (
              <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
                {rows.map((one) => (
                  <li key={one.itemId} className="py-1.5 text-[13px]">
                    <Link to={documentAddress(one.itemId)} className={`${LINK} [overflow-wrap:anywhere]`}>
                      {one.title}
                    </Link>
                  </li>
                ))}
              </ul>
            );
          }}
        </Block>
        <Block title={GAPS_HEADING} icon={<SearchX aria-hidden />} answer={questions} loading="Loading what could not be answered.">
          {() => {
            const body = readQuestions(questions.data);
            const gaps = (body?.gaps ?? []).filter((one) => one.department === slug);
            if (body?.nothing_connected === true) {
              return (
                <p className="m-0 text-[13px] text-body">
                  No source is connected, so every question is answered: <q>{body.answered_when_nothing_connected}</q>{" "}
                  <Link to="/connectors" className="text-acc-text underline-offset-4 hover:underline">
                    Connect a source
                  </Link>
                </p>
              );
            }
            return gaps.length === 0 ? (
              <p className="m-0 text-[13px] text-dim">{NO_GAP}</p>
            ) : (
              <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
                {gaps.map((one) => (
                  <li key={one.source ?? ""} className="flex items-center justify-between gap-2 py-1.5 text-[13px]">
                    <span className="[overflow-wrap:anywhere]">{one.source ?? "Sources you may not name"}</span>
                    <span className="text-dim tabular-nums">{String(one.asked)} asked</span>
                  </li>
                ))}
              </ul>
            );
          }}
        </Block>
        <SectionCard title={QUEUES_HEADING} action={<span className="text-dim [&>svg]:size-4"><Inbox aria-hidden /></span>}>
          <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
            {QUEUES.map((queue) => (
              <li key={queue.to} className="flex flex-col py-1.5 text-[13px]">
                <Link to={queue.to} className={`${LINK} font-medium`}>
                  {queue.label}
                </Link>
                <span className="text-[12px] text-dim">{queue.what}</span>
              </li>
            ))}
          </ul>
        </SectionCard>
      </div>
    </div>
  );
}

function Profile({ slug, name, row }: { readonly slug: string; readonly name: string; readonly row: Resource<unknown> }) {
  const department = row.data === null ? null : departmentIn(row.data, slug);
  const scopes = useResource<unknown>(department === null ? null : scopesNamingApiPath(slug));
  const scopeLabels = readScopes(scopes.data).scopes.map((one) => one.label);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title="Profile"
        lede="Its name, who leads it and how it is organised."
        footer={
          row.data === null && !notTheirs(row.failure) ? undefined : department === null ? (
            <NotOffered>{PROFILE_ELSEWHERE}</NotOffered>
          ) : (
            <p className="m-0 text-[12.5px]">
              <Link to={departmentAddress(slug, "teams")} className="text-acc-text underline-offset-4 hover:underline">
                Manage its teams and scopes
              </Link>
            </p>
          )
        }
      >
        {row.failure !== null && !notTheirs(row.failure) ? (
          <FailureState failure={row.failure} />
        ) : row.data === null && row.failure === null ? (
          <LoadingState label="Loading its profile." rows={3} />
        ) : (
          <FactList>
            <Fact label="Name">{name}</Fact>
            {department === null ? null : (
              <>
                <Fact label="Lead">
                  {department.lead === null || department.lead === undefined ? (
                    "None you may see"
                  ) : (
                    <Link to={personAddress(department.lead.principal_id)} className={LINK}>
                      {department.lead.display_name}
                    </Link>
                  )}
                </Fact>
                <Fact label="Teams">{department.teams.length === 0 ? "None yet" : department.teams.map((one) => one.name).join(", ")}</Fact>
                {scopeLabels.length === 0 ? null : <Fact label="Scopes naming it">{scopeLabels.join(", ")}</Fact>}
              </>
            )}
          </FactList>
        )}
      </SectionCard>
      <Advanced>
        <FactList>
          <Fact label="Short name">
            <code className="font-mono text-[12px]">{slug}</code>
          </Fact>
        </FactList>
      </Advanced>
    </div>
  );
}

function About({ slug }: { readonly slug: string }) {
  const history = useResource<unknown>(departmentHistoryApiPath(slug));
  const names = useNames(history.data !== null);
  const rows = useMemo(() => readLedgerPage(history.data).rows.filter((one) => one.subject_id === slug), [history.data, slug]);
  const columns: readonly EntityColumn<AuditRow>[] = [
    { id: "when", header: "When", hideable: false, cell: (row) => whenWords(row.at), text: (row) => row.at },
    {
      id: "who",
      header: "Who",
      cell: (row) => <PersonName principalId={row.actor_id} names={names} />,
      text: (row) => names.get(row.actor_id) ?? "",
    },
    { id: "what", header: "What", cell: (row) => sentenceOf(phraseFor(row.action, row.details)), text: (row) => sentenceOf(phraseFor(row.action, row.details)) },
  ];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title="How a department works">
        <p className="m-0 text-[13px] text-body">{HOW_IT_WORKS}</p>
      </SectionCard>
      <Block
        title={HISTORY_HEADING}
        lede="The newest changes to it that you may see."
        answer={history}
        loading="Loading its history."
      >
        {() =>
          rows.length === 0 ? (
            <EmptyState title="No history to show" description={NO_HISTORY} icon={<History aria-hidden />} />
          ) : (
            <div className="flex min-w-0 flex-col gap-2">
              <EntityTable caption="Changes to this department" columns={columns} rows={rows} rowId={(row) => `${row.at} ${row.action} ${row.actor_id}`} rowLabel={(row) => whenWords(row.at)} />
              <p className="m-0 text-[12.5px]">
                <Link to="/audit" className="text-acc-text underline-offset-4 hover:underline">
                  Open the audit log
                </Link>
              </p>
            </div>
          )
        }
      </Block>
    </div>
  );
}

/** An audit phrase as a sentence: its first letter capital and no trailing colon. */
function sentenceOf(phrase: string): string {
  const words = phrase.replace(/[:,]\s*$/u, "").trim();
  return words === "" ? phrase : `${words.slice(0, 1).toLocaleUpperCase("en-GB")}${words.slice(1)}`;
}

function DepartmentHome({
  slug,
  view,
  held,
}: {
  readonly slug: string;
  readonly view: DepartmentHomeView;
  /** Every department the reader administers, by short name, which is how the navigation names them. */
  readonly held: readonly string[];
}) {
  const several = held.length > 1;
  const [version, setVersion] = useState(0);
  const row = useResource<unknown>(oneDepartmentApiPath(slug), version);
  const people = useResource<unknown>(listPath(DIRECTORY_API_PATH, { ...NO_QUESTION, filters: { department: slug } }, null, 50));
  const [renaming, setRenaming] = useState<Target | null>(null);
  const written = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const organisation = useMemo(() => readOrganisation(row.data), [row.data]);
  const department = row.data === null ? null : departmentIn(row.data, slug);
  const fromDirectory = readPeople(people.data).find((one) => one.department === slug)?.departmentName;
  const name = department?.name ?? fromDirectory ?? YOUR_DEPARTMENT;
  const views: DetailView[] = DEPARTMENT_HOME_VIEWS.map((one) => ({
    key: one,
    label: DEPARTMENT_HOME_VIEW_LABELS[one],
    to: departmentHomeAddress(one, slug, several),
    icon: VIEW_ICONS[one],
  }));
  const target: Target = { kind: "department", slug, name };

  return (
    <DetailPage
      crumbs={[{ label: DEPARTMENT_HEADING }, { label: name }]}
      header={
        <DetailHeader
          name={name}
          headingId="department-home-heading"
          actions={
            department === null ? undefined : (
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
                {organisation.mayFound ? <RetireControl target={target} consequence={organisation.retiringDepartment} onWritten={written} /> : null}
              </>
            )
          }
          figures={
            department === null ? undefined : (
              <KpiStrip label="This department at a glance" count={2}>
                <StatCard label="Lead" value={department.lead?.display_name ?? "None you may see"} />
                <StatCard
                  label="Teams"
                  value={String(department.teams.length)}
                  sub={department.teams.length === 0 ? undefined : department.teams.map((one) => one.name).join(", ")}
                />
              </KpiStrip>
            )
          }
        />
      }
      switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
      beside={
        several ? (
          <nav aria-label="Your other departments" className="flex flex-wrap items-center gap-2 text-[12.5px] text-dim">
            Also yours:
            {held
              .filter((one) => one !== slug)
              .map((one) => (
                <Link key={one} to={departmentHomeAddress(view, one, true)} className="font-mono text-acc-text underline-offset-4 hover:underline">
                  {one}
                </Link>
              ))}
          </nav>
        ) : undefined
      }
    >
      {view === "dashboard" ? <Dashboard slug={slug} people={people} /> : null}
      {view === "profile" ? <Profile slug={slug} name={name} row={row} /> : null}
      {view === "about" ? <About slug={slug} /> : null}
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

export function DepartmentHomePage({ view }: { readonly view: DepartmentHomeView }) {
  const [search] = useSearchParams();
  const navigation = useResource<unknown>(NAVIGATION_API_PATH);
  if (navigation.failure !== null) {
    return <FailureState failure={navigation.failure} />;
  }
  if (navigation.data === null) {
    return <LoadingState label={LOADING_DEPARTMENT} />;
  }
  const given = readNavigation(navigation.data);
  const held = given?.console === "department" ? given.departments : [];
  const slug = chosenDepartment(held, search.get(DEPARTMENT_PARAMETER));
  if (slug === null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader crumbs={[{ label: DEPARTMENT_HEADING }]} title={DEPARTMENT_HEADING} />
        <EmptyState
          title={NOT_A_DEPARTMENT_CONSOLE}
          description={NOT_A_DEPARTMENT_CONSOLE_DESCRIPTION}
          icon={<Building2 aria-hidden />}
          action={
            <Button asChild variant="outline">
              <Link to="/departments">Open Departments</Link>
            </Button>
          }
        />
      </div>
    );
  }
  return (
    <div data-slot="department-home" className="min-w-0">
      <DepartmentHome key={slug} slug={slug} view={view} held={held} />
    </div>
  );
}
