/**
 * The Roles tab of Roles and permissions, on the shared page kit: the six platform roles and what
 * each is for, who holds each one, which directory groups confer one, and the Approver flag.
 *
 * **A role grants nothing, and the page never draws a capability beside one.** `brain.console.screens`
 * says what this screen has to make visible: a role governs the platform and never implies a
 * capability. So the catalogue is a role, what it exists to do, how many usually hold it and whether
 * it needs a scope, and there is no column that could grow a capability. Editing what a role grants is
 * not offered, because there is nothing to edit (`NotOffered`).
 *
 * **Holders, named, and no count of anybody hidden.** `GET /govern/roles/holders` answers only the
 * appointments the Roles screen's read admits over where each holder sits, and each carries the
 * holder's name, so the list names people rather than printing principal ids. Nothing says how many
 * holders were left out; `typical_count` is product prose about the role, not a figure of this install.
 *
 * **Every act is confirmed where it ends something**: removing a role and retiring a group mapping ask
 * first; appointing, deputising and mapping are drawers. The controls are drawn when the API says
 * `editable`, and every route asks its own question.
 *
 * **Nominations, for the person who cannot appoint** (M33.1.2.3). Anybody this page opens for may
 * propose somebody; the section lists what the reader may decide and what they proposed, and never
 * how many others are waiting. Deciding is a drawer that confirms or declines.
 *
 * Removed from the old screen: principal ids typed into and printed on the forms and lists, the role
 * key as a heading, and three forms drawn open under the lists (now one press away).
 *
 * Task ids: M27.11.3, M1.3.2, M1.3.3, M1.3.4, M1.1.5, M1.8.4, M27.16.1, M33.1.2.3
 */

import { Plus, UserCog } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useResource } from "../../api/useResource";
import {
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  NotOffered,
  PageHeader,
  SectionCard,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  GROUP_RULES_API_PATH,
  HOLDERS_API_PATH,
  MISCONFIGURATIONS_API_PATH,
  NOMINATIONS_API_PATH,
  ROLES_API_PATH,
  readGroupRules,
  readMisconfigurations,
  readNominations,
  readRoles,
  type GroupRuleRow,
  type NominationRow,
  type RoleRow,
} from "../governQuery";
import { dayWords } from "../access/formParts";
import { PersonName, roleWords, useNames } from "../access/PersonName";
import { scopeLines } from "../scopeText";
import { AppointDrawer, DeputyDrawer, EndDialog, GroupRuleDrawer, NominationDecisionDrawer, type Ending } from "./RoleDrawers";

export const ROLES_HEADING = "Roles and permissions";
export const ROLES_LEDE = "The six platform roles, who holds each, and which directory groups confer one. A role grants nothing.";
export const ROLES_CRUMB = "Roles";
export const HOLDERS_HEADING = "Who holds a role";
export const NO_HOLDERS = "Nobody you may see holds a role";
export const GROUP_RULES_HEADING = "Directory groups";
export const NOMINATIONS_HEADING = "Nominations";
export const NOTHING_TO_DECIDE = "Nothing is waiting for your decision";
export const NOMINATED_NOBODY = "You have not nominated anybody";

/** A nomination's state, in words. */
export function nominationState(row: NominationRow): string {
  if (row.outcome === "confirmed") {
    return "Confirmed";
  }
  if (row.outcome === "declined") {
    return "Declined";
  }
  return "Waiting for a decision";
}
export const MISCONFIGURED_HEADING = "Approver role and approve permission";
export const SYNCED_HEADING = "Roles the sync wrote from a group";
export const A_ROLE_IS_NOT_EDITED =
  "What a role grants is not edited here, because a role grants nothing: what somebody may see is only what their grants say.";

/** One holder, as the holders route sends one. */
export interface HolderLine {
  readonly id: string;
  readonly principalId: string;
  readonly displayName?: string;
  readonly role: string;
  readonly scope: unknown;
  readonly deputyOf?: string;
  readonly notAfter?: string;
}

