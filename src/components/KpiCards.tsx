import { Zap, Leaf, Thermometer, Gauge, TrendingDown, AlertTriangle } from 'lucide-react';
import type { Kpis } from '@/hooks/useLiveData';

type Props = {
  kpis: Kpis;
};

type Accent = {
  ring: string;
  glow: string;
  iconBg: string;
  iconColor: string;
  bar: string;
};

const ACCENTS: Record<string, Accent> = {
  emerald: {
    ring: 'hover:border-emerald-400/40',
    glow: 'from-emerald-500/15',
    iconBg: 'bg-emerald-500/10',
    iconColor: 'text-emerald-600',
    bar: 'bg-emerald-400',
  },
  teal: {
    ring: 'hover:border-teal-400/40',
    glow: 'from-teal-500/15',
    iconBg: 'bg-teal-500/10',
    iconColor: 'text-teal-600',
    bar: 'bg-teal-400',
  },
  amber: {
    ring: 'hover:border-amber-400/40',
    glow: 'from-amber-500/15',
    iconBg: 'bg-amber-500/10',
    iconColor: 'text-amber-600',
    bar: 'bg-amber-400',
  },
  rose: {
    ring: 'hover:border-rose-400/40',
    glow: 'from-rose-500/15',
    iconBg: 'bg-rose-500/10',
    iconColor: 'text-rose-600',
    bar: 'bg-rose-400',
  },
};

function Card({
  icon,
  label,
  children,
  accentKey,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
  accentKey: keyof typeof ACCENTS;
}) {
  const a = ACCENTS[accentKey];
  return (
    <div
      className={`group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 transition-all duration-300 ${a.ring} hover:shadow-glow`}
    >
      <div
        className={`pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-gradient-to-br ${a.glow} to-transparent opacity-60 blur-2xl transition-opacity duration-300 group-hover:opacity-100`}
      />
      <div className="relative flex items-center justify-between">
        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-slate-500">
          {label}
        </span>
        <span className={`grid h-9 w-9 place-items-center rounded-lg ${a.iconBg} ring-1 ring-slate-900/5`}>
          {icon}
        </span>
      </div>
      <div className="relative mt-4">{children}</div>
    </div>
  );
}

export function KpiCards({ kpis }: Props) {
  const tempStatus = kpis.zoneTemp >= 20 && kpis.zoneTemp <= 24 ? 'Optimal' : 'Warning';
  const tempOk = tempStatus === 'Optimal';
  const peakCarbon = kpis.gridCarbon >= 400;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 xl:gap-5">
      <Card
        label="Total Energy Saved"
        accentKey="emerald"
        icon={<Zap className="h-5 w-5 text-emerald-600" />}
      >
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-3xl font-semibold leading-none tracking-tight text-slate-900 tabular-nums">
            {kpis.energySavedKwh.toFixed(1)}
          </span>
          <span className="text-sm text-slate-500">kWh</span>
        </div>
        <div className="mt-3 inline-flex items-center gap-1.5 text-xs text-emerald-600">
          <TrendingDown className="h-3.5 w-3.5" />
          <span className="font-mono tabular-nums">{kpis.energySavedPct}%</span>
          <span className="text-slate-600">reduction vs baseline</span>
        </div>
      </Card>

      <Card
        label="Carbon Avoided"
        accentKey="teal"
        icon={<Leaf className="h-5 w-5 text-teal-600" />}
      >
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-3xl font-semibold leading-none tracking-tight text-slate-900 tabular-nums">
            {kpis.carbonAvoidedKg.toFixed(1)}
          </span>
          <span className="text-sm text-slate-500">kg CO₂</span>
        </div>
        <div className="mt-3 text-xs tracking-wide text-slate-600">Offset this session</div>
      </Card>

      <Card
        label="Zone Temperature"
        accentKey="amber"
        icon={<Thermometer className="h-5 w-5 text-amber-600" />}
      >
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-3xl font-semibold leading-none tracking-tight text-slate-900 tabular-nums">
            {kpis.zoneTemp.toFixed(1)}
          </span>
          <span className="text-sm text-slate-500">°C avg</span>
        </div>
        <span
          className={`mt-3 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${
            tempOk
              ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-700'
              : 'border-amber-400/30 bg-amber-500/10 text-amber-700'
          }`}
        >
          {!tempOk && <AlertTriangle className="h-3 w-3" />}
          {tempStatus}
        </span>
      </Card>

      <Card
        label="Grid Carbon Intensity"
        accentKey="rose"
        icon={<Gauge className="h-5 w-5 text-rose-600" />}
      >
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-3xl font-semibold leading-none tracking-tight text-slate-900 tabular-nums">
            {kpis.gridCarbon}
          </span>
          <span className="text-sm text-slate-500">gCO₂/kWh</span>
        </div>
        <span
          className={`mt-3 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${
            peakCarbon
              ? 'border-rose-400/30 bg-rose-500/10 text-rose-700'
              : 'border-slate-300 bg-slate-100 text-slate-700'
          }`}
        >
          {peakCarbon ? 'Peak carbon hours' : 'Normal range'}
        </span>
      </Card>
    </div>
  );
}
