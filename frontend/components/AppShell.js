"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, Database, Gauge, Search, Shield, ShoppingCart, Siren, Upload } from "lucide-react";
import clsx from "clsx";
import { useDemo } from "../lib/demo";
import { useStream } from "../lib/stream";
import { SALES, SCENARIOS } from "../lib/scenarios";
import { ConfirmModal, SeverityBadge, Toasts, useClock } from "./ui";

const NAV = [
  { href: "/", label: "Overview", icon: Activity },
  { href: "/war-room", label: "Sale War Room", icon: ShoppingCart },
  { href: "/investigate", label: "Investigate", icon: Search },
  { href: "/incidents", label: "Incidents", icon: Siren },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/model", label: "Model", icon: Gauge },
  { href: "/governance", label: "Governance", icon: Shield },
  { href: "/data", label: "Data", icon: Database },
];

const KEYED = Object.fromEntries([...SCENARIOS, ...SALES].filter((item) => item.key).map((item) => [item.key.toLowerCase(), item.id]));

export default function AppShell({ children }) {
  const path = usePathname();
  const stream = useStream();
  const demo = useDemo();
  const now = useClock();
  const [collapsed, setCollapsed] = useState(false);
  const [killOpen, setKillOpen] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    function onKey(event) {
      const tag = event.target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") {
        if (event.key === "Escape") event.target.blur();
        return;
      }
      if (demo.active) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const scenario = KEYED[String(event.key).toLowerCase()];
      if (scenario) stream.launch(scenario);
      if (event.key === "r" || event.key === "R") stream.reset();
      if (event.key === "k" || event.key === "K") setKillOpen(true);
      if (event.key === "j" || event.key === "J") demo.start();
      if (event.key === "/") {
        event.preventDefault();
        stream.filterRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stream, demo.active]);

  const clock = now
    ? new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(now)
    : "--:--:--";

  return (
    <div className="flex min-h-screen">
      <aside className={clsx("flex shrink-0 flex-col border-r border-line bg-panel", collapsed ? "w-16" : "w-56")}>
        <button className="px-4 py-4 text-left" onClick={() => setCollapsed((value) => !value)}>
          <p className="text-[10px] uppercase tracking-[0.22em] text-mint">SurgeShield</p>
          {!collapsed && <p className="text-sm font-semibold">Fraud operations</p>}
        </button>
        <nav className="flex-1 space-y-1 px-2">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? path === "/" : path?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-sm",
                  active ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5"
                )}
              >
                <Icon size={16} />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            );
          })}
        </nav>
        {!collapsed && (
          <p className="px-4 py-3 text-[10px] leading-relaxed text-slate-600">
            1-9 and 0 scenarios · B and G sales · R reset · K kill switch · / filter · J jury mode
          </p>
        )}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2 text-xs">
          <span className="flex items-center gap-1.5">
            <span className={clsx("h-2 w-2 rounded-full", stream.connection === "LIVE" ? "bg-ok" : stream.connection === "POLLING" ? "bg-amber" : "bg-ember")} />
            {stream.connection}
          </span>
          <SeverityBadge value={stream.regime} />
          <span className="num text-slate-400">{stream.config?.model_version || "model"}</span>
          {stream.safeMode && <span className="rounded bg-amber px-2 py-0.5 font-semibold text-ink">SAFE MODE</span>}
          <span className="text-slate-400">Open incidents {stream.openIncidents}</span>
          <button className="ml-auto rounded border border-mint px-2 py-0.5 text-mint" onClick={demo.start}>Jury mode</button>
          <span className="rounded border border-line px-2 py-0.5 text-slate-400">DEMO</span>
          <span className="num text-slate-300">{clock} IST</span>
        </header>
        {stream.safeMode && (
          <div className="bg-amber/15 px-4 py-1.5 text-xs text-amber">
            Kill switch is on. Rules authorise payments. The model is not deciding.
          </div>
        )}
        <main className="min-w-0 flex-1 px-4 py-4">{children}</main>
      </div>
      <Toasts items={stream.toasts} />
      <ConfirmModal
        open={killOpen}
        title={stream.safeMode ? "Restore the model" : "Engage kill switch"}
        confirmLabel={stream.safeMode ? "Restore" : "Engage"}
        onClose={() => setKillOpen(false)}
        onConfirm={async () => {
          await stream.setKillSwitch(!stream.safeMode, reason);
          setReason("");
          setKillOpen(false);
        }}
      >
        <p>Checkout keeps running. This flip is written to the audit chain.</p>
        <input
          className="mt-3 w-full rounded border border-line bg-ink px-3 py-2 text-sm"
          placeholder="Reason for the change"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </ConfirmModal>
    </div>
  );
}
