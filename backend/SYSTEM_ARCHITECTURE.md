# EcoLoop — System Architecture Document

## 1. Overview

EcoLoop is a closed-loop building energy agent: EnergyPlus simulates the
physical building, a ReAct-style loop drives an open-source LLM through a
set of MCP tools, and the LLM's decisions are forward-injected back into the
same running simulation via EnergyPlus's EMS actuator API. This document
covers the four things the spec specifically asks for: tool-calling
architecture, prompt engineering strategy, latency management, and handling
long simulation logs — plus a short note on what was verified by actually
running this against a real EnergyPlus install, not just written and
assumed correct.

```
EnergyPlus (pyenergyplus EMS API)
   |  sensors: zone temp, PMV, facility power, IAQ estimate
   v
app/energyplus/runtime.py  --(per-timestep callback)-->  app/main.py::make_decision
   ^                                                              |
   | actuator writes (cooling/heating setpoint)                   v
   +------------------------------------------------  app/agent/react_agent.py
                                                        (ReAct loop, MCP tools)
                                                                |
                                                                v
                                                     OSS LLM (OpenAI-compatible:
                                                     Ollama / vLLM / LM Studio)
```

## 2. Tool-calling architecture

The LLM never touches EnergyPlus, Supabase, or the filesystem directly —
every action goes through one of five MCP tools defined once in
`app/mcp/tools.py` and re-used in two different transports:

- **Embedded mode** (`app.main`, used for the actual closed loop): the
  ReAct agent in `app/agent/react_agent.py` calls the tool functions
  directly as Python function references — zero transport overhead, since
  agent and simulation share one process.
- **Standalone MCP server** (`python -m app.mcp.server`): the exact same
  functions, wrapped with `@mcp.tool()` and served over stdio or SSE, for a
  separate LLM host (e.g. Claude Desktop) to attach to.

Keeping the tool *implementations* in one module (`tools.py`) and having
both the embedded agent and the MCP server import from it means the tool
contract can't drift between the two paths — there's one definition of what
`set_zone_setpoint` does, not two.

The five tools:

| Tool | Purpose | Notes |
|---|---|---|
| `get_current_telemetry` | Read zone temps, PMV, facility kW, IAQ estimate, peak-demand threshold | Called first, every cycle |
| `get_grid_carbon` | Read current grid carbon intensity | Static diurnal curve or a real provider (electricitymaps), see `app/telemetry/carbon.py` |
| `get_recent_errors` | Parse the EnergyPlus `.err` file into a compact digest | See §4 |
| `list_zones` | Enumerate zones from the IDF | Read-only |
| `set_zone_setpoint` | Propose a cooling/heating setpoint change | The only actuation path; always passes through `app/energyplus/safety.py`'s clamp before it reaches the simulation |

A second, read-only tool subset (`READ_ONLY_TOOL_NAMES` in
`react_agent.py`) excludes `set_zone_setpoint` entirely and backs the
dashboard's NLP Insights panel — an operator asking a question can never
accidentally trigger a setpoint change, because the tool to do so isn't in
that call's tool list at all. This is enforced structurally (the tool
schema list passed to the LLM), not by a prompt instruction the model could
ignore.

## 3. Prompt engineering strategy

`app/agent/prompts.py` holds two system prompts sharing one design
philosophy: **make the model's job procedural, not open-ended.**

- **Explicit priority order.** The control-loop prompt states four
  priorities in order (comfort + IAQ → peak demand → carbon/energy →
  avoid unnecessary churn) rather than asking the model to "optimize
  everything," so trade-off decisions have a defined resolution order
  instead of being left to the model's judgment call each time.
