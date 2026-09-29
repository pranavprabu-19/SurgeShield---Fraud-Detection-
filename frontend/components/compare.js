"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { useStream } from "../lib/stream";
import { Panel } from "./ui";

const COLORS = { logistic: "#3ee0c5", lightgbm: "#38bdf8", xgboost: "#fbbf24" };
const METRICS = [
  ["pr_auc", "PR-AUC"],
  ["roc_auc", "ROC-AUC"],
  ["recall_at_0_1pct_fpr", "Recall at 0.1% FPR"],
];

export function ModelCompare({ selected }) {
  const stream = useStream();
  const [body, setBody] = useState(null);
  const [active, setActive] = useState("logistic");
  const [feature, setFeature] = useState("Amount");

  useEffect(() => {
    api("/compare").then(setBody).catch(() => {});
  }, []);

  const models = body?.models || {};
  const names = Object.keys(models);
  const bars = METRICS.map(([key, label]) => {
    const row = { metric: label };
    names.forEach((name) => {
      row[name] = Number(models[name]?.[key] || 0);
    });
    return row;
  });
  const features = body?.features || [];
  const picked = features.find((row) => row.feature === feature) || features[0];
  const liveValue = selected?.signals?.[picked?.feature];
  const latest = stream.feed[0];
  const mix = useMemo(() => {
    const counts = { APPROVE: 0, STEP_UP: 0, BLOCK: 0 };
    stream.feed.forEach((row) => {
      if (counts[row.decision] != null) counts[row.decision] += 1;
    });
    return counts;
  }, [stream.feed]);

  return (
    <Panel title="Three models">
      <p className="text-sm text-slate-400">
        {body?.note || "Held-out test.csv. XGBoost is not on the scoring path. Only the calibrated logistic champion blocks."}
      </p>
      {!body?.ready && <p className="mt-2 text-sm text-slate-500">No comparison file yet. Run python -m ml.compare.</p>}
      <div className="mt-3 grid gap-2 md:grid-cols-3">
        {names.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setActive(name)}
            className={`rounded border px-3 py-2 text-left ${active === name ? "border-mint" : "border-line"}`}
          >
            <p className="text-xs uppercase text-slate-500">{name}{name === "logistic" ? " · champion" : ""}</p>
            <p className="num text-2xl">{Number(models[name].pr_auc).toFixed(3)}</p>
            <p className="text-[11px] text-slate-500">PR-AUC · ROC {Number(models[name].roc_auc).toFixed(3)}</p>
          </button>
        ))}
      </div>
      {bars.length > 0 && (
        <div className="mt-3 h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bars}>
              <XAxis dataKey="metric" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} domain={[0, 1]} />
              <Tooltip />
              {names.map((name) => (
                <Bar key={name} dataKey={name} fill={COLORS[name] || "#94a3b8"} opacity={name === active ? 1 : 0.35}>
                  {bars.map((row) => <Cell key={`${name}-${row.metric}`} />)}
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Live stream {stream.feed.length ? "moving" : "idle"}
        {latest ? ` · last risk ${latest.risk_100} · ${latest.decision}` : ""}.
        Approve {mix.APPROVE} · step-up {mix.STEP_UP} · block {mix.BLOCK}. These counts are the socket, not test.csv.
      </p>
      {picked && (
        <div className="mt-4">
          <p className="text-[11px] uppercase text-slate-500">Legitimate vs fraud · click a feature</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {features.slice(0, 10).map((row) => (
              <button
                key={row.feature}
                type="button"
                onClick={() => setFeature(row.feature)}
                className={`rounded border px-2 py-1 text-xs ${row.feature === picked.feature ? "border-mint text-mint" : "border-line text-slate-400"}`}
              >
                {row.feature}
              </button>
            ))}
          </div>
          <Dumbbell row={picked} live={liveValue} />
        </div>
      )}
    </Panel>
  );
}

function Dumbbell({ row, live }) {
  const values = [row.legit_mean, row.fraud_mean, live].filter((value) => value != null && Number.isFinite(Number(value)));
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const span = max - min || 1;
  const place = (value) => `${((Number(value) - min) / span) * 100}%`;
  return (
    <div className="mt-3">
      <div className="relative h-3 rounded bg-white/10">
        <span className="absolute top-0 h-3 w-2 -translate-x-1/2 rounded bg-mint" style={{ left: place(row.legit_mean) }} title="Legitimate mean" />
        <span className="absolute top-0 h-3 w-2 -translate-x-1/2 rounded bg-amber" style={{ left: place(row.fraud_mean) }} title="Fraud mean" />
        {live != null && <span className="absolute top-0 h-3 w-2 -translate-x-1/2 rounded bg-ember" style={{ left: place(live) }} title="This payment" />}
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Legit mean {row.legit_mean} · fraud mean {row.fraud_mean} · gap {row.gap}
        {live != null ? ` · this payment ${live}` : " · pick a live payment to place it on the line"}
      </p>
    </div>
  );
}

export function LivePayments({ rows, onPick, empty }) {
  return (
    <ul className="max-h-72 space-y-1 overflow-auto text-sm">
      {rows.length === 0 && <li className="text-slate-500">{empty}</li>}
      {rows.slice(0, 20).map((row) => (
        <li key={row.id}>
          <button type="button" className="flex w-full items-center justify-between gap-2 rounded border border-white/5 px-2 py-1.5 text-left hover:border-mint" onClick={() => onPick(row)}>
            <span>
              {row.decision}
              {row.synthesized ? " · synthesized" : ""}
              <span className="ml-2 text-slate-500">risk {row.risk_100}</span>
            </span>
            <span className="num text-slate-400">{row.amount}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
