/**
 * An agent's Memory section: what it remembers as readable text, stated apart from inferred, what it
 * keeps about the reader, every change with its diff, and how it learns, tier by tier.
 *
 * **Every list is the route's, drawn as sent.** A list the API sent empty says it is empty in one
 * sentence; a list it left out is not drawn, and nothing counts what was left out. Tier three is
 * drawn only when sent, which is for a reader who may be shown where gated changes went.
 *
 * **Correcting and deleting are confirmed, and offered only where the API said so.** A memory the
 * reader may change carries Correct and Delete; the correction says its format before anything is
 * sent, and both ask first, because a delete stops the memory being recalled for everybody and a
 * correction replaces what it says. The undo of an automatic change is the Learning screen's own
 * route, offered on the rows the API marked, and confirmed the same way.
 *
 * Task ids: M39.4.1.1, M39.4.1.2, M39.4.1.3, M39.4.1.4, M39.4.1.5, M39.4.2.1, M39.4.2.2, M39.4.2.4
 */

import { Brain } from "lucide-react";
import { useCallback, useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { dayWords } from "../access/formParts";
import { TIER_WORDS, UNDO_API_PATH, undoBody } from "../learningQuery";
import { changeWords } from "../learning/learningActions";
import { WORKS_AT } from "./agentActions";
import {
  PROVENANCE_WORDS,
  agentMemoryApiPath,
  memoryDeletionApiPath,
  memoryEditApiPath,
  readAgentMemory,
  type AgentMemory as Memory,
  type MemoryItem,
  type MemoryStep,
} from "./agentMemoryQuery";

export const MEMORY_HEADING = "What it remembers";
export const ABOUT_YOU_HEADING = "What it keeps about you";
export const HISTORY_HEADING = "Every change";
export const LEARNING_HEADING = "How it learns";
export const NOTHING_REMEMBERED = "Nothing you may read is remembered yet.";
export const NOTHING_ABOUT_YOU = "It keeps nothing about you.";
export const CORRECTION_FORMAT = "What the memory should say instead, in one or two sentences of up to 500 characters.";
export const CORRECTION_NEEDED = "Type what the memory should say before correcting it.";
export const LOADING_MEMORY = "Loading what this agent remembers.";

type Asking =
  | { readonly kind: "delete"; readonly item: MemoryItem }
  | { readonly kind: "edit"; readonly item: MemoryItem; readonly statement: string }
  | { readonly kind: "undo"; readonly memoryId: string; readonly change: string };

function Confidence({ value }: { readonly value: number }) {
  return <span className="font-mono text-[11px] text-dim">{`${String(Math.round(value * 100))}% sure`}</span>;
}

function MemoryRow({
  item,
  onAsk,
}: {
  readonly item: MemoryItem;
  readonly onAsk: (asking: Asking) => void;
}) {
  const inputId = useId();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.statement);
  const [said, setSaid] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (text.trim() === "") {
      setSaid(CORRECTION_NEEDED);
      return;
    }
    setSaid(null);
    onAsk({ kind: "edit", item, statement: text.trim() });
  };
  return (
    <li data-slot="memory-item" className="flex flex-col gap-1 border-b border-line py-2.5 text-[13px] last:border-b-0">
      <p className="m-0 text-ink [overflow-wrap:anywhere]">{item.statement}</p>
      <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-dim">
        <span>{PROVENANCE_WORDS[item.provenance] ?? item.provenance}</span>
        <span>{dayWords(item.formedAt)}</span>
        <Confidence value={item.confidence} />
        {item.aboutYou ? <span>about you</span> : null}
        {item.changeable ? (
          <span className="ml-auto flex gap-1">
            <Button variant="ghost" size="xs" aria-expanded={editing} onClick={() => setEditing((was) => !was)}>
              Correct
            </Button>
            <Button variant="ghost" size="xs" onClick={() => onAsk({ kind: "delete", item })}>
              Delete
            </Button>
          </span>
        ) : null}
      </div>
      {editing ? (
        <form onSubmit={submit} className="flex flex-col gap-1.5 pt-1">
          <Label htmlFor={inputId}>Correct this memory</Label>
          <Textarea id={inputId} value={text} maxLength={500} onChange={(event) => setText(event.target.value)} aria-describedby={`${inputId}-format`} />
          <span id={`${inputId}-format`} className="text-[11.5px] text-dim">
            {CORRECTION_FORMAT}
          </span>
          {said === null ? null : (
            <p role="alert" className="m-0 text-[12px] text-crit">
              {said}
            </p>
          )}
          <div>
            <Button type="submit" size="sm" variant="outline" className="min-h-11 sm:min-h-8">
              Save correction
            </Button>
          </div>
        </form>
      ) : null}
    </li>
  );
}

