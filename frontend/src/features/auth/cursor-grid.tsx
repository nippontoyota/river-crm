"use client";

import { useEffect, useRef } from "react";

type Falloff = "linear" | "smooth" | "sharp";

interface CursorGridProps {
  cellSize?: number;
  color?: string;
  radius?: number;
  falloff?: Falloff;
  holdTime?: number;
  fadeDuration?: number;
  lineWidth?: number;
  maxOpacity?: number;
  fillOpacity?: number;
  gridOpacity?: number;
  cellRadius?: number;
  clickPulse?: boolean;
  pulseSpeed?: number;
  className?: string;
}

interface Pulse {
  x: number;
  y: number;
  t0: number;
}

const falloffCurves: Record<Falloff, (value: number) => number> = {
  linear: (value) => value,
  smooth: (value) => value * value * (3 - 2 * value),
  sharp: (value) => value * value * value,
};

const hexToRgb = (hex: string): [number, number, number] => {
  const raw = hex.replace("#", "");
  const normalized = raw.length === 3 ? raw.split("").map((character) => character + character).join("") : raw;
  const value = Number.parseInt(normalized.slice(0, 6), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
};

export function CursorGrid({
  cellSize = 70,
  color = "#8ce0c6",
  radius = 140,
  falloff = "smooth",
  holdTime = 400,
  fadeDuration = 800,
  lineWidth = 1.2,
  maxOpacity = 1,
  fillOpacity = 0,
  gridOpacity = 0,
  cellRadius = 0,
  clickPulse = true,
  pulseSpeed = 600,
  className = "",
}: CursorGridProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    const context = canvas.getContext("2d");
    if (!context) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const [red, green, blue] = hexToRgb(color);
    const pulses: Pulse[] = [];
    let columns = 0;
    let rows = 0;
    let offsetX = 0;
    let offsetY = 0;
    let alphas = new Float32Array(0);
    let touched = new Float64Array(0);
    let width = 0;
    let height = 0;
    let animationFrame = 0;
    let running = false;
    let lastFrame = 0;

    const rebuild = () => {
      width = container.offsetWidth;
      height = container.offsetHeight;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      columns = Math.ceil(width / cellSize) + 1;
      rows = Math.ceil(height / cellSize) + 1;
      offsetX = (width - columns * cellSize) / 2;
      offsetY = (height - rows * cellSize) / 2;
      alphas = new Float32Array(columns * rows);
      touched = new Float64Array(columns * rows);
    };

    const cellCenter = (index: number): [number, number] => [
      offsetX + (index % columns) * cellSize + cellSize / 2,
      offsetY + Math.floor(index / columns) * cellSize + cellSize / 2,
    ];

    const energize = (x: number, y: number) => {
      const effectRadius = Math.max(radius, 1);
      const ease = falloffCurves[falloff];
      const now = performance.now();
      const minimumColumn = Math.max(0, Math.floor((x - effectRadius - offsetX) / cellSize));
      const maximumColumn = Math.min(columns - 1, Math.floor((x + effectRadius - offsetX) / cellSize));
      const minimumRow = Math.max(0, Math.floor((y - effectRadius - offsetY) / cellSize));
      const maximumRow = Math.min(rows - 1, Math.floor((y + effectRadius - offsetY) / cellSize));

      for (let row = minimumRow; row <= maximumRow; row++) {
        for (let column = minimumColumn; column <= maximumColumn; column++) {
          const index = row * columns + column;
          const [centerX, centerY] = cellCenter(index);
          const distance = Math.hypot(centerX - x, centerY - y);
          if (distance > effectRadius) continue;
          const level = ease(1 - distance / effectRadius) * maxOpacity;
          if (level > alphas[index]) alphas[index] = level;
          touched[index] = now;
        }
      }
    };

    const draw = (now: number) => {
      const delta = Math.min(now - lastFrame, 50);
      lastFrame = now;
      context.clearRect(0, 0, width, height);

      if (gridOpacity > 0) {
        context.strokeStyle = `rgba(${red}, ${green}, ${blue}, ${gridOpacity})`;
        context.lineWidth = 1;
        context.beginPath();
        for (let column = 0; column <= columns; column++) {
          const x = Math.round(offsetX + column * cellSize) + 0.5;
          context.moveTo(x, 0);
          context.lineTo(x, height);
        }
        for (let row = 0; row <= rows; row++) {
          const y = Math.round(offsetY + row * cellSize) + 0.5;
          context.moveTo(0, y);
          context.lineTo(width, y);
        }
        context.stroke();
      }

      for (let pulseIndex = pulses.length - 1; pulseIndex >= 0; pulseIndex--) {
        const pulse = pulses[pulseIndex];
        const ringRadius = ((now - pulse.t0) / 1000) * pulseSpeed;
        if (ringRadius > Math.hypot(width, height)) {
          pulses.splice(pulseIndex, 1);
          continue;
        }
        const band = cellSize;
        const minimumColumn = Math.max(0, Math.floor((pulse.x - ringRadius - band - offsetX) / cellSize));
        const maximumColumn = Math.min(columns - 1, Math.floor((pulse.x + ringRadius + band - offsetX) / cellSize));
        const minimumRow = Math.max(0, Math.floor((pulse.y - ringRadius - band - offsetY) / cellSize));
        const maximumRow = Math.min(rows - 1, Math.floor((pulse.y + ringRadius + band - offsetY) / cellSize));

        for (let row = minimumRow; row <= maximumRow; row++) {
          for (let column = minimumColumn; column <= maximumColumn; column++) {
            const index = row * columns + column;
            const [centerX, centerY] = cellCenter(index);
            const distance = Math.hypot(centerX - pulse.x, centerY - pulse.y);
            if (Math.abs(distance - ringRadius) < band / 2 && maxOpacity > alphas[index]) {
              alphas[index] = maxOpacity;
              touched[index] = now;
            }
          }
        }
      }

      let anyVisible = pulses.length > 0;
      const fadeStep = delta / Math.max(fadeDuration, 16);
      const halfCell = cellSize / 2;

      for (let index = 0; index < alphas.length; index++) {
        let alpha = alphas[index];
        if (alpha <= 0) continue;
        if (now - touched[index] > holdTime) {
          alpha = Math.max(0, alpha - fadeStep);
          alphas[index] = alpha;
          if (alpha <= 0) continue;
        }
        anyVisible = true;

        const [centerX, centerY] = cellCenter(index);
        const gradient = context.createRadialGradient(centerX, centerY, halfCell * 0.1, centerX, centerY, cellSize);
        gradient.addColorStop(0, `rgba(${red}, ${green}, ${blue}, ${alpha})`);
        gradient.addColorStop(1, `rgba(${red}, ${green}, ${blue}, 0)`);
        const x = centerX - halfCell + 0.5;
        const y = centerY - halfCell + 0.5;
        const size = cellSize - 1;

        context.beginPath();
        if (cellRadius > 0) context.roundRect(x, y, size, size, cellRadius);
        else context.rect(x, y, size, size);
        if (fillOpacity > 0) {
          context.fillStyle = `rgba(${red}, ${green}, ${blue}, ${alpha * fillOpacity})`;
          context.fill();
        }
        context.strokeStyle = gradient;
        context.lineWidth = lineWidth;
        context.stroke();
      }

      if (anyVisible) animationFrame = requestAnimationFrame(draw);
      else running = false;
    };

    const wake = () => {
      if (running) return;
      running = true;
      lastFrame = performance.now();
      animationFrame = requestAnimationFrame(draw);
    };

    const localPointer = (event: PointerEvent): [number, number] => {
      const bounds = canvas.getBoundingClientRect();
      return [event.clientX - bounds.left, event.clientY - bounds.top];
    };

    const handlePointerMove = (event: PointerEvent) => {
      const [x, y] = localPointer(event);
      energize(x, y);
      wake();
    };

    const handlePointerDown = (event: PointerEvent) => {
      if (!clickPulse) return;
      const [x, y] = localPointer(event);
      pulses.push({ x, y, t0: performance.now() });
      wake();
    };

    const resizeObserver = new ResizeObserver(() => {
      rebuild();
      wake();
    });

    resizeObserver.observe(container);
    rebuild();
    wake();
    container.addEventListener("pointermove", handlePointerMove);
    container.addEventListener("pointerdown", handlePointerDown);

    return () => {
      cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      container.removeEventListener("pointermove", handlePointerMove);
      container.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [cellRadius, cellSize, clickPulse, color, fadeDuration, falloff, fillOpacity, gridOpacity, holdTime, lineWidth, maxOpacity, pulseSpeed, radius]);

  return (
    <div ref={containerRef} className={`cursor-grid${className ? ` ${className}` : ""}`} aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  );
}
