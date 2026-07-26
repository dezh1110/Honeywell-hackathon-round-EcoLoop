import { useState } from 'react';
import { Play, Loader2, TrendingDown, TrendingUp, Gauge } from 'lucide-react';
import { supabase, isSupabaseConfigured, type WhatifRequestRow } from '@/lib/supabase';

const ZONES = ['ZONE A', 'ZONE B', 'ZONE C', 'ZONE D'];

function mockPredict(zone: string, cooling: number): WhatifRequestRow {
  const kwDelta = Math.round((23 - cooling) * 0.18 * 100) / 100;
  const pmv = Math.round((cooling - 23.0) * 0.45 * 100) / 100;
  const comfort = Math.abs(pmv) <= 0.5 ? 'comfortable' : Math.abs(pmv) <= 1.0 ? 'slightly uncomfortable' : 'uncomfortable';
  const direction = kwDelta < 0 ? 'less' : kwDelta > 0 ? 'more' : 'the same';
  return {
    id: `mock-${Date.now()}`,
    created_at: new Date().toISOString(),
    zone,
    proposed_cooling_setpoint_c: cooling,
    proposed_heating_setpoint_c: null,
    predicted_kw_delta: kwDelta,
    predicted_pmv: pmv,
    comfort_status: comfort,
    explanation: `Projected over the next 120 minutes, ${zone} would settle near ${cooling.toFixed(1)}°C (${comfort}, PMV ${pmv >= 0 ? '+' : ''}${pmv.toFixed(2)}) and draw ${Math.abs(kwDelta).toFixed(2)} kW ${direction} than holding the current setpoint.`,
    status: 'done',
  };
}

export function WhatIfSimulator() {
  const [zone, setZone] = useState(ZONES[0]);
  const [cooling, setCooling] = useState(23);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<WhatifRequestRow | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setResult(null);
    setRunError(null);

    if (!isSupabaseConfigured) {
      setTimeout(() => {
        setResult(mockPredict(zone, cooling));
        setRunning(false);
      }, 700);
      return;
    }

    const { data, error } = await supabase
      .from('whatif_requests')
      .insert({ zone, proposed_cooling_setpoint_c: cooling, status: 'pending' })
      .select()
      .single();

    if (error || !data) {
      setRunning(false);
      setRunError(`Couldn't submit the request${error ? `: ${error.message}` : ''}. Check that Supabase is reachable.`);
      return;
    }

    const requestId = data.id as string;
    const poll = setInterval(async () => {
      const { data: row } = await supabase.from('whatif_requests').select('*').eq('id', requestId).single();
      if (row && row.status !== 'pending') {
        clearInterval(poll);
        setResult(row as WhatifRequestRow);
        setRunning(false);
      }
    }, 1000);
    setTimeout(() => {
      clearInterval(poll);
      setRunning((wasRunning) => {
        if (wasRunning) {
          setRunError('The backend is taking longer than expected to respond. Check that the backend agent container is running.');
        }
        return false;
      });
    }, 60000);
  };

  const savingEnergy = (result?.predicted_kw_delta ?? 0) <= 0;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
        <div className="mb-1 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">Simulation Parameters</h2>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-600">what-if</span>
        </div>
        <div className="mb-5 h-px bg-gradient-to-r from-emerald-400/30 via-slate-300/60 to-transparent" />

        <label className="mb-1.5 block text-xs font-medium text-slate-500">Select Zone</label>
        <select
          value={zone}
          onChange={(e) => setZone(e.target.value)}
          className="mb-5 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-emerald-400/40"
        >
          {ZONES.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>

        <div className="mb-2 flex items-center justify-between">
          <label className="text-xs font-medium text-slate-500">Proposed Cooling Setpoint</label>
          <span className="font-mono text-sm font-semibold text-slate-900 tabular-nums">{cooling.toFixed(1)}°C</span>
        </div>
        <input
          type="range"
          min={18}
          max={28}
          step={0.5}
          value={cooling}
          onChange={(e) => setCooling(parseFloat(e.target.value))}
          className="mb-6 h-2 w-full"
        />

        <button
          onClick={run}
          disabled={running}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-700 disabled:opacity-60"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? 'Projecting…' : 'Run Simulation'}
        </button>
        <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
          Uses a fast physics-based projection (not a full re-simulation) to estimate impact before you commit
          the change via Manual Override.
        </p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
        <div className="mb-1 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">Predicted Impact</h2>
        </div>
        <div className="mb-5 h-px bg-gradient-to-r from-cyan-400/30 via-slate-300/60 to-transparent" />

        {!result && !running && !runError && (
          <div className="flex h-48 flex-col items-center justify-center text-center text-xs text-slate-600">
            <Gauge className="mb-2 h-8 w-8 text-slate-700" />
            Run a simulation to see the projected effect on energy and comfort.
          </div>
        )}
        {runError && !running && (
          <div className="flex h-48 flex-col items-center justify-center gap-2 text-center text-xs text-rose-600">
            <Gauge className="h-8 w-8 text-rose-400" />
            {runError}
          </div>
        )}
        {running && (
          <div className="flex h-48 flex-col items-center justify-center gap-2">
            <Loader2 className="h-6 w-6 animate-spin text-emerald-600" />
            <span className="text-[11px] text-slate-500">Waiting for the backend agent to respond…</span>
          </div>
        )}
        {result && !running && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-600">
                  {savingEnergy ? (
                    <TrendingDown className="h-3 w-3 text-emerald-600" />
                  ) : (
                    <TrendingUp className="h-3 w-3 text-rose-600" />
                  )}
                  Power delta
                </div>
                <div
                  className={`font-mono text-xl font-semibold tabular-nums ${
                    savingEnergy ? 'text-emerald-600' : 'text-rose-600'
                  }`}
                >
                  {(result.predicted_kw_delta ?? 0) >= 0 ? '+' : ''}
                  {result.predicted_kw_delta?.toFixed(2)} kW
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-600">Predicted comfort</div>
                <div className="font-mono text-xl font-semibold capitalize text-slate-900">
                  {result.comfort_status}
                </div>
                <div className="mt-0.5 text-[10px] text-slate-600">
                  PMV {(result.predicted_pmv ?? 0) >= 0 ? '+' : ''}
                  {result.predicted_pmv?.toFixed(2)}
                </div>
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3 text-xs leading-relaxed text-slate-500">
              {result.explanation}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
