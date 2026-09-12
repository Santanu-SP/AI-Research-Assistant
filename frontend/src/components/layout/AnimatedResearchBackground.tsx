import React, { useEffect, useRef } from 'react';
import { THEME_CHANGE_EVENT } from '../../theme';

const MAX_DEVICE_PIXEL_RATIO = 2;
const TARGET_FRAME_INTERVAL = 1000 / 30;

interface FieldPalette {
  rgb: string;
  opacityScale: number;
}

interface ScanDash {
  x: number;
  y: number;
  length: number;
  vertical: boolean;
  phase: number;
}

const createRandom = (seed: number) => {
  let state = seed >>> 0;

  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
};

const clamp = (value: number, minimum = 0, maximum = 1) =>
  Math.min(Math.max(value, minimum), maximum);

const smoothStep = (minimum: number, maximum: number, value: number) => {
  const normalized = clamp((value - minimum) / (maximum - minimum));
  return normalized * normalized * (3 - 2 * normalized);
};

const getFieldPalette = (): FieldPalette => {
  const styles = window.getComputedStyle(document.documentElement);
  const opacityScale = Number.parseFloat(
    styles.getPropertyValue('--research-field-opacity-scale'),
  );

  return {
    rgb: styles.getPropertyValue('--research-field-rgb').trim() || '22, 51, 40',
    opacityScale: Number.isFinite(opacityScale) ? opacityScale : 1,
  };
};

const getGridSpacing = (width: number) => {
  if (width < 640) return 28;
  if (width < 1024) return 34;
  return 40;
};

const getPrimaryCurve = (normalizedX: number, time: number) =>
  0.86 -
  normalizedX * 0.67 +
  Math.sin(normalizedX * Math.PI * 3.1 + time * 0.34) * 0.075;

const createScanDashes = (width: number, height: number): ScanDash[] => {
  const random = createRandom(0xd07f13 + Math.round(width) * 23 + Math.round(height));
  const count = width < 640 ? 6 : width < 1024 ? 9 : 13;

  return Array.from({ length: count }, () => {
    const normalizedX = 0.04 + random() * 0.92;
    const curve = getPrimaryCurve(normalizedX, 0);
    const echoCurve = curve - 0.24;
    const useEcho = normalizedX > 0.42 && random() > 0.46;
    const normalizedY = (useEcho ? echoCurve : curve) + (random() - 0.5) * 0.22;

    return {
      x: normalizedX * width,
      y: clamp(normalizedY, 0.05, 0.95) * height,
      length: 18 + random() * (width < 640 ? 28 : 54),
      vertical: random() > 0.72,
      phase: random() * Math.PI * 2,
    };
  });
};

const drawDotField = (
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  elapsed: number,
  reducedMotion: boolean,
  palette: FieldPalette,
  scanDashes: ScanDash[],
) => {
  context.clearRect(0, 0, width, height);

  const spacing = getGridSpacing(width);
  const columns = Math.ceil(width / spacing) + 2;
  const rows = Math.ceil(height / spacing) + 2;
  const time = reducedMotion ? 4.5 : elapsed / 1000;

  for (let row = -1; row < rows; row += 1) {
    for (let column = -1; column < columns; column += 1) {
      const baseX = column * spacing + spacing * 0.5;
      const baseY = row * spacing + spacing * 0.5;
      const normalizedX = baseX / width;
      const normalizedY = baseY / height;
      const primaryCurve = getPrimaryCurve(normalizedX, time);
      const echoCurve =
        primaryCurve -
        0.24 +
        Math.sin(normalizedX * Math.PI * 4.4 - time * 0.28) * 0.035;
      const primaryDistance = Math.abs(normalizedY - primaryCurve);
      const echoDistance = Math.abs(normalizedY - echoCurve);
      const primaryBand = 1 - smoothStep(0.035, 0.18, primaryDistance);
      const echoGate = smoothStep(0.34, 0.58, normalizedX);
      const echoBand =
        (1 - smoothStep(0.025, 0.14, echoDistance)) * echoGate * 0.78;
      const bandStrength = Math.max(primaryBand, echoBand);

      if (bandStrength < 0.035) continue;

      const horizontalEdge = Math.min(
        smoothStep(0, 0.07, normalizedX),
        smoothStep(1, 0.93, normalizedX),
      );
      const verticalEdge = Math.min(
        smoothStep(0, 0.06, normalizedY),
        smoothStep(1, 0.94, normalizedY),
      );
      const edgeFade = horizontalEdge * verticalEdge;
      const readingColumn =
        smoothStep(0.2, 0.31, normalizedX) *
        smoothStep(0.96, 0.84, normalizedX);
      const topReadingBand =
        smoothStep(0.035, 0.075, normalizedY) *
        (1 - smoothStep(0.08, 0.22, normalizedY));
      const readabilityFade = 1 - readingColumn * topReadingBand * 0.72;
      const flow = reducedMotion
        ? 0.9
        : 0.78 +
          Math.sin(time * 1.05 + column * 0.38 - row * 0.24) * 0.22;
      const broadPulse = reducedMotion
        ? 0.92
        : 0.84 + Math.sin(time * 0.43 - normalizedX * 5.2) * 0.16;
      const emphasis = (column * 7 + row * 11) % 13 === 0;
      const opacity =
        bandStrength *
        edgeFade *
        readabilityFade *
        flow *
        broadPulse *
        (emphasis ? 0.58 : 0.38) *
        palette.opacityScale;

      if (opacity < 0.025) continue;

      const displacement = reducedMotion
        ? 0
        : Math.sin(time * 0.62 + normalizedX * 7.5 + row * 0.055) *
          4.2 *
          bandStrength;
      const x =
        baseX +
        (reducedMotion
          ? 0
          : Math.cos(time * 0.38 + normalizedY * 5.5) * 1.7 * bandStrength);
      const y = baseY + displacement;
      const radius = emphasis ? 1.85 : 1.3;

      if (emphasis && opacity > 0.2) {
        context.beginPath();
        context.arc(x, y, radius * 2.8, 0, Math.PI * 2);
        context.fillStyle = `rgba(${palette.rgb}, ${Math.min(opacity * 0.13, 0.09)})`;
        context.fill();
      }

      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fillStyle = `rgba(${palette.rgb}, ${Math.min(opacity, 0.68)})`;
      context.fill();
    }
  }

  if (reducedMotion) return;

  context.lineCap = 'round';
  scanDashes.forEach((dash) => {
    const pulse = Math.pow(
      Math.max(0, Math.sin(time * 0.72 + dash.phase)),
      7,
    );

    if (pulse < 0.045) return;

    const travel = Math.sin(time * 0.31 + dash.phase) * 10;
    const xStart = dash.x + (dash.vertical ? 0 : travel) - dash.length / 2;
    const yStart = dash.y + (dash.vertical ? travel : 0) - dash.length / 2;
    const xEnd = xStart + (dash.vertical ? 0 : dash.length);
    const yEnd = yStart + (dash.vertical ? dash.length : 0);
    const gradient = context.createLinearGradient(xStart, yStart, xEnd, yEnd);
    const dashOpacity = Math.min(
      pulse * 0.72 * palette.opacityScale,
      0.82,
    );

    gradient.addColorStop(0, `rgba(${palette.rgb}, 0)`);
    gradient.addColorStop(0.24, `rgba(${palette.rgb}, ${dashOpacity})`);
    gradient.addColorStop(0.76, `rgba(${palette.rgb}, ${dashOpacity})`);
    gradient.addColorStop(1, `rgba(${palette.rgb}, 0)`);

    context.beginPath();
    context.moveTo(xStart, yStart);
    context.lineTo(xEnd, yEnd);
    context.strokeStyle = gradient;
    context.lineWidth = 1.5;
    context.stroke();
  });
};

