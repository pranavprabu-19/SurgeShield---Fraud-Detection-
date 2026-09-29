"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { API, KEY, WS, api } from "./api";

const StreamContext = createContext(null);

export function StreamProvider({ children }) {
  const [connection, setConnection] = useState("DOWN");
  const [regime, setRegime] = useState("NORMAL");
  const [totals, setTotals] = useState(null);
  const [feed, setFeed] = useState([]);
  const [status, setStatus] = useState("Connecting");
  const [safeMode, setSafeMode] = useState(false);
  const [config, setConfig] = useState(null);
  const [openIncidents, setOpenIncidents] = useState(0);
  const [toasts, setToasts] = useState([]);
  const [eps, setEps] = useState(30);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(false);
  const filterRef = useRef(null);

  function toast(text) {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current.slice(-3), { id, text }]);
    setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 4000);
  }

  function apply(row) {
    if (!row || pausedRef.current) return;
    if (row.regime) setRegime(row.regime);
    if (row.totals) setTotals(row.totals);
    if (row.decision) {
      setFeed((current) => [row, ...current.filter((item) => item.id !== row.id)].slice(0, 200));
    }
  }

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    let socket;
    let retry;
    let attempt = 0;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(`${WS}/ws/stream?api_key=${KEY}`);
      socket.onopen = () => {
        attempt = 0;
        setConnection("LIVE");
        setStatus(`Live on ${API}`);
      };
      socket.onmessage = (message) => {
        try {
          apply(JSON.parse(message.data));
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onerror = () => setConnection("POLLING");
      socket.onclose = () => {
        if (closed) return;
        setConnection("POLLING");
        setStatus(`Socket down. Polling ${API}`);
        const wait = Math.min(8000, 500 * 2 ** attempt);
        attempt += 1;
        retry = setTimeout(connect, wait);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const data = await api("/recent");
        if (data.totals) setTotals(data.totals);
        const newest = (data.transactions || [])[0];
        if (newest?.regime) setRegime(newest.regime);
        if (!pausedRef.current) setFeed((data.transactions || []).slice(0, 200));
        setConnection((current) => (current === "LIVE" ? current : "POLLING"));
      } catch {
        setConnection("DOWN");
        setStatus(`API is not reachable at ${API}`);
      }
    }, 1000);
    return () => clearInterval(poll);
  }, []);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const [health, cfg, incidents] = await Promise.all([
          api("/health"),
          api("/config"),
          api("/incidents"),
        ]);
        if (stop) return;
        setSafeMode(Boolean(health.safe_mode));
        setConfig(cfg);
        setOpenIncidents(incidents.open || 0);
      } catch {
        /* status bar degrades quietly */
      }
    }
    tick();
    const timer = setInterval(tick, 4000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  async function launch(scenario) {
    setFeed([]);
    setPaused(false);
    setStatus(`Running ${scenario}`);
    await api("/simulate", {
      method: "POST",
      body: JSON.stringify({ scenario, events_per_second: Number(eps) }),
    });
    toast(`Scenario ${scenario} started`);
  }

  async function reset() {
    await api("/simulate/reset", { method: "POST" });
    setFeed([]);
    setTotals(null);
    setRegime("NORMAL");
    setStatus("Stream reset");
    toast("Stream reset");
  }

  async function setKillSwitch(enabled, reason) {
    const result = await api(
      `/killswitch?enabled=${enabled}&reason=${encodeURIComponent(reason || "")}`,
      { method: "POST" }
    );
    setSafeMode(Boolean(result.safe_mode));
    toast(result.safe_mode ? "Safe mode engaged" : "Model restored");
    return result;
  }

  const value = useMemo(
    () => ({
      connection,
      regime,
      totals,
      feed,
      status,
      safeMode,
      config,
      openIncidents,
      toasts,
      eps,
      setEps,
      paused,
      setPaused,
      filterRef,
      launch,
      reset,
      setKillSwitch,
      toast,
    }),
    [connection, regime, totals, feed, status, safeMode, config, openIncidents, toasts, eps, paused]
  );

  return <StreamContext.Provider value={value}>{children}</StreamContext.Provider>;
}

export function useStream() {
  const value = useContext(StreamContext);
  if (!value) throw new Error("useStream outside provider");
  return value;
}
