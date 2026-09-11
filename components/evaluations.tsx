"use client";
import { useState } from "react";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Download,
  FlaskConical,
  Info,
} from "lucide-react";
import { Run, User, when, schoolNames } from "./api";
function LossChart({ history }: { history: { step: number; loss: number }[] }) {
  const vals = history.map((h) => h.loss);
  const min = Math.min(...vals) * 0.92;
  const max = Math.max(...vals) * 1.05;
  const range = max - min || 1;
  const points = history
    .map(
      (h, i) =>
        `${48 + (i / Math.max(history.length - 1, 1)) * 622},${175 - ((h.loss - min) / range) * 135}`,
    )
    .join(" ");
  return (
    <svg
      viewBox="0 0 710 220"
      className="loss-chart"
      role="img"
      aria-label={`Actual training loss over ${history.length} optimizer steps. First loss ${vals[0]?.toFixed(3)}, last loss ${vals.at(-1)?.toFixed(3)}.`}
    >
      {[0, 0.5, 1].map((v, i) => (
        <g key={i}>
          <line
            x1="48"
            x2="680"
            y1={175 - v * 135}
            y2={175 - v * 135}
            stroke="#e9edf5"
            strokeDasharray="4 5"
          />
          <text x="8" y={179 - v * 135} fill="#7d899c" fontSize="12">
            {(min + range * v).toFixed(2)}
          </text>
        </g>
      ))}
      <polyline
        fill="none"
        stroke="#596be2"
        strokeWidth="3"
        points={points}
        strokeLinejoin="round"
      />
      {history.map((h, i) => (
        <circle
          key={h.step}
          cx={48 + (i / Math.max(history.length - 1, 1)) * 622}
          cy={175 - ((h.loss - min) / range) * 135}
          r="3.5"
          fill="#596be2"
        >
          <title>
            Step {h.step}: {h.loss.toFixed(4)}
          </title>
        </circle>
      ))}
      <text x="48" y="205" fill="#7d899c" fontSize="12">
        Step 1
      </text>
      <text x="625" y="205" fill="#7d899c" fontSize="12">
        Step {history.length}
      </text>
    </svg>
  );
}
export default function Evaluations({
  runs,
  user,
  onTrain,
  initialId,
}: {
  runs: Run[];
  user: User;
  onTrain: () => void;
  initialId: string;
}) {
  const [choice, setChoice] = useState(initialId);
  const complete = runs.filter((r) => r.status === "completed" && r.metrics);
  const run = complete.find((r) => r.id === choice) || complete[0];
  const m = run?.metrics;
  function download() {
    if (!run) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(run, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `campus-evaluation-${run.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  const change = m
    ? ((m.tuned.loss - m.baseline.loss) / m.baseline.loss) * 100
    : 0;
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MEASURE WHAT CHANGED</div>
          <h1>Evidence before sharing.</h1>
          <p>
            Compare the base model and school adapter on the same held-out
            examples.
          </p>
        </div>
        {m && (
          <button className="button" onClick={download}>
            <Download size={16} />
            Export evaluation
          </button>
        )}
      </div>
      {!m ? (
        <section className="panel empty-state">
          <div className="empty-icon">
            <FlaskConical size={30} />
          </div>
          <h2>No evaluation results yet</h2>
          <p>
            {user.role === "contributor"
              ? "Finish a training run to see real baseline and tuned metrics. We never fill this view with simulated scores."
              : "Results will appear when a contributor shares a completed model."}
          </p>
          {user.role === "contributor" && (
            <button className="button primary" onClick={onTrain}>
              Start an experiment
              <ArrowRight size={16} />
            </button>
          )}
        </section>
      ) : (
        <>
          <div className="evaluation-picker">
            <label className="field">
              Experiment
              <select
                value={run.id}
                onChange={(e) => setChoice(e.target.value)}
              >
                {complete.map((r) => (
                  <option value={r.id} key={r.id}>
                    {r.name} · {schoolNames[r.school_id]} · {when(r.created)}
                  </option>
                ))}
              </select>
            </label>
            <span className="tag success">Measured locally</span>
          </div>
          <div className="metric-grid evaluation-metrics">
            <div className="metric">
              <span>Held-out loss change</span>
              <strong className={change <= 0 ? "positive" : "negative"}>
                {change <= 0 ? (
                  <ArrowDownRight size={24} />
                ) : (
                  <ArrowUpRight size={24} />
                )}{" "}
                {Math.abs(change).toFixed(1)}%
              </strong>
              <small>
                {change <= 0
                  ? "Lower loss on this small test split"
                  : "Loss increased on this test split"}
              </small>
            </div>
            <div className="metric">
              <span>Evaluation examples</span>
              <strong>{m.eval_examples}</strong>
              <small>{m.train_examples} separate training examples</small>
            </div>
            <div className="metric">
              <span>Scored answer tokens</span>
              <strong>{m.tuned.tokens}</strong>
              <small>Prompt and padding tokens excluded</small>
            </div>
            <div className="metric">
              <span>Training + tuned evaluation</span>
              <strong>
                {m.seconds < 60
                  ? `${m.seconds.toFixed(0)}s`
                  : `${(m.seconds / 60).toFixed(1)}m`}
              </strong>
              <small>
                {m.device.toUpperCase()} · excludes loading and baseline
              </small>
            </div>
          </div>
          <section className="panel">
            <div className="section-title">
              <div>
                <h2>Base vs. school adapter</h2>
                <p>
                  Lower is better for both metrics. This is a small-sample
                  experiment, not a general quality benchmark.
                </p>
              </div>
              <span className="badge">SAME TEST SPLIT</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Answer loss</th>
                    <th>Perplexity</th>
                    <th>Data used for evaluation</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      <span className="model-table-mark base" />
                      TinyLlama base
                    </td>
                    <td>{m.baseline.loss.toFixed(4)}</td>
                    <td>{m.baseline.perplexity.toFixed(2)}</td>
                    <td>{m.eval_examples} held-out examples</td>
                  </tr>
                  <tr>
                    <td>
                      <span className="model-table-mark" />
                      {run.name}
                    </td>
                    <td>{m.tuned.loss.toFixed(4)}</td>
                    <td>{m.tuned.perplexity.toFixed(2)}</td>
                    <td>The same {m.eval_examples} examples</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="subtle-note">
              <Info size={15} />
              <p>
                Loss is the token-weighted negative log-likelihood of the
                expected answer. Perplexity is exp(loss), capped at exp(20) for
                display. Better values do not establish teaching effectiveness
                or privacy.
              </p>
            </div>
          </section>
          {run.history && run.history.length > 0 && (
            <section className="panel">
              <div className="section-title">
                <div>
                  <h2>Training loss</h2>
                  <p>
                    Actual loss recorded after each optimizer step. This is
                    training data, separate from the evaluation above.
                  </p>
                </div>
                <span className="chart-legend">
                  <i />
                  School adapter
                </span>
              </div>
              <LossChart history={run.history} />
            </section>
          )}
          {m.samples?.map((sample, i) => (
            <section className="panel" key={i}>
              <div className="section-title">
                <div>
                  <h2>Read the outputs</h2>
                  <p>
                    One held-out example. A qualitative spot check, not an
                    automatic correctness score.
                  </p>
                </div>
                <span className="tag">PRIVATE TO YOUR SCHOOL</span>
              </div>
              <div className="prompt-block">
                <span>HELD-OUT INSTRUCTION</span>
                <p>{sample.instruction}</p>
              </div>
              <div className="two-column response-columns">
                <div className="answer-card">
                  <div>
                    <span className="model-table-mark base" />
                    <strong>Base model</strong>
                  </div>
                  <p>{sample.baseline || "(No text generated)"}</p>
                </div>
                <div className="answer-card tuned">
                  <div>
                    <span className="model-table-mark" />
                    <strong>School adapter</strong>
                  </div>
                  <p>{sample.tuned || "(No text generated)"}</p>
                </div>
              </div>
              <details className="expected-answer">
                <summary>View the reference answer</summary>
                <p>{sample.expected}</p>
              </details>
            </section>
          ))}
          <div className="info-banner">
            <Info size={21} />
            <div>
              <strong>Keep the conclusion proportional to the evidence.</strong>
              <p>
                The split is deterministic and deduplicates instructions.
                Similar topics may still occur in both splits. These results do
                not measure demographic fairness, factual reliability, or
                resistance to privacy attacks.
              </p>
            </div>
          </div>
        </>
      )}
    </>
  );
}