export const AnimatedResearchBackground: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext('2d');
    if (!context) return;

    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    let reducedMotion = reducedMotionQuery.matches;
    let viewportWidth = 0;
    let viewportHeight = 0;
    let scanDashes: ScanDash[] = [];
    let animationFrame: number | null = null;
    let animationStartedAt: number | null = null;
    let lastFrameAt = 0;
    let palette = getFieldPalette();

    const draw = (elapsed: number) => {
      drawDotField(
        context,
        viewportWidth,
        viewportHeight,
        elapsed,
        reducedMotion,
        palette,
        scanDashes,
      );
    };

    const resize = () => {
      viewportWidth = window.innerWidth;
      viewportHeight = window.innerHeight;
      const pixelRatio = Math.min(
        window.devicePixelRatio || 1,
        MAX_DEVICE_PIXEL_RATIO,
      );

      canvas.width = Math.round(viewportWidth * pixelRatio);
      canvas.height = Math.round(viewportHeight * pixelRatio);
      canvas.style.width = `${viewportWidth}px`;
      canvas.style.height = `${viewportHeight}px`;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      scanDashes = createScanDashes(viewportWidth, viewportHeight);
      draw(0);
    };

    const animate = (timestamp: number) => {
      if (document.visibilityState === 'hidden' || reducedMotion) {
        animationFrame = null;
        return;
      }

      animationStartedAt ??= timestamp;
      if (timestamp - lastFrameAt >= TARGET_FRAME_INTERVAL) {
        draw(timestamp - animationStartedAt);
        lastFrameAt = timestamp;
      }
      animationFrame = window.requestAnimationFrame(animate);
    };

    const startAnimation = () => {
      if (
        animationFrame === null &&
        !reducedMotion &&
        document.visibilityState !== 'hidden'
      ) {
        animationFrame = window.requestAnimationFrame(animate);
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
        animationFrame = null;
        return;
      }

      startAnimation();
    };

    const handleMotionPreference = (event: MediaQueryListEvent) => {
      reducedMotion = event.matches;
      if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
      animationFrame = null;
      draw(0);
      startAnimation();
    };

    const handleThemeChange = () => {
      palette = getFieldPalette();
      draw(animationStartedAt === null ? 0 : performance.now() - animationStartedAt);
    };

    resize();
    startAnimation();
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    reducedMotionQuery.addEventListener('change', handleMotionPreference);
    window.addEventListener(THEME_CHANGE_EVENT, handleThemeChange);

    return () => {
      if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      reducedMotionQuery.removeEventListener('change', handleMotionPreference);
      window.removeEventListener(THEME_CHANGE_EVENT, handleThemeChange);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 z-0 block pointer-events-none"
      aria-hidden="true"
    />
  );
};
