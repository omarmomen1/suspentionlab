"use client";
import React, { useMemo } from "react";
import EmptyState from "../EmptyState";
import { limitEllipse, thin } from "../../../lib/v2/instruments";

export interface EnvelopePlotProps {
  /** Run G samples. */
  latG: number[];
  longG: number[];
  /** Model limit half-axes [g]. Use envelope maxima; leave undefined when not available. */
  limits?: { latG?: number | null; accelG?: number | null; brakeG?: number | null } | null;
  title?: string;
}

const S = 300;
const M = 30;

/**
 * G-G view with the model limit ellipse. The disclaimer is part of the component: the ellipse
 * is built from envelope maxima across speed, so it is an optimistic upper bound for what the
 * model allows, not a measured tire limit. No phase-usage percentages are computed.
 */
export default function EnvelopePlot({ latG, longG, limits, title = "G-G envelope" }: EnvelopePlotProps) {
  const n = Math.min(latG.length, longG.length);
  const pts = useMemo(() => thin(Array.from({ length: n }, (_, i) => [latG[i], longG[i]] as [number, number]).filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b)), 600), [latG, longG, n]);
  const ell = limitEllipse({ latG: Number(limits?.latG), accelG: Number(limits?.accelG), brakeG: Number(limits?.brakeG) });
  const bound = Math.max(1, ...pts.map(([a, b]) => Math.max(Math.abs(a), Math.abs(b))), ...ell.lat.map(Math.abs), ...ell.long.map(Math.abs), Number.isFinite(Number(limits?.latG)) ? Number(limits?.latG) : 0) * 1.1;
  const P = (v: number) => M + ((v + bound) / (2 * bound)) * (S - 2 * M);
  const Q = (v: number) => S - M - ((v + bound) / (2 * bound)) * (S - 2 * M);

  return (
    <figure data-testid="envelope-plot" className="rounded border border-hairline bg-panel p-3">
      <figcaption className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-400">{title}</figcaption>
      {pts.length === 0 ? (
        <EmptyState kind="not_run" reason="No G samples" />
      ) : (
        <svg viewBox={`0 0 ${S} ${S}`} className="mx-auto h-auto w-full max-w-[340px]" role="img" aria-label="G-G plot with model limit ellipse">
          <rect x={M} y={M} width={S - 2 * M} height={S - 2 * M} fill="none" stroke="#2a313a" />
          <line x1={P(0)} y1={M} x2={P(0)} y2={S - M} stroke="#2a313a" />
          <line x1={M} y1={Q(0)} x2={S - M} y2={Q(0)} stroke="#2a313a" />
          {ell.lat.length > 0 && (
            <polyline data-testid="limit-ellipse" fill="none" stroke="#FFB84D" strokeWidth={1} strokeDasharray="4 3"
              points={ell.lat.map((x, i) => `${P(x).toFixed(1)},${Q(ell.long[i]).toFixed(1)}`).join(" ")} />
          )}
          {ell.lat.length === 0 && Number.isFinite(Number(limits?.latG)) && Number(limits?.latG) > 0 && [-1, 1].map((sg) => (
            <line key={sg} data-testid="lat-limit-line" x1={P(sg * Number(limits?.latG))} y1={M} x2={P(sg * Number(limits?.latG))} y2={S - M} stroke="#FFB84D" strokeDasharray="4 3" />
          ))}
          {pts.map(([a, b], i) => <circle key={i} cx={P(a)} cy={Q(b)} r={1.2} fill="#57C8DC" />)}
          <text x={S / 2} y={S - 8} textAnchor="middle" fontSize={9} fill="#8b97a3">Lateral (g)</text>
          <text x={10} y={S / 2} textAnchor="middle" fontSize={9} fill="#8b97a3" transform={`rotate(-90 10 ${S / 2})`}>Longitudinal (g)</text>
        </svg>
      )}
      {ell.lat.length === 0 && pts.length > 0 && <p className="mt-1 text-xs text-zinc-400"><EmptyState reason="Model limit ellipse (no envelope data)" /></p>}
      <p data-testid="envelope-disclaimer" className="mt-2 text-xs leading-relaxed text-zinc-400">
        Model limit, optimistic: the ellipse axes are the envelope maxima across speed from the solver&apos;s tire and aero model.
        The ellipse shape is an approximation, and real tire and driver limits are usually lower.
      </p>
    </figure>
  );
}
