/*
# Add tables for real closed-loop telemetry and control

The frontend project already ships `building_logs` (see its own
supabase/migrations/). This migration adds the three tables the Python
backend needs so the dashboard can plot *real* EnergyPlus/mock-model output
instead of client-side random telemetry, and so the Control Panel's
autonomous/manual toggle actually reaches the simulation.

1. New Tables
- `building_telemetry` — one row per agent decision cycle: baseline vs.
  optimized facility kW, grid carbon intensity, average zone temp, and the
  full per-zone reading array (jsonb) for drill-down.
- `control_actions` — audit trail of every setpoint change the system made,
  whether proposed by the agent or a human operator, post safety-clamp.
- `control_overrides` — write-only inbox the dashboard's Control Panel
  inserts into when a human manually sets a setpoint; the backend polls
  `applied = false` rows, applies them through the same safety clamp as the
  agent, and flips `applied` to true.

2. Security
- RLS enabled on all three, matching `building_logs`: anon + authenticated
  can select/insert (single-tenant demo, no auth). Restrict this before any
  real deployment with untrusted users.
- Realtime enabled on `building_telemetry` and `control_actions` so the
  dashboard can subscribe instead of polling.
*/

CREATE TABLE IF NOT EXISTS building_telemetry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  sim_time text NOT NULL,
  baseline_kw double precision NOT NULL,
  optimized_kw double precision NOT NULL,
  grid_carbon_intensity double precision NOT NULL,
  avg_zone_temp double precision NOT NULL,
  zones jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS control_actions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  zone text NOT NULL,
  cooling_setpoint_c double precision,
  heating_setpoint_c double precision,
  reason text NOT NULL,
  source text NOT NULL DEFAULT 'agent'
);

CREATE TABLE IF NOT EXISTS control_overrides (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  zone text NOT NULL,
  cooling_setpoint_c double precision,
  heating_setpoint_c double precision,
  applied boolean NOT NULL DEFAULT false
);

ALTER TABLE building_telemetry ENABLE ROW LEVEL SECURITY;
ALTER TABLE control_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE control_overrides ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_all_building_telemetry" ON building_telemetry;
CREATE POLICY "anon_all_building_telemetry" ON building_telemetry
  FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_all_control_actions" ON control_actions;
CREATE POLICY "anon_all_control_actions" ON control_actions
  FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_all_control_overrides" ON control_overrides;
CREATE POLICY "anon_all_control_overrides" ON control_overrides
  FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);

ALTER PUBLICATION supabase_realtime ADD TABLE building_telemetry;
ALTER PUBLICATION supabase_realtime ADD TABLE control_actions;

CREATE INDEX IF NOT EXISTS building_telemetry_created_at_idx ON building_telemetry (created_at DESC);
CREATE INDEX IF NOT EXISTS control_actions_created_at_idx ON control_actions (created_at DESC);
CREATE INDEX IF NOT EXISTS control_overrides_applied_idx ON control_overrides (applied) WHERE applied = false;
