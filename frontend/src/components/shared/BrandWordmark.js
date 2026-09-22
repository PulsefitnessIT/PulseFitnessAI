/**
 * BrandWordmark — the single canonical Pulse Fitness logo used across every
 * sign-in surface and shell header so branding is identical platform-wide.
 * Renders the hosted primary logo badge with the same crop the Navbar uses.
 */
export const PULSE_LOGO_SRC =
  'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg';

export default function BrandWordmark({ height = 40, className = '', testId = 'brand-wordmark' }) {
  return (
    <img
      src={PULSE_LOGO_SRC}
      alt="Pulse Fitness"
      className={`rounded-md object-cover ${className}`}
      style={{
        height,
        objectPosition: 'center',
        aspectRatio: '3.8/1',
        clipPath: 'inset(12% 3% 12% 3% round 6px)',
      }}
      data-testid={testId}
    />
  );
}
