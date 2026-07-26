import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TelemetryPoint } from '@/hooks/useLiveData';

type Props = {
  data: TelemetryPoint[];
};

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs shadow-glow backdrop-blur">
      <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.15em] text-slate-600">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full ring-1 ring-slate-900/10"
            style={{ background: p.color }}
          />
          <span className="text-slate-500">{p.name}:</span>
          <span className="font-mono text-slate-900 tabular-nums">{p.value} kWh</span>
        </div>
      ))}
    </div>
  );
}

export function TelemetryChart({ data }: Props) {
  return (
    <div className="h-full rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">Power Consumption Telemetry</h2>
          <p className="mt-0.5 text-xs tracking-wide text-slate-600">Baseline vs AI-Optimized · last 24 samples</p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="inline-flex items-center gap-1.5 text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-rose-400 ring-1 ring-rose-400/30" /> Baseline
          </span>
          <span className="inline-flex items-center gap-1.5 text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 ring-1 ring-emerald-400/30" /> AI-Optimized
          </span>
        </div>
      </div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
            <defs>
              <linearGradient id="baselineGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#fb7185" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#fb7185" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="optGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#34d399" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="t"
              tick={{ fill: '#64748b', fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              minTickGap={32}
            />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={48}
              unit=""
            />
            <Tooltip content={<ChartTooltip />} />
            <Legend wrapperStyle={{ display: 'none' }} />
            <Area
              type="monotone"
              dataKey="baseline"
              name="Baseline Power"
              stroke="#e11d48"
              strokeWidth={2}
              fill="url(#baselineGrad)"
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="optimized"
              name="AI-Optimized Power"
              stroke="#059669"
              strokeWidth={2}
              fill="url(#optGrad)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
