"use client";

export function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-line bg-[#0b1220] px-2.5 py-1.5 text-xs shadow-lg">
      {label != null && label !== "" && <p className="mb-1 text-slate-400">{label}</p>}
      {payload.map((item) => (
        <p key={item.name} className="num" style={{ color: item.color || item.fill || "#e8eef7" }}>
          {item.name}: {typeof item.value === "number" ? item.value.toLocaleString("en-IN") : item.value}
        </p>
      ))}
    </div>
  );
}

export const tick = { fill: "#94a3b8", fontSize: 11 };

export function ChartBox({ children, height = 220 }) {
  return (
    <div className="min-w-0 w-full" style={{ height }}>
      {children}
    </div>
  );
}
