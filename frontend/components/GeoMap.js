"use client";

import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from "react-leaflet";

const COLOR = { APPROVE: "#34d399", STEP_UP: "#fbbf24", BLOCK: "#fb7185" };

export default function GeoMap({ points = [], path = false, height = 320, center = [21.5, 79.0], zoom = 4 }) {
  const valid = points.filter((point) => point.lat != null && point.lon != null);
  const line = path ? valid.map((point) => [point.lat, point.lon]) : [];
  return (
    <div style={{ height }} className="overflow-hidden rounded-lg border border-line">
      <MapContainer center={center} zoom={zoom} scrollWheelZoom={false} style={{ height: "100%", width: "100%", background: "#0b1220" }}>
        <TileLayer
          className="map-tiles"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {line.length > 1 && <Polyline positions={line} pathOptions={{ color: "#fb7185", weight: 2, dashArray: "4 6" }} />}
        {valid.map((point, index) => (
          <CircleMarker
            key={point.key ?? `${point.id ?? index}-${index}`}
            center={[point.lat, point.lon]}
            radius={point.radius || (point.decision === "APPROVE" ? 4 : 7)}
            pathOptions={{ color: COLOR[point.decision] || "#38bdf8", fillColor: COLOR[point.decision] || "#38bdf8", fillOpacity: 0.7, weight: 1 }}
          >
            <Tooltip>
              <span>{point.label || `${point.decision} ${point.region || ""}`}</span>
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
