"use client";

import { useEffect, useState } from "react";
import { Area, AreaChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../../lib/api";
import { DataTable, EmptyState, Panel, SeverityBadge, Timeline } from "../../components/ui";

export default function IncidentsPage() {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [copilot, setCopilot] = useState("");
  const [story, setStory] = useState(null);

  async function load(keepId) {
    const body = await api("/incidents");
    setItems(body.items || []);
    setSelected((current) => {
      const id = keepId || current?.id;
      return (body.items || []).find((item) => item.id === id) || body.items?.[0] || null;
    });
  }

  useEffect(() => {
    function tick() {
      load().catch(() => {});
      api("/story").then(setStory).catch(() => {});
    }
    tick();
    const timer = setInterval(tick, 2000);
    return () => clearInterval(timer);
  }, []);

  async function act(path) {
    if (!selected) return;
    await api(path, { method: "POST" });
    await load(selected.id);
  }

  async function explain() {
    if (!selected) return;
    const result = await api("/copilot", {
      method: "POST",
      body: JSON.stringify({
        decision: "BLOCK",
        regime: "ATTACK",
        reasons: [{ text: `segment ${selected.segment} tightness ${selected.peak?.tightness}` }],
      }),
    });
    setCopilot(result.text);
  }

  function printReport() {
    if (!selected) return;
    const popup = window.open("", "_blank");
    if (!popup) return;
    const mules = (selected.mules || []).join(", ");
    popup.document.write(`<!doctype html><title>${selected.id}</title><body style="font-family:sans-serif;padding:32px">
      <h1>RBI-style incident filing ${selected.id}</h1>
      <p>Status ${selected.status}. Segment ${selected.segment}. Severity ${selected.severity}.</p>
      <p>Rupees at risk ${selected.rupees_at_risk}. Rupees blocked ${selected.rupees_blocked}.</p>
      <p>Mule tokens: ${mules || "none recorded"}.</p>
      <p>Peak tightness ${selected.peak?.tightness}, probe ${selected.peak?.probe}, coordination ${selected.peak?.coordination}.</p>
      <p>Member decisions: ${(selected.members || []).map((m) => m.id + " " + m.decision).join("; ")}</p>
      </body>`);
    popup.document.close();
    popup.print();
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[0.9fr_1.3fr]">
      <Panel title="Incidents">
        {items.length === 0 ? (
          <EmptyState title="No incidents" detail="A bot attack that latches ATTACK opens one here." />
        ) : (
          <DataTable
            rows={items}
            rowKey={(row) => row.id}
            onRow={setSelected}
            columns={[
              { key: "id", label: "Id" },
              { key: "status", label: "Status", render: (row) => <SeverityBadge value={row.status} /> },
              { key: "sev", label: "Sev", render: (row) => <SeverityBadge value={row.severity} /> },
              { key: "seg", label: "Seg", render: (row) => row.segment },
              { key: "risk", label: "At risk", render: (row) => money(row.rupees_at_risk) },
              { key: "stopped", label: "Stopped", render: (row) => money(row.rupees_blocked) },
              { key: "mules", label: "Mules", render: (row) => (row.mules || []).length },
            ]}
          />
        )}
      </Panel>
      <div className="space-y-4">
        {!selected ? (
          <Panel title="Detail"><EmptyState title="Select an incident" /></Panel>
        ) : (
          <>
            <Panel
              title={selected.id}
              action={
                <div className="flex gap-2 text-xs">
                  <button className="rounded border border-line px-2 py-1" onClick={() => act(`/incidents/${selected.id}/ack`)}>Acknowledge</button>
                  <button className="rounded border border-line px-2 py-1" onClick={() => act(`/incidents/${selected.id}/resolve`)}>Resolve</button>
                  <button className="rounded border border-mint px-2 py-1" onClick={printReport}>Export report</button>
                </div>
              }
            >
              <p className="text-sm text-slate-400">
                {duration(selected)} · segment {selected.segment} · {(selected.mules || []).length} mule tokens · {selected.tx_count} payments
              </p>
              <div className="mt-3 h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={selected.signals || []}>
                    <XAxis dataKey="id" hide />
                    <YAxis hide />
                    <Tooltip />
                    <Line dataKey="tightness" stroke="#fb7185" dot={false} name="Tightness" />
                    <Line dataKey="probe" stroke="#fbbf24" dot={false} name="Probe" />
                    <Line dataKey="coordination" stroke="#3ee0c5" dot={false} name="Coordination" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Replay timeline" demo="timeline">
              <Timeline milestones={story?.milestones} />
            </Panel>
            <Panel title="Probe then drain">
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={selected.amounts || []}>
                    <XAxis dataKey="id" hide />
                    <YAxis hide />
                    <Tooltip />
                    <Area dataKey="amount" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Member payments">
              <DataTable
                rows={selected.members || []}
                rowKey={(row) => row.id}
                columns={[
                  { key: "id", label: "Id" },
                  { key: "decision", label: "Decision", render: (row) => <SeverityBadge value={row.decision} /> },
                  { key: "score", label: "Score", render: (row) => <span className="num">{row.score}</span> },
                  { key: "amount", label: "Amount", render: (row) => money(row.amount) },
                  { key: "user", label: "Token", render: (row) => <span className="num text-xs">{row.user_token}</span> },
                ]}
              />
            </Panel>
            <Panel title="Copilot" action={<button className="text-xs text-mint" onClick={explain}>Summarise</button>}>
              <p className="text-sm text-slate-300">{copilot || "The copilot explains. It does not decide."}</p>
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}

function duration(item) {
  if (!item.started_at) return "—";
  const end = item.ended_at || Date.now() / 1000;
  const seconds = Math.max(0, Math.round(end - item.started_at));
  return `${seconds}s`;
}
