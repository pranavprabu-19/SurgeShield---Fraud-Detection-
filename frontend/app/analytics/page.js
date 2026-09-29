"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, money } from "../../lib/api";
import { ChartBox, Tip, tick } from "../../components/charts";
import { LivePayments, ModelCompare } from "../../components/compare";
import { ScenarioBar, TransactionDrawer } from "../../components/console";
import { EmptyState, Panel, Skeleton } from "../../components/ui";
import { useStream } from "../../lib/stream";

const GRID = "#1c2740";
const ANOMALIES = ["ood", "wormhole", "device_farm", "velocity_burst", "model_probe", "auth_flood", "topology"];

export default function AnalyticsPage() {
  const stream = useStream();
  const [data, setData] = useState(null);
  const [redteam, setRedteam] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");
  const [replay, setReplay] = useState(null);
  const [replaying, setReplaying] = useState(false);
  const [focus, setFocus] = useState(null);
  const [selected, setSelected] = useState(null);
  const [scale, setScale] = useState(1);
  const [v14, setV14] = useState(0);
  const [copies, setCopies] = useState(1);
  const [morphing, setMorphing] = useState(false);

  useEffect(() => {
    api("/metrics").then(setMetrics).catch(() => {});
    api("/config").then(setConfig).catch(() => {});
    api("/redteam").then(setRedteam).catch(() => {});
  }, []);

  useEffect(() => {
    let stop = false;
    async function tickLive() {
      try {
        const body = await api("/analytics");
        if (!stop) setData(body);
      } catch (err) {
        if (!stop) setError(String(err));
      }
    }
    tickLive();
    const timer = setInterval(tickLive, 2000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  if (error) return <p className="text-ember">{error}</p>;
  if (!data && !metrics) return <Skeleton className="h-40" />;

  const totals = data?.totals || {};
  const seen = totals.seen || 0;
  const live = (data?.samples || 0) > 0;
  const waterfall = [
    { name: "Fraud stopped", value: Math.round(totals.ss_fraud_caught_amt || 0) },
    { name: "OTP friction", value: -Math.round(data?.friction_rupees || 0) },
    { name: "Lost legit sales", value: -Math.round(totals.ss_legit_blocked_amt || 0) },
  ];
  const funnel = [
    { name: "Scored", value: seen },
    { name: "Approved", value: totals.ss_approve || 0 },
    { name: "Step-up", value: totals.ss_step || 0 },
    { name: "Blocked", value: totals.ss_block || 0 },
  ];
  const latency = (data?.latency_histogram || []).map((count, ms) => ({ ms: `${ms}`, count }));
  const runs = [
    ...(data?.live_scenario && data.live_scenario !== "idle" ? [{ scenario: `${data.live_scenario} (live)`, totals }] : []),
    ...(data?.scenario_runs || []),
  ];
  const thresholds = config?.thresholds || metrics?.thresholds || {};
  const histogram = (data?.score_histogram || []).map((count, index) => ({
    score: (index / 40).toFixed(2),
    count,
    fill: thresholds.t_block && index / 40 >= thresholds.t_block ? "#fb7185" : thresholds.t_step && index / 40 >= thresholds.t_step ? "#fbbf24" : "#3ee0c5",
  }));
  const anomalyCounts = {};
  ANOMALIES.forEach((name) => {
    anomalyCounts[name] = stream.feed.filter((row) => row.profile?.[name]).length;
  });
  const listed = stream.feed.filter((row) => {
    if (!focus) return true;
    if (focus.kind === "decision") return row.decision === focus.value;
    if (focus.kind === "segment") return row.segment === focus.value;
    if (focus.kind === "anomaly") return Boolean(row.profile?.[focus.value]);
    if (focus.kind === "score") return Number(row.score) >= focus.value && Number(row.score) < focus.value + 0.025;
    if (focus.kind === "cell") return cellMatch(row, focus.value);
    return true;
  });
  const recallRows = (redteam?.summary || []).map((row) => ({
    scenario: String(row.scenario || "").replaceAll("_", " "),
    recall: row.fraud_recall == null ? 0 : Math.round(row.fraud_recall * 100),
    detected: Math.round((row.detected_rate || 0) * 100),
  }));

  async function morph() {
    setMorphing(true);
    setError("");
    try {
      await api("/synthesize", {
        method: "POST",
        body: JSON.stringify({
          id: selected?.id,
          amount_scale: scale,
          v_shift: { V14: v14 },
          copies,
        }),
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setMorphing(false);
    }
  }

  return (
    <div className="space-y-4">
      <ScenarioBar />
      <ModelCompare selected={selected || stream.feed[0]} />
      <Panel title="Morph this payment">
        <p className="text-xs text-slate-500">
          Changes amount and V14 on a real scored row, then the champion scores the copies. It does not retrain and it does not invent login, network, or ATM logs.
          {selected ? ` Source payment ${selected.id}.` : " No row picked, so the last real payment is used."}
        </p>
        <label className="mt-3 block text-xs text-slate-400">Amount scale {scale.toFixed(1)}x
          <input className="ml-2 align-middle" type="range" min="0.5" max="8" step="0.1" value={scale} onChange={(event) => setScale(Number(event.target.value))} />
        </label>
        <label className="mt-2 block text-xs text-slate-400">V14 shift {v14.toFixed(1)}
          <input className="ml-2 align-middle" type="range" min="-5" max="5" step="0.1" value={v14} onChange={(event) => setV14(Number(event.target.value))} />
        </label>
        <label className="mt-2 block text-xs text-slate-400">Copies {copies}
          <input className="ml-2 align-middle" type="range" min="1" max="10" step="1" value={copies} onChange={(event) => setCopies(Number(event.target.value))} />
        </label>
        <button type="button" className="mt-3 rounded border border-mint px-3 py-1 text-sm text-mint disabled:opacity-50" disabled={morphing} onClick={morph}>
          {morphing ? "Scoring…" : "Score copies"}
        </button>
      </Panel>
      <Panel title="Live anomalies">
        <div className="flex flex-wrap gap-2">
          {ANOMALIES.map((name) => (
            <button key={name} type="button" onClick={() => setFocus(focus?.kind === "anomaly" && focus.value === name ? null : { kind: "anomaly", value: name })} className={`rounded border px-2 py-1 text-xs ${focus?.kind === "anomaly" && focus.value === name ? "border-mint text-mint" : "border-line text-slate-400"}`}>
              {name} {anomalyCounts[name]}
            </button>
          ))}
          {focus && <button type="button" className="text-xs text-slate-500 underline" onClick={() => setFocus(null)}>Clear filter</button>}
        </div>
        <div className="mt-3">
          <LivePayments
            rows={listed}
            onPick={setSelected}
            empty={stream.feed.length ? "Nothing in this filter." : "Stream is idle. Run a sale above. Nothing here is invented."}
          />
        </div>
      </Panel>
      <TransactionDrawer selected={selected} onClose={() => setSelected(null)} />
      <Panel title="Held-out precision and recall">
        <p className="mb-3 text-xs text-slate-500">
          This curve is from the trained model on test.csv. It stays on screen when the live stream is idle.
          {metrics?.test?.pr_auc != null && ` PR-AUC ${metrics.test.pr_auc.toFixed(3)}.`}
        </p>
        <ChartBox height={240}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={metrics?.pr_curve || []}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="recall" tick={tick} stroke="#64748b" tickFormatter={(value) => Number(value).toFixed(1)} />
              <YAxis tick={tick} stroke="#64748b" domain={[0, 1]} width={36} />
              <Tooltip content={<Tip />} />
              <Line dataKey="precision" name="Precision" stroke="#3ee0c5" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartBox>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Live score distribution">
          {!live ? (
            <EmptyState title="No live scores yet" detail="Run a sale or upload a file. The curve above is the held-out model." />
          ) : (
            <ChartBox>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histogram}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="score" tick={tick} stroke="#64748b" interval={4} />
                  <YAxis tick={tick} stroke="#64748b" width={32} allowDecimals={false} />
                  <Tooltip content={<Tip />} />
                  <Bar dataKey="count" name="Payments" radius={[3, 3, 0, 0]} onClick={(bar) => setFocus({ kind: "score", value: Number(bar?.score) })}>
                    {histogram.map((bin) => <Cell key={bin.score} fill={bin.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartBox>
          )}
          <p className="mt-2 text-xs text-slate-500">Mint is approve, amber is step-up, red is block.</p>
        </Panel>
        <Panel title="Segment risk">
          <ChartBox>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.segments || []}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="segment" tick={tick} stroke="#64748b" tickFormatter={(value) => `S${value}`} />
                <YAxis tick={tick} stroke="#64748b" domain={[0, 1]} width={32} />
                <Tooltip content={<Tip />} />
                <Bar dataKey="mean_risk" name="Mean risk" fill="#38bdf8" radius={[3, 3, 0, 0]} onClick={(bar) => setFocus({ kind: "segment", value: bar?.segment })} />
                <Bar dataKey="n" name="Payments" fill="#243352" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartBox>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="SurgeShield confusion">
          <Matrix matrix={data?.confusion_surgeshield} positive="Block or step-up" onPick={(cell) => setFocus({ kind: "cell", value: `ss:${cell}` })} />
        </Panel>
        <Panel title="Static threshold confusion">
          <Matrix matrix={data?.confusion_static} positive="Block" onPick={(cell) => setFocus({ kind: "cell", value: `st:${cell}` })} />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Cost waterfall (rupees)">
          <ChartBox>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={waterfall}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="name" tick={tick} stroke="#64748b" interval={0} />
                <YAxis tick={tick} stroke="#64748b" width={48} />
                <Tooltip content={<Tip />} />
                <Bar dataKey="value" name="Rupees" radius={[3, 3, 0, 0]}>
                  {waterfall.map((row) => <Cell key={row.name} fill={row.value >= 0 ? "#34d399" : "#fb7185"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartBox>
          <p className="text-xs text-slate-500">
            Net {money((totals.ss_fraud_caught_amt || 0) - (data?.friction_rupees || 0) - (totals.ss_legit_blocked_amt || 0))} after friction and lost sales.
          </p>
        </Panel>
        <Panel title="Decision funnel">
          <ChartBox>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnel} layout="vertical" margin={{ left: 8 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" tick={tick} stroke="#64748b" />
                <YAxis type="category" dataKey="name" tick={tick} stroke="#64748b" width={72} />
                <Tooltip content={<Tip />} />
                <Bar dataKey="value" name="Payments" fill="#38bdf8" radius={[0, 3, 3, 0]} barSize={18} onClick={(bar) => {
                  const map = { Approved: "APPROVE", Blocked: "BLOCK", "Step-up": "STEP_UP" };
                  setFocus(map[bar?.name] ? { kind: "decision", value: map[bar.name] } : null);
                }} />
              </BarChart>
            </ResponsiveContainer>
          </ChartBox>
          <p className="text-xs text-slate-500">Counts from this live run. OTP is a step-up, not a measured customer reply.</p>
        </Panel>
      </div>

      <Panel title="Latency histogram">
        {!latency.some((bin) => bin.count) ? (
          <EmptyState title="No latency samples yet" detail="Scores fill this as soon as a scenario or an upload runs." />
        ) : (
          <ChartBox height={180}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={latency}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="ms" tick={tick} stroke="#64748b" label={{ value: "ms", fill: "#64748b", fontSize: 11 }} />
                <YAxis tick={tick} stroke="#64748b" width={32} allowDecimals={false} />
                <Tooltip content={<Tip />} />
                <Bar dataKey="count" name="Payments" fill="#fbbf24" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartBox>
        )}
        <p className="text-xs text-slate-500">Bars are 1 ms wide. The live SLO is 25 ms.</p>
      </Panel>

      <Panel
        title="Red team replay"
        action={
          <button
            type="button"
            className="rounded border border-ember px-3 py-1 text-xs text-ember disabled:opacity-50"
            disabled={replaying}
            onClick={async () => {
              setReplaying(true);
              setError("");
              try {
                setReplay(await api("/redteam/replay", { method: "POST", body: "{}" }));
              } catch (err) {
                setError(String(err));
              } finally {
                setReplaying(false);
              }
            }}
          >
            {replaying ? "Replaying…" : "Replay scenarios"}
          </button>
        }
      >
        <p className="text-xs text-slate-500">
          Replays each recorded scenario once through the champion. It does not invent attacks, and it does not replace the five-seed report below.
        </p>
        {replay?.skipped?.length > 0 && <p className="mt-2 text-xs text-amber">Skipped: {replay.skipped.join(", ")}</p>}
        {replay?.scenarios?.length > 0 && (
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-[11px] uppercase text-slate-500">
              <tr>
                <th className="py-2">Scenario</th>
                <th>Events</th>
                <th>Latched</th>
                <th>Seconds</th>
                <th>Fraud recall</th>
                <th>False declines</th>
                <th>Leaked</th>
              </tr>
            </thead>
            <tbody>
              {replay.scenarios.map((row) => (
                <tr key={row.scenario} className="border-t border-line">
                  <td className="py-1.5">{row.scenario.replaceAll("_", " ")}</td>
                  <td className="num">{row.events}</td>
                  <td>{row.latched ? "yes" : "no"}</td>
                  <td className="num">{row.detect_seconds ?? "—"}</td>
                  <td className="num">{row.fraud_recall ?? "—"}</td>
                  <td className="num">{row.false_decline_rate ?? "—"}</td>
                  <td className="num">{money(row.rupees_leaked_before_latch)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {replay && <p className="mt-2 text-[11px] text-slate-500">{replay.elapsed_s}s · {replay.note}</p>}
      </Panel>

      <Panel title="Red team recall">
        {recallRows.length === 0 ? (
          <EmptyState title="No red-team report yet" detail="python -m ml.redteam writes ml/artifacts/redteam.json." />
        ) : (
          <ChartBox height={280}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={recallRows} margin={{ bottom: 48 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="scenario" tick={tick} stroke="#64748b" interval={0} angle={-30} textAnchor="end" height={70} />
                <YAxis tick={tick} stroke="#64748b" domain={[0, 100]} width={32} />
                <Tooltip content={<Tip />} />
                <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
                <Bar dataKey="recall" name="Fraud recall %" fill="#3ee0c5" radius={[3, 3, 0, 0]} />
                <Bar dataKey="detected" name="ATTACK latched %" fill="#fb7185" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartBox>
        )}
      </Panel>

      <Panel title="Scenario comparison">
        {runs.length === 0 ? (
          <EmptyState title="No saved scenarios" detail="Run a scenario, then start another. The finished run is kept here." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase text-slate-500">
              <tr>
                <th className="py-2">Scenario</th>
                <th>Seen</th>
                <th>Fraud stopped</th>
                <th>Static stopped</th>
                <th>Legit declined</th>
                <th>Static declined</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.scenario} className="border-t border-line">
                  <td className="py-2">{run.scenario}</td>
                  <td className="num">{run.totals.seen}</td>
                  <td className="num">{money(run.totals.ss_fraud_caught_amt)}</td>
                  <td className="num">{money(run.totals.st_fraud_caught_amt)}</td>
                  <td className="num">{run.totals.ss_legit_blocked_n}</td>
                  <td className="num">{run.totals.st_legit_blocked_n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

function cellMatch(row, token) {
  const [side, cell] = String(token).split(":");
  const positive = side === "st" ? row.static_decision === "BLOCK" : row.decision !== "APPROVE";
  const fraud = row.eval_label === 1;
  const legit = row.eval_label === 0;
  if (cell === "tp") return fraud && positive;
  if (cell === "fp") return legit && positive;
  if (cell === "fn") return fraud && !positive;
  if (cell === "tn") return legit && !positive;
  return false;
}

function Matrix({ matrix, positive, onPick }) {
  const cells = matrix || { tp: 0, fp: 0, tn: 0, fn: 0 };
  const items = [
    ["True positive", cells.tp, "text-ok", "tp"],
    ["False positive", cells.fp, "text-ember", "fp"],
    ["False negative", cells.fn, "text-amber", "fn"],
    ["True negative", cells.tn, "text-slate-200", "tn"],
  ];
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">Positive class: {positive}. Counts use simulator ground truth only.</p>
      <div className="grid grid-cols-2 gap-2">
        {items.map(([label, value, tone, cell]) => (
          <button key={label} type="button" className="panel-raised p-3 text-left" onClick={() => onPick?.(cell)}>
            <p className="text-[11px] uppercase text-slate-500">{label}</p>
            <p className={`num text-2xl ${tone}`}>{value}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
