import React from 'react';

/**
 * Pulse Fitness "blip" logo icon
 * Based on official brand guidelines — circular blip with internal pulse line
 * Primary: var(--color-brand-cyan-hover) (blue) on dark backgrounds
 * Secondary: var(--color-pulse-black) (dark) on light backgrounds
 */
const PulseFitnessLogo = ({ size = 36, variant = 'primary', className = '' }) => {
  const blue = 'var(--color-brand-cyan-hover)';
  const dark = 'var(--color-pulse-black)';
  const white = 'var(--color-white)';

  const circleColor = variant === 'primary' ? blue : dark;
  const lineColor = white;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      data-testid="pulse-fitness-logo"
    >
      {/* Outer circle */}
      <circle cx="50" cy="50" r="48" fill={circleColor} />
      {/* Pulse/heartbeat line */}
      <polyline
        points="15,50 30,50 38,30 46,70 54,25 62,68 70,50 85,50"
        stroke={lineColor}
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
};

export default PulseFitnessLogo;
