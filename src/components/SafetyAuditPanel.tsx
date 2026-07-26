import { useEffect, useState } from 'react';
import { ShieldCheck, Bot, Hand, Lock } from 'lucide-react';
import { supabase, isSupabaseConfigured, type ControlActionRow } from '@/lib/supabase';

type Counts = { agent: number; safety_clamp: number; manual_override: number };

const MOCK_ACTIONS: ControlActionRow[] = [
  { id: '1', created_at: new Date().toISOString(), zone: 'ZONE A', cooling_setpoint_c: 23, heating_setpoint_c: null, reason: 'Carbon intensity falling, relaxing setpoint.', source: 'agent' },
  { id: '2', created_at: new Date().toISOString(), zone: 'ZONE B', cooling_setpoint_c: 21, heating_setpoint_c: null, reason: 'Occupancy forecast spike.', source: 'agent' },
  { id: '3', created_at: new Date().toISOString(), zone: 'ZONE C', cooling_setpoint_c: 20, heating_setpoint_c: null, reason: 'Proposed setpoint outside safe bounds — clamped.', source: 'safety_clamp' },
  { id: '4', created_at: new Date().toISOString(), zone: 'ZONE D', cooling_setpoint_c: 24, heating_setpoint_c: null, reason: 'Manual override from dashboard control panel.', source: 'manual_override' },
];

export function SafetyAuditPanel() {
  const [actions, setActions] = useState<ControlActionRow[]>(MOCK_ACTIONS);
  const [live, setLive] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    let cancelled = false;

    (async () => {
      const { data, error } = await supabase
        .from('control_actions')
        .select('id, created_at, zone, cooling_setpoint_c, heating_setpoint_c, reason, source')
        .order('created_at', { ascending: false })
        .limit(100);
      if (cancelled || error || !data) return;
      if (data.length > 0) {
        setActions(data as ControlActionRow[]);
        setLive(true);
      }
    })();

    const channel = supabase
      .channel('control_actions_audit')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'control_actions' },
        (payload) => {
          setLive(true);
          setActions((prev) => [payload.new as ControlActionRow, ...prev].slice(0, 100));
        }
      )
      .subscribe();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, []);

  const counts: Counts = actions.reduce(
    (acc, a) => {
      acc[a.source] = (acc[a.source] ?? 0) + 1;
      return acc;
    },
    { agent: 0, safety_clamp: 0, manual_override: 0 } as Counts
  );
  const total = counts.agent + counts.safety_clamp + counts.manual_override;

  return (
    <div className="h-full rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">Safety &amp; Audit</h2>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-600">
          {live ? 'live' : 'simulated'}
        </span>
      </div>
      <div className="mb-4 h-px bg-gradient-to-r from-emerald-400/30 via-slate-300/60 to-transparent" />

      <div className="mb-4 grid grid-cols-3 gap-2.5">
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-3 text-center">
          <Bot className="mx-auto mb-1.5 h-4 w-4 text-emerald-600" />
          <div className="font-mono text-lg font-semibold text-slate-900 tabular-nums">{counts.agent}</div>
          <div className="mt-0.5 text-[10px] text-slate-600">agent decisions</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-3 text-center">
          <Lock className="mx-auto mb-1.5 h-4 w-4 text-amber-600" />
          <div className="font-mono text-lg font-semibold text-slate-900 tabular-nums">{counts.safety_clamp}</div>
          <div className="mt-0.5 text-[10px] text-slate-600">safety clamped</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-3 text-center">
          <Hand className="mx-auto mb-1.5 h-4 w-4 text-cyan-600" />
          <div className="font-mono text-lg font-semibold text-slate-900 tabular-nums">{counts.manual_override}</div>
          <div className="mt-0.5 text-[10px] text-slate-600">manual overrides</div>
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-500/[0.06] px-3 py-2 text-[11px] text-emerald-700">
        <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
        <span>
          Every setpoint the agent proposes is bounds-checked before it reaches the building.
          {total > 0 && (
            <>
              {' '}
              {Math.round((counts.safety_clamp / total) * 100)}% of {total} actions this session required
              clamping.
            </>
          )}
        </span>
      </div>

      <div className="mt-4 max-h-40 space-y-1.5 overflow-y-auto">
        {actions.slice(0, 6).map((a) => (
          <div key={a.id} className="flex items-center justify-between text-[11px]">
            <span className="text-slate-500">
              <span
                className={
                  a.source === 'agent'
                    ? 'text-emerald-600'
                    : a.source === 'safety_clamp'
                      ? 'text-amber-600'
                      : 'text-cyan-600'
                }
              >
                {a.source === 'agent' ? 'agent' : a.source === 'safety_clamp' ? 'clamped' : 'manual'}
              </span>{' '}
              · {a.zone}
            </span>
            <span className="font-mono text-slate-600 tabular-nums">
              {a.cooling_setpoint_c != null ? `${a.cooling_setpoint_c}°C` : a.heating_setpoint_c != null ? `${a.heating_setpoint_c}°C` : '—'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
