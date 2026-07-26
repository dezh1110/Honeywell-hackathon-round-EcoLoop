import { useEffect, useRef, useState } from 'react';
import {
  supabase,
  isSupabaseConfigured,
  type BuildingLog,
  type BuildingTelemetryRow,
  type ZoneReadingRow,
} from '@/lib/supabase';

export const ZONE_NAMES = ['ZONE A', 'ZONE B', 'ZONE C', 'ZONE D'];

export type TelemetryPoint = {
  t: string;
  baseline: number;
  optimized: number;
  carbon: number;
  zoneTemp: number;
  iaq: number;
};

export type Kpis = {
  energySavedKwh: number;
  energySavedPct: number;
  carbonAvoidedKg: number;
  zoneTemp: number;
  gridCarbon: number;
  iaq: number;
};

const MOCK_REASONS: string[] = [
  'Grid carbon spike detected -> Pre-cooling zone setpoint adjusted to 21C.',
  'Occupancy forecast: Zone B +18% load. Shifting HVAC bias proactively.',
  'Solar surplus detected. Discharging thermal storage in lieu of grid draw.',
  'Demand response window opening in 12 min. Pre-chilling Zone A by 1.5C.',
  'Zone C ambient drop detected. Heating setpoint raised to 21.5C.',
  'Carbon intensity falling. Relaxing cooling setpoint to 23C to bank savings.',
  'Battery SoC 84%. Holding discharge for forecast evening peak.',
  'Grid frequency dip -> load-shed non-critical Zone D pumps for 90s.',
  'Occupancy below threshold in Zone E. Setback to 19C to conserve energy.',
  'Renewable mix improved to 41%. Re-engaging comfort band optimization.',
];

const ZONES = ['Zone A', 'Zone B', 'Zone C', 'Zone D', 'Zone E'];

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n));
}

function smoothStep(prev: number, lo: number, hi: number, vol: number) {
  return clamp(prev + (Math.random() - 0.5) * vol, lo, hi);
}

function makeMockLog(now: Date, i: number): BuildingLog {
  const sev = Math.random() < 0.7 ? 'info' : Math.random() < 0.7 ? 'warning' : 'critical';
  const types = ['grid_carbon', 'cooling', 'heating', 'occupancy', 'system'] as const;
  return {
    id: `mock-${now.getTime()}-${i}`,
    created_at: now.toISOString(),
    event_type: pick([...types]),
    message: pick(MOCK_REASONS),
    severity: sev as BuildingLog['severity'],
    zone: Math.random() < 0.6 ? pick(ZONES) : null,
    metric_value: Math.round((18 + Math.random() * 8) * 10) / 10,
    reasoning_trace: [],
  };
}

function seedMockLogs(): BuildingLog[] {
  const out: BuildingLog[] = [];
  const now = new Date();
  for (let i = 0; i < 8; i++) {
    const d = new Date(now.getTime() - (8 - i) * 4000);
    out.push(makeMockLog(d, i));
  }
  return out;
}

function seedTelemetry(): TelemetryPoint[] {
  const pts: TelemetryPoint[] = [];
  const now = Date.now();
  let baseline = 62 + Math.random() * 6;
  let optimized = 42 + Math.random() * 5;
  let carbon = 320 + Math.random() * 40;
  let zoneTemp = 22 + Math.random();
  let iaq = 550 + Math.random() * 60;
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now - i * 2000);
    baseline = smoothStep(baseline, 55, 78, 4);
    optimized = smoothStep(optimized, 32, 52, 3.5);
    carbon = smoothStep(carbon, 240, 460, 18);
    zoneTemp = smoothStep(zoneTemp, 19.5, 25, 0.4);
    iaq = smoothStep(iaq, 420, 900, 25);
    pts.push({
      t: d.toLocaleTimeString('en-US', { hour12: false }),
      baseline: Math.round(baseline * 10) / 10,
      optimized: Math.round(optimized * 10) / 10,
      carbon: Math.round(carbon),
      zoneTemp: Math.round(zoneTemp * 10) / 10,
      iaq: Math.round(iaq),
    });
  }
  return pts;
}

const ZONE_TEMP_OFFSETS = [0.4, -0.3, 0.8, -0.6];

function makeZoneReadings(avgTemp: number): ZoneReadingRow[] {
  return ZONE_NAMES.map((zone, idx) => {
    const airTemp = Math.round((avgTemp + ZONE_TEMP_OFFSETS[idx]) * 10) / 10;
    return {
      zone,
      air_temp_c: airTemp,
      pmv: Math.round((airTemp - 23.0) * 0.45 * 100) / 100,
      occupant_count: null,
    };
  });
}

