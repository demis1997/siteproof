import type { NextRequest } from 'next/server';

export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get('origin');
  const host = request.headers.get('host');
  if (!origin || !host) return false;
  const configured = process.env.SITEPROOF_PUBLIC_ORIGIN;
  if (configured) return origin === configured;
  // Standalone Next binds to 0.0.0.0 in Docker. The incoming Host identifies the browser origin.
  return origin === `${request.nextUrl.protocol}//${host}`;
}
