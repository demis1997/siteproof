import type { NextConfig } from 'next';
const config: NextConfig = { output: 'standalone', poweredByHeader: false, async headers() { return [{source:'/:path*',headers:[{key:'X-Robots-Tag',value:'noindex, nofollow'},{key:'X-Content-Type-Options',value:'nosniff'},{key:'Referrer-Policy',value:'same-origin'}]}]; } };
export default config;
