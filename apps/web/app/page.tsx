import Dashboard from '@/components/dashboard';
import { tenantKey } from '@/lib/api';
export default async function Home() {return <Dashboard signedIn={Boolean(await tenantKey())}/>;}
