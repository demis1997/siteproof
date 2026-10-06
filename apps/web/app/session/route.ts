import { cookies } from 'next/headers';
import type { NextRequest } from 'next/server';
import { apiOrigin } from '@/lib/api';
export async function POST(request: NextRequest) {
  if(request.headers.get('origin')!==request.nextUrl.origin) return Response.json({detail:'Cross-origin writes are forbidden.'},{status:403});
  const {key}=await request.json();if(typeof key!=='string'||key.length>512||!key.trim())return Response.json({detail:'Provide a tenant access key.'},{status:400});
  try {const result=await fetch(`${apiOrigin}/api/jobs`,{headers:{'X-Tenant-Key':key},cache:'no-store'});if(!result.ok)return Response.json({detail:result.status===401?'Access key could not be verified.':'API dependencies unavailable.'},{status:result.status===401?401:503});}catch{return Response.json({detail:'API unavailable.'},{status:503});}
  (await cookies()).set('siteproof-session',key,{httpOnly:true,sameSite:'strict',secure:request.nextUrl.protocol==='https:',path:'/',maxAge:28800});return Response.json({ok:true});
}
export async function DELETE(request:NextRequest) {if(request.headers.get('origin')!==request.nextUrl.origin)return new Response(null,{status:403});(await cookies()).delete('siteproof-session');return Response.json({ok:true});}
