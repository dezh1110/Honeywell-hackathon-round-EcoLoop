/*
# Feature pack: NLP insights, what-if simulator, explainable reasoning, alerts

1. New Tables
- `nlp_queries` — natural-language questions asked from the dashboard's
  "NLP Insights" panel. The frontend inserts a row with `status='pending'`;
  the backend polls, answers using a read-only ReAct pass (same MCP tools,
  `set_zone_setpoint` excluded), and writes the answer + tool trace back.
- `whatif_requests` — "what if I set Zone X to Y°C" queries from the
  What-If Simulator. Backend polls, runs a fast physics-based estimate
  (not a full re-simulation), writes back predicted kW delta + comfort
  impact.

2. Table changes
- `building_logs` gains `reasoning_trace` (jsonb) so the dashboard can show
  the actual MCP tool calls behind a decision, not just the summary
  sentence, and `event_type` now also allows `'recommendation'` for
  proactive alerts (distinct from routine decision logs).

3. Security
- Same pattern as prior migrations: anon+authenticated full access
  (single-tenant demo). Tighten before any real multi-user deployment.
*/

CREATE TABLE IF NOT EXISTS nlp_queries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  question text NOT NULL,
  answer text,
  reasoning_trace jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'answered', 'error'))
);

CREATE TABLE IF NOT EXISTS whatif_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  zone text NOT NULL,
  proposed_cooling_setpoint_c double precision,
  proposed_heating_setpoint_c double precision,
  predicted_kw_delta double precision,
  predicted_pmv double precision,
  comfort_status text,
  explanation text,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'error'))
);

ALTER TABLE building_logs ADD COLUMN IF NOT EXISTS reasoning_trace jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE building_logs DROP CONSTRAINT IF EXISTS building_logs_event_type_check;
ALTER TABLE building_logs ADD CONSTRAINT building_logs_event_type_check
  CHECK (event_type IN ('grid_carbon', 'cooling', 'heating', 'occupancy', 'system', 'error', 'recommendation'));

ALTER TABLE nlp_queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatif_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_all_nlp_queries" ON nlp_queries;
CREATE POLICY "anon_all_nlp_queries" ON nlp_queries
  FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_all_whatif_requests" ON whatif_requests;
CREATE POLICY "anon_all_whatif_requests" ON whatif_requests
  FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);

ALTER PUBLICATION supabase_realtime ADD TABLE nlp_queries;
ALTER PUBLICATION supabase_realtime ADD TABLE whatif_requests;

CREATE INDEX IF NOT EXISTS nlp_queries_status_idx ON nlp_queries (status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS whatif_requests_status_idx ON whatif_requests (status) WHERE status = 'pending';
