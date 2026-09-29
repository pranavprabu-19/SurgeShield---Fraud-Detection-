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
import { EmptyState, Panel, Skeleton } from "../../components/ui";

const GRID = "#1c2740";

export default function AnalyticsPage() {
  const [data, setData] = useState(null);
  const [redteam, setRedteam] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");

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
  const recallRows = (redteam?.summary || []).map((row) => ({
    scenario: String(row.scenario || "").replaceAll("_", " "),
    recall: row.fraud_recall == null ? 0 : Math.round(row.fraud_recall * 100),
    detected: Math.round((row.detected_rate || 0) * 100),
  }));

  return (
    <div className="space-y-4">
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
                  <Bar dataKey="count" name="Payments" radius={[3, 3, 0, 0]}>
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
                <Bar dataKey="mean_risk" name="Mean risk" fill="#38bdf8" radius={[3, 3, 0, 0]} />
                <Bar dataKey="n" name="Payments" fill="#243352" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartBox>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="SurgeShield confusion">
          <Matrix matrix={data?.confusion_surgeshield} positive="Block or step-up" />
        </Panel>
        <Panel title="Static threshold confusion">
          <Matrix matrix={data?.confusion_static} positive="Block" />
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
                <Bar dataKey="value" name="Payments" fill="#38bdf8" radius={[0, 3, 3, 0]} barSize={18} />
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

function Matrix({ matrix, positive }) {
  const cells = matrix || { tp: 0, fp: 0, tn: 0, fn: 0 };
  const items = [
    ["True positive", cells.tp, "text-ok"],
    ["False positive", cells.fp, "text-ember"],
    ["False negative", cells.fn, "text-amber"],
    ["True negative", cells.tn, "text-slate-200"],
  ];
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">Positive class: {positive}. Counts use simulator ground truth only.</p>
      <div className="grid grid-cols-2 gap-2">
        {items.map(([label, value, tone]) => (
          <div key={label} className="panel-raised p-3">
            <p className="text-[11px] uppercase text-slate-500">{label}</p>
            <p className={`num text-2xl ${tone}`}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
