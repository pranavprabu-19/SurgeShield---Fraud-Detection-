"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../../lib/api";
import { useStream } from "../../lib/stream";
import { REAL } from "../../lib/scenarios";
import { EmptyState, Panel, Skeleton } from "../../components/ui";

const BADGE = {
  real: "border-ok/50 text-ok",
  simulated: "border-amber/50 text-amber",
  unavailable: "border-line text-slate-500",
};

function badgeFor(value) {
  if (value === "real") return BADGE.real;
  if (value === "simulated") return BADGE.simulated;
  if (String(value).startsWith("real")) return BADGE.real;
  return BADGE.unavailable;
}

const DECISION_COLOR = { APPROVE: "#34d399", STEP_UP: "#fbbf24", BLOCK: "#fb7185" };

function share(count, total) {
  if (!total || !count) return "0%";
  const pct = (count / total) * 100;
  if (pct < 1) return "<1%";
  return `${Math.round(pct)}%`;
}

function peakBand(histogram) {
  const best = (histogram || []).reduce((winner, row) => (row.count > winner.count ? row : winner), { count: 0, bin: 0 });
  if (!best.count) return null;
  const start = Number(best.bin) / 20;
  return { count: best.count, band: `${start.toFixed(2)}–${(start + 0.05).toFixed(2)}` };
}

function clock(seconds) {
  if (!seconds) return "";
  return new Date(seconds * 1000).toLocaleString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" });
}

