import { useEffect, useState } from 'react';
import { Activity, Radio } from 'lucide-react';

type Props = {
  source: 'connecting' | 'live' | 'mock';
};

const SOURCE_LABEL: Record<Props['source'], string> = {
  connecting: 'Establishing link…',
  live: 'Live (Supabase)',
  mock: 'Simulated feed',
};

const SOURCE_DOT: Record<Props['source'], string> = {
  connecting: 'bg-slate-500',
  live: 'bg-emerald-400',
  mock: 'bg-amber-400',
};

export function Header({ source }: Props) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
      <div className="flex items-center gap-4">
        <div className="relative grid h-12 w-12 place-items-center rounded-xl bg-emerald-500/10 ring-1 ring-emerald-400/30">
          <div className="absolute inset-0 rounded-xl bg-emerald-400/5 blur-md" />
          <Activity className="relative h-6 w-6 text-emerald-600" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-[-0.02em] text-slate-900 md:text-2xl">
            EcoLoop Autonomous BMS
          </h1>
          <p className="mt-0.5 text-xs tracking-wide text-slate-500">
            Building Management System · Command Center
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-500/5 px-3 py-1.5 text-xs font-medium text-emerald-700">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
          </span>
          Autonomous Agent: ONLINE
        </span>

        <span className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-slate-100 px-3 py-1.5 text-xs text-slate-700">
          <Radio className="h-3.5 w-3.5 text-cyan-600" />
          <span className={`h-1.5 w-1.5 rounded-full ${SOURCE_DOT[source]}`} />
          {SOURCE_LABEL[source]}
        </span>

        <div className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-right shadow-glow">
          <div className="font-mono text-lg leading-none text-slate-900 tabular-nums">
            {now.toLocaleTimeString('en-US', { hour12: false })}
          </div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-600">
            {now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
          </div>
        </div>
      </div>
    </header>
  );
}
