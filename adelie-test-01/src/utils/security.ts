export interface RateLimitOptions {
  maxRequests: number;
  windowMs: number;
}

// In‑memory store for IP address counters. In a real production app you would use a distributed store.
const ipStore = new Map<string, { count: number; resetTime: number }>();

/**
 * Simple rate limiter that can be used in Next.js middleware.
 * Returns a Response with status 429 when the limit is exceeded, otherwise null.
 */
export function rateLimiter(
  req: Request,
  options?: RateLimitOptions
): Response | null {
  const ipHeader = req.headers.get('x-forwarded-for') || req.headers.get('remote-addr') || '';
  const ip = ipHeader.split(',')[0].trim() || 'unknown';

  const max = options?.maxRequests ?? Number(process.env.RATE_LIMIT_MAX ?? 100);
  const windowMs = options?.windowMs ?? Number(process.env.RATE_LIMIT_WINDOW_MS ?? 15 * 60 * 1000);

  const now = Date.now();
  const record = ipStore.get(ip);

  if (!record) {
    ipStore.set(ip, { count: 1, resetTime: now + windowMs });
    return null;
  }

  if (now > record.resetTime) {
    // Reset the window for this IP
    record.count = 1;
    record.resetTime = now + windowMs;
    return null;
  }

  record.count += 1;
  if (record.count > max) {
    const retryAfter = Math.ceil((record.resetTime - now) / 1000);
    return new Response('Too Many Requests', {
      status: 429,
      headers: { 'Retry-After': retryAfter.toString() },
    });
  }

  return null;
}

/**
 * Adds a set of security‑related HTTP headers to the supplied Response.
 */
export function setSecurityHeaders(res: Response): Response {
  const headers = new Headers(res.headers);
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('X-Frame-Options', 'DENY');
  headers.set('Referrer-Policy', 'no-referrer');
  // X‑XSS‑Protection is deprecated in modern browsers but kept for legacy support.
  headers.set('X-XSS-Protection', '0');
  headers.set('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload');
  headers.set(
    'Content-Security-Policy',
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self';"
  );

  return new Response(res.body, {
    ...res,
    headers,
  });
}

/**
 * Very small runtime‑type validator. It checks that each property in `data`
 * matches the primitive type declared in `schema`. Throws on mismatch.
 */
export function validateSchema<T extends Record<string, any>>(
  data: any,
  schema: { [K in keyof T]: 'string' | 'number' | 'boolean' }
): T {
  const result: Partial<T> = {};
  for (const key in schema) {
    const expected = schema[key];
    const value = data[key];
    if (typeof value !== expected) {
      throw new Error(
        `Invalid type for ${key}: expected ${expected}, got ${typeof value}`
      );
    }
    (result as any)[key] = value;
  }
  return result as T;
}