export function readHolderLines(payload: unknown): { readonly items: readonly HolderLine[]; readonly editable: boolean } {
  if (typeof payload !== "object" || payload === null) {
    return { items: [], editable: false };
  }
  const body = payload as { items?: unknown; editable?: unknown };
  const items = (Array.isArray(body.items) ? (body.items as readonly unknown[]) : []).flatMap((item) => {
    const row = item as Record<string, unknown>;
    if (typeof row["id"] !== "string" || typeof row["principal_id"] !== "string" || typeof row["role"] !== "string") {
      return [];
    }
    return [
      {
        id: row["id"],
        principalId: row["principal_id"],
        role: row["role"],
        scope: row["scope"],
        ...(typeof row["display_name"] === "string" ? { displayName: row["display_name"] } : {}),
        ...(typeof row["deputy_of"] === "string" ? { deputyOf: row["deputy_of"] } : {}),
        ...(typeof row["not_after"] === "string" ? { notAfter: row["not_after"] } : {}),
      },
    ];
  });
  return { items, editable: body.editable === true };
}

function Catalogue() {
  const answer = useResource<unknown>(ROLES_API_PATH);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    return <LoadingState label="Loading the roles." rows={3} />;
  }
  const roles = readRoles(answer.data);
  const columns: readonly EntityColumn<RoleRow>[] = [
    { id: "role", header: "Role", hideable: false, cell: (row) => <span className="font-medium text-ink">{roleWords(row.role)}</span>, text: (row) => roleWords(row.role) },
    { id: "exists_to", header: "Exists to", cell: (row) => row.exists_to, text: (row) => row.exists_to },
    { id: "typical", header: "Usually held by", cell: (row) => row.typical_count, text: (row) => row.typical_count },
    {
      id: "scope",
      header: "Scope",
      cell: (row) => (row.scope_required ? "Held over a scope" : "Company-wide"),
      text: (row) => (row.scope_required ? "Held over a scope" : "Company-wide"),
    },
  ];
  return roles.length === 0 ? (
    <p className="m-0 text-[13px] text-dim">There are no roles to show.</p>
  ) : (
    <EntityTable caption="The platform roles" columns={columns} rows={roles} rowId={(row) => row.role} rowLabel={(row) => roleWords(row.role)} />
  );
}

function Holders({ version, onWritten }: { readonly version: number; readonly onWritten: () => void }) {
  const answer = useResource<unknown>(HOLDERS_API_PATH, version);
  const page = useMemo(() => readHolderLines(answer.data), [answer.data]);
  const [appointing, setAppointing] = useState(false);
  const [deputising, setDeputising] = useState(false);
  const [ending, setEnding] = useState<Ending | null>(null);

  const nameOf = (row: HolderLine) => row.displayName ?? "another account";
  const standing = page.items
    .filter((one) => one.deputyOf === undefined)
    .map((one) => ({ id: one.id, label: `${nameOf(one)}, ${roleWords(one.role)}` }));

  const columns: readonly EntityColumn<HolderLine>[] = [
    {
      id: "person",
      header: "Person",
      hideable: false,
      cell: (row) => <PersonName principalId={row.principalId} names={new Map()} known={row.displayName} />,
      text: (row) => nameOf(row),
    },
    { id: "role", header: "Role", cell: (row) => roleWords(row.role), text: (row) => roleWords(row.role) },
    {
      id: "scope",
      header: "Over",
      cell: (row) => scopeLines(row.scope).join("; ") || "The whole company",
      text: (row) => scopeLines(row.scope).join("; ") || "The whole company",
    },
    {
      id: "until",
      header: "Until",
      cell: (row) => (row.notAfter === undefined ? (row.deputyOf === undefined ? "Standing" : "") : `${row.deputyOf === undefined ? "" : "Deputy, "}${dayWords(row.notAfter)}`),
      text: (row) => row.notAfter ?? "",
    },
  ];

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label="Loading who holds a role." rows={3} />;
  } else if (page.items.length === 0) {
    body = <EmptyState title={NO_HOLDERS} description="A person holds a role once somebody appoints them here or a directory group mapped below confers it." icon={<UserCog aria-hidden />} />;
  } else {
    body = (
      <EntityTable
        caption="People holding a role"
        columns={columns}
        rows={page.items}
        rowId={(row) => row.id}
        rowLabel={(row) => `${nameOf(row)}, ${roleWords(row.role)}`}
        exportName="role-holders"
        rowActions={
          page.editable
            ? (row) => (
                <Button
                  size="sm"
                  variant="outline"
                  aria-label={`Remove ${roleWords(row.role)} from ${nameOf(row)}`}
                  onClick={() => {
                    setEnding({ kind: "role", grantId: row.id, question: `Remove ${roleWords(row.role)} from ${nameOf(row)}?` });
                  }}
                >
                  Remove
                </Button>
              )
            : undefined
        }
      />
    );
  }

  return (
    <SectionCard
      title={HOLDERS_HEADING}
      lede="Appointments you may see, with the scope each is held over."
      action={
        page.editable ? (
          <>
            {standing.length > 0 ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setDeputising(true);
                }}
              >
                Appoint a deputy
              </Button>
            ) : null}
            <Button
              size="sm"
              onClick={() => {
                setAppointing(true);
              }}
            >
              <Plus aria-hidden /> Appoint
            </Button>
          </>
        ) : undefined
      }
      footer={<NotOffered>{A_ROLE_IS_NOT_EDITED}</NotOffered>}
    >
      {body}
      <AppointDrawer open={appointing} onOpenChange={setAppointing} onWritten={onWritten} />
      <DeputyDrawer open={deputising} onOpenChange={setDeputising} standing={standing} onWritten={onWritten} />
      <EndDialog
        ending={ending}
        onClose={() => {
          setEnding(null);
        }}
        onWritten={onWritten}
      />
    </SectionCard>
  );
}

