export const SCENARIOS = [
  { id: "normal", label: "Normal day", key: "1" },
  { id: "flash_sale", label: "Flash sale", key: "2" },
  { id: "bot_attack", label: "Bot attack", key: "3" },
  { id: "mixed", label: "Attack inside a sale", key: "4" },
  { id: "noisy_ring", label: "Noisy ring", key: "5" },
  { id: "low_and_slow", label: "Low and slow", key: "6" },
  { id: "card_testing", label: "Card testing", key: "7" },
  { id: "account_takeover", label: "Account takeover", key: "8" },
  { id: "split_ring", label: "Split ring", key: "9" },
  { id: "mule_fan_in", label: "Mule fan-in", key: "0" },
  { id: "distributed_drain", label: "Distributed drain" },
  { id: "boundary_probe", label: "Boundary probe" },
];

export const SALES = [
  { id: "big_billion_day", label: "Big Billion Days", key: "B" },
  { id: "great_indian_festival", label: "Great Indian Festival", key: "G" },
];

export const REAL = [
  { id: "replay_real", label: "Replay imported data" },
  { id: "real_peak", label: "Imported data at sale peak" },
];

export const PHASE_LABEL = {
  warmup: "Warm-up",
  sale_open: "Sale open",
  scalper_bots: "Scalper bots",
  card_testing: "Card testing",
  account_takeover: "Account takeover",
  mule_cashout: "Mule cash-out",
  distributed_drain: "Distributed drain",
  cooldown: "Cool-down",
  live: "Live",
};

export function shortToken(token) {
  return token ? `…${String(token).slice(-6)}` : "—";
}
