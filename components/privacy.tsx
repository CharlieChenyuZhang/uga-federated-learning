"use client";
import { useState } from "react";
import {
  Check,
  ExternalLink,
  Eye,
  FileLock2,
  Info,
  LockKeyhole,
  Network,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { api, json, Run, User } from "./api";
export default function Privacy({
  runs,
  user,
  refresh,
  notify,
}: {
  runs: Run[];
  user: User;
  refresh: () => Promise<void>;
  notify: (s: string) => void;
}) {
  const [ack, setAck] = useState<Record<string, boolean>>({});
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  async function change(run: Run) {
    setPending(run.id);
    setError("");
    try {
      await api(
        `/runs/${run.id}/sharing`,
        json({ shared: !run.shared, acknowledge_risk: !!ack[run.id] }, "PATCH"),
      );
      await refresh();
      notify(
        run.shared
          ? "Model access returned to private."
          : "Model is now available to signed-in lab users.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending("");
    }
  }
  const completed = runs.filter((r) => r.status === "completed");
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">INTENTIONAL SHARING</div>
          <h1>Keep the boundary clear.</h1>
          <p>
            Sharing useful knowledge starts with knowing what can leave a
            workspace.
          </p>
        </div>
        <span className="privacy-header-icon">
          <ShieldCheck size={29} />
        </span>
      </div>
      <section className="privacy-answer">
        <div className="privacy-answer-icon">
          <ShieldAlert size={25} />
        </div>
        <div>
          <span className="eyebrow">CAN WE SAFELY SHARE EMBEDDINGS?</span>
          <h2>Embeddings are not anonymized data.</h2>
          <p>
            Vectors can reveal details about their source text and can be
            vulnerable to reconstruction attacks. Model adapters and generated
            answers may also expose training information. This lab keeps raw
            embedding export disabled.
          </p>
          <a
            href="https://arxiv.org/abs/2310.06816"
            target="_blank"
            rel="noreferrer"
            className="text-button"
          >
            Read the embedding inversion research
            <ExternalLink size={14} />
          </a>
        </div>
      </section>
      <section className="panel">
        <div className="section-title">
          <div>
            <h2>What is shared in this POC?</h2>
            <p>
              These controls apply to the website. A computer administrator can
              access the local files.
            </p>
          </div>
          <span className="badge">LOGICAL ISOLATION</span>
        </div>
        <div className="table-wrap">
          <table className="privacy-table">
            <thead>
              <tr>
                <th>Information</th>
                <th>Default boundary</th>
                <th>Available to other accounts?</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Raw dataset", "Institution only", "No"],
                ["Raw embeddings", "Export disabled", "No"],
                ["Held-out prompts & answers", "Institution only", "No"],
                [
                  "Adapter weights",
                  "Stored on this computer",
                  "No download endpoint",
                ],
                [
                  "Model inference access",
                  "Institution only",
                  "Only after contributor enables sharing",
                ],
                [
                  "Aggregate evaluation metrics",
                  "Institution only",
                  "Included with shared model access",
                ],
              ].map(([a, b, c]) => (
                <tr key={a}>
                  <td>{a}</td>
                  <td>
                    <LockKeyhole size={13} />
                    {b}
                  </td>
                  <td>{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {user.role === "contributor" && (
        <section className="panel">
          <div className="section-title">
            <div>
              <h2>Manage model access</h2>
              <p>
                Enable a completed adapter for other signed-in accounts. You can
                revoke access at any time.
              </p>
            </div>
            <Eye size={20} color="#8491ac" />
          </div>
          {error && (
            <div className="error-box" role="alert">
              {error}
            </div>
          )}
          {!completed.length ? (
            <div className="compact-empty">
              <FileLock2 size={25} />
              <p>
                Complete your first training run to review its sharing options.
              </p>
            </div>
          ) : (
            <div className="sharing-list">
              {completed.map((run) => (
                <div className="sharing-card" key={run.id}>
                  <div className="sharing-card-head">
                    <div className="file-icon">
                      <Network size={20} />
                    </div>
                    <div>
                      <h3>{run.name}</h3>
                      <p>
                        {run.metrics?.eval_examples} held-out examples ·{" "}
                        {run.shared
                          ? "Inference and numeric metrics shared"
                          : "Visible only to your institution"}
                      </p>
                    </div>
                    <span className={`tag ${run.shared ? "success" : ""}`}>
                      {run.shared ? "Shared" : "Private"}
                    </span>
                  </div>
                  {!run.shared && (
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={!!ack[run.id]}
                        onChange={(e) =>
                          setAck({ ...ack, [run.id]: e.target.checked })
                        }
                      />
                      <span>
                        I have reviewed this model and understand that outputs
                        may reveal training information. Sharing provides no
                        formal privacy guarantee.
                      </span>
                    </label>
                  )}
                  <div className="sharing-card-action">
                    <span>
                      <LockKeyhole size={13} />
                      Raw data and evaluation samples remain private
                    </span>
                    <button
                      className={`button ${run.shared ? "" : "primary"}`}
                      disabled={!!pending || (!run.shared && !ack[run.id])}
                      onClick={() => change(run)}
                    >
                      {pending === run.id
                        ? "Updating…"
                        : run.shared
                          ? "Revoke shared access"
                          : "Enable shared access"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}
      <div className="two-column">
        <section className="panel boundary-card">
          <div className="section-title">
            <h2>Implemented here</h2>
            <ShieldCheck size={19} />
          </div>
          {[
            "Server-enforced roles and institution ownership",
            "Private datasets and adapters by default",
            "Explicit, revocable model access",
            "Common-pattern PII screening on uploads",
            "Held-out evaluation before sharing",
          ].map((t) => (
            <p key={t}>
              <Check size={16} />
              {t}
            </p>
          ))}
        </section>
        <section className="panel boundary-card future">
          <div className="section-title">
            <h2>Beyond this experiment</h2>
            <Info size={19} />
          </div>
          {[
            "Separate institution-owned machines",
            "Federated rounds and adapter aggregation",
            "Differential privacy with an explicit budget",
            "Secure aggregation or encrypted computation",
            "Identity verification and production access controls",
          ].map((t) => (
            <p key={t}>
              <span className="future-dash" />
              {t}
            </p>
          ))}
        </section>
      </div>
      <div className="info-banner">
        <Info size={21} />
        <div>
          <strong>Local collaboration POC, not a privacy certification.</strong>
          <p>
            All three workspaces run on a single local server. This
            implementation does not claim FERPA/GDPR compliance, cryptographic
            isolation, or protection from model inversion. Use synthetic or
            approved de-identified data.
          </p>
        </div>
      </div>
    </>
  );
}
