"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../lib/api";
import { useStream } from "../lib/stream";
import { ChartBox, Tip, tick } from "../components/charts";
import { REGIME_COLOR, ScenarioBar, TransactionDrawer } from "../components/console";
import { DataTable, EmptyState, Gauge, KpiTile, Panel, SeverityBadge, Skeleton, Timeline } from "../components/ui";

const FRICTION = [
  ["friction_none", "None", "#34d399"],
  ["friction_device", "Device", "#3ee0c5"],
  ["friction_push", "Push", "#38bdf8"],
  ["friction_otp", "OTP", "#fbbf24"],
  ["friction_auth", "Step-up", "#fb7185"],
  ["friction_blocked", "Blocked", "#94a3b8"],
];

function FrictionBar({ totals }) {
  const parts = FRICTION.map(([key, name, fill]) => ({ name, fill, value: totals[key] || 0 }));
  const total = parts.reduce((sum, part) => sum + part.value, 0);
  const quiet = total ? ((parts[0].value / total) * 100).toFixed(0) : "0";
  return (
    <div>
      <p className="text-sm text-slate-300"><span className="num text-ok">{quiet}%</span> of payments had zero friction</p>
      <div className="mt-2 flex h-3 overflow-hidden rounded bg-white/5">
        {parts.map((part) => (
          part.value > 0 ? <div key={part.name} style={{ width: `${(part.value / Math.max(total, 1)) * 100}%`, background: part.fill }} title={`${part.name} ${part.value}`} /> : null
        ))}
      </div>
      <p className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-500">
        {parts.map((part) => <span key={part.name}>{part.name} <span className="num text-slate-300">{part.value}</span></span>)}
      </p>
    </div>
  );
}


