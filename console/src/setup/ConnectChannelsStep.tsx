/**
 * First run's channels step: the chat and email channels named on the Channels screen, offered for
 * connecting once the first administrator is signed in, each through the Channels screen's own
 * set-up form and test message. Skippable, and every word of it says the same can be done later
 * from Channels.
 *
 * **After the appointment, and never inside it**, for the reason `setup/ConnectSourcesStep.tsx`
 * gives: setting a channel up writes a secret into the vault and a record under the channel's own
 * grant, before the appointment nobody holds that grant, and the setup code appoints one
 * administrator and must not become a way to write a secret attributed to nobody. After the
 * finishing screen has bound the sign-in, the page holds the administrator's own token, so the
 * request is exactly the one the Channels screen makes, judged by the same route, confirmed in the
 * same words and recorded against the person.
 *
 * **A test message is part of it.** A channel connected and never proved is a channel that fails
 * at the first colleague's message, so the form that saves the set-up is followed by the form that
 * sends one short sentence through the vendor, which is the same component the Channels screen
 * draws. The step does not insist on it: a person who has no destination to hand can leave, and
 * the Channels screen says the test is still to do.
 *
 * **A name is looked up and not trusted.** The row for each name is read from the console's own
 * channel list; a name this release has no channel for gets the API's one refusal, drawn as a
 * sentence saying so, and a channel the signed-in person may not manage is the same refusal, which
 * is the Channels screen's rule and not repeated differently here.
 *
 * Task ids: M42.5.16
 */

import { useState } from "react";
import { useResource } from "../api/useResource";
import { ChannelProfile } from "../pages/channels/ChannelProfile";
import { channelRowApiPath, type ChannelRow } from "../pages/channels/channelRows";
import { FailureNotice } from "../ui/FailureNotice";
import type { Answers, StepKey } from "./wizard";

export const CONNECT_CHANNELS_TITLE = "Connect your chat and email channels";

export const CONNECT_CHANNELS_LATER =
  "You named these on the Channels screen of setup. Set each one up now and send a test message, or skip this: any channel can be set up at any time from Channels in the console, in exactly the same way.";

export const SKIP_CHANNELS = "Skip, and set up channels later from Channels";
export const ON_TO_THE_CONSOLE = "Open the console";

/** Said for a name that is no channel the signed-in person may manage. */
export const NO_SUCH_CHANNEL =
  "This system has no channel by that name that you can set up. Channels in the console lists every channel it has.";

export const CHANNEL_NOT_READ = "That channel could not be read";

/** The channels named on the channels screen, or none when it was skipped or left blank. */
export function namedChannels(answers: Answers, skipped: ReadonlySet<StepKey>): readonly string[] {
  if (skipped.has("channels")) {
    return [];
  }
  const typed = answers.channels?.["channels"] ?? "";
  const names = typed
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");
  return [...new Set(names)];
}

function ChannelSection({ name }: { readonly name: string }) {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState("");
  const answer = useResource<ChannelRow>(channelRowApiPath(name), version);
  const row = answer.data;
  return (
    <section className="first-run__section" aria-label={name}>
      <h2>{row?.channel ?? name}</h2>
      {answer.busy && row === null ? (
        <p className="note" role="status">
          Reading this channel.
        </p>
      ) : null}
      {answer.failure ? (
        answer.failure.status === 404 ? (
          <p>{NO_SUCH_CHANNEL}</p>
        ) : (
          <FailureNotice failure={answer.failure} title={CHANNEL_NOT_READ} />
        )
      ) : null}
      {told === "" ? null : <p className="note">{told}</p>}
      {row === null ? null : (
        <ChannelProfile
          row={row}
          onChanged={(sentence) => {
            setTold(sentence);
            setVersion((one) => one + 1);
          }}
        />
      )}
    </section>
  );
}

export function ConnectChannelsStep({
  named,
  kept,
  onDone,
}: {
  readonly named: readonly string[];
  /** What first run says about the provider key, when it kept one. */
  readonly kept: string | null;
  readonly onDone: () => void;
}) {
  return (
    <main className="first-run">
      <h1>{CONNECT_CHANNELS_TITLE}</h1>
      {kept === null ? null : <p>{kept}</p>}
      <p>{CONNECT_CHANNELS_LATER}</p>
      {named.map((name) => (
        <ChannelSection key={name} name={name} />
      ))}
      <div className="form-actions">
        <button type="button" className="button" onClick={onDone}>
          {SKIP_CHANNELS}
        </button>
        <button type="button" className="button" onClick={onDone}>
          {ON_TO_THE_CONSOLE}
        </button>
      </div>
    </main>
  );
}
