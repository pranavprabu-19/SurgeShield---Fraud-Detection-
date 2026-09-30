"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../lib/api";
import { useStream } from "../lib/stream";
import { SALES, SCENARIOS } from "../lib/scenarios";
import { Drawer, Gauge, SeverityBadge } from "./ui";
import { ShieldAlert, Fingerprint, Activity, Network, MapPin, Search } from "lucide-react";

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
    setCopilot("Analyzing transaction trajectory...");
    const result = await api("/copilot", {
      method: "POST",
      body: JSON.stringify({ decision: row.decision, regime: row.regime, reasons: row.reasons || [] }),
    });
    setCopilot(`${result.text} (${result.source})`);
  }
  
  return (
    <Drawer open={Boolean(selected)} title={<div className="flex items-center gap-2 text-slate-200 font-semibold"><Fingerprint className="w-5 h-5 text-mint" /> Transaction {selected?.id || ""}</div>} onClose={onClose}>
      {selected && (
        <div className="space-y-6 text-sm pb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <SeverityBadge value={selected.decision} />
              {selected.phase && <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">{selected.phase}</span>}
            </div>
            <div className="num text-right">
              <span className="text-xs text-slate-400 block uppercase tracking-wider">Risk Score</span>
              <span className="text-lg text-slate-200 font-bold">{selected.risk_100 ?? "—"} <span className="text-xs text-slate-500 font-normal">/ 100</span></span>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-2 text-xs border border-white/5 rounded-lg p-3 bg-white/[0.01]">
            <div><span className="text-slate-500 block">Regime</span><span className="text-slate-200">{selected.regime}</span></div>
            <div><span className="text-slate-500 block">Segment</span><span className="text-slate-200">{selected.segment}</span></div>
            <div><span className="text-slate-500 block">Mode</span><span className="text-slate-200">{selected.mode}</span></div>
            <div><span className="text-slate-500 block">Champion Score</span><span className="num text-slate-200">{selected.score}</span></div>
          </div>
          
          {/* Mock Interactive Graph / Deep Dive Component */}
          <div className="rounded-xl border border-white/10 bg-panel overflow-hidden shadow-lg">
            <div className="bg-white/5 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2 border-b border-white/10">
              <Network className="w-3.5 h-3.5" /> Entity Graph Preview
            </div>
            <div className="p-4 relative h-32 flex items-center justify-center">
               <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'radial-gradient(#3ee0c5 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>
               <div className="relative z-10 flex items-center justify-between w-full max-w-xs mx-auto">
                 <div className="flex flex-col items-center group cursor-pointer">
                   <div className="w-10 h-10 rounded-full bg-slate-800 border-2 border-slate-600 flex items-center justify-center group-hover:border-mint transition-colors">
                     <Fingerprint className="w-5 h-5 text-slate-400 group-hover:text-mint" />
                   </div>
                   <span className="text-[10px] mt-1 text-slate-400 group-hover:text-mint transition-colors">User ID</span>
                 </div>
                 <div className="h-0.5 flex-1 bg-gradient-to-r from-slate-600 to-amber relative">
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-panel px-1 text-[9px] text-slate-400 border border-slate-600 rounded">
                      ₹{selected.amount || '0'}
                    </div>
                 </div>
                 <div className="flex flex-col items-center group cursor-pointer">
                   <div className="w-10 h-10 rounded-full bg-slate-800 border-2 border-amber flex items-center justify-center group-hover:border-mint transition-colors">
                     <Activity className="w-5 h-5 text-amber group-hover:text-mint" />
                   </div>
                   <span className="text-[10px] mt-1 text-amber group-hover:text-mint transition-colors">Merchant</span>
                 </div>
               </div>
            </div>
            <div className="bg-white/5 p-2 flex justify-between gap-2 border-t border-white/10">
              {selected.user_token && (
                <Link className="flex-1 text-center rounded-lg bg-mint/10 px-2 py-1.5 text-[11px] font-medium text-mint hover:bg-mint/20 transition-colors" href={`/investigate/user/${selected.user_token}`}>Analyze User</Link>
              )}
              {selected.merchant_token && (
                <Link className="flex-1 text-center rounded-lg bg-white/5 px-2 py-1.5 text-[11px] font-medium text-slate-300 hover:bg-white/10 transition-colors" href={`/investigate/merchant/${selected.merchant_token}`}>Analyze Merchant</Link>
              )}
            </div>
          </div>

          <div className="space-y-3">
            <h3 className="text-[11px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Risk Factors & Signals</h3>
            {Object.entries(selected.layers || {}).map(([name, layer]) => (
              <Gauge key={name} label={`${name} · ${layer.label}`} value={layer.value} max={1} />
            ))}
            
            <div className="flex flex-wrap gap-2 mt-3">
              {(selected.reasons || []).map((reason) => (
                <span key={reason.feature} className="rounded-full border border-ember/30 bg-ember/10 px-2.5 py-1 text-[11px] text-ember flex items-center gap-1.5 shadow-sm" title={reason.feature}>
                  <ShieldAlert className="w-3 h-3" />
                  {reason.text || reason.feature}
                </span>
              ))}
              {(!selected.reasons || selected.reasons.length === 0) && (
                <p className="text-xs text-slate-500 italic">No specific anomaly triggers recorded.</p>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3 text-xs text-slate-300 space-y-2 shadow-inner">
            <h3 className="text-[10px] uppercase font-bold text-slate-500 tracking-wider flex items-center gap-1.5 mb-2"><MapPin className="w-3 h-3" /> Context Profile</h3>
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
              <span className="text-slate-500">Geography</span>
              <span>{selected.profile?.region || selected.region || "Unknown"} {selected.profile?.region_new && <span className="text-amber text-[10px] bg-amber/10 px-1 rounded ml-1 border border-amber/30">NEW</span>}</span>
              
              <span className="text-slate-500">Velocity</span>
              <span>{selected.profile?.travel_km ? `${selected.profile.travel_km} km at ${selected.profile.travel_kmh} km/h` : "N/A"} {selected.profile?.impossible_travel && <span className="text-ember text-[10px] bg-ember/10 px-1 rounded ml-1 border border-ember/30">IMPOSSIBLE</span>}</span>
              
              <span className="text-slate-500">Device</span>
              <span>{selected.profile?.device_new ? "Unrecognized" : "Known"} · {selected.profile?.device_users ? `Shared by ${selected.profile.device_users}` : "Single user"}</span>
              
              <span className="text-slate-500">Merchant</span>
              <span>Ticket {selected.profile?.ticket_ratio ?? "—"}x {selected.profile?.flash_sale && <span className="text-mint text-[10px] bg-mint/10 px-1 rounded ml-1 border border-mint/30">FLASH SALE</span>}</span>
            </div>
          </div>

          <div className="pt-2 border-t border-white/5">
            <button className="w-full flex items-center justify-center gap-2 rounded-lg bg-mint text-ink font-semibold px-4 py-2 text-sm hover:bg-mint/90 transition-all shadow-[0_0_15px_rgba(62,224,197,0.3)] hover:shadow-[0_0_20px_rgba(62,224,197,0.5)]" onClick={() => askCopilot(selected)}>
              <Search className="w-4 h-4" /> Ask AI Copilot
            </button>
            {copilot && (
              <div className="mt-3 rounded-lg border border-mint/30 bg-mint/5 p-3 text-[13px] text-slate-300 leading-relaxed shadow-inner">
                {copilot}
              </div>
            )}
          </div>
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
