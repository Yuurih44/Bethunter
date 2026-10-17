export interface User {
  id: number;
  email: string;
  role: string;
  csrf: string;
  mfa_enabled: boolean;
  email_verified?: boolean;
}
export interface Domain {
  id: number;
  name: string;
  created: string;
  origin: string;
}
export interface Analysis {
  id: number;
  domain_id: number;
  created: string;
  score: number;
  classification: string;
  review: string;
  domain?: string;
  result: {
    verdict?: {
      code: string;
      label: string;
      explanation: string;
      requires_human_review: boolean;
      crime_determined: boolean;
    };
    raw_document_ids?: number[];
    discovery?: Record<string, unknown>;
    factors: { key: string; explanation: string; weight: number }[];
    technical: Record<string, unknown>;
    regulation: {
      status: string;
      reason: string;
      url?: string;
      consulted?: string;
      document_updated?: string;
    };
    errors: string[];
    limitations: string[];
    rule_version: string;
  };
}
export interface Case {
  id: number;
  title: string;
  status: string;
  priority: string;
  notes: string;
  created: string;
  domain_ids: number[];
}
export interface Report {
  id: number;
  case_id: number;
  created: string;
  status: string;
  protocol: string;
  confirmation: string;
  sha256: string;
  archived?: boolean;
}
export interface Dashboard {
  domains: number;
  analyzed: number;
  pending: number;
  suspect: number;
  prepared: number;
  forwarded: number;
  distribution: { name: string; value: number }[];
  history: { date: string; analyses: number }[];
  recent: Analysis[];
}
export interface Source {
  id: number;
  url: string;
  consulted: string;
  document_updated: string | null;
  status: string;
  error: string;
  entries: unknown[];
  sha256: string;
}
export interface Audit {
  id: number;
  created: string;
  action: string;
  details: unknown;
}
export interface Rule {
  version: string;
  effective_from: string;
  effective_until: string | null;
  config: { weights: Record<string, number>; rationale: string };
}
export interface Graph {
  nodes: { id: string; label: string; kind: string }[];
  edges: { source: string; target: string; observed: string }[];
  limitation: string;
}
