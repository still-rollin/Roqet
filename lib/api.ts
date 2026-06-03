export interface SearchResult {
  name: string;
  kind: string;
  type_signature: string;
  statement: string;
  docstring: string;
  module_path: string;
  library: string;
  file_path: string;
  line_number: number;
  github_url: string;
  score: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
  elapsed_ms: number;
}

export interface StatsResponse {
  total_points: number;
  libraries: Record<string, number>;
  kinds: Record<string, number>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function searchDeclarations(
  q: string,
  opts: { limit?: number; lib?: string; kind?: string } = {}
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q });
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.lib)   params.set("lib", opts.lib);
  if (opts.kind)  params.set("kind", opts.kind);

  const res = await fetch(`${API_BASE}/search?${params}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getStats(): Promise<StatsResponse> {
  const res = await fetch(`${API_BASE}/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const LIBRARIES = ["stdlib", "mathcomp", "unimath", "hott"] as const;
export type Library = typeof LIBRARIES[number];

export const KINDS = [
  "Lemma", "Theorem", "Corollary", "Proposition",
  "Definition", "Fixpoint", "Inductive", "Record",
  "Class", "Instance", "Notation", "Axiom",
] as const;

export const LIBRARY_LABELS: Record<string, string> = {
  stdlib:   "Stdlib",
  mathcomp: "MathComp",
  unimath:  "UniMath",
  hott:     "HoTT",
};

export const EXAMPLE_QUERIES = [
  "commutativity of addition on natural numbers",
  "list concatenation associativity",
  "decidable equality",
  "transitivity of less-than relation",
  "group homomorphism preserves identity",
  "functional extensionality",
  "induction principle for lists",
  "path induction in HoTT",
];
