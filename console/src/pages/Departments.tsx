/**
 * Departments and teams: the organisation, who belongs to each part of it, and who leads each.
 *
 * `docs/screens.html` SCREEN 10, People and Grants, draws this as its Organisation card: the
 * company, each department with its lead beside it, and the people in it, with a person's row
 * leading to what they hold. This screen is that card at full width. The crumb, the filter bar, one
 * card per department with its lead, its teams and their members, and its people, and the hint under
 * it are the design's; each person links to their row on People and grants, which is the design's
 * entitlement panel beside the tree.
 *
 * **Adapted where the design draws a figure, and said in words.** The design puts a headcount beside
 * every department and a role and a grant count beside every person. No figure is drawn, because
 * every list here is narrowed to the reader and a number beside it is a subtraction; no role is
 * drawn, because no table records one. A team whose members this reader may not name reads as a
 * team nobody is in, and the API's sentence says so.
 *
 * **Placing somebody and appointing a lead are confirmed, in the API's words.** An organiser sees an
 * add control under each team, a remove control beside each member, and an appoint and a stand-down
 * control under the lead. Each opens a confirmation naming the person and the team or department and
 * carrying the API's sentence that none of it changes anybody's access. The candidates offered are
 * the department's own people already on this page, never a list from anywhere else, for
 * `governPeopleQuery.A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE`'s reason. The route asks
 * `brain.console.organisation.may_place` and `may_appoint` whatever this page offered.
 *
 * **A person's sign-in is disabled and enabled from their row, confirmed.** A reader holding the
 * grant decision sees the control beside each person; the confirmation names them and carries the
 * API's sentence that disabling ends their sessions and makes their grants inert without deleting
 * anything. `brain.principal_state_routes` asks `may_disable` about the row whatever this offered.
 *
 * **The structure is created, renamed and retired here, each act confirmed** (M27.11.1). A reader
 * holding the whole company's authority is offered to create a department and to retire each one; a
 * reader holding the authority over a department is offered to rename it and to create, rename and
 * retire its teams; a reader holding the authority over scopes is offered the Scopes card, which lists
 * the scopes the Scopes screen answers them and draws a new one over departments on this page. Each
 * control is presentation only, from the API's `may_found`, `shapeable` and `may_draw_scopes`, and
 * every route asks its own question whatever was drawn. A retirement's confirmation carries the API's
 * sentence about what it does and does not do, and a department under a live grant is refused in the
 * API's one sentence naming no grant (M27.15.22). A rename sends the name and the name the page
 * showed and never the short name, for `governPeopleQuery.A_SHORT_NAME_IS_NEVER_CHANGED`'s reason, and
 * a retirement is a retirement: the API keeps the row, and nothing here deletes anything.
 *
 * **Nothing here decides who may see anything.** The API answers from `brain.console.organisation`,
 * and the search, the filters, the order and "Show more" are requests to it (`brain.listing`), so a
 * search for a person finds the department they are shown under and never one they are withheld
 * from. The people in no recorded department arrive with the first page and are searched with the
 * same words. A write asks for the first page again, for `People.tsx`' reason: the page shows what
 * the database holds.
 *
 * Imported statically: it mounts neither heavy library and no stylesheet of its own.
 *
 * Task ids: M27.7.4, M27.8.6, M1.2.3, M27.11.1, M27.15.22
 */

import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { readScopesPage, scopeChoicesApiPath, type ScopeRowView } from "./governQuery";
import {
  ADDING_A_TEAM_DOES,
  ADD_TEAM_API_PATH,
  DISABLE_API_PATH,
  DRAWING_DOES,
  DRAW_SCOPE_API_PATH,
  ENABLE_API_PATH,
  FOUNDING_DOES,
  FOUND_API_PATH,
  LEAD_API_PATH,
  MEMBERSHIP_API_PATH,
  RENAME_DEPARTMENT_API_PATH,
  RENAME_TEAM_API_PATH,
  RENAMING_DOES,
  RETIRE_DEPARTMENT_API_PATH,
  RETIRE_SCOPE_API_PATH,
  RETIRE_TEAM_API_PATH,
  addTeamQuestion,
  appointBody,
  creationBlanks,
  DEPARTMENTS_API_PATH,
  DEPARTMENT_FILTERS,
  DEPARTMENT_SORTS,
  drawingBlanks,
  drawingBody,
  drawQuestion,
  foundQuestion,
  leadCandidates,
  leadQuestion,
  membershipBody,
  membershipQuestion,
  offersRetirement,
  personAddress,
  readOrganisation,
  renameQuestion,
  renamingBlank,
  retireQuestion,
  standDownBody,
  stateQuestion,
  teamCandidates,
  when,
  type DepartmentRow,
  type LeadBody,
  type MemberRow,
  type MembershipBody,
  type StateBody,
  type StructureBody,
  type TeamRow,
} from "./governPeopleQuery";
import { scopeLines } from "./scopeText";

