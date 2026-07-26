import { useEffect, useMemo, useState } from 'react';
import { supabase, isSupabaseConfigured } from '@/lib/supabase';

type HourBucket = { kw: number; count: number; live: boolean };

const BANDS = [
  { max: 1.0, label: '<1 kW', className: 'bg-emerald-100 text-emerald-800' },
  { max: 1.6, label: '1-1.6 kW', className: 'bg-yellow-100 text-yellow-800' },
  { max: 2.2, label: '1.6-2.2 kW', className: 'bg-orange-100 text-orange-800' },
  { max: 2.8, label: '2.2-2.8 kW', className: 'bg-rose-100 text-rose-800' },
  { max: Infinity, label: '>2.8 kW', className: 'bg-rose-200 text-rose-900' },
];

function bandFor(kw: number) {
  return BANDS.find((b) => kw < b.max) ?? BANDS[BANDS.length - 1];
}

// Synthetic daily curve used to fill in hours this session hasn't seen real
// data for yet, so the grid reads like a full day rather than one live
// cluster of hours. Cells that DO have real telemetry are marked "live" and
// take priority — see the small legend note under the grid.
function syntheticCurveKw(hour: number): number {
  const occupied = hour >= 9 && hour < 19;
  const base = occupied ? 1.4 + 0.9 * Math.sin(((hour - 9) / 10) * Math.PI) : 0.5;
  return Math.round(base * 100) / 100;
}

export function EnergyHeatmap() {
  const [buckets, setBuckets] = useState<Record<number, HourBucket>>(() => {
    const init: Record<number, HourBucket> = {};
    for (let h = 0; h < 24; h++) init[h] = { kw: syntheticCurveKw(h), count: 0, live: false };
    return init;
  });

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    let cancelled = false;

    (async () => {
      const { data } = await supabase
        .from('building_telemetry')
        .select('created_at, optimized_kw')
        .order('created_at', { ascending: false })
        .limit(500);
      if (cancelled || !data || data.length === 0) return;

      const sums: Record<number, { total: number; count: number }> = {};
      for (const row of data as { created_at: string; optimized_kw: number }[]) {
        const hour = new Date(row.created_at).getHours();
        if (!sums[hour]) sums[hour] = { total: 0, count: 0 };
        sums[hour].total += row.optimized_kw;
        sums[hour].count += 1;
      }

      setBuckets((prev) => {
        const next = { ...prev };
        for (const [hourStr, { total, count }] of Object.entries(sums)) {
          const hour = Number(hourStr);
          next[hour] = { kw: Math.round((total / count) * 100) / 100, count, live: true };
        }
        return next;
      });
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const hours = useMemo(() => Array.from({ length: 24 }, (_, i) => i), []);
  const hasLiveData = Object.values(buckets).some((b) => b.live);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-slate-900">Energy Heatmap by Hour</h2>
          <p className="mt-0.5 text-xs text-slate-600">Average AI-optimized power draw per hour of day</p>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
          {BANDS.map((b) => (
            <span key={b.label} className="inline-flex items-center gap-1.5">
              <span className={`h-3 w-3 rounded-full ${b.className}`} />
              {b.label}
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-6 gap-3 sm:grid-cols-8 lg:grid-cols-12">
        {hours.map((h) => {
          const bucket = buckets[h];
          const band = bandFor(bucket.kw);
          return (
            <div
              key={h}
              title={`${h.toString().padStart(2, '0')}:00 — ${bucket.kw.toFixed(2)} kW avg${bucket.live ? ` (${bucket.count} samples)` : ' (estimated)'}`}
              className={`rounded-xl px-3 py-4 text-center ${band.className} ${bucket.live ? '' : 'opacity-70'}`}
            >
              <div className="text-sm font-semibold tabular-nums">{h.toString().padStart(2, '0')}</div>
              <div className="mt-1 font-mono text-lg font-bold tabular-nums">{bucket.kw.toFixed(1)}</div>
              <div className="mt-1 text-xs tabular-nums opacity-70">{bucket.live ? bucket.count : 'est.'}</div>
            </div>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-slate-500">
        Hover over cells for detailed information. Numbers show average power draw (kW) and sample count.
        {!hasLiveData && ' Currently showing an estimated daily curve — connect Supabase and let the agent run to populate real per-hour data.'}
      </p>
    </div>
  );
}
