import { memo, useMemo, useState } from 'react';
import { Snowflake, Flame, Bot, Hand, Send, Check } from 'lucide-react';

type Props = {
  autonomous: boolean;
  onToggle: () => void;
  cooling: number;
  heating: number;
  onCooling: (v: number) => void;
  onHeating: (v: number) => void;
  zones?: string[];
  selectedZone?: string;
  onZoneChange?: (zone: string) => void;
  onApplyOverride?: (zone: string, cooling: number, heating: number) => Promise<void> | void;
};

type SliderProps = {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  disabled: boolean;
  accent: string;
  icon: React.ReactNode;
  unit: string;
};

const Slider = memo(function Slider({
  label,
  value,
  min,
  max,
  step = 0.5,
  onChange,
  disabled,
  accent,
  icon,
  unit,
}: SliderProps) {
  const pct = useMemo(
    () => Math.round(((value - min) / (max - min)) * 100),
    [value, min, max]
  );
  return (
    <div className={disabled ? 'opacity-40' : ''}>
      <div className="mb-2.5 flex items-center justify-between">
        <span className="inline-flex items-center gap-2 text-xs font-medium tracking-wide text-slate-700">
          <span className={accent}>{icon}</span>
          {label}
        </span>
        <span className="font-mono text-sm font-semibold text-slate-900 tabular-nums">
          {value.toFixed(1)}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ ['--pct' as any]: `${pct}%` }}
        className="h-7 w-full"
      />
      <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-600 tabular-nums">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
});

export const ControlPanel = memo(function ControlPanel({
  autonomous,
  onToggle,
  cooling,
  heating,
  onCooling,
  onHeating,
  zones = ['ZONE A', 'ZONE B', 'ZONE C', 'ZONE D'],
  selectedZone,
  onZoneChange,
  onApplyOverride,
}: Props) {
  const [applyState, setApplyState] = useState<'idle' | 'applying' | 'applied'>('idle');
  const zone = selectedZone ?? zones[0];

  const handleApply = async () => {
    if (!onApplyOverride) return;
    setApplyState('applying');
    try {
      await onApplyOverride(zone, cooling, heating);
      setApplyState('applied');
      setTimeout(() => setApplyState('idle'), 2000);
    } catch {
      setApplyState('idle');
    }
  };

  return (
    <div className="h-full rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">Manual Override & Control</h2>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-600">hvac</span>
      </div>
      <div className="mb-4 h-px bg-gradient-to-r from-emerald-400/30 via-slate-300/60 to-transparent" />

      <div
        className={`mb-6 flex items-center justify-between rounded-xl border bg-slate-50 px-4 py-3 transition-colors duration-300 ${
          autonomous ? 'border-emerald-400/20' : 'border-amber-400/25'
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`grid h-9 w-9 place-items-center rounded-lg ring-1 transition-colors duration-300 ${
              autonomous
                ? 'bg-emerald-500/10 ring-emerald-400/30'
                : 'bg-amber-500/10 ring-amber-400/30'
            }`}
          >
            {autonomous ? (
              <Bot className="h-5 w-5 text-emerald-600" />
            ) : (
              <Hand className="h-5 w-5 text-amber-600" />
            )}
          </div>
          <div>
            <div className="text-sm font-medium tracking-tight text-slate-900">
              {autonomous ? 'Autonomous Mode' : 'Manual Override'}
            </div>
            <div className="mt-0.5 text-[11px] leading-snug text-slate-600">
              {autonomous
                ? 'Agent is optimizing setpoints automatically'
                : 'Operator assumes direct control of HVAC setpoints'}
            </div>
          </div>
        </div>
        <button
          onClick={onToggle}
          role="switch"
          aria-checked={!autonomous}
          className={`relative h-7 w-12 shrink-0 rounded-full p-0.5 transition-all duration-300 ${
            autonomous
              ? 'bg-emerald-500/80 shadow-[0_0_12px_rgba(52,211,153,0.45)]'
              : 'bg-amber-500/80 shadow-[0_0_12px_rgba(251,191,36,0.45)]'
          }`}
        >
          <span
            className={`block h-6 w-6 rounded-full bg-white shadow transition-transform duration-300 ease-out ${
              autonomous ? 'translate-x-0' : 'translate-x-5'
            }`}
          />
        </button>
      </div>

      <div className="space-y-6">
        <Slider
          label="Target Cooling Setpoint"
          value={cooling}
          min={18}
          max={28}
          onChange={onCooling}
          disabled={autonomous}
          accent="text-cyan-600"
          icon={<Snowflake className="h-4 w-4" />}
          unit="°C"
        />
        <Slider
          label="Target Heating Setpoint"
          value={heating}
          min={16}
          max={26}
          onChange={onHeating}
          disabled={autonomous}
          accent="text-orange-600"
          icon={<Flame className="h-4 w-4" />}
          unit="°C"
        />
      </div>

      <div className={`mt-5 flex items-center gap-2 ${autonomous ? 'opacity-40' : ''}`}>
        <select
          value={zone}
          onChange={(e) => onZoneChange?.(e.target.value)}
          disabled={autonomous}
          className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs font-medium text-slate-700 outline-none focus:border-emerald-400/40"
        >
          {zones.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>
        <button
          onClick={handleApply}
          disabled={autonomous || applyState === 'applying'}
          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {applyState === 'applied' ? (
            <>
              <Check className="h-3.5 w-3.5" /> Sent
            </>
          ) : (
            <>
              <Send className="h-3.5 w-3.5" /> Apply Override
            </>
          )}
        </button>
      </div>

      <div
        className={`mt-5 overflow-hidden rounded-lg border text-xs transition-all duration-300 ${
          autonomous
            ? 'max-h-0 scale-y-0 border-transparent bg-transparent px-0 py-0 opacity-0'
            : 'max-h-20 scale-y-100 border-amber-400/30 bg-amber-500/10 px-3 py-2 opacity-100'
        }`}
      >
        <span className="text-amber-700">
          Manual override active — autonomous agent decisions are suspended for HVAC setpoints.
        </span>
      </div>
    </div>
  );
});
