import { backend } from '@/lib/api';
import type { NextRequest } from 'next/server';
async function proxy(request: NextRequest, {params}: {params: Promise<{path:string[]}>}) {
  if (!['GET','HEAD'].includes(request.method) && request.headers.get('origin') !== request.nextUrl.origin) return Response.json({detail:'Cross-origin writes are forbidden.'},{status:403});
  const {path} = await params;
  if (!['jobs','artifacts'].includes(path[0])) return Response.json({detail:'Unknown endpoint'},{status:404});
  const headers = new Headers();
  for (const name of ['content-type','idempotency-key']) {const value=request.headers.get(name);if(value) headers.set(name,value);}
  try {
    const result=await backend(path.map(encodeURIComponent).join('/')+request.nextUrl.search,{method:request.method,headers,...(!['GET','HEAD'].includes(request.method)?{body:await request.text()}:{})});
    const out=new Headers();for(const name of ['content-type','content-disposition','content-security-policy','x-robots-tag']) {const value=result.headers.get(name);if(value)out.set(name,value);}out.set('Cache-Control','private, no-store');
    return new Response(result.body,{status:result.status,headers:out});
  } catch {return Response.json({detail:'API unavailable. Check the API and worker services.'},{status:503});}
}
export const GET=proxy;export const POST=proxy;export const DELETE=proxy;
