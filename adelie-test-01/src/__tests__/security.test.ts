import { rateLimiter, setSecurityHeaders, validateSchema } from '../utils/security';

/**
 * Jest tests for the security utilities defined in src/utils/security.ts.
 */

describe('Security utilities', () => {
  beforeEach(() => {
    // Reset any environment overrides between tests.
    delete process.env.RATE_LIMIT_MAX;
    delete process.env.RATE_LIMIT_WINDOW_MS;
    // Clear the in‑memory IP store by reloading the module.
    jest.resetModules();
  });

  test('setSecurityHeaders adds required headers', () => {
    const original = new Response('ok');
    const secured = setSecurityHeaders(original);
    const h = secured.headers;
    expect(h.get('X-Content-Type-Options')).toBe('nosniff');
    expect(h.get('X-Frame-Options')).toBe('DENY');
    expect(h.get('Content-Security-Policy')).toContain("default-src 'self'");
  });

  test('rateLimiter allows requests under the limit', () => {
    const req = new Request('http://example.com', {
      headers: { 'x-forwarded-for': '1.2.3.4' },
    });
    const result = rateLimiter(req);
    expect(result).toBeNull();
  });

  test('rateLimiter blocks after exceeding the limit', () => {
    process.env.RATE_LIMIT_MAX = '2';
    process.env.RATE_LIMIT_WINDOW_MS = '10000'; // 10 seconds
    const ip = '5.6.7.8';
    const req = new Request('http://example.com', {
      headers: { 'x-forwarded-for': ip },
    });
    // First two requests should pass.
    expect(rateLimiter(req)).toBeNull();
    expect(rateLimiter(req)).toBeNull();
    // Third request must be blocked.
    const blocked = rateLimiter(req);
    expect(blocked).not.toBeNull();
    expect(blocked?.status).toBe(429);
    expect(blocked?.headers.get('Retry-After')).toBeDefined();
  });

  test('validateSchema passes when data matches schema', () => {
    const data = { name: 'Alice', age: 30, active: true };
    const schema = { name: 'string', age: 'number', active: 'boolean' } as const;
    const result = validateSchema(data, schema);
    expect(result).toEqual(data);
  });

  test('validateSchema throws on type mismatch', () => {
    const data = { name: 'Bob', age: 'thirty', active: true };
    const schema = { name: 'string', age: 'number', active: 'boolean' } as const;
    expect(() => validateSchema(data, schema)).toThrow(/Invalid type for age/);
  });
});