function GroupRules({ version, onWritten }: { readonly version: number; readonly onWritten: () => void }) {
  const answer = useResource<unknown>(GROUP_RULES_API_PATH, version);
  const page = useMemo(() => readGroupRules(answer.data), [answer.data]);
  const names = useNames(page.synced.length > 0);
  const [mapping, setMapping] = useState(false);
  const [ending, setEnding] = useState<Ending | null>(null);
  const columns: readonly EntityColumn<GroupRuleRow>[] = [
    { id: "group", header: "Group", hideable: false, cell: (row) => <code className="font-mono text-[12px]">{row.idp_group}</code>, text: (row) => row.idp_group },
    { id: "role", header: "Role", cell: (row) => roleWords(row.role), text: (row) => roleWords(row.role) },
    { id: "since", header: "Since", cell: (row) => dayWords(row.created_at), text: (row) => row.created_at },
  ];

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label="Loading the directory group mappings." rows={2} />;
  } else if (page.rules.length === 0) {
    body = <p className="m-0 text-[13px] text-dim">No directory group maps to a role yet.</p>;
  } else {
    body = (
      <EntityTable
        caption="Directory group mappings"
        columns={columns}
        rows={page.rules}
        rowId={(row) => row.id}
        rowLabel={(row) => row.idp_group}
        rowActions={
          page.editable
            ? (row) => (
                <Button
                  size="sm"
                  variant="outline"
                  aria-label={`Retire the mapping of ${row.idp_group}`}
                  onClick={() => {
                    setEnding({ kind: "rule", ruleId: row.id, question: `Retire the mapping of ${row.idp_group} to ${roleWords(row.role)}?` });
                  }}
                >
                  Retire
                </Button>
              )
            : undefined
        }
      />
    );
  }

  const synced = page.synced;
  return (
    <SectionCard
      title={GROUP_RULES_HEADING}
      lede="Each group maps to one role. Somebody in the group holds it from their next sign-in and loses it when they leave."
      action={
        page.editable ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setMapping(true);
            }}
          >
            Map a group
          </Button>
        ) : undefined
      }
    >
      {body}
      {synced.length === 0 ? null : (
        <section aria-label={SYNCED_HEADING} className="mt-4 flex flex-col gap-1.5">
          <h3 className="m-0 font-mono text-[10px] tracking-[0.09em] text-dim uppercase">{SYNCED_HEADING}</h3>
          <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
            {synced.map((one) => (
              <li key={`${one.principal_id} ${one.role} ${one.source_group}`} className="flex flex-wrap items-baseline gap-x-2 py-1.5 text-[13px]">
                <PersonName principalId={one.principal_id} names={names} />
                <span className="text-body">{roleWords(one.role)}</span>
                <span className="text-dim">
                  from <code className="font-mono text-[12px]">{one.source_group}</code>, last confirmed {dayWords(one.last_seen_at)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <GroupRuleDrawer open={mapping} onOpenChange={setMapping} onWritten={onWritten} />
      <EndDialog
        ending={ending}
        onClose={() => {
          setEnding(null);
        }}
        onWritten={onWritten}
      />
    </SectionCard>
  );
}

function Misconfigured() {
  const answer = useResource<unknown>(MISCONFIGURATIONS_API_PATH);
  const rows = readMisconfigurations(answer.data);
  const names = useNames(rows.length > 0);
  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label="Checking the Approver role against the approve permission." rows={1} />;
  } else if (rows.length === 0) {
    body = <p className="m-0 text-[13px] text-dim">Nobody you may see holds one without the other.</p>;
  } else {
    body = (
      <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
        {rows.map((row) => (
          <li key={`${row.principal_id}-${row.kind}`} className="flex flex-col gap-0.5 py-2 text-[13px]">
            <PersonName principalId={row.principal_id} names={names} />
            <span className="text-dim">{row.sentence}</span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <SectionCard title={MISCONFIGURED_HEADING} lede="The approve permission alone decides who may approve. Holding one without the other is a misconfiguration either way.">
      {body}
    </SectionCard>
  );
}

function Nominations({ version, onWritten }: { readonly version: number; readonly onWritten: () => void }) {
  const answer = useResource<unknown>(NOMINATIONS_API_PATH, version);
  const page = useMemo(() => readNominations(answer.data), [answer.data]);
  const [nominating, setNominating] = useState(false);
  const [deciding, setDeciding] = useState<{ readonly id: string; readonly label: string } | null>(null);

  const nameOf = (row: NominationRow) => row.display_name ?? "another account";
  const labelOf = (row: NominationRow) => `${nameOf(row)}, ${roleWords(row.role)}`;
  const columns: readonly EntityColumn<NominationRow>[] = [
    {
      id: "person",
      header: "Person",
      hideable: false,
      cell: (row) => <PersonName principalId={row.principal_id} names={new Map()} known={row.display_name ?? undefined} />,
      text: (row) => nameOf(row),
    },
    { id: "role", header: "Role", cell: (row) => roleWords(row.role), text: (row) => roleWords(row.role) },
    { id: "reason", header: "Why", cell: (row) => row.reason, text: (row) => row.reason },
    { id: "state", header: "State", cell: (row) => nominationState(row), text: (row) => nominationState(row) },
  ];

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label="Loading nominations." rows={2} />;
  } else {
    body = (
      <div className="flex flex-col gap-4">
        {page.deciding.length === 0 ? (
          <p className="m-0 text-[13px] text-dim">{NOTHING_TO_DECIDE}</p>
        ) : (
          <EntityTable
            caption="Nominations waiting for your decision"
            columns={columns}
            rows={page.deciding}
            rowId={(row) => row.id}
            rowLabel={labelOf}
            rowActions={(row) => (
              <Button
                size="sm"
                variant="outline"
                aria-label={`Decide the nomination of ${labelOf(row)}`}
                onClick={() => {
                  setDeciding({ id: row.id, label: labelOf(row) });
                }}
              >
                Decide
              </Button>
            )}
          />
        )}
        {page.mine.length === 0 ? (
          <p className="m-0 text-[13px] text-dim">{NOMINATED_NOBODY}</p>
        ) : (
          <EntityTable caption="Your nominations" columns={columns} rows={page.mine} rowId={(row) => row.id} rowLabel={labelOf} />
        )}
      </div>
    );
  }

  return (
    <SectionCard
      title={NOMINATIONS_HEADING}
      lede="Somebody proposed for a role, confirmed or declined by a person with the grant decision over them."
      action={
        answer.failure === null ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setNominating(true);
            }}
          >
            <Plus aria-hidden /> Nominate
          </Button>
        ) : undefined
      }
    >
      {body}
      <AppointDrawer open={nominating} onOpenChange={setNominating} onWritten={onWritten} nominating />
      <NominationDecisionDrawer
        nomination={deciding}
        onClose={() => {
          setDeciding(null);
        }}
        onWritten={onWritten}
      />
    </SectionCard>
  );
}

export function RolesPage() {
  const [version, setVersion] = useState(0);
  const written = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  return (
    <div data-slot="roles-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: ROLES_HEADING }, { label: ROLES_CRUMB }]} title={ROLES_HEADING} lede={ROLES_LEDE} />
      <SectionCard title="Roles" lede="What each role exists to do. A role governs the platform; it never implies a capability.">
        <Catalogue />
      </SectionCard>
      <Holders version={version} onWritten={written} />
      <Nominations version={version} onWritten={written} />
      <GroupRules version={version} onWritten={written} />
      <Misconfigured />
    </div>
  );
}
