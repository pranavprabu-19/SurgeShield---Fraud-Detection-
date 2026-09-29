"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useDemo } from "../lib/demo";
import { useStream } from "../lib/stream";

export default function DemoOverlay() {
  const demo = useDemo();
  const stream = useStream();
  const [box, setBox] = useState(null);
  const [matrix, setMatrix] = useState([]);
  const [trustNote, setTrustNote] = useState("");

  useEffect(() => {
    if (!demo.active) return undefined;
    function place() {
      const node = document.querySelector(`[data-demo="${demo.chapter.target}"]`);
      if (!node) {
        setBox(null);
        return;
      }
      const rect = node.getBoundingClientRect();
      setBox({ top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12 });
    }
    place();
    const timer = setInterval(place, 400);
    window.addEventListener("resize", place);
    return () => {
      clearInterval(timer);
      window.removeEventListener("resize", place);
    };
  }, [demo.active, demo.chapter, demo.step]);

  useEffect(() => {
    if (!demo.active) return undefined;
    function onKey(event) {
      const tag = event.target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (event.key === "Escape") {
        event.preventDefault();
        demo.exit();
      }
      if (event.key === " ") {
        event.preventDefault();
        demo.next();
      }
      if (event.key === "Backspace") {
        event.preventDefault();
        demo.back();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [demo.active, demo.index, demo.step]);

  useEffect(() => {
    if (demo.active && demo.chapter.id === "scorecard") {
      api("/redteam").then((body) => setMatrix(body.summary || [])).catch(() => {});
    }
  }, [demo.active, demo.chapter]);

  if (!demo.active) return null;
  const type = demo.large ? "text-lg" : "text-sm";

  return (
    <>
      {box && (
        <div
          className="pointer-events-none fixed z-40 rounded-xl ring-2 ring-mint"
          style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
        />
      )}
      <div className="fixed inset-x-0 bottom-0 z-50 px-4 pb-4">
        <div className="panel mx-auto max-w-4xl p-4 shadow-xl">
          <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-slate-500">
            <span>Jury mode</span>
            <span className="num text-mint">{demo.index + 1}/{demo.total}</span>
            <div className="ml-2 h-1 flex-1 overflow-hidden rounded bg-white/10">
              <div className="h-1 bg-mint" style={{ width: `${((demo.index + 1) / demo.total) * 100}%` }} />
            </div>
          </div>
          <p className={`font-semibold text-slate-100 ${demo.large ? "text-2xl" : "text-base"}`}>{demo.chapter.title}</p>
          <p className={`mt-1 text-slate-300 ${type}`}>{demo.chapter.narration}</p>
          <p className={`mt-2 text-mint ${type}`}>What to notice: {demo.chapter.notice}</p>
          {demo.offline && (
            <div className="mt-3">
              <p className="text-ember">The API is not reachable. Play the backup instead of a blank screen.</p>
              <video className="mt-2 max-h-40 w-full rounded" src="/demo_backup.mp4" controls />
            </div>
          )}
          {demo.chapter.id === "trust" && (
            <div data-demo="trust" className="mt-3 flex flex-wrap gap-2">
              <button className="rounded border border-line px-3 py-1 text-xs" onClick={async () => setTrustNote(JSON.stringify(await api("/audit/verify")))}>Verify chain</button>
              <button className="rounded border border-ember px-3 py-1 text-xs text-ember" onClick={async () => setTrustNote(JSON.stringify(await api("/audit/tamper", { method: "POST" })))}>Tamper one record</button>
              <button className="rounded border border-amber px-3 py-1 text-xs text-amber" onClick={() => stream.setKillSwitch(!stream.safeMode, "jury demo")}>
                {stream.safeMode ? "Restore model" : "Kill switch"}
              </button>
              {trustNote && <p className="w-full text-xs text-slate-400">{trustNote.slice(0, 280)}</p>}
            </div>
          )}
          {demo.chapter.id === "scorecard" && (
            <div data-demo="scorecard" className="mt-3 max-h-40 overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-slate-500">
                  <tr><th>Shape</th><th>Before</th><th>After</th><th>Leaked</th></tr>
                </thead>
                <tbody>
                  {matrix.map((row) => (
                    <tr key={row.scenario} className="border-t border-line">
                      <td className="py-1">{row.scenario}</td>
                      <td className="num">{row.baseline_detected_rate ?? "—"}</td>
                      <td className="num">{row.detected_rate}</td>
                      <td className="num">{row.rupees_leaked_before_latch}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <button className="rounded border border-line px-2 py-1" onClick={demo.back}>Back</button>
            <button className="rounded bg-mint px-2 py-1 text-ink" onClick={demo.next}>Next</button>
            <button className="rounded border border-line px-2 py-1" onClick={() => demo.setAuto((value) => !value)}>{demo.auto ? "Auto on" : "Auto off"}</button>
            <button className="rounded border border-line px-2 py-1" onClick={() => demo.setLarge((value) => !value)}>{demo.large ? "Normal type" : "Large type"}</button>
            <button className="ml-auto text-slate-500" onClick={demo.exit}>Exit</button>
            <span className="text-slate-600">Space next · Backspace back · Esc exit</span>
          </div>
        </div>
      </div>
    </>
  );
}
