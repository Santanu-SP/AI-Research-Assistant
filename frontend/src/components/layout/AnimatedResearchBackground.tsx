import React, { useEffect, useRef } from 'react';

const FOREST_GREEN = '22, 51, 40';
const MAX_DEVICE_PIXEL_RATIO = 2;
const TARGET_FRAME_INTERVAL = 1000 / 24;
const MIN_POINT_COUNT = 28;
const MAX_POINT_COUNT = 56;

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

interface ResearchField {
  points: FieldPoint[];
  segments: FieldSegment[];
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
    speed: 0.000025 + random() * 0.00002,
  }));
  const clusteredPointCount = clusterCount * 4;

  const points = Array.from({ length: pointCount }, (_, index): FieldPoint => {
    const isClustered = index < clusteredPointCount;
    const cluster = isClustered ? clusters[index % clusterCount] : undefined;
    const angle = random() * Math.PI * 2;
    const distance = 22 + random() * 48;
    const strongerPoint = random() < 0.12;
    const driftingPoint = !isClustered && random() < 0.4;

    return {
      x: cluster
        ? clamp(cluster.x + Math.cos(angle) * distance, 12, width - 12)
        : 12 + random() * Math.max(width - 24, 1),
      y: cluster
        ? clamp(cluster.y + Math.sin(angle) * distance, 12, height - 12)
        : 12 + random() * Math.max(height - 24, 1),
      radius: 0.95 + random() * 0.7,
      opacity: strongerPoint ? 0.16 + random() * 0.04 : 0.09 + random() * 0.04,
      phase: random() * Math.PI * 2,
      driftX: driftingPoint ? 1.5 + random() * 3.5 : 0,
      driftY: driftingPoint ? 1.5 + random() * 3.5 : 0,
      cluster,
      clusterShiftX: cluster ? -Math.cos(angle) * (3 + random() * 8) : 0,
      clusterShiftY: cluster ? -Math.sin(angle) * (3 + random() * 8) : 0,
    };
  });

  const segmentCount = clamp(Math.round((width * height) / 340000), 2, 5);
  const segments = Array.from({ length: segmentCount }, (): FieldSegment => ({
    x: width * (0.08 + random() * 0.84),
    y: height * (0.1 + random() * 0.8),
    length: 12 + random() * 18,
    vertical: random() > 0.5,
    phase: random() * Math.PI * 2,
    speed: 0.000045 + random() * 0.000025,
  }));

  return { points, segments };
};

const smoothStep = (value: number) => value * value * (3 - 2 * value);

const drawField = (
  context: CanvasRenderingContext2D,
  field: ResearchField,
  width: number,
  height: number,
  elapsed: number,
  reducedMotion: boolean,
) => {
  context.clearRect(0, 0, width, height);

  field.points.forEach((point) => {
    const driftTime = reducedMotion ? 0 : elapsed * 0.00012;
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
    const opacity = Math.min(
      point.opacity + (point.cluster ? formation * 0.035 : 0),
      0.21,
    );

    context.beginPath();
    context.arc(
      point.x + point.clusterShiftX * formation + driftX,
      point.y + point.clusterShiftY * formation + driftY,
      point.radius,
      0,
      Math.PI * 2,
    );
    context.fillStyle = `rgba(${FOREST_GREEN}, ${opacity})`;
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
    context.strokeStyle = `rgba(${FOREST_GREEN}, ${0.05 + pulse * 0.06})`;
    context.lineWidth = 0.75;
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
      drawField(context, field, viewportWidth, viewportHeight, 0, reducedMotion);
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
      drawField(context, field, viewportWidth, viewportHeight, 0, reducedMotion);
      startAnimation();
    };

    resize();
    startAnimation();
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    reducedMotionQuery.addEventListener('change', handleMotionPreference);

    return () => {
      if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      reducedMotionQuery.removeEventListener('change', handleMotionPreference);
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
