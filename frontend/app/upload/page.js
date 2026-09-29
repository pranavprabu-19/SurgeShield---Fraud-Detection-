"use client";

import { useState } from "react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../../lib/api";
import { ChartBox, Tip, tick } from "../../components/charts";
import { DataTable, KpiTile, Panel, SeverityBadge } from "../../components/ui";

const COLORS = { APPROVE: "#34d399", STEP_UP: "#fbbf24", BLOCK: "#fb7185" };

export default function UploadPage() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");

  async function submit(file) {
    if (!file) return;
    setBusy(true);
    setError("");
    setName(file.name);
    const body = new FormData();
    body.append("file", file);
    try {
      setReport(await api("/score/csv", { method: "POST", body }));
    } catch (err) {
      setReport(null);
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  const summary = report?.summary || {};
  const mix = ["APPROVE", "STEP_UP", "BLOCK"].map((decision) => ({
    name: decision,
    value: summary[decision] || 0,
    fill: COLORS[decision],
  }));
  const labels = report?.labels || {};

  return (
    <div className="space-y-4">
      <Panel title="Score a transaction file">
        <p className="max-w-3xl text-sm text-slate-400">
          Drop a CSV. Each row is scored by the live champion, the same path as checkout. Columns: Time, Amount, V1 to V28.
          Optional: user_id, merchant_id, Class, region, lat, lon, device, category. The first 2,000 rows are scored. Raw ids are tokenized and not stored.
        </p>
        <label
          className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-line bg-white/5 px-6 py-10 text-center"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            submit(event.dataTransfer.files?.[0]);
          }}
        >
          <span className="text-sm text-slate-200">{busy ? "Scoring…" : name || "Choose a CSV"}</span>
          <span className="mt-1 text-xs text-slate-500">or drop it here</span>
          <input
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            disabled={busy}
            onChange={(event) => submit(event.target.files?.[0])}
          />
        </label>
        {error && <p className="mt-3 text-sm text-ember">{error}</p>}
      </Panel>

      {report && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiTile label="Scored" value={report.count} hint={report.truncated ? "Stopped at 2,000 rows" : `${report.skipped} skipped`} />
            <KpiTile label="Approved" value={summary.APPROVE || 0} hint={money(report.amounts?.APPROVE)} />
            <KpiTile label="Step-up" value={summary.STEP_UP || 0} hint={money(report.amounts?.STEP_UP)} />
            <KpiTile label="Blocked" value={summary.BLOCK || 0} hint={money(report.amounts?.BLOCK)} />
          </section>
          {labels.fraud + labels.legit > 0 && (
            <p className="text-sm text-slate-400">
              Labelled rows: {labels.fraud_caught} of {labels.fraud} fraud challenged, {labels.legit_blocked} of {labels.legit} genuine buyers blocked.
            </p>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Decisions">
              <ChartBox>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={mix}>
                    <CartesianGrid stroke="#1c2740" vertical={false} />
                    <XAxis dataKey="name" tick={tick} stroke="#64748b" />
                    <YAxis tick={tick} stroke="#64748b" width={36} allowDecimals={false} />
                    <Tooltip content={<Tip />} />
                    <Bar dataKey="value" name="Payments" radius={[3, 3, 0, 0]}>
                      {mix.map((row) => <Cell key={row.name} fill={row.fill} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartBox>
            </Panel>
            <Panel title="Score distribution">
              <ChartBox>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={report.histogram || []}>
                    <CartesianGrid stroke="#1c2740" vertical={false} />
                    <XAxis dataKey="bin" tick={tick} stroke="#64748b" />
                    <YAxis tick={tick} stroke="#64748b" width={32} allowDecimals={false} />
                    <Tooltip content={<Tip />} />
                    <Bar dataKey="count" name="Payments" fill="#3ee0c5" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartBox>
            </Panel>
          </div>
          <Panel title="Signals that fired">
            {(report.reasons || []).length === 0 ? (
              <p className="text-sm text-slate-500">No detector chips on this file. Decisions came from the champion score alone.</p>
            ) : (
              <ChartBox height={180}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={report.reasons} layout="vertical" margin={{ left: 24 }}>
                    <XAxis type="number" tick={tick} stroke="#64748b" allowDecimals={false} />
                    <YAxis type="category" dataKey="feature" tick={tick} stroke="#64748b" width={110} />
                    <Tooltip content={<Tip />} />
                    <Bar dataKey="count" name="Payments" fill="#fbbf24" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartBox>
            )}
          </Panel>
          <Panel title="First rows" action={<Link href="/investigate" className="text-xs text-mint">Open cases</Link>}>
            <DataTable
              rows={report.decisions || []}
              rowKey={(row) => row.id}
              columns={[
                { key: "id", label: "Id", render: (row) => <span className="num">{row.id}</span> },
                { key: "decision", label: "Decision", render: (row) => <SeverityBadge value={row.decision} /> },
                { key: "risk", label: "Risk", render: (row) => <span className="num">{row.risk_100}</span> },
                { key: "amount", label: "Amount", render: (row) => money(row.amount) },
                { key: "regime", label: "Regime", render: (row) => row.regime },
                {
                  key: "who",
                  label: "Customer",
                  render: (row) => row.user_token ? <Link className="text-mint" href={`/investigate/user/${row.user_token}`}>…{row.user_token.slice(-6)}</Link> : "—",
                },
                { key: "why", label: "Reason", render: (row) => <span className="text-xs text-slate-400">{row.reason || "model score"}</span> },
              ]}
            />
          </Panel>
        </>
      )}
    </div>
  );
}
