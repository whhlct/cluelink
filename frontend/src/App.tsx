import { FormEvent, useEffect, useState } from "react";

// In development Vite proxies /v1 to the backend, avoiding browser-to-WSL port forwarding.
// Set VITE_API_URL when deploying the static client with a separately hosted API.
const API_URL = import.meta.env.VITE_API_URL ?? "";
const LAST_SESSION_KEY = "cluelink:last-session";
const PUZZLE_TYPES = ["connection", "hidden_entity", "common_link"] as const;
const DIFFICULTIES = ["easy", "medium", "hard"] as const;

type Entity = { id: string; name: string; entity_type: string };
type GameRoute = { puzzleType: string; difficulty: string };
type Session = {
  session_id: string;
  status: "active" | "won" | "failed";
  failure_reason?: string | null;
  puzzle: { id: string; type: string; difficulty: string; payload: Record<string, unknown> };
  progress: { current_entity?: Entity | null; moves: number; guesses: number; wrong_guesses: number; hints: number; remaining_guesses: number | null; stars?: number | null; elapsed_seconds: number };
  hint?: Record<string, unknown>;
  solution?: { kind: string; path?: Entity[]; relations?: string[]; answers?: Entity[] };
  last_relation?: string;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) }, ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Request failed");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

function routeFromLocation(): GameRoute | null {
  const [puzzleType, difficulty, ...remaining] = window.location.pathname.split("/").filter(Boolean);
  if (remaining.length > 0 || !PUZZLE_TYPES.includes(puzzleType as typeof PUZZLE_TYPES[number]) || !DIFFICULTIES.includes(difficulty as typeof DIFFICULTIES[number])) return null;
  return { puzzleType, difficulty };
}

