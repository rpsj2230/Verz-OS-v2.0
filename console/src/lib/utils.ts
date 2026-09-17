/**
 * Class names for the component layer: joined, with the later of two conflicting utilities kept.
 *
 * shadcn/ui's own `cn`, on `clsx` and `tailwind-merge`, rather than the single `cn` package the
 * design spike used. The spike's package is newer and describes itself as a drop-in replacement;
 * it also carried 41.5 kB unminified into the spike's entry chunk against the two libraries it
 * replaces, and every component copied from shadcn/ui or from a template built on it is written
 * against this pair. Choosing the pair keeps a pasted component working with no edit to its
 * imports' meaning.
 *
 * Why merging matters rather than joining: a component that says `px-2.5` and a caller that says
 * `px-4` would otherwise both reach the element, and which one wins is decided by the order the
 * utilities happen to be written in the generated stylesheet, not by who asked last.
 *
 * Task ids: M27.10.2
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
