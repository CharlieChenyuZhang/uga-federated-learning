"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Building2,
  Check,
  ChevronRight,
  Cpu,
  Database,
  FlaskConical,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  MessageSquare,
  Network,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import Login from "./login";
import { useModelTools } from "./webmcp";
import Institution from "./institution";
import Evaluations from "./evaluations";
import Privacy from "./privacy";
import Playground from "./playground";
import { api, json, User, Overview, Dataset, Run, when } from "./api";
type Tab =
  "overview" | "institution" | "evaluations" | "privacy" | "playground";
const titles: Record<Tab, string> = {
  overview: "Overview",
  institution: "My institution",
  evaluations: "Evaluations",
  privacy: "Sharing & privacy",
  playground: "Model playground",
};
function locationFor(user: User) {
  const [page, query] = window.location.hash.slice(1).split("?");
  const fallback = user.role === "user" ? "playground" : "overview";
  const tab =
    Object.hasOwn(titles, page) &&
    (page !== "institution" || user.role === "contributor")
      ? (page as Tab)
      : fallback;
  return {
    tab,
    evaluationId:
      tab === "evaluations" ? new URLSearchParams(query).get("run") || "" : "",
  };
}
function tabUrl(tab: Tab, evaluationId = "") {
  return `#${tab}${tab === "evaluations" && evaluationId ? `?run=${encodeURIComponent(evaluationId)}` : ""}`;
}
export default function Workspace() {
  const [user, setUser] = useState<User | null>(null);
  const [boot, setBoot] = useState(true);
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [models, setModels] = useState<Run[]>([]);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  useModelTools(!!user);
  const sessionEpoch = useRef(0);
  const activeIdentity = useRef<string | null>(null);
  const [evaluationId, setEvaluationId] = useState("");
  function beginSession(next: User | null) {
    sessionEpoch.current++;
    activeIdentity.current = next?.id || null;
    setUser(next);
    setOverview(null);
    setRuns([]);
    setModels([]);
    setDatasets([]);
    setError("");
    setToast("");
    setUploadOpen(false);
    const location = next
      ? locationFor(next)
      : { tab: "overview" as Tab, evaluationId: "" };
    setTab(location.tab);
    setEvaluationId(location.evaluationId);
    window.history.replaceState(
      null,
      "",
      next
        ? tabUrl(location.tab, location.evaluationId)
        : window.location.pathname,
    );
  }
  const refresh = useCallback(async () => {
    if (!user || activeIdentity.current !== user.id) return;
    const epoch = sessionEpoch.current;
    try {
      const [o, r, m, d] = await Promise.all([
        api<Overview>("/overview"),
        api<Run[]>("/runs"),
        api<Run[]>("/models"),
        user.role === "contributor"
          ? api<Dataset[]>("/datasets")
          : Promise.resolve([]),
      ]);
      if (epoch !== sessionEpoch.current || activeIdentity.current !== user.id)
        return;
      setOverview(o);
      setRuns(r);
      setModels(m);
      setDatasets(d);
      setError("");
    } catch (e) {
      if (epoch === sessionEpoch.current && activeIdentity.current === user.id)
        setError((e as Error).message);
    }
  }, [user]);
  useEffect(() => {
    api<User>("/auth/me")
      .then(beginSession)
      .catch(() => {})
      .finally(() => setBoot(false));
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (!user) return;
    const restoreLocation = () => {
      const location = locationFor(user);
      setTab(location.tab);
      setEvaluationId(location.evaluationId);
      setUploadOpen(false);
      const canonical = tabUrl(location.tab, location.evaluationId);
      if (window.location.hash !== canonical)
        window.history.replaceState(null, "", canonical);
      window.scrollTo({ top: 0, behavior: "instant" });
    };
    window.addEventListener("hashchange", restoreLocation);
    window.addEventListener("popstate", restoreLocation);
    return () => {
      window.removeEventListener("hashchange", restoreLocation);
      window.removeEventListener("popstate", restoreLocation);
    };
  }, [user]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  async function logout() {
    try {
      await api("/auth/logout", json({}));
      beginSession(null);
      setTab("overview");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const navigate = (next: Tab, id = "") => {
    if (next === "institution" && user?.role !== "contributor")
      next = "playground";
    setTab(next);
    setEvaluationId(next === "evaluations" ? id : "");
    setUploadOpen(false);
    const url = tabUrl(next, id);
    if (window.location.hash !== url) window.history.pushState(null, "", url);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const upload = () => {
    navigate("institution");
    setUploadOpen(true);
  };
  if (boot)
    return (
      <div className="boot">
        <Network size={32} />
        <p>Opening your local workspace…</p>
      </div>
    );
  if (!user)
    return (
      <Login
        onLogin={(u) => {
          beginSession(u);
        }}
      />
    );
  const ownSchool = overview?.schools.find((s) => s.id === user.school_id);
  const completed = runs.filter((r) => r.status === "completed");
  const active = runs.find((r) => ["queued", "running"].includes(r.status));
  const nav = [
    { id: "overview" as Tab, icon: LayoutDashboard },
    { id: "institution" as Tab, icon: Building2 },
    { id: "playground" as Tab, icon: MessageSquare },
    { id: "evaluations" as Tab, icon: FlaskConical },
    { id: "privacy" as Tab, icon: ShieldCheck },
  ].filter((n) => user.role === "contributor" || n.id !== "institution");
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview">
          <span className="brand-mark">
            <Network size={22} />
          </span>
          campus<span className="brand-dot">.</span>
        </a>
        <span className="workspace-label">RESEARCH WORKSPACE</span>
        <nav aria-label="Main navigation">
          {nav.map((n) => (
            <a
              key={n.id}
              href={tabUrl(n.id)}
              title={titles[n.id]}
              className={`nav-item ${tab === n.id ? "active" : ""}`}
              aria-current={tab === n.id ? "page" : undefined}
            >
              <n.icon size={18} />
              {titles[n.id]}
              {n.id === "institution" && active && (
                <span className="nav-count">1</span>
              )}
            </a>
          ))}
        </nav>
        <div className="sidebar-lab">
          <Cpu size={18} />
          <div>
            <strong>TinyLlama 1.1B</strong>
            <small>Runs on this computer</small>
          </div>
        </div>
        <div className="sidebar-bottom">
          <span className="badge">LOCAL POC</span>
          <p>
            Independent workspaces.
            <br />
            Connected ideas.
          </p>
          <div className="profile">
            <div className={`avatar ${ownSchool?.color || "blue"}`}>
              {ownSchool?.short || "RG"}
            </div>
            <div>
              <strong>
                {ownSchool?.name === "University of Georgia"
                  ? "UGA Researcher"
                  : ownSchool?.name === "Georgia Tech"
                    ? "GT Researcher"
                    : ownSchool
                      ? "Emory Researcher"
                      : "Research Guest"}
              </strong>
              <small>
                {user.role === "contributor" ? "Contributor" : "User"}
              </small>
            </div>
            <button
              className="icon-button"
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
        <button
          className="mobile-signout icon-button"
          onClick={logout}
          aria-label="Sign out"
        >
          <LogOut size={19} />
        </button>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span>
            Workspace <span className="slash">/</span>
            <strong>{titles[tab]}</strong>
          </span>
          <div className="topbar-right">
            <span className="runtime-pill">
              <span
                className={`status-dot ${overview?.runtime.busy ? "busy" : ""}`}
              />
              {overview?.runtime.busy
                ? "Local model busy"
                : "Local environment"}
            </span>
            <span className="topbar-role">{user.role}</span>
          </div>
        </header>
        <main>
          {error && (
            <div className="error-box" role="alert">
              {error}
              <button className="text-button" onClick={refresh}>
                <RefreshCw size={14} />
                Retry
              </button>
            </div>
          )}
          {!overview ? (
            <div className="empty-state">
              <Network size={32} />
              <h2>Connecting to your lab</h2>
              <p>
                Start the local service with <code>./scripts/dev.sh</code>.
              </p>
              <button className="button" onClick={refresh}>
                Retry connection
              </button>
            </div>
          ) : (
            <>
              {tab === "overview" && (
                <>
                  <div className="page-heading">
                    <div>
                      <div className="eyebrow">COLLABORATIVE AI LAB</div>
                      <h1>Shared ideas. Local experiments.</h1>
                      <p>
                        Explore how different communities can learn, build, and
                        share across independent workspaces.
                      </p>
                    </div>
                    <button
                      className="button primary"
                      onClick={
                        user.role === "contributor"
                          ? upload
                          : () => navigate("playground")
                      }
                    >
                      {user.role === "contributor" ? (
                        <Upload size={17} />
                      ) : (
                        <MessageSquare size={17} />
                      )}{" "}
                      {user.role === "contributor"
                        ? "Upload a dataset"
                        : "Try a model"}
                    </button>
                  </div>
                  <div className="metric-grid">
                    {[
                      [
                        "Example workspaces",
                        String(overview.schools.length).padStart(2, "0"),
                        "Sample communities in this local POC",
                      ],
                      [
                        "Base model",
                        "TinyLlama",
                        "1.1B parameters · Llama architecture",
                      ],
                      [
                        user.role === "contributor"
                          ? "My completed runs"
                          : "Shared models",
                        String(completed.length).padStart(2, "0"),
                        active
                          ? "A training run is in progress"
                          : completed.length
                            ? "Measured on held-out examples"
                            : "Ready for the first experiment",
                      ],
                      [
                        "Data boundary",
                        "Private",
                        "Access is scoped by institution",
                      ],
                    ].map(([label, value, detail], i) => (
                      <div className="metric" key={label}>
                        <div className="metric-label">
                          <span>{label}</span>
                          {i === 0 ? (
                            <Building2 size={15} />
                          ) : i === 1 ? (
                            <Cpu size={15} />
                          ) : i === 2 ? (
                            <FlaskConical size={15} />
                          ) : (
                            <LockKeyhole size={15} />
                          )}
                        </div>
                        <strong>{value}</strong>
                        <small>{detail}</small>
                      </div>
                    ))}
                  </div>
                  <section className="panel network-panel">
                    <div className="section-title">
                      <div>
                        <h2>Explore the example network</h2>
                        <p>
                          Start from the same model. Learn from your own data.
                        </p>
                      </div>
                      <span className="badge">DEMO WORKSPACES</span>
                    </div>
                    <div className="foundation-strip">
                      <div className="foundation-icon">
                        <Network size={20} />
                      </div>
                      <div>
                        <strong>One shared foundation</strong>
                        <span>
                          TinyLlama-1.1B-Chat · Independent LoRA adapters
                        </span>
                      </div>
                      <span className="foundation-tag">
                        <LockKeyhole size={13} />
                        Private by default
                      </span>
                    </div>
                    <div className="school-grid">
                      {overview.schools.map((s) => (
                        <article
                          className={`school-card ${s.id === user.school_id ? "own-school" : ""}`}
                          key={s.id}
                        >
                          <div className="school-card-top">
                            <div className={`school-logo ${s.color}`}>
                              {s.short}
                            </div>
                            {s.id === user.school_id ? (
                              <span className="tag mine">YOUR INSTITUTION</span>
                            ) : (
                              <LockKeyhole size={15} color="#929bad" />
                            )}
                          </div>
                          <h3>{s.name}</h3>
                          <p>{s.city}</p>
                          <div className="school-focus">
                            <span>RESEARCH FOCUS</span>
                            {s.focus}
                          </div>
                          <div className="school-line">
                            <Database size={14} />
                            {s.id === user.school_id
                              ? `${datasets.length} private dataset${datasets.length === 1 ? "" : "s"}`
                              : "Institution-managed data"}
                          </div>
                          <button
                            className="school-footer"
                            onClick={() =>
                              s.id === user.school_id
                                ? navigate("institution")
                                : navigate("playground")
                            }
                          >
                            <span>
                              {s.id === user.school_id
                                ? "Open my workspace"
                                : `${s.shared_models} shared model${s.shared_models === 1 ? "" : "s"}`}
                            </span>
                            <ArrowUpRight size={17} />
                          </button>
                        </article>
                      ))}
                    </div>
                  </section>
                  <div className="two-column overview-bottom">
                    <section className="panel">
                      <div className="section-title">
                        <h2>Your next experiment</h2>
                        <FlaskConical size={18} color="#8792a8" />
                      </div>
                      <div className="workflow">
                        {[
                          {
                            n: "01",
                            title: "Bring your own examples",
                            detail: "Upload instruction-response pairs.",
                            done: datasets.length > 0,
                            target: "institution" as Tab,
                          },
                          {
                            n: "02",
                            title: "Tune a school adapter",
                            detail: "Train a small update to the base model.",
                            done: completed.length > 0,
                            target: "institution" as Tab,
                          },
                          {
                            n: "03",
                            title: "Measure, then decide",
                            detail: "Compare results before enabling access.",
                            done: completed.some((r) => r.shared),
                            target: "evaluations" as Tab,
                          },
                        ].map((step) => (
                          <button
                            className="workflow-row"
                            key={step.n}
                            onClick={() =>
                              navigate(
                                user.role === "user"
                                  ? "playground"
                                  : step.target,
                              )
                            }
                          >
                            <span
                              className={`step-number ${step.done ? "done" : ""}`}
                            >
                              {step.done ? <Check size={15} /> : step.n}
                            </span>
                            <span>
                              <strong>{step.title}</strong>
                              <small>{step.detail}</small>
                            </span>
                            <ChevronRight size={16} />
                          </button>
                        ))}
                      </div>
                    </section>
                    <section className="panel">
                      <div className="section-title">
                        <h2>Recent activity</h2>
                        <span className="text-muted small">
                          {user.role === "contributor"
                            ? "Your institution"
                            : "Shared models"}
                        </span>
                      </div>
                      {runs.length ? (
                        <div className="activity-list">
                          {runs.slice(0, 3).map((r) => (
                            <button
                              className="activity"
                              key={r.id}
                              onClick={() => {
                                if (r.status === "completed")
                                  navigate("evaluations", r.id);
                                else navigate("institution");
                              }}
                            >
                              <span
                                className={`activity-icon ${r.status === "completed" ? "complete" : ""}`}
                              >
                                <FlaskConical size={17} />
                              </span>
                              <span>
                                <strong>{r.name}</strong>
                                <small>
                                  {r.phase} · {when(r.created)}
                                </small>
                              </span>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className="activity-empty">
                          <div className="empty-icon">
                            <FlaskConical size={23} />
                          </div>
                          <strong>No experiments yet</strong>
                          <p>
                            Your training and evaluation activity will appear
                            here.
                          </p>
                          <button
                            className="text-button"
                            onClick={() =>
                              navigate(
                                user.role === "contributor"
                                  ? "institution"
                                  : "playground",
                              )
                            }
                          >
                            Start exploring
                            <ArrowRight size={14} />
                          </button>
                        </div>
                      )}
                    </section>
                  </div>
                  <div className="info-banner">
                    <ShieldCheck size={21} />
                    <div>
                      <strong>
                        Privacy is a design choice, not a model feature.
                      </strong>
                      <p>
                        Workspaces share this local server. Embeddings and model
                        updates can leak information; this POC does not
                        implement differential privacy or secure aggregation.
                      </p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("privacy")}
                    >
                      View boundaries
                      <ArrowRight size={14} />
                    </button>
                  </div>
                  <div className="page-foot">
                    <span>Campus research lab</span>
                    <span>
                      Synthetic examples only · No institutional affiliation
                      implied
                    </span>
                  </div>
                </>
              )}
              {tab === "institution" && user.role === "contributor" && (
                <Institution
                  user={user}
                  datasets={datasets}
                  runs={runs}
                  runtime={overview.runtime}
                  uploadOpen={uploadOpen}
                  setUploadOpen={setUploadOpen}
                  refresh={refresh}
                  notify={setToast}
                  onEvaluate={(id) => {
                    navigate("evaluations", id);
                  }}
                />
              )}{" "}
              {tab === "evaluations" && (
                <Evaluations
                  runs={runs}
                  user={user}
                  selectedId={evaluationId}
                  onSelect={(id) => navigate("evaluations", id)}
                  onTrain={() => navigate("institution")}
                />
              )}{" "}
              {tab === "privacy" && (
                <Privacy
                  runs={runs}
                  user={user}
                  refresh={refresh}
                  notify={setToast}
                />
              )}{" "}
              <div hidden={tab !== "playground"} key={user.id}>
                <Playground
                  models={models}
                  busy={overview.runtime.busy}
                  ready={overview.runtime.ml_available}
                />
              </div>
            </>
          )}
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Check size={18} />
          {toast}
        </div>
      )}
    </div>
  );
}
