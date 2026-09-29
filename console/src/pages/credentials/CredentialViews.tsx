/**
 * One slot's three views, in SCREEN 14's order: Dashboard (where it stands), Profile (what it is
 * for, what to ask the issuer for, and set or replace), About (how it is used, and its history from
 * the audit ledger).
 *
 * **Each view draws only what the API sent this reader.** A last use the API left out is "not
 * recorded yet", with the API's reason where nothing records one for this kind; a history the API
 * could not read is its sentence and no table. The vault path and the ids the ledger names writers
 * by are in Advanced, the one place a page may show an identifier.
 *
 * Task ids: M27.11.10, M27.15.50
 */

import { Link } from "react-router-dom";
import {
  Advanced,
  Fact,
  FactList,
  Note,
  NotOffered,
  NOT_RECORDED,
  SectionCard,
  UnavailableAction,
} from "../../components/kit";
import { NOT_REMOVED, UNAVAILABLE, WORKS_AT } from "./credentialActions";
import { READ_BY_WORDS, stateWords, whenWords, type CredentialDetail } from "./credentialRows";
import { SetValueForm } from "./SetValueForm";

export const WHERE_IT_STANDS = "Where it stands";
export const WHAT_IT_IS_FOR = "What it is for";
export const SET_OR_REPLACE_HEADING = "Set or replace";
export const SET_OR_REPLACE_LEDE = "The value goes into the vault and is never shown again, here or anywhere.";
export const HOW_IT_IS_USED = "How it is used";
export const HISTORY_HEADING = "History";
export const NO_CHANGES = "No value has been written into this slot from the console or the setup wizard.";
export const NO_HINTS = "Nothing is recorded about what to ask the issuer of this credential for.";
export const ASK_FOR = "Ask the issuer for";
export const NEVER_ASK = "Never ask for";
export const VALUE_LABEL = "Value";
export const LAST_SET_LABEL = "Last set";
export const LAST_USED_LABEL = "Last used";
export const READ_BY_LABEL = "Read by";
export const NEW_VALUE_LABEL = "A new value is used";
export const SLOT_LABEL = "Vault slot";
export const CHECK_ON_MODELS = "Check this provider on Models";
export const CONNECT_ON_CONNECTORS = "Open Connectors";
export const RELAY_SETTINGS = "Relay settings and a test message";
export const CHECK_SOURCE = "Check the key";

/** The anchor the header's Set or replace button opens the Profile at. */
export const SET_VALUE_ANCHOR = "set-value";

function Lines({ lines }: { readonly lines: readonly string[] }) {
  return lines.length === 1 ? (
    <>{lines[0]}</>
  ) : (
    <ul className="m-0 flex list-disc flex-col gap-1 pl-4">
      {lines.map((one) => (
        <li key={one}>{one}</li>
      ))}
    </ul>
  );
}

export function CredentialDashboard({ detail }: { readonly detail: CredentialDetail }) {
  const { row } = detail;
  const outranked = row.outrankedBy !== undefined;
  return (
    <SectionCard
      title={WHERE_IT_STANDS}
      footer={
        outranked || !row.writable || detail.history?.length === 0 ? (
          <>
            {outranked ? <Note kind="not-yet">{detail.takesEffectTold}</Note> : null}
            {row.writable ? null : <Note>{row.writeTold}</Note>}
            {detail.history?.length === 0 ? <Note>{NO_CHANGES}</Note> : null}
          </>
        ) : undefined
      }
    >
      <FactList>
        <Fact label={VALUE_LABEL}>{stateWords(row.state)}</Fact>
        <Fact label={LAST_SET_LABEL}>{whenWords(row.setAt) ?? NOT_RECORDED}</Fact>
        <Fact label={LAST_USED_LABEL}>
          {whenWords(detail.lastUsedAt) ?? NOT_RECORDED}
          <span className="mt-0.5 block text-[12px] text-dim">{detail.lastUsedTold}</span>
        </Fact>
      </FactList>
    </SectionCard>
  );
}

