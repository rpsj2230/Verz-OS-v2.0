/**
 * A step's picture: a simplified outline of the screen the step happens on, drawn from the API's
 * description of it (`brain.ops.connect_steps.Sketch`).
 *
 * **Drawn here, in the product's own colours, and never an image from anywhere.** The API says
 * what the screen is (its address bar in words, its left menu, its heading, its tabs, a few rows
 * and the button to press) and which of those to look at; this turns that into SVG with the
 * theme's tokens, so it reads in the light and the dark theme alike and carries no vendor artwork.
 * A screenshot would be wrong the day the vendor moved a button and could not be taken without the
 * owner's logins; an outline goes stale only when the words do, and the words are the step's own.
 * See `A_PICTURE_IS_AN_OUTLINE_THAT_NAMES_WHERE_TO_PRESS` on the server.
 *
 * **Each marked element carries a number, and the caption repeats them in words**, so the picture
 * and the sentence beside it point at the same thing, and a reader who cannot see the picture has
 * the same list.
 *
 * Task ids: M11.9.4, M27.11.9
 */

import { useId } from "react";
import type { components } from "../../api/schema";
import { cn } from "../../lib/utils";

export type SketchView = components["schemas"]["SketchView"];
export type SketchLine = components["schemas"]["SketchLineView"];

const WIDTH = 480;
const HEIGHT = 300;
const BAR = 28;
const MENU_WIDTH = 132;
const ROW = 34;
const GUTTER = 16;

/** Roughly how wide a character is at a font size, for cutting a label to fit its box. */
function fits(text: string, width: number, size: number): string {
  const most = Math.max(1, Math.floor(width / (size * 0.56)));
  return text.length <= most ? text : `${text.slice(0, Math.max(1, most - 1))}…`;
}

/** Every marked element in reading order, which is the order the numbers are drawn in. */
export function sketchMarks(sketch: SketchView): readonly string[] {
  const rows = sketch.lines.filter((one) => one.mark).map((one) => one.label);
  return [sketch.menu_mark, sketch.tab_mark, ...rows, sketch.button].filter((one) => one.trim() !== "");
}

/** What the picture shows, in words, for a reader who cannot see it. */
export function sketchWords(sketch: SketchView): string {
  const marks = sketchMarks(sketch);
  const where = `${sketch.place}, ${sketch.heading}.`;
  return marks.length === 0 ? where : `${where} ${marks.map((one, index) => `${index + 1}: ${one}`).join(". ")}.`;
}

function Badge({ x, y, n }: { readonly x: number; readonly y: number; readonly n: number }) {
  return (
    <g aria-hidden>
      <circle cx={x} cy={y} r={8} className="fill-acc-text" />
      <text x={x} y={y + 3.5} textAnchor="middle" fontSize={10} fontWeight={700} className="fill-panel">
        {n}
      </text>
    </g>
  );
}

function Row({ line, x, y, width }: { readonly line: SketchLine; readonly x: number; readonly y: number; readonly width: number }) {
  const mark = line.mark;
  const tint = mark ? "fill-acc-text" : "fill-ink";
  switch (line.kind) {
    case "field":
      return (
        <g>
          <text x={x} y={y + 10} fontSize={10} className="fill-dim">
            {fits(line.label, width, 10)}
          </text>
          <rect x={x} y={y + 14} width={width} height={17} rx={4} className={cn("fill-ground", mark ? "stroke-acc-text" : "stroke-line")} />
          <text x={x + 7} y={y + 26} fontSize={10} className="fill-body font-mono">
            {fits(line.value, width - 14, 10)}
          </text>
        </g>
      );
    case "item":
      return (
        <g>
          <rect x={x} y={y + 10} width={12} height={12} rx={2.5} className={mark ? "fill-acc-text stroke-acc-text" : "fill-panel stroke-line"} />
          {mark ? <path d={`M${x + 3} ${y + 16} l2.5 2.5 l4 -5`} className="fill-none stroke-panel" strokeWidth={1.6} /> : null}
          <text x={x + 19} y={y + 20} fontSize={11} fontWeight={mark ? 600 : 400} className={tint}>
            {fits(line.label, width - 19 - (line.value === "" ? 0 : 70), 11)}
          </text>
          {line.value === "" ? null : (
            <text x={x + width} y={y + 20} fontSize={10} textAnchor="end" className="fill-dim">
              {fits(line.value, 66, 10)}
            </text>
          )}
        </g>
      );
    case "toggle":
      return (
        <g>
          <text x={x} y={y + 20} fontSize={11} className={tint}>
            {fits(line.label, width - 40, 11)}
          </text>
          <rect x={x + width - 28} y={y + 10} width={28} height={14} rx={7} className={mark ? "fill-acc-text" : "fill-line"} />
          <circle cx={x + width - (mark ? 7 : 21)} cy={y + 17} r={5} className="fill-panel" />
        </g>
      );
    default:
      return (
        <text x={x} y={y + 20} fontSize={11} className="fill-dim">
          {fits(line.label, width, 11)}
        </text>
      );
  }
}

