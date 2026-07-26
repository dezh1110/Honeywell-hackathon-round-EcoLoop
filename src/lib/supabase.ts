import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: { persistSession: false },
  realtime: { params: { eventsPerSecond: 10 } },
});

export type ReasoningStep = {
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
};

export type BuildingLog = {
  id: string;
  created_at: string;
  event_type: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
  zone: string | null;
  metric_value: number | null;
  reasoning_trace: ReasoningStep[];
};

export type ZoneReadingRow = {
  zone: string;
  air_temp_c: number;
  pmv: number | null;
  occupant_count: number | null;
};

export type BuildingTelemetryRow = {
  id: string;
  created_at: string;
  sim_time: string;
  baseline_kw: number;
  optimized_kw: number;
  grid_carbon_intensity: number;
  indoor_air_quality_ppm: number;
  avg_zone_temp: number;
  zones: ZoneReadingRow[];
};

export type ControlActionRow = {
  id: string;
  created_at: string;
  zone: string;
  cooling_setpoint_c: number | null;
  heating_setpoint_c: number | null;
  reason: string;
  source: 'agent' | 'safety_clamp' | 'manual_override';
};

export type NlpQueryRow = {
  id: string;
  created_at: string;
  question: string;
  answer: string | null;
  reasoning_trace: ReasoningStep[];
  status: 'pending' | 'answered' | 'error';
};

export type WhatifRequestRow = {
  id: string;
  created_at: string;
  zone: string;
  proposed_cooling_setpoint_c: number | null;
  proposed_heating_setpoint_c: number | null;
  predicted_kw_delta: number | null;
  predicted_pmv: number | null;
  comfort_status: string | null;
  explanation: string | null;
  status: 'pending' | 'done' | 'error';
};
