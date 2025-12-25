'use client';

import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import { Delaunay } from 'd3-delaunay';
import { BackButton } from '../components/BackButton';


// Dynamic import for Plotly to avoid SSR issues
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type PlotlyTrace = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type PlotlyLayout = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type PlotlyConfig = any;

// Types
interface Tweet {
  id: string;
  sid: string;
  txt: string;
  dt: string;
  lk: number;
  rt: number;
  x: number;
  y: number;
  e: number;
  r: number;
  u: string;
  c: string;
  a?: string;  // annotation for essential tweets
}

interface StrandMeta {
  title: string;
  label: string;
  summary: string;
  username: string;
  color: string;
}

interface AtlasData {
  tweets: Tweet[];
  strands: Record<string, StrandMeta>;
  palette: string[];
}

// Nausicaa palette (Toxic Forest colors) - base colors to interpolate between
const NAUSICAA_COLORS = [
  [107, 63, 160],  // #6b3fa0
  [131, 82, 181],  // #8352b5
  [94, 79, 162],   // #5e4fa2
  [50, 136, 189],  // #3288bd
  [33, 160, 160],  // #21a0a0
  [65, 182, 171],  // #41b6ab
  [102, 194, 164], // #66c2a4
  [120, 198, 121], // #78c679
  [173, 221, 142], // #addd8e
  [244, 167, 66],  // #f4a742
  [217, 79, 107],  // #d94f6b
  [181, 69, 110],  // #b5456e
  [140, 71, 153],  // #8c4799
];

// Interpolate between nausicaa colors based on continuous value t (0-1)
function interpolateNausicaaColor(t: number): string {
  t = ((t % 1) + 1) % 1;
  const n = NAUSICAA_COLORS.length;
  const scaled = t * n;
  const idx = Math.floor(scaled);
  const frac = scaled - idx;
  const c1 = NAUSICAA_COLORS[idx % n];
  const c2 = NAUSICAA_COLORS[(idx + 1) % n];
  const r = Math.round(c1[0] + (c2[0] - c1[0]) * frac);
  const g = Math.round(c1[1] + (c2[1] - c1[1]) * frac);
  const b = Math.round(c1[2] + (c2[2] - c1[2]) * frac);
  return `rgb(${r},${g},${b})`;
}

// Get strand colors - one color per strand, interpolated from nausicaa
function getStrandColors(tweets: Tweet[]): Map<string, string> {
  const centerX = tweets.reduce((sum, t) => sum + t.x, 0) / tweets.length;
  const centerY = tweets.reduce((sum, t) => sum + t.y, 0) / tweets.length;

  const strandTweets = new Map<string, Tweet[]>();
  for (const tweet of tweets) {
    const list = strandTweets.get(tweet.sid) || [];
    list.push(tweet);
    strandTweets.set(tweet.sid, list);
  }

  const strandColors = new Map<string, string>();

  for (const [strandId, strandList] of strandTweets) {
    const important = strandList.filter(t => t.e || t.r);
    const toUse = important.length > 0 ? important : strandList;

    const xs = toUse.map(t => t.x).sort((a, b) => a - b);
    const ys = toUse.map(t => t.y).sort((a, b) => a - b);
    const medianX = xs[Math.floor(xs.length / 2)];
    const medianY = ys[Math.floor(ys.length / 2)];

    const angle = Math.atan2(medianY - centerY, medianX - centerX);
    const t = (angle + Math.PI) / (2 * Math.PI);
    strandColors.set(strandId, interpolateNausicaaColor(t));
  }

  return strandColors;
}

// Extract timestamp from Twitter snowflake ID
function getTimestampFromTweetId(tweetId: string): number {
  const TWITTER_EPOCH = 1288834974657;
  const id = BigInt(tweetId);
  return Number((id >> BigInt(22)) + BigInt(TWITTER_EPOCH)) / 1000;
}

