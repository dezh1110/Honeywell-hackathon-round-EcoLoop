import { useCallback, useEffect, useState } from 'react';
import { LayoutDashboard, Bot, LineChart, FlaskConical, Activity, Radio } from 'lucide-react';
import { KpiCards } from '@/components/KpiCards';
import { TelemetryChart } from '@/components/TelemetryChart';
import { ReasoningFeed } from '@/components/ReasoningFeed';
import { ControlPanel } from '@/components/ControlPanel';
import { AlertsPanel } from '@/components/AlertsPanel';
import { SafetyAuditPanel } from '@/components/SafetyAuditPanel';
import { NlpInsights } from '@/components/NlpInsights';
import { EnergyHeatmap } from '@/components/EnergyHeatmap';
import { ZoneNetworkGraph } from '@/components/ZoneNetworkGraph';
import { CostSavings } from '@/components/CostSavings';
import { WhatIfSimulator } from '@/components/WhatIfSimulator';
import { useLiveData } from '@/hooks/useLiveData';
import { supabase, isSupabaseConfigured } from '@/lib/supabase';

const ZONES = ['ZONE A', 'ZONE B', 'ZONE C', 'ZONE D'];

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'agent', label: 'Agent & Alerts', icon: Bot },
  { id: 'analytics', label: 'Analytics', icon: LineChart },
  { id: 'whatif', label: 'What-If Simulator', icon: FlaskConical },
] as const;

type TabId = (typeof NAV_ITEMS)[number]['id'];

const TAB_META: Record<TabId, { title: string; subtitle: string }> = {
  overview: { title: 'Building Overview', subtitle: 'Live telemetry, control panel, and zone status' },
  agent: { title: 'Agent & Alerts', subtitle: 'Reasoning trace, predictive alerts, NLP insights, and audit trail' },
  analytics: { title: 'Analytics', subtitle: 'Energy patterns, zone coupling, and cost impact' },
  whatif: { title: 'What-If Simulator', subtitle: 'Preview a setpoint change before committing it' },
};

function Sidebar({ tab, onSelect, source }: { tab: TabId; onSelect: (t: TabId) => void; source: 'connecting' | 'live' | 'mock' }) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white px-4 py-6">
      <div className="mb-8 flex items-center gap-3 px-2">
        <div
          className="relative grid h-10 w-10 place-items-center rounded-xl ring-1"
          style={{ background: 'rgba(16,185,129,0.10)', borderColor: 'rgba(52,211,153,0.3)' }}
        >
          <Activity className="h-5 w-5 text-emerald-600" />
        </div>
        <div>
          <div className="text-sm font-semibold tracking-tight text-slate-900">EcoLoop</div>
          <div className="text-[11px] text-slate-600">Autonomous BMS</div>
        </div>
      </div>

      <div className="mb-2 px-2 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-600">Monitor</div>
      <nav className="space-y-1">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const active = tab === id;
          return (
            <button
              key={id}
              onClick={() => onSelect(id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                active
                  ? 'bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-400/25'
                  : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3 pt-6">
        <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/[0.06] px-3.5 py-3">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="text-xs font-medium text-emerald-700">Agent online</span>
          </div>
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-600">
            <Radio className="h-3 w-3 text-cyan-600" />
            {source === 'live' ? 'Live (Supabase)' : source === 'mock' ? 'Simulated feed' : 'Connecting…'}
          </div>
        </div>
        <div className="px-2 text-[10px] text-slate-600">EcoLoop Autonomous BMS</div>
      </div>
    </aside>
  );
}

function TopBar({ title, subtitle }: { title: string; subtitle: string }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="mb-7 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900 md:text-2xl">{title}</h1>
        <p className="mt-0.5 text-xs tracking-wide text-slate-500">{subtitle}</p>
      </div>
      <div className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-right shadow-glow">
        <div className="font-mono text-lg leading-none text-slate-900 tabular-nums">
          {now.toLocaleTimeString('en-US', { hour12: false })}
        </div>
        <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-600">
          {now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
        </div>
      </div>
    </div>
  );
}

function App() {
  const { telemetry, telemetryRows, logs, source, kpis } = useLiveData();
  const [tab, setTab] = useState<TabId>('overview');
  const [autonomous, setAutonomous] = useState(true);
  const [cooling, setCooling] = useState(23);
  const [heating, setHeating] = useState(21);
  const [zone, setZone] = useState(ZONES[0]);

  const handleToggle = useCallback(() => setAutonomous((v) => !v), []);

  const handleApplyOverride = useCallback(
    async (z: string, coolingSetpoint: number, heatingSetpoint: number) => {
      if (!isSupabaseConfigured) {
        console.warn('Supabase not configured — override not sent to the backend agent.');
        return;
      }
      const { error } = await supabase.from('control_overrides').insert({
        zone: z,
        cooling_setpoint_c: coolingSetpoint,
        heating_setpoint_c: heatingSetpoint,
        applied: false,
      });
      if (error) throw error;
    },
    []
  );

  const meta = TAB_META[tab];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="flex min-h-screen">
        <Sidebar tab={tab} onSelect={setTab} source={source} />

        <div className="flex-1 px-4 py-6 md:px-8 md:py-10">
          <div className="mx-auto max-w-6xl">
            <TopBar title={meta.title} subtitle={meta.subtitle} />

            <main className="space-y-8">
              {tab === 'overview' && (
                <>
                  <KpiCards kpis={kpis} />

                  <TelemetryChart data={telemetry} />

                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:gap-7">
                    <div className="lg:col-span-2">
                      <ControlPanel
                        autonomous={autonomous}
                        onToggle={handleToggle}
                        cooling={cooling}
                        heating={heating}
                        onCooling={setCooling}
                        onHeating={setHeating}
                        zones={ZONES}
                        selectedZone={zone}
                        onZoneChange={setZone}
                        onApplyOverride={handleApplyOverride}
                      />
                    </div>
                    <div className="lg:col-span-1">
                      <ZoneSummary telemetry={telemetry} />
                    </div>
                  </div>
                </>
              )}

              {tab === 'agent' && (
                <>
                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-7">
                    <ReasoningFeed logs={logs} source={source} />
                    <AlertsPanel logs={logs} />
                  </div>
                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-7">
                    <NlpInsights />
                    <SafetyAuditPanel />
                  </div>
                </>
              )}

              {tab === 'analytics' && (
                <>
                  <EnergyHeatmap />
                  <ZoneNetworkGraph telemetryRows={telemetryRows} />
                  <CostSavings energySavedKwh={kpis.energySavedKwh} energySavedPct={kpis.energySavedPct} />
                </>
              )}

              {tab === 'whatif' && <WhatIfSimulator />}
            </main>

            <footer className="mt-10 flex flex-col items-center gap-1 border-t border-slate-200 pt-5 text-center text-[11px] text-slate-600">
              <span className="font-mono uppercase tracking-[0.2em] text-slate-600">EcoLoop Autonomous BMS</span>
              <span>
                Real-time energy optimization ·{' '}
                {source === 'live' ? 'Connected to Supabase' : source === 'mock' ? 'Simulated telemetry' : 'Connecting…'}
              </span>
            </footer>
          </div>
        </div>
      </div>
    </div>
  );
}

