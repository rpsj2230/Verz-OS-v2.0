/**
 * What one agent is assembled from, and what it has been costing: the two right-hand blocks
 * of `docs/screens.html` SCREEN 13.
 *
 * **Every row here was decided by a read module before it reached this file.** The connectors
 * are `brain.console.workspace_capabilities.connector_rows` with `connector_strip`'s overflow,
 * the skills are the manifest's own pinned references behind the Skills screen's read, the
 * channels are `offered_channels` at `E_run(caller, agent)` and the figures are
 * `brain.console.workspace.headline` at the basis `basis_for` gave this reader. Nothing is
 * recomputed in the browser and there is nothing here to recompute one with: this file has no
 * entitlement, no policy and no clock.
 *
 * **A block with nothing in it draws nothing at all**, which is
 * `brain.console.workspace.A_TAB_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS` one level
 * down. A heading reading Skills over an empty pane says this agent has skills the reader may
 * not be told about, and the reader cannot tell that from an agent with none, so neither may
 * the markup.
 *
 * **Three things the design draws are deliberately absent, and each is absent because nothing
 * measures it.** SCREEN 13 shows a connector's health, a skill's review state and a channel
 * that is switched on; this console is sent none of the three, because no probe, no approved
 * library and no per-agent channel enablement exists behind the API. A badge invented here
 * would be this browser asserting a fact nobody checked, which is the failure
 * `src/ui/Status.tsx` refuses in the small: a state word is rendered as it arrived or not at
 * all.
 *
 * **The one number on these blocks is the connector overflow**, and it is the count the Python
 * side argues is safe: it is computed from the rows this reader may see, so it says how many
 * connectors are off the end of the row and never how many are out of reach. There is no other
 * figure here that is a count of rows: spend and runs are measurements over the window and
 * carry the basis saying whose they are.
 *
 * Task ids: M39.1.2.3
 */

import type {
  AgentFigures,
  ChannelOffer,
  ConnectorStrip,
  SkillPin,
} from "../pages/agentQuery";
import "../styles/agent-workspace.css";

/** The heading over the block. SCREEN 13's own words. */
export const CAPABILITIES_HEADING = "Capabilities";

/** Under it, saying what the block is. SCREEN 13's own sentence. */
export const CAPABILITIES_LEDE = "What this agent is assembled from.";

export const CONNECTORS_LABEL = "Connectors";
export const SKILLS_LABEL = "Skills";
export const CHANNELS_LABEL = "Channels";

/**
 * What the overflow says, with the number the API computed in it.
 *
 * A sentence rather than a bare digit beside the icons, because the digit alone is read as a
 * count of everything that exists. This one says what it counts: connectors on this agent
 * that this row did not have space for.
 */
export function moreConnectors(overflow: number): string {
  return `${overflow} more on this agent.`;
}

/** What is said beside a channel: the layout an answer would be delivered in there. */
export const PROFILE_WORD = "as";

/**
 * The two words for a basis, which are the API's own members spelled for a reader.
 *
 * A table of two rather than the member rendered raw, because "own" and "everyone" are
 * `brain.console.workspace.Basis`' keys rather than sentences, and the whole point of the
 * label is that somebody reads it and knows whose figure they are looking at. A basis that is
 * neither renders as itself, which is `src/ui/Status.tsx`'s rule for an unknown state word.
 */
const BASIS_WORDS: Readonly<Record<string, string>> = Object.freeze({
  own: "your runs",
  everyone: "all runs",
});

export function basisWords(basis: string): string {
  return BASIS_WORDS[basis] ?? basis;
}

/** The heading over the figures, and the labels beside them. SCREEN 13's own words. */
export const FIGURES_HEADING = "Runs and cost";
export const SPEND_LABEL = "Spend";
export const RUNS_LABEL = "Runs";

/**
 * A figure's label with the window it was measured over, as SCREEN 13 writes "Spend 30d".
 *
 * The window is the API's word rather than a number composed here, so a label and the figure
 * under it cannot disagree about how long a month is.
 */
export function measuredOver(label: string, range: string): string {
  return `${label} ${range}`;
}

/** The label over the parts this install edited, in SCREEN 13's own words. */
export const DIVERGENCE_LABEL = "Local divergence";

