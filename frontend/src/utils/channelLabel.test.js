/**
 * Tests for channelLabel — Iter 220cp.
 *
 * Pins the cross-module channel display helper used by the engineer
 * app + operations portal. Mirrors the backend tests in
 * test_iter_220cp_channel_unification.py.
 *
 * Run with `yarn test src/utils/channelLabel.test.js`.
 */
import { resolveChannel } from './channelLabel';

describe('resolveChannel', () => {
  it('returns null when no channel/source set', () => {
    expect(resolveChannel(null)).toBeNull();
    expect(resolveChannel(undefined)).toBeNull();
    expect(resolveChannel({})).toBeNull();
    expect(resolveChannel({ intake_channel: '', source: '' })).toBeNull();
  });

  it('prefers intake_channel over source (engineer-app first)', () => {
    const r = resolveChannel({ intake_channel: 'portal', source: 'phone' });
    expect(r.code).toBe('portal');
    expect(r.label).toBe('Customer portal');
  });

  it('falls back to source when intake_channel is missing', () => {
    const r = resolveChannel({ source: 'portal' });
    expect(r.code).toBe('portal');
    expect(r.label).toBe('Customer portal');
  });

  it('labels each known channel correctly', () => {
    const cases = [
      ['manual',        'Walked in / counter'],
      ['phone',         'Phone call'],
      ['email',         'Email request'],
      ['inbound_email', 'Email inbox'],
      ['portal',        'Customer portal'],
      ['embed_widget',  'Embedded widget'],
      ['supplier_card', 'Supplier card'],
      ['service_desk',  'Service desk'],
      ['other',         'Other / referral'],
    ];
    cases.forEach(([code, label]) => {
      const r = resolveChannel({ intake_channel: code });
      expect(r.code).toBe(code);
      expect(r.label).toBe(label);
    });
  });

  it('gracefully falls back for unknown codes', () => {
    const r = resolveChannel({ intake_channel: 'sky_writing' });
    expect(r.code).toBe('sky_writing');
    expect(r.label).toBe('sky writing');
    // cls always set so the chip doesn't crash on render.
    expect(typeof r.cls).toBe('string');
  });

  it('is case-insensitive', () => {
    const r = resolveChannel({ intake_channel: 'PORTAL' });
    expect(r.code).toBe('portal');
  });
});
