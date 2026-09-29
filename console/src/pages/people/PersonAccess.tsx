/**
 * A person's Access view: what they may see and why, as `docs/admin-console-architecture.md` Part
 * 4.4 lays it out, three questions kept apart and never merged into one answer.
 *
 * 1. **What do they hold?** Every grant this reader may be told, grouped by where it came from: given
 *    by a person, from a pack, or from an approved elevation with its lapse. Additive only: no deny row
 *    exists and none is drawn, and a capability not listed is one no grant gives them.
 * 2. **What may they use from here?** For the reader's own page, the verbs their grants hold that this
 *    sign-in does not let them use, from `/me`. For anybody else, only what the console needs a second
 *    factor for, never a list derived from that person's grants.
 * 3. **What does a run through an agent reach for them?** `E(caller) ∩ agent_ceiling`, which only the
 *    gate itself may compute. No route previews it for somebody else yet, so the control is drawn
 *    inert with its reason rather than computed here, where it would be a second implementation of
 *    the one rule this product has.
 *
 * **Roles are shown beside the grants and apart from them**, with the sentence that a role grants
 * nothing, because a table putting the two side by side would be read as though one implied the other.
 *
 * **"Who can reach this record" is never asked here.** The reverse question is asked of a capability
 * over a scope, on the Capabilities screen, because asking it of a record confirms the record exists.
 *
 * Task ids: M27.11.3, M27.15.60, M27.16.1
 */

import { Bot } from "lucide-react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Chip, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { VERB_WORDS } from "../../layout/signInStrengthQuery";
import { scopeLines } from "../scopeText";
import { dayWords } from "../access/formParts";
import { roleWords } from "../access/PersonName";
import { A_ROLE_GRANTS_NOTHING, WHAT_NEEDS_A_SECOND_FACTOR, WORKS_AT } from "./peopleActions";
import { PersonPreview } from "./PersonPreview";
import { originWords, scopeWords } from "./PersonGrants";
import {
  HOLDERS_API_PATH,
  ME_API_PATH,
  fromElevation,
  personAddress,
  readMe,
  readRolesHeld,
  type Held,
  type PersonDetail,
} from "./peopleQuery";

export const HOLDS_HEADING = "What they hold";
export const ROLES_HEADING = "Roles";
export const USABLE_HEADING = "What needs a stronger sign-in";
export const THROUGH_AN_AGENT_HEADING = "Through an agent";
export const HOLDS_NOTHING_SHOWN =
  "No grant you may be told about. Grants only add: a person reaches what their grants say and nothing else.";

const GROUPS: readonly { readonly key: "person" | "pack" | "elevation"; readonly title: string; readonly pick: (held: Held) => boolean }[] = [
  { key: "person", title: "Given by a person", pick: (held) => held.kind === "grant" && !fromElevation(held) },
  { key: "pack", title: "From a pack", pick: (held) => held.kind === "pack" },
  { key: "elevation", title: "From an approved elevation", pick: fromElevation },
];

function HeldLine({ held }: { readonly held: Held }) {
  return (
    <li className="flex flex-col gap-1 py-2">
      <span className="flex flex-wrap gap-1">
        {held.capabilities.map((one) => (
          <Chip key={one} mono>
            {one}
          </Chip>
        ))}
      </span>
      <span className="text-[12.5px] text-dim [overflow-wrap:anywhere]">
        over {scopeWords(held)}
        {held.kind === "pack" ? ` · ${originWords(held)}` : ""}
        {held.grantedByName === undefined ? "" : ` · given by ${held.grantedByName}`}
        {held.notAfter === undefined ? "" : ` · lapses ${dayWords(held.notAfter)}`}
      </span>
    </li>
  );
}

