"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  Search, Loader2, ExternalLink, ChevronDown, X, Copy, Check, GitBranch,
} from "lucide-react";
import {
  searchDeclarations,
  getStats,
  SearchResult,
  StatsResponse,
  LIBRARIES,
  KINDS,
  LIBRARY_LABELS,
  GEOCOQ_CHAPTERS,
  EXAMPLE_QUERIES,
} from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://roqet-production-b979.up.railway.app";

// ---------------------------------------------------------------------------
// Atoms
// ---------------------------------------------------------------------------
function KindBadge({ kind }: { kind: string }) {
  const key = kind.split(" ").pop() ?? kind;
  return <span className={`kind-badge kind-${key}`}>{kind}</span>;
}

function LibBadge({ lib }: { lib: string }) {
  return (
    <span className="text-[11px] px-2 py-0.5 rounded-md border border-[var(--border)] bg-[var(--surface2)] text-[var(--muted)]">
      {LIBRARY_LABELS[lib] ?? lib}
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() =>
        navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        })
      }
      className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-[var(--text)] transition-colors"
      title="Copy statement"
    >
      {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Result card
// ---------------------------------------------------------------------------
function ResultCard({ r, rank }: { r: SearchResult; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const score = Math.max(0, Math.min(100, Math.round(r.score * 100)));

  return (
    <div
      className="border border-[var(--border)] rounded-2xl bg-[var(--surface)] hover:border-[var(--border-strong)] hover:shadow-sm transition-all duration-150 animate-slide-up overflow-hidden"
      style={{ animationDelay: `${Math.min(rank, 12) * 30}ms` }}
    >
      <div className="flex items-start gap-3 p-4">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <KindBadge kind={r.kind} />
            <span className="font-semibold text-[var(--text)] text-[15px] break-all">{r.name}</span>
            <LibBadge lib={r.library} />
            {r.chapter && (
              <span className="text-[11px] px-2 py-0.5 rounded-md border border-[var(--border)] bg-[var(--surface2)] text-[var(--muted2)] font-mono">
                {r.chapter}
              </span>
            )}
            <span className="text-[11px] text-[var(--muted2)] ml-auto tabular-nums">{score}%</span>
          </div>

          {r.type_signature && (
            <div className="type-sig mb-2 bg-[var(--surface2)] border border-[var(--border)] rounded-xl px-3 py-2">
              {r.type_signature}
            </div>
          )}

          {r.docstring && (
            <p className="text-sm text-[var(--muted)] mb-2 leading-relaxed">{r.docstring}</p>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-2.5">
            <span className="text-[11px] text-[var(--muted2)] truncate max-w-[18rem]">
              {r.module_path ? `${r.module_path} · ` : ""}{r.file_path.split("/").pop()}:{r.line_number}
            </span>

            {r.statement && <CopyButton text={r.statement} />}

            {r.github_url && (
              <a
                href={r.github_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-[var(--accent)] hover:underline"
              >
                <ExternalLink size={12} /> Source
              </a>
            )}

            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-[var(--text)] transition-colors ml-auto"
            >
              Details
              <ChevronDown size={13} className={`transition-transform ${expanded ? "rotate-180" : ""}`} />
            </button>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-[var(--border)] px-4 py-3 bg-[var(--surface2)] text-xs text-[var(--muted)] space-y-1 animate-fade-in">
          {r.statement && <div className="text-[var(--text)] mb-2 whitespace-pre-wrap break-words">{r.statement}</div>}
          <div><span className="text-[var(--muted2)]">library:</span> {r.library}</div>
          <div><span className="text-[var(--muted2)]">file:</span> {r.file_path}</div>
          <div><span className="text-[var(--muted2)]">line:</span> {r.line_number}</div>
          <div><span className="text-[var(--muted2)]">module:</span> {r.module_path || "(root)"}</div>
        </div>
      )}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="border border-[var(--border)] rounded-2xl bg-[var(--surface)] p-4 space-y-3">
      <div className="flex gap-2">
        <div className="skeleton h-4 w-16" />
        <div className="skeleton h-4 w-32" />
      </div>
      <div className="skeleton h-8 w-full" />
      <div className="skeleton h-3 w-2/3" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function Home() {
  const [query, setQuery]       = useState("");
  const [results, setResults]   = useState<SearchResult[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [elapsed, setElapsed]   = useState(0);
  const [hasSearched, setHasSearched] = useState(false);
  const [stats, setStats]       = useState<StatsResponse | null>(null);

  const [filterLib,  setFilterLib]  = useState("");
  const [filterKind, setFilterKind] = useState("");
  const [filterChapter, setFilterChapter] = useState("");

  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    getStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "/" || (e.key === "k" && (e.metaKey || e.ctrlKey))) && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === "Escape" && document.activeElement === inputRef.current) inputRef.current?.blur();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); setHasSearched(false); return; }
    setLoading(true);
    setError("");
    try {
      const resp = await searchDeclarations(q, {
        limit: 20,
        lib:  filterLib  || undefined,
        kind: filterKind || undefined,
        chapter: (filterLib === "geocoq" && filterChapter) || undefined,
      });
      setResults(resp.results);
      setElapsed(resp.elapsed_ms);
      setHasSearched(true);
    } catch {
      setError("Could not reach the API. Make sure the backend is running on :8000");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [filterLib, filterKind, filterChapter]);

  const handleInput = (val: string) => {
    setQuery(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(val), 280);
  };

  useEffect(() => {
    if (query.trim()) doSearch(query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterLib, filterKind, filterChapter]);

  const handleExample = (q: string) => { setQuery(q); doSearch(q); inputRef.current?.focus(); };

  const clearAll = () => {
    setQuery(""); setResults([]); setHasSearched(false);
    setFilterLib(""); setFilterKind(""); setFilterChapter("");
    inputRef.current?.focus();
  };

  const heroMode = !hasSearched && !loading;
  const totalDecls = stats?.total_points ?? 0;
  const totalLibs = stats ? Object.keys(stats.libraries).length : 0;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-5">
        <button onClick={clearAll} className="text-xl font-bold tracking-tight text-[var(--text)]">
          Rocqet
        </button>
        <a
          href="https://github.com/LLM4Rocq/rocqet-search"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--text)] border border-[var(--border)] hover:border-[var(--border-strong)] rounded-lg px-3 py-1.5 transition-colors"
        >
          <GitBranch size={14} /> GitHub
        </a>
      </nav>

      {/* Main */}
      <main className={`flex-1 w-full max-w-2xl mx-auto px-4 flex flex-col ${heroMode ? "justify-center pb-32" : "pt-2"}`}>
        {/* Hero headline */}
        {heroMode && (
          <div className="text-center mb-8 animate-fade-in">
            <h1 className="text-4xl sm:text-5xl font-bold text-[var(--text)] tracking-tight">
              Rocqet Search!
            </h1>
            <p className="text-[var(--muted)] mt-4 text-sm">
              Semantic search across Rocq/Coq libraries — describe it in plain language.
            </p>
            {stats && (
              <p className="text-xs text-[var(--muted2)] mt-4 font-mono">
                {totalDecls.toLocaleString()} declarations ·{" "}
                {Object.entries(stats.libraries)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => `${LIBRARY_LABELS[k] ?? k} ${v.toLocaleString()}`)
                  .join(" · ")}
              </p>
            )}
          </div>
        )}

        {/* Search bar */}
        <div className="relative">
          <div className={`flex items-center gap-3 bg-[var(--surface)] border rounded-2xl px-5 py-4 transition-all duration-150
            ${heroMode ? "search-shadow" : ""}
            ${query ? "border-[var(--border-strong)]" : "border-[var(--border)] hover:border-[var(--border-strong)]"}`}>
            {loading
              ? <Loader2 size={18} className="text-[var(--muted)] shrink-0 animate-spin" />
              : <Search size={18} className="text-[var(--muted2)] shrink-0" />}
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => handleInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && doSearch(query)}
              placeholder="commutativity of addition on natural numbers…"
              autoFocus
              className="flex-1 bg-transparent outline-none text-[var(--text)] placeholder:text-[var(--muted2)] text-[15px]"
            />
            {query
              ? <button onClick={clearAll} className="text-[var(--muted2)] hover:text-[var(--text)] transition-colors"><X size={16} /></button>
              : <kbd className="kbd hidden sm:block">/</kbd>}
          </div>
        </div>

        {/* Filters (first-class) + meta */}
        <div className="flex items-center gap-2 mt-4 flex-wrap">
          <select
            value={filterLib}
            onChange={e => setFilterLib(e.target.value)}
            className="bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--border-strong)] text-[var(--text)] text-xs rounded-lg px-2.5 py-1.5 outline-none cursor-pointer"
            aria-label="Filter by library"
          >
            <option value="">All libraries</option>
            {LIBRARIES.map(l => <option key={l} value={l}>{LIBRARY_LABELS[l]}</option>)}
          </select>
          <select
            value={filterKind}
            onChange={e => setFilterKind(e.target.value)}
            className="bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--border-strong)] text-[var(--text)] text-xs rounded-lg px-2.5 py-1.5 outline-none cursor-pointer"
            aria-label="Filter by kind"
          >
            <option value="">All kinds</option>
            {KINDS.map(k => <option key={k} value={k}>{k}</option>)}
          </select>
          {filterLib === "geocoq" && (
            <select
              value={filterChapter}
              onChange={e => setFilterChapter(e.target.value)}
              className="bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--border-strong)] text-[var(--text)] text-xs rounded-lg px-2.5 py-1.5 outline-none cursor-pointer"
              aria-label="Filter by GeoCoq chapter"
            >
              <option value="">All chapters</option>
              {GEOCOQ_CHAPTERS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          )}
          {(filterLib || filterKind || filterChapter) && (
            <button
              onClick={() => { setFilterLib(""); setFilterKind(""); setFilterChapter(""); }}
              className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-[var(--text)] transition-colors"
            >
              <X size={11} /> clear
            </button>
          )}
          {hasSearched && !loading && (
            <span className="text-xs text-[var(--muted2)] ml-auto tabular-nums">
              {results.length} results · {elapsed}ms
            </span>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="mt-5 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-600 text-sm">
            {error}
          </div>
        )}

        {/* Example queries (hero only) */}
        {heroMode && (
          <div className="mt-6 animate-fade-in">
            <div className="flex flex-wrap gap-2 justify-center">
              {EXAMPLE_QUERIES.slice(0, 6).map(q => (
                <button
                  key={q}
                  onClick={() => handleExample(q)}
                  className="text-xs text-[var(--muted)] hover:text-[var(--text)] border border-[var(--border)] hover:border-[var(--border-strong)] rounded-full px-3 py-1.5 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>

            {/* Use from Claude Code (MCP) */}
            <details className="mt-8 max-w-md mx-auto">
              <summary className="text-xs text-[var(--muted)] cursor-pointer hover:text-[var(--text)] text-center list-none">
                Use it from Claude Code / an MCP client →
              </summary>
              <pre className="mt-3 text-[11px] leading-relaxed bg-[var(--surface2)] border border-[var(--border)] rounded-lg p-3 overflow-x-auto text-[var(--text)]">{`claude mcp add rocqet \\
  --env ROCQET_API_URL=${API_URL} \\
  -- rocqet-mcp`}</pre>
              <p className="text-[11px] text-[var(--muted2)] mt-2 text-center">
                Exposes semantic search as agent tools. See the{" "}
                <a href="https://github.com/LLM4Rocq/rocqet-search#mcp-server" target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] hover:underline">README</a>.
              </p>
            </details>
          </div>
        )}

        {/* Loading skeletons */}
        {loading && results.length === 0 && (
          <div className="mt-5 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        )}

        {/* Results */}
        {results.length > 0 && (
          <div className="mt-5 space-y-3 pb-12">
            {results.map((r, i) => (
              <ResultCard key={`${r.library}-${r.file_path}-${r.line_number}-${r.name}`} r={r} rank={i} />
            ))}
          </div>
        )}

        {/* No results */}
        {hasSearched && results.length === 0 && !loading && !error && (
          <div className="text-center py-16 text-[var(--muted)]">
            <p className="text-base mb-1">No results found</p>
            <p className="text-sm text-[var(--muted2)]">Try different wording or remove filters.</p>
            {stats && (
              <p className="text-xs text-[var(--muted2)] mt-3 font-mono">
                Indexed: {Object.keys(stats.libraries).map(k => LIBRARY_LABELS[k] ?? k).join(", ")}
              </p>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="px-6 py-5 text-xs text-[var(--muted2)] flex items-center justify-between">
        <span>© 2026 Rocqet. Semantic search for Rocq.</span>
        <span className="flex items-center gap-4">
          {totalDecls > 0 && <span className="hidden sm:inline tabular-nums">{totalDecls.toLocaleString()} decls · {totalLibs} libs</span>}
          <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="hover:text-[var(--text)] transition-colors">
            <GitBranch size={15} />
          </a>
        </span>
      </footer>
    </div>
  );
}
