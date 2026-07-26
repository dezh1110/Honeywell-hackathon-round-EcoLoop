/*
# Create building_logs table (single-tenant, no auth)

1. New Tables
- `building_logs`
  - `id` (uuid, primary key)
  - `created_at` (timestamptz, default now) — when the log event occurred
  - `event_type` (text) — category of decision/event, e.g. 'grid_carbon', 'cooling', 'heating', 'occupancy', 'system'
  - `message` (text) — human-readable AI reasoning line shown in the console feed
  - `severity` (text, default 'info') — 'info' | 'warning' | 'critical'
  - `zone` (text, nullable) — affected zone label, e.g. 'Zone A'
  - `metric_value` (double precision, nullable) — optional numeric payload (setpoint, kWh, gCO2/kWh, etc.)

2. Security
- Enable RLS on `building_logs`.
- Allow anon + authenticated CRUD because the dashboard is intentionally public/shared (no sign-in screen).
- Realtime publication enabled so the frontend can subscribe to INSERT events.
*/

CREATE TABLE IF NOT EXISTS building_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  event_type text NOT NULL DEFAULT 'system',
  message text NOT NULL,
  severity text NOT NULL DEFAULT 'info',
  zone text,
  metric_value double precision
);

ALTER TABLE building_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_select_building_logs" ON building_logs;
CREATE POLICY "anon_select_building_logs" ON building_logs FOR SELECT
  TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_building_logs" ON building_logs;
CREATE POLICY "anon_insert_building_logs" ON building_logs FOR INSERT
  TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_building_logs" ON building_logs;
CREATE POLICY "anon_update_building_logs" ON building_logs FOR UPDATE
  TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_building_logs" ON building_logs;
CREATE POLICY "anon_delete_building_logs" ON building_logs FOR DELETE
  TO anon, authenticated USING (true);

-- Add table to the realtime publication so INSERT events are broadcast.
ALTER PUBLICATION supabase_realtime ADD TABLE building_logs;

-- Index for the common "recent logs" query.
CREATE INDEX IF NOT EXISTS building_logs_created_at_idx ON building_logs (created_at DESC);
