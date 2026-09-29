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
  const features = (reasons || []).map((row) => `<li><strong>${escapeHtml(row.feature)}</strong> ${Number(row.count).toLocaleString("en-IN")}. ${escapeHtml(FEATURE_MEANING[row.feature] || row.feature)}</li>`).join("") || "<li>No detector fired. Decisions came from the champion score alone.</li>";
  const missing = gaps.map((line) => `<li>${escapeHtml(line)}</li>`).join("") || "<li>None.</li>";
  const steps = WORKFLOW.map((line) => `<li>${escapeHtml(line)}</li>`).join("");
  popup.document.write(`<!doctype html><title>${escapeHtml(name)} report</title><body style="font-family:sans-serif;padding:32px;max-width:720px"><h1>File report</h1><p>${escapeHtml(name)} scored ${Number(scored).toLocaleString("en-IN")} rows${truncated ? ", stopped at 2,000" : ""}. Approve ${summary.APPROVE || 0}, step-up ${summary.STEP_UP || 0}, block ${summary.BLOCK || 0}.</p><h2>Features that fired</h2><ul>${features}</ul><h2>What this file cannot see</h2><ul>${missing}</ul><h2>Workflow</h2><ol>${steps}</ol></body>`);
  popup.document.close();
  popup.print();
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
