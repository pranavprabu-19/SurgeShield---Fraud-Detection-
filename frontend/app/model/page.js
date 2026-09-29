"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../lib/api";
import { Panel, Skeleton } from "../../components/ui";

export default function ModelPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [bench, setBench] = useState(null);
  const [cut, setCut] = useState(0.2);

  useEffect(() => {
    api("/metrics").then((body) => {
      setData(body);
      setCut(body.thresholds?.t_block || 0.2);
    }).catch((err) => setError(String(err)));
  }, []);

  const point = useMemo(() => nearest(data?.pr_curve || [], cut), [data, cut]);

  if (error) return <p className="text-ember">{error}</p>;
  if (!data) return <Skeleton className="h-40" />;
  const test = data.test || {};
  const rates = data.test_at_block_threshold || {};
  const champion = data.champion_kind === "linear" ? data.logreg_baseline_test : data.lightgbm_raw_test;
  const shadow = data.champion_kind === "linear" ? data.lightgbm_raw_test : data.logreg_baseline_test;

  return (
    <div className="space-y-4">
      <Panel title="Held-out test.csv, scored once">
        <h1 className="text-2xl font-semibold">Accuracy is the wrong score</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-400">
          Approving every transaction scores {((test.always_legit_accuracy || 0) * 100).toFixed(2)}% accuracy and stops no fraud.
          The operating point is precision, recall at a 0.1% false-positive rate, and rupees.
        </p>
      </Panel>
      <section className="grid gap-3 md:grid-cols-4">
        <Metric label="PR-AUC" value={test.pr_auc?.toFixed(3)} />
        <Metric label="ROC-AUC" value={test.roc_auc?.toFixed(3)} />
        <Metric label="Recall at 0.1% FPR" value={test.recall_at_0_1pct_fpr?.toFixed(3)} />
        <Metric label="Precision at block" value={rates.precision?.toFixed(3)} />
      </section>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Precision-recall curve">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.pr_curve || []}>
                <XAxis dataKey="recall" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} domain={[0, 1]} />
                <Tooltip />
                <Line dataKey="precision" stroke="#3ee0c5" dot={false} />
                {point && <ReferenceLine x={point.recall} stroke="#fbbf24" />}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-500">
            Cuts: step-up {data.thresholds?.t_step?.toFixed(3)}, block {data.thresholds?.t_block?.toFixed(3)}, static {data.thresholds?.t_static?.toFixed(3)}.
          </p>
        </Panel>
        <Panel title="Threshold what-if">
          <input type="range" min="0.05" max="0.95" step="0.01" value={cut} onChange={(event) => setCut(Number(event.target.value))} className="w-full" />
          <p className="num mt-3 text-sm">Cut {cut.toFixed(2)}</p>
          <p className="mt-2 text-sm text-slate-300">Precision {point?.precision ?? "—"} · Recall {point?.recall ?? "—"}</p>
          <p className="mt-2 text-xs text-slate-500">Read from the stored curve. It does not retrain or change the live thresholds.</p>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-slate-500">Champion (calibrated logistic regression)</p>
              <p className="num text-2xl">{champion?.pr_auc?.toFixed(3)}</p>
            </div>
            <div>
              <p className="text-slate-500">Shadow LightGBM</p>
              <p className="num text-2xl">{shadow?.pr_auc?.toFixed(3)}</p>
            </div>
          </div>
        </Panel>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Calibration">
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.calibration || []}>
                <XAxis dataKey="mean_score" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} domain={[0, 1]} />
                <Tooltip />
                <Line dataKey="fraud_rate" stroke="#38bdf8" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Global feature importance">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.feature_importance || []} layout="vertical">
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="feature" stroke="#64748b" fontSize={10} width={90} />
                <Tooltip />
                <Bar dataKey="coef" fill="#3ee0c5" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
      <Panel title="Latency benchmark">
        <button className="rounded border border-mint px-3 py-1.5 text-sm" onClick={() => api("/benchmark?n=220").then(setBench)}>
          Run explain-off benchmark
        </button>
        {bench && (
          <>
            <p className="mt-3 text-sm">{bench.n} payments at {bench.tps}/s. p50 {bench.p50_ms} ms, p99 {bench.p99_ms} ms.</p>
            <div className="mt-3 h-32">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={hist(bench.latencies_ms || [])}>
                  <XAxis dataKey="ms" stroke="#64748b" fontSize={10} />
                  <YAxis hide />
                  <Tooltip />
                  <Bar dataKey="count" fill="#34d399" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Offline test cost is not a flash sale. SurgeShield {data.test_cost_surgeshield?.total_cost?.toFixed(0)} versus static {data.test_cost_static?.total_cost?.toFixed(0)}. The rupee gap shows up in the simulator.
        </p>
      </Panel>
      <SkillsPanel />
      <AdaptPanel />
    </div>
  );
}

function SkillsPanel() {
  const [body, setBody] = useState(null);
  useEffect(() => {
    api("/skills").then(setBody).catch(() => {});
  }, []);
  const skills = body?.skills || [];
  const families = [...new Set(skills.map((skill) => skill.family))];
  return (
    <Panel title="Anomaly skills">
      <p className="text-sm text-slate-400">{body?.rule || "Loading skills."}</p>
      {families.map((family) => (
        <div key={family} className="mt-4">
          <p className="text-[11px] uppercase text-slate-500">{family}</p>
          <ul className="mt-2 space-y-2 text-sm">
            {skills.filter((skill) => skill.family === family).map((skill) => (
              <li key={skill.id} className="grid gap-1 border-t border-white/5 pt-2 md:grid-cols-[12rem_6rem_1fr]">
                <span>{skill.name}</span>
                <span className={skill.status === "unavailable" ? "text-slate-500" : "text-mint"}>{skill.status}</span>
                <span className="text-slate-400">{skill.sees} {skill.action}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </Panel>
  );
}

function AdaptPanel() {
  const [body, setBody] = useState(null);
  useEffect(() => {
    api("/adapt").then(setBody).catch(() => {});
  }, []);
  const offsets = body?.offsets || {};
  return (
    <Panel title="Adaptive thresholds">
      <p className="text-sm text-slate-400">Analyst releases loosen a segment by at most 0.03. Upholds tighten it by the same cap. The kill switch still overrides the model.</p>
      <p className="num mt-2 text-sm">Feedback rows {body?.feedback ?? 0}. Cap ±{body?.cap ?? 0.03}.</p>
      <ul className="mt-2 text-sm">
        {Object.keys(offsets).length === 0 && <li className="text-slate-500">No segment has four labelled reviews yet.</li>}
        {Object.entries(offsets).map(([segment, offset]) => (
          <li key={segment}>Segment {segment}: {offset > 0 ? "+" : ""}{offset}</li>
        ))}
      </ul>
    </Panel>
  );
}

function Metric({ label, value }) {
  return (
    <div className="panel p-3">
      <p className="text-[11px] uppercase text-slate-500">{label}</p>
      <p className="num mt-1 text-2xl">{value ?? "—"}</p>
    </div>
  );
}

function nearest(points, cut) {
  if (!points.length) return null;
  return points.reduce((best, point) =>
    Math.abs(point.threshold - cut) < Math.abs(best.threshold - cut) ? point : best
  );
}

function hist(values) {
  const bins = Array.from({ length: 16 }, (_, index) => ({ ms: index, count: 0 }));
  values.forEach((value) => {
    bins[Math.min(15, Math.floor(value))] .count += 1;
  });
  return bins;
}
