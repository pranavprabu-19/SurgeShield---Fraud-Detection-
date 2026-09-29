"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, ShieldAlert, Smartphone, XCircle } from "lucide-react";
import { api, money } from "../../../../lib/api";
import { useStream } from "../../../../lib/stream";
import { PHASE_LABEL, shortToken } from "../../../../lib/scenarios";
import { EmptyState, Panel, SeverityBadge, Skeleton } from "../../../../components/ui";

const GeoMap = dynamic(() => import("../../../../components/GeoMap"), {
  ssr: false,
  loading: () => <div className="h-[300px] animate-pulse rounded-lg bg-white/5" />,
});

const ACTIONS = [
  { id: "APPROVE", label: "Approve", hint: "Release the latest held payment", icon: CheckCircle2, style: "border-ok/60 text-ok hover:bg-ok/10" },
  { id: "DECLINE", label: "Decline and flag", hint: "Uphold the block and teach the thresholds", icon: XCircle, style: "border-ember/60 text-ember hover:bg-ember/10" },
  { id: "ESCALATE", label: "Escalate", hint: "Open an incident for the fraud team", icon: ShieldAlert, style: "border-high/60 text-high hover:bg-high/10" },
  { id: "VERIFY", label: "Request verification", hint: "Ask the customer to confirm by OTP or call", icon: Smartphone, style: "border-amber/60 text-amber hover:bg-amber/10" },
];

const TIMELINE_DOT = { seen: "bg-slate-400", block: "bg-ember", step_up: "bg-amber", incident: "bg-high", action: "bg-mint", note: "bg-sky-400" };

function clock(seconds) {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" });
}

