"use client";

import { useEffect, useState } from "react";
import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../../lib/api";
import { useStream } from "../../lib/stream";
import { ConfirmModal, EmptyState, Panel, SeverityBadge } from "../../components/ui";

export default function GovernancePage() {
  const stream = useStream();
  const [verify, setVerify] = useState(null);
  const [drift, setDrift] = useState(null);
  const [privacy, setPrivacy] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [copilot, setCopilot] = useState("");
  const [error, setError] = useState("");
  const [killOpen, setKillOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("analyst review");
  const [picked, setPicked] = useState({});
  const [fairness, setFairness] = useState(null);

  async function refresh() {
    try {
      const [chain, driftBody, privacyBody, reviewBody, fairBody] = await Promise.all([
        api("/audit/verify"),
        api("/drift"),
        api("/privacy"),
        api("/review"),
        api("/fairness"),
      ]);
      setFairness(fairBody);
      setVerify({ ...chain, checked_at: new Date().toISOString() });
      setDrift(driftBody);
      setPrivacy(privacyBody);
      setReviews(reviewBody.items || []);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, []);

  async function explainTop() {
    const open = reviews.find((item) => item.status === "OPEN") || reviews[0];
    const result = await api("/copilot", {
      method: "POST",
      body: JSON.stringify({
        decision: open?.decision || "BLOCK",
        regime: "ATTACK",
        reasons: open?.reasons || [{ text: "tight burst of look-alike payments" }],
      }),
    });
    setCopilot(`${result.text} (${result.source}; decision owner: ${result.decision_owner})`);
  }

  async function review(ids, action) {
    if (!note.trim()) {
      setError("A review note is required.");
      return;
    }
    for (const id of ids) {
      await api(`/review/${id}`, { method: "POST", body: JSON.stringify({ action, note }) });
    }
    setPicked({});
    await refresh();
  }

  const openIds = reviews.filter((item) => item.status === "OPEN" && picked[item.id]).map((item) => item.id);
  const nodes = Array.from({ length: 12 }, (_, index) => index);
  const broken = verify && !verify.ok;

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-ember">{error}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel
          demo="trust"
          title="Hash-chained audit log"
          action={<button className="text-xs text-slate-400" onClick={refresh}>Verify</button>}
        >
          <p className={`text-2xl ${verify?.ok ? "text-ok" : "text-ember"}`}>
            {verify ? (verify.ok ? "Chain intact" : `Broken at record ${verify.broken_at}`) : "—"}
          </p>
          <p className="text-xs text-slate-500">{verify?.records ?? 0} AES-256-GCM records · checked {verify?.checked_at?.slice(11, 19) || "—"}</p>
          <div className="mt-3 flex gap-1">
            {nodes.map((index) => (
              <div
                key={index}
                className="h-3 flex-1 rounded-sm"
                style={{ background: broken && index === nodes.length - 1 ? "#fb7185" : "#34d399" }}
                title={broken && index === nodes.length - 1 ? `break ${verify.broken_at}` : "link"}
              />
            ))}
          </div>
          <button
            className="mt-3 rounded border border-ember px-3 py-1 text-xs text-ember"
            onClick={async () => { await api("/audit/tamper", { method: "POST" }); await refresh(); }}
          >
            Tamper latest record
          </button>
        </Panel>
        <Panel title="Kill switch">
          <p className="text-2xl">{stream.safeMode ? "Safe mode" : "Model in control"}</p>
          <p className="text-sm text-slate-400">Safe mode keeps authorising with rules only. Checkout does not stop.</p>
          <button className="mt-3 rounded border border-amber px-3 py-1 text-sm" onClick={() => setKillOpen(true)}>
            {stream.safeMode ? "Restore model" : "Engage kill switch"}
          </button>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Model health">
          <p className={`num text-3xl ${drift?.sustained ? "text-ember" : drift?.alert ? "text-amber" : "text-ok"}`}>{drift?.psi ?? 0}</p>
          <p className="text-xs text-slate-500">
            {drift?.sustained ? "Sustained drift" : drift?.alert ? "Alert" : "Stable"} · PSI threshold {drift?.threshold} · {drift?.samples ?? 0} scores
          </p>
          <p className="mt-2 text-sm text-slate-300">
            Mean score <span className="num">{drift?.current_mean ?? 0}</span> versus training <span className="num">{drift?.baseline_mean ?? 0}</span>
            {" "}(shift <span className="num">{drift?.mean_shift ?? 0}</span>)
          </p>
          {drift?.suggestion && <p className="mt-2 text-xs text-amber">{drift.suggestion}</p>}
          <div className="mt-3 h-36">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={drift?.history || []}>
                <XAxis dataKey="t" hide />
                <YAxis hide domain={[0, 0.6]} />
                <Tooltip />
                <ReferenceLine y={0.2} stroke="#fbbf24" />
                <Line dataKey="psi" stroke="#3ee0c5" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Fairness">
          {!fairness?.available ? (
            <p className="text-sm text-slate-400">This dataset has no age, gender, or geography column. Those fields are never model inputs. When a file has them, false-decline and step-up rates appear here.</p>
          ) : (
            Object.entries(fairness.groups).map(([name, group]) => (
              <div key={name} className="mb-3">
                <p className="text-xs uppercase text-slate-500">{name} disparity {group.disparity_ratio ?? "n/a"}</p>
                {group.rows.map((row) => (
                  <p key={row.value} className="text-sm">
                    {row.value}: decline {(row.false_decline_rate * 100).toFixed(1)}% · step-up {(row.step_up_rate * 100).toFixed(1)}% · n {row.seen}
                  </p>
                ))}
              </div>
            ))
          )}
        </Panel>
        <Panel title="Privacy">
          <div className="grid grid-cols-3 gap-2 text-xs">
            <Flow title="Raw identifier" body="user_id, merchant_id. Never written to the audit log." />
            <Flow title="HMAC token" body={(privacy?.tokenized || []).join(", ") || "user and merchant tokens"} />
            <Flow title="Audit record" body="Decision, regime, score, amount, tokens, reason names. AES-256-GCM." />
          </div>
          <p className="mt-3 text-sm">Model inputs, not persisted: {(privacy?.minimized_fields || []).join(", ") || "—"}</p>
          <p className="text-sm text-slate-400">Not stored: {(privacy?.not_stored || []).join(", ")}</p>
          <p className="mt-2 text-xs text-slate-500">{(privacy?.statutes || []).join(" · ")}</p>
        </Panel>
      </div>

      <Panel title="Challenger model" action={<button className="text-xs text-mint" onClick={async () => { const result = await api("/challenger/train", { method: "POST" }); setCopilot(JSON.stringify(result)); }}>Train from reviews</button>}>
        <p className="text-sm text-slate-400">Uphold and Release labels can propose a challenger. Promotion is a separate audited action. It does not happen on its own.</p>
        <button
          className="mt-2 rounded border border-line px-3 py-1 text-xs"
          onClick={async () => setCopilot(JSON.stringify(await api("/challenger/promote", { method: "POST" })))}
        >
          Promote if recommended
        </button>
      </Panel>
      <Panel title="Model registry">
        <div className="grid gap-3 text-sm md:grid-cols-4">
          <Reg label="Version" value={stream.config?.model_version} />
          <Reg label="Trained" value={stream.config?.trained_at?.slice(0, 19)} />
          <Reg label="Artifact" value={stream.config?.artifact_sha256?.slice(0, 12)} />
          <Reg label="Owner" value="SurgeShield demo" />
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Lineage lives in docs/MODEL_CARD.md, docs/DATASHEET.md, and docs/THREAT_MODEL.md.
        </p>
      </Panel>

      <Panel
        title="Human review queue"
        action={
          <div className="flex items-center gap-2 text-xs">
            <button className="text-mint" onClick={explainTop}>Ask the copilot</button>
            <button disabled={!openIds.length} onClick={() => review(openIds, "UPHOLD")}>Uphold selected</button>
            <button disabled={!openIds.length} onClick={() => review(openIds, "RELEASE")}>Release selected</button>
          </div>
        }
      >
        <input
          className="mb-3 w-full rounded border border-line bg-ink px-3 py-2 text-sm"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Required note"
        />
        {copilot && <p className="mb-3 rounded bg-black/30 p-3 text-sm">{copilot}</p>}
        {reviews.length === 0 && <EmptyState title="No challenged payments yet" detail="Run an attack scenario first." />}
        <div className="space-y-2">
          {reviews.slice(0, 12).map((item) => (
            <div key={item.id} className="flex flex-wrap items-center gap-3 border-t border-line py-2 text-sm">
              {item.status === "OPEN" && (
                <input type="checkbox" checked={Boolean(picked[item.id])} onChange={(event) => setPicked((current) => ({ ...current, [item.id]: event.target.checked }))} />
              )}
              <SeverityBadge value={item.decision} />
              <span className="num">#{item.id}</span>
              <span>{money(item.amount)}</span>
              <span className="text-xs text-slate-500">{age(item.created_at)} · SLA 15m</span>
              <span className="text-xs text-slate-500">{item.status}</span>
              {item.status === "OPEN" && (
                <span className="ml-auto flex gap-2 text-xs">
                  <button onClick={() => review([item.id], "RELEASE")}>Release</button>
                  <button onClick={() => review([item.id], "UPHOLD")}>Uphold</button>
                </span>
              )}
            </div>
          ))}
        </div>
      </Panel>

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
        <p>This change is an audit event. Checkout continues on rules while safe mode is on.</p>
        <input className="mt-3 w-full rounded border border-line bg-ink px-3 py-2" placeholder="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      </ConfirmModal>
    </div>
  );
}

function Flow({ title, body }) {
  return (
    <div className="panel-raised p-3">
      <p className="uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-1 text-slate-300">{body}</p>
    </div>
  );
}

function Reg({ label, value }) {
  return (
    <div>
      <p className="text-[11px] uppercase text-slate-500">{label}</p>
      <p className="num">{value || "—"}</p>
    </div>
  );
}

function age(created) {
  if (!created) return "—";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - created));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.round(seconds / 60)}m`;
}
