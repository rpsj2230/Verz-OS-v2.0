/**
 * The Profile's capability detail: connectors with the fields they project and the health the
 * Connectors page last saw, skills with their version, source, review and runs and the library's
 * offers, the knowledge the agent draws on as a predicate, and a preview of one person's run.
 *
 * **Every block is drawn from `agentCapabilitiesQuery.ts` and from nothing else.** A block the API
 * sent nothing for is absent, not empty under a heading, which would be a count of hidden things in
 * words. A connector row's overflow opens the reader's own rows and never a row the strip did not
 * already count.
 *
 * **Attaching and taking off a skill are the Skills page's routes, confirmed first.** An approved
 * library skill is offered to attach and anything unreviewed only with a link to its review, never
 * both; the server decides again when either is pressed and its refusal is shown in its words.
 *
 * **A preview is the gate's answer for one person.** The form takes a person's user id, says so
 * before anything is sent, and draws the tools that person's run would be handed and the strictest
 * rung it would be held to, or the one sentence every refusal shares.
 *
 * Task ids: M39.2.1.1, M39.2.1.3, M39.2.1.4, M39.2.1.5, M39.2.2.1, M39.2.2.2, M39.2.2.3
 * Task ids: M39.2.2.4, M39.2.3.1, M39.2.3.2, M39.2.3.3, M39.2.3.4, M39.3.1.4
 */

