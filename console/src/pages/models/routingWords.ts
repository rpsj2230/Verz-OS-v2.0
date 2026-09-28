/**
 * The failover matrix as the Routing page draws it, and what its acts say before they are sent.
 *
 * **The rows are the owner's screenshot** (2026-09-03): Complexity, Step, Provider, Model, Role,
 * each level named once, its steps numbered from 1 in the order a question tries them. The rows
 * and their numbers are `GET /routing/rungs`, the matrix's own route; the role and the marker on a
 * step that will not answer are the plan's (`GET /models/providers`), which derives the role from
 * the chain as the next call walks it, so a level whose first step was just retired reads right.
 * When the plan cannot be read the stored role is drawn and no marker, never a guess.
 *
 * **A move is up, down, or to a named level and step**, and every one is confirmed saying it is
 * tried against the golden questions first, because a move can be held like any change.
 *
 * Task ids: M5.3.3, M27.15.38, M27.16.1
 */

import type { RungRow } from "../matrixQuery";
import { levelName, providerName, stepMarker, type ProviderStateRow, type RungStateRow, type StepMarker } from "../modelsQuery";

/** The levels in the order a question escalates through them. */
export const LEVELS: readonly ("small" | "main" | "heavy")[] = ["small", "main", "heavy"];

/** One row of the matrix: a step, or a level with none. */
export interface MatrixLine {
  readonly key: string;
  readonly tier: string;
  /** The level's name on its first row, and null after it. */
  readonly level: string | null;
  /** From 1 within the level; null on a level with no step. */
  readonly step: number | null;
  /** How many steps the level holds, for Move down. */
  readonly of: number;
  readonly rung: RungRow | null;
  readonly provider: string;
  readonly model: string;
  readonly role: string;
  readonly marker: StepMarker | null;
}

/** The matrix's lines: every level in ladder order, then any other the API named, by position. */
export function matrixLines(
  rungs: readonly RungRow[],
  plan: readonly RungStateRow[],
  providers: readonly ProviderStateRow[],
): MatrixLine[] {
  const planned = new Map(plan.map((one) => [one.rung_id, one]));
  const levels: string[] = [...LEVELS];
  for (const one of rungs) {
    if (!levels.includes(one.tier)) {
      levels.push(one.tier);
    }
  }
  const lines: MatrixLine[] = [];
  for (const tier of levels) {
    const steps = rungs.filter((one) => one.tier === tier).slice().sort((a, b) => a.position - b.position);
    if (steps.length === 0) {
      lines.push({
        key: `level-${tier}`,
        tier,
        level: levelName(tier),
        step: null,
        of: 0,
        rung: null,
        provider: "",
        model: "",
        role: "",
        marker: null,
      });
      continue;
    }
    steps.forEach((one, index) => {
      const step = planned.get(one.id);
      lines.push({
        key: one.id,
        tier,
        level: index === 0 ? levelName(tier) : null,
        step: index + 1,
        of: steps.length,
        rung: one,
        provider: providerName(one.provider, providers),
        model: one.model,
        role: step?.role ?? one.role,
        marker: step === undefined ? null : stepMarker(step),
      });
    });
  }
  return lines;
}

/** A step as a person names it: its number, its level, and what it calls. */
export function stepName(line: { readonly step: number | null; readonly tier: string; readonly provider: string; readonly model: string }): string {
  return `step ${String(line.step ?? 0)} of the ${levelName(line.tier)} level (${line.provider} ${line.model})`;
}

/** What every change on this page is tried against before it is used. */
export const TRIED_FIRST =
  "It is tried against the golden questions and the permission checks first: if nothing gets worse " +
  "the next question uses it, and if something does it is held with what failed and nothing changes.";

export function retireQuestion(line: MatrixLine): string {
  return `Retire ${stepName(line)}?`;
}

export function retireConsequence(line: MatrixLine): string {
  return (
    `The ${levelName(line.tier)} level stops trying this step, and the steps after it move up. ` +
    `${TRIED_FIRST} A level's last step cannot be retired.`
  );
}

export function moveQuestion(line: MatrixLine, tier: string, step: number): string {
  return tier === line.tier
    ? `Move ${stepName(line)} to step ${String(step)}?`
    : `Move ${stepName(line)} to step ${String(step)} of the ${levelName(tier)} level?`;
}

export function moveConsequence(tier: string, step: number): string {
  return (
    `It becomes step ${String(step)} of the ${levelName(tier)} level and the steps from there on move down one. ` +
    `It is saved as a new step in its new place and the old one is retired, both on the audit log. ${TRIED_FIRST}`
  );
}

export const RETIRE_STEP = "Retire";
export const KEEP_STEP = "Keep the step";
export const MOVE_STEP = "Move it";
export const MOVE_UP = "Move up";
export const MOVE_DOWN = "Move down";

/** The four numbers an edit carries, as `brain.routing_routes.RungEdit` declares them. */
export interface StepNumbers {
  readonly attempts: number;
  readonly timeout_seconds: number;
  readonly max_concurrency: number;
  readonly enabled: boolean;
}

export const SAVE_STEP = "Save these numbers";

export function saveQuestion(line: MatrixLine): string {
  return `Save new numbers for ${stepName(line)}?`;
}

export function saveConsequence(edit: StepNumbers): string {
  return (
    `The step would make ${String(edit.attempts)} attempt${edit.attempts === 1 ? "" : "s"}, wait ` +
    `${String(edit.timeout_seconds)} seconds for an answer, take at most ${String(edit.max_concurrency)} ` +
    `calls at once, and be ${edit.enabled ? "in use" : "paused"}. ${TRIED_FIRST}`
  );
}