- **A fixed per-cycle procedure.** The prompt spells out the exact tool-call
  sequence expected (telemetry → carbon → [errors if anomalous] → decide →
  act or don't) rather than leaving tool selection to chance. This
  materially reduces variance in what a smaller/quantized OSS model does
  cycle to cycle.
- **Explicit grounding instruction.** "Never invent sensor values" is
  stated directly, because small models under-specified on this point will
  confidently narrate plausible-sounding numbers instead of the tool's
  actual return value.
- **Self-correction feedback loop.** When a proposed setpoint gets
  safety-clamped, `app/energyplus/safety.py` writes a note to
  `shared_state.note_correction()`. The *next* cycle's user prompt includes
  any recent correction notes (see `react_agent.run_reasoning_cycle`), and
  the system prompt tells the model explicitly what to do with them: don't
  repeat the same out-of-bounds proposal. This turns clamping from a silent
  one-shot correction into something the agent can actually learn from
  within a session — verified with a real clamp-then-inspect test
  (`tests/test_self_correction.py`), not just described.
- **Output-length constraint.** The prompt caps the final summary at 1-2
  sentences, since this string is written directly to the dashboard's
  scrolling operator feed — a verbose model response would be
  operationally useless there regardless of reasoning quality.
- **Separate, narrower prompt for the NLP path.** `NLP_QA_SYSTEM_PROMPT` is
  deliberately not the control-loop prompt with a tool removed — it's
  written for a different audience contract (a human asking a question,
  answered in 2-4 grounded sentences) rather than reusing control-loop
  framing that doesn't fit a Q&A interaction.

## 4. Handling lengthy simulation logs

EnergyPlus `.err` files accumulate warnings across an entire run — for a
multi-day simulation this can be hundreds of lines, which would blow past
a reasonable context budget if handed to the LLM raw every cycle.
`app/energyplus/idf_utils.py` handles this in two stages:

1. **`parse_err_file`** turns the raw text into structured
   `EnergyPlusRuntimeError` records (severity + message), stripping
   EnergyPlus's fixed-width `** Warning **` formatting.
2. **`summarize_errors`** compresses that list into a fixed-size digest for
   the LLM: a one-line count ("2 fatal, 5 severe, 40 warning") followed by
   at most `max_items` (default 10) individual messages, **prioritized by
   severity** — fatal and severe errors always survive the truncation
   before warnings do, so the model doesn't miss something important buried
   after 200 low-priority warnings just because of ordering.

This keeps every reasoning cycle's error-context bounded and predictable in
size regardless of how long the simulation has been running, and it's the
same summarizer used both by the MCP `get_recent_errors` tool and by
`app/main.py`'s failure-path logging.

## 5. Latency management

Three layers keep the loop from stalling on a slow or unreachable LLM:

1. **Bounded tool-call iterations.** `settings.llm_max_tool_iterations`
   (default 6) caps how many tool-call round-trips one reasoning cycle can
   take before the loop gives up and returns a "reached max iterations"
   message rather than looping indefinitely against a model that won't
   converge to a final answer.
2. **Decision cadence, not every-timestep reasoning.**
   `agent_decision_every_n_timesteps` (default 3) means the LLM is
   consulted roughly every 30 simulated minutes, not every 10-minute zone
   timestep — reasoning latency only has to keep pace with the decision
   cadence, not the physics timestep, which is what makes a real (non-quantized
   local) LLM practical here at all.
3. **Failure isolation, not failure propagation.** `app/main.py::make_decision`
   wraps the reasoning call in a try/except: if the LLM endpoint is slow,
   unreachable, or errors, the exception is caught, logged as a
   `building_logs` warning, and the loop holds current setpoints rather
   than crashing the simulation or blocking indefinitely. This was a
   deliberate design choice — an LLM failure should degrade gracefully to
   "do nothing this cycle," never to "stop controlling the building."

## 6. What was verified by actually running this, not just written

This system was tested against a real EnergyPlus 26.1.0 install (not just
authored and assumed correct):

- The IDF and the Python EMS bridge were run end-to-end; that process
  surfaced and fixed 8 real bugs (see `backend/README.md` "Verified against
  real EnergyPlus" for the full list) that a static/syntax check alone
  would not have caught.
- A real setpoint change through the real actuator was confirmed to
  measurably change one zone's temperature trajectory versus its untouched
  neighbors in the same run.
- The baseline-vs-optimized comparison for the real EnergyPlus backend
  (`app/energyplus/baseline_runner.py`) was initially implemented as a
  concurrent second EnergyPlus instance; testing that against the real
  install surfaced a genuine concurrency bug (the baseline reading froze at
  an early value under GIL contention between two blocking native calls).
  It was redesigned to run the baseline simulation to completion first,
  caching its time series, then have the optimized run look up matching
  timestamps — the same approach real building-baseline methodologies
  (e.g. ASHRAE Guideline 14-style calibrated baselines) use, and confirmed
  working: baseline values now vary correctly across simulated time instead
  of freezing.

## 7. Known limitations (stated plainly, not hidden)

- The mock RC-model backend (`SIMULATION_BACKEND=mock`) is a deliberately
  crude single-node thermal approximation for demoing the loop without an
  EnergyPlus install — not a substitute for real building physics.
- The IDF's HVAC electricity accounting is an EMS-computed COP-based proxy
  on top of Ideal Loads, not a fully specified packaged DX unit with real
  performance curves.
- `models/weather/bengaluru.epw` is a real Bengaluru weather file (verified
  running successfully through EnergyPlus with this project's IDF), but
  it's a climate-morphed near-term projection (RCP4.5, 2026-2045 median),
  not a strict current-year TMY file — see `models/weather/README.md` for
  the full sourcing note and where to get a standard TMY file instead.
- No authentication anywhere — matches the frontend's single-tenant,
  no-auth demo design; add real auth before any production exposure.