export const DEPARTMENTS_HEADING = "Departments and teams";
export const DEPARTMENTS_CRUMB = "Govern › Departments and teams";
export const DEPARTMENTS_LEDE =
  "Every department you may see, who leads it, the teams inside it and who is in each, and the " +
  "people who sit in it. Open a person to see what they hold.";

/** The four states. */
export const READING_DEPARTMENTS = "Reading the organisation.";
export const NO_DEPARTMENTS_HERE = "There are no departments to show.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

/** A department or a team with nobody listed under it. About the page, never a figure. */
export const NOBODY_LISTED = "Nobody is listed in this department.";
export const NOBODY_IN_TEAM = "Nobody you may see is listed in this team.";
export const NO_LEAD = "No lead you may see is recorded for this department.";
export const NO_TEAMS = "This department has no teams.";
export const NONE_MATCH = NOTHING_MATCHES;
export const MORE_ROWS = "This list came back full, so there is more than it shows.";
export const DISABLED = "Disabled";

export const SEARCH_LABEL = "Find a department or a person";
export const UNPLACED_HEADING = "Not in a recorded department";

/** The controls, as verbs. */
export const ADD_LABEL = "Add to team";
export const REMOVE_LABEL = "Take out";
export const APPOINT_LABEL = "Appoint as lead";
export const STAND_DOWN_LABEL = "Stand down";
export const DISABLE_LABEL = "Disable sign-in";
export const ENABLE_LABEL = "Enable sign-in";
export const CANCEL_LABEL = "Leave it as it is";
export const CHOOSE_PERSON = "Choose a person";
/** What an add or an appointment sent with nobody chosen says, before anything is sent. */
export const CHOOSE_SOMEBODY_FIRST = "Choose who to place first; nothing has been sent.";

/** The structure's controls (M27.11.1), as verbs. */
export const RENAME_LABEL = "Rename";
export const RENAME_DEPARTMENT_LABEL = "Rename department";
export const RENAME_TEAM_LABEL = "Rename team";
export const RETIRE_DEPARTMENT_LABEL = "Retire department";
export const RETIRE_TEAM_LABEL = "Retire team";
export const RETIRE_SCOPE_LABEL = "Retire scope";
export const CREATE_DEPARTMENT_LABEL = "Create department";
export const CREATE_TEAM_LABEL = "Create team";
export const DRAW_SCOPE_LABEL = "Draw scope";
export const RETIRE_LABEL = "Retire";

export const FOUND_HEADING = "Create a department";
export const SCOPES_HEADING = "Scopes";
export const SCOPES_LEDE =
  "The scopes a grant can be written over, as the Scopes screen answers you. A department's own " +
  "scope goes with its department, and the company-wide scope is never retired.";
export const READING_SCOPES = "Reading the scopes.";
export const NO_SCOPES = "There are no scopes to show.";
export const WHOLE_DEPARTMENT = "The whole department";
export const SHORT_NAME_LABEL = "Short name";
export const NAME_LABEL = "Name";
export const NEW_NAME_LABEL = "New name";
export const SCOPE_DEPARTMENTS_LABEL = "Departments it reaches";
export const SCOPE_TEAM_LABEL = "Only this team";
/** Said beside a rename, so nobody looks for a way to change the short name. */
export function shortNameStays(slug: string): string {
  return `The short name ${slug} stays as it is.`;
}