/**
 * An amount in minor units, as digits with a separator and no currency sign.
 *
 * No symbol, because nothing in the response says which currency this installation counts in:
 * `brain.ops.budgets` says money is counted in minor units and the sign is a fact about the
 * company that the API does not send. A pound sign written here would be right for one
 * installation and wrong for the next, which is exactly what `CLAUDE.md` says configuration
 * is for.
 */
export function minorUnits(amount: number): string {
  return (amount / 100).toFixed(2);
}

function Block({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="agent-assembly__block">
      <h4 className="agent-assembly__label">{label}</h4>
      {children}
    </div>
  );
}

/**
 * The capability block: connectors, skills and channels, each drawn only when it has rows.
 *
 * Rendered in SCREEN 13's order. The whole block is absent when all three are, so an agent
 * whose assembly this reader may not see renders exactly as an agent that is assembled from
 * nothing.
 */
export function AgentCapabilities({
  connectors,
  skills,
  channels,
}: {
  readonly connectors: ConnectorStrip;
  readonly skills: readonly SkillPin[];
  readonly channels: readonly ChannelOffer[];
}) {
  const anything =
    connectors.shown.length > 0 || skills.length > 0 || channels.length > 0;
  if (!anything) {
    return null;
  }
  return (
    <section className="agent-assembly" aria-label={CAPABILITIES_HEADING}>
      <h3>{CAPABILITIES_HEADING}</h3>
      <p className="note">{CAPABILITIES_LEDE}</p>

      {connectors.shown.length === 0 ? null : (
        <Block label={CONNECTORS_LABEL}>
          <ul className="agent-assembly__list">
            {connectors.shown.map((one) => (
              <li key={one.source}>
                <code>{one.source}</code> <span className="note">{one.presence}</span>
              </li>
            ))}
          </ul>
          {connectors.overflow > 0 ? (
            <p className="note">{moreConnectors(connectors.overflow)}</p>
          ) : null}
        </Block>
      )}

      {skills.length === 0 ? null : (
        <Block label={SKILLS_LABEL}>
          <ul className="agent-assembly__list">
            {skills.map((one) => (
              <li key={one.name}>
                <code>{one.name}</code>{" "}
                <span className="note agent-assembly__digest">{one.digest}</span>
              </li>
            ))}
          </ul>
        </Block>
      )}

      {channels.length === 0 ? null : (
        <Block label={CHANNELS_LABEL}>
          <ul className="agent-assembly__list">
            {channels.map((one) => (
              <li key={one.channel}>
                <code>{one.channel}</code>{" "}
                <span className="note">
                  {PROFILE_WORD} {one.profile}
                </span>
              </li>
            ))}
          </ul>
        </Block>
      )}
    </section>
  );
}

/**
 * The dashboard pane: spend and runs over the window the API measured them in.
 *
 * Nothing when the API sent no figures. An empty dashboard is the honest rendering of an
 * answer with no headline in it, and a nought composed here would be a measurement this
 * console made up.
 */
export function AgentFiguresView({
  figures,
  divergent = [],
}: {
  readonly figures?: AgentFigures;
  /**
   * The parts this install edited that its template supplies, which SCREEN 13 draws as a tile
   * beside the figures. Sent only to a reader of the Settings tab, and a reader who was not
   * sent it and an install with no local edit are one absence here: no row at all.
   */
  readonly divergent?: readonly string[];
}) {
  if (figures === undefined && divergent.length === 0) {
    return null;
  }
  return (
    <section className="agent-assembly" aria-label={FIGURES_HEADING}>
      <h3>{FIGURES_HEADING}</h3>
      <dl className="agent-header__facts">
        {figures === undefined ? null : (
          <>
            <div className="fields__row">
              <dt>{measuredOver(SPEND_LABEL, figures.range)}</dt>
              <dd>{minorUnits(figures.spendMinor)}</dd>
            </div>
            <div className="fields__row">
              <dt>{measuredOver(RUNS_LABEL, figures.range)}</dt>
              <dd>{figures.runs}</dd>
            </div>
          </>
        )}
        {divergent.length === 0 ? null : (
          <div className="fields__row">
            <dt>{DIVERGENCE_LABEL}</dt>
            <dd>
              {divergent.map((part) => (
                <code className="roster__clause" key={part}>
                  {part}
                </code>
              ))}
            </dd>
          </div>
        )}
      </dl>
      {figures === undefined ? null : <p className="note">{basisWords(figures.basis)}.</p>}
    </section>
  );
}
