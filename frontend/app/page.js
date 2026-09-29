"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../lib/api";
import { useStream } from "../lib/stream";
import { ChartBox, Tip, tick } from "../components/charts";
import { REGIME_COLOR, ScenarioBar, TransactionDrawer } from "../components/console";
import { DataTable, EmptyState, Gauge, KpiTile, Panel, SeverityBadge, Skeleton, Timeline } from "../components/ui";

export default function OverviewPage() {
  const stream = useStream();
  const [buckets, setBuckets] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [story, setStory] = useState(null);
  const [selected, setSelected] = useState(null);
  const [focus, setFocus] = useState("decisions");

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const [series, stats, storyBody] = await Promise.all([api("/timeseries?seconds=120"), api("/analytics"), api("/story")]);
        if (stop) return;
        setBuckets(series.buckets || []);
        setAnalytics(stats);
        setStory(storyBody);
      } catch {
        /* charts wait for the API */
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
  const totals = stream.totals || {};
  const seen = totals.seen || 0;
  const approveRate = seen ? (totals.ss_approve / seen) * 100 : 0;
  const ssDecline = seen ? totals.ss_legit_blocked_n / seen : 0;
  const stDecline = seen ? totals.st_legit_blocked_n / seen : 0;
  const benefit =
    (totals.ss_fraud_caught_amt || 0) -
    (totals.st_fraud_caught_amt || 0) +
    ((totals.st_legit_blocked_amt || 0) - (totals.ss_legit_blocked_amt || 0));
  const tps = buckets.at(-1)?.tps || 0;
  const rules = stream.config?.regime_rules || {};
  const flagged = useMemo(() => stream.feed.filter((row) => row.decision !== "APPROVE").slice(0, 12), [stream.feed]);
  const mix = [
    { name: "Approve", value: totals.ss_approve || 0, fill: "#34d399" },
    { name: "Step-up", value: totals.ss_step || 0, fill: "#fbbf24" },
    { name: "Block", value: totals.ss_block || 0, fill: "#fb7185" },
  ];
  const histogram = (analytics?.score_histogram || []).map((count, index) => ({ score: index, count }));

  const cumulative = useMemo(() => {
    let ss = 0;
    let st = 0;
    return buckets.map((bucket) => {
      ss += bucket.ss_caught || 0;
      st += bucket.st_caught || 0;
      return { t: bucket.t, surge: Math.round(ss), static: Math.round(st) };
    });
  }, [buckets]);

  return (
    <div className="space-y-4">
      <ScenarioBar />

      <Panel title="Stream regime" demo="regime">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <SeverityBadge value={stream.regime} />
            <p className="mt-2 max-w-xl text-sm text-slate-400">
              Volume alone does not move this state. A genuine sale stays open. A tight probe-then-drain ring flips it to attack.
            </p>
          </div>
          <p className="num text-xs text-slate-400">p50 {totals.latency_p50 ?? 0} ms · p99 {totals.latency_p99 ?? 0} ms</p>
        </div>
        <div className="mt-3 flex h-3 overflow-hidden rounded bg-white/5">
          {(buckets.length ? buckets : [{ regime: "NORMAL" }]).map((bucket, index) => (
            <div key={`${bucket.t || index}`} className="h-3 flex-1" style={{ background: REGIME_COLOR[bucket.regime] || "#1c2740" }} title={bucket.regime} />
          ))}
        </div>
      </Panel>

      <section className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <button type="button" onClick={() => setFocus("throughput")} className="text-left">
          <KpiTile label="Throughput" value={`${tps}/s`} hint="Last second. Click to chart it." spark={buckets.map((b) => b.tps)} />
        </button>
        <KpiTile label="p99 latency" value={`${totals.latency_p99 ?? 0} ms`} hint={`SLO ${stream.config?.slo_p99_ms || 25} ms`} />
        <button type="button" onClick={() => setFocus("decisions")} className="text-left">
          <KpiTile label="Approval rate" value={`${approveRate.toFixed(1)}%`} hint={`${totals.ss_approve || 0} approved. Click the mix.`} />
        </button>
        <KpiTile label="Fraud stopped" value={money(totals.ss_fraud_caught_amt)} hint={`Static ${money(totals.st_fraud_caught_amt)}`} />
        <KpiTile label="False declines" value={totals.ss_legit_blocked_n ?? 0} hint={`Static ${totals.st_legit_blocked_n ?? 0}`} delta={Number(((stDecline - ssDecline) * 100).toFixed(2))} />
        <button type="button" onClick={() => setFocus("value")} className="text-left">
          <KpiTile label="Net vs static" value={money(benefit)} hint="Click to compare rupees" />
        </button>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Detection signals" demo="signals">
          <div className="space-y-3">
            <Gauge label="Volume z-score" value={latest?.vol_z} max={6} threshold={rules.vol_z_surge || 2.5} />
            <Gauge label="Cluster tightness" value={latest?.tightness} max={1} threshold={rules.tightness_attack || 0.62} />
            <Gauge label="Probe then drain" value={latest?.probe} max={1} threshold={rules.probe || 0.45} />
            <Gauge label="Coordination" value={latest?.coordination} max={1} threshold={0.75} />
            <Gauge label="Drift PSI" value={latest?.psi} max={0.6} threshold={rules.psi_alert || 0.2} />
          </div>
        </Panel>
        <Panel title={focus === "value" ? "Rupees stopped, this run versus static" : focus === "throughput" ? "Payments per second" : "Decisions per second"}>
          <div className="mb-2 flex gap-2 text-xs">
            {[
              ["decisions", "Decisions"],
              ["throughput", "Throughput"],
              ["value", "Rupees"],
            ].map(([id, label]) => (
              <button key={id} type="button" onClick={() => setFocus(id)} className={focus === id ? "text-mint" : "text-slate-500"}>
                {label}
              </button>
            ))}
          </div>
          <ChartBox height={220}>
            <ResponsiveContainer width="100%" height="100%">
              {focus === "value" ? (
                <AreaChart data={cumulative}>
                  <CartesianGrid stroke="#1c2740" vertical={false} />
                  <XAxis dataKey="t" hide />
                  <YAxis tick={tick} stroke="#64748b" width={40} />
                  <Tooltip content={<Tip />} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Area dataKey="surge" name="SurgeShield" stroke="#3ee0c5" fill="#3ee0c5" fillOpacity={0.25} />
                  <Area dataKey="static" name="Static" stroke="#fb7185" fill="#fb7185" fillOpacity={0.12} />
                </AreaChart>
              ) : (
                <BarChart data={buckets}>
                  <CartesianGrid stroke="#1c2740" vertical={false} />
                  <XAxis dataKey="t" hide />
                  <YAxis tick={tick} stroke="#64748b" width={28} allowDecimals={false} />
                  <Tooltip content={<Tip />} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {focus === "throughput" ? (
                    <Bar dataKey="tps" name="Payments / s" fill="#3ee0c5" radius={[3, 3, 0, 0]} />
                  ) : (
                    <>
                      <Bar dataKey="approve" stackId="d" fill="#34d399" name="Approve" />
                      <Bar dataKey="step" stackId="d" fill="#fbbf24" name="Step-up" />
                      <Bar dataKey="block" stackId="d" fill="#fb7185" name="Block" />
                    </>
                  )}
                </BarChart>
              )}
            </ResponsiveContainer>
          </ChartBox>
        </Panel>
        <Panel title="Decision mix and score shape" demo="compare">
          <div className="grid grid-cols-2 gap-2">
            <ChartBox height={160}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={mix} dataKey="value" nameKey="name" innerRadius={36} outerRadius={58} paddingAngle={2}>
                    {mix.map((slice) => <Cell key={slice.name} fill={slice.fill} />)}
                  </Pie>
                  <Tooltip content={<Tip />} />
                </PieChart>
              </ResponsiveContainer>
            </ChartBox>
            <ChartBox height={160}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histogram}>
                  <XAxis dataKey="score" hide />
                  <YAxis hide />
                  <Tooltip content={<Tip />} />
                  <Bar dataKey="count" name="Scores" fill="#38bdf8" />
                </BarChart>
              </ResponsiveContainer>
            </ChartBox>
          </div>
          <ul className="mt-2 space-y-1 text-sm">
            <li className="flex justify-between"><span className="text-slate-400">Fraud stopped</span><span className="num">{money(totals.ss_fraud_caught_amt)} vs {money(totals.st_fraud_caught_amt)}</span></li>
            <li className="flex justify-between"><span className="text-slate-400">Legit sales declined</span><span className="num">{totals.ss_legit_blocked_n ?? 0} vs {totals.st_legit_blocked_n ?? 0}</span></li>
            <li className="flex justify-between"><span className="text-slate-400">OTP friction</span><span className="num">{money(analytics?.friction_rupees)}</span></li>
          </ul>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.4fr]">
        <Panel title="Replay timeline" demo="timeline">
          {story ? <Timeline milestones={story.milestones} /> : <Skeleton className="h-16" />}
        </Panel>
        <Panel
          title="Latest challenged payments"
          action={<Link href="/investigate" className="text-xs text-mint">Full feed and search</Link>}
        >
          {flagged.length === 0 ? (
            <EmptyState title="Nothing challenged yet" detail="Launch a sale or an attack. B and G start the sales." />
          ) : (
            <DataTable
              rows={flagged}
              rowKey={(row) => row.id}
              onRow={setSelected}
              columns={[
                { key: "id", label: "Id", render: (row) => <span className="num">{row.id}</span> },
                { key: "decision", label: "Decision", render: (row) => <SeverityBadge value={row.decision} /> },
                { key: "risk", label: "Risk", render: (row) => <span className="num">{row.risk_100}</span> },
                { key: "amount", label: "Amount", render: (row) => money(row.amount) },
                { key: "region", label: "City", render: (row) => row.region || "—" },
                { key: "why", label: "Top reason", render: (row) => <span className="text-xs text-slate-400">{row.reasons?.[0]?.text || "model score"}</span> },
              ]}
            />
          )}
        </Panel>
      </div>

      <TransactionDrawer selected={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
