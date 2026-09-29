"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";

export function Panel({ title, action, children, className, demo }) {
  return (
    <section className={clsx("panel p-4", className)} data-demo={demo}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-xs uppercase tracking-[0.16em] text-slate-400">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function KpiTile({ label, value, hint, delta, spark }) {
  return (
    <div className="panel p-3">
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="num mt-1 text-xl font-semibold text-slate-50">{value}</p>
      <div className="mt-1 flex items-center justify-between gap-2">
        <p className="text-[11px] text-slate-500">{hint}</p>
        {delta != null && (
          <span className={clsx("num text-[11px]", delta >= 0 ? "text-ok" : "text-ember")}>
            {delta >= 0 ? "+" : ""}
            {delta}
          </span>
        )}
      </div>
      {spark?.length > 1 && (
        <svg viewBox="0 0 80 18" className="mt-2 h-4 w-full">
          <polyline
            fill="none"
            stroke="#3ee0c5"
            strokeWidth="1.4"
            points={spark
              .map((value, index) => {
                const max = Math.max(...spark, 1);
                const x = (index / (spark.length - 1)) * 80;
                const y = 16 - (value / max) * 14;
                return `${x},${y}`;
              })
              .join(" ")}
          />
        </svg>
      )}
    </div>
  );
}

const SEVERITY = {
  CRITICAL: "bg-ember/15 text-ember border-ember/40",
  HIGH: "bg-high/15 text-high border-high/40",
  MEDIUM: "bg-amber/15 text-amber border-amber/40",
  LOW: "bg-low/15 text-low border-low/40",
  OK: "bg-ok/15 text-ok border-ok/40",
  OPEN: "bg-ember/15 text-ember border-ember/40",
  ACK: "bg-amber/15 text-amber border-amber/40",
  RESOLVED: "bg-ok/15 text-ok border-ok/40",
  BLOCK: "bg-ember/15 text-ember border-ember/40",
  STEP_UP: "bg-amber/15 text-amber border-amber/40",
  APPROVE: "bg-ok/15 text-ok border-ok/40",
  NORMAL: "bg-ok/15 text-ok border-ok/40",
  SURGE: "bg-amber/15 text-amber border-amber/40",
  ATTACK: "bg-ember/20 text-ember border-ember/50",
  RECOVERY: "bg-low/15 text-low border-low/40",
  APPROVED: "bg-ok/15 text-ok border-ok/40",
  DECLINED: "bg-ember/15 text-ember border-ember/40",
  ESCALATED: "bg-high/15 text-high border-high/40",
  VERIFY_REQUESTED: "bg-amber/15 text-amber border-amber/40",
};

export function SeverityBadge({ value }) {
  return (
    <span className={clsx("inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide", SEVERITY[value] || SEVERITY.LOW)}>
      {value}
    </span>
  );
}

export function Gauge({ label, value, max = 1, threshold, unit = "", polarity = "risk" }) {
  const missing = value == null || Number.isNaN(Number(value));
  const num = missing ? 0 : Number(value);
  const pct = Math.max(0, Math.min(100, (num / max) * 100));
  const mark = threshold == null ? null : Math.max(0, Math.min(100, (threshold / max) * 100));
  const hot = !missing && threshold != null && (polarity === "genuine" ? num < threshold : num >= threshold);
  return (
    <div>
      <div className="flex justify-between text-[11px] text-slate-400">
        <span>{label}</span>
        <span className={clsx("num", hot ? "text-ember" : "text-slate-200")}>
          {missing ? "—" : num.toFixed(2)}
          {missing ? "" : unit}
        </span>
      </div>
      <div className="relative mt-1 h-1.5 rounded bg-white/5">
        <div className={clsx("h-1.5 rounded", hot ? "bg-ember" : "bg-mint")} style={{ width: `${missing ? 0 : pct}%` }} />
        {mark != null && <div className="absolute top-[-2px] h-2.5 w-px bg-amber" style={{ left: `${mark}%` }} />}
      </div>
    </div>
  );
}

export function EmptyState({ title, detail }) {
  return (
    <div className="px-3 py-8 text-sm text-slate-500">
      <p className="text-slate-300">{title}</p>
      {detail && <p className="mt-1 text-xs">{detail}</p>}
    </div>
  );
}

export function Drawer({ open, title, onClose, children }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <aside className="h-full w-full max-w-md overflow-y-auto border-l border-line bg-ink p-5" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm uppercase tracking-[0.16em] text-slate-400">{title}</h2>
          <button className="text-sm text-slate-400" onClick={onClose}>Close</button>
        </div>
        {children}
      </aside>
    </div>
  );
}

export function ConfirmModal({ open, title, confirmLabel, onConfirm, onClose, children }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <div className="panel w-full max-w-md p-5">
        <h2 className="text-lg font-semibold">{title}</h2>
        <div className="mt-3 text-sm text-slate-300">{children}</div>
        <div className="mt-4 flex justify-end gap-2">
          <button className="rounded border border-line px-3 py-1.5 text-sm" onClick={onClose}>Cancel</button>
          <button className="rounded bg-ember px-3 py-1.5 text-sm text-ink" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

export function Toasts({ items }) {
  if (!items?.length) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {items.map((item) => (
        <div key={item.id} className="panel-raised px-3 py-2 text-sm shadow-lg">{item.text}</div>
      ))}
    </div>
  );
}

export function Skeleton({ className }) {
  return <div className={clsx("animate-pulse rounded bg-white/5", className)} />;
}

export function DataTable({ columns, rows, onRow, rowKey }) {
  return (
    <div className="max-h-[420px] overflow-auto">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-panel text-[11px] uppercase tracking-wide text-slate-500">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="px-3 py-2 font-medium">{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={rowKey ? rowKey(row) : index}
              className="cursor-pointer border-t border-line hover:bg-white/[0.03]"
              onClick={() => onRow?.(row)}
            >
              {columns.map((column) => (
                <td key={column.key} className="px-3 py-2 align-middle">
                  {column.render ? column.render(row) : row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Timeline({ milestones }) {
  const items = milestones || [];
  if (!items.length) {
    return <p className="text-xs text-slate-500">No milestones yet. Launch a scenario.</p>;
  }
  const start = items[0].t;
  const end = Math.max(items[items.length - 1].t, start + 1);
  return (
    <div>
      <div className="relative h-2 rounded bg-white/10">
        {items.map((item) => (
          <span
            key={`${item.kind}-${item.t}`}
            className="absolute top-[-3px] h-3.5 w-1.5 rounded bg-mint"
            style={{ left: `${((item.t - start) / (end - start)) * 100}%` }}
            title={item.label}
          />
        ))}
      </div>
      <ul className="mt-2 space-y-1 text-xs text-slate-400">
        {items.map((item) => (
          <li key={`${item.kind}-${item.seq || item.t}`}>{item.label}</li>
        ))}
      </ul>
    </div>
  );
}

export function useClock() {
  const [now, setNow] = useState(null);
  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}