function MemoryList({ items, empty, onAsk }: { readonly items: readonly MemoryItem[]; readonly empty: string; readonly onAsk: (asking: Asking) => void }) {
  if (items.length === 0) {
    return <Note>{empty}</Note>;
  }
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {items.map((one) => (
        <MemoryRow key={one.memoryId} item={one} onAsk={onAsk} />
      ))}
    </ul>
  );
}

function stepWords(step: MemoryStep): string {
  if (step.correction === "demoted") {
    return "Stopped being recalled";
  }
  return step.replacedId === undefined ? "Formed" : "Replaced an earlier memory";
}

function History({ steps }: { readonly steps: readonly MemoryStep[] }) {
  if (steps.length === 0) {
    return <Note>Nothing has changed yet.</Note>;
  }
  return (
    <ol data-slot="memory-history" className="m-0 flex list-none flex-col p-0">
      {steps.map((one) => (
        <li key={`${one.memoryId}-${one.at}`} className="flex flex-col gap-1 border-b border-line py-2 text-[12.5px] last:border-b-0">
          <span className="text-ink">
            {stepWords(one)} <span className="text-dim">{dayWords(one.at)}</span>
            {one.trigger === undefined ? null : <span className="text-dim">{` · because it was ${one.trigger.replace(/_/g, " ")}`}</span>}
          </span>
          {one.diff.length === 0 ? null : (
            <pre className="m-0 overflow-x-auto rounded-sm bg-sunk p-2 font-mono text-[11.5px] whitespace-pre-wrap">
              {one.diff.map((line) => (
                <span key={line} className={line.startsWith("+") ? "block text-ok" : line.startsWith("-") ? "block text-crit" : "block text-dim"}>
                  {line}
                </span>
              ))}
            </pre>
          )}
        </li>
      ))}
    </ol>
  );
}