/** What a success says: what changed, for whom, and the instant the database recorded. */
export function changedSentence(question: string, at: string): string {
  return `Done: ${question.replace(/\?$/, "")}, recorded at ${when(at)}.`;
}

function readAt(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const at = (payload as { at?: unknown }).at;
  return typeof at === "string" ? at : "";
}

/** One write waiting for its confirmation: where it goes, what it sends, and the words it shows. */
interface Pending {
  readonly path: string;
  readonly body: MembershipBody | LeadBody | StateBody | StructureBody;
  readonly question: string;
  readonly consequence: string;
  readonly confirmLabel: string;
}

/** The sentences one structure form was answered with before anything was sent. */
interface Said {
  readonly form: string;
  readonly sentences: readonly string[];
}

function Blanks({ said, form }: { readonly said: Said | null; readonly form: string }) {
  return said === null || said.form !== form ? null : (
    <>
      {said.sentences.map((sentence) => (
        <p className="note" key={sentence}>
          {sentence}
        </p>
      ))}
    </>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
}) {
  return (
    <label className="control-label">
      {label}{" "}
      <input
        className="form-control"
        type="text"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </label>
  );
}

function Person({ member, department }: { readonly member: MemberRow; readonly department?: string | null }) {
  return (
    <>
      <Link to={personAddress(member.principal_id)}>{member.display_name}</Link> <code>{member.principal_id}</code>
      {department === undefined || department === null ? null : (
        <>
          {" "}
          <code>{department}</code>
        </>
      )}
      {member.disabled ? <span className="note"> {DISABLED}</span> : null}
    </>
  );
}

