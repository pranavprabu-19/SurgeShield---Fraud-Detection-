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
  {
    label: "Live",
    items: [
      { href: "/", label: "Overview", icon: Activity, line: "Read p50, p99, and the share of payments with zero friction." },
      { href: "/war-room", label: "Sale War Room", icon: ShoppingCart, line: "Press B, then Boundary probe. The gap under the block line is that row's gap, and the decision stays a step-up." },
    ],
  },
  {
    label: "Decide",
    items: [
      { href: "/upload", label: "Upload", icon: Upload, line: "The file report appears above the charts when scoring finishes." },
      { href: "/investigate", label: "Investigate", icon: Search, line: "The history review is already running. Status and Why update on their own." },
      { href: "/incidents", label: "Incidents", icon: Siren, line: "A latched ATTACK opens a filing here." },
    ],
  },
  {
    label: "Evidence",
    items: [
      { href: "/analytics", label: "Analytics", icon: BarChart3, line: "Replay scenarios runs once. Morph this payment tags the copies synthesized." },
      { href: "/model", label: "Model", icon: Gauge, line: "The champion is the only blocker. The comparison models do not score checkout." },
      { href: "/governance", label: "Governance", icon: Shield, line: "Verify the chain, then the kill switch. Jury mode is the button in this bar." },
      { href: "/data", label: "Data", icon: Database, line: "Reports lists the upload next to the creditcard test slice, with PR-AUC." },
    ],
  },
];

function activeItem(path) {
  const items = NAV.flatMap((group) => group.items);
  return items.find((item) => (item.href === "/" ? path === "/" : path?.startsWith(item.href))) || items[0];
}

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
    <div className="flex min-h-screen relative z-10">
      <aside className={clsx("flex shrink-0 flex-col border-r border-line bg-panel/70 backdrop-blur-md", collapsed ? "w-16" : "w-56")}>
        <button className="px-4 py-4 text-left" onClick={() => setCollapsed((value) => !value)}>
          <p className="text-[10px] uppercase tracking-[0.22em] text-mint">SurgeShield</p>
          {!collapsed && <p className="text-sm font-semibold">Fraud operations</p>}
        </button>
        <nav className="flex-1 space-y-3 overflow-auto px-2 pb-2">
          {NAV.map((group) => (
            <div key={group.label}>
              {!collapsed && <p className="px-3 pb-1 text-[10px] uppercase tracking-[0.16em] text-slate-600">{group.label}</p>}
              <div className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = item.href === "/" ? path === "/" : path?.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={collapsed ? item.label : undefined}
                      className={clsx(
                        "flex items-center gap-2 rounded-lg px-3 py-2 text-sm",
                        active ? "bg-mint/10 text-mint" : "text-slate-400 hover:bg-white/5"
                      )}
                    >
                      <Icon size={16} />
                      {!collapsed && <span>{item.label}</span>}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        {!collapsed && (
          <p className="px-4 py-3 text-[10px] leading-relaxed text-slate-600">
            1-9 and 0 scenarios · B and G sales · R reset · K kill switch · / filter · J jury mode
          </p>
        )}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2 text-xs bg-ink/50 backdrop-blur-sm">
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
        <p className="border-b border-line px-4 py-2 text-xs text-slate-400">{activeItem(path).line}</p>
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
