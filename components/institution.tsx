"use client";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Database,
  Download,
  FileJson,
  FlaskConical,
  Info,
  LoaderCircle,
  LockKeyhole,
  Play,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  api,
  json,
  Dataset,
  Run,
  User,
  Overview,
  schoolNames,
  when,
} from "./api";
export default function Institution({
  user,
  datasets,
  runs,
  runtime,
  uploadOpen,
  setUploadOpen,
  refresh,
  notify,
  onEvaluate,
}: {
  user: User;
  datasets: Dataset[];
  runs: Run[];
  runtime: Overview["runtime"];
  uploadOpen: boolean;
  setUploadOpen: (v: boolean) => void;
  refresh: () => Promise<void>;
  notify: (s: string) => void;
  onEvaluate: (id: string) => void;
}) {
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("STEM coaching adapter");
  const [steps, setSteps] = useState(8);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const [uploadError, setUploadError] = useState("");
  useEffect(() => {
    if (!datasets.some((d) => d.id === selected))
      setSelected(datasets[0]?.id || "");
  }, [datasets, selected]);
  useEffect(() => {
    if (uploadOpen) dialog.current?.showModal();
    else dialog.current?.close();
  }, [uploadOpen]);
  async function sample() {
    setPending("sample");
    setError("");
    try {
      const d = await api<Dataset>("/datasets/sample", json({}));
      setSelected(d.id);
      await refresh();
      notify("Synthetic examples are ready in your workspace.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending("");
    }
  }
  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !consent) return;
    setPending("upload");
    setUploadError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const d = await api<Dataset>("/datasets", { method: "POST", body: form });
      await refresh();
      setSelected(d.id);
      setUploadOpen(false);
      setFile(null);
      setConsent(false);
      notify(`${d.row_count} examples uploaded and checked.`);
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setPending("");
    }
  }
  async function train(e: React.FormEvent) {
    e.preventDefault();
    setPending("train");
    setError("");
    try {
      await api("/runs", json({ dataset_id: selected, steps, name }));
      await refresh();
      notify("Training started. You can follow the run below.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending("");
    }
  }
  async function remove(id: string) {
    setPending(id);
    setError("");
    try {
      await api(`/datasets/${id}`, { method: "DELETE" });
      await refresh();
      notify("Dataset removed from this workspace.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending("");
    }
  }
  const active = runs.find((r) => ["queued", "running"].includes(r.status));
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CONTRIBUTOR WORKSPACE</div>
          <h1>{schoolNames[user.school_id || "uga"]}</h1>
          <p>
            Your examples, adapters, and evaluation results stay private until
            you choose to share model access.
          </p>
        </div>
        <button className="button primary" onClick={() => setUploadOpen(true)}>
          <Upload size={17} />
          Upload dataset
        </button>
      </div>
      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}
      <div className="two-column institution-columns">
        <section className="panel">
          <div className="section-title">
            <div>
              <h2>1. Prepare your data</h2>
              <p>Short instruction-response pairs work best.</p>
            </div>
            <span className="count-label">{datasets.length}</span>
          </div>
          {datasets.length ? (
            <div className="dataset-list">
              {datasets.map((d) => (
                <div
                  className={`dataset-row ${selected === d.id ? "selected" : ""}`}
                  key={d.id}
                >
                  <button
                    className="dataset-select"
                    onClick={() => setSelected(d.id)}
                  >
                    <div className="file-icon">
                      <FileJson size={20} />
                    </div>
                    <span>
                      <strong>{d.name}</strong>
                      <small>
                        {d.row_count} examples ·{" "}
                        {d.synthetic ? "Synthetic sample" : "Uploaded"}
                        <span className="dataset-private">
                          <LockKeyhole size={11} />
                          Private
                        </span>
                      </small>
                    </span>
                  </button>
                  <button
                    className="icon-button"
                    onClick={() => remove(d.id)}
                    disabled={
                      !!pending || runs.some((r) => r.dataset_id === d.id)
                    }
                    title={
                      runs.some((r) => r.dataset_id === d.id)
                        ? "Retained for run reproducibility"
                        : "Delete unused dataset"
                    }
                    aria-label={`Delete ${d.name}`}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="dataset-empty">
              <div className="empty-icon">
                <Database size={25} />
              </div>
              <h3>A place for your campus knowledge</h3>
              <p>
                Upload your prepared examples, or try 24 synthetic STEM coaching
                examples.
              </p>
              <button className="button" onClick={sample} disabled={!!pending}>
                {pending === "sample" ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Plus size={16} />
                )}
                Use sample dataset
              </button>
            </div>
          )}
          <div className="dataset-actions">
            <a className="text-button" href="/api/datasets/template">
              <Download size={14} />
              Download example JSONL
            </a>
            {datasets.length > 0 && !datasets.some((d) => d.synthetic) && (
              <button
                className="text-button"
                disabled={!!pending}
                onClick={sample}
              >
                Add sample
              </button>
            )}
          </div>
          <div className="subtle-note">
            <Info size={15} />
            <p>
              6–500 unique examples · CSV or JSONL · Up to 2 MB
              <br />
              We screen for common email, phone, and SSN patterns. This is not a
              complete privacy review.
            </p>
          </div>
        </section>
        <section className="panel">
          <div className="section-title">
            <div>
              <h2>2. Fine-tune an adapter</h2>
              <p>A small, independent update to TinyLlama.</p>
            </div>
            <FlaskConical size={20} color="#7b89b4" />
          </div>
          <form onSubmit={train}>
            <label className="field">
              Training dataset
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                required
                disabled={!datasets.length}
              >
                <option value="" disabled>
                  Select a dataset
                </option>
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.row_count} examples)
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Experiment name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={80}
                required
              />
            </label>
            <div className="training-settings">
              <div>
                <span>Base model</span>
                <strong>TinyLlama 1.1B</strong>
              </div>
              <div>
                <span>Method</span>
                <strong>LoRA · rank 8</strong>
              </div>
              <div>
                <span>Context</span>
                <strong>256 tokens</strong>
              </div>
            </div>
            <label className="field">
              Training budget
              <select
                value={steps}
                onChange={(e) => setSteps(Number(e.target.value))}
              >
                <option value={2}>Smoke test · 2 steps</option>
                <option value={8}>Quick experiment · 8 steps</option>
                <option value={30}>Longer experiment · 30 steps</option>
                <option value={100}>Extended experiment · 100 steps</option>
              </select>
            </label>
            <div className="training-note">
              <LockKeyhole size={15} />
              <p>
                Training runs on this computer. The first run downloads
                approximately 2.2 GB of model weights. Your examples are not
                sent to Hugging Face.
              </p>
            </div>
            <button
              className="button primary full"
              disabled={
                !!pending || !selected || runtime.busy || !runtime.ml_available
              }
            >
              <Play size={16} />
              {runtime.busy
                ? "Local model is busy"
                : pending === "train"
                  ? "Starting run…"
                  : "Start local fine-tuning"}
            </button>
            {!runtime.ml_available && (
              <p className="field-help">
                Install training dependencies with{" "}
                <code>./scripts/setup.sh</code>.
              </p>
            )}
          </form>
        </section>
      </div>
      <section className="panel">
        <div className="section-title">
          <div>
            <h2>Training runs</h2>
            <p>
              Progress is reported by the local worker. Evaluation follows each
              completed run.
            </p>
          </div>
          <span className="badge">
            {active ? "RUN IN PROGRESS" : "LOCAL WORKER"}
          </span>
        </div>
        {!runs.length ? (
          <div className="compact-empty">
            <FlaskConical size={24} />
            <p>
              Your first run will appear here. Start with the sample dataset
              above.
            </p>
          </div>
        ) : (
          <div className="run-list">
            {runs.map((r) => (
              <div className="run-row" key={r.id}>
                <div className="run-row-heading">
                  <span className="run-symbol">
                    <FlaskConical size={19} />
                  </span>
                  <div>
                    <h3>{r.name}</h3>
                    <p>
                      {when(r.created)} · {r.steps} optimizer steps
                    </p>
                  </div>
                  <span
                    className={`tag ${r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "running"}`}
                  >
                    {r.status === "completed"
                      ? "Completed"
                      : r.status === "failed"
                        ? "Failed"
                        : "In progress"}
                  </span>
                </div>
                {["running", "queued"].includes(r.status) ? (
                  <div className="run-progress">
                    <div>
                      <span>{r.phase}</span>
                      <strong>
                        {r.step} / {r.steps} steps
                      </strong>
                    </div>
                    <progress value={r.step} max={r.steps} />
                    {r.step === 0 && (
                      <small>
                        Model download and baseline evaluation can take a few
                        minutes.
                      </small>
                    )}
                  </div>
                ) : r.status === "failed" ? (
                  <div className="error-box">{r.error}</div>
                ) : (
                  <div className="run-result">
                    <span>
                      <CheckCircle2 size={15} />
                      {r.metrics?.eval_examples} held-out examples evaluated
                    </span>
                    <button
                      className="text-button"
                      onClick={() => onEvaluate(r.id)}
                    >
                      View evaluation
                      <ArrowRight size={14} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
      <dialog
        className="upload-dialog"
        ref={dialog}
        onCancel={() => setUploadOpen(false)}
        onClick={(e) => {
          if (e.target === e.currentTarget && !pending) setUploadOpen(false);
        }}
      >
        <div className="dialog-heading">
          <div>
            <h2>Upload a dataset</h2>
            <p>Private to {schoolNames[user.school_id || "uga"]}.</p>
          </div>
          <button
            className="icon-button"
            onClick={() => setUploadOpen(false)}
            aria-label="Close upload dialog"
          >
            <X size={20} />
          </button>
        </div>
        <form onSubmit={upload}>
          <label
            className="dropzone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
            }}
          >
            <span className="upload-icon">
              <Upload size={24} />
            </span>
            <strong>
              {file ? file.name : "Choose a file or drop it here"}
            </strong>
            <span>CSV or JSONL · Up to 2 MB</span>
            <input
              type="file"
              accept=".jsonl,.csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              aria-label="Dataset file"
            />
          </label>
          <div className="format-example">
            <span>Each row needs these two fields</span>
            <pre>
              {
                '{"instruction": "Explain gravity.",\n "response": "Gravity attracts objects with mass."}'
              }
            </pre>
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              required
            />
            <span>
              I have permission to use this dataset and have removed student
              identities and other sensitive information.
            </span>
          </label>
          {uploadError && (
            <div className="error-box" role="alert">
              {uploadError}
            </div>
          )}
          <div className="dialog-actions">
            <button
              type="button"
              className="button"
              onClick={() => setUploadOpen(false)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={!file || !consent || !!pending}
            >
              {pending === "upload" ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Upload size={16} />
              )}
              Validate & upload
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