function ZoneSummary({ telemetry }: { telemetry: ReturnType<typeof useLiveData>['telemetry'] }) {
  const last = telemetry[telemetry.length - 1];
  const temp = last?.zoneTemp ?? 22;
  const carbon = last?.carbon ?? 320;
  const iaq = last?.iaq ?? 550;
  const iaqElevated = iaq >= 1000;
  const zones = [
    { name: 'Zone A', temp: +(temp + 0.4).toFixed(1), load: 68 },
    { name: 'Zone B', temp: +(temp - 0.3).toFixed(1), load: 54 },
    { name: 'Zone C', temp: +(temp + 0.8).toFixed(1), load: 41 },
    { name: 'Zone D', temp: +(temp - 0.6).toFixed(1), load: 77 },
  ];
  return (
    <div className="h-full rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">Zone Status</h2>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-600">live</span>
      </div>
      <div className="mb-4 h-px bg-gradient-to-r from-emerald-400/30 via-slate-300/60 to-transparent" />
      <div className="space-y-3">
        {zones.map((z) => {
          const ok = z.temp >= 20 && z.temp <= 24;
          return (
            <div key={z.name} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium tracking-wide text-slate-700">{z.name}</span>
                <span
                  className={`font-mono text-sm tabular-nums ${
                    ok ? 'text-emerald-600' : 'text-amber-600'
                  }`}
                >
                  {z.temp}°C
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-emerald-400 transition-all duration-500"
                    style={{ width: `${z.load}%` }}
                  />
                </div>
                <span className="font-mono text-[10px] text-slate-600 tabular-nums">{z.load}%</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-4 space-y-1.5 border-t border-slate-200 pt-3 text-[11px] text-slate-600">
        <div className="flex items-center justify-between">
          <span className="tracking-wide">Grid carbon intensity</span>
          <span className="font-mono text-slate-700 tabular-nums">{carbon} gCO₂/kWh</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="tracking-wide">Indoor air quality (CO₂, est.)</span>
          <span className={`font-mono tabular-nums ${iaqElevated ? 'text-amber-600' : 'text-slate-700'}`}>
            {iaq} ppm
          </span>
        </div>
      </div>
    </div>
  );
}

export default App;
