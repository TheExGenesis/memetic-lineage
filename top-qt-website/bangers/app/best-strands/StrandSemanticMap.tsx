'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
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

  // Load data
  useEffect(() => {
    fetch('/strand_semantic_map.json')
      .then(res => res.json())
      .then(setData)
      .catch(console.error);
  }, []);

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

  // Convert data coords to canvas coords
  const toCanvasCoords = useCallback((x: number, y: number) => {
    const scale = getScaleFactors();
    if (!scale) return { cx: 0, cy: 0 };

    const cx = scale.padding + (x - scale.xMin) * scale.scaleX;
    // Flip y axis (canvas y increases downward)
    const cy = scale.labelPadding + (scale.containerHeight - scale.padding - scale.labelPadding) - (y - scale.yMin) * scale.scaleY;

    return { cx, cy };
  }, [getScaleFactors]);

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

    const labelBoxes: LabelBox[] = data.labeled_indices.map(i => {
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

  }, [data, hoveredIndex, toCanvasCoords]);

  // Handle mouse move for hover
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data || !containerRef.current) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Find closest point within threshold
    let closestIdx: number | null = null;
    let closestDist = 20; // Hover threshold in pixels

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
  }, [data, toCanvasCoords]);

  const handleMouseLeave = useCallback(() => {
    setHoveredIndex(null);
    setTooltip({ visible: false, x: 0, y: 0, point: null });
  }, []);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data || !containerRef.current) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Find clicked point
    let clickedIdx: number | null = null;
    let closestDist = 15;

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
  }, [data, toCanvasCoords, router]);

  if (!data) {
    return (
      <div className="w-full h-[350px] bg-gray-50 flex items-center justify-center text-gray-400 text-sm">
        Loading semantic map...
      </div>
    );
  }

  return (
    <div className="relative w-full mb-6">
      <div
        ref={containerRef}
        className="w-full h-[350px] bg-[#fafafa] border-2 border-black shadow-[4px_4px_0_0_#000]"
      >
        <canvas
          ref={canvasRef}
          className="w-full h-full cursor-pointer"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onClick={handleClick}
        />
      </div>

      {/* Tooltip */}
      {tooltip.visible && tooltip.point && (
        <div
          className="fixed z-50 pointer-events-none bg-white border border-gray-200 shadow-lg rounded-lg p-3 max-w-sm"
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
      )}
    </div>
  );
}
