import React, { useEffect, useRef } from 'react';
import { THEME_CHANGE_EVENT } from '../../theme';

const MAX_DEVICE_PIXEL_RATIO = 2;
const TARGET_FRAME_INTERVAL = 1000 / 45;
const PATH_COUNT = 3;

interface FieldPalette {
  primaryRgb: string;
  accentRgb: string;
  opacityScale: number;
}

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
    primaryRgb:
      styles.getPropertyValue('--research-field-rgb').trim() || '22, 51, 40',
    accentRgb:
      styles.getPropertyValue('--research-field-accent-rgb').trim() ||
      '66, 119, 94',
    opacityScale: Number.isFinite(opacityScale) ? opacityScale : 1,
  };
};

const getGridSpacing = (width: number) => {
  if (width < 640) return 31;
  if (width < 1024) return 37;
  return 43;
};

const getPathY = (pathIndex: number, normalizedX: number, time: number) => {
  switch (pathIndex) {
    case 0:
      return (
        0.84 -
        normalizedX * 0.61 +
        Math.sin(normalizedX * 7.2 + time * 1.18) * 0.065
      );
    case 1:
      return (
        0.17 +
        normalizedX * 0.58 +
        Math.sin(normalizedX * 6.4 - time * 1.04 + 1.4) * 0.06
      );
    default:
      return (
        0.51 +
        Math.sin(normalizedX * 8.6 + time * 1.28 + 2.1) * 0.085
      );
  }
};

const getPathInfluence = (
  pathIndex: number,
  normalizedX: number,
  normalizedY: number,
  time: number,
) => {
  const distance = Math.abs(
    normalizedY - getPathY(pathIndex, normalizedX, time),
  );
  const width = pathIndex === 2 ? 0.11 : 0.135;
  return 1 - smoothStep(width * 0.22, width, distance);
};

const drawAmbientGlow = (
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  time: number,
  palette: FieldPalette,
) => {
  const glows = [
    {
      x: width * (0.83 + Math.sin(time * 0.18) * 0.035),
      y: height * (0.15 + Math.cos(time * 0.16) * 0.035),
      radius: Math.max(width, height) * 0.48,
      rgb: palette.accentRgb,
      opacity: 0.055,
    },
    {
      x: width * (0.2 + Math.cos(time * 0.15) * 0.035),
      y: height * (0.82 + Math.sin(time * 0.19) * 0.035),
      radius: Math.max(width, height) * 0.42,
      rgb: palette.primaryRgb,
      opacity: 0.04,
    },
  ];

  glows.forEach((glow) => {
    const gradient = context.createRadialGradient(
      glow.x,
      glow.y,
      0,
      glow.x,
      glow.y,
      glow.radius,
    );
    gradient.addColorStop(
      0,
      `rgba(${glow.rgb}, ${glow.opacity * palette.opacityScale})`,
    );
    gradient.addColorStop(1, `rgba(${glow.rgb}, 0)`);
    context.fillStyle = gradient;
    context.fillRect(
      glow.x - glow.radius,
      glow.y - glow.radius,
      glow.radius * 2,
      glow.radius * 2,
    );
  });
};

const drawSignalGrid = (
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  time: number,
  reducedMotion: boolean,
  palette: FieldPalette,
) => {
  const spacing = getGridSpacing(width);
  const columns = Math.ceil(width / spacing) + 2;
  const rows = Math.ceil(height / spacing) + 2;

  for (let row = -1; row < rows; row += 1) {
    for (let column = -1; column < columns; column += 1) {
      const offsetX = row % 2 === 0 ? 0 : spacing * 0.5;
      const baseX = column * spacing + spacing * 0.5 + offsetX;
      const baseY = row * spacing + spacing * 0.5;
      const normalizedX = baseX / width;
      const normalizedY = baseY / height;
      let strongestInfluence = getPathInfluence(
        0,
        normalizedX,
        normalizedY,
        time,
      );
      let dominantPath = 0;

      for (let pathIndex = 1; pathIndex < PATH_COUNT; pathIndex += 1) {
        const influence = getPathInfluence(
          pathIndex,
          normalizedX,
          normalizedY,
          time,
        );

        if (influence > strongestInfluence) {
          strongestInfluence = influence;
          dominantPath = pathIndex;
        }
      }
      const ambientPulse = reducedMotion
        ? 0.88
        : 0.8 +
          Math.sin(time * 2.1 + column * 0.31 - row * 0.27) * 0.2;
      const currentPulse = reducedMotion
        ? 0.9
        : 0.82 +
          Math.sin(time * 2.8 - normalizedX * 6.2 + row * 0.08) * 0.18;
      const edgeFade =
        Math.min(
          smoothStep(0, 0.025, normalizedX),
          smoothStep(1, 0.975, normalizedX),
        ) *
        Math.min(
          smoothStep(0, 0.025, normalizedY),
          smoothStep(1, 0.975, normalizedY),
        );
      const readingColumn =
        smoothStep(0.2, 0.31, normalizedX) *
        smoothStep(0.96, 0.84, normalizedX);
      const topReadingBand =
        smoothStep(0.035, 0.075, normalizedY) *
        (1 - smoothStep(0.08, 0.22, normalizedY));
      const readabilityFade = 1 - readingColumn * topReadingBand * 0.76;
      const emphasis = (column * 11 + row * 7) % 19 === 0;
      const opacity =
        (0.14 * ambientPulse + strongestInfluence * 0.29 * currentPulse) *
        edgeFade *
        readabilityFade *
        palette.opacityScale *
        (emphasis ? 1.15 : 1);

      if (opacity < 0.018) continue;

      // Keep the whole viewport alive; the research currents add emphasis
      // without limiting visible movement to a few narrow bands.
      const motionStrength = 0.72 + strongestInfluence * 0.28;
      const x =
        baseX +
        (reducedMotion
          ? 0
          : Math.cos(time * 1.68 + normalizedY * 6.1 + dominantPath) *
            3.8 *
            motionStrength);
      const y =
        baseY +
        (reducedMotion
          ? 0
          : Math.sin(time * 2.08 + normalizedX * 7.4 - dominantPath) *
            7.2 *
            motionStrength);
      const radius =
        1.05 + strongestInfluence * 0.48 + (emphasis ? 0.42 : 0);
      const rgb = dominantPath === 1 ? palette.accentRgb : palette.primaryRgb;

      if (emphasis && strongestInfluence > 0.45) {
        context.beginPath();
        context.arc(x, y, radius * 3.2, 0, Math.PI * 2);
        context.fillStyle = `rgba(${rgb}, ${Math.min(opacity * 0.15, 0.095)})`;
        context.fill();
      }

      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fillStyle = `rgba(${rgb}, ${Math.min(opacity, 0.72)})`;
      context.fill();
    }
  }
};

const drawField = (
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  elapsed: number,
  reducedMotion: boolean,
  palette: FieldPalette,
) => {
  context.clearRect(0, 0, width, height);
  const time = reducedMotion ? 3.2 : elapsed / 1000;

  drawAmbientGlow(context, width, height, time, palette);
  drawSignalGrid(
    context,
    width,
    height,
    time,
    reducedMotion,
    palette,
  );
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
    let animationFrame: number | null = null;
    let animationStartedAt: number | null = null;
    let lastFrameAt = 0;
    let palette = getFieldPalette();

    const draw = (elapsed: number) => {
      drawField(
        context,
        viewportWidth,
        viewportHeight,
        elapsed,
        reducedMotion,
        palette,
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
