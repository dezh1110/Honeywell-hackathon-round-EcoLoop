import { useEffect, useRef, useState } from 'react';
import { MessageSquare, Send, Loader2, ChevronDown, Wrench } from 'lucide-react';
import { supabase, isSupabaseConfigured, type NlpQueryRow } from '@/lib/supabase';

const SAMPLE_QUESTIONS = [
  'Which zone is using the most energy right now?',
  'Is the grid carbon intensity high right now?',
  'Are there any runtime errors in the current simulation?',
  'What is the current temperature in Zone C?',
];

function mockAnswer(question: string): string {
  const q = question.toLowerCase();
  if (q.includes('energy') || q.includes('load')) {
    return 'Zone D is currently drawing the most power at roughly 2.1 kW, about 18% above the building average.';
  }
  if (q.includes('carbon')) {
    return 'Grid carbon intensity is currently 342 gCO2/kWh, within the normal range for this time of day.';
  }
  if (q.includes('error')) {
    return 'No warnings, severe, or fatal errors in the most recent simulation run.';
  }
  return 'Zone C is currently at 23.1°C, within the comfort band and not requiring any action.';
}

function TracePreview({ trace }: { trace: NlpQueryRow['reasoning_trace'] }) {
  const [open, setOpen] = useState(false);
  if (!trace || trace.length === 0) return null;
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded border border-slate-300 px-1.5 py-0.5 text-[10px] text-slate-500 hover:border-emerald-400/40 hover:text-emerald-700"
      >
        <Wrench className="h-2.5 w-2.5" />
        {trace.length} tool call{trace.length > 1 ? 's' : ''}
        <ChevronDown className={`h-2.5 w-2.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="mt-1.5 space-y-1 border-l border-slate-200 pl-3 font-mono text-[10px] text-slate-600">
          {trace.map((step, i) => (
            <div key={i}>
              <span className="text-cyan-600">{step.tool}</span>
              {' → '}
              {typeof step.result === 'string' ? step.result : JSON.stringify(step.result)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function NlpInsights() {
  const [question, setQuestion] = useState('');
  const [queries, setQueries] = useState<NlpQueryRow[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [queries]);

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    let cancelled = false;

    (async () => {
      const { data } = await supabase
        .from('nlp_queries')
        .select('*')
        .order('created_at', { ascending: true })
        .limit(30);
      if (!cancelled && data) setQueries(data as NlpQueryRow[]);
    })();

    const channel = supabase
      .channel('nlp_queries_changes')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'nlp_queries' },
        (payload) => {
          const row = payload.new as NlpQueryRow;
          setQueries((prev) => {
            const idx = prev.findIndex((q) => q.id === row.id);
            if (idx === -1) return [...prev, row];
            const next = [...prev];
            next[idx] = row;
            return next;
          });
        }
      )
      .subscribe();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, []);

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || submitting) return;
    setSubmitting(true);
    setQuestion('');

    if (!isSupabaseConfigured) {
      const localRow: NlpQueryRow = {
        id: `mock-${Date.now()}`,
        created_at: new Date().toISOString(),
        question: q,
        answer: null,
        reasoning_trace: [],
        status: 'pending',
      };
      setQueries((prev) => [...prev, localRow]);
      setTimeout(() => {
        setQueries((prev) =>
          prev.map((row) =>
            row.id === localRow.id
              ? { ...row, answer: mockAnswer(q), status: 'answered', reasoning_trace: [
                  { tool: 'get_current_telemetry', arguments: {}, result: '(simulated)' },
                ] }
              : row
          )
        );
        setSubmitting(false);
      }, 900);
      return;
    }

    const { data, error } = await supabase
      .from('nlp_queries')
      .insert({ question: q, status: 'pending' })
      .select()
      .single();

    if (error || !data) {
      console.error(error);
      setQueries((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          created_at: new Date().toISOString(),
          question: q,
          answer: `Couldn't submit that question${error ? `: ${error.message}` : ''}. Check that Supabase is reachable.`,
          reasoning_trace: [],
          status: 'error',
        },
      ]);
      setSubmitting(false);
      return;
    }

    setQueries((prev) => {
      if (prev.some((row) => row.id === data.id)) return prev;
      return [...prev, data as NlpQueryRow];
    });
    setSubmitting(false);
  };

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-glow">
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-emerald-600" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">NLP Insights</h2>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-600">
          {isSupabaseConfigured ? 'live agent' : 'simulated'}
        </span>
      </div>

      <div ref={scrollRef} className="scroll-thin flex-1 space-y-3 overflow-y-auto px-5 py-4" style={{ maxHeight: 280 }}>
        {queries.length === 0 && (
          <div className="py-6 text-center text-xs text-slate-600">
            Ask a question about the building's current state, agent decisions, or performance.
          </div>
        )}
        {queries.map((row) => (
          <div key={row.id} className="space-y-1.5">
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-xl rounded-tr-sm bg-emerald-500/10 px-3 py-2 text-xs text-emerald-800">
                {row.question}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-xl rounded-tl-sm border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
                {row.status === 'pending' ? (
                  <span className="inline-flex items-center gap-1.5 text-slate-600">
                    <Loader2 className="h-3 w-3 animate-spin" /> thinking…
                  </span>
                ) : (
                  <>
                    {row.answer}
                    <TracePreview trace={row.reasoning_trace} />
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-slate-200 px-5 py-3.5">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SAMPLE_QUESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => ask(s)}
              className="rounded-full border border-slate-200 px-2.5 py-1 text-[10px] text-slate-500 hover:border-emerald-400/40 hover:text-emerald-700"
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && ask(question)}
            placeholder="Ask me anything about the building..."
            className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 outline-none placeholder:text-slate-600 focus:border-emerald-400/40"
          />
          <button
            onClick={() => ask(question)}
            disabled={submitting || !question.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" /> Ask
          </button>
        </div>
      </div>
    </div>
  );
}