export function StepSketch({ sketch, className }: { readonly sketch: SketchView; readonly className?: string | undefined }) {
  const titleId = useId();
  const menu = sketch.menu.length > 0;
  const left = menu ? MENU_WIDTH + GUTTER : GUTTER;
  const width = WIDTH - left - GUTTER - 8;
  const buttonWidth = sketch.button === "" ? 0 : Math.min(Math.max(sketch.button.length * 6.2 + 22, 64), width * 0.55);
  const tabsTop = 72;
  const rowsTop = sketch.tabs.length > 0 ? 104 : 78;
  const room = Math.max(0, Math.floor((HEIGHT - rowsTop - 8) / ROW));
  const rows = sketch.lines.slice(0, room);
  let badge = 0;
  const next = (): number => {
    badge += 1;
    return badge;
  };
  const menuTop = BAR + 12;
  const markedItem = sketch.menu.indexOf(sketch.menu_mark);
  const menuBadge = sketch.menu_mark === "" ? 0 : next();
  // Tabs are laid left to right and a tab that would run past the edge is not drawn: the picture
  // needs the tab to press and its neighbours only as context.
  let tabX = left;
  const tabs = sketch.tabs.flatMap((tab) => {
    const at = tabX;
    const room = Math.min(tab.length * 5.6 + 8, 142);
    tabX += room + 22;
    return at + room <= left + width || tab === sketch.tab_mark ? [{ tab, at }] : [];
  });
  const tabBadge = sketch.tab_mark === "" ? 0 : next();
  const rowBadges = rows.map((one) => (one.mark ? next() : 0));
  const buttonBadge = sketch.button === "" ? 0 : next();

  return (
    <svg
      data-slot="step-sketch"
      role="img"
      aria-labelledby={titleId}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className={cn("h-auto w-full select-none", className)}
    >
      <title id={titleId}>{`A picture of the screen: ${sketchWords(sketch)}`}</title>
      <rect x={1} y={1} width={WIDTH - 2} height={HEIGHT - 2} rx={10} className="fill-panel stroke-line" />
      <path d={`M1 ${BAR} V11 a10 10 0 0 1 10 -10 H${WIDTH - 11} a10 10 0 0 1 10 10 V${BAR} Z`} className="fill-sunk" />
      <line x1={1} y1={BAR} x2={WIDTH - 1} y2={BAR} className="stroke-line" />
      {[14, 26, 38].map((cx) => (
        <circle key={cx} cx={cx} cy={BAR / 2} r={3.5} className="fill-line" />
      ))}
      <rect x={56} y={7} width={WIDTH - 112} height={15} rx={7.5} className="fill-panel stroke-line" />
      <text x={WIDTH / 2} y={18} fontSize={9.5} textAnchor="middle" className="fill-dim">
        {fits(sketch.place, WIDTH - 130, 9.5)}
      </text>

      {menu ? (
        <g>
          <rect x={1} y={BAR + 0.5} width={MENU_WIDTH} height={HEIGHT - BAR - 2} className="fill-sunk" />
          <line x1={MENU_WIDTH + 1} y1={BAR} x2={MENU_WIDTH + 1} y2={HEIGHT - 1} className="stroke-line" />
          {sketch.menu.map((item, index) => {
            const top = menuTop + index * 28;
            const marked = index === markedItem;
            return (
              <g key={item}>
                {marked ? <rect x={6} y={top} width={MENU_WIDTH - 11} height={23} rx={5} className="fill-acc-wash stroke-acc-text" /> : null}
                <text x={13} y={top + 15.5} fontSize={10} fontWeight={marked ? 600 : 400} className={marked ? "fill-acc-text" : "fill-body"}>
                  {fits(item, MENU_WIDTH - (marked ? 40 : 22), 10)}
                </text>
                {marked ? <Badge x={MENU_WIDTH - 14} y={top + 11.5} n={menuBadge} /> : null}
              </g>
            );
          })}
        </g>
      ) : null}

      <text x={left} y={58} fontSize={14} fontWeight={600} className="fill-ink">
        {fits(sketch.heading, width - buttonWidth - 12, 14)}
      </text>
      {sketch.button === "" ? null : (
        <g>
          <rect x={left + width - buttonWidth} y={40} width={buttonWidth} height={25} rx={6} className="fill-brand" />
          <text x={left + width - buttonWidth / 2} y={56.5} fontSize={10.5} fontWeight={600} textAnchor="middle" className="fill-brand-ink">
            {fits(sketch.button, buttonWidth - 12, 10.5)}
          </text>
          <rect
            x={left + width - buttonWidth - 3.5}
            y={36.5}
            width={buttonWidth + 7}
            height={32}
            rx={8}
            className="fill-none stroke-acc-text"
            strokeWidth={2}
          />
          <Badge x={left + width - buttonWidth - 4} y={37} n={buttonBadge} />
        </g>
      )}

      {tabs.length === 0 ? null : (
        <g>
          <line x1={left} y1={tabsTop + 20} x2={left + width} y2={tabsTop + 20} className="stroke-line" />
          {tabs.map(({ tab, at }) => {
            const marked = tab === sketch.tab_mark;
            const tabWidth = Math.min(tab.length * 5.6 + 8, 142);
            return (
              <g key={tab}>
                <text x={at} y={tabsTop + 13} fontSize={10} fontWeight={marked ? 600 : 400} className={marked ? "fill-acc-text" : "fill-dim"}>
                  {fits(tab, 142, 10)}
                </text>
                {marked ? (
                  <>
                    <line x1={at} y1={tabsTop + 20} x2={at + tabWidth} y2={tabsTop + 20} className="stroke-acc-text" strokeWidth={2} />
                    <Badge x={at + tabWidth + 8} y={tabsTop + 9} n={tabBadge} />
                  </>
                ) : null}
              </g>
            );
          })}
        </g>
      )}

      {rows.map((line, index) => {
        const y = rowsTop + index * ROW;
        return (
          <g key={`${line.label} ${index}`}>
            {line.mark ? <rect x={left - 6} y={y + 3} width={width + 12} height={ROW - 3} rx={6} className="fill-acc-wash" /> : null}
            <Row line={line} x={left} y={y} width={width} />
            {line.mark ? <Badge x={left + width + 13} y={y + 18} n={rowBadges[index] ?? 0} /> : null}
          </g>
        );
      })}
    </svg>
  );
}
