"use client";

import { useState } from "react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../../lib/api";
import { ChartBox, tick } from "../../components/charts";
import { DataTable, KpiTile, Panel, SeverityBadge } from "../../components/ui";

const COLORS = { APPROVE: "#34d399", STEP_UP: "#fbbf24", BLOCK: "#fb7185" };

function share(count, total) {
  if (!total) return "0%";
  return `${Math.round((count / total) * 100)}%`;
}

function scoreBand(bin) {
  const start = Number(bin) / 20;
  return `${start.toFixed(2)}–${(start + 0.05).toFixed(2)}`;
}

function scoreFill(bin) {
  if (bin >= 8) return "#fb7185";
  if (bin >= 4) return "#fbbf24";
  return "#3ee0c5";
}

const FEATURE_MEANING = {
  duplicate: "The same payment showed up again in this window.",
  geometry: "Payments in this cohort are unusually alike.",
  fan_in: "Many cards paid one merchant and they look alike.",
  fan_out: "One account paid many merchants in a short window.",
  card_test: "A burst of tiny amounts crossed many merchants.",
  sequence: "Amounts ramp from probes into larger drains.",
  ood: "This payment sits past the training distance for its segment. Step-up only.",
  wormhole: "One device paid far apart within a minute, under two accounts. Step-up only.",
  device_farm: "Several accounts shared one device in a few minutes.",
  impossible_travel: "The gap between payments is too far for the time between them.",
  auth_flood: "This account had many failed logins in a short window. Step-up only.",
  topology: "A tight group of repeat payers is sharing at most two merchants. Note only, not a step-up.",
  ticket: "The amount is far above this merchant's usual ticket.",
  amount_spike: "The amount jumped past this account's recent pace.",
  velocity_burst: "Payments arrived faster than this account's recent pace.",
  model_score: "The champion score itself stepped the row up or blocked it. No named detector fired.",
  model_probe: "Amounts walked up through the band just under the block line. Step-up only.",
};

const WORKFLOW = [
  "The champion scored each row. A named signal can step a quiet row up. It does not block by itself.",
  "A step-up or block opens a case. The Customer cell links to that case. A file with no customer id uses csv-row-1, csv-row-2, and so on.",
  "Investigate lists those cases, shows the anomaly name on the payment, and keeps reviewing histories while the page is open.",
  "Data, Reports keeps this file next to the installed creditcard report.",
];

function hasColumn(columns, names) {
  const present = new Set((columns || []).map((name) => String(name).toLowerCase()));
  return names.some((name) => present.has(name));
}