function Chooser({
  label,
  people,
  value,
  onChange,
}: {
  readonly label: string;
  readonly people: readonly MemberRow[];
  readonly value: string;
  readonly onChange: (value: string) => void;
}) {
  return (
    <label className="control-label">
      {label}{" "}
      <select
        className="form-control"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        <option value="">{CHOOSE_PERSON}</option>
        {people.map((one) => (
          <option key={one.principal_id} value={one.principal_id}>
            {one.display_name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Organisation({
  version,
  onChanged,
}: {
  readonly version: number;
  readonly onChanged: (sentence: string) => void;
}) {
  const listing = useListing<DepartmentRow>(DEPARTMENTS_API_PATH, {
    choices: DEPARTMENT_FILTERS,
    version,
  });
  const [chosen, setChosen] = useState<Readonly<Record<string, string>>>({});
  const [pending, setPending] = useState<Pending | null>(null);
  const [blank, setBlank] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  // The structure's forms: what is typed, which rename is open, which departments a scope reaches.
  const [drafts, setDrafts] = useState<Readonly<Record<string, string>>>({});
  const [renaming, setRenaming] = useState<string | null>(null);
  const [ticked, setTicked] = useState<readonly string[]>([]);
  const [said, setSaid] = useState<Said | null>(null);

  const send = useCallback(
    (asked: Pending) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(asked.path, { method: "POST", body: asked.body });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        setDrafts({});
        setRenaming(null);
        setTicked([]);
        onChanged(changedSentence(asked.question, readAt(result.data)));
      })();
    },
    [onChanged],
  );

  const page = readOrganisation(listing.body);
  const shown = page.departments;
  const scopes = useResource<unknown>(page.mayDrawScopes ? scopeChoicesApiPath() : null, version);
  const scopeRows = readScopesPage(scopes.data).scopes;
  const choose = (key: string) => (value: string) => {
    setChosen({ ...chosen, [key]: value });
  };
  const draft = (key: string) => drafts[key] ?? "";
  const type = (key: string) => (value: string) => {
    setDrafts({ ...drafts, [key]: value });
  };
  const nameOf = (people: readonly MemberRow[], id: string) =>
    people.find((one) => one.principal_id === id)?.display_name ?? id;
  const ask = (asked: Pending) => {
    setFailure(null);
    setSaid(null);
    setPending(asked);
  };
  // True when the form was answered with sentences, so nothing is asked.
  const answered = (form: string, sentences: readonly string[]) => {
    setSaid({ form, sentences });
    return sentences.length > 0;
  };

  const askJoin = (department: DepartmentRow, team: TeamRow, principalId: string) => {
    const question = membershipQuestion(team.name, nameOf(department.members, principalId), "join");
    setFailure(null);
    setPending({
      path: MEMBERSHIP_API_PATH,
      body: membershipBody(department.slug, team.slug, principalId, "join"),
      question,
      consequence: page.teams,
      confirmLabel: ADD_LABEL,
    });
  };
  const askLeave = (department: DepartmentRow, team: TeamRow, member: MemberRow) => {
    setFailure(null);
    setPending({
      path: MEMBERSHIP_API_PATH,
      body: membershipBody(department.slug, team.slug, member.principal_id, "leave"),
      question: membershipQuestion(team.name, member.display_name, "leave"),
      consequence: page.teams,
      confirmLabel: REMOVE_LABEL,
    });
  };
  const askAppoint = (department: DepartmentRow, principalId: string) => {
    setFailure(null);
    setPending({
      path: LEAD_API_PATH,
      body: appointBody(department.slug, principalId),
      question: leadQuestion(department.name, nameOf(department.members, principalId), "appoint"),
      consequence: page.leads,
      confirmLabel: APPOINT_LABEL,
    });
  };
  const askState = (member: MemberRow) => {
    const disable = !member.disabled;
    setFailure(null);
    setPending({
      path: disable ? DISABLE_API_PATH : ENABLE_API_PATH,
      body: { principal_id: member.principal_id },
      question: stateQuestion(member.display_name, disable),
      consequence: page.disabling,
      confirmLabel: disable ? DISABLE_LABEL : ENABLE_LABEL,
    });
  };
  const stateControl = (member: MemberRow) =>
    page.mayDisable ? (
      <>
        {" "}
        <button
          type="button"
          className="button"
          disabled={busy}
          aria-label={`${member.disabled ? ENABLE_LABEL : DISABLE_LABEL}: ${member.display_name}`}
          onClick={() => {
            askState(member);
          }}
        >
          {member.disabled ? ENABLE_LABEL : DISABLE_LABEL}
        </button>
      </>
    ) : null;
  const askStandDown = (department: DepartmentRow, lead: MemberRow) => {
    setFailure(null);
    setPending({
      path: LEAD_API_PATH,
      body: standDownBody(department.slug),
      question: leadQuestion(department.name, lead.display_name, "stand_down"),
      consequence: page.leads,
      confirmLabel: STAND_DOWN_LABEL,
    });
  };

  // ------------------------------------------------------------ the structure (M27.11.1)

  const openRename = (key: string, current: string) => {
    setSaid(null);
    setRenaming(key);
    setDrafts({ ...drafts, [key]: current });
  };
  const askRenameDepartment = (department: DepartmentRow) => {
    const key = `rename:${department.slug}`;
    const typed = draft(key).trim();
    const refused = renamingBlank(department.name, typed);
    if (answered(key, refused === null ? [] : [refused])) {
      return;
    }
    ask({
      path: RENAME_DEPARTMENT_API_PATH,
      body: { slug: department.slug, expected_name: department.name, name: typed },
      question: renameQuestion("department", department.name, typed),
      consequence: RENAMING_DOES,
      confirmLabel: RENAME_LABEL,
    });
  };
  const askRetireDepartment = (department: DepartmentRow) => {
    ask({
      path: RETIRE_DEPARTMENT_API_PATH,
      body: { slug: department.slug, expected_name: department.name },
      question: retireQuestion("department", department.name),
      consequence: page.retiringDepartment,
      confirmLabel: RETIRE_LABEL,
    });
  };
  const askAddTeam = (department: DepartmentRow) => {
    const key = `team:${department.slug}`;
    const slug = draft(`${key}:slug`).trim();
    const name = draft(`${key}:name`).trim();
    if (answered(key, creationBlanks(slug, name))) {
      return;
    }
    ask({
      path: ADD_TEAM_API_PATH,
      body: { department: department.slug, slug, name },
      question: addTeamQuestion(department.name, name, slug),
      consequence: ADDING_A_TEAM_DOES,
      confirmLabel: CREATE_TEAM_LABEL,
    });
  };
  const askRenameTeam = (department: DepartmentRow, team: TeamRow) => {
    const key = `rename:${department.slug}.${team.slug}`;
    const typed = draft(key).trim();
    const refused = renamingBlank(team.name, typed);
    if (answered(key, refused === null ? [] : [refused])) {
      return;
    }
    ask({
      path: RENAME_TEAM_API_PATH,
      body: { department: department.slug, slug: team.slug, expected_name: team.name, name: typed },
      question: renameQuestion("team", team.name, typed),
      consequence: RENAMING_DOES,
      confirmLabel: RENAME_LABEL,
    });
  };
  const askRetireTeam = (department: DepartmentRow, team: TeamRow) => {
    ask({
      path: RETIRE_TEAM_API_PATH,
      body: { department: department.slug, slug: team.slug, expected_name: team.name },
      question: retireQuestion("team", team.name),
      consequence: page.retiringTeam,
      confirmLabel: RETIRE_LABEL,
    });
  };
  const askFound = () => {
    const slug = draft("found:slug").trim();
    const name = draft("found:name").trim();
    if (answered("found", creationBlanks(slug, name))) {
      return;
    }
    ask({
      path: FOUND_API_PATH,
      body: { slug, name },
      question: foundQuestion(name, slug),
      consequence: FOUNDING_DOES,
      confirmLabel: CREATE_DEPARTMENT_LABEL,
    });
  };
  // The departments a scope may reach are the ones on this page, never a list from elsewhere.
  const reachable = ticked.filter((slug) => shown.some((one) => one.slug === slug));
  const onlyOne = reachable.length === 1 ? shown.find((one) => one.slug === reachable[0]) : undefined;
  const askDraw = () => {
    const slug = draft("scope:slug").trim();
    const label = draft("scope:label").trim();
    if (answered("scope", drawingBlanks(slug, label, reachable))) {
      return;
    }
    ask({
      path: DRAW_SCOPE_API_PATH,
      body: drawingBody(slug, label, reachable, onlyOne === undefined ? "" : draft("scope:team")),
      question: drawQuestion(label, slug),
      consequence: DRAWING_DOES,
      confirmLabel: DRAW_SCOPE_LABEL,
    });
  };
  const askRetireScope = (row: ScopeRowView) => {
    ask({
      path: RETIRE_SCOPE_API_PATH,
      body: { slug: row.slug, expected_scope: row.scope },
      question: retireQuestion("scope", row.label),
      consequence: page.retiringScope,
      confirmLabel: RETIRE_LABEL,
    });
  };

  const renameForm = (key: string, label: string, slug: string, onAsk: () => void) => (
    <form
      className="form"
      aria-label={label}
      onSubmit={(event) => {
        event.preventDefault();
        onAsk();
      }}
    >
      <TextField label={NEW_NAME_LABEL} value={draft(key)} onChange={type(key)} />{" "}
      <button type="submit" className="button" disabled={busy}>
        {RENAME_LABEL}
      </button>
      <p className="note">{shortNameStays(slug)}</p>
      <Blanks said={said} form={key} />
    </form>
  );

  return (
    <>
      <ListControls
        label={SEARCH_LABEL}
        listing={listing}
        choices={DEPARTMENT_FILTERS}
        sorts={DEPARTMENT_SORTS}
      />

      {failure === null ? null : <FailureNotice failure={failure} />}

      {pending === null ? null : (
        <ConfirmAction
          question={pending.question}
          consequence={pending.consequence}
          confirmLabel={pending.confirmLabel}
          cancelLabel={CANCEL_LABEL}
          busy={busy}
          onConfirm={() => {
            send(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}

      {listing.failure ? (
        <FailureNotice failure={listing.failure} />
      ) : listing.busy ? (
        <p className="note" role="status">
          {READING_DEPARTMENTS}
        </p>
      ) : shown.length === 0 ? (
        <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_DEPARTMENTS_HERE}</p>
      ) : (
        shown.map((department) => {
          const shapeable = department.shapeable === true;
          const renameKey = `rename:${department.slug}`;
          return (
            <section className="card" key={department.slug} aria-labelledby={`department-${department.slug}`}>
              <h2 id={`department-${department.slug}`}>
                {department.name} <code>{department.slug}</code>
              </h2>
              {shapeable || page.mayFound ? (
                <p>
                  {shapeable ? (
                    <button
                      type="button"
                      className="button"
                      disabled={busy}
                      aria-label={`${RENAME_DEPARTMENT_LABEL}: ${department.name}`}
                      onClick={() => {
                        openRename(renameKey, department.name);
                      }}
                    >
                      {RENAME_LABEL}
                    </button>
                  ) : null}{" "}
                  {page.mayFound ? (
                    <button
                      type="button"
                      className="button"
                      disabled={busy}
                      aria-label={`${RETIRE_DEPARTMENT_LABEL}: ${department.name}`}
                      onClick={() => {
                        askRetireDepartment(department);
                      }}
                    >
                      {RETIRE_DEPARTMENT_LABEL}
                    </button>
                  ) : null}
                </p>
              ) : null}
              {shapeable && renaming === renameKey
                ? renameForm(renameKey, `${RENAME_DEPARTMENT_LABEL}: ${department.name}`, department.slug, () => {
                    askRenameDepartment(department);
                  })
                : null}

              <h3>Lead</h3>
              {department.lead === null || department.lead === undefined ? (
                <p className="note">{NO_LEAD}</p>
              ) : (
                <p aria-label={`Lead of ${department.name}`}>
                  <Person member={department.lead} />
                  {page.mayOrganise ? (
                    <>
                      {" "}
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        onClick={() => {
                          if (department.lead) {
                            askStandDown(department, department.lead);
                          }
                        }}
                      >
                        {STAND_DOWN_LABEL}
                      </button>
                    </>
                  ) : null}
                </p>
              )}
              {page.mayOrganise && leadCandidates(department).length > 0 ? (
                <form
                  className="form"
                  aria-label={`Lead of ${department.name}`}
                  onSubmit={(event) => {
                    event.preventDefault();
                    const principalId = chosen[`lead:${department.slug}`] ?? "";
                    if (principalId === "") {
                      setBlank(`lead:${department.slug}`);
                      return;
                    }
                    setBlank(null);
                    askAppoint(department, principalId);
                  }}
                >
                  <Chooser
                    label={`Lead of ${department.name}`}
                    people={leadCandidates(department)}
                    value={chosen[`lead:${department.slug}`] ?? ""}
                    onChange={choose(`lead:${department.slug}`)}
                  />{" "}
                  <button type="submit" className="button" disabled={busy}>
                    {APPOINT_LABEL}
                  </button>
                  {blank === `lead:${department.slug}` ? <p className="note">{CHOOSE_SOMEBODY_FIRST}</p> : null}
                </form>
              ) : null}

              <h3>Teams</h3>
              {department.teams.length === 0 ? (
                <p className="note">{NO_TEAMS}</p>
              ) : (
                <ul className="roster" aria-label={`Teams in ${department.name}`}>
                  {department.teams.map((team) => {
                    const members = team.members ?? [];
                    const key = `team:${department.slug}.${team.slug}`;
                    const teamRenameKey = `rename:${department.slug}.${team.slug}`;
                    const candidates = teamCandidates(department, team);
                    return (
                      <li key={team.slug}>
                        {team.name} <code>{`${department.slug}.${team.slug}`}</code>
                        {shapeable ? (
                          <>
                            {" "}
                            <button
                              type="button"
                              className="button"
                              disabled={busy}
                              aria-label={`${RENAME_TEAM_LABEL}: ${team.name}`}
                              onClick={() => {
                                openRename(teamRenameKey, team.name);
                              }}
                            >
                              {RENAME_LABEL}
                            </button>{" "}
                            <button
                              type="button"
                              className="button"
                              disabled={busy}
                              aria-label={`${RETIRE_TEAM_LABEL}: ${team.name}`}
                              onClick={() => {
                                askRetireTeam(department, team);
                              }}
                            >
                              {RETIRE_TEAM_LABEL}
                            </button>
                          </>
                        ) : null}
                        {shapeable && renaming === teamRenameKey
                          ? renameForm(
                              teamRenameKey,
                              `${RENAME_TEAM_LABEL}: ${team.name}`,
                              `${department.slug}.${team.slug}`,
                              () => {
                                askRenameTeam(department, team);
                              },
                            )
                          : null}
                        {members.length === 0 ? (
                          <p className="note">{NOBODY_IN_TEAM}</p>
                        ) : (
                          <ul className="roster" aria-label={`Members of ${team.name}`}>
                            {members.map((member) => (
                              <li key={member.principal_id}>
                                <Person member={member} />
                                {page.mayOrganise ? (
                                  <>
                                    {" "}
                                    <button
                                      type="button"
                                      className="button"
                                      disabled={busy}
                                      aria-label={`${REMOVE_LABEL}: ${membershipQuestion(team.name, member.display_name, "leave")}`}
                                      onClick={() => {
                                        askLeave(department, team, member);
                                      }}
                                    >
                                      {REMOVE_LABEL}
                                    </button>
                                  </>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        )}
                        {page.mayOrganise && candidates.length > 0 ? (
                          <form
                            className="form"
                            aria-label={`Add to ${team.name}`}
                            onSubmit={(event) => {
                              event.preventDefault();
                              const principalId = chosen[key] ?? "";
                              if (principalId === "") {
                                setBlank(key);
                                return;
                              }
                              setBlank(null);
                              askJoin(department, team, principalId);
                            }}
                          >
                            <Chooser
                              label={`Add to ${team.name}`}
                              people={candidates}
                              value={chosen[key] ?? ""}
                              onChange={choose(key)}
                            />{" "}
                            <button type="submit" className="button" disabled={busy}>
                              {ADD_LABEL}
                            </button>
                            {blank === key ? <p className="note">{CHOOSE_SOMEBODY_FIRST}</p> : null}
                          </form>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
              {shapeable ? (
                <form
                  className="form"
                  aria-label={`${CREATE_TEAM_LABEL} in ${department.name}`}
                  onSubmit={(event) => {
                    event.preventDefault();
                    askAddTeam(department);
                  }}
                >
                  <TextField
                    label={SHORT_NAME_LABEL}
                    value={draft(`team:${department.slug}:slug`)}
                    onChange={type(`team:${department.slug}:slug`)}
                  />{" "}
                  <TextField
                    label={NAME_LABEL}
                    value={draft(`team:${department.slug}:name`)}
                    onChange={type(`team:${department.slug}:name`)}
                  />{" "}
                  <button type="submit" className="button" disabled={busy}>
                    {CREATE_TEAM_LABEL}
                  </button>
                  <Blanks said={said} form={`team:${department.slug}`} />
                </form>
              ) : null}

              <h3>People</h3>
              {department.members.length === 0 ? (
                <p className="note">{NOBODY_LISTED}</p>
              ) : (
                <ul className="roster" aria-label={`People in ${department.name}`}>
                  {department.members.map((member) => (
                    <li key={member.principal_id}>
                      <Person member={member} />
                      {stateControl(member)}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })
      )}

      {listing.busy || listing.failure ? null : <ShowMore listing={listing} />}

      {listing.busy || page.unplaced.length === 0 ? null : (
        <section className="card" aria-labelledby="department-unplaced">
          <h2 id="department-unplaced">{UNPLACED_HEADING}</h2>
          <ul className="roster" aria-label={UNPLACED_HEADING}>
            {page.unplaced.map((member) => (
              <li key={member.principal_id}>
                <Person member={member} department={member.department} />
                {stateControl(member)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {listing.busy || !page.mayFound ? null : (
        <section className="card" aria-labelledby="department-found">
          <h2 id="department-found">{FOUND_HEADING}</h2>
          <form
            className="form"
            aria-label={FOUND_HEADING}
            onSubmit={(event) => {
              event.preventDefault();
              askFound();
            }}
          >
            <TextField label={SHORT_NAME_LABEL} value={draft("found:slug")} onChange={type("found:slug")} />{" "}
            <TextField label={NAME_LABEL} value={draft("found:name")} onChange={type("found:name")} />{" "}
            <button type="submit" className="button" disabled={busy}>
              {CREATE_DEPARTMENT_LABEL}
            </button>
            <Blanks said={said} form="found" />
          </form>
        </section>
      )}

      {listing.busy || !page.mayDrawScopes ? null : (
        <section className="card" aria-labelledby="department-scopes">
          <h2 id="department-scopes">{SCOPES_HEADING}</h2>
          <p className="note">{SCOPES_LEDE}</p>
          {scopes.failure ? (
            <FailureNotice failure={scopes.failure} />
          ) : scopes.busy ? (
            <p className="note">{READING_SCOPES}</p>
          ) : scopeRows.length === 0 ? (
            <p className="note">{NO_SCOPES}</p>
          ) : (
            <ul className="roster" aria-label={SCOPES_HEADING}>
              {scopeRows.map((row) => (
                <li key={row.slug}>
                  {row.label} <code>{row.slug}</code> {scopeLines(row.scope).join("; ")}
                  {offersRetirement(row) ? (
                    <>
                      {" "}
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        aria-label={`${RETIRE_SCOPE_LABEL}: ${row.label}`}
                        onClick={() => {
                          askRetireScope(row);
                        }}
                      >
                        {RETIRE_SCOPE_LABEL}
                      </button>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <form
            className="form"
            aria-label={DRAW_SCOPE_LABEL}
            onSubmit={(event) => {
              event.preventDefault();
              askDraw();
            }}
          >
            <TextField label={SHORT_NAME_LABEL} value={draft("scope:slug")} onChange={type("scope:slug")} />{" "}
            <TextField label={NAME_LABEL} value={draft("scope:label")} onChange={type("scope:label")} />
            <fieldset className="form">
              <legend>{SCOPE_DEPARTMENTS_LABEL}</legend>
              {shown.map((one) => (
                <label className="control-label" key={one.slug}>
                  <input
                    type="checkbox"
                    checked={ticked.includes(one.slug)}
                    onChange={(event) => {
                      setTicked(
                        event.target.checked ? [...ticked, one.slug] : ticked.filter((slug) => slug !== one.slug),
                      );
                    }}
                  />{" "}
                  {one.name} <code>{one.slug}</code>
                </label>
              ))}
            </fieldset>
            {onlyOne === undefined || onlyOne.teams.length === 0 ? null : (
              <label className="control-label">
                {SCOPE_TEAM_LABEL}{" "}
                <select
                  className="form-control"
                  value={draft("scope:team")}
                  onChange={(event) => {
                    type("scope:team")(event.target.value);
                  }}
                >
                  <option value="">{WHOLE_DEPARTMENT}</option>
                  {onlyOne.teams.map((team) => (
                    <option key={team.slug} value={team.slug}>
                      {team.name}
                    </option>
                  ))}
                </select>
              </label>
            )}{" "}
            <button type="submit" className="button" disabled={busy}>
              {DRAW_SCOPE_LABEL}
            </button>
            <Blanks said={said} form="scope" />
          </form>
        </section>
      )}

      {page.truncated ? <p className="note">{MORE_ROWS}</p> : null}
      {[
        page.teams,
        page.leads,
        page.counted,
        page.mayOrganise ? page.organising : "",
        page.mayFound || page.mayDrawScopes || shown.some((one) => one.shapeable === true) ? page.shaping : "",
      ]
        .filter((sentence) => sentence !== "")
        .map((sentence) => (
          <p className="note" key={sentence}>
            {sentence}
          </p>
        ))}
    </>
  );
}

export function Departments() {
  // A counter, so two changes in a row ask twice. Never rendered.
  const [version, setVersion] = useState(0);
  const [changed, setChanged] = useState<string | null>(null);
  const onChanged = useCallback((sentence: string) => {
    setChanged(sentence);
    setVersion((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{DEPARTMENTS_CRUMB}</p>
      <h1>{DEPARTMENTS_HEADING}</h1>
      <p className="lede">{DEPARTMENTS_LEDE}</p>
      {changed === null ? null : (
        <p className="note" role="status">
          {changed}
        </p>
      )}
      <Organisation version={version} onChanged={onChanged} />
    </article>
  );
}
