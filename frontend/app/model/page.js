"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../lib/api";
import { LivePayments, ModelCompare } from "../../components/compare";
import { Panel, Skeleton } from "../../components/ui";
import { useStream } from "../../lib/stream";

export default function ModelPage() {
  const stream = useStream();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [bench, setBench] = useState(null);
  const [cut, setCut] = useState(0.2);
  const [picked, setPicked] = useState(null);

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
      <ModelCompare selected={picked || stream.feed[0]} />
      <Panel title="Last 20 scored">
        <p className="mb-2 text-xs text-slate-500">From the live socket. Held-out curves above do not move with this list.</p>
        <LivePayments rows={stream.feed} onPick={setPicked} empty="No payments yet. Run a sale or upload a file." />
      </Panel>
      <TaxonomyPanel />
      <SkillsPanel />
      <AdaptPanel />
    </div>
  );
}

const GROUPS = ["Anomaly types", "Entry", "Identity", "Persistence", "Infrastructure", "Fraud", "Insider", "Physical", "Impact"];
const BADGE = {
  live: "bg-mint/15 text-mint",
  partial: "bg-amber/15 text-amber",
  "needs data": "bg-white/5 text-slate-400",
};

function CoverageRow({ item }) {
  return (
    <li className="border-t border-white/5 py-2">
      <div className="flex items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${BADGE[item.status] || BADGE["needs data"]}`}>{item.status}</span>
        <span className="text-sm">{item.name}</span>
      </div>
      <p className="mt-1 text-xs text-slate-400">{item.basis}</p>
      {item.file && item.status === "needs data" && <p className="mt-1 text-xs text-slate-500">{item.file}</p>}
    </li>
  );
}

function TaxonomyPanel() {
  const [body, setBody] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [openHidden, setOpenHidden] = useState({});
  useEffect(() => {
    api("/taxonomy").then(setBody).catch(() => {});
  }, []);
  const counts = body?.counts || {};
  const needle = query.trim().toLowerCase();
  const items = (body?.items || []).filter((item) => {
    if (filter !== "all" && item.status !== filter) return false;
    if (!needle) return true;
    return `${item.name} ${item.basis} ${item.file || ""}`.toLowerCase().includes(needle);
  });
  const tiles = [
    ["live", "Live", counts.live || 0],
    ["partial", "Partial", counts.partial || 0],
    ["needs data", "Needs data", counts["needs data"] || 0],
  ];
  return (
    <Panel title="Coverage">
      <p className="text-sm text-slate-400">{body?.note}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {tiles.map(([status, label, count]) => (
          <button key={status} type="button" onClick={() => setFilter(filter === status ? "all" : status)} className={`rounded border px-3 py-2 text-left ${filter === status ? "border-mint" : "border-line"}`}>
            <p className="num text-2xl">{count}</p>
            <p className="text-xs uppercase text-slate-500">{label}</p>
          </button>
        ))}
      </div>
      <input
        className="mt-3 w-full rounded border border-line bg-transparent px-3 py-2 text-sm"
        placeholder="Search coverage"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="mt-3 max-h-[32rem] space-y-3 overflow-auto">
        {GROUPS.map((group) => {
          const rows = items.filter((item) => item.group === group);
          if (!rows.length) return null;
          const hidden = rows.filter((item) => item.status === "needs data");
          const shown = filter === "needs data" ? rows : rows.filter((item) => item.status !== "needs data");
          const bar = ["live", "partial", "needs data"].map((status) => rows.filter((item) => item.status === status).length);
          return (
            <div key={group} className="rounded border border-line p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm">{group}</p>
                <p className="text-[11px] text-slate-500">{bar[0]} live · {bar[1]} partial · {bar[2]} needs data</p>
              </div>
              <div className="mt-2 flex h-1.5 overflow-hidden rounded bg-white/5">
                <div className="bg-mint" style={{ width: `${rows.length ? (bar[0] / rows.length) * 100 : 0}%` }} />
                <div className="bg-amber" style={{ width: `${rows.length ? (bar[1] / rows.length) * 100 : 0}%` }} />
                <div className="bg-slate-600" style={{ width: `${rows.length ? (bar[2] / rows.length) * 100 : 0}%` }} />
              </div>
              <ul>{shown.map((item) => <CoverageRow key={item.name} item={item} />)}</ul>
              {filter !== "needs data" && hidden.length > 0 && (
                <div className="mt-2">
                  <button type="button" className="text-xs text-slate-400" onClick={() => setOpenHidden((prev) => ({ ...prev, [group]: !prev[group] }))}>
                    {openHidden[group] ? "Hide" : "Show"} what this stream cannot see ({hidden.length})
                  </button>
                  {openHidden[group] && <ul>{hidden.map((item) => <CoverageRow key={item.name} item={item} />)}</ul>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

const SKILL_FLAG = {
  ood: "ood",
  topology: "topology",
  wormhole: "wormhole",
  model_probe: "model_probe",
  amount_spike: "amount_spike",
  velocity_burst: "velocity_burst",
  auth_flood: "auth_flood",
  input_syntax: "suspicious_syntax",
};

function SkillsPanel() {
  const stream = useStream();
  const [body, setBody] = useState(null);
  useEffect(() => {
    api("/skills").then(setBody).catch(() => {});
  }, []);
  const skills = body?.skills || [];
  const fires = {};
  stream.feed.forEach((row) => {
    const profile = row.profile || {};
    Object.entries(SKILL_FLAG).forEach(([skill, flag]) => {
      if (profile[flag]) fires[skill] = (fires[skill] || 0) + 1;
    });
    if (profile.device_farm || profile.impossible_travel || profile.device_new || profile.hour_unusual) {
      fires.login_context = (fires.login_context || 0) + 1;
    }
  });
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
                <span className={skill.status === "unavailable" ? "text-slate-500" : "text-mint"}>{skill.status}{fires[skill.id] ? ` · ${fires[skill.id]} live` : ""}</span>
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