function makeMockTelemetryRow(d: Date, i: number, point: TelemetryPoint): BuildingTelemetryRow {
  return {
    id: `mock-tel-${d.getTime()}-${i}`,
    created_at: d.toISOString(),
    sim_time: point.t,
    baseline_kw: point.baseline,
    optimized_kw: point.optimized,
    grid_carbon_intensity: point.carbon,
    indoor_air_quality_ppm: point.iaq,
    avg_zone_temp: point.zoneTemp,
    zones: makeZoneReadings(point.zoneTemp),
  };
}

export type DataSource = 'connecting' | 'live' | 'mock';

export function useLiveData() {
  const [telemetry, setTelemetry] = useState<TelemetryPoint[]>(() => seedTelemetry());
  const [telemetryRows, setTelemetryRows] = useState<BuildingTelemetryRow[]>(() =>
    seedTelemetry().map((p, i) => makeMockTelemetryRow(new Date(Date.now() - (11 - i) * 2000), i, p))
  );
  const [logs, setLogs] = useState<BuildingLog[]>(() => seedMockLogs());
  const [source, setSource] = useState<DataSource>('connecting');
  const [kpis, setKpis] = useState<Kpis>({
    energySavedKwh: 0,
    energySavedPct: 0,
    carbonAvoidedKg: 0,
    zoneTemp: 22,
    gridCarbon: 320,
    iaq: 550,
  });

  const mockTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const liveTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stateRef = useRef<DataSource>('connecting');
  stateRef.current = source;
  // Once real rows land in `building_telemetry` (written by the Python
  // backend agent), stop overwriting `telemetry` with the synthetic
  // random-walk below — real data wins.
  const usingRealTelemetryRef = useRef(false);

  const stopMock = () => {
    if (mockTimer.current) {
      clearInterval(mockTimer.current);
      mockTimer.current = null;
    }
  };
  const stopLive = () => {
    if (liveTimer.current) {
      clearInterval(liveTimer.current);
      liveTimer.current = null;
    }
  };

  const nextMockPoint = (last: TelemetryPoint): TelemetryPoint => {
    const d = new Date();
    const baseline = smoothStep(last.baseline, 55, 78, 4);
    const optimized = smoothStep(last.optimized, 32, 52, 3.5);
    const carbon = smoothStep(last.carbon, 240, 460, 18);
    const zoneTemp = smoothStep(last.zoneTemp, 19.5, 25, 0.4);
    const iaq = smoothStep(last.iaq, 420, 900, 25);
    return {
      t: d.toLocaleTimeString('en-US', { hour12: false }),
      baseline: Math.round(baseline * 10) / 10,
      optimized: Math.round(optimized * 10) / 10,
      carbon: Math.round(carbon),
      zoneTemp: Math.round(zoneTemp * 10) / 10,
      iaq: Math.round(iaq),
    };
  };

  const advanceMockTelemetry = () => {
    if (usingRealTelemetryRef.current) return;
    setTelemetry((prev) => {
      const point = nextMockPoint(prev[prev.length - 1]);
      setTelemetryRows((prevRows) => [
        ...prevRows.slice(-23),
        makeMockTelemetryRow(new Date(), prevRows.length, point),
      ]);
      return [...prev.slice(-23), point];
    });
  };

  const startMock = () => {
    stopMock();
    mockTimer.current = setInterval(() => {
      advanceMockTelemetry();
      setLogs((prev) => {
        const next = makeMockLog(new Date(), prev.length);
        return [...prev.slice(-49), next];
      });
    }, 2000);
  };

  const startLivePoll = () => {
    stopLive();
    liveTimer.current = setInterval(async () => {
      const { data, error } = await supabase
        .from('building_logs')
        .select('id, created_at, event_type, message, severity, zone, metric_value, reasoning_trace')
        .order('created_at', { ascending: false })
        .limit(50);
      if (error) {
        setSource('mock');
        startMock();
        return;
      }
      if (data && data.length > 0) {
        const sorted = [...data].reverse() as BuildingLog[];
        setLogs(sorted);
      }
      advanceMockTelemetry();
    }, 2000);
  };

  const mapTelemetryRow = (row: BuildingTelemetryRow): TelemetryPoint => ({
    t: new Date(row.created_at).toLocaleTimeString('en-US', { hour12: false }),
    baseline: Math.round(row.baseline_kw * 10) / 10,
    optimized: Math.round(row.optimized_kw * 10) / 10,
    carbon: Math.round(row.grid_carbon_intensity),
    zoneTemp: Math.round(row.avg_zone_temp * 10) / 10,
    iaq: Math.round(row.indoor_air_quality_ppm),
  });

  useEffect(() => {
    if (!isSupabaseConfigured) {
      setSource('mock');
      startMock();
      return () => stopMock();
    }

    let channel: ReturnType<typeof supabase.channel> | null = null;
    let telemetryChannel: ReturnType<typeof supabase.channel> | null = null;
    let cancelled = false;

    (async () => {
      // Initial fetch
      const { data, error } = await supabase
        .from('building_logs')
        .select('id, created_at, event_type, message, severity, zone, metric_value, reasoning_trace')
        .order('created_at', { ascending: false })
        .limit(50);

      if (cancelled) return;

      if (error) {
        setSource('mock');
        startMock();
        return;
      }

      if (data && data.length > 0) {
        setLogs([...data].reverse() as BuildingLog[]);
        setSource('live');
        startLivePoll();
      } else {
        // No rows yet; stream mock until rows arrive via realtime.
        setSource('mock');
        startMock();
      }

      // Realtime subscription: reasoning log feed
      channel = supabase
        .channel('building_logs_changes')
        .on(
          'postgres_changes',
          { event: 'INSERT', schema: 'public', table: 'building_logs' },
          (payload) => {
            const row = payload.new as BuildingLog;
            setLogs((prev) => {
              if (prev.some((l) => l.id === row.id)) return prev;
              return [...prev.slice(-49), row];
            });
            if (stateRef.current !== 'live') {
              setSource('live');
              stopMock();
              startLivePoll();
            }
          }
        )
        .subscribe();

      // Initial telemetry fetch + realtime subscription: real
      // baseline-vs-optimized kW, grid carbon, and zone temps written by the
      // Python backend agent every decision cycle. Falls back to the
      // synthetic random-walk above until the first row arrives.
      const { data: rawTelemetryRows } = await supabase
        .from('building_telemetry')
        .select('id, created_at, sim_time, baseline_kw, optimized_kw, grid_carbon_intensity, indoor_air_quality_ppm, avg_zone_temp, zones')
        .order('created_at', { ascending: false })
        .limit(24);

      if (!cancelled && rawTelemetryRows && rawTelemetryRows.length > 0) {
        usingRealTelemetryRef.current = true;
        const reversed = [...rawTelemetryRows].reverse() as BuildingTelemetryRow[];
        setTelemetry(reversed.map((r) => mapTelemetryRow(r)));
        setTelemetryRows(reversed);
      }

      telemetryChannel = supabase
        .channel('building_telemetry_changes')
        .on(
          'postgres_changes',
          { event: 'INSERT', schema: 'public', table: 'building_telemetry' },
          (payload) => {
            usingRealTelemetryRef.current = true;
            const row = payload.new as BuildingTelemetryRow;
            setTelemetry((prev) => [...prev.slice(-23), mapTelemetryRow(row)]);
            setTelemetryRows((prev) => [...prev.slice(-23), row]);
          }
        )
        .subscribe();
    })();

    return () => {
      cancelled = true;
      stopMock();
      stopLive();
      if (channel) supabase.removeChannel(channel);
      if (telemetryChannel) supabase.removeChannel(telemetryChannel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Derive KPIs from telemetry + logs.
  useEffect(() => {
    if (telemetry.length === 0) return;
    const recent = telemetry.slice(-12);
    const baselineSum = recent.reduce((s, p) => s + p.baseline, 0);
    const optSum = recent.reduce((s, p) => s + p.optimized, 0);
    const savedKwh = Math.max(0, Math.round((baselineSum - optSum) * 10) / 10);
    const savedPct = baselineSum > 0 ? Math.round(((baselineSum - optSum) / baselineSum) * 100) : 0;
    const carbonAvoided = Math.round(savedKwh * 0.42 * 10) / 10;
    const last = recent[recent.length - 1];
    setKpis({
      energySavedKwh: savedKwh,
      energySavedPct: savedPct,
      carbonAvoidedKg: carbonAvoided,
      zoneTemp: last.zoneTemp,
      gridCarbon: last.carbon,
      iaq: last.iaq,
    });
  }, [telemetry]);

  return { telemetry, telemetryRows, logs, source, kpis, isSupabaseConfigured };
}
