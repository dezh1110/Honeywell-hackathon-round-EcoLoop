import { useState } from 'react';
import { IndianRupee, Settings2 } from 'lucide-react';

type Props = {
  energySavedKwh: number;
  energySavedPct: number;
};

const DEFAULT_RATE_PER_KWH = 8; // INR/kWh, typical Indian commercial tariff — adjust to your actual tariff
const DEFAULT_DEPLOYMENT_COST = 150000; // INR, illustrative agent+sensor retrofit cost for a small building

export function CostSavings({ energySavedKwh, energySavedPct }: Props) {
  const [rate, setRate] = useState(DEFAULT_RATE_PER_KWH);
  const [deploymentCost, setDeploymentCost] = useState(DEFAULT_DEPLOYMENT_COST);
  const [showAssumptions, setShowAssumptions] = useState(false);

  const sessionSavingsInr = energySavedKwh * rate;
  // Rough monthly projection: assumes the session's savings rate holds
  // across a representative 10 operating hours/day, 26 days/month. This is
  // explicitly illustrative — see the assumptions panel.
  const monthlyKwh = (energySavedKwh * (10 * 26)) / 4; // session sample assumed ~4 "operating hours" of data
  const monthlySavingsInr = monthlyKwh * rate;
  const paybackMonths = monthlySavingsInr > 0 ? deploymentCost / monthlySavingsInr : Infinity;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-glow">
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <IndianRupee className="h-4 w-4 text-emerald-600" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">Cost Impact</h2>
        </div>
        <button
          onClick={() => setShowAssumptions((v) => !v)}
          className="inline-flex items-center gap-1 text-[10px] text-slate-600 hover:text-emerald-700"
        >
          <Settings2 className="h-3 w-3" /> assumptions
        </button>
      </div>
      <div className="mb-4 h-px bg-gradient-to-r from-emerald-400/30 via-slate-300/60 to-transparent" />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-600">This session</div>
          <div className="mt-1 font-mono text-xl font-semibold text-emerald-600 tabular-nums">
            ₹{sessionSavingsInr.toFixed(0)}
          </div>
          <div className="mt-0.5 text-[10px] text-slate-600">{energySavedPct}% below baseline</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-600">Projected monthly</div>
          <div className="mt-1 font-mono text-xl font-semibold text-slate-900 tabular-nums">
            ₹{monthlySavingsInr.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </div>
          <div className="mt-0.5 text-[10px] text-slate-600">at current optimization rate</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-600">Payback estimate</div>
          <div className="mt-1 font-mono text-xl font-semibold text-slate-900 tabular-nums">
            {Number.isFinite(paybackMonths) ? `${paybackMonths.toFixed(1)} mo` : '—'}
          </div>
          <div className="mt-0.5 text-[10px] text-slate-600">on ₹{deploymentCost.toLocaleString('en-IN')} retrofit</div>
        </div>
      </div>

      {showAssumptions && (
        <div className="mt-4 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3.5">
          <div>
            <label className="mb-1 block text-[11px] text-slate-500">Electricity rate (₹/kWh)</label>
            <input
              type="number"
              value={rate}
              onChange={(e) => setRate(parseFloat(e.target.value) || 0)}
              className="w-full rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-800 outline-none focus:border-emerald-400/40"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-slate-500">Agent + sensor retrofit cost (₹)</label>
            <input
              type="number"
              value={deploymentCost}
              onChange={(e) => setDeploymentCost(parseFloat(e.target.value) || 0)}
              className="w-full rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-800 outline-none focus:border-emerald-400/40"
            />
          </div>
          <p className="text-[10px] leading-relaxed text-slate-600">
            These figures are illustrative projections from a short session, not a financial guarantee. Monthly
            and payback estimates assume the current optimization rate holds across representative operating
            hours — adjust the inputs above to match your actual tariff and deployment cost.
          </p>
        </div>
      )}
    </div>
  );
}