export default function CaseView() {
  const params = useParams();
  const kind = params?.kind === "merchant" ? "merchant" : "user";
  const token = String(params?.token || "");
  const stream = useStream();
  const [view, setView] = useState(null);
  const [missing, setMissing] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [copilot, setCopilot] = useState("");
  const [selectedId, setSelectedId] = useState(null);

  const load = useCallback(async () => {
    try {
      const body = await api(`/entity/${kind}/${token}`);
      setView(body);
      setMissing(false);
    } catch {
      setMissing(true);
    }
  }, [kind, token]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [load]);

  const history = view?.history || [];
  const latestFlag = history.find((event) => event.decision !== "APPROVE");
  const focus = history.find((event) => event.id === selectedId) || latestFlag || history[0];
  const maxRisk = history.reduce((max, event) => Math.max(max, event.risk_100 || 0), 0);
  const status = view?.case?.status || "NO CASE";
  const points = useMemo(
    () =>
      [...(view?.geo || [])].reverse().map((point) => ({
        ...point,
        radius: point.id === focus?.id ? 10 : undefined,
        label: `${point.decision} ${money(point.amount)} · ${point.region || "unknown"}`,
      })),
    [view, focus?.id]
  );
  const geoSource = view?.geo?.[0]?.source;

  useEffect(() => {
    setCopilot("");
    if (!latestFlag) return;
    const reasons = latestFlag.reasons.map((text, index) => ({ feature: latestFlag.features[index] || "signal", text }));
    api("/copilot", { method: "POST", body: JSON.stringify({ decision: latestFlag.decision, regime: latestFlag.regime, reasons }) })
      .then((body) => setCopilot(`${body.text} (${body.source})`))
      .catch(() => {});
  }, [latestFlag?.id]);

  async function act(action) {
    if (!view) return;
    setBusy(action);
    try {
      const body = await api(`/cases/${kind}-${token}/action`, { method: "POST", body: JSON.stringify({ action, note }) });
      const extra = body.review ? ` Review ${body.review.review_id} ${body.review.override.toLowerCase()}.` : body.incident ? ` ${body.incident} opened.` : "";
      stream.toast(`${action.toLowerCase()} recorded.${extra}`);
      if (action === "NOTE") setNote("");
      await load();
    } catch (error) {
      stream.toast(String(error));
    } finally {
      setBusy("");
    }
  }

  if (missing) {
    return (
      <div className="space-y-3">
        <Link href="/investigate" className="text-xs text-mint">Back to Investigate</Link>
        <EmptyState title="No history for this token in the current run" detail="History is in memory and resets with the stream. Run a scenario, then open a case." />
      </div>
    );
  }
  if (!view) return <Skeleton className="h-64" />;

  const summary = view.summary || {};
  const profile = view.profile || {};
  const label = kind === "user" ? "Customer" : "Merchant";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/investigate" className="text-xs text-mint">Investigate</Link>
        <span className="text-slate-600">/</span>
        <h1 className="text-lg font-semibold">{label} case <span className="num text-slate-400">{shortToken(token)}</span></h1>
        <SeverityBadge value={status} />
        <span className={`num rounded border px-2 py-0.5 text-xs ${maxRisk >= 60 ? "border-ember/50 text-ember" : maxRisk >= 30 ? "border-amber/50 text-amber" : "border-line text-slate-300"}`}>
          Peak risk {maxRisk} / 100
        </span>
        {view.case?.why && <span className="text-xs text-slate-500">Opened for {view.case.why}</span>}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.6fr_1fr]">
        <Panel title={`${label} profile`}>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
            <dt className="text-slate-500">Token</dt><dd className="num truncate text-xs" title={token}>{token}</dd>
            <dt className="text-slate-500">Payments</dt><dd className="num">{summary.payments}</dd>
            <dt className="text-slate-500">Challenged</dt><dd className="num">{summary.flags}</dd>
            <dt className="text-slate-500">Total value</dt><dd className="num">{money(summary.amount)}</dd>
            <dt className="text-slate-500">Blocked value</dt><dd className="num">{money(summary.blocked)}</dd>
            <dt className="text-slate-500">Average ticket</dt><dd className="num">{profile.avg_amount != null ? money(profile.avg_amount) : "—"}</dd>
            <dt className="text-slate-500">First seen</dt><dd className="num">{clock(summary.first_seen)}</dd>
            {kind === "user" ? (
              <>
                <dt className="text-slate-500">Merchants</dt><dd className="num">{profile.merchants ?? "—"}</dd>
                <dt className="text-slate-500">Devices</dt><dd className="num">{profile.devices ?? "—"}</dd>
                <dt className="text-slate-500">Peak pace</dt><dd className="num">{profile.peak_velocity_60s ?? "—"} / min</dd>
              </>
            ) : (
              <>
                <dt className="text-slate-500">Buyers</dt><dd className="num">{profile.unique_buyers ?? "—"}</dd>
              </>
            )}
          </dl>
          {(profile.regions || []).length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] uppercase text-slate-500">Cities</p>
              <p className="text-xs text-slate-300">{profile.regions.map((row) => `${row.name} (${row.n})`).join(", ")}</p>
            </div>
          )}
          {(profile.categories || []).length > 0 && (
            <div className="mt-2">
              <p className="text-[11px] uppercase text-slate-500">Categories</p>
              <p className="text-xs text-slate-300">{profile.categories.map((row) => `${row.name} (${row.n})`).join(", ")}</p>
            </div>
          )}
          {(view.counterparts || []).length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] uppercase text-slate-500">{kind === "user" ? "Paid to" : "Paid by"}</p>
              <ul className="mt-1 space-y-0.5 text-xs">
                {view.counterparts.slice(0, 6).map((row) => (
                  <li key={row.token} className="flex justify-between">
                    <Link className="num hover:text-mint" href={`/investigate/${kind === "user" ? "merchant" : "user"}/${row.token}`}>{shortToken(row.token)}</Link>
                    <span className="num text-slate-500">{row.n}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>

        <Panel
          title="Flagged locations"
          demo="case"
          action={<span className="text-[11px] text-slate-500">{geoSource === "real" ? "Real coordinates" : geoSource === "simulated" ? "Simulated city centroids" : "No location on these rows"}</span>}
        >
          {points.length === 0 ? (
            <EmptyState title="Location unavailable" detail="These rows carry no city or coordinates." />
          ) : (
            <GeoMap points={points} path={kind === "user"} height={300} />
          )}
          {focus && (
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <div><p className="text-slate-500">Transaction</p><p className="num">#{focus.id}</p></div>
              <div><p className="text-slate-500">Amount</p><p className="num">{money(focus.amount)}</p></div>
              <div><p className="text-slate-500">Decision</p><SeverityBadge value={focus.decision} /></div>
              <div><p className="text-slate-500">Risk</p><p className="num">{focus.risk_100 ?? "—"} / 100</p></div>
              <div><p className="text-slate-500">City</p><p>{focus.region || "—"}</p></div>
              <div><p className="text-slate-500">Category</p><p>{focus.category || "—"}</p></div>
              <div><p className="text-slate-500">Phase</p><p>{PHASE_LABEL[focus.phase] || focus.phase || "—"}</p></div>
              <div><p className="text-slate-500">Device</p><p className="num">{shortToken(focus.device_token)}</p></div>
            </div>
          )}
          {view.sources && (
            <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
              {Object.entries(view.sources).map(([field, source]) => (
                <span key={field} className={`rounded border px-1.5 py-0.5 ${String(source).startsWith("real") ? "border-ok/50 text-ok" : "border-amber/50 text-amber"}`}>
                  {field}: {source}
                </span>
              ))}
            </div>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="AI insights">
            <ul className="space-y-2 text-sm">
              {(view.insights || []).map((text) => (
                <li key={text} className="flex gap-2">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber" />
                  <span className="text-slate-300">{text}</span>
                </li>
              ))}
            </ul>
            {copilot && <p className="mt-3 rounded border border-line p-2 text-xs text-slate-400">{copilot}</p>}
            <p className="mt-2 text-[10px] text-slate-600">Insights restate stored reason codes. The model made the decision.</p>
          </Panel>
          <Panel title="Actions">
            <div className="grid gap-2">
              {ACTIONS.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    disabled={Boolean(busy)}
                    onClick={() => act(item.id)}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm disabled:opacity-50 ${item.style}`}
                    title={item.hint}
                  >
                    <Icon size={16} />
                    <span className="flex-1">{item.label}</span>
                    {busy === item.id && <span className="text-[10px]">…</span>}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-[10px] text-slate-500">Approve and Decline close the newest open review for this {label.toLowerCase()}. Every action is written to the audit chain.</p>
          </Panel>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <Panel title="Case timeline">
          {(view.timeline || []).length === 0 ? (
            <EmptyState title="No events yet" />
          ) : (
            <ol className="max-h-72 space-y-2 overflow-auto border-l border-line pl-4 text-sm">
              {view.timeline.slice().reverse().map((item, index) => (
                <li key={`${item.t}-${index}`} className="relative">
                  <span className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full ${TIMELINE_DOT[item.kind] || "bg-slate-500"}`} />
                  <p className="text-slate-300">{item.label}</p>
                  <p className="num text-[10px] text-slate-500">{clock(item.t)}</p>
                </li>
              ))}
            </ol>
          )}
          {(view.incidents || []).length > 0 && (
            <p className="mt-3 text-xs text-slate-400">
              Incidents: {view.incidents.map((inc) => inc.id).join(", ")}. <Link href="/incidents" className="text-mint">Open incidents</Link>
            </p>
          )}
        </Panel>
        <Panel title="Notes">
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={3}
            maxLength={500}
            placeholder="What did you check? Notes are attached to the next action too."
            className="w-full rounded border border-line bg-ink px-3 py-2 text-sm"
          />
          <div className="mt-2 flex justify-end">
            <button disabled={!note.trim() || Boolean(busy)} onClick={() => act("NOTE")} className="rounded border border-mint px-3 py-1 text-xs text-mint disabled:opacity-40">Save note</button>
          </div>
          <ul className="mt-3 space-y-2 text-sm">
            {(view.case?.notes || []).slice().reverse().map((entry) => (
              <li key={entry.t} className="rounded border border-line p-2">
                <p className="text-slate-300">{entry.note}</p>
                <p className="num text-[10px] text-slate-500">{clock(entry.t)}</p>
              </li>
            ))}
            {(view.case?.notes || []).length === 0 && <p className="text-xs text-slate-500">No notes yet.</p>}
          </ul>
        </Panel>
      </div>

      <Panel title={`Transaction history (last ${history.length})`}>
        {history.length === 0 ? (
          <EmptyState title="No payments" />
        ) : (
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-panel text-[11px] uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2">Id</th><th>Time</th><th>Decision</th><th>Risk</th><th>Amount</th>
                  <th>{kind === "user" ? "Merchant" : "Customer"}</th><th>City</th><th>Phase</th><th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {history.map((event) => (
                  <tr
                    key={event.id}
                    onClick={() => setSelectedId(event.id)}
                    className={`cursor-pointer border-t border-line hover:bg-white/[0.03] ${event.id === focus?.id ? "bg-white/[0.04]" : ""}`}
                  >
                    <td className="num px-2 py-1.5">{event.id}</td>
                    <td className="num text-xs text-slate-400">{clock(event.t)}</td>
                    <td><SeverityBadge value={event.decision} /></td>
                    <td className="num">{event.risk_100}</td>
                    <td className="num">{money(event.amount)}</td>
                    <td className="num text-xs">{shortToken(kind === "user" ? event.merchant_token : event.user_token)}</td>
                    <td className="text-xs">{event.region || "—"}</td>
                    <td className="text-xs text-slate-400">{PHASE_LABEL[event.phase] || event.phase || "—"}</td>
                    <td className="max-w-[260px] truncate text-xs text-slate-400">{event.reasons?.[0] || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(view.reviews || []).length > 0 && (
          <p className="mt-2 text-xs text-slate-500">
            Reviews: {view.reviews.map((row) => `#${row.id} ${row.status}${row.override_action ? ` (${row.override_action})` : ""}`).join(", ")}
          </p>
        )}
      </Panel>
    </div>
  );
}
