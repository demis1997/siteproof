import Link from 'next/link';
import {tenantKey} from '@/lib/api';
export const dynamic='force-dynamic';
export default async function Preview({params}:{params:Promise<{id:string}>}) {const {id}=await params;if(!await tenantKey())return <main className="preview-unavailable"><h1>Private preview unavailable</h1><p>Sign in to the owning tenant workspace.</p><Link href="/">Return to workspace</Link></main>;return <main className="verified-preview"><div className="preview-toolbar"><Link href="/">← Audit workspace</Link><span>Private preview · This is the document captured by verification</span></div><iframe title="Verified private homepage redesign" src={`/api/jobs/${encodeURIComponent(id)}/preview-html`} sandbox="allow-same-origin"/></main>;}
