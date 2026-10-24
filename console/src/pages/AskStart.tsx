/**
 * The two ways a member starts on Ask: start a task, or talk to an agent (M40.7.5).
 *
 * **Start a task names no agent.** The question goes to the router, which chooses among the agents
 * this person may call by what each is for (`brain.gate.select`), or answers as the person's own
 * reach when none fits. **Talk to an agent** shows the picker and sends the one chosen. Nothing here
 * decides who answers or what they may read: the body carries an agent id or none, and the route
 * judges it like any name, so an agent the person may not use answers as one that does not exist.
 *
 * Offered only when the roster came back with an agent in it. A person who may call none has one way
 * to start, so there is nothing to choose between and no control.
 *
 * Task ids: M40.7.5
 */

import { msg } from "../locale";

export type StartMode = "task" | "agent";

export const START_LEGEND = msg("console.ask.start_legend", "How do you want to start?");
export const START_TASK = msg("console.ask.start_task", "Start a task");
export const START_TASK_NOTE =
  msg("console.ask.start_task_note", "Say what you need. An agent you may call is chosen for it, and it works with only what you are able to see.");
export const TALK_TO_AGENT = msg("console.ask.talk_to_agent", "Talk to an agent");
export const TALK_NOTE = msg("console.ask.talk_note", "Choose who you are talking to.");

export function AskStart({
  mode,
  onMode,
  disabled,
}: {
  readonly mode: StartMode;
  readonly onMode: (mode: StartMode) => void;
  readonly disabled: boolean;
}): React.JSX.Element {
  return (
    <fieldset className="ask__start">
      <legend>{START_LEGEND}</legend>
      <label>
        <input
          type="radio"
          name="ask-start"
          value="task"
          checked={mode === "task"}
          disabled={disabled}
          onChange={() => {
            onMode("task");
          }}
        />{" "}
        {START_TASK}
        <span className="note">{` ${START_TASK_NOTE}`}</span>
      </label>
      <label>
        <input
          type="radio"
          name="ask-start"
          value="agent"
          checked={mode === "agent"}
          disabled={disabled}
          onChange={() => {
            onMode("agent");
          }}
        />{" "}
        {TALK_TO_AGENT}
        <span className="note">{` ${TALK_NOTE}`}</span>
      </label>
    </fieldset>
  );
}