function exportTrainedDataReport(totals, analytics, benefit) {
  const popup = window.open("", "_blank");
  if (!popup) return;

  const ss_approve = totals.ss_approve || 0;
  const ss_step = totals.ss_step || 0;
  const ss_block = totals.ss_block || 0;
  const seen = totals.seen || Math.max(ss_approve + ss_step + ss_block, 1);
  
  const ss_fraud_caught_amt = totals.ss_fraud_caught_amt || 0;
  const ss_legit_approved_amt = totals.ss_legit_approved_amt || 0;
  const ss_legit_blocked_amt = totals.ss_legit_blocked_amt || 0;
  
  const st_fraud_caught_amt = totals.st_fraud_caught_amt || 0;
  const st_legit_blocked_amt = totals.st_legit_blocked_amt || 0;

  popup.document.write(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Training & Stream Analytics Report</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>

    body { font-family: 'Inter', sans-serif; padding: 40px; color: #e2e8f0; max-width: 900px; margin: 0 auto; background-color: #0b1220; position: relative; }
    body::before {
      content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
      background-image: linear-gradient(rgba(62, 224, 197, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(62, 224, 197, 0.05) 1px, transparent 1px);
      background-size: 20px 20px; z-index: -1; pointer-events: none;
    }
    .header { text-align: center; margin-bottom: 40px; border-bottom: 2px solid #3ee0c5; padding-bottom: 20px; }
    .title { font-size: 32px; font-weight: 800; color: #3ee0c5; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.1em; text-shadow: 0 0 10px rgba(62,224,197,0.5); }
    .subtitle { font-size: 14px; color: #94a3b8; font-family: monospace; }
    .card { background: rgba(30, 41, 59, 0.7); border-radius: 12px; padding: 24px; box-shadow: 0 0 20px rgba(0,0,0,0.5); margin-bottom: 32px; border: 1px solid rgba(62, 224, 197, 0.2); backdrop-filter: blur(10px); }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
    .kpi { padding: 16px; background: rgba(15, 23, 42, 0.8); border-radius: 8px; text-align: center; border: 1px solid rgba(255,255,255,0.05); }
    .kpi-value { font-size: 28px; font-weight: 700; font-family: monospace; }
    .kpi-label { font-size: 10px; text-transform: uppercase; color: #94a3b8; margin-top: 6px; font-weight: 700; letter-spacing: 0.1em; }
    .bar-chart { display: flex; height: 16px; border-radius: 4px; overflow: hidden; margin-top: 24px; box-shadow: inset 0 0 10px rgba(0,0,0,0.5); }
    .bar { height: 100%; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #0b1220; font-weight: 700; }
    .bar.approve { background: #3ee0c5; }
    .bar.step-up { background: #fbbf24; }
    .bar.block { background: #fb7185; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; text-align: left; background: rgba(15, 23, 42, 0.8); border-radius: 8px; overflow: hidden; }
    th { padding: 14px; border-bottom: 1px solid rgba(62,224,197,0.3); font-weight: 700; color: #3ee0c5; text-transform: uppercase; font-size: 11px; letter-spacing: 0.1em; background: rgba(30,41,59,0.9); }
    td { padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.05); color: #cbd5e1; font-size: 13px; font-family: monospace; }
    tr:hover { background: rgba(62,224,197,0.05); }
    h2 { font-size: 14px; font-weight: 700; color: #3ee0c5; margin-top: 0; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 0.1em; display: flex; align-items: center; gap: 8px; }
    h2::before { content: "■"; color: #fbbf24; }
    .footer { text-align: center; margin-top: 60px; font-size: 11px; font-family: monospace; color: #64748b; border-top: 1px solid rgba(62,224,197,0.2); padding-top: 24px; }
    @media print {
      body { background-color: #0b1220 !important; -webkit-print-color-adjust: exact; color-adjust: exact; }
    }

  </style>
</head>
<body>
  <div class="header">
    <div class="title">Trained Data & Stream Report</div>
    <div class="subtitle">SurgeShield Overall Performance Overview</div>
  </div>

  <div class="card">
    <h2>Traffic Decisions</h2>
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-value" style="color: #3b82f6;">${seen.toLocaleString("en-IN")}</div>
        <div class="kpi-label">Total Seen</div>
      </div>
      <div class="kpi">
        <div class="kpi-value" style="color: #10b981;">${ss_approve.toLocaleString("en-IN")}</div>
        <div class="kpi-label">Approved</div>
      </div>
      <div class="kpi">
        <div class="kpi-value" style="color: #f59e0b;">${ss_step.toLocaleString("en-IN")}</div>
        <div class="kpi-label">Step-Up</div>
      </div>
      <div class="kpi">
        <div class="kpi-value" style="color: #ef4444;">${ss_block.toLocaleString("en-IN")}</div>
        <div class="kpi-label">Blocked</div>
      </div>
    </div>
    
    <div style="font-size: 14px; color: #64748b; text-align: center; margin-bottom: 8px;">Decision Distribution</div>
    <div class="bar-chart">
      ${ss_approve > 0 ? `<div class="bar approve" style="width: ${(ss_approve / seen) * 100}%"></div>` : ''}
      ${ss_step > 0 ? `<div class="bar step-up" style="width: ${(ss_step / seen) * 100}%"></div>` : ''}
      ${ss_block > 0 ? `<div class="bar block" style="width: ${(ss_block / seen) * 100}%"></div>` : ''}
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 12px; color: #64748b; margin-top: 8px; font-weight: 500;">
      <span style="color: #10b981;">${Math.round((ss_approve/seen)*100)}% Approved</span>
      <span style="color: #f59e0b;">${Math.round((ss_step/seen)*100)}% Step-Up</span>
      <span style="color: #ef4444;">${Math.round((ss_block/seen)*100)}% Blocked</span>
    </div>
  </div>

  <div class="card">
    <h2>Business Impact vs Static Rules</h2>
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th>SurgeShield AI</th>
          <th>Static Threshold</th>
          <th>Difference</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td style="font-weight: 500; color: #e2e8f0;">Fraud Stopped</td>
          <td style="color: #10b981; font-weight: 600;">₹${ss_fraud_caught_amt.toLocaleString("en-IN")}</td>
          <td>₹${st_fraud_caught_amt.toLocaleString("en-IN")}</td>
          <td style="color: ${(ss_fraud_caught_amt - st_fraud_caught_amt) >= 0 ? '#10b981' : '#ef4444'};">
            ${(ss_fraud_caught_amt - st_fraud_caught_amt) >= 0 ? '+' : ''}₹${(ss_fraud_caught_amt - st_fraud_caught_amt).toLocaleString("en-IN")}
          </td>
        </tr>
        <tr>
          <td style="font-weight: 500; color: #e2e8f0;">Revenue Lost (False Declines)</td>
          <td style="color: #ef4444; font-weight: 600;">₹${ss_legit_blocked_amt.toLocaleString("en-IN")}</td>
          <td>₹${st_legit_blocked_amt.toLocaleString("en-IN")}</td>
          <td style="color: ${(st_legit_blocked_amt - ss_legit_blocked_amt) >= 0 ? '#10b981' : '#ef4444'};">
            ${(st_legit_blocked_amt - ss_legit_blocked_amt) >= 0 ? '+' : ''}₹${(st_legit_blocked_amt - ss_legit_blocked_amt).toLocaleString("en-IN")} saved
          </td>
        </tr>
      </tbody>
    </table>
    
    <div style="margin-top: 24px; padding: 16px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(62,224,197,0.3); border-radius: 8px; border-left: 4px solid #10b981;">
      <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.05em;">Net Financial Benefit</div>
      <div style="font-size: 28px; font-weight: 700; color: #3ee0c5; text-shadow: 0 0 10px rgba(62,224,197,0.5); margin-top: 4px;">₹${(benefit || 0).toLocaleString("en-IN")}</div>
      <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">Total financial gain of SurgeShield AI vs static rules.</div>
    </div>
  </div>

  <div class="footer">
    Generated by SurgeShield Analytics &bull; ${new Date().toLocaleString()}
  </div>
</body>
</html>`);
  popup.document.close();
  setTimeout(() => popup.print(), 500);
}

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

      <Panel 
        title="Stream regime" 
        demo="regime" 
        action={
          <button
            type="button"
            onClick={() => exportTrainedDataReport(totals, analytics, benefit)}
            className="rounded border border-mint px-3 py-1 text-xs text-mint"
          >
            Export training report
          </button>
        }
      >
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

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Friction applied">
          <FrictionBar totals={totals} />
          <p className="mt-2 text-xs text-slate-500">
            Device check and a push are the quieter channels. The rupee comparison still uses the existing OTP catch rate, not a separate rate for each channel.
          </p>
        </Panel>
        <Panel title="Business impact">
          <ul className="space-y-1 text-sm">
            <li className="flex justify-between"><span className="text-slate-400">Fraud stopped</span><span className="num">{money(totals.ss_fraud_caught_amt)}</span></li>
            <li className="flex justify-between"><span className="text-slate-400">Genuine revenue approved</span><span className="num">{money(totals.ss_legit_approved_amt)}</span></li>
            <li className="flex justify-between"><span className="text-slate-400">Lost to false declines</span><span className="num">{money(totals.ss_legit_blocked_amt)}</span></li>
            <li className="flex justify-between"><span className="text-slate-400">Customers approved</span><span className="num">{totals.ss_legit_approved_n ?? 0}</span></li>
            <li className="flex justify-between"><span className="text-slate-400">Customers challenged</span><span className="num">{totals.ss_legit_step_n ?? 0}</span></li>
          </ul>
          <p className="mt-2 text-xs text-slate-500">Only payments that carry a fraud label are counted. Unlabeled live rows stay out of these rupees.</p>
        </Panel>
      </div>

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
