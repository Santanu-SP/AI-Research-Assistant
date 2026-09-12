import React, { useEffect, useRef } from 'react';
import { THEME_CHANGE_EVENT } from '../../theme';

const MAX_DEVICE_PIXEL_RATIO = 2;
const TARGET_FRAME_INTERVAL = 1000 / 24;
const MIN_POINT_COUNT = 44;
const MAX_POINT_COUNT = 84;

interface Cluster {
  x: number;
  y: number;
  phase: number;
  speed: number;
}

interface FieldPoint {
  x: number;
  y: number;
  radius: number;
  opacity: number;
  phase: number;
  driftX: number;
  driftY: number;
  cluster?: Cluster;
  clusterShiftX: number;
  clusterShiftY: number;
}

interface FieldSegment {
  x: number;
  y: number;
  length: number;
  vertical: boolean;
  phase: number;
  speed: number;
}

interface FieldConnection {
  from: number;
  to: number;
  phase: number;
}

interface ResearchField {
  points: FieldPoint[];
  segments: FieldSegment[];
  connections: FieldConnection[];
}

interface FieldPalette {
  rgb: string;
  opacityScale: number;
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

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

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

const createField = (width: number, height: number): ResearchField => {
  const random = createRandom(0x163328 + Math.round(width) * 17 + Math.round(height));
  const pointCount = clamp(
    Math.round((width * height) / 30000),
    MIN_POINT_COUNT,
    MAX_POINT_COUNT,
  );
  const clusterCount = width >= 1280 ? 4 : 3;
  const clusters: Cluster[] = Array.from({ length: clusterCount }, () => ({
    x: width * (0.12 + random() * 0.8),
    y: height * (0.12 + random() * 0.76),
    phase: random() * Math.PI * 2,
    speed: 0.00024 + random() * 0.00014,
  }));
  const clusteredPointCount = clusterCount * 4;

  const points = Array.from({ length: pointCount }, (_, index): FieldPoint => {
    const isClustered = index < clusteredPointCount;
    const cluster = isClustered ? clusters[index % clusterCount] : undefined;
    const angle = random() * Math.PI * 2;
    const distance = 28 + random() * 62;
    const strongerPoint = random() < 0.18;
    const driftingPoint = !isClustered && random() < 0.68;

    return {
      x: cluster
        ? clamp(cluster.x + Math.cos(angle) * distance, 12, width - 12)
        : 12 + random() * Math.max(width - 24, 1),
      y: cluster
        ? clamp(cluster.y + Math.sin(angle) * distance, 12, height - 12)
        : 12 + random() * Math.max(height - 24, 1),
      radius: 1.25 + random() * 1.05,
      opacity: strongerPoint ? 0.34 + random() * 0.1 : 0.18 + random() * 0.08,
      phase: random() * Math.PI * 2,
      driftX: driftingPoint ? 4 + random() * 8 : 0,
      driftY: driftingPoint ? 4 + random() * 8 : 0,
      cluster,
      clusterShiftX: cluster ? -Math.cos(angle) * (8 + random() * 16) : 0,
      clusterShiftY: cluster ? -Math.sin(angle) * (8 + random() * 16) : 0,
    };
  });

  const connections: FieldConnection[] = [];
  for (let clusterIndex = 0; clusterIndex < clusterCount; clusterIndex += 1) {
    const clusterPointIndexes = Array.from(
      { length: 4 },
      (_, pointIndex) => clusterIndex + pointIndex * clusterCount,
    );

    clusterPointIndexes.forEach((pointIndex, index) => {
      connections.push({
        from: pointIndex,
        to: clusterPointIndexes[(index + 1) % clusterPointIndexes.length],
        phase: random() * Math.PI * 2,
      });
    });
  }

  const segmentCount = clamp(Math.round((width * height) / 190000), 4, 9);
  const segments = Array.from({ length: segmentCount }, (): FieldSegment => ({
    x: width * (0.08 + random() * 0.84),
    y: height * (0.1 + random() * 0.8),
    length: 18 + random() * 28,
    vertical: random() > 0.5,
    phase: random() * Math.PI * 2,
    speed: 0.00042 + random() * 0.00018,
  }));

  return { points, segments, connections };
};

const smoothStep = (value: number) => value * value * (3 - 2 * value);

const drawField = (
  context: CanvasRenderingContext2D,
  field: ResearchField,
  width: number,
  height: number,
  elapsed: number,
  reducedMotion: boolean,
  palette: FieldPalette,
) => {
  context.clearRect(0, 0, width, height);

  const renderedPoints = field.points.map((point) => {
    const driftTime = reducedMotion ? 0 : elapsed * 0.00042;
    const formation = point.cluster
      ? smoothStep(
          reducedMotion
            ? 0.5
            : (Math.sin(elapsed * point.cluster.speed + point.cluster.phase) + 1) / 2,
        )
      : 0;
    const driftX = reducedMotion
      ? 0
      : Math.sin(driftTime + point.phase) * point.driftX;
    const driftY = reducedMotion
      ? 0
      : Math.cos(driftTime * 0.83 + point.phase) * point.driftY;
    const pulse = reducedMotion
      ? 0.86
      : 0.78 + Math.sin(elapsed * 0.00055 + point.phase) * 0.18;
    const opacity = Math.min(
      (point.opacity + (point.cluster ? formation * 0.08 : 0)) * pulse,
      0.5,
    );

    return {
      x: point.x + point.clusterShiftX * formation + driftX,
      y: point.y + point.clusterShiftY * formation + driftY,
      radius: point.radius,
      opacity,
    };
  });

  field.connections.forEach((connection) => {
    const from = renderedPoints[connection.from];
    const to = renderedPoints[connection.to];
    const pulse = reducedMotion
      ? 0.72
      : 0.68 + Math.sin(elapsed * 0.00034 + connection.phase) * 0.24;

    context.beginPath();
    context.moveTo(from.x, from.y);
    context.lineTo(to.x, to.y);
    context.strokeStyle = `rgba(${palette.rgb}, ${Math.min(
      0.16 * pulse * palette.opacityScale,
      0.2,
    )})`;
    context.lineWidth = 0.85;
    context.stroke();
  });

  renderedPoints.forEach((point) => {
    context.beginPath();
    context.arc(point.x, point.y, point.radius, 0, Math.PI * 2);
    const scaledOpacity = Math.min(point.opacity * palette.opacityScale, 0.52);
    context.fillStyle = `rgba(${palette.rgb}, ${scaledOpacity})`;
    context.fill();
  });

  if (reducedMotion) return;

  field.segments.forEach((segment) => {
    const pulse = Math.pow(
      Math.max(0, Math.sin(elapsed * segment.speed + segment.phase)),
      10,
    );

    if (pulse < 0.08) return;

    context.beginPath();
    context.moveTo(segment.x, segment.y);
    context.lineTo(
      segment.x + (segment.vertical ? 0 : segment.length),
      segment.y + (segment.vertical ? segment.length : 0),
    );
    const opacity = Math.min(
      (0.13 + pulse * 0.16) * palette.opacityScale,
      0.34,
    );
    context.strokeStyle = `rgba(${palette.rgb}, ${opacity})`;
    context.lineWidth = 1;
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
    let field: ResearchField;
    let viewportWidth = 0;
    let viewportHeight = 0;
    let animationFrame: number | null = null;
    let animationStartedAt: number | null = null;
    let lastFrameAt = 0;
    let palette = getFieldPalette();

    const resize = () => {
      viewportWidth = window.innerWidth;
      viewportHeight = window.innerHeight;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, MAX_DEVICE_PIXEL_RATIO);

      canvas.width = Math.round(viewportWidth * pixelRatio);
      canvas.height = Math.round(viewportHeight * pixelRatio);
      canvas.style.width = `${viewportWidth}px`;
      canvas.style.height = `${viewportHeight}px`;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      field = createField(viewportWidth, viewportHeight);
      drawField(
        context,
        field,
        viewportWidth,
        viewportHeight,
        0,
        reducedMotion,
        palette,
      );
    };

    const animate = (timestamp: number) => {
      if (document.visibilityState === 'hidden' || reducedMotion) {
        animationFrame = null;
        return;
      }

      animationStartedAt ??= timestamp;
      if (timestamp - lastFrameAt >= TARGET_FRAME_INTERVAL) {
        drawField(
          context,
          field,
          viewportWidth,
          viewportHeight,
          timestamp - animationStartedAt,
          false,
          palette,
        );
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
      drawField(
        context,
        field,
        viewportWidth,
        viewportHeight,
        0,
        reducedMotion,
        palette,
      );
      startAnimation();
    };

    const handleThemeChange = () => {
      palette = getFieldPalette();
      drawField(
        context,
        field,
        viewportWidth,
        viewportHeight,
        0,
        reducedMotion,
        palette,
      );
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
