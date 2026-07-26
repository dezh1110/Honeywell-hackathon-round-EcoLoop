# EcoLoop Backend — closed-loop building agent

**See [`SYSTEM_ARCHITECTURE.md`](./SYSTEM_ARCHITECTURE.md) for the full
tool-calling architecture, prompt engineering strategy, latency management,
and log-handling design.** This README covers setup and what's verified;
that document covers how and why it's built the way it is.

Implements the hackathon spec's three required pieces, plus a feature pack
aimed at judge-legible explainability on top of the core closed loop:

1. **Simulation Engine** — `app/energyplus/runtime.py` drives a real
   EnergyPlus simulation through its EMS Python API (`pyenergyplus`),
   reading zone temperatures/PMV/facility electricity every timestep and
   writing thermostat setpoints back via an EMS actuator — a true closed
   loop, not file-rewriting between separate runs.
   `app/energyplus/baseline_runner.py` runs the same model unmodified
   first, so `optimized_kw` vs `baseline_kw` is a genuine comparison for the
   real EnergyPlus backend, not just the mock one.
2. **Cognitive Engine & Protocol** — `app/mcp/` exposes the building's state
   and control surface as MCP tools; `app/agent/react_agent.py` is a
   ReAct-style loop against any OSS LLM (Llama 3, Mistral, Qwen…) served
   behind an OpenAI-compatible endpoint (Ollama, vLLM, LM Studio, TGI).
3. **Closed-Loop Execution** — `app/main.py` wires
   telemetry → reasoning → setpoint → forward injection, and logs every
   cycle to the same Supabase project the React dashboard already reads.

**Explainability & operator tooling on top of the loop:**
- **Reasoning trace** — every decision cycle's actual MCP tool calls (not
  just the one-line summary) are stored in `building_logs.reasoning_trace`
  and rendered as an expandable trace in the dashboard.
- **Self-correction loop** — when a proposed setpoint gets safety-clamped,
  `app/energyplus/safety.py` records why; the *next* reasoning cycle's
  prompt includes that note, and the system prompt tells the model not to
  repeat the same out-of-bounds proposal. See
  `tests/test_self_correction.py`.
- **NLP Insights** — `answer_nlp_question()` runs a read-only ReAct pass
  (no `set_zone_setpoint` in its tool set) so an operator can ask plain-
  language questions from the dashboard without risking an accidental
  setpoint change. Polled via the `nlp_queries` table.
- **What-If Simulator** — `app/agent/whatif.py` projects a proposed
  setpoint's kW and comfort (PMV) impact using the same RC thermal model as
  the mock backend, *before* an operator commits to it. Polled via the
  `whatif_requests` table. This is a fast approximation, not a full
  EnergyPlus re-run — labeled as such in the UI.
- **Predictive alerts** — `app/agent/recommendations.py` turns raw signals
  (grid-carbon peaks, override frequency, extreme temperatures) into
  proactive operator-facing recommendations, logged with
  `event_type='recommendation'` and shown in a separate Alerts panel.
- **Safety & audit trail** — every setpoint (agent, safety-clamped, or
  manual override) is in `control_actions` with its `source`; the
  dashboard's Safety & Audit panel surfaces the counts and the clamp rate.

A second, `SIMULATION_BACKEND=mock` mode (`app/energyplus/mock_runtime.py`)
implements the exact same decision-callback contract with a lightweight RC
thermal model, so you can develop/demo the LLM + MCP + dashboard stack
without installing EnergyPlus. Flip one env var to go from that to the real
physics engine — nothing else in the agent changes.

## Quick start (mock mode, no EnergyPlus needed)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env defaults to SIMULATION_BACKEND=mock — good for a first run

# Optional but recommended: a real local LLM instead of relying on
# LLM connection errors being swallowed (the agent holds setpoints and
# logs a warning if the LLM endpoint is unreachable, it won't crash).
#   ollama pull llama3.2:3b
#   ollama serve