function Tiers({ memory, onAsk }: { readonly memory: Memory; readonly onAsk: (asking: Asking) => void }) {
  return (
    <SectionCard
      title={LEARNING_HEADING}
      lede="What it may learn from answered questions, ordered by how far a change would reach."
      action={<Brain aria-hidden className="size-4 text-dim" />}
      footer={
        <Link to={WORKS_AT.learning} className="w-fit text-[12px] text-acc-text underline-offset-4 hover:underline">
          Open the learning review
        </Link>
      }
    >
      <ol data-slot="learning-tiers" className="m-0 flex list-none flex-col p-0">
        {[0, 1, 2, 3].map((tier) => (
          <li key={tier} className="[display:grid] grid-cols-[1.5rem_minmax(0,1fr)_auto] gap-x-2 border-b border-line py-2 text-[13px] last:border-b-0">
            <span className="font-mono text-[11px] text-dim">{tier}</span>
            <span className="text-ink">{TIER_WORDS[tier]?.what ?? String(tier)}</span>
            <span className="text-[11.5px] text-dim">{memory.activeTiers.includes(tier) ? "Active" : tier === 3 ? "A person decides" : "Off"}</span>
          </li>
        ))}
      </ol>
      {memory.tierOne.length === 0 ? null : (
        <div className="mt-3">
          <h3 className="m-0 mb-1 text-[13px] font-medium text-ink">Applied by itself</h3>
          <ul data-slot="tier-one" className="m-0 flex list-none flex-col p-0">
            {memory.tierOne.map((one) => (
              <li key={one.memoryId} className="flex flex-wrap items-center gap-2 border-b border-line py-1.5 text-[12.5px] last:border-b-0">
                <span className="text-ink">{changeWords(one.change)}</span>
                <span className="text-dim">{dayWords(one.learnedAt)}</span>
                {one.inEffect ? null : <span className="text-dim">undone</span>}
                {one.undoOffered ? (
                  <Button className="ml-auto" variant="ghost" size="xs" onClick={() => onAsk({ kind: "undo", memoryId: one.memoryId, change: one.change })}>
                    Undo
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}
      {memory.tierTwo.length === 0 ? null : (
        <div className="mt-3">
          <h3 className="m-0 mb-1 text-[13px] font-medium text-ink">Proving itself in shadow</h3>
          <ul data-slot="tier-two" className="m-0 flex list-none flex-col p-0">
            {memory.tierTwo.map((one) => (
              <li key={one.memoryId} className="flex flex-wrap items-center gap-2 border-b border-line py-1.5 text-[12.5px] last:border-b-0">
                <span className="text-ink">{changeWords(one.change)}</span>
                <span className="text-dim">{one.evidence.length === 0 ? "no evidence yet" : `noticed: ${one.evidence.join(", ")}`}</span>
                <span className="text-dim">{one.promoteReady ? "ready to promote" : "not yet agreed by separate conversations"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {memory.tierThree === undefined || memory.tierThree.length === 0 ? null : (
        <div className="mt-3">
          <h3 className="m-0 mb-1 text-[13px] font-medium text-ink">Waiting for a person</h3>
          <ul data-slot="tier-three" className="m-0 flex list-none flex-col p-0">
            {memory.tierThree.map((one) => (
              <li key={one.memoryId} className="flex flex-wrap items-center gap-2 border-b border-line py-1.5 text-[12.5px] last:border-b-0">
                <span className="text-ink">{`In the ${one.department} department's review`}</span>
                <Link to={WORKS_AT.learning} className="text-[12px] text-acc-text underline-offset-4 hover:underline">
                  Decide it there
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

export function AgentMemory({ agentId }: { readonly agentId: string }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentMemoryApiPath(agentId), version);
  const [asking, setAsking] = useState<Asking | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const onAsk = useCallback((next: Asking) => {
    setAsking(next);
  }, []);

  const decide = async (one: Asking): Promise<void> => {
    setBusy(true);
    const result =
      one.kind === "delete"
        ? await request<unknown>(memoryDeletionApiPath(agentId, one.item.memoryId), { method: "POST" })
        : one.kind === "edit"
          ? await request<unknown>(memoryEditApiPath(agentId, one.item.memoryId), { method: "POST", body: { statement: one.statement } })
          : await request<unknown>(UNDO_API_PATH, { method: "POST", body: undoBody(one.memoryId) });
    setBusy(false);
    setAsking(null);
    setSaid(result.ok ? null : result.failure.message);
    setVersion((count) => count + 1);
  };

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  const memory = answer.data === null ? null : readAgentMemory(answer.data);
  if (answer.busy || memory === null) {
    return <LoadingState label={LOADING_MEMORY} />;
  }
  return (
    <div data-slot="agent-memory" className="flex min-w-0 flex-col gap-4">
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12.5px] text-crit">
          {said}
        </p>
      )}
      <div className="[display:grid] min-w-0 gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <SectionCard title={MEMORY_HEADING} lede="What this agent learnt, as the words it keeps. Stated by a person, then inferred from how people asked.">
            <div data-slot="memory-curated">
              <MemoryList items={memory.curated} empty={NOTHING_REMEMBERED} onAsk={onAsk} />
            </div>
            {memory.extracted.length === 0 ? null : (
              <div data-slot="memory-extracted" className="mt-3">
                <h3 className="m-0 mb-1 text-[13px] font-medium text-ink">Inferred</h3>
                <MemoryList items={memory.extracted} empty="" onAsk={onAsk} />
              </div>
            )}
          </SectionCard>
          <SectionCard title={ABOUT_YOU_HEADING} lede="What it keeps about you from your own conversations, apart from what it learnt overall.">
            <div data-slot="memory-about-you">
              <MemoryList items={memory.aboutYou} empty={NOTHING_ABOUT_YOU} onAsk={onAsk} />
            </div>
          </SectionCard>
          <SectionCard title={HISTORY_HEADING} lede="Each change to what it remembers, with what changed and why.">
            <History steps={memory.history} />
          </SectionCard>
        </div>
        <Tiers memory={memory} onAsk={onAsk} />
      </div>
      <ConfirmDialog
        open={asking !== null}
        question={asking === null ? "" : asking.kind === "delete" ? "Delete this memory?" : asking.kind === "edit" ? "Save this correction?" : `Undo ${changeWords(asking.change).toLowerCase()}?`}
        consequence={
          asking?.kind === "delete"
            ? "It stops being recalled for everybody from now on. It stays on the record, and the delete is on the audit log."
            : asking?.kind === "edit"
              ? "The corrected words replace what it said from now on. The earlier words stay in the history, and the change is on the audit log."
              : "The change stops taking effect from now on, and the undo is on the audit log."
        }
        details={asking?.kind === "edit" ? <p className="m-0 text-[13px] text-ink">{asking.statement}</p> : undefined}
        confirmLabel={asking?.kind === "delete" ? "Delete" : asking?.kind === "edit" ? "Save correction" : "Undo"}
        cancelLabel="Keep it"
        danger={asking?.kind !== "edit"}
        busy={busy}
        onConfirm={() => {
          if (asking !== null) {
            void decide(asking);
          }
        }}
        onCancel={() => setAsking(null)}
      />
    </div>
  );
}