import { BookOpen, Plus, Sparkles, X } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import { Chip, ConfirmDialog, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { healthWords } from "../connectors/connectorSources";
import { ReviewPill } from "../skills/pills";
import {
  SOURCE_WORDS,
  agentPreviewApiPath,
  clauseWords,
  readPreview,
  skillAssignApiPath,
  skillDetachApiPath,
  type ConnectorDetail,
  type KnowledgeSlice,
  type Preview,
  type SkillChip,
  type SkillOffer,
} from "./agentCapabilitiesQuery";
import { rungWords } from "./agentActions";

/** How many connectors the row draws before the rest become the reader's own "N more". */
export const CONNECTORS_ON_THE_ROW = 5;

export const KNOWLEDGE_HEADING = "Knowledge";
export const NARROWS_NOTHING = "It narrows nothing of its own: it draws on whatever the person it works for may read.";
export const ADD_DOCUMENT = "Add a document or a link";
export const ADD_SKILL = "Add a skill";
export const PREVIEW_HEADING = "Preview as a person";
export const PREVIEW_FORMAT = "Their user id, as the People page shows it.";
export const PREVIEW_NEEDED = "Type whose run to preview.";

/** A source's monogram, the icon a connector is drawn with: its own name, so no second registry. */
export function monogram(source: string): string {
  const letters = source.replace(/[^a-z0-9]/gi, "");
  return (letters.slice(0, 2) || "?").toUpperCase();
}

function ConnectorChip({ one }: { readonly one: ConnectorDetail }) {
  const icon = (
    <span aria-hidden className="inline-flex size-4 items-center justify-center rounded-[3px] bg-sunk font-mono text-[8.5px] font-semibold text-dim">
      {monogram(one.source)}
    </span>
  );
  const health = one.health === undefined ? null : ` · ${healthWords(one.health)}`;
  const title = one.projects.length === 0 ? undefined : one.projects.join(", ");
  // The word says it and the dashed edge repeats it, so the difference is never colour alone.
  return one.presence === "attached" ? (
    <Chip mono icon={icon} title={title}>
      {one.source}
      {health}
    </Chip>
  ) : (
    <Chip mono icon={icon} tone="requested" title={title}>
      {`${one.source} · ${one.presence}`}
      {health}
    </Chip>
  );
}

export function ConnectorsDetail({ connectors }: { readonly connectors: readonly ConnectorDetail[] }) {
  const [open, setOpen] = useState(false);
  if (connectors.length === 0) {
    return null;
  }
  const shown = open ? connectors : connectors.slice(0, CONNECTORS_ON_THE_ROW);
  const more = connectors.length - CONNECTORS_ON_THE_ROW;
  const projecting = connectors.filter((one) => one.projects.length > 0);
  return (
    <div data-slot="connector-detail" className="flex min-w-0 flex-col gap-2">
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        {shown.map((one) => (
          <ConnectorChip key={one.source} one={one} />
        ))}
        {more > 0 ? (
          <Button variant="ghost" size="xs" aria-expanded={open} onClick={() => setOpen((was) => !was)}>
            {open ? "Show fewer" : `${String(more)} more`}
          </Button>
        ) : null}
      </div>
      {projecting.length === 0 ? null : (
        <ul data-slot="connector-fields" className="m-0 flex list-none flex-col gap-1 p-0 text-[12px] text-body">
          {projecting.map((one) => (
            <li key={one.source} className="[overflow-wrap:anywhere]">
              <span className="font-mono text-[11.5px] text-ink">{one.source}</span> shows your run: {one.projects.join(", ")}
            </li>
          ))}
        </ul>
      )}
      <Note>Attached means the agent is set up to use the source; requested means it asks for one nothing links yet. Health is the Connectors page's last check.</Note>
    </div>
  );
}

interface Asking {
  readonly kind: "attach" | "detach";
  readonly name: string;
  readonly version?: string | undefined;
  readonly digest: string;
}

export function SkillsDetail({
  agentId,
  skills,
  offers,
  editable,
  unused,
  basis,
  onChanged,
}: {
  readonly agentId: string;
  readonly skills: readonly SkillChip[];
  readonly offers: readonly SkillOffer[];
  readonly editable: boolean;
  readonly unused: readonly string[];
  readonly basis: string | undefined;
  readonly onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [asking, setAsking] = useState<Asking | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Sent only from the confirmation below, which names the skill and the agent.
  const decide = async (one: Asking): Promise<void> => {
    setBusy(true);
    const path = one.kind === "attach" ? skillAssignApiPath(one.digest) : skillDetachApiPath(one.digest);
    const result = await request<unknown>(path, { method: "POST", body: { agent_id: agentId } });
    setBusy(false);
    setAsking(null);
    if (!result.ok) {
      setSaid(result.failure.message);
      return;
    }
    setSaid(null);
    onChanged();
  };
  if (skills.length === 0 && offers.length === 0) {
    return null;
  }
  const whose = basis === "own" ? "your runs" : "all runs";
  return (
    <div data-slot="skill-detail" className="flex min-w-0 flex-col gap-2">
      <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
        {skills.map((one) => (
          <li key={one.digest} data-slot="skill-chip" className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-panel py-1 pr-1 pl-2.5 text-[12.5px]">
            <Sparkles aria-hidden className="size-3.5 shrink-0 text-dim" />
            <span className="min-w-0 font-mono text-[11.5px] text-ink [overflow-wrap:anywhere]">{one.name}</span>
            {one.version === undefined ? null : <span className="font-mono text-[11px] text-dim">{one.version}</span>}
            {one.review === undefined ? null : <ReviewPill review={one.review} />}
            <span className="text-[11px] text-dim">{`${String(one.runs)} ${one.runs === 1 ? "run" : "runs"}`}</span>
            {one.source === undefined ? null : <span className="text-[11px] text-dim">{SOURCE_WORDS[one.source] ?? one.source}</span>}
            {one.detachable ? (
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Take ${one.name} off this agent`}
                onClick={() => setAsking({ kind: "detach", name: one.name, version: one.version, digest: one.digest })}
              >
                <X aria-hidden />
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {skills.length === 0 ? null : <Note>{`Runs are counted over 30 days of ${whose}.${unused.length === 0 ? "" : ` Not used in that time: ${unused.join(", ")}.`}`}</Note>}
      {offers.length === 0 ? null : (
        <div className="flex flex-col gap-2">
          <div>
            <Button variant="outline" size="xs" aria-expanded={adding} onClick={() => setAdding((was) => !was)}>
              <Plus aria-hidden /> {ADD_SKILL}
            </Button>
          </div>
          {adding ? (
            <ul data-slot="skill-offers" className="m-0 flex list-none flex-col rounded-md border border-line p-0">
              {offers.map((one) => (
                <li key={one.digest} className="[display:grid] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line px-3 py-2 last:border-b-0">
                  <span className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <span className="font-mono text-[11.5px] text-ink [overflow-wrap:anywhere]">{one.name}</span>
                    <span className="font-mono text-[11px] text-dim">{one.version}</span>
                    <ReviewPill review={one.review} />
                  </span>
                  {one.control === "attach" ? (
                    <Button variant="outline" size="xs" onClick={() => setAsking({ kind: "attach", name: one.name, version: one.version, digest: one.digest })}>
                      Attach
                    </Button>
                  ) : one.control === "review" ? (
                    <Link to={one.route} className="text-[12px] text-acc-text underline-offset-4 hover:underline">
                      Send to review
                    </Link>
                  ) : (
                    <span className="text-[12px] text-dim">Waiting for a reviewer</span>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12px] text-crit">
          {said}
        </p>
      )}
      {editable || asking !== null ? (
        <ConfirmDialog
          open={asking !== null}
          question={asking === null ? "" : asking.kind === "attach" ? `Attach ${asking.name} ${asking.version ?? ""} to this agent?` : `Take ${asking.name} off this agent?`}
          consequence={
            asking?.kind === "attach"
              ? "The agent is pinned to this approved version and can use it from its next run. The attachment is recorded on the audit log."
              : "The agent stops using this skill from its next run. The version stays in the library, and the removal is recorded on the audit log."
          }
          confirmLabel={asking?.kind === "attach" ? "Attach" : "Take it off"}
          cancelLabel="Keep it as it is"
          danger={asking?.kind === "detach"}
          busy={busy}
          onConfirm={() => {
            if (asking !== null) {
              void decide(asking);
            }
          }}
          onCancel={() => setAsking(null)}
        />
      ) : null}
    </div>
  );
}

function Figure({ label, value }: { readonly label: string; readonly value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11.5px] text-dim">{label}</dt>
      <dd className="m-0 font-mono text-[15px] text-ink">{value}</dd>
    </div>
  );
}

export function KnowledgeCard({ knowledge, onWiden }: { readonly knowledge: KnowledgeSlice; readonly onWiden?: (() => void) | undefined }) {
  const described = knowledge.clauses.length === 0 ? NARROWS_NOTHING : `It draws on ${knowledge.clauses.map(clauseWords).join(", and ")}.`;
  const atLeast = knowledge.atLeast ? "at least " : "";
  return (
    <SectionCard
      title={KNOWLEDGE_HEADING}
      lede="What this agent draws on, as a rule about where documents sit rather than a list of documents."
      action={<BookOpen aria-hidden className="size-4 text-dim" />}
      footer={
        <div className="flex flex-wrap items-center gap-3">
          <Link to="/knowledge" className="text-[12px] text-acc-text underline-offset-4 hover:underline">
            {ADD_DOCUMENT}
          </Link>
          {onWiden === undefined ? null : (
            <Button variant="ghost" size="xs" onClick={onWiden}>
              Widen what it draws on, through a draft
            </Button>
          )}
        </div>
      }
    >
      <p data-slot="knowledge-predicate" className="m-0 text-[13px] text-ink">
        {described}
      </p>
      <dl data-slot="knowledge-slice" className="m-0 mt-3 [display:grid] grid-cols-2 gap-3 sm:grid-cols-4">
        <Figure label="Of your documents, it meets" value={`${atLeast}${String(knowledge.matched)}`} />
        <Figure label="Verified" value={String(knowledge.verified)} />
        <Figure label="Due for review" value={String(knowledge.stale)} />
        <Figure label="Not verified" value={String(knowledge.unverified)} />
      </dl>
      <div className="mt-2">
        <Note>Counted over the documents you may read. A document added where this rule does not reach is not drawn on until the rule is widened.</Note>
      </div>
    </SectionCard>
  );
}

export function PreviewForm({ agentId }: { readonly agentId: string }) {
  const inputId = useId();
  const [person, setPerson] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState<Preview | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (person.trim() === "") {
      setSaid(PREVIEW_NEEDED);
      return;
    }
    setBusy(true);
    const result = await request<unknown>(agentPreviewApiPath(agentId), { method: "POST", body: { person_id: person.trim() } });
    setBusy(false);
    if (!result.ok) {
      setShown(null);
      setSaid(result.failure.message);
      return;
    }
    setSaid(null);
    setShown(readPreview(result.data));
  };
  return (
    <div data-slot="agent-preview" className="flex flex-col gap-2">
      <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-1.5">
        <Label htmlFor={inputId}>{PREVIEW_HEADING}</Label>
        <div className="flex flex-wrap gap-2">
          <Input id={inputId} value={person} onChange={(event) => setPerson(event.target.value)} aria-describedby={`${inputId}-format`} className="max-w-72" />
          <Button type="submit" size="sm" variant="outline" disabled={busy} className="min-h-11 sm:min-h-8">
            Preview
          </Button>
        </div>
        <span id={`${inputId}-format`} className="text-[11.5px] text-dim">
          {PREVIEW_FORMAT}
        </span>
      </form>
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12px] text-crit">
          {said}
        </p>
      )}
      {shown === null ? null : (
        <div data-slot="preview-result" className="rounded-md border border-line p-3 text-[13px]">
          {shown.tools.length === 0 ? (
            <p className="m-0 text-body">{shown.notice ?? "This person's run of this agent would return nothing."}</p>
          ) : (
            <>
              <p className="m-0 text-body">
                {`${shown.personName ?? shown.personId}'s run would be handed ${String(shown.tools.length)} ${shown.tools.length === 1 ? "action" : "actions"}`}
                {shown.rung === undefined ? "." : `, held at ${rungWords(shown.rung)}.`}
              </p>
              <ul className="m-0 mt-2 flex list-disc flex-col gap-0.5 pl-4">
                {shown.tools.map((one) => (
                  <li key={one.name}>{one.description ?? one.name}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