function EntityPicker({ onSelect, entityType }: { onSelect: (entity: Entity) => void; entityType?: string }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Entity[]>([]);
  useEffect(() => {
    if (query.trim().length < 2) return void setResults([]);
    const timer = window.setTimeout(() => {
      const suffix = entityType ? `&entity_type=${encodeURIComponent(entityType)}` : "";
      request<Entity[]>(`/v1/entities?query=${encodeURIComponent(query)}${suffix}`).then(setResults).catch(() => setResults([]));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [query, entityType]);
  return <div className="picker">
    <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search people or movies" />
    {results.length > 0 && <ul>{results.map((entity) => <li key={entity.id}><button onClick={() => { onSelect(entity); setQuery(""); setResults([]); }}>{entity.name} <small>{entity.entity_type}</small></button></li>)}</ul>}
  </div>;
}

export function App() {
  const initialRoute = routeFromLocation();
  const [session, setSession] = useState<Session | null>(null);
  const [puzzleType, setPuzzleType] = useState(initialRoute?.puzzleType ?? "connection");
  const [difficulty, setDifficulty] = useState(initialRoute?.difficulty ?? "easy");
  const [route, setRoute] = useState<GameRoute | null>(initialRoute);
  const [error, setError] = useState("");
  const [hint, setHint] = useState<Record<string, unknown> | null>(null);
  const [givingUp, setGivingUp] = useState(false);

  const navigateToGame = (next: Session) => {
    const nextRoute = { puzzleType: next.puzzle.type, difficulty: next.puzzle.difficulty };
    const path = `/${nextRoute.puzzleType}/${nextRoute.difficulty}`;
    if (window.location.pathname !== path) window.history.pushState({}, "", path);
    setRoute(nextRoute);
  };

  const update = async (action: () => Promise<Session>) => {
    try {
      setError("");
      const next = await action();
      setSession(next);
      setHint(next.hint ?? null);
      localStorage.setItem(LAST_SESSION_KEY, next.session_id);
      navigateToGame(next);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Request failed"); }
  };

  useEffect(() => {
    const onPopState = () => setRoute(routeFromLocation());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (route) {
      setPuzzleType(route.puzzleType);
      setDifficulty(route.difficulty);
    }
    const sessionId = localStorage.getItem(LAST_SESSION_KEY);
    if (!sessionId) return;
    let cancelled = false;
    request<Session>(`/v1/sessions/${sessionId}`).then((next) => {
      if (cancelled) return;
      const matchesRoute = !route || (next.puzzle.type === route.puzzleType && next.puzzle.difficulty === route.difficulty);
      if (!matchesRoute) {
        setSession(null);
        setHint(null);
        return;
      }
      setSession(next);
      setHint(next.hint ?? null);
      if (!route) navigateToGame(next);
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : "Request failed");
    });
    return () => { cancelled = true; };
  }, [route]);

  const start = (event: FormEvent) => {
    event.preventDefault();
    update(() => request<Session>("/v1/sessions", { method: "POST", body: JSON.stringify({ puzzle_type: puzzleType, difficulty }) }));
  };

  const playAnother = () => {
    localStorage.removeItem(LAST_SESSION_KEY);
    window.history.pushState({}, "", "/");
    setRoute(null);
    setSession(null);
    setHint(null);
    setGivingUp(false);
  };
  const terminal = session && session.status !== "active";
  const payload = session?.puzzle.payload;

  return <main>
    <header><h1>Cluelink</h1><p>Find the film-world connection.</p></header>
    {error && <p className="error" role="alert">{error}</p>}
    {!session && <form className="card" onSubmit={start}>
      <h2>Start a puzzle</h2>
      <label>Mode<select value={puzzleType} onChange={(event) => setPuzzleType(event.target.value)}><option value="connection">Connection path</option><option value="hidden_entity">Hidden entity</option><option value="common_link">Common link</option></select></label>
      <label>Difficulty<select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
      <button type="submit">Play</button>
    </form>}
    {session && <section className="card">
      <div className="meta"><span>{session.puzzle.type.replace("_", " ")}</span><span>{session.puzzle.difficulty}</span></div>
      <h2>{String(payload?.prompt ?? "")}</h2>
      {Array.isArray(payload?.clues) && <ul className="clues">{(payload.clues as Entity[]).map((clue) => <li key={clue.id}>{clue.name}</li>)}</ul>}
      {session.puzzle.type === "connection" && <p>Current: <strong>{session.progress.current_entity?.name}</strong> → Target: <strong>{(payload?.target as Entity)?.name}</strong></p>}
      <p className="stats">Moves: {session.progress.moves} · Guesses: {session.progress.guesses}{session.progress.remaining_guesses === null ? " (unlimited)" : ` / ${session.progress.guesses + session.progress.remaining_guesses}`} · Hints: {session.progress.hints} · {session.progress.elapsed_seconds}s</p>
      {!terminal && <>
        <EntityPicker entityType={session.puzzle.type === "connection" ? undefined : String(payload?.answer_entity_type)} onSelect={(entity) => update(() => request<Session>(`/v1/sessions/${session.session_id}/${session.puzzle.type === "connection" ? "moves" : "guesses"}`, { method: "POST", body: JSON.stringify({ entity_id: entity.id }) }))} />
        <div className="actions"><button onClick={() => update(() => request<Session>(`/v1/sessions/${session.session_id}/hints`, { method: "POST" }))}>Hint</button><button className="danger" onClick={() => setGivingUp(true)}>Give up</button></div>
        {hint && <aside className="hint"><strong>Hint:</strong> {hint.next_entity ? `Try ${(hint.next_entity as Entity).name}` : hint.relation_type ? `Relation: ${hint.relation_type}` : hint.answer_initial ? `Answer starts with ${hint.answer_initial}` : `Answer type: ${hint.answer_entity_type}`}</aside>}
      </>}
      {givingUp && !terminal && <div className="dialog"><p>Give up and reveal the solution?</p><button className="danger" onClick={() => update(() => request<Session>(`/v1/sessions/${session.session_id}/give-up`, { method: "POST" }))}>Reveal solution</button><button onClick={() => setGivingUp(false)}>Keep playing</button></div>}
      {terminal && <section className={session.status === "won" ? "terminal won" : "terminal failed"}>
        <h2>{session.status === "won" ? `${"★".repeat(session.progress.stars ?? 1)} You solved it` : `Game over: ${session.failure_reason?.replaceAll("_", " ")}`}</h2>
        <Solution solution={session.solution} /><p>Moves {session.progress.moves} · Wrong guesses {session.progress.wrong_guesses} · Hints {session.progress.hints} · {session.progress.elapsed_seconds}s</p><button onClick={playAnother}>Play another</button>
      </section>}
    </section>}
  </main>;
}

function Solution({ solution }: { solution?: Session["solution"] }) {
  if (!solution) return null;
  if (solution.kind === "path") return <div><h3>Solution path</h3><ol>{solution.path?.map((node, index) => <li key={node.id}>{node.name}{solution.relations?.[index] ? ` — ${solution.relations[index]} →` : ""}</li>)}</ol></div>;
  return <div><h3>Solution</h3><p>{solution.answers?.map((answer) => answer.name).join(", ")}</p></div>;
}
