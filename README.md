# EcoLoop — Autonomous Building Energy Agent

A closed-loop physical-AI system for HVAC optimization: EnergyPlus (real
building physics) + an open-source LLM (via MCP tools) + a live dashboard,
built around the "Eco-Loop Building Agents" hackathon spec.

```
┌───────────────┐   telemetry (zone temp, PMV, kW)   ┌──────────────────┐
│  EnergyPlus   │ ─────────────────────────────────► │   MCP Tools      │
│  (or mock RC  │                                     │  get_telemetry   │
│  thermal model)│ ◄───────────────────────────────── │  get_grid_carbon │
└───────────────┘   setpoint (EMS actuator, clamped)  │  set_setpoint    │
        ▲                                              └────────┬─────────┘
        │                                                        │
        │                                              ┌─────────▼────────┐
        │  Supabase (telemetry, logs, control_actions)  │  ReAct agent      │
        └───────────────────────────────────────────────┤  (OSS LLM via     │
                                                          │  Ollama/vLLM/etc)│
┌──────────────────┐        realtime subscribe           └──────────────────┘
│  React dashboard │ ◄───────────────────────────────────────────
│  (this repo root)│
└──────────────────┘
```

## Structure

- `src/`, `index.html`, `package.json` — the React/Vite/Tailwind dashboard,
  with four tabs: **Overview** (KPIs, telemetry, control panel), **Agent &
  Alerts** (expandable reasoning trace, predictive alerts, NLP chat, safety
  audit), **Analytics** (energy heatmap, zone thermal-coupling graph, cost
  impact), **What-If Simulator** (predict a setpoint change's impact before
  committing).
- `backend/` — the Python closed-loop agent: EnergyPlus EMS integration,
  MCP server, ReAct agent, Supabase writer, NLP Q&A, what-if projection,
  recommendation heuristics. **See `backend/README.md`** for setup — that's
  where the actual "Eco-Loop" logic lives.
- `supabase/migrations/` — `building_logs` table (dashboard's reasoning feed).
- `backend/supabase/migrations/` — run both files here, in order: real
  telemetry/control-action/manual-override tables, then NLP/what-if/trace/
  alert tables.
- `docker-compose.yml` — runs the dashboard, the backend agent, and a local
  Ollama instance together.

## Running everything

**Before you start: give Docker Desktop enough memory.** Settings → Resources
→ Memory, at least 6-8GB for the whole stack (EnergyPlus + Ollama +
dashboard build). Too little and Ollama's model process gets OOM-killed
mid-run — the agent handles that gracefully rather than crashing, but it's
better avoided.

1. Create a Supabase project; run **all four migration files**, in order:
   `supabase/migrations/*.sql`, then the three files under
   `backend/supabase/migrations/*.sql` in filename order.
2. Copy `.env.example` to `.env` at the repo root (not just `backend/.env`)
   with `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_KEY`, and `SIMULATION_BACKEND`. **This root `.env` is
   what `docker-compose.yml` actually reads for `SIMULATION_BACKEND`** —
   editing `backend/.env` alone won't change it for the Docker path, since
   `docker-compose.yml`'s `environment:` block overrides it.
3. Also copy `backend/.env.example` to `backend/.env` (Compose passes this
   in via `env_file`, and it's also what a non-Docker local run uses).
4. `docker compose up --build` — starts Ollama, the backend agent (real
   EnergyPlus by default; see `backend/README.md` for what that involves),
   and the dashboard on http://localhost:5173.
5. `docker compose exec ollama ollama pull llama3.2:3b` (first run only,
   matches the default `LLM_MODEL` — pulling a different model without
   also setting `LLM_MODEL` to match will just trade one error for
   another), then `docker compose restart backend` so it picks up the model.


Or run each piece locally without Docker — `npm run dev` for the dashboard,
`python -m app.main` for the backend (see `backend/README.md`).

### Troubleshooting the Docker path (found by actually running it)

- **`OSError: libX11.so.6: cannot open shared object file`** — EnergyPlus's
  binary links against X11/GL libraries even for headless use.
  `backend/Dockerfile` installs them; if you're on an older copy of this
  repo without that fix, add `libx11-6 libxext6 libxrender1 libxrandr2
  libxi6 libsm6 libice6 libgl1 libglu1-mesa` to the `apt-get install` line.
- **`OSError: .../libenergyplusapi.so: cannot open shared object file`**
  persisting even after the above, especially on Apple Silicon (M1/M2/M3/M4)
  — check `uname -m` inside the container
  (`docker compose run --rm backend uname -m`). If it says `aarch64`, that's
  the real cause: the EnergyPlus release used here is x86_64-only.
  `docker-compose.yml`'s `backend` service sets `platform: linux/amd64` to
  force x86_64 emulation, which works but is slower than a native host.
- **`openai.InternalServerError: ... signal: killed`** — this is Ollama's
  model process getting OOM-killed by the OS, not a bug in the agent (the
  reasoning cycle fails gracefully and holds setpoints rather than
  crashing — see `app/main.py`). The default model (`llama3.2:3b`) needs
  roughly 2-3GB RAM — lighter than `llama3.1:8b` (~5-6GB), chosen
  specifically to reduce this risk — but if you're still hitting it, raise
  Docker Desktop's memory limit (Settings → Resources → Memory, 6-8GB+
  recommended for the whole stack) or drop to `llama3.2:1b` in the root
  `.env`.
- **`permission denied for table building_logs` (or similar)** — some
  Supabase projects need explicit grants to `service_role` even though it
  normally bypasses RLS. Run in the SQL Editor:
  ```sql
  GRANT SELECT, INSERT, UPDATE, DELETE ON public.building_logs TO service_role;
  GRANT SELECT, INSERT, UPDATE, DELETE ON public.building_telemetry TO service_role;
  GRANT SELECT, INSERT, UPDATE, DELETE ON public.control_actions TO service_role;
  GRANT SELECT, INSERT, UPDATE, DELETE ON public.control_overrides TO service_role;
  GRANT SELECT, INSERT, UPDATE, DELETE ON public.nlp_queries TO service_role;
  GRANT SELECT, INSERT, UPDATE, DELETE ON public.whatif_requests TO service_role;
  ```

## What's real vs. what's a documented stand-in

- The EnergyPlus EMS closed loop (`backend/app/energyplus/runtime.py`) is a
  genuine real-time integration, not a rewrite-the-file-and-rerun loop.
- The included `models/small_office.idf` is a realistic starting model but
  ships with a few HVAC sub-objects intentionally left for you to fill in —
  flagged clearly in `backend/README.md` rather than silently glossed over.
- A `SIMULATION_BACKEND=mock` mode is included so the LLM/MCP/dashboard loop
  can be demoed without an EnergyPlus install; it's explicitly labeled as a
  stand-in, not a substitute for the real physics engine.
