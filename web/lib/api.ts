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
  chapter: string;
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
  opts: { limit?: number; lib?: string; kind?: string; chapter?: string } = {}
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q });
  if (opts.limit)   params.set("limit", String(opts.limit));
  if (opts.lib)     params.set("lib", opts.lib);
  if (opts.kind)    params.set("kind", opts.kind);
  if (opts.chapter) params.set("chapter", opts.chapter);

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

export const LIBRARIES = ["stdlib", "mathcomp", "geocoq","mathcomp-analysis", "unimath", "hott"] as const;
export type Library = typeof LIBRARIES[number];

// Currently indexed & searchable. We only ship a library once it has high-quality
// natural-language descriptions (MathComp is first). The rest are rolling out.
export const ACTIVE_LIBRARIES = ["mathcomp"] as const;
export const COMING_SOON_LIBRARIES = ["stdlib", "mathcomp-analysis", "geocoq"] as const;

// GeoCoq Tarski_dev chapters (Ch02–Ch16). Used for the geocoq-only chapter filter.
export const GEOCOQ_CHAPTERS = [
  "Ch02", "Ch03", "Ch04", "Ch05", "Ch06", "Ch07", "Ch08", "Ch09",
  "Ch10", "Ch11", "Ch12", "Ch13", "Ch14", "Ch15", "Ch16",
] as const;

export const KINDS = [
  "Lemma", "Theorem", "Corollary", "Proposition",
  "Definition", "Fixpoint", "Inductive", "Record",
  "Class", "Instance", "Notation", "Axiom",
] as const;

export const LIBRARY_LABELS: Record<string, string> = {
  stdlib:   "Stdlib",
  mathcomp: "MathComp",
  geocoq:   "GeoCoq",
  unimath:  "UniMath",
  hott:     "HoTT",
  "mathcomp-analysis": "MathComp-Analysis",
};

export const EXAMPLE_QUERIES = [
  "multiplication in a ring is associative",
  "a group homomorphism maps the identity to the identity",
  "the determinant of a product is the product of determinants",
  "convert a row vector into a polynomial",
  "every finite integral domain is a field",
  "the order of an element divides the order of the group",
  "polynomial evaluation is a ring morphism",
  "the gcd divides both of its arguments",
];
