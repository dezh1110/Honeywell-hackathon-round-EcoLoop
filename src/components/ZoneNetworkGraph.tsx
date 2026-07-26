import { useMemo } from 'react';
import { Share2 } from 'lucide-react';
import type { BuildingTelemetryRow } from '@/lib/supabase';

type Props = {
  telemetryRows: BuildingTelemetryRow[];
};

// Matches the physical adjacency in models/small_office.idf: a 2x2 grid
// where A-B, A-C, B-D, C-D each share a wall (A-D and B-C are diagonal, no
// shared wall). This is a real thermal-coupling topology, not a stand-in —
// a setpoint change in one zone measurably affects its neighbors' load via
// the shared partition walls.
const ZONES = ['ZONE A', 'ZONE B', 'ZONE C', 'ZONE D'];
const POSITIONS: Record<string, { x: number; y: number }> = {
  'ZONE A': { x: 90, y: 70 },
  'ZONE B': { x: 260, y: 70 },
  'ZONE C': { x: 90, y: 220 },
  'ZONE D': { x: 260, y: 220 },
};
const EDGES: [string, string][] = [
  ['ZONE A', 'ZONE B'],
  ['ZONE A', 'ZONE C'],
  ['ZONE B', 'ZONE D'],
  ['ZONE C', 'ZONE D'],
];

export function ZoneNetworkGraph({ telemetryRows }: Props) {
  const latest = telemetryRows[telemetryRows.length - 1];

  const zoneStats = useMemo(() => {
    const stats: Record<string, { temp: number; deviation: number }> = {};
    for (const name of ZONES) {
      const reading = latest?.zones.find((z) => z.zone === name);
      const temp = reading?.air_temp_c ?? 23;
      stats[name] = { temp, deviation: Math.abs(temp - 23) };
    }
    return stats;
  }, [latest]);

  const mostInfluential = useMemo(() => {
    return ZONES.reduce((best, z) => (zoneStats[z].deviation > zoneStats[best].deviation ? z : best), ZONES[0]);
  }, [zoneStats]);

  const maxDeviation = Math.max(0.01, ...ZONES.map((z) => zoneStats[z].deviation));

  const colorFor = (temp: number) => {
    if (temp >= 20 && temp <= 24) return { fill: '#10b981', ring: 'rgba(52,211,153,0.4)' };
    if (temp < 20) return { fill: '#22d3ee', ring: 'rgba(34,211,238,0.4)' };
    return { fill: '#f87171', ring: 'rgba(248,113,113,0.4)' };
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Share2 className="h-4 w-4 text-emerald-600" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">Zone Thermal Coupling</h2>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-600">
          shared-wall adjacency
        </span>
      </div>
      <div className="mb-4 h-px bg-gradient-to-r from-emerald-400/30 via-slate-300/60 to-transparent" />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <svg viewBox="0 0 350 290" className="h-64 w-full">
            {EDGES.map(([a, b]) => {
              const pa = POSITIONS[a];
              const pb = POSITIONS[b];
              const strength = (zoneStats[a].deviation + zoneStats[b].deviation) / 2;
              const width = 1.5 + (strength / maxDeviation) * 3;
              return (
                <line
                  key={`${a}-${b}`}
                  x1={pa.x}
                  y1={pa.y}
                  x2={pb.x}
                  y2={pb.y}
                  stroke="#475569"
                  strokeWidth={width}
                  strokeOpacity={0.6}
                />
              );
            })}
            {ZONES.map((z) => {
              const pos = POSITIONS[z];
              const { temp } = zoneStats[z];
              const colors = colorFor(temp);
              const isTop = z === mostInfluential;
              return (
                <g key={z}>
                  {isTop && (
                    <circle cx={pos.x} cy={pos.y} r={34} fill="none" stroke={colors.ring} strokeWidth={2} />
                  )}
                  <circle cx={pos.x} cy={pos.y} r={28} fill={colors.fill} fillOpacity={0.18} stroke={colors.fill} strokeWidth={1.5} />
                  <text x={pos.x} y={pos.y - 3} textAnchor="middle" className="fill-slate-900 text-[11px] font-semibold">
                    {z.replace('ZONE ', '')}
                  </text>
                  <text x={pos.x} y={pos.y + 11} textAnchor="middle" className="fill-slate-600 text-[10px] font-mono">
                    {temp.toFixed(1)}°C
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        <div className="space-y-2.5">
          <div className="rounded-lg border border-amber-400/25 bg-amber-500/[0.06] px-3.5 py-3">
            <div className="text-[10px] uppercase tracking-wider text-amber-600/80">Highest influence</div>
            <div className="mt-1 text-sm font-semibold text-amber-800">{mostInfluential}</div>
            <div className="mt-1 text-[11px] text-amber-700/70">
              Largest deviation from the 23°C comfort target — changes here propagate to adjacent zones through
              shared walls.
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3 text-[11px] text-slate-500">
            Edge thickness = combined comfort deviation of the two connected zones. A(0,0)-B(1,0), A-C, B-D, and
            C-D each share a physical wall in the 4-zone model; A-D and B-C are diagonal with no direct coupling.
          </div>
        </div>
      </div>
    </div>
  );
}
