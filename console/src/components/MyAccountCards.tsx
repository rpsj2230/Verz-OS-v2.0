/**
 * A person's own account, in My workspace: where they are signed in, who has read their record,
 * what agents made for them and what is kept about them.
 *
 * Every card is the API's answer for the person asking (`brain.member_self_routes`) and draws what
 * it was sent. Ending a sign-in is confirmed, never offered for the one asking, and refused by the
 * API for any session that is not theirs. The reads card shows who and when and never what was
 * shown, and none of the cards shows a total of anything hidden.
 *
 * Task ids: M40.1.1.3, M40.4.2.4, M40.3.3.1, M40.4.2.1
 */

import { useCallback, useState } from "react";
import { request, requestFile } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { when } from "../pages/artifactsQuery";
import {
  END_MY_DEVICE_API_PATH,
  MY_ARTIFACTS_API_PATH,
  MY_DEVICES_API_PATH,
  MY_READS_API_PATH,
  MY_SHARES_API_PATH,
  REQUESTABLE_API_PATH,
  askForAgentApiPath,
  type RequestableBody,
  MY_STORED_API_PATH,
  SHARED_WITH_ME_API_PATH,
  colleagueBody,
  endBody,
  shareApiPath,
  sharedFileApiPath,
  unshareApiPath,
  type MySharesBody,
  type SharedWithMeBody,
  type MyArtifactsBody,
  type MyDevice,
  type MyDevicesBody,
  type MyReadsBody,
  type MyStoredBody,
} from "../pages/myAccountQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { ConfirmAction } from "./ConfirmAction";
import { BY_THE_INSTALL, EmptyList } from "./kit/states";

export const DEVICES_CAPTION = "Where I am signed in";
export const READS_CAPTION = "Who has read my record";
export const ARTIFACTS_CAPTION = "Made for me";
export const STORED_CAPTION = "What is kept about me";
export const THIS_ONE = "This sign-in";
export const END_DEVICE_LABEL = "Sign out";
export const KEEP_DEVICE_LABEL = "Stay signed in";
export const END_DEVICE_CONSEQUENCE =
  "That sign-in stops working at once. You can sign in there again. It is recorded in the audit " +
  "ledger.";
export const NO_READS = "Nobody has read your record.";
export const NO_ARTIFACTS = "No agent has made anything for you.";
export const ASK_LABEL = "Ask for it";
export const ASKED = "Asked";
export const REQUESTABLE_CAPTION = "Agents I can ask for";
export const NOTHING_REQUESTABLE = "There is no agent you can see and cannot run.";
export const SHARE_LABEL = "Share";
export const TAKE_BACK_LABEL = "Take back";
export const OPEN_LABEL = "Download";
export const SHARED_CAPTION = "Shared with me";
export const SHARES_CAPTION = "I shared";
export const NOTHING_SHARED_WITH_ME = "Nothing has been shared with you that you can open.";
export const NOTHING_SHARED = "You have not shared anything.";
export const COLLEAGUE_LABEL = "Colleague's person id";
export const CANNOT_SAVE_FILE = "This browser could not save the file.";
export const MORE_ROWS = "There are more than are shown here.";

function Reading({ what }: { readonly what: string }) {
  return (
    <p className="note" role="status">
      {`Reading ${what}.`}
    </p>
  );
}

