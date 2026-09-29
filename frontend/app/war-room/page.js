"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../../lib/api";
import { useStream } from "../../lib/stream";
import { PHASE_LABEL, SALES, shortToken } from "../../lib/scenarios";
import { ScenarioBar, TransactionDrawer } from "../../components/console";
import { EmptyState, Gauge, KpiTile, Panel, SeverityBadge } from "../../components/ui";

const GeoMap = dynamic(() => import("../../components/GeoMap"), {
  ssr: false,
  loading: () => <div className="h-[340px] animate-pulse rounded-lg bg-white/5" />,
});

const MIX_COLORS = { Approve: "#34d399", "Step-up": "#fbbf24", Block: "#fb7185" };
const SLICE_COLORS = ["#3ee0c5", "#38bdf8", "#fbbf24", "#fb7185", "#a78bfa", "#64748b"];

function surgeVerdict(latest) {
  if (!latest) return "—";
  if (Number(latest.vol_z) < 2.5) return "No surge";
  return latest.surge?.verdict || "—";
}

export default function WarRoomPage() {
  const stream = useStream();
  const [events, setEvents] = useState([]);
  const [report, setReport] = useState(null);
  const [buckets, setBuckets] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    api("/sales").then((body) => setEvents(body.events || [])).catch(() => {});
  }, []);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const [body, series] = await Promise.all([api("/sale/report"), api("/timeseries?seconds=120")]);
        if (stop) return;
        setReport(body);
        setBuckets(series.buckets || []);
      } catch {
        /* waits for the API */
      }
    }
    tick();
    const timer = setInterval(tick, 1500);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  const latest = stream.feed[0];
  const sale = events.find((event) => event.id === report?.scenario);
  const phaseRows = report?.phases || [];
  const statsByPhase = Object.fromEntries(phaseRows.map((row) => [row.phase, row]));
  const phases = sale ? sale.phases : phaseRows.map((row) => ({ id: row.phase, label: PHASE_LABEL[row.phase] || row.phase }));
  const activePhase = latest?.phase || "";
  const totals = report?.totals || {};
  const tps = buckets.at(-1)?.tps || 0;

  const points = useMemo(
    () =>
      stream.feed
        .filter((row) => row.lat != null && row.lon != null)
        .map((row) => ({
          id: row.id,
          lat: row.lat,
          lon: row.lon,
          decision: row.decision,
          region: row.region,
          label: `${row.decision} ${money(row.amount)} · ${row.region || "unknown"}${row.phase ? ` · ${PHASE_LABEL[row.phase] || row.phase}` : ""}`,
        })),
    [stream.feed]
  );
  const geoSource = stream.feed.find((row) => row.geo_source)?.geo_source;
  const attacks = useMemo(() => stream.feed.filter((row) => row.decision !== "APPROVE").slice(0, 30), [stream.feed]);

  const mix = useMemo(() => {
    const counts = { Approve: 0, "Step-up": 0, Block: 0 };
    phaseRows.forEach((row) => {
      counts.Approve += row.decisions?.APPROVE || 0;
      counts["Step-up"] += row.decisions?.STEP_UP || 0;
      counts.Block += row.decisions?.BLOCK || 0;
    });
    return Object.entries(counts).map(([name, n]) => ({ name, n }));
  }, [phaseRows]);
  const merchants = report?.merchants || [];
  const merchantSlices = merchants.slice(0, 5).map((row) => ({ name: row.name || shortToken(row.token), n: row.payments }));

  return (
    <div className="space-y-4">
      <ScenarioBar />

      <Panel title={sale ? `${sale.name} · live` : "Sale War Room"} demo="phases">
        {!sale && (
          <p className="mb-3 text-sm text-slate-400">
            Run Big Billion Days (B) or Great Indian Festival (G). Phases, merchants, and attacks fill in as the sale plays out.
            Other scenarios still report here as one live phase.
          </p>
        )}
        <div className="flex gap-2 overflow-x-auto">
          {phases.map((phase) => {
            const row = statsByPhase[phase.id];
            const active = phase.id === activePhase;
            const attack = !["warmup", "sale_open", "cooldown", "live"].includes(phase.id);
            return (
              <div
                key={phase.id}
                className={`min-w-[140px] flex-1 rounded-lg border p-2 ${active ? "border-mint bg-mint/10" : row ? "border-line bg-white/[0.02]" : "border-line/50 opacity-50"}`}
              >
                <p className={`text-[11px] uppercase tracking-wide ${attack ? "text-ember" : "text-slate-400"}`}>{phase.label}</p>
                <p className="num text-lg">{row?.n ?? 0}</p>
                <p className="text-[10px] text-slate-500">
                  {row ? `${row.tps}/s · ${row.regime}` : "not reached"}
                </p>
                {row?.catch_rate != null && <p className="num text-[10px] text-ok">caught {(row.catch_rate * 100).toFixed(0)}%</p>}
                {row?.false_decline_rate != null && row.legit_n > 0 && (
                  <p className="num text-[10px] text-slate-400">false decline {(row.false_decline_rate * 100).toFixed(2)}%</p>
                )}
              </div>
            );
          })}
        </div>
      </Panel>

      <section className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <KpiTile label="GMV approved" value={money(totals.gmv)} hint="Approved sale value" />
        <KpiTile label="Throughput" value={`${tps}/s`} hint="Last second" spark={buckets.map((b) => b.tps)} />
        <KpiTile label="Fraud blocked" value={money(totals.blocked_amount)} hint={`${totals.fraud_caught || 0} of ${totals.fraud_n || 0} fraud rows`} />
        <KpiTile label="Fraud leaked" value={money(totals.fraud_leaked)} hint="Approved fraud rupees" />
        <KpiTile label="Buyers declined" value={totals.legit_blocked ?? 0} hint={`of ${totals.legit_n || 0} genuine`} />
        <KpiTile label="Regime" value={stream.regime} hint={surgeVerdict(latest)} />
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Panel title="Where payments come from" action={<span className="text-[11px] text-slate-500">{geoSource === "real" ? "Real coordinates" : geoSource === "simulated" ? "Simulated city centroids" : "No location on these rows"}</span>}>
          <GeoMap points={points} height={340} />
          <p className="mt-2 text-[11px] text-slate-500">Last 200 payments. Green approved, amber stepped up, red blocked. Tiles from OpenStreetMap.</p>
        </Panel>
        <Panel title="Is this a genuine sale?" demo="surge">
          <p className="text-lg font-semibold">{surgeVerdict(latest)}</p>
          <p className="mb-3 text-xs text-slate-500">Shown only when volume is actually high.</p>
          <div className="space-y-3">
            <Gauge label="Merchant concentration" value={latest?.surge?.merchant_gini} max={1} threshold={0.45} polarity="genuine" />
            <Gauge label="Round amounts" value={latest?.surge?.round_ratio} max={1} threshold={0.5} />
            <Gauge label="Timing regularity" value={latest?.surge?.timing_cv == null ? null : Math.max(0, 1 - latest.surge.timing_cv)} max={1} threshold={0.7} />
            <Gauge label="Device diversity" value={latest?.surge?.device_diversity} max={1} threshold={0.3} polarity="genuine" />
            <Gauge label="Geography spread" value={latest?.surge?.geo_entropy} max={1} threshold={0.55} />
            <Gauge label="Fan-out" value={latest?.detectors?.fan_out} max={1} threshold={0.5} />
            <Gauge label="Card testing" value={latest?.detectors?.card_test} max={1} threshold={0.5} />
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Merchant leaderboard">
          {merchants.length === 0 ? (
            <EmptyState title="No merchants yet" />
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-[11px] uppercase text-slate-500">
                <tr><th className="py-1">Merchant</th><th>Payments</th><th>Value</th><th>Flagged</th></tr>
              </thead>
              <tbody>
                {merchants.map((row) => (
                  <tr key={row.token} className="border-t border-line">
                    <td className="py-1.5">
                      <Link className="hover:text-mint" href={`/investigate/merchant/${row.token}`}>{row.name || shortToken(row.token)}</Link>
                      {row.category && <span className="ml-1 text-[10px] text-slate-500">{row.category}</span>}
                    </td>
                    <td className="num">{row.payments}</td>
                    <td className="num">{money(row.amount)}</td>
                    <td className={`num ${row.flag_rate >= 0.2 ? "text-ember" : "text-slate-300"}`}>{(row.flag_rate * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
        <Panel title="Decisions this sale">
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={mix} dataKey="n" nameKey="name" innerRadius={40} outerRadius={64}>
                  {mix.map((slice) => <Cell key={slice.name} fill={MIX_COLORS[slice.name]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Merchant concentration">
          <div className="h-44">
            {merchantSlices.length === 0 ? <EmptyState title="No merchants yet" /> : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={merchantSlices} dataKey="n" nameKey="name" innerRadius={40} outerRadius={64}>
                    {merchantSlices.map((slice, index) => <Cell key={slice.name} fill={SLICE_COLORS[index % SLICE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
          <p className="text-[11px] text-slate-500">A genuine sale piles onto a few flagship merchants.</p>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Panel title="Attack feed" action={<Link href="/investigate" className="text-xs text-mint">Open cases</Link>}>
          {attacks.length === 0 ? (
            <EmptyState title="No challenged payments yet" />
          ) : (
            <ul className="max-h-80 space-y-1 overflow-auto text-sm">
              {attacks.map((row) => (
                <li key={row.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-white/5" onClick={() => setSelected(row)}>
                  <SeverityBadge value={row.decision} />
                  <span className="num w-20 text-slate-300">{money(row.amount)}</span>
                  <span className="w-28 truncate text-xs text-slate-500">{PHASE_LABEL[row.phase] || row.phase || "—"}</span>
                  <span className="w-20 truncate text-xs text-slate-500">{row.region || "—"}</span>
                  <span className="flex-1 truncate text-xs text-slate-400">{row.reasons?.[0]?.text || "model score"}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Sale report">
          {phaseRows.length === 0 ? (
            <EmptyState title="Nothing scored yet" />
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase text-slate-500">
                <tr><th className="py-1">Phase</th><th>n</th><th>GMV</th><th>Blocked</th><th>Top signal</th></tr>
              </thead>
              <tbody>
                {phaseRows.map((row) => (
                  <tr key={row.phase} className="border-t border-line">
                    <td className="py-1">{PHASE_LABEL[row.phase] || row.phase}</td>
                    <td className="num">{row.n}</td>
                    <td className="num">{money(row.gmv)}</td>
                    <td className="num">{money(row.blocked_amount)}</td>
                    <td className="text-slate-400">{row.top_signals?.[0] || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="mt-3 h-24">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={buckets}>
                <XAxis dataKey="t" hide />
                <YAxis hide />
                <Tooltip />
                <Line dataKey="legit_n" name="Legitimate" stroke="#34d399" dot={false} strokeWidth={2} />
                <Line dataKey="flagged_n" name="Challenged or blocked" stroke="#fb7185" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-slate-500">
            Available sales: {SALES.map((item) => item.label).join(", ")}.
          </p>
        </Panel>
      </div>

      <TransactionDrawer selected={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
