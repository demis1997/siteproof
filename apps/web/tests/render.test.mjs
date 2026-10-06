import {test} from 'node:test';
import assert from 'node:assert/strict';
import route from '../.next/server/app/internal/render/route.js';
const {POST}=route.routeModule.userland;
process.env.SITEPROOF_RENDER_KEY='test-render-key';
const spec={title:'Fixture <script>alert(1)</script>',layout:'editorial',typography:'sans',headline:'Home repairs',about:'Verified about',services:['Repairs'],details:['Monday 09:00–17:00','£50'],contacts:[{kind:'email',value:'hello@example.com',href:'mailto:hello@example.com'}],fixture:true};
function request(body,key='test-render-key'){return new Request('http://localhost/internal/render',{method:'POST',headers:{'Content-Type':'application/json','X-Render-Key':key},body:JSON.stringify(body)});}
test('renderer requires shared secret',async()=>assert.equal((await POST(request({spec},'wrong'))).status,403));
test('renderer rejects unconstrained specification',async()=>assert.equal((await POST(request({spec:{...spec,layout:'execute-js'}}))).status,422));
test('exact preview uses semantic React HTML, escapes content and preserves facts',async()=>{const response=await POST(request({spec}));assert.equal(response.status,200);const html=await response.text();assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script/i);assert.match(html,/href="mailto:hello@example.com"/);assert.match(html,/Monday 09:00–17:00/);assert.match(html,/£50/);assert.match(html,/<nav aria-label="Main navigation">/);assert.match(html,/Fixture data/);assert.match(response.headers.get('content-security-policy'),/default-src 'none'/);});
test('invalid model contact destination cannot become a link',async()=>{const response=await POST(request({spec:{...spec,contacts:[{kind:'phone',value:'Unknown',href:'javascript:alert(1)'}]}}));assert.doesNotMatch(await response.text(),/href="javascript:/);});