export function MyDevices() {
  const [version, setVersion] = useState(0);
  const answer = useResource<MyDevicesBody>(MY_DEVICES_API_PATH, version);
  const [confirming, setConfirming] = useState<MyDevice | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const end = useCallback((device: MyDevice) => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(END_MY_DEVICE_API_PATH, {
        method: "POST",
        body: endBody(device.session_id),
      });
      setBusy(false);
      setConfirming(null);
      if (result.ok) {
        setVersion((current) => current + 1);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);

  return (
    <section className="card">
      <h2>{DEVICES_CAPTION}</h2>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {confirming === null ? null : (
        <ConfirmAction
          question="Sign this one out?"
          consequence={END_DEVICE_CONSEQUENCE}
          confirmLabel={END_DEVICE_LABEL}
          cancelLabel={KEEP_DEVICE_LABEL}
          busy={busy}
          onConfirm={() => {
            end(confirming);
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        />
      )}
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : answer.data === null ? (
        <Reading what="your sign-ins" />
      ) : (
        <>
          <ul aria-label={DEVICES_CAPTION}>
            {answer.data.devices.map((one) => (
              <li key={one.session_id}>
                {`${one.channel}, since ${when(one.started_at)}, until ${when(one.expires_at)}${
                  one.second_factor ? ", with a second factor" : ""
                }. `}
                {one.is_this_one ? (
                  <strong>{THIS_ONE}</strong>
                ) : (
                  <button
                    type="button"
                    className="button"
                    aria-label={`${END_DEVICE_LABEL}: ${one.session_id}`}
                    disabled={busy}
                    onClick={() => {
                      setFailure(null);
                      setConfirming(one);
                    }}
                  >
                    {END_DEVICE_LABEL}
                  </button>
                )}
              </li>
            ))}
          </ul>
          {answer.data.more ? <p className="note">{MORE_ROWS}</p> : null}
        </>
      )}
    </section>
  );
}

export function MyReads() {
  const answer = useResource<MyReadsBody>(MY_READS_API_PATH, 0);
  return (
    <section className="card">
      <h2>{READS_CAPTION}</h2>
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : answer.data === null ? (
        <Reading what="who has read your record" />
      ) : answer.data.reads.length === 0 ? (
        <EmptyList
          compact
          title={NO_READS}
          adds="A read is recorded each time an agent reads your record."
          by={BY_THE_INSTALL}
        />
      ) : (
        <ul aria-label={READS_CAPTION}>
          {answer.data.reads.map((one) => (
            <li key={`${one.at}-${one.actor_id}-${one.agent_id}`}>
              {`${when(one.at)}: ${one.actor_id}${
                one.agent_id === "" ? "" : `, through ${one.agent_id}`
              }, ${one.record_kind}.`}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function saveFile(name: string, body: Blob): boolean {
  if (typeof URL.createObjectURL !== "function") {
    return false;
  }
  const address = URL.createObjectURL(body);
  const link = document.createElement("a");
  link.href = address;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(address);
  return true;
}

export function MyArtifacts() {
  const [version, setVersion] = useState(0);
  const answer = useResource<MyArtifactsBody>(MY_ARTIFACTS_API_PATH, version);
  const [colleague, setColleague] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const shareWith = useCallback((artifactId: string, who: string) => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(shareApiPath(artifactId), {
        method: "POST",
        body: colleagueBody(who),
      });
      setBusy(false);
      if (result.ok) {
        setColleague((was) => ({ ...was, [artifactId]: "" }));
        setVersion((current) => current + 1);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);
  return (
    <section className="card">
      <h2>{ARTIFACTS_CAPTION}</h2>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : answer.data === null ? (
        <Reading what="what was made for you" />
      ) : answer.data.artifacts.length === 0 ? (
        <EmptyList
          compact
          title={NO_ARTIFACTS}
          adds="An artifact is listed when an agent produces a document, a deck, a report or an image for you."
          by={BY_THE_INSTALL}
        />
      ) : (
        <>
          <ul aria-label={ARTIFACTS_CAPTION}>
            {answer.data.artifacts.map((one) => (
              <li key={one.artifact_id}>
                {`${one.kind} by ${one.agent_id}, ${when(one.produced_at)}, ${one.kept_because}. `}
                <input
                  aria-label={`${COLLEAGUE_LABEL}: ${one.artifact_id}`}
                  value={colleague[one.artifact_id] ?? ""}
                  onChange={(event) => {
                    setColleague((was) => ({ ...was, [one.artifact_id]: event.target.value }));
                  }}
                />{" "}
                <button
                  type="button"
                  className="button"
                  aria-label={`${SHARE_LABEL}: ${one.artifact_id}`}
                  disabled={busy || (colleague[one.artifact_id] ?? "").trim() === ""}
                  onClick={() => {
                    shareWith(one.artifact_id, colleague[one.artifact_id] ?? "");
                  }}
                >
                  {SHARE_LABEL}
                </button>
              </li>
            ))}
          </ul>
          {answer.data.more ? <p className="note">{MORE_ROWS}</p> : null}
        </>
      )}
    </section>
  );
}

export function MyStored() {
  const answer = useResource<MyStoredBody>(MY_STORED_API_PATH, 0);
  return (
    <section className="card">
      <h2>{STORED_CAPTION}</h2>
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : answer.data === null ? (
        <Reading what="what is kept about you" />
      ) : (
        <>
          <ul aria-label={STORED_CAPTION}>
            {answer.data.stores.map((one) => (
              <li key={one.store}>{`${one.holds}. Deletion here: ${one.deletion}.`}</li>
            ))}
          </ul>
          <p className="note">{answer.data.told}</p>
        </>
      )}
    </section>
  );
}

export function MyShared() {
  const [version, setVersion] = useState(0);
  const received = useResource<SharedWithMeBody>(SHARED_WITH_ME_API_PATH, version);
  const sent = useResource<MySharesBody>(MY_SHARES_API_PATH, version);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState<string | null>(null);

  const open = useCallback((artifactId: string, kind: string) => {
    setSaid(null);
    void (async () => {
      const got = await requestFile(sharedFileApiPath(artifactId));
      if (!got.ok) {
        setFailure(got.failure);
        return;
      }
      setSaid(saveFile(`${kind}-${artifactId}`, got.body) ? null : CANNOT_SAVE_FILE);
    })();
  }, []);

  const takeBack = useCallback((artifactId: string, who: string) => {
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(unshareApiPath(artifactId), {
        method: "POST",
        body: colleagueBody(who),
      });
      if (result.ok) {
        setVersion((current) => current + 1);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);

  return (
    <section className="card">
      <h2>{SHARED_CAPTION}</h2>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {said === null ? null : <p className="note">{said}</p>}
      {received.failure ? (
        <FailureNotice failure={received.failure} />
      ) : received.data === null ? (
        <Reading what="what was shared with you" />
      ) : received.data.items.length === 0 ? (
        <EmptyList
          compact
          title={NOTHING_SHARED_WITH_ME}
          adds="A colleague shares one of their artifacts with you."
          by={["member"]}
        />
      ) : (
        <ul aria-label={SHARED_CAPTION}>
          {received.data.items.map((one) => (
            <li key={one.artifact.artifact_id}>
              {`${one.artifact.kind} from ${one.shared_by}, ${when(one.shared_at)}. `}
              <button
                type="button"
                className="button"
                aria-label={`${OPEN_LABEL}: ${one.artifact.artifact_id}`}
                onClick={() => {
                  open(one.artifact.artifact_id, one.artifact.kind);
                }}
              >
                {OPEN_LABEL}
              </button>
            </li>
          ))}
        </ul>
      )}
      <h3>{SHARES_CAPTION}</h3>
      {sent.failure ? (
        <FailureNotice failure={sent.failure} />
      ) : sent.data === null ? (
        <Reading what="what you shared" />
      ) : sent.data.shares.length === 0 ? (
        <p className="note">{NOTHING_SHARED}</p>
      ) : (
        <ul aria-label={SHARES_CAPTION}>
          {sent.data.shares.map((one) => (
            <li key={`${one.artifact_id}-${one.shared_with}`}>
              {`${one.artifact_id} with ${one.shared_with}, ${when(one.shared_at)}. `}
              <button
                type="button"
                className="button"
                aria-label={`${TAKE_BACK_LABEL}: ${one.artifact_id} from ${one.shared_with}`}
                onClick={() => {
                  takeBack(one.artifact_id, one.shared_with);
                }}
              >
                {TAKE_BACK_LABEL}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function MyRequestableAgents() {
  const [version, setVersion] = useState(0);
  const answer = useResource<RequestableBody>(REQUESTABLE_API_PATH, version);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const ask = useCallback((agentId: string) => {
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(askForAgentApiPath(agentId), { method: "POST" });
      if (result.ok) {
        setVersion((current) => current + 1);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);

  return (
    <section className="card">
      <h2>{REQUESTABLE_CAPTION}</h2>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : answer.data === null ? (
        <Reading what="the agents you can ask for" />
      ) : answer.data.agents.length === 0 ? (
        <EmptyList
          compact
          title={NOTHING_REQUESTABLE}
          adds="An agent is listed once it is published to a department you can reach."
          by={["super_admin", "department_admin"]}
        />
      ) : (
        <ul aria-label={REQUESTABLE_CAPTION}>
          {answer.data.agents.map((one) => (
            <li key={one.agent_id}>
              {`${one.display_name} `}
              {one.asked ? (
                <strong>{ASKED}</strong>
              ) : (
                <button
                  type="button"
                  className="button"
                  aria-label={`${ASK_LABEL}: ${one.agent_id}`}
                  onClick={() => {
                    ask(one.agent_id);
                  }}
                >
                  {ASK_LABEL}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
