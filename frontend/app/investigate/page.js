"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, money } from "../../lib/api";
import { useStream } from "../../lib/stream";
import { PHASE_LABEL, shortToken } from "../../lib/scenarios";
import { ScoreBar, TransactionDrawer } from "../../components/console";
import { DataTable, EmptyState, Panel, SeverityBadge } from "../../components/ui";

export default function InvestigatePage() {
  const stream = useStream();
  const router = useRouter();
  const [kind, setKind] = useState("user");
  const [raw, setRaw] = useState("");
  const [lookup, setLookup] = useState("");
  const [cases, setCases] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [filter, setFilter] = useState("ALL");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [review, setReview] = useState(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");

  useEffect(() => {
    let stop = false;
    let inflight = false;
    async function tick() {
      if (inflight || stop) return;
      inflight = true;
      setRunning(true);
      setRunError("");
      try {
        const body = await api("/investigate/run", { method: "POST" });
        if (!stop) setReview(body);
      } catch (error) {
        if (!stop) setRunError(String(error.message || error));
      } finally {
        inflight = false;
        if (!stop) setRunning(false);
      }
    }
    tick();
    const timer = setInterval(tick, 5000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const body = await api("/cases");
        if (stop) return;
        setCases(body.cases || []);
        setWatchlist(body.watchlist || []);
      } catch {
        /* waits for the API */
      }
    }
    tick();
    const timer = setInterval(tick, 2500);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  async function search(event) {
    event.preventDefault();
    const value = raw.trim();
    if (!value) return;
    setLookup("");
    if (/^[0-9a-f]{24}$/.test(value)) {
      router.push(`/investigate/${kind}/${value}`);
      return;
    }
    try {
      const body = await api("/entity/lookup", { method: "POST", body: JSON.stringify({ kind, raw_id: value }) });
      setRaw("");
      if (body.found) router.push(`/investigate/${body.kind}/${body.token}`);
      else setLookup(`No history for that ${kind} in this run. Token ${shortToken(body.token)}.`);
    } catch (error) {
      setLookup(String(error));
    }
  }

  const rows = useMemo(() => {
    return stream.feed
      .filter((row) => {
        if (filter === "BLOCK" || filter === "STEP_UP") return row.decision === filter;
        if (filter === "DIFF") return row.decision !== row.static_decision;
        if (filter === "DUP") return row.duplicate;
        return true;
      })
      .filter((row) => !query || String(row.id).includes(query) || String(row.user_token || "").includes(query) || String(row.merchant_token || "").includes(query));
  }, [stream.feed, filter, query]);

  const totals = stream.totals || {};
  const seen = totals.seen || 0;
  const attackOnly = seen > 0 && !totals.ss_approve && !totals.ss_step && totals.ss_block > 0;

  return (
    <div className="space-y-4">
      <Panel
        title="Run the model"
        action={
          <button type="button" disabled className="rounded border border-mint px-3 py-1.5 text-sm text-mint disabled:opacity-70">
            {running ? "Running…" : "Model running"}
          </button>
        }
      >
        <p className="max-w-3xl text-sm text-slate-400">
          Run the model reads every customer and merchant with a stored history. A history that stays challenged is blocked and the case is declined. A history that is mostly quiet, or that gets quieter, is approved. Case status updates immediately.
        </p>
        <div className="mt-3 flex flex-wrap gap-4 text-sm">
          <span>Scored <span className="num">{seen}</span></span>
          <span className="text-ok">Approved <span className="num">{totals.ss_approve || 0}</span></span>
          <span className="text-amber">Step-up <span className="num">{totals.ss_step || 0}</span></span>
          <span className="text-ember">Blocked <span className="num">{totals.ss_block || 0}</span></span>
        </div>
        {attackOnly && (
          <p className="mt-2 text-sm text-slate-300">
            This run is only an attack, so there is no genuine buyer to approve. A normal day approves all 220 payments. A flash sale approves all 360. An attack hidden in a sale approves the buyers and does not approve the fraud.
          </p>
        )}
        {runError && <p className="mt-2 text-sm text-ember">{runError}</p>}
        {review && (
          <div className="mt-4 space-y-3">
            <div className="flex flex-wrap gap-4 text-sm">
              <span>Histories <span className="num">{review.payments}</span></span>
              <span className="text-ok">Approved <span className="num">{review.summary?.APPROVE || 0}</span></span>
              <span className="text-ember">Blocked <span className="num">{review.summary?.BLOCK || 0}</span></span>
            </div>
            {review.payments === 0 ? (
              <EmptyState title="No histories yet" detail="Run a sale or an attack so customers and merchants build a history, then run the model." />
            ) : (
              <>
                <p className="text-xs text-slate-500">Blocked histories are listed. Approved ones stay off this list because their payments were mostly quiet.</p>
                <DataTable
                rows={review.rows || []}
                rowKey={(row) => row.id}
                columns={[
                  { key: "who", label: "Entity", render: (row) => <Link className="num text-xs text-mint" href={`/investigate/${row.kind}/${row.token}`}>{row.kind === "user" ? "Customer" : "Merchant"} {shortToken(row.token)}</Link> },
                  { key: "decision", label: "Decision", render: (row) => <SeverityBadge value={row.decision} /> },
                  { key: "flags", label: "Challenged", render: (row) => <span className="num">{row.flags}/{row.payments}</span> },
                  { key: "risk", label: "Peak risk", render: (row) => <span className="num">{row.risk_100}</span> },
                  { key: "amount", label: "Value", render: (row) => money(row.amount) },
                  { key: "why", label: "From the history", render: (row) => <span className="text-xs text-slate-400">{row.why}</span> },
                ]}
              />
              </>
            )}
          </div>
        )}
      </Panel>

      <Panel title="Find a customer or merchant">
        <form onSubmit={search} className="flex flex-wrap items-center gap-2">
          <select value={kind} onChange={(event) => setKind(event.target.value)} className="rounded border border-line bg-ink px-2 py-1.5 text-sm">
            <option value="user">Customer</option>
            <option value="merchant">Merchant</option>
          </select>
          <input
            value={raw}
            onChange={(event) => setRaw(event.target.value)}
            placeholder="Customer or merchant id, or a 24-character token"
            className="min-w-[320px] flex-1 rounded border border-line bg-ink px-3 py-1.5 text-sm"
          />
          <button className="rounded border border-mint px-3 py-1.5 text-sm text-mint">Open</button>
        </form>
        <p className="mt-2 text-[11px] text-slate-500">
          Raw ids are tokenized on the server with the same HMAC key as the stream and are never stored or logged.
        </p>
        {lookup && <p className="mt-2 text-xs text-amber">{lookup}</p>}
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Panel title={`Cases (${cases.length})`}>
          {cases.length === 0 ? (
            <EmptyState title="No cases yet" detail="A customer opens a case after two challenged payments. A CSV upload opens one as soon as that row is stepped up or blocked." />
          ) : (
            <div className="max-h-[420px] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-panel text-[11px] uppercase text-slate-500">
                  <tr><th className="px-2 py-2">Entity</th><th>Status</th><th>Risk</th><th>Flags</th><th>Value</th><th>Signals</th><th>Why</th></tr>
                </thead>
                <tbody>
                  {cases.map((row) => (
                    <tr key={row.id} className="cursor-pointer border-t border-line hover:bg-white/[0.03]" onClick={() => router.push(`/investigate/${row.kind}/${row.token}`)}>
                      <td className="px-2 py-1.5">
                        <span className="text-[10px] uppercase text-slate-500">{row.kind === "user" ? "customer" : "merchant"}</span>{" "}
                        <span className="num">{shortToken(row.token)}</span>
                      </td>
                      <td><SeverityBadge value={row.status} /></td>
                      <td className="num">{row.max_risk}</td>
                      <td className="num">{row.flags}/{row.payments}</td>
                      <td className="num">{money(row.amount)}</td>
                      <td className="text-xs text-slate-400">{(row.top_signals || []).join(", ") || "—"}</td>
                      <td className="text-xs text-slate-500">{row.why}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <Panel title="Watchlist">
          {watchlist.length === 0 ? (
            <EmptyState title="Nobody flagged yet" />
          ) : (
            <ul className="space-y-1 text-sm">
              {watchlist.map((row) => (
                <li key={`${row.kind}-${row.token}`}>
                  <Link href={`/investigate/${row.kind}/${row.token}`} className="flex items-center justify-between rounded px-2 py-1 hover:bg-white/5">
                    <span>
                      <span className="text-[10px] uppercase text-slate-500">{row.kind === "user" ? "customer" : "merchant"}</span>{" "}
                      <span className="num">{shortToken(row.token)}</span>
                    </span>
                    <span className="num text-xs text-slate-400">{row.flags} flags · {money(row.amount)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel
        title="Decision feed"
        action={
          <div className="flex items-center gap-2 text-xs">
            {["ALL", "BLOCK", "STEP_UP", "DIFF", "DUP"].map((chip) => (
              <button key={chip} onClick={() => setFilter(chip)} className={filter === chip ? "text-mint" : "text-slate-500"}>{chip}</button>
            ))}
            <input
              ref={stream.filterRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="id or token"
              className="w-32 rounded border border-line bg-ink px-2 py-1 text-xs"
            />
          </div>
        }
      >
        {rows.length === 0 ? (
          <EmptyState title="Waiting for transactions" detail="Launch a scenario from Overview or the War Room, or score a CSV on Upload." />
        ) : (
          <DataTable
            rows={rows}
            rowKey={(row) => row.id}
            onRow={setSelected}
            columns={[
              { key: "id", label: "Id", render: (row) => <span className="num">{row.id}</span> },
              { key: "decision", label: "Decision", render: (row) => <SeverityBadge value={row.decision} /> },
              { key: "static", label: "Static", render: (row) => row.static_decision },
              { key: "score", label: "Score", render: (row) => <ScoreBar score={row.score} /> },
              { key: "amount", label: "Amount", render: (row) => money(row.amount) },
              { key: "user", label: "Customer", render: (row) => <span className="num text-xs">{shortToken(row.user_token)}</span> },
              { key: "region", label: "City", render: (row) => row.region || "—" },
              { key: "phase", label: "Phase", render: (row) => <span className="text-xs text-slate-400">{PHASE_LABEL[row.phase] || row.phase || "—"}</span> },
            ]}
          />
        )}
      </Panel>

      <TransactionDrawer selected={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
