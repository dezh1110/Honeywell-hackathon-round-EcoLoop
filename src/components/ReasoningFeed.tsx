import { useEffect, useRef, useState } from 'react';
import { Terminal, Cpu, ChevronDown, Wrench } from 'lucide-react';
import type { BuildingLog } from '@/lib/supabase';

type Props = {
  logs: BuildingLog[];
  source: 'connecting' | 'live' | 'mock';
};

const SEVERITY_COLOR: Record<BuildingLog['severity'], string> = {
  info: 'text-emerald-600',
  warning: 'text-amber-600',
  critical: 'text-rose-600',
};

const SEVERITY_TAG: Record<BuildingLog['severity'], string> = {
  info: 'INFO',
  warning: 'WARN',
  critical: 'CRIT',
};

const SOURCE_LABEL: Record<Props['source'], string> = {
  connecting: 'connecting',
  live: 'live stream',
  mock: 'simulated',
};

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString('en-US', { hour12: false });
  } catch {
    return '--:--:--';
  }
}

function TraceRow({ log }: { log: BuildingLog }) {
  const [open, setOpen] = useState(false);
  const hasTrace = log.reasoning_trace && log.reasoning_trace.length > 0;

  return (
    <div className="row-in py-0.5">
      <div className="flex items-start gap-2">
        <span className="shrink-0 text-slate-600">[{fmtTime(log.created_at)}]</span>
        <span className={`shrink-0 ${SEVERITY_COLOR[log.severity]}`}>{SEVERITY_TAG[log.severity]}</span>
        <span className="flex-1 text-slate-700">{log.message}</span>
        {hasTrace && (
          <button
            onClick={() => setOpen((v) => !v)}
            className="inline-flex shrink-0 items-center gap-1 rounded border border-slate-300 px-1.5 py-0.5 text-[10px] text-slate-500 hover:border-emerald-400/40 hover:text-emerald-700"
            aria-label="Show agent tool calls"
          >
            <Wrench className="h-2.5 w-2.5" />
            {log.reasoning_trace.length}
            <ChevronDown className={`h-2.5 w-2.5 transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>
        )}
      </div>
      {hasTrace && open && (
        <div className="ml-6 mt-1 space-y-1.5 border-l border-slate-200 pl-3">
          {log.reasoning_trace.map((step, i) => (
            <div key={i} className="text-[11px]">
              <div className="flex items-center gap-1.5 text-cyan-600">
                <span className="text-slate-600">{i + 1}.</span>
                <span className="font-semibold">{step.tool}</span>
                {Object.keys(step.arguments || {}).length > 0 && (
                  <span className="text-slate-600">
                    ({Object.entries(step.arguments)
                      .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                      .join(', ')})
                  </span>
                )}
              </div>
              <div className="ml-4 truncate text-slate-600">
                → {typeof step.result === 'string' ? step.result : JSON.stringify(step.result)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ReasoningFeed({ logs, source }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const visibleLogs = logs.filter((l) => l.event_type !== 'recommendation');

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-glow">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-emerald-600" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">Autonomous Agent Reasoning</h2>
        </div>
        <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-slate-600">
          <Cpu className="h-3 w-3" />
          {SOURCE_LABEL[source]}
        </span>
      </div>
      <div className="scanline relative flex-1">
        <div
          ref={scrollRef}
          className="scroll-thin h-full overflow-y-auto px-4 py-3 font-mono text-xs leading-relaxed"
        >
          {visibleLogs.length === 0 && (
            <div className="text-slate-600">awaiting agent output…</div>
          )}
          {visibleLogs.map((log) => (
            <TraceRow key={log.id} log={log} />
          ))}
        </div>
      </div>
    </div>
  );
}
