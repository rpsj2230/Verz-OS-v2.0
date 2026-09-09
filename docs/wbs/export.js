// Exports the work breakdown to JSON so the application can compute progress without
// needing Node at runtime. Run alongside render.js whenever the WBS changes.
const fs = require("fs");
const path = require("path");

const MODS = [].concat(
  require(path.join(__dirname, "wbs-a.js")),
  require(path.join(__dirname, "wbs-b.js")),
  require(path.join(__dirname, "wbs-c.js")),
  require(path.join(__dirname, "wbs-d.js")),
  require(path.join(__dirname, "wbs-e.js")),
  require(path.join(__dirname, "wbs-f.js"))
);
const SCH = require(path.join(__dirname, "schedule.js"));
const ACT = require(path.join(__dirname, "acts.js"));

// Leaf numbering must match render.js exactly, or a commit closing M0.2.4 would tick a
// different box in the tracker than the one the status page counts.
// Each leaf is pushed as [id, text] in one statement, so the two exported arrays cannot
// drift apart. Kept as pairs internally and split at the end rather than exported as an
// object keyed by id, which would repeat 1251 ids that leaf_ids already carries.
function leaves(node, prefix, out) {
  const kids = node.s || [];
  const keys = node.k || [];
  // render.js reads k-or-s; this reads s and then k. Identical while no node carries both,
  // and silently divergent the moment one does: the tracker would tick a different box than
  // the status page counts. Fail loudly rather than drift.
  if (kids.length && keys.length) {
    throw new Error(`${prefix} has both s and k children; render.js and export.js would number its leaves differently`);
  }
  kids.forEach((child, i) => {
    const id = `${prefix}.${i + 1}`;
    if (typeof child === "string") out.push([id, child]);
    else leaves(child, id, out);
  });
  keys.forEach((key, i) => out.push([`${prefix}.${kids.length + i + 1}`, key]));
}

// The name of every node that is not a leaf, by id. Only used for the ones holding a flagged
// leaf, and gathered by walking the tree the same way `leaves` does rather than by a second
// numbering: a heading over the wrong group is the same class of error as a flag on the wrong
// leaf, and it is the one a reader of the delivery checklist would believe.
function groups(node, prefix, out) {
  const kids = node.s || [];
  kids.forEach((child, i) => {
    if (typeof child === "string") return;
    const id = `${prefix}.${i + 1}`;
    out[id] = child.n;
    groups(child, id, out);
  });
}

//: Every leaf sentence in the whole breakdown, by id. Built before the modules so the flags
//: can be checked against it once, rather than per module where a flag naming a leaf in
//: another module would look like a flag naming no leaf at all.
const ALL_TEXTS = {};
const ALL_GROUPS = {};
MODS.forEach((m) => {
  (m.tasks || []).forEach((t, i) => {
    const pairs = [];
    leaves(t, `${m.id}.${i + 1}`, pairs);
    pairs.forEach(([id, text]) => (ALL_TEXTS[id] = text));
    ALL_GROUPS[`${m.id}.${i + 1}`] = t.n;
    groups(t, `${m.id}.${i + 1}`, ALL_GROUPS);
  });
});
// Throws rather than writing a stale `wbs.json`, so a leaf that moved under a flag is a build
// failure and not a checklist quietly listing different work. See the header of acts.js.
const ACT_COUNT = ACT.check((id) => ALL_TEXTS[id]);

const modules = MODS.map((m) => {
  const pairs = [];
  (m.tasks || []).forEach((t, i) => leaves(t, `${m.id}.${i + 1}`, pairs));
  const ids = pairs.map((one) => one[0]);
  // Only the leaves that differ from their module's wave, so the common case stays
  // absent rather than repeating the module wave 1148 times.
  const leaf_waves = {};
  const modWave = SCH.WAVE[m.id] ?? 0;
  ids.forEach((id) => {
    const w = (SCH.LEAF_WAVE || {})[id];
    if (w !== undefined && w !== modWave) leaf_waves[id] = w;
  });
  const leaf_acts = {};
  const act_groups = {};
  ids.forEach((id) => {
    const flag = ACT.ACTS[id];
    if (!flag) return;
    leaf_acts[id] = { kind: flag.kind, gate: flag.gate === true, why: flag.why || "" };
    // Every ancestor of the leaf that is a group, which is every prefix from the task down.
    const parts = id.split(".");
    for (let cut = 2; cut < parts.length; cut++) {
      const gid = parts.slice(0, cut).join(".");
      if (ALL_GROUPS[gid] !== undefined) act_groups[gid] = ALL_GROUPS[gid];
    }
  });
  return {
    id: m.id,
    name: m.name,
    wave: modWave,
    leaf_ids: ids,
    // The leaf sentences themselves, positionally aligned with leaf_ids. Python has no way
    // to read the .js sources, so before this every check of a constant against the leaf
    // that specifies it had to restate the leaf in the test, which is the constant compared
    // against itself wearing a different hat.
    leaf_texts: pairs.map((one) => one[1]),
    leaf_waves,
    // Leaves no commit can close, by id, with the kind and whether the leaf gates the
    // cutover. Absent from a module holding none, for the reason `leaf_waves` is: the common
    // case should be silence rather than 1218 entries saying nothing.
    leaf_acts,
    // The headings above those leaves, so the generated checklist can be read by somebody who
    // is not holding the tracker open. Only the ancestors of a flagged leaf, so a module with
    // no acts carries nothing.
    act_groups,
  };
});

const out = {
  generated_by: "docs/wbs/export.js",
  start: SCH.START,
  wave_names: SCH.NAMES,
  modules,
};

fs.writeFileSync(path.join(__dirname, "..", "wbs.json"), JSON.stringify(out, null, 1));
const total = modules.reduce((a, m) => a + m.leaf_ids.length, 0);
const gated = Object.values(ACT.ACTS).filter((one) => one.gate === true).length;
console.log(`wrote wbs.json: ${modules.length} modules, ${total} leaves`);
console.log(
  `  of which ${ACT_COUNT} are acts no commit can close, ${gated} of them gating the cutover;` +
    ` ${total - ACT_COUNT} buildable`
);
