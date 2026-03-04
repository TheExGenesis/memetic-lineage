'use client';

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';

interface StrandPoint {
  seed_tweet_id: string;
  title: string;
  label?: string | null;  // Custom label for chart (overrides title)
  x: number;
  y: number;
  color: string;
  username: string;
  likes: number;
  retweets: number;
  seeds_count: number;
  tweets_count: number;
  full_text: string;
  summary: string;
}

interface SemanticMapData {
  width: number;
  height: number;
  points: StrandPoint[];
  labeled_indices: number[];
}

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  point: StrandPoint | null;
}

export function StrandSemanticMap() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<SemanticMapData | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState>({ visible: false, x: 0, y: 0, point: null });
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const router = useRouter();

  // Time filter state
  const [timeFilterEnabled, setTimeFilterEnabled] = useState(true);
  const [timeRange, setTimeRange] = useState<[number, number]>([0, 0]);
  const sliderRef = useRef<HTMLDivElement>(null);
  const sliderDragRef = useRef<{ startX: number; startRange: [number, number] } | null>(null);
  const [isDraggingSlider, setIsDraggingSlider] = useState(false);

  // Pan and zoom state
  const [zoom, setZoom] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const lastMousePos = useRef({ x: 0, y: 0 });
  const dragStartPos = useRef({ x: 0, y: 0 });
  const hasDragged = useRef(false);

  // Load data
  useEffect(() => {
    fetch('/strand_semantic_map.json')
      .then(res => res.json())
      .then(setData)
      .catch(console.error);
  }, []);

  // Compute timestamps from seed_tweet_ids (Twitter snowflake formula)
  const pointTimestamps = useMemo(() => {
    if (!data) return { timestamps: [] as number[], minTs: 0, maxTs: 0 };
    const TWITTER_EPOCH = BigInt(1288834974657);
    const timestamps = data.points.map(p => {
      const id = BigInt(p.seed_tweet_id);
      return Number((id >> BigInt(22)) + TWITTER_EPOCH) / 1000;
    });
    const minTs = Math.min(...timestamps);
    const maxTs = Math.max(...timestamps);
    return { timestamps, minTs, maxTs };
  }, [data]);

  // Initialize time range when data loads
  useEffect(() => {
    if (pointTimestamps.minTs > 0) {
      setTimeRange([pointTimestamps.minTs, pointTimestamps.maxTs]);
    }
  }, [pointTimestamps]);

  // Calculate scale factors to fit data in container
  const getScaleFactors = useCallback(() => {
    if (!data || !containerRef.current) return null;

    const container = containerRef.current;
    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;

    // Find data bounds
    const xMin = Math.min(...data.points.map(p => p.x));
    const xMax = Math.max(...data.points.map(p => p.x));
    const yMin = Math.min(...data.points.map(p => p.y));
    const yMax = Math.max(...data.points.map(p => p.y));

    // Add padding
    const padding = 40;
    const labelPadding = 50; // Extra top padding for labels

    const scaleX = (containerWidth - padding * 2) / (xMax - xMin);
    const scaleY = (containerHeight - padding - labelPadding) / (yMax - yMin);

    return {
      scaleX,
      scaleY,
      xMin,
      yMin,
      padding,
      labelPadding,
      containerWidth,
      containerHeight,
    };
  }, [data]);

  // Convert data coords to canvas coords (with zoom and pan)
  const toCanvasCoords = useCallback((x: number, y: number) => {
    const scale = getScaleFactors();
    if (!scale) return { cx: 0, cy: 0 };

    // Base coordinates
    let cx = scale.padding + (x - scale.xMin) * scale.scaleX;
    // Flip y axis (canvas y increases downward)
    let cy = scale.labelPadding + (scale.containerHeight - scale.padding - scale.labelPadding) - (y - scale.yMin) * scale.scaleY;

    // Apply zoom (around center) and pan
    const centerX = scale.containerWidth / 2;
    const centerY = scale.containerHeight / 2;
    cx = centerX + (cx - centerX) * zoom + panOffset.x;
    cy = centerY + (cy - centerY) * zoom + panOffset.y;

    return { cx, cy };
  }, [getScaleFactors, zoom, panOffset]);

  // Draw canvas
  useEffect(() => {
    if (!data || !canvasRef.current || !containerRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const container = containerRef.current;
    const dpr = window.devicePixelRatio || 1;

    // Set canvas size
    canvas.width = container.clientWidth * dpr;
    canvas.height = container.clientHeight * dpr;
    canvas.style.width = `${container.clientWidth}px`;
    canvas.style.height = `${container.clientHeight}px`;
    ctx.scale(dpr, dpr);

    // Clear
    ctx.fillStyle = '#fafafa';
    ctx.fillRect(0, 0, container.clientWidth, container.clientHeight);

    const labeledSet = new Set(data.labeled_indices);

    // Draw all points
    data.points.forEach((point, i) => {
      const { cx, cy } = toCanvasCoords(point.x, point.y);
      const isLabeled = labeledSet.has(i);
      const isHovered = hoveredIndex === i;

      // Check if point is in time range
      const inRange = !timeFilterEnabled || (
        pointTimestamps.timestamps[i] >= timeRange[0] &&
        pointTimestamps.timestamps[i] <= timeRange[1]
      );

      if (!inRange && !isHovered) {
        // Dimmed point
        ctx.beginPath();
        ctx.arc(cx, cy, isLabeled ? 4 : 3, 0, Math.PI * 2);
        ctx.fillStyle = point.color;
        ctx.globalAlpha = 0.08;
        ctx.fill();
        ctx.globalAlpha = 1;
        return;
      }

      // Draw circle
      ctx.beginPath();
      ctx.arc(cx, cy, isHovered ? 8 : (isLabeled ? 7 : 5), 0, Math.PI * 2);
      ctx.fillStyle = point.color;
      ctx.globalAlpha = isHovered ? 1 : (isLabeled ? 0.95 : 0.8);
      ctx.fill();

      // Border
      ctx.strokeStyle = isHovered ? '#000' : (isLabeled ? '#1a1a1a' : 'rgba(255,255,255,0.6)');
      ctx.lineWidth = isHovered ? 2.5 : (isLabeled ? 2 : 1);
      ctx.stroke();
      ctx.globalAlpha = 1;
    });

    // Draw labels for labeled points with collision detection
    ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';

    // Calculate all label bounding boxes first
    interface LabelBox {
      index: number;
      text: string;
      cx: number;
      cy: number;
      x: number;
      y: number;
      width: number;
      height: number;
      likes: number;
    }

    const labelBoxes: LabelBox[] = data.labeled_indices
      .filter(i => {
        // Skip labels for out-of-range points
        if (!timeFilterEnabled) return true;
        return pointTimestamps.timestamps[i] >= timeRange[0] &&
               pointTimestamps.timestamps[i] <= timeRange[1];
      })
      .map(i => {
        const point = data.points[i];
        const { cx, cy } = toCanvasCoords(point.x, point.y);
        const text = point.label || point.title;
        const metrics = ctx.measureText(text);
        const textWidth = metrics.width + 8; // padding
        const textHeight = 18;
        const labelY = cy - 22 - textHeight;

        return {
          index: i,
          text,
          cx,
          cy,
          x: cx - textWidth / 2,
          y: labelY,
          width: textWidth,
          height: textHeight,
          likes: point.likes,
        };
      });

    // Sort by likes (highest first) to prioritize popular strands
    labelBoxes.sort((a, b) => b.likes - a.likes);

    // Check if two boxes overlap
    const boxesOverlap = (a: LabelBox, b: LabelBox, padding = 4) => {
      return !(a.x + a.width + padding < b.x ||
               b.x + b.width + padding < a.x ||
               a.y + a.height + padding < b.y ||
               b.y + b.height + padding < a.y);
    };

    // Try alternative positions for a label
    const tryPositions = (box: LabelBox, placed: LabelBox[]): LabelBox | null => {
      // Positions to try: above (default), below, left, right
      const offsets = [
        { dx: 0, dy: 0 },           // above (default)
        { dx: 0, dy: box.cy + 8 - box.y },  // below point
        { dx: -box.width / 2 - 10, dy: box.height / 2 }, // left
        { dx: box.width / 2 + 10, dy: box.height / 2 },  // right
      ];

      for (const offset of offsets) {
        const testBox = {
          ...box,
          x: box.x + offset.dx,
          y: box.y + offset.dy,
        };

        // Check if this position works
        const hasCollision = placed.some(p => boxesOverlap(testBox, p));
        if (!hasCollision) {
          return testBox;
        }
      }

      return null; // No valid position found
    };

    // Place labels, skipping those that would overlap
    const placedLabels: LabelBox[] = [];

    for (const box of labelBoxes) {
      const positioned = tryPositions(box, placedLabels);
      if (positioned) {
        placedLabels.push(positioned);
      }
    }

    // Draw the placed labels
    for (const box of placedLabels) {
      // Background
      ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
      ctx.fillRect(box.x, box.y, box.width, box.height);

      // Text
      ctx.fillStyle = '#333';
      ctx.textAlign = 'center';
      ctx.fillText(box.text, box.x + box.width / 2, box.y + box.height - 4);
    }

  }, [data, hoveredIndex, toCanvasCoords, zoom, panOffset, timeFilterEnabled, timeRange, pointTimestamps]);

  // Store zoom in ref for wheel handler (avoids stale closure)
  const zoomRef = useRef(zoom);
  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);

  // Handle wheel for zoom - use native event listener with passive: false
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // Zoom factor
      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
      const newZoom = Math.min(Math.max(zoomRef.current * zoomFactor, 0.5), 5);

      // Adjust pan to zoom toward mouse position
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const dx = mouseX - centerX;
      const dy = mouseY - centerY;

      setPanOffset(prev => ({
        x: prev.x - dx * (zoomFactor - 1),
        y: prev.y - dy * (zoomFactor - 1),
      }));
      setZoom(newZoom);
    };

    canvas.addEventListener('wheel', handleWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', handleWheel);
  }, [data]);

  // Handle mouse down for pan start
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button === 0) { // Left mouse button
      setIsPanning(true);
      lastMousePos.current = { x: e.clientX, y: e.clientY };
      dragStartPos.current = { x: e.clientX, y: e.clientY };
      hasDragged.current = false;
    }
  }, []);

  // Handle mouse up for pan end
  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  // Handle mouse move for hover and pan
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data || !containerRef.current) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    // Handle panning
    if (isPanning) {
      const dx = e.clientX - lastMousePos.current.x;
      const dy = e.clientY - lastMousePos.current.y;

      // Check if dragged more than 5 pixels from start
      const totalDx = e.clientX - dragStartPos.current.x;
      const totalDy = e.clientY - dragStartPos.current.y;
      if (Math.abs(totalDx) > 5 || Math.abs(totalDy) > 5) {
        hasDragged.current = true;
      }

      setPanOffset(prev => ({ x: prev.x + dx, y: prev.y + dy }));
      lastMousePos.current = { x: e.clientX, y: e.clientY };
      return; // Don't update hover while panning
    }

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Find closest point within threshold (scale threshold with zoom)
    let closestIdx: number | null = null;
    let closestDist = 20 * zoom; // Hover threshold scales with zoom

    data.points.forEach((point, i) => {
      const { cx, cy } = toCanvasCoords(point.x, point.y);
      const dist = Math.sqrt((mouseX - cx) ** 2 + (mouseY - cy) ** 2);
      if (dist < closestDist) {
        closestDist = dist;
        closestIdx = i;
      }
    });

    if (closestIdx !== null) {
      const point = data.points[closestIdx];
      setHoveredIndex(closestIdx);
      setTooltip({
        visible: true,
        x: e.clientX,
        y: e.clientY,
        point,
      });
    } else {
      setHoveredIndex(null);
      setTooltip({ visible: false, x: 0, y: 0, point: null });
    }
  }, [data, toCanvasCoords, isPanning, zoom]);

  const handleMouseLeave = useCallback(() => {
    setHoveredIndex(null);
    setTooltip({ visible: false, x: 0, y: 0, point: null });
    setIsPanning(false);
  }, []);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    // Don't click if we were just dragging
    if (hasDragged.current) return;
    if (!data || !containerRef.current) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Find clicked point (scale threshold with zoom)
    let clickedIdx: number | null = null;
    let closestDist = 15 * zoom;

    data.points.forEach((point, i) => {
      const { cx, cy } = toCanvasCoords(point.x, point.y);
      const dist = Math.sqrt((mouseX - cx) ** 2 + (mouseY - cy) ** 2);
      if (dist < closestDist) {
        closestDist = dist;
        clickedIdx = i;
      }
    });

    if (clickedIdx !== null) {
      const point = data.points[clickedIdx];
      router.push(`/best-strands/${point.seed_tweet_id}`);
    }
  }, [data, toCanvasCoords, router, zoom]);

  // Drag the slider interior to scrub the time window
  const handleSliderDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    if (!sliderRef.current) return;
    sliderDragRef.current = { startX: e.clientX, startRange: [timeRange[0], timeRange[1]] };
    setIsDraggingSlider(true);

    const handleMouseMove = (ev: MouseEvent) => {
      if (!sliderDragRef.current || !sliderRef.current) return;
      const sliderWidth = sliderRef.current.clientWidth;
      const totalRange = pointTimestamps.maxTs - pointTimestamps.minTs;
      if (totalRange === 0 || sliderWidth === 0) return;
      const pxDelta = ev.clientX - sliderDragRef.current.startX;
      const timeDelta = (pxDelta / sliderWidth) * totalRange;
      const windowSize = sliderDragRef.current.startRange[1] - sliderDragRef.current.startRange[0];
      let newStart = sliderDragRef.current.startRange[0] + timeDelta;
      let newEnd = newStart + windowSize;
      if (newStart < pointTimestamps.minTs) {
        newStart = pointTimestamps.minTs;
        newEnd = newStart + windowSize;
      }
      if (newEnd > pointTimestamps.maxTs) {
        newEnd = pointTimestamps.maxTs;
        newStart = newEnd - windowSize;
      }
      setTimeRange([newStart, newEnd]);
    };

    const handleMouseUp = () => {
      sliderDragRef.current = null;
      setIsDraggingSlider(false);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }, [timeRange, pointTimestamps]);

  // Reset view handler
  const handleResetView = useCallback(() => {
    setZoom(1);
    setPanOffset({ x: 0, y: 0 });
  }, []);

  if (!data) {
    return (
      <div className="w-full h-[350px] lg:h-[520px] bg-gray-50 flex items-center justify-center text-gray-400 text-sm border-2 border-gray-200">
        Loading semantic map...
      </div>
    );
  }

  // Format unix timestamp to human-readable date
  const formatTimestamp = (ts: number): string => {
    const d = new Date(ts * 1000);
    return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  };

  const tooltipEl = tooltip.visible && tooltip.point ? (
    <div
      className="fixed z-[9999] pointer-events-none bg-white border border-gray-200 shadow-lg rounded-lg p-3 max-w-sm"
      style={{
        left: tooltip.x + 15,
        top: tooltip.y + 15,
        transform: tooltip.x > window.innerWidth / 2 ? 'translateX(-100%)' : undefined,
      }}
    >
      <div className="font-semibold text-sm mb-1">{tooltip.point.title}</div>
      <div className="text-xs text-gray-600 mb-2">
        @{tooltip.point.username} · ❤️ {tooltip.point.likes.toLocaleString()} · 🔄 {tooltip.point.retweets.toLocaleString()}
      </div>
      {tooltip.point.full_text && (
        <div className="text-xs text-gray-700 mb-2 leading-relaxed">
          {tooltip.point.full_text}
        </div>
      )}
      {tooltip.point.summary && (
        <div className="text-xs text-gray-500 italic leading-relaxed">
          {tooltip.point.summary}
        </div>
      )}
      <div className="text-xs text-gray-400 mt-2">
        {tooltip.point.seeds_count} seeds · {tooltip.point.tweets_count} tweets
      </div>
    </div>
  ) : null;

  return (
    <div className="relative w-full">
      <div
        ref={containerRef}
        className="w-full h-[350px] lg:h-[520px] bg-[#fafafa] border-2 border-black shadow-[4px_4px_0_0_#000] overflow-hidden"
      >
        <canvas
          ref={canvasRef}
          className={`w-full h-full ${isPanning ? 'cursor-grabbing' : 'cursor-grab'}`}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onClick={handleClick}
        />
      </div>
      {/* Reset button - only show when zoomed/panned */}
      {(zoom !== 1 || panOffset.x !== 0 || panOffset.y !== 0) && (
        <button
          onClick={handleResetView}
          className="absolute top-2 right-2 px-2 py-1 text-xs bg-white/90 hover:bg-white border border-gray-300 rounded shadow-sm transition-colors"
          title="Reset view"
        >
          Reset
        </button>
      )}

      {/* Time filter slider */}
      {pointTimestamps.minTs > 0 && (
        <div className="mt-2">
          <div className="flex items-center gap-3 text-sm">
              <span className="text-xs font-medium text-gray-600 w-20 text-right shrink-0">
                {formatTimestamp(timeRange[0])}
              </span>
              <div ref={sliderRef} className="relative flex-1 h-6" style={{ minWidth: '120px' }}>
                <div className="absolute top-1/2 -translate-y-1/2 left-0 right-0 h-1 bg-gray-200 rounded" />
                <div
                  className="absolute top-1/2 -translate-y-1/2 h-4"
                  style={{
                    left: `${((timeRange[0] - pointTimestamps.minTs) / (pointTimestamps.maxTs - pointTimestamps.minTs || 1)) * 100}%`,
                    right: `${100 - ((timeRange[1] - pointTimestamps.minTs) / (pointTimestamps.maxTs - pointTimestamps.minTs || 1)) * 100}%`,
                    cursor: isDraggingSlider ? 'grabbing' : 'grab',
                    zIndex: 2,
                  }}
                  onMouseDown={handleSliderDragStart}
                >
                  <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-1 bg-indigo-400 rounded" />
                </div>
                <input
                  type="range"
                  className="time-slider"
                  min={pointTimestamps.minTs}
                  max={pointTimestamps.maxTs}
                  step={2592000}
                  value={timeRange[0]}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setTimeRange([Math.min(v, timeRange[1] - 2592000), timeRange[1]]);
                  }}
                  style={{ zIndex: timeRange[0] > pointTimestamps.minTs + (pointTimestamps.maxTs - pointTimestamps.minTs) * 0.9 ? 5 : 3 }}
                />
                <input
                  type="range"
                  className="time-slider"
                  min={pointTimestamps.minTs}
                  max={pointTimestamps.maxTs}
                  step={2592000}
                  value={timeRange[1]}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setTimeRange([timeRange[0], Math.max(v, timeRange[0] + 2592000)]);
                  }}
                  style={{ zIndex: 4 }}
                />
              </div>
              <span className="text-xs font-medium text-gray-600 w-20 shrink-0">
                {formatTimestamp(timeRange[1])}
              </span>
            </div>
        </div>
      )}

      {/* Tooltip via portal to escape stacking context */}
      {typeof document !== 'undefined' && tooltipEl && createPortal(tooltipEl, document.body)}
    </div>
  );
}