// Adjust saturation based on age
function adjustSaturationByAge(
  color: string,
  timestamp: number,
  minTs: number,
  maxTs: number
): string {
  const match = color.match(/rgb\((\d+),(\d+),(\d+)\)/);
  if (!match) return color;

  let r = parseInt(match[1]) / 255;
  let g = parseInt(match[2]) / 255;
  let b = parseInt(match[3]) / 255;

  const ageFactor = maxTs === minTs ? 1 : (timestamp - minTs) / (maxTs - minTs);
  const satMult = 0.3 + ageFactor * 0.7;

  const gray = 0.299 * r + 0.587 * g + 0.114 * b;
  r = gray + (r - gray) * satMult;
  g = gray + (g - gray) * satMult;
  b = gray + (b - gray) * satMult;

  return `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
}

// Compute alpha shape (concave hull) using Delaunay triangulation
function computeAlphaShape(points: [number, number][], alpha: number): [number, number][] | null {
  if (points.length < 3) return null;
  if (points.length === 3) {
    return [...points, points[0]];
  }

  try {
    const delaunay = Delaunay.from(points);
    const triangles = delaunay.triangles;
    const edges = new Map<string, { count: number; p1: [number, number]; p2: [number, number] }>();

    for (let i = 0; i < triangles.length; i += 3) {
      const i0 = triangles[i];
      const i1 = triangles[i + 1];
      const i2 = triangles[i + 2];

      const p0 = points[i0];
      const p1 = points[i1];
      const p2 = points[i2];

      const ax = p1[0] - p0[0], ay = p1[1] - p0[1];
      const bx = p2[0] - p0[0], by = p2[1] - p0[1];
      const d = 2 * (ax * by - ay * bx);

      if (Math.abs(d) < 1e-10) continue;

      const ux = (by * (ax * ax + ay * ay) - ay * (bx * bx + by * by)) / d;
      const uy = (ax * (bx * bx + by * by) - bx * (ax * ax + ay * ay)) / d;
      const circumradius = Math.sqrt(ux * ux + uy * uy);

      if (circumradius > 1 / alpha) continue;

      const triEdges: [number, number][] = [[i0, i1], [i1, i2], [i2, i0]];
      for (const [a, b] of triEdges) {
        const key = a < b ? `${a}-${b}` : `${b}-${a}`;
        const existing = edges.get(key);
        if (existing) {
          existing.count++;
        } else {
          edges.set(key, { count: 1, p1: points[a], p2: points[b] });
        }
      }
    }

    const boundaryEdges: Array<{ p1: [number, number]; p2: [number, number] }> = [];
    for (const edge of edges.values()) {
      if (edge.count === 1) {
        boundaryEdges.push(edge);
      }
    }

    if (boundaryEdges.length === 0) return null;

    const polygon: [number, number][] = [boundaryEdges[0].p1, boundaryEdges[0].p2];
    const usedEdges = new Set([0]);

    while (usedEdges.size < boundaryEdges.length) {
      const lastPoint = polygon[polygon.length - 1];
      let found = false;

      for (let i = 0; i < boundaryEdges.length; i++) {
        if (usedEdges.has(i)) continue;
        const edge = boundaryEdges[i];

        const dist1 = Math.hypot(edge.p1[0] - lastPoint[0], edge.p1[1] - lastPoint[1]);
        const dist2 = Math.hypot(edge.p2[0] - lastPoint[0], edge.p2[1] - lastPoint[1]);

        if (dist1 < 0.0001) {
          polygon.push(edge.p2);
          usedEdges.add(i);
          found = true;
          break;
        } else if (dist2 < 0.0001) {
          polygon.push(edge.p1);
          usedEdges.add(i);
          found = true;
          break;
        }
      }

      if (!found) break;
    }

    return polygon.length >= 3 ? polygon : null;
  } catch {
    return null;
  }
}

// Compute convex hull as fallback
function computeConvexHull(points: [number, number][]): [number, number][] | null {
  if (points.length < 3) return null;
  const delaunay = Delaunay.from(points);
  const hull = delaunay.hull;
  if (hull.length < 3) return null;
  const hullPoints: [number, number][] = [];
  for (const idx of hull) {
    hullPoints.push(points[idx]);
  }
  hullPoints.push(hullPoints[0]);
  return hullPoints;
}

// Format hover text
function formatHoverText(tweet: Tweet, strands: Record<string, StrandMeta>): string {
  const meta = strands[tweet.sid];
  const title = meta?.title || `Strand ${tweet.sid.slice(-8)}`;
  const summary = meta?.summary || '';

  const wrapText = (text: string, maxLen: number = 40): string => {
    const words = text.split(' ');
    const lines: string[] = [];
    let currentLine = '';

    for (const word of words) {
      if ((currentLine + ' ' + word).length > maxLen && currentLine) {
        lines.push(currentLine);
        currentLine = word;
      } else {
        currentLine = currentLine ? currentLine + ' ' + word : word;
      }
    }
    if (currentLine) lines.push(currentLine);
    return lines.join('<br>');
  };

  let hover = `<b style="color:#000">${wrapText(title, 35)}</b><br>`;
  hover += `<span style="color:#222">@${tweet.u}</span>`;
  if (tweet.dt) hover += ` · ${tweet.dt}`;
  hover += `<br>`;

  if (tweet.lk || tweet.rt) {
    hover += `<span style="color:#333">${tweet.lk.toLocaleString()} likes · ${tweet.rt.toLocaleString()} RTs</span><br>`;
  }

  hover += `<br><span style="color:#111">${wrapText(tweet.txt.replace(/\n/g, ' '), 40)}</span>`;

  // Show annotation for essential tweets, otherwise show strand summary
  if (tweet.a && tweet.e) {
    hover += `<br><br><span style="color:#1a5f1a; font-weight:500">${wrapText(tweet.a, 40)}</span>`;
  } else if (summary) {
    const shortSummary = summary.slice(0, 150) + (summary.length > 150 ? '...' : '');
    hover += `<br><br><span style="color:#444; font-style:italic">${wrapText(shortSummary, 40)}</span>`;
  }

  return hover;
}

// Control panel component
function ControlPanel({
  params,
  setParams,
}: {
  params: Parameters;
  setParams: (p: Parameters) => void;
}) {
  return (
    <div className="bg-white border-b border-gray-200 p-4 flex flex-wrap gap-6 items-center text-sm">
      <BackButton fallbackHref="/best-strands" />
      {/* Edges */}
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            checked={params.showEdges}
            onChange={(e) => setParams({ ...params, showEdges: e.target.checked })}
            className="rounded"
          />
          <span className="font-medium text-gray-700">Edges</span>
        </label>
        {params.showEdges && (
          <>
            <span className="text-xs text-gray-500">dist:</span>
            <input
              type="range"
              min="0.5"
              max="5"
              step="0.25"
              value={params.edgeThreshold}
              onChange={(e) => setParams({ ...params, edgeThreshold: parseFloat(e.target.value) })}
              className="w-20"
            />
            <span className="text-xs text-gray-500 w-6">{params.edgeThreshold}</span>
          </>
        )}
      </div>

      {/* Envelopes */}
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            checked={params.showEnvelopes}
            onChange={(e) => setParams({ ...params, showEnvelopes: e.target.checked })}
            className="rounded"
          />
          <span className="font-medium text-gray-700">Envelopes</span>
        </label>
        {params.showEnvelopes && (
          <>
            <span className="text-xs text-gray-500">tightness:</span>
            <input
              type="range"
              min="0.5"
              max="3"
              step="0.1"
              value={params.alphaValue}
              onChange={(e) => setParams({ ...params, alphaValue: parseFloat(e.target.value) })}
              className="w-20"
            />
            <span className="text-xs text-gray-500 w-6">{params.alphaValue}</span>
          </>
        )}
      </div>

      {/* Strand Labels */}
      <label className="flex items-center gap-1 cursor-pointer">
        <input
          type="checkbox"
          checked={params.showRootLabels}
          onChange={(e) => setParams({ ...params, showRootLabels: e.target.checked })}
          className="rounded"
        />
        <span className="font-medium text-gray-700">Strand Labels</span>
      </label>

      {/* Label Percentile */}
      {params.showRootLabels && (
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-700">Top Labels:</label>
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={100 - params.labelPercentile}
            onChange={(e) => setParams({ ...params, labelPercentile: 100 - parseFloat(e.target.value) })}
            className="w-20"
          />
          <span className="text-xs text-gray-500 w-10">{100 - params.labelPercentile}%</span>
        </div>
      )}

      {/* Edge Opacity */}
      <div className="flex items-center gap-2">
        <label className="font-medium text-gray-700">Edge Opacity:</label>
        <input
          type="range"
          min="0"
          max="0.6"
          step="0.05"
          value={params.edgeOpacity}
          onChange={(e) => setParams({ ...params, edgeOpacity: parseFloat(e.target.value) })}
          className="w-16"
        />
        <span className="text-xs text-gray-500 w-8">{params.edgeOpacity.toFixed(2)}</span>
      </div>

      {/* Fill Opacity */}
      <div className="flex items-center gap-2">
        <label className="font-medium text-gray-700">Fill Opacity:</label>
        <input
          type="range"
          min="0"
          max="0.4"
          step="0.025"
          value={params.envelopeFillOpacity}
          onChange={(e) => setParams({ ...params, envelopeFillOpacity: parseFloat(e.target.value) })}
          className="w-16"
        />
        <span className="text-xs text-gray-500 w-8">{params.envelopeFillOpacity.toFixed(2)}</span>
      </div>
    </div>
  );
}

interface Parameters {
  showEdges: boolean;
  edgeThreshold: number;
  showEnvelopes: boolean;
  alphaValue: number;
  showRootLabels: boolean;
  edgeOpacity: number;
  envelopeFillOpacity: number;
  labelPercentile: number;
}

export function AtlasClient() {
  const [data, setData] = useState<AtlasData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStrandId, setSelectedStrandId] = useState<string | null>(null);
  const [params, setParams] = useState<Parameters>({
    showEdges: true,
    edgeThreshold: 1.5,
    showEnvelopes: true,
    alphaValue: 1.5,
    showRootLabels: true,
    edgeOpacity: 0.25,
    envelopeFillOpacity: 0.15,
    labelPercentile: 80,
  });

  // Load data
  useEffect(() => {
    fetch('/atlas_data.json')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load data');
        return res.json();
      })
      .then((json: AtlasData) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Compute strand colors
  const strandColors = useMemo(() => {
    if (!data) return new Map<string, string>();
    return getStrandColors(data.tweets);
  }, [data]);

  // Get strand scores from data
  const strandScores = useMemo(() => {
    if (!data) return { scores: new Map<string, number>(), threshold: () => 0 };

    const scores = new Map<string, number>();
    for (const [strandId, meta] of Object.entries(data.strands)) {
      const score = (meta as StrandMeta & { score?: number }).score ?? 0;
      scores.set(strandId, score);
    }

    const sortedScores = [...scores.values()].sort((a, b) => a - b);
    const threshold = (percentile: number) => {
      if (sortedScores.length === 0) return 0;
      const idx = Math.floor((percentile / 100) * sortedScores.length);
      return sortedScores[Math.min(idx, sortedScores.length - 1)];
    };

    return { scores, threshold };
  }, [data]);

  const getColor = useMemo(() => {
    return (tweet: Tweet) => strandColors.get(tweet.sid) || 'gray';
  }, [strandColors]);

  const getStrandColor = useMemo(() => {
    return (strandId: string) => strandColors.get(strandId) || 'rgb(128,128,128)';
  }, [strandColors]);

  // Compute alpha shape envelopes
  const strandEnvelopes = useMemo(() => {
    if (!data || !params.showEnvelopes) return new Map<string, [number, number][]>();

    const envelopes = new Map<string, [number, number][]>();
    const strandTweets = new Map<string, Tweet[]>();

    for (const t of data.tweets) {
      const list = strandTweets.get(t.sid) || [];
      list.push(t);
      strandTweets.set(t.sid, list);
    }

    for (const [strandId, tweets] of strandTweets) {
      const important = tweets.filter(t => t.e || t.r);
      if (important.length < 3) continue;

      const points: [number, number][] = important.map(t => [t.x, t.y]);
      let envelope = computeAlphaShape(points, params.alphaValue);
      if (!envelope) {
        envelope = computeConvexHull(points);
      }
      if (envelope) {
        envelopes.set(strandId, envelope);
      }
    }

    return envelopes;
  }, [data, params.showEnvelopes, params.alphaValue]);

  // Track if a point was clicked (to distinguish from background clicks)
  const pointClickedRef = useRef(false);

  // Handle Plotly initialization - attach native click events
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handlePlotInitialized = useCallback((figure: any, graphDiv: any) => {
    // Point click - select/toggle strand
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    graphDiv.on('plotly_click', (event: any) => {
      const point = event?.points?.[0];
      if (point?.customdata) {
        pointClickedRef.current = true;
        const strandId = point.customdata;
        setSelectedStrandId(prev => prev === strandId ? null : strandId);
      }
    });

    // Background click - clear selection
    // Use mousedown on the plot area to detect clicks that don't hit points
    const plotArea = graphDiv.querySelector('.plotly');
    if (plotArea) {
      plotArea.addEventListener('click', () => {
        // If a point was clicked, Plotly's handler already ran
        if (pointClickedRef.current) {
          pointClickedRef.current = false;
          return;
        }
        // Background click - clear selection
        setSelectedStrandId(null);
      });
    }
  }, []);

  // Simple click handler (backup for react-plotly.js onClick prop)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handlePlotClick = useCallback((event: any) => {
    const point = event?.points?.[0];
    if (point?.customdata) {
      pointClickedRef.current = true;
      const strandId = point.customdata;
      setSelectedStrandId(prev => prev === strandId ? null : strandId);
    }
  }, []);

  // Build plot traces - includes selection-based styling
  const traces = useMemo(() => {
    if (!data) return [];

    const tweets = data.tweets;
    const strands = data.strands;
    const traces: PlotlyTrace[] = [];

    const regular = tweets.filter((t) => !t.e && !t.r);
    const essential = tweets.filter((t) => t.e && !t.r);
    const root = tweets.filter((t) => t.r);

    // Helper for opacity based on selection
    const sel = selectedStrandId;

    // 1. Envelopes - split into selected and non-selected for efficiency
    if (params.showEnvelopes && params.envelopeFillOpacity > 0) {
      // If selection active, render selected envelope separately for highlighting
      if (sel && strandEnvelopes.has(sel)) {
        const envelope = strandEnvelopes.get(sel)!;
        const color = getStrandColor(sel);
        const rgbMatch = color.match(/rgb\((\d+),(\d+),(\d+)\)/);
        if (rgbMatch) {
          const [, r, g, b] = rgbMatch;
          traces.push({
            type: 'scatter',
            x: envelope.map((c) => c[0]),
            y: envelope.map((c) => c[1]),
            mode: 'lines',
            fill: 'toself',
            fillcolor: `rgba(${r},${g},${b},${params.envelopeFillOpacity * 2})`,
            line: { color: `rgba(${r},${g},${b},0.8)`, width: 2 },
            showlegend: false,
            hoverinfo: 'skip',
            customdata: envelope.map(() => sel),
          } as PlotlyTrace);
        }
      }

      // All other envelopes in a single batch (dimmed if selection active)
      const dimmedOpacity = sel ? params.envelopeFillOpacity * 0.2 : params.envelopeFillOpacity;
      const borderOpacity = sel ? 0.15 : 0.5;
      for (const [strandId, envelope] of strandEnvelopes) {
        if (sel === strandId) continue; // Already rendered above
        const color = getStrandColor(strandId);
        const rgbMatch = color.match(/rgb\((\d+),(\d+),(\d+)\)/);
        if (!rgbMatch) continue;
        const [, r, g, b] = rgbMatch;

        traces.push({
          type: 'scatter',
          x: envelope.map((c) => c[0]),
          y: envelope.map((c) => c[1]),
          mode: 'lines',
          fill: 'toself',
          fillcolor: `rgba(${r},${g},${b},${dimmedOpacity})`,
          line: { color: `rgba(${r},${g},${b},${borderOpacity})`, width: 1 },
          showlegend: false,
          hoverinfo: 'skip',
          customdata: envelope.map(() => strandId),
        } as PlotlyTrace);
      }
    }

    // 2. Edges - consolidated into 2 traces (selected + others) for performance
    if (params.showEdges && params.edgeOpacity > 0) {
      const strandImportant = new Map<string, Tweet[]>();
      for (const t of tweets) {
        if (t.e || t.r) {
          const list = strandImportant.get(t.sid) || [];
          list.push(t);
          strandImportant.set(t.sid, list);
        }
      }

      // Collect all edges, separating selected strand if any
      const selectedEdgeX: (number | null)[] = [];
      const selectedEdgeY: (number | null)[] = [];
      const otherEdgeX: (number | null)[] = [];
      const otherEdgeY: (number | null)[] = [];
      const otherEdgeColors: (string | null)[] = [];
      const otherEdgeCustomdata: (string | null)[] = [];

      for (const [strandId, strandTweets] of strandImportant) {
        if (strandTweets.length < 2) continue;

        const sorted = [...strandTweets].sort((a, b) => a.dt.localeCompare(b.dt));
        const color = getStrandColor(strandId);
        const isSelected = sel === strandId;

        for (let i = 0; i < sorted.length - 1; i++) {
          const t1 = sorted[i];
          const t2 = sorted[i + 1];
          const dist = Math.sqrt((t2.x - t1.x) ** 2 + (t2.y - t1.y) ** 2);

          if (dist <= params.edgeThreshold) {
            if (isSelected) {
              selectedEdgeX.push(t1.x, t2.x, null);
              selectedEdgeY.push(t1.y, t2.y, null);
            } else {
              otherEdgeX.push(t1.x, t2.x, null);
              otherEdgeY.push(t1.y, t2.y, null);
              otherEdgeColors.push(color, color, null);
              otherEdgeCustomdata.push(strandId, strandId, null);
            }
          }
        }
      }

      // Non-selected edges in one trace
      if (otherEdgeX.length > 0) {
        traces.push({
          type: 'scattergl',
          x: otherEdgeX,
          y: otherEdgeY,
          mode: 'lines',
          line: { color: otherEdgeColors, width: 1.5 },
          opacity: sel ? params.edgeOpacity * 0.1 : params.edgeOpacity,
          showlegend: false,
          hoverinfo: 'skip',
          customdata: otherEdgeCustomdata,
        } as PlotlyTrace);
      }

      // Selected strand edges highlighted
      if (sel && selectedEdgeX.length > 0) {
        traces.push({
          type: 'scattergl',
          x: selectedEdgeX,
          y: selectedEdgeY,
          mode: 'lines',
          line: { color: getStrandColor(sel), width: 3 },
          opacity: Math.min(params.edgeOpacity * 3, 0.9),
          showlegend: false,
          hoverinfo: 'skip',
          customdata: selectedEdgeX.map(() => sel),
        } as PlotlyTrace);
      }
    }

    // 3. Regular tweets
    if (regular.length > 0) {
      traces.push({
        type: 'scattergl',
        x: regular.map((t) => t.x),
        y: regular.map((t) => t.y),
        mode: 'markers',
        name: 'Tweets',
        text: regular.map((t) => formatHoverText(t, strands)),
        customdata: regular.map((t) => t.sid),
        hoverinfo: 'text',
        marker: {
          size: 5,
          color: regular.map(getColor),
          opacity: sel ? regular.map(t => t.sid === sel ? 0.6 : 0.05) : 0.3,
        },
      } as PlotlyTrace);
    }

    // 4. Essential tweets
    if (essential.length > 0) {
      const timestamps = essential.map((t) => getTimestampFromTweetId(t.id));
      const minTs = Math.min(...timestamps);
      const maxTs = Math.max(...timestamps);

      const colors = essential.map((t, idx) => {
        const baseColor = getColor(t);
        return adjustSaturationByAge(baseColor, timestamps[idx], minTs, maxTs);
      });

      traces.push({
        type: 'scattergl',
        x: essential.map((t) => t.x),
        y: essential.map((t) => t.y),
        mode: 'markers',
        name: 'Essential',
        text: essential.map((t) => formatHoverText(t, strands)),
        customdata: essential.map((t) => t.sid),
        hoverinfo: 'text',
        marker: {
          size: sel ? essential.map(t => t.sid === sel ? 14 : 6) : 10,
          color: colors,
          opacity: sel ? essential.map(t => t.sid === sel ? 1.0 : 0.15) : 0.9,
          line: { color: 'rgba(0,0,0,0.3)', width: 1 },
        },
      } as PlotlyTrace);
    }

    // 5. Root tweets
    if (root.length > 0) {
      traces.push({
        type: 'scattergl',
        x: root.map((t) => t.x),
        y: root.map((t) => t.y),
        mode: 'markers',
        name: 'Root',
        text: root.map((t) => formatHoverText(t, strands)),
        customdata: root.map((t) => t.sid),
        hoverinfo: 'text',
        marker: {
          size: sel ? root.map(t => t.sid === sel ? 20 : 10) : 14,
          symbol: 'diamond',
          color: root.map(getColor),
          opacity: sel ? root.map(t => t.sid === sel ? 1.0 : 0.15) : 1.0,
          line: { color: 'rgba(0,0,0,0.5)', width: 2 },
        },
      } as PlotlyTrace);
    }

    return traces;
  }, [data, getColor, getStrandColor, params, strandEnvelopes, selectedStrandId]);

  const layout: Partial<PlotlyLayout> = useMemo(() => {
    const rootTweets = data?.tweets.filter(t => t.r) || [];
    const scoreThreshold = strandScores.threshold(params.labelPercentile);
    const annotationTweets = rootTweets.filter(t => (strandScores.scores.get(t.sid) || 0) >= scoreThreshold);

    return {
      title: {
        text: 'Strand Tweet Atlas',
        font: { size: 18, color: '#333' },
      },
      xaxis: {
        title: '',
        showgrid: true,
        gridcolor: '#eee',
        scaleanchor: 'y',
        scaleratio: 1,
        zeroline: false,
      },
      yaxis: {
        title: '',
        showgrid: true,
        gridcolor: '#eee',
        zeroline: false,
      },
      showlegend: true,
      legend: {
        x: 1,
        y: 1,
        xanchor: 'right',
        bgcolor: 'rgba(255,255,255,0.8)',
      },
      paper_bgcolor: '#fafafa',
      plot_bgcolor: '#fafafa',
      dragmode: 'pan',
      hovermode: 'closest',
      margin: { t: 50, b: 30, l: 30, r: 30 },
      hoverlabel: {
        bgcolor: 'white',
        bordercolor: '#ddd',
        font: { size: 11, family: 'system-ui, sans-serif' },
      },
      uirevision: 'constant',
      annotations: params.showRootLabels && data ? annotationTweets.map(t => {
        const meta = data.strands[t.sid];
        const label = meta?.label || meta?.title || `@${t.u}`;
        return {
          x: t.x,
          y: t.y,
          yshift: 18,  // Pixel offset - stays constant regardless of zoom
          text: label,
          showarrow: false,
          font: { size: 10, color: '#2a2a2a', family: 'system-ui, sans-serif' },
          bgcolor: 'rgba(255,255,255,0.85)',
          borderpad: 3,
          xanchor: 'center',
          yanchor: 'bottom',
        };
      }) : [],
    };
  }, [params.showRootLabels, params.labelPercentile, data, strandScores]);

  const config: Partial<PlotlyConfig> = useMemo(() => ({
    scrollZoom: true,
    displayModeBar: true,
    displaylogo: false,
    responsive: true,
    toImageButtonOptions: {
      format: 'png',
      filename: 'strand_atlas',
      height: 1080,
      width: 1920,
      scale: 2,
    },
  }), []);

  // Clear selection handler
  const handleClearSelection = useCallback(() => {
    setSelectedStrandId(null);
  }, []);

  // Compute stats
  const stats = useMemo(() => {
    if (!data) return null;
    const strandCounts = new Map<string, number>();
    for (const t of data.tweets) {
      strandCounts.set(t.sid, (strandCounts.get(t.sid) || 0) + 1);
    }
    const counts = [...strandCounts.values()].sort((a, b) => a - b);
    const totalTweets = data.tweets.length;
    const totalStrands = strandCounts.size;
    const minTweets = counts[0] || 0;
    const maxTweets = counts[counts.length - 1] || 0;
    const avgTweets = totalStrands > 0 ? Math.round(totalTweets / totalStrands) : 0;
    const essentialCount = data.tweets.filter(t => t.e).length;
    return { totalTweets, totalStrands, minTweets, maxTweets, avgTweets, essentialCount };
  }, [data]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading atlas data (~12MB)...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center text-red-600">
          <p className="font-medium">Error loading data</p>
          <p className="text-sm">{error}</p>
        </div>
      </div>
    );
  }

  // Get selected strand info for display
  const selectedStrandInfo = selectedStrandId && data ? data.strands[selectedStrandId] : null;

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <ControlPanel params={params} setParams={setParams} />
      {stats && (
        <div className="bg-gray-100 border-b border-gray-200 px-4 py-2 flex flex-wrap gap-4 text-xs text-gray-600">
          <span><strong>{stats.totalTweets.toLocaleString()}</strong> tweets</span>
          <span><strong>{stats.totalStrands}</strong> strands</span>
          <span><strong>{stats.essentialCount.toLocaleString()}</strong> essential</span>
          <span className="text-gray-400">|</span>
          <span>per strand: <strong>{stats.minTweets}</strong>–<strong>{stats.maxTweets}</strong> (avg {stats.avgTweets})</span>
        </div>
      )}
      {selectedStrandInfo && (
        <div className="bg-white border-b border-gray-200 px-4 py-2 flex items-center gap-4 text-sm">
          <span className="font-medium text-gray-700">Selected:</span>
          <span className="text-gray-900">{selectedStrandInfo.title}</span>
          <span className="text-gray-500">@{selectedStrandInfo.username}</span>
          <button
            onClick={handleClearSelection}
            className="ml-auto px-3 py-1 bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded text-xs transition-colors"
          >
            Clear selection
          </button>
        </div>
      )}
      <div className="flex-1 p-4">
        <Plot
          data={traces}
          layout={layout}
          config={config}
          style={{ width: '100%', height: selectedStrandInfo ? 'calc(100vh - 190px)' : 'calc(100vh - 150px)' }}
          useResizeHandler
          onClick={handlePlotClick}
          onInitialized={handlePlotInitialized}
        />
      </div>
    </div>
  );
}