python -m app.main
```

You should see log lines like:
```
[07/25 14:30:00] baseline=0.42kW optimized=0.31kW avg_zone_temp=23.4C carbon=372gCO2/kWh
```
and, if Supabase is configured (see below), the same rows landing in
`building_telemetry` / `building_logs` in real time for the dashboard.

## Verified against real EnergyPlus

This model and the Python EMS bridge (`app/energyplus/runtime.py`) have been
run end-to-end against a real **EnergyPlus 26.1.0** install (Linux,
Ubuntu 24.04), including the actual closed loop: live sensor reads, an
injected decision callback, and a real actuator write that measurably
changed one zone's temperature trajectory versus its neighbors — not just a
static syntax check.

That process caught six real bugs a cross-reference check alone can't catch
(it only verifies that referenced *names* exist, not that field *positions*
or *values* are correct):

1. All 24 `BuildingSurface:Detailed` objects had a vertex-count field
   misalignment (`,1,,,` instead of `,1,4,`) that shifted every vertex
   coordinate by two positions.
2. The `People` objects' CO2 generation rate landed in the wrong field
   (silently overwriting "Mean Radiant Temperature Calculation Type").
3. The `Lights` objects were missing the "Fraction Replaceable" field,
   pushing the End-Use Subcategory into the wrong slot.
4. `RunPeriod`'s last field must be an enum (`Hour1`/`Hour24`), not `Yes`/`No`.
5. Interior partition walls had the paired surface's name in the wrong
   field (`Space Name` instead of `Outside Boundary Condition Object`) and
   the wrong boundary condition type — fixed by switching to explicit
   `Surface`-type matching.
6. `ZoneControl:Thermostat`'s control-type schedule was wired to a generic
   on/off schedule instead of one containing the integer control code (`4`)
   for the `DualSetpoint` control actually being used.
7. The Fanger PMV comfort model was returning nonsense (~-22, far outside
   the valid -3..+3 range) because the People objects' Activity Level
   Schedule -- which is a metabolic rate in **Watts**, not a 0-1 fraction --
   was wired to the generic "Always On" (value 1.0) schedule. Fixed with a
   dedicated ~120W schedule plus the clothing/air-velocity schedules Fanger
   needs, and a `Fanger` comfort model type declaration on each `People`
   object.
8. A units bug in `runtime.py`'s Python side: it divided the meter's
   per-timestep Joules by a fixed 3,600,000 (seconds/hour), which is only
   correct if the zone timestep were exactly one hour. For this model's
   10-minute timestep that silently under-reported power by 6x. Fixed by
   dividing by `zone_time_step()` (the actual timestep length in fractional
   hours) instead of a hardcoded constant.

**One environment-specific note, not a bug in the model:** this particular
EnergyPlus 26.1.0 build's Data Exchange API returns an invalid handle for
`Electricity:Facility` specifically, even though the meter exists (it shows
up in `eplusout.mdd`). `Electricity:Building` is exposed by the same API and
is numerically identical for this model (there are no exterior-only end
uses), so `runtime.py` uses that instead — confirmed by comparing its value
against the `.csv`-reported `Electricity:Facility` value for the same
timestep. If you add exterior lighting/equipment to the model, or the
handle behaves differently on the exact EnergyPlus build you install,
revisit that one line.

After all of the above: `EnergyPlus Completed Successfully -- 21 Warning; 0
Severe Errors`, real zone temperatures/PMV/facility power in the output
files, and a confirmed forward-injection (the targeted zone's temperature
measurably diverged from its untouched neighbors after a setpoint change).

## Running against real EnergyPlus (setup steps)

1. Install EnergyPlus ≥ 24.1 for your OS from
   https://github.com/NREL/EnergyPlus/releases (adds `pyenergyplus` under the
   install directory). This was built and tested against 26.1.0.
2. Set `ENERGYPLUS_INSTALL_DIR` in `.env` to that install path.
3. `models/weather/bengaluru.epw` is bundled and set as the default
   `EPW_PATH` — a real Bengaluru weather file (see
   `models/weather/README.md` for exactly what it is: a climate-morphed
   near-term projection, not a strict current-year TMY file, and where to
   get one of those instead if you need it). Verified running successfully
   through a real EnergyPlus 26.1.0 install with this project's IDF.
4. `models/small_office.idf` is complete, self-contained, and has been run
   successfully end-to-end — see "Verified against real EnergyPlus" above.
5. `SIMULATION_BACKEND=energyplus` in `.env`, then `python -m app.main`.

## Running the MCP server standalone

Useful if you want a separate LLM host (e.g. Claude Desktop) to attach to
the same tools instead of the embedded ReAct loop:

```bash
python -m app.mcp.server            # stdio transport
MCP_TRANSPORT=sse python -m app.mcp.server   # SSE on MCP_SSE_PORT
```

Note: in standalone mode, `get_current_telemetry` only has data once you add
a Supabase read (see the comment in `app/telemetry/shared_state.py`) — the
embedded mode used by `app.main` doesn't need this because it shares process
memory with the simulation.

## Supabase setup

1. Create a Supabase project (or reuse the frontend's).
2. Run **all** migration files against it, in order: the frontend's
   `../supabase/migrations/*.sql` (creates `building_logs`), then this
   backend's `supabase/migrations/*.sql` files in filename order — the first
   adds `building_telemetry`, `control_actions`, `control_overrides`; the
   second adds `nlp_queries`, `whatif_requests`, and the `reasoning_trace`
   column + `recommendation` event type on `building_logs`.
3. Set `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (service role, not anon — this
   is a server-side process) in `.env`.
4. Point the frontend's `.env` (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`)
   at the same project.

## Tests

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -v
```

Tests cover IDF error parsing, safety clamping, and the ReAct tool-calling
loop against a fake LLM client — none require EnergyPlus or a real LLM
endpoint, so they run in CI.

## Safety

Every setpoint the LLM proposes passes through `app/energyplus/safety.py`
before being applied, regardless of backend. The agent can suggest anything;
it can only ever actuate within `MIN/MAX_*_SETPOINT_C` in `.env`.

## What's still a PoC, not production

Being upfront about this (matching the honesty the rest of this project aims
for):
- The mock RC model is a deliberately crude single-node thermal
  approximation — good for demoing the control loop, not for anything
  resembling real load prediction.
- The IDF's HVAC electricity number is itself a modeled approximation (an
  EMS-computed COP-based proxy on top of Ideal Loads, not a physically
  simulated compressor/fan) — appropriate for a fast, curve-free PoC model,
  but not the same fidelity as a fully specified packaged DX unit.
- `models/weather/bengaluru.epw` is a climate-morphed near-term projection
  (RCP4.5, 2026-2045 median), not a strict current-year TMY file — see
  `models/weather/README.md` for exactly what it is and a link to a
  standard TMY source if you need one for anything beyond a demo.
- `shared_state.py`'s Supabase-read fallback for the standalone MCP server
  isn't implemented — only the embedded (single-process) path is.
- No authentication/authorization anywhere (matches the existing frontend's
  single-tenant, no-auth design) — add real auth before exposing this beyond
  a demo.