function ElsewhereLinks({ detail }: { readonly detail: CredentialDetail }) {
  const kind = detail.row.kind;
  const link = "text-[12.5px] text-acc-text underline-offset-4 hover:underline";
  return (
    <div className="flex flex-wrap items-center gap-3">
      {kind === "provider" ? (
        <Link to={WORKS_AT.models} className={link}>
          {CHECK_ON_MODELS}
        </Link>
      ) : null}
      {kind === "connector" ? (
        <>
          <Link to={WORKS_AT.connectors} className={link}>
            {CONNECT_ON_CONNECTORS}
          </Link>
          <UnavailableAction label={CHECK_SOURCE} text={CHECK_SOURCE} reason={UNAVAILABLE.checkSource.reason} />
        </>
      ) : null}
      {kind === "relay" ? (
        <Link to={WORKS_AT.notifications} className={link}>
          {RELAY_SETTINGS}
        </Link>
      ) : null}
    </div>
  );
}

export function CredentialProfile({
  detail,
  saved,
  onSaved,
}: {
  readonly detail: CredentialDetail;
  /** The API's sentence after the last save on this page, if any. */
  readonly saved: string | null;
  readonly onSaved: (sentence: string) => void;
}) {
  const { row } = detail;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title={WHAT_IT_IS_FOR} lede={detail.description === "" ? undefined : detail.description}>
        {detail.askFor.length === 0 && detail.never.length === 0 ? <p className="m-0 text-[12.5px] text-dim">{NO_HINTS}</p> : null}
        <FactList>
          {detail.askFor.length > 0 ? (
            <Fact label={ASK_FOR}>
              <Lines lines={detail.askFor} />
            </Fact>
          ) : null}
          {detail.never.length > 0 ? (
            <Fact label={NEVER_ASK}>
              <Lines lines={detail.never} />
            </Fact>
          ) : null}
        </FactList>
      </SectionCard>
      <SectionCard
        id={SET_VALUE_ANCHOR}
        title={SET_OR_REPLACE_HEADING}
        lede={SET_OR_REPLACE_LEDE}
        footer={
          <>
            <NotOffered>{NOT_REMOVED}</NotOffered>
            <ElsewhereLinks detail={detail} />
          </>
        }
      >
        <div className="flex min-w-0 flex-col gap-3">
          {saved === null ? null : <Note kind="done">{saved}</Note>}
          {row.writable ? <SetValueForm detail={detail} onSaved={onSaved} /> : <Note>{row.writeTold}</Note>}
        </div>
      </SectionCard>
    </div>
  );
}

export function CredentialAbout({ detail }: { readonly detail: CredentialDetail }) {
  const { row } = detail;
  const writers = [...new Set((detail.history ?? []).map((one) => one.byId).filter((one) => one !== ""))];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title={HOW_IT_IS_USED}>
        <FactList>
          {row.readBy === undefined ? null : <Fact label={READ_BY_LABEL}>{READ_BY_WORDS[row.readBy] ?? row.readBy}</Fact>}
          <Fact label={NEW_VALUE_LABEL}>{detail.takesEffectTold}</Fact>
        </FactList>
      </SectionCard>
      <SectionCard title={HISTORY_HEADING} footer={<Note>{detail.historyTold}</Note>}>
        {detail.history === null ? null : detail.history.length === 0 ? (
          <p className="m-0 text-[12.5px] text-dim">{NO_CHANGES}</p>
        ) : (
          <div className="overflow-x-auto">
            <table aria-label={HISTORY_HEADING} className="w-full min-w-[20rem] border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] text-dim">
                  <th scope="col" className="py-1.5 pr-3 font-medium">
                    When
                  </th>
                  <th scope="col" className="py-1.5 font-medium">
                    Written by
                  </th>
                </tr>
              </thead>
              <tbody>
                {detail.history.map((one, index) => (
                  <tr key={`${one.at}-${String(index)}`} className="border-b border-line last:border-b-0">
                    <td className="py-1.5 pr-3 font-mono text-[12px] whitespace-nowrap tabular-nums">{whenWords(one.at)}</td>
                    <td className="py-1.5 text-ink">{one.by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
      <Advanced>
        <FactList>
          <Fact label={SLOT_LABEL}>
            <code className="font-mono text-[12px]">{row.slot}</code>
          </Fact>
          {writers.length === 0 ? null : (
            <Fact label="Writers' ids">
              <code className="font-mono text-[12px]">{writers.join(", ")}</code>
            </Fact>
          )}
        </FactList>
      </Advanced>
    </div>
  );
}
