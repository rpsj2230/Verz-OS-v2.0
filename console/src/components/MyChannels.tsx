/**
 * A person's own chat channels, in My workspace: which they may connect, which they have, the
 * one-time code that connects one, and disconnecting one.
 *
 * `docs/screens.html` SCREEN 12 puts Channels under Me, and this is that card. The API answers for
 * the person asking and nobody else: `brain.binding_routes` takes no parameter naming a person, opens
 * on the member screen `channels`, and mints a code only inside the asker's live sign-in. The code is
 * shown once, here, and held nowhere but this card's memory until the page is left; the server keeps
 * only its digest. Disconnecting is confirmed and recorded in the audit ledger.
 *
 * A channel switched off and a channel the person holds nothing on are one absence to the API, so
 * this card lists what it was sent and asks about nothing else.
 *
 * Task ids: M10.3.1, M10.3.4
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { when } from "../pages/artifactsQuery";
import {
  MY_CHANNELS_API_PATH,
  myCodeApiPath,
  myUnbindApiPath,
  type CodeBody,
  type MyChannelRow,
  type MyChannelsBody,
} from "../pages/channelsQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { ConfirmAction } from "./ConfirmAction";

export const MY_CHANNELS_CAPTION = "Channels";
export const READING_MY_CHANNELS = "Reading your chat channels.";
export const NO_MY_CHANNELS = "No chat channel is switched on for you to connect.";
export const GET_CODE_LABEL = "Get a code";
export const DISCONNECT_LABEL = "Disconnect";
export const KEEP_LABEL = "Keep it as it is";
export const DISCONNECT_CONSEQUENCE =
  "The Brain stops answering that chat account as you, at once. You can connect it again with a " +
  "new code. It is recorded in the audit ledger.";

function myStatus(row: MyChannelRow): string {
  if (row.bound_at !== null) {
    return `Connected since ${when(row.bound_at)}.`;
  }
  return row.may_bind ? "Not connected." : "Not connected, and not switched on.";
}

export function MyChannels() {
  const [version, setVersion] = useState(0);
  const answer = useResource<MyChannelsBody>(MY_CHANNELS_API_PATH, version);
  const [code, setCode] = useState<CodeBody | null>(null);
  const [confirming, setConfirming] = useState<MyChannelRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const mint = useCallback((row: MyChannelRow) => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<CodeBody>(myCodeApiPath(row.channel), { method: "POST" });
      setBusy(false);
      if (result.ok) {
        setCode(result.data);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);

  const disconnect = useCallback((row: MyChannelRow) => {
    setBusy(true);
    void (async () => {
      const result = await request<MyChannelsBody>(myUnbindApiPath(row.channel), { method: "POST" });
      setBusy(false);
      setConfirming(null);
      if (result.ok) {
        setCode(null);
        setVersion((current) => current + 1);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);

  return (
    <section className="card">
      <h2>{MY_CHANNELS_CAPTION}</h2>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {confirming === null ? null : (
        <ConfirmAction
          question={`Disconnect your ${confirming.channel} account?`}
          consequence={DISCONNECT_CONSEQUENCE}
          confirmLabel={DISCONNECT_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            disconnect(confirming);
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        />
      )}
      {code === null ? null : (
        <p role="status">
          Your code for {code.channel}: <code>{code.code}</code>. {code.told} It lapses at{" "}
          {when(code.expires_at)}.
        </p>
      )}
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : answer.data === null ? (
        <p className="note" role="status">
          {READING_MY_CHANNELS}
        </p>
      ) : answer.data.channels.length === 0 ? (
        <p className="note">{NO_MY_CHANNELS}</p>
      ) : (
        <>
          <ul aria-label="Your chat channels">
            {answer.data.channels.map((row) => (
              <li key={row.channel}>
                {row.channel}: {myStatus(row)}{" "}
                {row.may_bind ? (
                  <button
                    type="button"
                    className="button"
                    aria-label={`${GET_CODE_LABEL}: ${row.channel}`}
                    disabled={busy}
                    onClick={() => {
                      mint(row);
                    }}
                  >
                    {GET_CODE_LABEL}
                  </button>
                ) : null}{" "}
                {row.bound ? (
                  <button
                    type="button"
                    className="button"
                    aria-label={`${DISCONNECT_LABEL}: ${row.channel}`}
                    disabled={busy}
                    onClick={() => {
                      setFailure(null);
                      setConfirming(row);
                    }}
                  >
                    {DISCONNECT_LABEL}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="hint note">{answer.data.told}</p>
        </>
      )}
    </section>
  );
}
