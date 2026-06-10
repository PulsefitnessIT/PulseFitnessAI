/**
 * Tests for formatApiError — Iter 216bh.
 *
 * Specifically guards against the "Reset Link → Network unreachable"
 * regression where a client-side ReferenceError was reported to the
 * user as a network problem, sending Lee on a wild-goose chase.
 *
 * Run with `yarn test src/lib/formatApiError.test.js`.
 */
import { formatApiError } from './formatApiError';

describe('formatApiError', () => {
  // Silence the diagnostic console.error from the JS-bug branch in
  // tests — we're asserting the *return value*, not the log.
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('client-side JS bugs (Iter 216bh hardening)', () => {
    it('ReferenceError surfaces error name + message, not "Network unreachable"', () => {
      let caught;
      try {
        // Simulate the original bug: API undefined in a template literal.
        // eslint-disable-next-line no-undef
        const url = `${API_THAT_DOES_NOT_EXIST}/foo`;
        return url;
      } catch (e) { caught = e; }
      const result = formatApiError(caught, 'Failed to generate reset link');
      expect(result.title).toBe('Failed to generate reset link');
      expect(result.detail).toMatch(/Unexpected client error/);
      expect(result.detail).toMatch(/ReferenceError/);
      expect(result.detail).not.toMatch(/Network unreachable/);
    });

    it('TypeError on undefined.foo surfaces actual error', () => {
      let caught;
      try {
        const obj = undefined;
         
        obj.foo;
      } catch (e) { caught = e; }
      const result = formatApiError(caught, 'Failed to load');
      expect(result.detail).toMatch(/Unexpected client error/);
      expect(result.detail).toMatch(/TypeError/);
    });
  });

  describe('genuine network failures', () => {
    it('ERR_NETWORK still surfaces "Network unreachable"', () => {
      const result = formatApiError({ code: 'ERR_NETWORK' }, 'Failed to save');
      expect(result.detail).toMatch(/Network unreachable/);
      expect(result.status).toBeNull();
    });

    it('ECONNABORTED surfaces timeout copy', () => {
      const result = formatApiError({ code: 'ECONNABORTED' }, 'Failed to save');
      expect(result.detail).toMatch(/timed out/);
    });
  });

  describe('HTTP errors', () => {
    it('401 produces session-expired prompt', () => {
      const result = formatApiError({ response: { status: 401, data: {} } }, 'Failed');
      expect(result.title).toBe('Session expired');
      expect(result.status).toBe(401);
    });

    it('401 from the login endpoint reads as failed sign-in, not expired session', () => {
      const result = formatApiError(
        {
          response: { status: 401, data: { detail: 'Invalid email or password' } },
          config: { url: '/api/auth/login' },
        },
        'Invalid credentials',
      );
      expect(result.title).toBe('Invalid credentials');
      expect(result.detail).toBe('Invalid email or password');
      expect(result.status).toBe(401);
    });

    it('403 surfaces server detail when present', () => {
      const result = formatApiError(
        { response: { status: 403, data: { detail: 'Master admin only' } } },
        'Failed',
      );
      expect(result.title).toBe('Permission denied');
      expect(result.detail).toBe('Master admin only');
    });

    it('500 series includes a Ref timestamp', () => {
      const result = formatApiError(
        { response: { status: 500, data: { detail: 'boom' } } },
        'Failed to save',
      );
      expect(result.detail).toMatch(/Server error \(500\)/);
      expect(result.detail).toMatch(/Ref \d{4}-\d{2}-\d{2}/);
    });
  });

  describe('unknown errors', () => {
    it('plain Error with message is reported, not masked as network', () => {
      const err = new Error('something exploded in a util');
      const result = formatApiError(err, 'Failed');
      expect(result.detail).toMatch(/Unexpected error/);
      expect(result.detail).toMatch(/something exploded/);
      expect(result.detail).not.toMatch(/Network unreachable/);
    });

    it('truly empty error falls back to network message', () => {
      const result = formatApiError(null, 'Failed');
      expect(result.detail).toMatch(/Network unreachable/);
    });
  });
});
