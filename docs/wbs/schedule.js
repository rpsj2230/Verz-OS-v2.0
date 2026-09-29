// ONE PHASE. Everything ships. 7 waves; wave six is the independent install proof only.
// Connectors are built against recorded vendor payloads and proved live on the install in the
// wave that builds them (owner, 2026-09-28, item 100): done means working on the install.
module.exports = {
  START:"2026-09-08", TRACK_CAP:10, LEAVES_PER_TRACK_DAY:14, INTEGRATION_DAYS:1,
  // modules large enough to run as two or three concurrent tracks
  SPLIT:{M39:2,M40:2,M32:2,M13:2,M37:3,M11:2,M14:2,M33:2,M30:2,M19:2,M27:2,M7:2,M16:2,M17:2},
  WAVE:{
    // W0 foundation - everything types against this
    // M41 is here because client independence is a property kept from the first commit,
    // not a packaging step at the end. A value stripped out later is a value that got
    // in, and the sweep that refuses one has to be green from day one or the final
    // audit becomes a year of drift cleaned in a panic.
    M0:0, M31:0, M38:0, M41:0,
    // W1 the gate - the one wave that is not compressed
    M1:1, M2:1, M3:1, M4:1, M24:1, M5:1,
    // W2 data, channels, retrieval - connectors coded against cassettes
    M32:2, M11:2, M10:2, M9:2, M12:2, M15:2, M7:2, M22:2, M23:2, M8:2,
    // W3 agents, knowledge, memory, console
    M13:3, M39:3, M20:3, M6:3, M28:3, M14:3, M16:3, M27:3, M33:3,
    // W4 doing, lifecycle, extensions
    M17:4, M40:4, M18:4, M21:4, M25:4, M26:4, M29:4, M34:4, M35:4,
    // W5 hands, delivery, scale, go-live
    M19:5, M30:5, M36:5, M37:5, M42:5
  },
  // Leaves whose module sits in one wave but whose own work cannot happen until a later
  // one. M38 is continuous delivery: the pipeline is wave 0, but "what is live after each
  // wave" and go-live against real credentials are, by definition, those waves.
  //
  // Without this the wave-0 denominator contains work that wave 0 cannot do, so wave 0 can
  // never reach 100% and the figure on /build understates real progress. Nothing is removed
  // from the programme by this map; the total is unchanged and the work is only re-dated to
  // the wave that can actually do it.
  LEAF_WAVE:{
    // The Maintenance agent needs connectors, knowledge and agents (Waves 2-3): owner, 2026-09-21, item 77.
    "M38.5.3":3,
    // The starter pack needs the template signing key built in Wave 3: owner, 2026-09-21, item 82.
    "M41.2.7":3,
    // The template signing key itself is pulled forward so agents can be published from the
    // console: owner, 2026-09-29, item 82.
    "M13.8.10":2,
    // "Every <area> requirement is demonstrated on an install" closes only when every row of the
    // area has its proof, and most of those proofs are later waves' work (measured 2026-09-29: 69 of
    // 80 permissions rows are proved in Wave 3). Each moves to the wave of its area's last proof:
    // owner, 2026-09-29, item 112.
    "M5.6.5":3, "M1.8.8":4, "M2.3.2":4, "M24.3.6":5,
    // "Each of OpenAI, Anthropic, Moonshot and DeepSeek answers": the owner turned OpenAI and DeepSeek
    // off on 2026-09-29 until their accounts are funded, to use them later: owner, 2026-09-29, item 113.
    "M5.7.1":5,
    // The full profile needs presidio, which the redactor (M4) uses: owner, 2026-09-21, item 77.
    "M0.4.2":1,
    // Ignoring a duplicate chat delivery needs Wave 2's inbound chat route: owner, 2026-09-22, item 95.
    "M3.2.2":2,
    // Sharing the provider's tool cache needs agents that call tools (Wave 3): owner, 2026-09-22, item 95.
    "M3.7.2":3,
    // The chat halves of the sign-in and department checks need Wave 2's Lark chat channel: owner, 2026-09-28, item 97.
    "M1.8.5":2, "M2.3.1":2,
    // Proved with an agent, which Wave 3 creates: owner, 2026-09-28, item 100. Their Wave 2 parts
    // are built in Wave 2 and the task closes when the agent half is proved.
    "M11.9.3":3, "M11.9.4":3, "M11.9.5":3, "M11.9.6":3, "M11.9.7":3, "M11.9.8":3, "M11.9.9":3, "M11.9.10":3, "M11.9.11":3, "M11.9.12":3, "M11.9.13":3, "M11.9.14":3, "M11.8.8":3, "M10.7.3":3, "M12.2.5":3, "M12.2.7":3, "M12.2.8":3, "M12.3.3":3, "M12.4.8":3, "M12.4.10":3, "M8.2.4":3, "M8.3.5":3, "M11.8.10":3, "M12.4.2":3, "M5.7.3":3,
    // "What is live after each wave" - each line is that wave's own exit criterion.
    "M38.2.2.2":1, "M38.2.2.3":2, "M38.2.2.4":3, "M38.2.2.5":4, "M38.2.2.6":5,
    // A smoke test needs a real person asking a real question, so the gate must exist.
    "M38.2.1.4":1,
    // "Restore drill from wave three onward" - the task says so itself.
    "M38.2.1.5":3,
    // The evening report is sent into Lark, which W2 ships.
    "M38.3.3.1":2, "M38.3.3.2":2, "M38.3.3.3":2, "M38.3.3.4":2,
    // Contract tests need the connector adapters they test.
    "M38.4.1.2":2,
    // Go-live: real credentials against live APIs.
    "M38.4.2.1":5, "M38.4.2.2":5, "M38.4.2.3":5, "M38.4.2.4":5, "M38.4.2.5":5,
    // The audit and the independent install are the only leaves that need a finished,
    // deployed, verified system to exist first. Everything else in M42 describes and
    // scripts a system being built, and waiting for go-live to write any of it is how a
    // deployment guide ends up describing what somebody remembers.
    "M42.4.1":6, "M42.4.2":6, "M42.4.3":6, "M42.4.4":6, "M42.4.5":6, "M42.4.6":6
  },
  NAMES:{
    0:"Foundation", 1:"The gate", 2:"Data, channels, retrieval",
    3:"Agents, knowledge, console", 4:"Doing, lifecycle, extensions",
    5:"Hands, delivery, go-live", 6:"Client template"
  }
};
