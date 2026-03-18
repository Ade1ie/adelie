import { NextResponse, NextRequest } from 'next/server';
import { rateLimiter, setSecurityHeaders } from './src/utils/security';

/**
 * Global Next.js middleware that applies security hardening to every request.
 * It performs:
 *   1. Rate limiting based on the client IP.
 *   2. Injection of security‑related HTTP headers (CSP, HSTS, etc.).
 */
export async function middleware(req: NextRequest) {
  // ---- Rate limiting ----------------------------------------------------
  const limitResult = rateLimiter(req);
  if (limitResult) {
    // If the limit is exceeded we return the 429 response immediately.
    return limitResult;
  }

  // Continue processing the request.
  const response = NextResponse.next();

  // ---- Security headers -------------------------------------------------
  return setSecurityHeaders(response);
}

// Apply the middleware to all routes.
export const config = {
  matcher: '/:path*',
};
