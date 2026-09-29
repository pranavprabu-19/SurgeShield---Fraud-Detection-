"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../lib/api";
import { useStream } from "../lib/stream";
import { SALES, SCENARIOS } from "../lib/scenarios";
import { Drawer, Gauge, SeverityBadge } from "./ui";

export const REGIME_COLOR = { NORMAL: "#34d399", SURGE: "#fbbf24", ATTACK: "#fb7185", RECOVERY: "#38bdf8" };

export function ScenarioBar() {
  const stream = useStream();
  const [choice, setChoice] = useState(SCENARIOS[0].id);
  return (
    <section className="flex flex-wrap items-center gap-2">
      {SALES.map((item) => (
        <button key={item.id} onClick={() => stream.launch(item.id)} className="rounded-full border border-mint/60 bg-mint/10 px-3 py-1.5 text-sm text-mint hover:bg-mint/20">
          {item.label} <span className="text-[10px] text-slate-400">{item.key}</span>
        </button>
      ))}
      <select value={choice} onChange={(event) => setChoice(event.target.value)} className="rounded-full border border-line bg-panel px-3 py-1.5 text-sm">
        {SCENARIOS.map((item) => (
          <option key={item.id} value={item.id}>{item.key ? `${item.key} · ` : ""}{item.label}</option>
        ))}
      </select>
      <button onClick={() => stream.launch(choice)} className="rounded-full border border-line bg-panel px-3 py-1.5 text-sm hover:border-mint">Run</button>
      <label className="text-xs text-slate-400">
        {stream.eps}/s
        <input className="ml-2 align-middle" type="range" min="5" max="200" value={stream.eps} onChange={(event) => stream.setEps(event.target.value)} />
      </label>
      <button className="text-xs text-slate-400 underline" onClick={stream.reset}>Reset</button>
      <button className="text-xs text-slate-400 underline" onClick={() => stream.setPaused((value) => !value)}>
        {stream.paused ? "Resume feed" : "Pause feed"}
      </button>
      <span className="text-xs text-slate-500">{stream.status}</span>
    </section>
  );
}

export function TransactionDrawer({ selected, onClose }) {
  const [copilot, setCopilot] = useState("");
  useEffect(() => setCopilot(""), [selected?.id]);
  async function askCopilot(row) {
    const result = await api("/copilot", {
      method: "POST",
      body: JSON.stringify({ decision: row.decision, regime: row.regime, reasons: row.reasons || [] }),
    });
    setCopilot(`${result.text} (${result.source})`);
  }
  return (
    <Drawer open={Boolean(selected)} title={`Transaction ${selected?.id || ""}`} onClose={onClose}>
      {selected && (
        <div className="space-y-4 text-sm">
          <div className="flex items-center gap-2">
            <SeverityBadge value={selected.decision} />
            <span className="num text-slate-300">Risk {selected.risk_100 ?? "—"} / 100</span>
            {selected.phase && <span className="text-xs text-slate-500">{selected.phase}</span>}
          </div>
          <p className="text-slate-400">Mode {selected.mode}. Regime {selected.regime}. Segment {selected.segment}.</p>
          <p className="num text-xs">Champion {selected.score} · shadow {selected.shadow_score} · anomaly {selected.anomaly}</p>
          <div className="flex flex-wrap gap-2 text-xs">
            {selected.user_token && (
              <Link className="rounded border border-mint/60 px-2 py-1 text-mint" href={`/investigate/user/${selected.user_token}`}>Open customer case</Link>
            )}
            {selected.merchant_token && (
              <Link className="rounded border border-line px-2 py-1 text-slate-300" href={`/investigate/merchant/${selected.merchant_token}`}>Open merchant</Link>
            )}
          </div>
          <div className="space-y-2">
            {Object.entries(selected.layers || {}).map(([name, layer]) => (
              <Gauge key={name} label={`${name} · ${layer.label}`} value={layer.value} max={1} />
            ))}
          </div>
          <div className="rounded border border-line p-2 text-xs text-slate-300">
            <p>Familiarity {selected.profile?.merchant_familiarity ?? "—"} · amount vs usual {selected.profile?.amount_ratio ?? "—"} · {selected.profile?.new_user ? "new user" : "known user"}</p>
            <p>Region {selected.profile?.region || selected.region || "—"}{selected.profile?.region_new ? " · new" : ""} · category {selected.profile?.category || "—"}{selected.profile?.category_new ? " · new" : ""}</p>
            <p>Device {selected.profile?.device_new ? "new" : "known"} · shared by {selected.profile?.device_users || "—"} accounts · hour {selected.profile?.hour_unusual ? "unusual" : "usual"}</p>
            <p>Travel {selected.profile?.travel_km ? `${selected.profile.travel_km} km at ${selected.profile.travel_kmh} km/h` : "—"}{selected.profile?.impossible_travel ? " · impossible" : ""}</p>
            <p>Merchant surge {selected.profile?.merchant_surge_ratio ?? "—"}x · ticket {selected.profile?.ticket_ratio ?? "—"}x{selected.profile?.flash_sale ? " · flash sale" : ""}</p>
            <p>Human score {selected.human_score ?? "—"} {selected.telemetry_simulated ? "· simulated telemetry" : ""}</p>
          </div>
          {selected.eval_label != null && (
            <p className="text-xs text-amber">Simulator ground truth: {selected.eval_label === 1 ? "fraud" : "legitimate"}</p>
          )}
          <div className="flex flex-wrap gap-2">
            {(selected.reasons || []).map((reason) => (
              <span key={reason.feature} className="rounded-full border border-line px-2 py-1 text-xs text-slate-300" title={reason.feature}>
                {reason.text || reason.feature}
              </span>
            ))}
            {(!selected.reasons || selected.reasons.length === 0) && (
              <p className="text-slate-500">Approved payments are not explained on the hot path.</p>
            )}
          </div>
          <button className="rounded border border-mint px-3 py-1 text-xs" onClick={() => askCopilot(selected)}>Ask copilot</button>
          {copilot && <p className="text-slate-300">{copilot}</p>}
        </div>
      )}
    </Drawer>
  );
}

export function ScoreBar({ score }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded bg-white/10">
        <div className="h-1.5 rounded bg-mint" style={{ width: `${Math.min(100, score * 100)}%` }} />
      </div>
      <span className="num text-xs">{Number(score).toFixed(3)}</span>
    </div>
  );
}
