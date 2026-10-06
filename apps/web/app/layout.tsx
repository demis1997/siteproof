import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'SiteProof · Evidence before opinion',description:'Private website audits and verified redesign previews.',robots:{index:false,follow:false}};
export default function Layout({children}:{children:React.ReactNode}) {return <html lang="en"><body>{children}</body></html>;}
