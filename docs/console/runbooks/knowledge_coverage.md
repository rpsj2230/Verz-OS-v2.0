# Knowledge coverage

Where the answers come from and where they cannot: which areas are covered, which are stale, and which have nothing behind them at all.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `knowledge_coverage` |
| Title | Knowledge coverage |
| Group | `operate` |
| Tool | `console.knowledge_coverage` |
| Needs | `read:knowledge_coverage` |
| Console plane | `read:console.existence` |
| Narrowed by | `department, person, connector, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

For each department you reach, how many knowledge items there are and how fresh they are, band by band (`CoverageRow`): where answers can come from, and where nothing is behind them at all. There is no total for the whole corpus.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.knowledge_coverage` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:knowledge_coverage` and `read:console.existence`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

The rows use the knowledge reach from `brain.knowledge.search.reach_for`, so each figure counts only items that reach admits, and a department outside it has no row.

## When it is empty or refuses

An empty list means you hold no read of the knowledge plane at all, an expired person included, or that your grant admits no department; the two look the same. A department with zero items is a gap, and finding gaps is the point of the screen. A grant whose scope cannot be reduced to departments is refused by `reach_for`.

## When it shows an alarm

`Freshness.STALE` is the band this screen exists for: re-verify or re-sync that department's documents. `AGEING` is worth checking. `UNSTATED` means nobody has vouched for the item or its timestamp is in the future, which is not the same as stale. The bands come from `DEFAULT_HORIZON`, which an install can retune.
