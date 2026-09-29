"use client";

import { useEffect, useState } from "react";
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
