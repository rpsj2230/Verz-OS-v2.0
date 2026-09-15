# Service levels

Each lane's measured latency and success rate over a window, against the objective it promises, and which lanes could not be measured at all.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `service_levels` |
| Title | Service levels |
| Group | `report` |
| Tool | `console.service_levels` |
| Needs | `read:usage` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `no` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

For each lane the install declares an objective for (fast, answer and task), over a window: how many requests it carried, the 95th percentile latency where the lane promises one, the share of requests that succeeded, and every way the lane falls short of its objective (`service_levels.against_target`, `LaneReading`). The objectives themselves are `reliability.LANE_OBJECTIVES`.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.service_levels` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:usage` and `read:console.configuration`, both, and a role on its own confers neither. It shares `read:usage` with Usage and tokens, because a reading is a count of the same activity, and a separate grant would let somebody read the whole install's request volume without being allowed any department's usage.

A department admin is not offered it in their menu, for the reason recorded against it in the screen registry, and anybody holding the capability still reaches it by its address. The reading is the whole install's and cannot be narrowed, so only a `read:usage` grant with no scope shows it (`service_level_view.may_read_service_levels`). The department and person filters narrow nothing on this screen.

## When it is empty or refuses

No lanes at all means either that your `read:usage` grant is missing or scoped to a department, or that this install declares no objectives. The screen deliberately shows the two the same way.

A lane with no requests in the window is shown as unmeasured rather than met. A lane with a latency objective and fewer than 20 requests has no percentile, because a 95th percentile over fewer is just the slowest request. Latency is only recorded as a duration today, and every request is currently recorded on the fast lane, so the answer and task lanes read unmeasured until something routes to them.

## When it shows an alarm

A shortfall names the lane and what it missed. Latency above the objective on the fast lane means the gate or the row read has slowed; on the answer lane, look at the model provider first. A success rate below the objective means requests are failing rather than being refused: a withheld record and an absent one both count as success here. Unmeasured is not an alarm about the system, it is a window too short or too quiet to say anything, so widen the window before acting on it.
