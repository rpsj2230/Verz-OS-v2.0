/**
 * Every page object, by the module group it covers.
 *
 * `specs/modules.spec.ts` fails when the served menu has a group with no entry here, and
 * `tests/unit/test_browser_harness.py` fails when `brain.console.screens.ModuleGroup` has a value
 * with no file in this directory. The two together are the "page object per module" of M27.10.6.
 *
 * Task ids: M27.10.6
 */

import { agents } from "./agents";
import { channels } from "./channels";
import { governance } from "./governance";
import { home } from "./home";
import { knowledge } from "./knowledge";
import type { ModulePage } from "./module";
import { operations } from "./operations";
import { people } from "./people";
import { platform } from "./platform";
import { reports } from "./reports";

export const MODULE_PAGES: ReadonlyMap<string, ModulePage> = new Map(
  [home, people, agents, knowledge, channels, operations, governance, reports, platform].map((one) => [one.group, one]),
);
