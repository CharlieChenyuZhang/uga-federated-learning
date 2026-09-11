"use client";
import { useState } from "react";
import {
  ArrowUp,
  Clock3,
  Cpu,
  LoaderCircle,
  MessageSquare,
  Network,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { api, json, Run, schoolNames } from "./api";
type Exchange = {
  prompt: string;
  answer: string;
  model: string;
  seconds: number;
  device: string;
};
export default function Playground({
  models,
  busy,
  ready,
}: {
  models: Run[];
  busy: boolean;
  ready: boolean;
}) {
  const [model, setModel] = useState("base");
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const effectiveModel =
    model === "base" || models.some((m) => m.id === model) ? model : "base";
  const selected =
    effectiveModel === "base"
      ? "TinyLlama base"
      : models.find((m) => m.id === effectiveModel)?.name ||
        "Unavailable model";
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setPending(true);
    setError("");
    const question = prompt;
    try {
      const result = await api<{
        answer: string;
        seconds: number;
        device: string;
      }>("/chat", json({ prompt: question, model_id: effectiveModel }));
      setExchanges((previous) => [
        ...previous,
        { ...result, prompt: question, model: selected },
      ]);
      setPrompt("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">TRY THE LEARNING</div>
          <h1>A small model, in conversation.</h1>
          <p>
            Explore the foundation model or an available school adapter with a
            single-turn question.
          </p>
        </div>
        <button
          className="button"
          onClick={() => {
            setExchanges([]);
            setError("");
          }}
          disabled={pending || !exchanges.length}
        >
          <RotateCcw size={16} />
          Clear session
        </button>
      </div>
      <div className="playground-layout">
        <section className="panel chat-panel">
          <div className="chat-toolbar">
            <div className="chat-model-icon">
              <Network size={19} />
            </div>
            <label>
              Active model
              <select
                aria-label="Active model"
                value={effectiveModel}
                onChange={(e) => setModel(e.target.value)}
                disabled={pending}
              >
                <option value="base">TinyLlama base · 1.1B</option>
                {models.map((m) => (
                  <option value={m.id} key={m.id}>
                    {m.name} · {schoolNames[m.school_id]}
                  </option>
                ))}
              </select>
            </label>
            <span className="tag">LOCAL</span>
          </div>
          <div className="chat-body" aria-live="polite">
            {!exchanges.length && !pending ? (
              <div className="chat-empty">
                <div className="chat-empty-logo">
                  <MessageSquare size={29} />
                </div>
                <h2>Put an idea to the test.</h2>
                <p>
                  Try a classroom question, then switch models to explore how
                  their responses differ.
                </p>
                <div className="prompt-suggestions">
                  {[
                    "How would you help a student support a scientific claim with evidence?",
                    "Explain why correlation does not prove causation.",
                    "Suggest a simple classroom experiment about friction.",
                  ].map((p) => (
                    <button key={p} onClick={() => setPrompt(p)}>
                      <span>{p}</span>
                      <ArrowUp size={15} />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              exchanges.map((x, i) => (
                <div className="exchange" key={i}>
                  <div className="user-message">
                    <span>YOU</span>
                    <p>{x.prompt}</p>
                  </div>
                  <div className="model-message">
                    <span className="model-message-label">
                      <Network size={16} />
                      {x.model}
                    </span>
                    <p>{x.answer || "(The model returned no text.)"}</p>
                    <small>
                      <Clock3 size={12} />
                      {x.seconds.toFixed(1)}s · {x.device.toUpperCase()} · Local
                      inference
                    </small>
                  </div>
                </div>
              ))
            )}
            {pending && (
              <div className="thinking">
                <LoaderCircle className="spin" size={18} />
                <span>
                  Generating on this computer…
                  <small>
                    The first request may download the model. This can take a
                    few minutes.
                  </small>
                </span>
              </div>
            )}
          </div>
          {error && (
            <div className="error-box" role="alert">
              {error}
            </div>
          )}
          <form className="chat-compose" onSubmit={submit}>
            <label className="sr-only" htmlFor="prompt">
              Your question
            </label>
            <textarea
              id="prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="Ask a question about teaching, science, or evidence…"
              disabled={pending}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="compose-footer">
              <span>Each question is independent · {prompt.length}/2,000</span>
              <button
                className="button primary"
                disabled={!prompt.trim() || pending || busy || !ready}
                aria-label="Send question"
              >
                {pending ? (
                  <LoaderCircle className="spin" size={18} />
                ) : (
                  <ArrowUp size={18} />
                )}
              </button>
            </div>
          </form>
          <div className="chat-disclaimer">
            Model output can be incorrect. Review responses before using them in
            education.
          </div>
        </section>
        <aside className="playground-aside">
          <section className="panel">
            <div className="section-title">
              <h3>About this session</h3>
              <Cpu size={18} />
            </div>
            <div className="session-stat">
              <span>Foundation</span>
              <strong>TinyLlama 1.1B</strong>
            </div>
            <div className="session-stat">
              <span>Available adapters</span>
              <strong>{models.length}</strong>
            </div>
            <div className="session-stat">
              <span>Response length</span>
              <strong>Up to 96 tokens</strong>
            </div>
            <div className="session-stat">
              <span>Generation</span>
              <strong>Greedy decoding</strong>
            </div>
            <div className="subtle-note">
              <p>
                Prompts are processed by the local model. This website does not
                save playground conversations to its database.
              </p>
            </div>
          </section>
          <div className="playground-tip">
            <Sparkles size={20} />
            <h3>Look for the difference.</h3>
            <p>
              Try the same question with the base model and a tuned adapter.
              Look for useful feedback, evidence-based reasoning, and
              unsupported claims.
            </p>
          </div>
          {busy && !pending && (
            <div className="info-banner">
              <p>
                The local model is currently busy. Send your question when the
                current job finishes.
              </p>
            </div>
          )}
          {!ready && (
            <div className="error-box">
              Install the Python model dependencies with{" "}
              <code>./scripts/setup.sh</code> to enable inference.
            </div>
          )}
        </aside>
      </div>
    </>
  );
}