function gapsFor(columns) {
  const gaps = [];
  if (!hasColumn(columns, ["lat", "lon", "long"])) gaps.push("Location checks were not available. This file has no lat or lon column.");
  if (!hasColumn(columns, ["device", "device_id"])) gaps.push("Device checks were not available. This file has no device column.");
  if (!hasColumn(columns, ["class", "is_fraud", "label", "eval_label"])) gaps.push("Labelled catch-rate was not available. This file has no Class column.");
  return gaps;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function exportFileReport({ name, scored, summary, truncated, reasons, gaps }) {
  const popup = window.open("", "_blank");
  if (!popup) return;

  const approve = summary.APPROVE || 0;
  const stepUp = summary.STEP_UP || 0;
  const block = summary.BLOCK || 0;
  const total = Math.max(scored, 1);

  const featuresHtml = (reasons || []).map((row) => `
    <tr>
      <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; font-weight: 500; color: #e2e8f0;">${escapeHtml(row.feature)}</td>
      <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; color: #94a3b8; font-variant-numeric: tabular-nums;">${Number(row.count).toLocaleString("en-IN")}</td>
      <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; color: #94a3b8;">${Math.round((row.count / total) * 100)}%</td>
      <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; color: #64748b; font-size: 13px;">${escapeHtml(FEATURE_MEANING[row.feature] || row.feature)}</td>
    </tr>
  `).join("") || "<tr><td colspan='4' style='padding: 12px; color: #64748b; text-align: center;'>No detector fired. Decisions came from the champion score alone.</td></tr>";

  const missingHtml = gaps.map((line) => `<li style="margin-bottom: 8px;">${escapeHtml(line)}</li>`).join("") || "<li>None. Location, device, and label columns are all present.</li>";

  popup.document.write(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(name)} - Analytics Report</title>
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
    <div class="title">File Analytics Report</div>
    <div class="subtitle">Detailed analysis of ${escapeHtml(name)}</div>
  </div>

  <div class="card">
    <h2>Overview</h2>
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-value" style="color: #3b82f6;">${Number(scored).toLocaleString("en-IN")}</div>
        <div class="kpi-label">Rows Scored</div>
      </div>
      <div class="kpi">
        <div class="kpi-value" style="color: #10b981;">${approve.toLocaleString("en-IN")}</div>
        <div class="kpi-label">Approved</div>
      </div>
      <div class="kpi">
        <div class="kpi-value" style="color: #f59e0b;">${stepUp.toLocaleString("en-IN")}</div>
        <div class="kpi-label">Step-Up</div>
      </div>
      <div class="kpi">
        <div class="kpi-value" style="color: #ef4444;">${block.toLocaleString("en-IN")}</div>
        <div class="kpi-label">Blocked</div>
      </div>
    </div>
    
    <div style="font-size: 14px; color: #64748b; text-align: center; margin-bottom: 8px;">Decision Distribution</div>
    <div class="bar-chart">
      ${approve > 0 ? `<div class="bar approve" style="width: ${(approve / total) * 100}%" title="Approve"></div>` : ''}
      ${stepUp > 0 ? `<div class="bar step-up" style="width: ${(stepUp / total) * 100}%" title="Step-Up"></div>` : ''}
      ${block > 0 ? `<div class="bar block" style="width: ${(block / total) * 100}%" title="Block"></div>` : ''}
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 12px; color: #64748b; margin-top: 8px; font-weight: 500;">
      <span style="color: #10b981;">${Math.round((approve/total)*100)}% Approved</span>
      <span style="color: #f59e0b;">${Math.round((stepUp/total)*100)}% Step-Up</span>
      <span style="color: #ef4444;">${Math.round((block/total)*100)}% Blocked</span>
    </div>
  </div>

  <div class="card">
    <h2>Identified Anomalies & Features</h2>
    <table>
      <thead>
        <tr>
          <th>Signal Name</th>
          <th>Occurrences</th>
          <th>% of Traffic</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        ${featuresHtml}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>Data Quality & Gaps</h2>
    <ul>${missingHtml}</ul>
  </div>

  <div class="footer">
    Generated by SurgeShield Analytics &bull; ${new Date().toLocaleString()} &bull; ${truncated ? "Processing was truncated to 2,000 rows." : "Full file processed."}
  </div>
</body>
</html>`);
  popup.document.close();
  setTimeout(() => popup.print(), 500);
}

function ScoreTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-md border border-line bg-[#0b1220] px-2.5 py-1.5 text-xs shadow-lg">
      <p className="text-slate-400">Score {row.band}</p>
      <p className="num text-mint">Payments: {Number(row.count).toLocaleString("en-IN")}</p>
    </div>
  );
}

export default function UploadPage() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");

  async function submit(file) {
    if (!file) return;
    setBusy(true);
    setError("");
    setName(file.name);
    const body = new FormData();
    body.append("file", file);
    try {
      setReport(await api("/score/csv", { method: "POST", body }));
    } catch (err) {
      setReport(null);
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  const summary = report?.summary || {};
  const scored = report?.count || 0;
  const mix = ["APPROVE", "STEP_UP", "BLOCK"].map((decision) => ({
    name: decision,
    value: summary[decision] || 0,
    fill: COLORS[decision],
  }));
  const histogram = (report?.histogram || []).map((row) => ({
    ...row,
    band: scoreBand(row.bin),
    fill: scoreFill(row.bin),
  }));
  const peak = histogram.reduce((best, row) => (row.count > best.count ? row : best), { count: 0, band: "" });
  const labels = report?.labels || {};
  const gaps = gapsFor(report?.columns);

  return (
    <div className="space-y-4">
      <Panel title="Score a transaction file">
        <p className="max-w-3xl text-sm text-slate-400">
          Drop a CSV. Each row is scored by the live champion, the same path as checkout. Columns: Time, Amount, V1 to V28.
          Optional: user_id, merchant_id, Class, region, lat, lon, device, category. The first 2,000 rows are scored even if the file is larger. Raw ids are tokenized and not stored.
        </p>
        <label
          className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-line bg-white/5 px-6 py-10 text-center"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            submit(event.dataTransfer.files?.[0]);
          }}
        >
          <span className="text-sm text-slate-200">{busy ? "Scoring…" : name || "Choose a CSV"}</span>
          <span className="mt-1 text-xs text-slate-500">or drop it here</span>
          <input
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            disabled={busy}
            onChange={(event) => submit(event.target.files?.[0])}
          />
        </label>
        {error && <p className="mt-3 text-sm text-ember">{error}</p>}
        {report && <p className="mt-3 text-xs text-slate-500">Saved under Data, Reports.</p>}
      </Panel>

      {report && (
        <>
          <Panel
            title="File report"
            action={
              <button
                type="button"
                onClick={() => exportFileReport({ name: name || "upload.csv", scored, summary, truncated: report.truncated, reasons: report.reasons, gaps })}
                className="rounded border border-mint px-3 py-1 text-xs text-mint"
              >
                Export this report
              </button>
            }
          >
            <p className="text-sm text-slate-300">
              <span className="text-slate-100">{name || "upload.csv"}</span> scored{" "}
              <span className="num">{scored.toLocaleString("en-IN")}</span> rows
              {report.truncated ? ", stopped at 2,000" : ""}. Approve {summary.APPROVE || 0}, step-up {summary.STEP_UP || 0}, block {summary.BLOCK || 0}.
            </p>
            <h3 className="mt-4 text-xs uppercase tracking-wide text-slate-500">Features that fired on this file</h3>
            {(report.reasons || []).length === 0 ? (
              <p className="mt-2 text-sm text-slate-400">No detector fired. Decisions came from the champion score alone.</p>
            ) : (
              <ul className="mt-2 space-y-2 text-sm">
                {report.reasons.map((row) => (
                  <li key={row.feature}>
                    <span className="text-slate-100">{row.feature}</span>
                    <span className="num text-slate-500"> {Number(row.count).toLocaleString("en-IN")}</span>
                    <span className="text-slate-400">. {FEATURE_MEANING[row.feature] || row.feature}</span>
                  </li>
                ))}
              </ul>
            )}
            <h3 className="mt-4 text-xs uppercase tracking-wide text-slate-500">What this file cannot see</h3>
            {gaps.length === 0 ? (
              <p className="mt-2 text-sm text-slate-400">Location, device, and a label column are all present.</p>
            ) : (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-400">
                {gaps.map((line) => <li key={line}>{line}</li>)}
              </ul>
            )}
            <h3 className="mt-4 text-xs uppercase tracking-wide text-slate-500">Workflow</h3>
            <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm text-slate-300">
              {WORKFLOW.map((line) => <li key={line}>{line}</li>)}
            </ol>
          </Panel>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiTile label="Scored" value={report.count} hint={report.truncated ? "Stopped at 2,000 rows" : `${report.skipped} skipped`} />
            <KpiTile label="Approved" value={summary.APPROVE || 0} hint={money(report.amounts?.APPROVE)} />
            <KpiTile label="Step-up" value={summary.STEP_UP || 0} hint={money(report.amounts?.STEP_UP)} />
            <KpiTile label="Blocked" value={summary.BLOCK || 0} hint={money(report.amounts?.BLOCK)} />
          </section>
          {labels.fraud + labels.legit > 0 && (
            <p className="text-sm text-slate-400">
              Labelled rows: {labels.fraud_caught} of {labels.fraud} fraud challenged, {labels.legit_blocked} of {labels.legit} genuine buyers blocked.
            </p>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Decisions">
              <div className="flex h-3 overflow-hidden rounded-full bg-white/5">
                {mix.map((row) => (
                  row.value > 0 ? (
                    <div key={row.name} style={{ width: `${(row.value / Math.max(scored, 1)) * 100}%`, background: row.fill }} title={`${row.name} ${row.value}`} />
                  ) : null
                ))}
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2">
                {mix.map((row) => (
                  <div key={row.name} className="rounded-md border border-line px-3 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">{row.name}</p>
                    <p className="num text-lg" style={{ color: row.fill }}>{row.value.toLocaleString("en-IN")}</p>
                    <p className="num text-[11px] text-slate-500">{share(row.value, scored)} of scored</p>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel title="Score distribution">
              {peak.count > 0 && (
                <p className="mb-2 text-xs text-slate-400">
                  <span className="num text-slate-200">{peak.count.toLocaleString("en-IN")}</span> payments sit in score {peak.band}.
                </p>
              )}
              <ChartBox>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={histogram}>
                    <CartesianGrid stroke="#1c2740" vertical={false} />
                    <XAxis dataKey="band" tick={tick} stroke="#64748b" interval={3} />
                    <YAxis tick={tick} stroke="#64748b" width={36} allowDecimals={false} />
                    <Tooltip content={<ScoreTip />} cursor={false} />
                    <Bar dataKey="count" name="Payments" radius={[3, 3, 0, 0]}>
                      {histogram.map((row) => <Cell key={row.bin} fill={row.fill} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartBox>
              <p className="mt-2 text-[11px] text-slate-500">Each bar is a 0.05 slice of the champion score. Mint is under 0.20, amber is 0.20–0.40, red is 0.40 and above.</p>
            </Panel>
          </div>
          <Panel title="Signals that fired">
            {(report.reasons || []).length === 0 ? (
              <p className="text-sm text-slate-500">No detector chips on this file. Decisions came from the champion score alone.</p>
            ) : (
              <ul className="space-y-3">
                {report.reasons.map((row) => (
                  <li key={row.feature}>
                    <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                      <span className="text-slate-200">{row.feature}</span>
                      <span className="num text-xs text-slate-400">
                        {Number(row.count).toLocaleString("en-IN")} · {share(row.count, scored)}
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/5">
                      <div className="h-full rounded-full bg-amber" style={{ width: `${Math.max(2, (row.count / Math.max(scored, 1)) * 100)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="First rows" action={<Link href="/investigate" className="text-xs text-mint">Open cases</Link>}>
            <DataTable
              rows={report.decisions || []}
              rowKey={(row) => row.id}
              columns={[
                { key: "id", label: "Id", render: (row) => <span className="num">{row.id}</span> },
                { key: "decision", label: "Decision", render: (row) => <SeverityBadge value={row.decision} /> },
                { key: "risk", label: "Risk", render: (row) => <span className="num">{row.risk_100}</span> },
                { key: "amount", label: "Amount", render: (row) => money(row.amount) },
                { key: "regime", label: "Regime", render: (row) => row.regime },
                {
                  key: "who",
                  label: "Customer",
                  render: (row) => row.user_token ? <Link className="text-mint" href={`/investigate/user/${row.user_token}`}>…{row.user_token.slice(-6)}</Link> : "—",
                },
                {
                  key: "why",
                  label: "Reason",
                  render: (row) => (
                    <span className="text-xs text-slate-400" title={row.reason || ""}>
                      {(row.features || []).filter(Boolean).join(", ") || row.reason || "model score"}
                    </span>
                  ),
                },
              ]}
            />
          </Panel>
        </>
      )}
    </div>
  );
}
