import { AlertTriangle, TrendingUp, ShieldAlert } from 'lucide-react';
import type { BuildingLog } from '@/lib/supabase';

type Props = {
  logs: BuildingLog[];
};

function iconFor(message: string) {
  const lower = message.toLowerCase();
  if (lower.includes('carbon') || lower.includes('peak')) return TrendingUp;
  if (lower.includes('overridden') || lower.includes('clamp')) return ShieldAlert;
  return AlertTriangle;
}

export function AlertsPanel({ logs }: Props) {
  const recommendations = logs
    .filter((l) => l.event_type === 'recommendation')
    .slice(-8)
    .reverse();

  return (
    <div className="h-full rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">Predictive Alerts</h2>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-600">
          {recommendations.length} active
        </span>
      </div>
      <div className="mb-4 h-px bg-gradient-to-r from-amber-400/30 via-slate-300/60 to-transparent" />

      {recommendations.length === 0 ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-center text-xs text-slate-600">
          No active recommendations. The agent will surface proactive alerts here as conditions change
          (carbon peaks, comfort violations, frequent overrides).
        </div>
      ) : (
        <div className="space-y-2.5">
          {recommendations.map((log) => {
            const Icon = iconFor(log.message);
            return (
              <div
                key={log.id}
                className="flex gap-3 rounded-lg border border-amber-400/25 bg-amber-500/[0.06] px-3.5 py-3"
              >
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                <div>
                  <p className="text-xs leading-relaxed text-amber-800/90">{log.message}</p>
                  <span className="mt-1 block font-mono text-[10px] text-amber-600/70">
                    {new Date(log.created_at).toLocaleTimeString('en-US', { hour12: false })}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
