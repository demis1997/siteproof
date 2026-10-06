export type JobStatus = 'queued'|'capturing'|'auditing'|'designing'|'verifying'|'needs_review'|'completed'|'failed'|'cancelled';
export interface PageSpec { title:string; layout:'editorial'|'classic'|'compact'; typography:'sans'|'serif'; headline:string; about:string; services:string[]; details:string[]; contacts:{kind:string;value:string;href:string}[]; fixture:boolean }
export interface Evidence {id:string;kind:string;viewport?:string;artifact_url?:string;selector?:string;data?:Record<string,unknown>;[key:string]:unknown}
export interface Finding {id:string;category:string;severity:string;claim:string;evidence_ids:string[];confidence:number;objective?:boolean;kind?:string;proposed_change:string;verification_method:string;approved?:boolean}
export interface BusinessFact {id:string;kind?:string;value:string;source_url:string;evidence_id:string;approved?:boolean;[key:string]:unknown}
export interface Verification {id?:string;finding_id?:string;check?:string;status?:string;results?:Verification[];required_checks_passed?:boolean;regressions?:string[];facts_preserved?:boolean;details?:unknown;[key:string]:unknown}
export interface AuditJob {id:string;url?:string;submitted_url?:string;canonical_url?:string;status:JobStatus;stage:string;created_at?:string;updated_at?:string;mode?:string;fixture?:boolean;error?:unknown;data?:Record<string,unknown>;[key:string]:unknown}
