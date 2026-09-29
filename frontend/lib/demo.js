"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "./api";
import { useStream } from "./stream";

export const CHAPTERS = [
  {
    id: "normal",
    title: "Normal baseline",
    href: "/",
    scenario: "normal",
    target: "regime",
    narration: "A quiet hour on the Overview. Scores stay low, the regime stays NORMAL, and almost every payment is approved.",
    notice: "Watch the regime bar. It should not move.",
    done: (stream) => (stream.totals?.seen || 0) >= 30,
  },
  {
    id: "surge",
    title: "Flash sale",
    href: "/",
    scenario: "flash_sale",
    target: "signals",
    narration: "Volume jumps. Merchant concentration is high, devices are diverse, and arrivals are uneven. That is a sale. We loosen cuts for segments that are not under attack.",
    notice: "Declines stay near zero while volume is several times a normal minute.",
    done: (stream) => stream.regime === "SURGE" || stream.regime === "RECOVERY",
  },
  {
    id: "attack",
    title: "Bot ring",
    href: "/",
    scenario: "bot_attack",
    target: "signals",
    narration: "An attack is a tight knot of look-alike payments: a few rupees first, then the drain. The banner should flip to ATTACK.",
    notice: "Tightness and the probe-then-drain gauge cross the mark. Fraud rupees stopped climb.",
    done: (stream) => stream.regime === "ATTACK",
  },
  {
    id: "mixed",
    title: "Attack inside the sale",
    href: "/",
    scenario: "mixed",
    target: "compare",
    narration: "The same ring hides inside the sale. SurgeShield blocks the knot. The static threshold either misses it or declines the buyers around it.",
    notice: "Fraud stopped goes up. Legitimate declines stay below the static count.",
    done: (stream) => stream.regime === "ATTACK" && (stream.totals?.seen || 0) >= 40,
  },
  {
    id: "shapes",
    title: "Slow rings, testing, takeover, mules",
    href: "/",
    steps: ["card_testing", "account_takeover", "mule_fan_in", "distributed_drain"],
    target: "timeline",
    narration: "Card testing is tiny amounts across many merchants. Account takeover is one token across many merchants. Mule fan-in is many cards into two cash-out merchants. Each one latches ATTACK for a different reason.",
    notice: "Read the detector chips: card testing, fan-out, then fan-in.",
    done: (stream) => stream.regime === "ATTACK",
  },
  {
    id: "sale",
    title: "Big Billion Days",
    href: "/war-room",
    scenario: "big_billion_day",
    target: "phases",
    narration: "Midnight open. Buyers pile onto four flagship merchants from every city. Then scalper bots, card testers, a hijacked saved card, and mule cash-out hide inside the rush. Each wave is caught while the genuine buyers keep checking out.",
    notice: "Watch the phase strip: caught 100% on the attack phases, false declines near zero on the sale phase.",
    done: (stream) => stream.feed[0]?.phase === "cooldown",
  },
  {
    id: "case",
    title: "Open a case",
    href: "/investigate",
    caseView: true,
    target: "case",
    narration: "Pick the customer the system flagged. The case shows its payment history, the cities it paid from on a real map, the timeline, and plain-language insights. The analyst approves, declines, escalates, or asks for verification, and each click is written to the audit chain.",
    notice: "The dashed line joins payments from cities hundreds of kilometres apart within seconds.",
    done: () => false,
  },
  {
    id: "trust",
    title: "Trust",
    href: "/governance",
    target: "trust",
    narration: "The model decides. The copilot only translates reason codes. The audit log is hash-chained. Tamper one record and the verifier names it. The kill switch drops to rules and checkout keeps running.",
    notice: "Use the buttons on this card. They call the same controls as the page.",
    done: () => false,
  },
  {
    id: "scorecard",
    title: "Before and after",
    href: "/",
    target: "scorecard",
    narration: "Five seeds each. The old detector already caught the classic ring. It missed slow pacing, card testing, fan-out, and mule fan-in. Those latch now. A flash sale still does not.",
    notice: "Latch rate of 0 on the flash sale is the result we want.",
    done: () => false,
  },
];

const DemoContext = createContext(null);

export function DemoProvider({ children }) {
  const stream = useStream();
  const router = useRouter();
  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);
  const [step, setStep] = useState(0);
  const [auto, setAuto] = useState(true);
  const [large, setLarge] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);

  const chapter = CHAPTERS[index];

  async function runChapter(nextIndex, nextStep = 0) {
    const item = CHAPTERS[nextIndex];
    setBusy(true);
    setIndex(nextIndex);
    setStep(nextStep);
    setStartedAt(Date.now());
    try {
      await api("/health");
      setOffline(false);
    } catch {
      setOffline(true);
      setBusy(false);
      return;
    }
    let href = item.href;
    if (item.caseView) {
      try {
        const body = await api("/cases");
        const rows = body.cases || [];
        const pick =
          rows.find((row) => row.kind === "user" && (row.top_signals || []).includes("impossible_travel")) ||
          rows.find((row) => row.kind === "user") ||
          rows[0];
        if (pick) href = `/investigate/${pick.kind}/${pick.token}`;
      } catch {
        /* falls back to the case list */
      }
    }
    if (href) router.push(href);
    const scenario = item.steps ? item.steps[nextStep] : item.scenario;
    if (scenario) {
      try {
        await stream.reset();
        await stream.launch(scenario);
      } catch {
        setOffline(true);
      }
    }
    setBusy(false);
  }

  function start() {
    setActive(true);
    setAuto(true);
    runChapter(0, 0);
  }

  function exit() {
    setActive(false);
  }

  function next() {
    if (!active) return;
    const item = CHAPTERS[index];
    if (item.steps && step < item.steps.length - 1) {
      runChapter(index, step + 1);
      return;
    }
    if (index < CHAPTERS.length - 1) runChapter(index + 1, 0);
  }

  function back() {
    if (!active) return;
    if (step > 0) {
      runChapter(index, step - 1);
      return;
    }
    if (index > 0) runChapter(index - 1, 0);
  }

  useEffect(() => {
    if (!active || !auto || busy || offline) return undefined;
    const timer = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      const finished = elapsed > 45000 || (elapsed > 4000 && chapter.done(stream));
      if (finished && !["case", "trust", "scorecard"].includes(chapter.id)) next();
    }, 1000);
    return () => clearInterval(timer);
  }, [active, auto, busy, offline, startedAt, chapter, stream.regime, stream.totals, index, step]);

  const value = useMemo(
    () => ({
      active,
      chapter,
      index,
      step,
      auto,
      setAuto,
      large,
      setLarge,
      offline,
      busy,
      total: CHAPTERS.length,
      start,
      exit,
      next,
      back,
    }),
    [active, index, step, auto, large, offline, busy, stream.regime, stream.totals]
  );

  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemo() {
  const value = useContext(DemoContext);
  if (!value) throw new Error("useDemo outside provider");
  return value;
}