function ScoreReadout({ score }) {
  if (!score) return <p className="text-sm text-slate-500">No test file to score.</p>;
  const total = score.count || 0;
  const summary = score.summary || {};
  const mix = ["APPROVE", "STEP_UP", "BLOCK"].map((name) => ({ name, value: summary[name] || 0 }));
  const peak = peakBand(score.histogram);
  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Scored <span className="num text-slate-300">{total.toLocaleString("en-IN")}</span>
        {score.truncated ? " · first 2,000 rows" : ""}
        {score.scored_at ? ` · ${clock(score.scored_at)}` : ""}
      </p>
      <div className="flex h-2 overflow-hidden rounded-full bg-white/5">
        {mix.map((row) => (
          row.value > 0 ? <div key={row.name} style={{ width: `${(row.value / Math.max(total, 1)) * 100}%`, background: DECISION_COLOR[row.name] }} /> : null
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {mix.map((row) => (
          <div key={row.name}>
            <p className="text-[10px] uppercase text-slate-500">{row.name}</p>
            <p className="num text-sm" style={{ color: DECISION_COLOR[row.name] }}>{row.value.toLocaleString("en-IN")}</p>
            <p className="num text-[11px] text-slate-500">{share(row.value, total)}</p>
          </div>
        ))}
      </div>
      {peak && (
        <p className="text-xs text-slate-400">
          <span className="num text-slate-200">{peak.count.toLocaleString("en-IN")}</span> payments sit in score {peak.band}.
        </p>
      )}
      {(score.reasons || []).length === 0 ? (
        <p className="text-xs text-slate-500">No detector chips. Decisions came from the champion score alone.</p>
      ) : (
        <ul className="space-y-2">
          {score.reasons.map((row) => (
            <li key={row.feature}>
              <div className="mb-1 flex justify-between text-xs">
                <span className="text-slate-200">{row.feature}</span>
                <span className="num text-slate-400">{Number(row.count).toLocaleString("en-IN")} · {share(row.count, total)}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                <div className="h-full rounded-full bg-amber" style={{ width: `${Math.max(2, (row.count / Math.max(total, 1)) * 100)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function exportReports(reports) {
  const popup = window.open("", "_blank");
  if (!popup) return;
  const uploadBlocks = (reports.uploads || []).map((row) => {
    const summary = row.summary || {};
    const signals = (row.reasons || []).map((signal) => `${signal.feature} ${signal.count}`).join(", ") || "none";
    return `<h2>${escapeHtml(row.name)}</h2><p>Uploaded ${escapeHtml(clock(row.scored_at))}. Scored ${row.count}. Approve ${summary.APPROVE || 0}, step-up ${summary.STEP_UP || 0}, block ${summary.BLOCK || 0}. Signals: ${escapeHtml(signals)}.</p>`;
  }).join("") || "<p>No uploaded files.</p>";
  const installedBlocks = (reports.installed || []).map((row) => {
    const score = row.score || {};
    const summary = score.summary || {};
    const signals = (score.reasons || []).map((signal) => `${signal.feature} ${signal.count}`).join(", ") || "none";
    const extra = [
      row.rows ? `${row.rows.train} train, ${row.rows.test} test` : "",
      row.fraud_rate != null ? `fraud rate ${(row.fraud_rate * 100).toFixed(2)}%` : "",
      row.pr_auc != null ? `PR-AUC ${Number(row.pr_auc).toFixed(3)}` : "",
    ].filter(Boolean).join(". ");
    return `<h2>${escapeHtml(row.name)}</h2><p>${escapeHtml(row.source)}. ${escapeHtml(extra)}. Scored ${score.count || 0}. Approve ${summary.APPROVE || 0}, step-up ${summary.STEP_UP || 0}, block ${summary.BLOCK || 0}. Signals: ${escapeHtml(signals)}.</p>`;
  }).join("");
  popup.document.write(`<!doctype html><title>SurgeShield dataset reports</title><body style="font-family:sans-serif;padding:32px"><h1>Dataset reports</h1><h2>Uploaded files</h2>${uploadBlocks}<h2>Installed datasets</h2>${installedBlocks}</body>`);
  popup.document.close();
  popup.print();
}

const CREDITCARD_COVERAGE = {
  "customer history and cases": "simulated",
  "merchant leaderboard and fan-in": "simulated",
  "map of payment locations": "simulated",
  "impossible travel": "simulated",
  "device farm": "simulated",
  "category risk": "simulated",
  "merchant ticket ratio": "simulated",
  "fairness report": "unavailable",
  "checkout telemetry (human score)": "simulated",
};

export default function DataPage() {
  const stream = useStream();
  const [body, setBody] = useState(null);
  const [reports, setReports] = useState(null);
  const [reportsError, setReportsError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function load() {
    try {
      setBody(await api("/datasets"));
      setError("");
    } catch (err) {
      setError(String(err));
    }
  }

  useEffect(() => {
    load();
    api("/reports")
      .then((payload) => {
        setReports(payload);
        setReportsError("");
      })
      .catch((err) => setReportsError(String(err.message || err)));
  }, []);

  async function activate(name) {
    setBusy(name);
    try {
      await api("/datasets/activate", { method: "POST", body: JSON.stringify({ name, note: "activated from the Data page" }) });
      stream.toast(`${name} is now the live model and replay source`);
      await load();
    } catch (err) {
      stream.toast(String(err));
    } finally {
      setBusy("");
    }
  }

  if (error) return <p className="text-ember">{error}</p>;
  if (!body) return <Skeleton className="h-40" />;
  const rows = body.datasets || [];

  return (
    <div className="space-y-4">
      <Panel title="Datasets">
        <p className="mb-3 text-sm text-slate-400">
          Live model: <span className="text-mint">{body.loaded}</span>. Replay source: <span className="text-mint">{body.active}</span>.
          Activating reloads the model under the scoring lock, resets the stream, and writes the change to the audit chain.
        </p>
        <div className="flex flex-wrap gap-2">
          {REAL.map((item) => (
            <button key={item.id} onClick={() => stream.launch(item.id)} className="rounded-full border border-line bg-panel px-3 py-1.5 text-sm hover:border-mint">
              {item.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          Replay plays the active test file in time order with the clock compressed. Peak plays its busiest hour at real pace.
        </p>
      </Panel>

      <Panel
        title="Reports"
        action={
          <button
            type="button"
            disabled={!reports}
            onClick={() => exportReports(reports)}
            className="rounded border border-mint px-3 py-1 text-xs text-mint disabled:opacity-40"
          >
            Export report
          </button>
        }
      >
        {reportsError && <p className="text-sm text-ember">{reportsError}</p>}
        {!reports && !reportsError && <p className="text-sm text-slate-500">Scoring the installed test files…</p>}
        {reports && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-3">
              <h3 className="text-xs uppercase tracking-wide text-slate-500">Uploaded files</h3>
              {(reports.uploads || []).length === 0 ? (
                <p className="text-sm text-slate-500">No uploads yet. Score a CSV on <Link href="/upload" className="text-mint">Upload</Link>.</p>
              ) : (
                reports.uploads.map((row) => (
                  <div key={`${row.name}-${row.scored_at}`} className="rounded border border-line p-3">
                    <p className="text-sm text-slate-200">{row.name}</p>
                    <ScoreReadout score={row} />
                  </div>
                ))
              )}
            </div>
            <div className="space-y-3">
              <h3 className="text-xs uppercase tracking-wide text-slate-500">Already installed</h3>
              {(reports.installed || []).map((row) => (
                <div key={row.name} className="rounded border border-line p-3">
                  <p className="text-sm text-slate-200">{row.name}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {row.source}
                    {row.rows ? ` · ${row.rows.train} train · ${row.rows.test} test` : ""}
                    {row.fraud_rate != null ? ` · fraud ${(row.fraud_rate * 100).toFixed(2)}%` : ""}
                    {row.pr_auc != null ? ` · PR-AUC ${Number(row.pr_auc).toFixed(3)}` : ""}
                  </p>
                  <div className="mt-2">
                    <ScoreReadout score={row.score} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Panel>

      {rows.length === 0 && <EmptyState title="No datasets found" />}

      {rows.map((row) => {
        const report = row.report || {};
        const coverage = report.coverage || (row.name === "creditcard" ? CREDITCARD_COVERAGE : {});
        const metrics = row.metrics?.test || {};
        const active = body.loaded === row.name;
        return (
          <Panel
            key={row.name}
            title={row.name}
            action={
              <button
                disabled={active || !row.has_model || Boolean(busy)}
                onClick={() => activate(row.name)}
                className="rounded border border-mint px-3 py-1 text-xs text-mint disabled:opacity-40"
                title={row.has_model ? "" : `Train first: SURGESHIELD_DATASET=${row.name} python -m ml.train`}
              >
                {active ? "Active" : busy === row.name ? "Loading…" : row.has_model ? "Activate" : "Not trained"}
              </button>
            }
          >
            <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
              <div className="space-y-2 text-sm">
                {report.rows ? (
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                    <dt className="text-slate-500">Source</dt><dd>{report.source}</dd>
                    <dt className="text-slate-500">Detected as</dt><dd>{report.detected || "custom mapping"}</dd>
                    <dt className="text-slate-500">Rows</dt><dd className="num">{report.rows.train} train · {report.rows.test} test</dd>
                    <dt className="text-slate-500">Fraud rate</dt><dd className="num">{(report.fraud_rate * 100).toFixed(2)}%</dd>
                    <dt className="text-slate-500">Time span</dt><dd className="num">{report.time_span_days} days</dd>
                    <dt className="text-slate-500">Split</dt><dd>{report.split}</dd>
                    <dt className="text-slate-500">Duplicates</dt><dd className="num">{report.duplicates_dropped}</dd>
                  </dl>
                ) : (
                  <p className="text-slate-400">Built-in anonymised card file (PCA features V1 to V28). No ids, cities, or devices, so those features are simulated.</p>
                )}
                {report.dropped && (
                  <div className="text-xs text-slate-400">
                    {Object.entries(report.dropped).filter(([, cols]) => cols.length).map(([kind, cols]) => (
                      <p key={kind}><span className="text-slate-500">Dropped ({kind}):</span> {cols.join(", ")}</p>
                    ))}
                  </div>
                )}
                {report.model_features && (
                  <p className="text-xs text-slate-400"><span className="text-slate-500">Model inputs:</span> {report.model_features.join(", ") || "derived only"}</p>
                )}
                <div className="grid grid-cols-3 gap-2 pt-1">
                  <div className="panel-raised p-2"><p className="text-[10px] uppercase text-slate-500">PR-AUC</p><p className="num">{metrics.pr_auc != null ? Number(metrics.pr_auc).toFixed(3) : "—"}</p></div>
                  <div className="panel-raised p-2"><p className="text-[10px] uppercase text-slate-500">ROC-AUC</p><p className="num">{metrics.roc_auc != null ? Number(metrics.roc_auc).toFixed(3) : "—"}</p></div>
                  <div className="panel-raised p-2"><p className="text-[10px] uppercase text-slate-500">Champion</p><p className="text-xs">{row.metrics?.champion_kind || "—"}</p></div>
                </div>
              </div>
              <table className="w-full text-left text-sm">
                <thead className="text-[11px] uppercase text-slate-500">
                  <tr><th className="py-1">Feature</th><th>Runs on</th></tr>
                </thead>
                <tbody>
                  {Object.entries(coverage).map(([feature, value]) => (
                    <tr key={feature} className="border-t border-line">
                      <td className="py-1.5">{feature}</td>
                      <td><span className={`rounded border px-1.5 py-0.5 text-[11px] ${badgeFor(value)}`}>{value}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        );
      })}

      <Panel title="Import your own file">
        <pre className="overflow-auto rounded bg-ink p-3 text-xs text-slate-300">{`PYTHONPATH=. .venv/bin/python -m ml.import_dataset --path fraudTrain.csv --test fraudTest.csv
PYTHONPATH=. .venv/bin/python -m ml.import_dataset --path upi.csv --name upi_bank \\
  --map time=txn_ts,amount=amt,label=fraud,user=payer_vpa,merchant=payee_vpa,city=city,lat=lat,lon=lon,device=device_id,category=mcc
SURGESHIELD_DATASET=upi_bank PYTHONPATH=. .venv/bin/python -m ml.train`}</pre>
        <p className="mt-2 text-[11px] text-slate-500">
          Names, streets, jobs, and transaction numbers are dropped on import. Card numbers and VPAs stay only as keys and are tokenized at scoring time.
          Any column that predicts the label by itself (AUC above 0.98) is treated as a leak and dropped.
        </p>
      </Panel>
    </div>
  );
}
