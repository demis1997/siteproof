import { cookies } from 'next/headers';
export const apiOrigin = process.env.API_INTERNAL_URL || 'http://localhost:8000';
export async function tenantKey() { return (await cookies()).get('siteproof-session')?.value; }
export async function backend(path: string, init: RequestInit = {}) {
  const key = await tenantKey();
  if (!key) return new Response(JSON.stringify({detail:'Sign in with your tenant access key.'}), {status:401});
  const headers = new Headers(init.headers); headers.set('X-Tenant-Key', key);
  return fetch(`${apiOrigin}/api/${path}`, {...init, headers, cache:'no-store'});
}
