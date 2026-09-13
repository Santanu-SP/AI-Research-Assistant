import React from 'react';

interface LoadingOrbProps {
  /** Diameter in CSS pixels. */
  size?: number;
  /** Accessible status text. Omit for an inline decorative loader. */
  label?: string;
  className?: string;
}

type OrbDot = {
  x: number;
  y: number;
  tier: number;
};

// Native-frame analysis of the reference reveals a circular 24-dot matrix on
// a 6 × 6 grid: row widths 2, 4, 6, 6, 4, 2. The central four dots are the
// largest and the two outer tiers become progressively smaller.
const ROW_RANGES = [
  [2, 3],
  [1, 4],
  [0, 5],
  [0, 5],
  [1, 4],
  [2, 3],
] as const;

const DOTS: OrbDot[] = ROW_RANGES.flatMap(([start, end], y) =>
  Array.from({ length: end - start + 1 }, (_, offset) => {
    const x = start + offset;
    const radialDistance = Math.hypot(x - 2.5, y - 2.5);
    const tier = radialDistance < 1 ? 0 : radialDistance < 2.25 ? 1 : 2;
    return { x, y, tier };
  })
);

export const LoadingOrb: React.FC<LoadingOrbProps> = ({
  size = 38,
  label,
  className = '',
}) => {
  const style = { '--loading-orb-size': `${size}px` } as React.CSSProperties;

  return (
    <span
      className={`loading-orb ${className}`}
      style={style}
      role={label ? 'status' : undefined}
      aria-label={label}
    >
      {DOTS.map(({ x, y, tier }) => (
        <span
          key={`${x}-${y}`}
          aria-hidden="true"
          className="loading-orb__dot"
          style={
            {
              '--loading-orb-x': x,
              '--loading-orb-y': y,
              '--loading-orb-tier': tier,
            } as React.CSSProperties
          }
        />
      ))}
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
};
