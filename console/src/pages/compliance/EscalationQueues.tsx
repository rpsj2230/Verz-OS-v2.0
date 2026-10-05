/**
 * Escalation queues on the Compliance screen: who answers for each queue a skill hands its unanswered
 * questions to, and where they are reached (M8.3.2).
 *
 * **On this screen, under its authority, because it is the same decision as a sensitive topic's.**
 * `brain.escalation_routes` asks `admin:compliance` for the list and the form, as
 * `brain.compliance_routes` does for the topics: routing a question to a named person instead of
 * answering it is one kind of decision, made by one person.
 *
 * **A queue is named by a skill and a person by this form.** A skill's author writes the queue's
 * name; this form says who answers for it, on which channel and at which address there. The
 * channels offered are the API's list of those a message can be sent on, and nothing else can be
 * chosen. A queue nobody has named yet is typed in by its name, which the skill that declares it
 * shows.
 *
 * **Every naming is confirmed**, because it replaces whoever was named: the questions handed to the
 * queue from then on reach the person named here, and the confirmation says so in those words.
 *
 * Task ids: M8.3.2
 */

import { MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
  Drawer,
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  SectionCard,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { Input } from "../../components/ui/input";
import { Field, FormProblem, NativeSelect } from "../access/formParts";
import { whenWords } from "../review/parts";

export const ESCALATION_ROUTES_API_PATH = "/govern/escalation-routes";

export function escalationRouteApiPath(queue: string): string {
  return `${ESCALATION_ROUTES_API_PATH}/${encodeURIComponent(queue)}`;
}

export const QUEUES_HEADING = "Escalation queues";
export const READING_QUEUES = "Reading the escalation queues.";
export const NO_QUEUES = "Nobody is named for any queue yet";
export const NO_QUEUES_MORE = "A skill names a queue for the questions it could not answer. Name who answers for it here.";
export const NAME_QUEUE_LABEL = "Name who answers for a queue";
export const NAME_SOMEBODY_ELSE = "Name somebody else";
export const NAME_QUEUE_SUBMIT = "Name this person";
export const KEEP_QUEUE = "Keep it as it is";

/** What each field takes, said before anything is sent. */
export const QUEUE_HINTS = Object.freeze({
  queue: "The queue's name as the skill writes it: lowercase letters, digits and _.",
  person: "The person's reference as their page in People shows it under Advanced, with no spaces.",
  channel: "Where they are reached. Only channels a message can be sent on are listed.",
  address: "Their address on that channel: a chat or user id, a mailbox, or a webhook's name.",
});

/** The blank sentences, and the queue's shape, judged before the confirmation opens. */
export const QUEUE_PROBLEMS = Object.freeze({
  queue: "Enter the queue's name: lowercase letters, digits and _, starting with a letter.",
  person: "Enter the person's reference.",
  channel: "Choose where they are reached.",
  address: "Enter their address on that channel.",
});

const QUEUE_SHAPE = /^[a-z][a-z0-9_]{0,59}$/;

export interface RouteRow {
  readonly queue: string;
  readonly person: string;
  readonly person_name: string;
  readonly channel: string;
  readonly address: string;
  readonly named_by: string;
  readonly named_at: string;
}

export interface RoutesAnswer {
  readonly routes: readonly RouteRow[];
  readonly channels: readonly string[];
  readonly told: string;
}

export interface QueueForm {
  readonly queue: string;
  readonly person: string;
  readonly channel: string;
  readonly address: string;
}

/** What is wrong with the form, field by field, before it is sent. */
export function queueProblems(form: QueueForm): Partial<Record<keyof QueueForm, string>> {
  const found: Partial<Record<keyof QueueForm, string>> = {};
  if (!QUEUE_SHAPE.test(form.queue.trim())) {
    found.queue = QUEUE_PROBLEMS.queue;
  }
  if (form.person.trim() === "") {
    found.person = QUEUE_PROBLEMS.person;
  }
  if (form.channel === "") {
    found.channel = QUEUE_PROBLEMS.channel;
  }
  if (form.address.trim() === "") {
    found.address = QUEUE_PROBLEMS.address;
  }
  return found;
}

/** The body the route declares: the person, the channel and the address, trimmed. */
export function queueBody(form: QueueForm): { person: string; channel: string; address: string } {
  return { person: form.person.trim(), channel: form.channel, address: form.address.trim() };
}

function NameQueueDrawer({
  start,
  channels,
  onClose,
  onDone,
}: {
  readonly start: QueueForm;
  readonly channels: readonly string[];
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const [form, setForm] = useState<QueueForm>(start);
  const [problems, setProblems] = useState<Partial<Record<keyof QueueForm, string>>>({});
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const set = (name: keyof QueueForm) => (value: string) => {
    setForm({ ...form, [name]: value });
  };
  const send = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(escalationRouteApiPath(form.queue.trim()), { method: "PUT", body: queueBody(form) });
      setBusy(false);
      setConfirming(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onDone(`Questions handed to ${form.queue.trim()} now go to ${form.person.trim()}.`);
    })();
  }, [form, onDone]);
  return (
    <Drawer
      open
      onOpenChange={(next) => {
        if (!next && !busy) {
          onClose();
        }
      }}
      title={NAME_QUEUE_LABEL}
      description="The person named here is sent each question a skill hands to this queue, in their own channel."
      footer={
        <>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            {KEEP_QUEUE}
          </Button>
          <Button type="submit" form="name-queue" disabled={busy}>
            {NAME_QUEUE_SUBMIT}
          </Button>
        </>
      }
    >
      <form
        id="name-queue"
        aria-label={NAME_QUEUE_LABEL}
        className="flex min-w-0 flex-col gap-4"
        noValidate
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const found = queueProblems(form);
          setProblems(found);
          if (Object.keys(found).length === 0) {
            setFailure(null);
            setConfirming(true);
          }
        }}
      >
        {failure === null ? null : <FailureState failure={failure} />}
        <Field label="Queue" hint={QUEUE_HINTS.queue} problem={problems.queue}>
          {({ id, describedBy }) => <Input id={id} name="queue" autoComplete="off" aria-describedby={describedBy || undefined} value={form.queue} onChange={(event) => set("queue")(event.target.value)} />}
        </Field>
        <Field label="Person, by reference" hint={QUEUE_HINTS.person} problem={problems.person}>
          {({ id, describedBy }) => <Input id={id} name="person" autoComplete="off" aria-describedby={describedBy || undefined} value={form.person} onChange={(event) => set("person")(event.target.value)} />}
        </Field>
        <Field label="Channel" hint={QUEUE_HINTS.channel} problem={problems.channel}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={form.channel} onChange={set("channel")}>
              <option value="">Choose a channel</option>
              {channels.map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Address on that channel" hint={QUEUE_HINTS.address} problem={problems.address}>
          {({ id, describedBy }) => <Input id={id} name="address" autoComplete="off" aria-describedby={describedBy || undefined} value={form.address} onChange={(event) => set("address")(event.target.value)} />}
        </Field>
        {Object.keys(problems).length === 0 ? null : <FormProblem>Nothing was sent. Each field above says what it takes.</FormProblem>}
      </form>
      <ConfirmDialog
        open={confirming}
        question={`Hand ${form.queue.trim()} questions to ${form.person.trim()}?`}
        consequence={`From now, each question a skill hands to ${form.queue.trim()} is sent to ${form.person.trim()} on ${form.channel}, with who asked, the question, what was tried and what is needed, in place of whoever was named before.`}
        confirmLabel={NAME_QUEUE_SUBMIT}
        cancelLabel={KEEP_QUEUE}
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </Drawer>
  );
}

