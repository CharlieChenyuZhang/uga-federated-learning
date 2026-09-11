"use client";
import { useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  GraduationCap,
  LockKeyhole,
  Network,
  Users,
} from "lucide-react";
import { api, json, User } from "./api";
export default function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [role, setRole] = useState("contributor");
  const [school, setSchool] = useState("uga");
  const [password, setPassword] = useState("local-lab");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(
        await api<User>(
          "/auth/login",
          json({ account: role === "user" ? "user" : school, password }),
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <section className="login-story">
        <a className="brand" href="/">
          <span className="brand-mark">
            <Network size={22} />
          </span>
          campus<span className="brand-dot">.</span>
        </a>
        <div className="login-story-body">
          <span className="badge">FEDERATED LEARNING LAB</span>
          <h1>
            Shared knowledge.
            <br />
            <span>Independent learning.</span>
          </h1>
          <p>
            A small model. Three campus workspaces.
            <br />A clearer path from local data to better teaching.
          </p>
          <div
            className="login-network"
            aria-label="Three independent school workspaces use a common TinyLlama base model"
          >
            <div className="network-base">
              <Network size={24} />
              <span>
                TinyLlama <small>Shared foundation · 1.1B</small>
              </span>
            </div>
            <div className="network-branches">
              <span />
              <span />
              <span />
            </div>
            <div className="network-schools">
              <div>
                <b>UG</b>
                <span>Georgia</span>
              </div>
              <div>
                <b>GT</b>
                <span>Georgia Tech</span>
              </div>
              <div>
                <b>EU</b>
                <span>Emory</span>
              </div>
            </div>
          </div>
          <div className="login-story-note">
            <LockKeyhole size={16} />
            <span>Private datasets. Deliberate sharing.</span>
          </div>
        </div>
        <div className="login-foot">
          LOCAL RESEARCH POC <span>STEM+C EDUCATION</span>
        </div>
      </section>
      <section className="login-form-side">
        <div className="login-form-wrap">
          <span className="eyebrow">YOUR RESEARCH STARTS HERE</span>
          <h2>Welcome to the lab.</h2>
          <p>Choose how you want to participate.</p>
          <form onSubmit={submit}>
            <div className="role-options">
              <button
                type="button"
                className={`role-card ${role === "contributor" ? "selected" : ""}`}
                onClick={() => setRole("contributor")}
              >
                <span className="role-icon">
                  <GraduationCap size={22} />
                </span>
                <strong>Contributor</strong>
                <small>Upload, tune & evaluate</small>
                {role === "contributor" && (
                  <Check className="role-check" size={16} />
                )}
              </button>
              <button
                type="button"
                className={`role-card ${role === "user" ? "selected" : ""}`}
                onClick={() => setRole("user")}
              >
                <span className="role-icon">
                  <BookOpen size={22} />
                </span>
                <strong>User</strong>
                <small>Explore shared models</small>
                {role === "user" && <Check className="role-check" size={16} />}
              </button>
            </div>
            {role === "contributor" ? (
              <label className="field">
                Institution
                <select
                  value={school}
                  onChange={(e) => setSchool(e.target.value)}
                >
                  <option value="uga">University of Georgia</option>
                  <option value="gatech">Georgia Tech</option>
                  <option value="emory">Emory University</option>
                </select>
              </label>
            ) : (
              <div className="guest-note">
                <Users size={18} />
                <span>
                  Sign in as Research Guest. Use the base model and any models
                  contributors have shared.
                </span>
              </div>
            )}
            <label className="field">
              Local demo password
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            <p className="field-help">
              Prefilled for local testing: <code>local-lab</code>
            </p>
            {error && (
              <div className="error-box" role="alert">
                {error}
              </div>
            )}
            <button className="button primary login-submit" disabled={busy}>
              {busy ? "Signing in…" : "Enter workspace"}
              <ArrowRight size={18} />
            </button>
          </form>
          <div className="login-disclaimer">
            <LockKeyhole size={16} />
            <p>
              Demo accounts for this computer only. Institution names are
              illustrative; no real student data is included.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