function Holds({ detail }: { readonly detail: PersonDetail }) {
  if (detail.held.length === 0) {
    return <p className="m-0 text-[13px] text-dim">{HOLDS_NOTHING_SHOWN}</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {GROUPS.map((group) => {
        const rows = detail.held.filter(group.pick);
        return rows.length === 0 ? null : (
          <section key={group.key} aria-label={group.title}>
            <h3 className="m-0 font-mono text-[10px] tracking-[0.09em] text-dim uppercase">{group.title}</h3>
            <ul className="m-0 list-none divide-y divide-line p-0">
              {rows.map((one) => (
                <HeldLine key={`${one.kind}:${one.rowId}`} held={one} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function Roles({ principalId }: { readonly principalId: string }) {
  const holders = useResource<unknown>(HOLDERS_API_PATH);
  if (holders.failure !== null) {
    return <FailureState failure={holders.failure} />;
  }
  if (holders.data === null) {
    return <LoadingState label="Loading the roles they hold." rows={1} />;
  }
  const held = readRolesHeld(holders.data, principalId);
  if (held.length === 0) {
    return <p className="m-0 text-[13px] text-dim">No role you may see.</p>;
  }
  return (
    <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
      {held.map((one) => {
        const lines = scopeLines(one.scope);
        return (
          <li key={one.id} className="flex flex-wrap items-baseline gap-2 py-2 text-[13px]">
            <span className="font-medium text-ink">{roleWords(one.role)}</span>
            <span className="text-dim">{lines.length === 0 ? "over the whole company" : `over ${lines.join("; ")}`}</span>
            {one.deputyOf === undefined ? null : <span className="text-dim">as a deputy</span>}
            {one.notAfter === undefined ? null : <span className="text-dim">until {dayWords(one.notAfter)}</span>}
          </li>
        );
      })}
    </ul>
  );
}

function Usable({ principalId }: { readonly principalId: string }) {
  const me = useResource<unknown>(ME_API_PATH);
  const own = readMe(me.data);
  if (me.data === null || own.principalId !== principalId) {
    return <p className="m-0 text-[13px] text-body">{WHAT_NEEDS_A_SECOND_FACTOR}</p>;
  }
  if (own.withheldVerbs.length === 0) {
    return <p className="m-0 text-[13px] text-body">Nothing you hold is held back by this sign-in.</p>;
  }
  return (
    <p className="m-0 text-[13px] text-body">
      With this sign-in you cannot use what you hold for {own.withheldVerbs.map((one) => VERB_WORDS[one] ?? one).join(", ")}.
      {own.secondFactorNeeded ? " Signing in again with your authenticator gives it back." : ""}
    </p>
  );
}

export function PersonAccess({ detail }: { readonly detail: PersonDetail }) {
  const { person, placements } = detail;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title={HOLDS_HEADING}
        lede="Every grant you may be told about, by where it came from."
        action={
          <Link to={personAddress(person.principalId, "grants")} className="text-[12.5px] text-acc-text underline-offset-4 hover:underline">
            Change on Grants
          </Link>
        }
      >
        <Holds detail={detail} />
      </SectionCard>
      <SectionCard
        title={ROLES_HEADING}
        lede={A_ROLE_GRANTS_NOTHING}
        action={
          <Link to={WORKS_AT.roles} className="text-[12.5px] text-acc-text underline-offset-4 hover:underline">
            Roles
          </Link>
        }
      >
        <Roles principalId={person.principalId} />
      </SectionCard>
      <SectionCard title={USABLE_HEADING} lede="A grant held is not always usable from every sign-in.">
        <Usable principalId={person.principalId} />
      </SectionCard>
      <SectionCard title="Where they sit" lede="Where somebody sits changes nobody's access; it bounds what a scope over a department reaches.">
        <p className="m-0 text-[13px] text-body">
          {placements.department === undefined ? "Not placed in a department you may see." : placements.department.name}
          {placements.teams.length === 0 ? "" : `, in ${placements.teams.map((one) => one.name).join(", ")}`}
          {placements.leads.length === 0 ? "" : `; leads ${placements.leads.map((one) => one.name).join(", ")}`}
        </p>
      </SectionCard>
      <SectionCard
        title={THROUGH_AN_AGENT_HEADING}
        lede="An agent reaches, for the person using it, only what that person may reach and its own limits allow."
        action={<Bot aria-hidden className="size-4 text-dim" />}
      >
        <div className="flex flex-col gap-3">
          <PersonPreview principalId={person.principalId} />
          <Note>
            Who can reach something is asked of a capability over a scope, on the Capabilities screen, and never of a single record.
          </Note>
        </div>
      </SectionCard>
    </div>
  );
}
