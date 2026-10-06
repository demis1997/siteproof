import {readFile} from 'node:fs/promises';
import {timingSafeEqual} from 'node:crypto';
import {createElement} from 'react';
import PageRenderer from '@/components/page-renderer';
import type {PageSpec} from '@/lib/types';
export const runtime='nodejs';
function valid(value:unknown):value is PageSpec {
 if(!value||typeof value!=='object')return false;
 const s=value as Record<string,unknown>;
 return ['title','headline','about'].every(k=>typeof s[k]==='string'&&(s[k] as string).length<=10000)&&['editorial','classic','compact'].includes(String(s.layout))&&['sans','serif'].includes(String(s.typography))&&typeof s.fixture==='boolean'&&['services','details'].every(k=>Array.isArray(s[k])&&(s[k] as unknown[]).length<=100&&(s[k] as unknown[]).every(v=>typeof v==='string'&&v.length<=10000))&&Array.isArray(s.contacts)&&s.contacts.length<=30&&s.contacts.every(c=>c&&typeof c==='object'&&['kind','value','href'].every(k=>typeof c[k]==='string'&&c[k].length<=1000));
}
export async function POST(request:Request) {
 const expected=process.env.SITEPROOF_RENDER_KEY,actual=request.headers.get('X-Render-Key');
 if(!expected||!actual||Buffer.byteLength(expected)!==Buffer.byteLength(actual)||!timingSafeEqual(Buffer.from(expected),Buffer.from(actual)))return Response.json({detail:'Render access denied'},{status:403});
 if(Number(request.headers.get('content-length')||0)>200000)return Response.json({detail:'Specification too large'},{status:413});
 let body:unknown;try{const text=await request.text();if(text.length>200000)return Response.json({detail:'Specification too large'},{status:413});body=JSON.parse(text);}catch{return Response.json({detail:'Invalid JSON'},{status:422});}
 const spec=(body as {spec?:unknown})?.spec;if(!valid(spec))return Response.json({detail:'Invalid page specification'},{status:422});
 // Server renderer is loaded as a Node module; this route emits no executable scripts.
 const {renderToStaticMarkup}=await import('react-dom/server');
 const css=await readFile(process.cwd()+'/app/preview.css','utf8');
 const content=renderToStaticMarkup(createElement(PageRenderer,{spec}));
 return new Response('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Private SiteProof preview</title><style>'+css+'</style></head><body>'+content+'</body></html>',{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'",'X-Robots-Tag':'noindex, nofollow'}});
}
