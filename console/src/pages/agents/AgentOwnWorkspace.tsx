/**
 * A person's own Google account on their personal agent, on its Profile (M39.10.4).
 *
 * **The card is drawn only for the owner of a personal agent.** `GET /agents/{id}/own-workspace`
 * answers nobody else: a colleague, an administrator and a team agent's page get the one 404 an agent
 * that does not exist gets, so the card is absent there and nothing says why. A failed read draws
 * nothing for the same reason, and the Profile around it already says if the Brain could not be
 * reached.
 *
 * **Both presses go through `kit/ConfirmDialog`**, because attaching lets the agent read the person's
 * own mail, calendar and documents, and taking it off stops it, and each says so in the dialog. The
 * body sends only what the person chose (`attached`); the route decides whether it may, and a refusal
 * is the API's own sentence under a heading that says nothing was changed.
 *
 * **What it tells the person and what it does not.** Whether they have connected their own account at
 * Google is said, with the way to do it (My workspace), because attaching before connecting reads
 * nothing and a person who attached first deserves to know the other half is theirs. What the agent
 * read is never on this card: nothing about a person's mail is kept, so there is nothing to show.
 *
 * Task ids: M39.10.4
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";

export const OWN_WORKSPACE_HEADING = "Your own Google account";
export const OWN_WORKSPACE_LEDE =
  "Let this agent read your own mail, calendar and documents. It is yours alone: nobody else can ask it for them, and a team agent never carries one.";
export const ATTACH_LABEL = "Attach my Google account";
export const DETACH_LABEL = "Take my Google account off";
export const ATTACHED_WORDS = "Attached. This agent reads your own account when you ask it something.";
export const NOT_ATTACHED_WORDS = "Not attached. This agent reads nothing of your Google account.";
export const CANNOT_ATTACH_YET =
  "It cannot be attached yet: either your company has not connected Google Workspace, or you have not been given access to it. Ask your administrator.";
export const CONNECTED_WORDS = "You have connected your Google account.";
export const NOT_CONNECTED_WORDS = "You have not connected your Google account yet. Connect it from My workspace; until then the agent reads nothing.";
export const MY_WORKSPACE_LINK = "My workspace";
export const ATTACH_QUESTION = (name: string): string => `Attach your own Google account to ${name}?`;
export const ATTACH_CONSEQUENCE =
  "From your next question the agent reads your own mail, calendar and documents, with your own consent at Google, for you alone, and nothing is copied into the Brain. Nobody else can ask it for them. You can take it off at any time.";
export const DETACH_QUESTION = (name: string): string => `Take your Google account off ${name}?`;
export const DETACH_CONSEQUENCE =
  "From your next question the agent reads nothing of your account. Your connection to Google stays, and you can attach it again.";
export const ATTACHED_DONE = "Your Google account is attached";
export const DETACHED_DONE = "Your Google account was taken off";
export const NOT_CHANGED = "Nothing was changed";

export interface OwnWorkspaceShown {
  readonly agentId: string;
  readonly attached: boolean;
  readonly mayAttach: boolean;
  readonly accountConnected: boolean | null;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field is read back
  // through a type test below.
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

export function agentOwnWorkspaceApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/own-workspace`;
}

/** The card's facts out of a body, or null when the body is not one. */
export function readOwnWorkspace(payload: unknown): OwnWorkspaceShown | null {
  const fields = fieldsOf(payload);
  if (fields === null || typeof fields["agent_id"] !== "string" || typeof fields["attached"] !== "boolean") {
    return null;
  }
  return {
    agentId: fields["agent_id"],
    attached: fields["attached"],
    mayAttach: fields["may_attach"] === true,
    accountConnected: typeof fields["account_connected"] === "boolean" ? fields["account_connected"] : null,
  };
}

/** The body a press sends: what the person chose, and nothing else. */
export function ownWorkspaceBody(attach: boolean): { attached: boolean } {
  return { attached: attach };
}

export function AgentOwnWorkspace({ agentId, name }: { readonly agentId: string; readonly name: string }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentOwnWorkspaceApiPath(agentId), version);
  const shown = answer.data === null ? null : readOwnWorkspace(answer.data);
  const [asking, setAsking] = useState<boolean | null>(null);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [refused, setRefused] = useState<ApiFailure | null>(null);

  if (shown === null) {
    return null;
  }

  const confirm = () => {
    if (asking === null) {
      return;
    }
    const attach = asking;
    setSending(true);
    void (async () => {
      const result = await request<unknown>(agentOwnWorkspaceApiPath(agentId), {
        method: "POST",
        body: ownWorkspaceBody(attach),
      });
      setSending(false);
      setAsking(null);
      if (result.ok) {
        setRefused(null);
        setDone(attach ? ATTACHED_DONE : DETACHED_DONE);
        setVersion((count) => count + 1);
        return;
      }
      setDone(null);
      setRefused(result.failure);
    })();
  };

  const press =
    shown.attached || shown.mayAttach ? (
      <Button
        variant="outline"
        size="sm"
        className="min-h-11 sm:min-h-8"
        disabled={sending}
        onClick={() => {
          setDone(null);
          setRefused(null);
          setAsking(!shown.attached);
        }}
      >
        {shown.attached ? DETACH_LABEL : ATTACH_LABEL}
      </Button>
    ) : undefined;

  return (
    <SectionCard title={OWN_WORKSPACE_HEADING} lede={OWN_WORKSPACE_LEDE} action={press}>
      <div data-slot="agent-own-workspace" className="flex min-w-0 flex-col gap-2">
        {refused === null ? null : <FailureNotice failure={refused} title={NOT_CHANGED} />}
        {done === null ? null : <Notice title={done}>{name}</Notice>}
        <Note>{shown.attached ? ATTACHED_WORDS : NOT_ATTACHED_WORDS}</Note>
        {!shown.attached && !shown.mayAttach ? <Note>{CANNOT_ATTACH_YET}</Note> : null}
        {shown.accountConnected === null ? null : (
          <Note>
            {shown.accountConnected ? CONNECTED_WORDS : NOT_CONNECTED_WORDS}{" "}
            <Link to="/me">{MY_WORKSPACE_LINK}</Link>
          </Note>
        )}
      </div>
      <ConfirmDialog
        open={asking !== null}
        question={asking === true ? ATTACH_QUESTION(name) : DETACH_QUESTION(name)}
        consequence={asking === true ? ATTACH_CONSEQUENCE : DETACH_CONSEQUENCE}
        confirmLabel={asking === true ? "Attach" : "Take off"}
        cancelLabel="Not now"
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setAsking(null);
        }}
      />
    </SectionCard>
  );
}