const EMPTY_FORM: QueueForm = { queue: "", person: "", channel: "", address: "" };

export function EscalationQueuesView({ onDone, version }: { readonly onDone: (told: string) => void; readonly version: number }) {
  const [naming, setNaming] = useState<QueueForm | null>(null);
  const answer = useResource<RoutesAnswer>(ESCALATION_ROUTES_API_PATH, version);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    return <LoadingState label={READING_QUEUES} rows={2} />;
  }
  const found = answer.data;
  const columns: EntityColumn<RouteRow>[] = [
    { id: "queue", header: "Queue", hideable: false, cell: (one) => <span className="font-mono text-[12px] font-medium text-ink">{one.queue}</span>, text: (one) => one.queue },
    { id: "person", header: "Handed to", cell: (one) => one.person_name || one.person, text: (one) => one.person_name || one.person },
    { id: "channel", header: "Reached on", cell: (one) => `${one.channel}, ${one.address}`, text: (one) => `${one.channel}, ${one.address}` },
    { id: "named", header: "Named", className: "whitespace-nowrap", cell: (one) => whenWords(one.named_at), text: (one) => one.named_at },
  ];
  return (
    <SectionCard
      title={QUEUES_HEADING}
      lede={found.told}
      action={
        <Button size="sm" className="min-h-11 sm:min-h-8" onClick={() => setNaming(EMPTY_FORM)}>
          <Plus aria-hidden /> {NAME_QUEUE_LABEL}
        </Button>
      }
    >
      {found.routes.length === 0 ? (
        <EmptyState title={NO_QUEUES} description={NO_QUEUES_MORE} />
      ) : (
        <EntityTable
          caption="Who each escalation queue is handed to"
          columns={columns}
          rows={found.routes}
          rowId={(one) => one.queue}
          rowLabel={(one) => one.queue}
          rowActions={(one) => (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${one.queue}`}>
                  <MoreHorizontal aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem onSelect={() => setNaming({ ...EMPTY_FORM, queue: one.queue })}>{NAME_SOMEBODY_ELSE}</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        />
      )}
      {naming === null ? null : (
        <NameQueueDrawer
          start={naming}
          channels={found.channels}
          onClose={() => setNaming(null)}
          onDone={(told) => {
            setNaming(null);
            onDone(told);
          }}
        />
      )}
    </SectionCard>
  );
}
