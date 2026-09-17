"use client";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  Download,
  Eye,
  FlaskConical,
  GitMerge,
  LoaderCircle,
  LockKeyhole,
  Network,
  Play,
  Plus,
  Users,
} from "lucide-react";
import {
  api,
  Dataset,
  Federation,
  json,
  Overview,
  schoolNames,
  User,
  when,
} from "./api";

export default function FederatedLearning({
  user,
  federations,
  datasets,
  runtime,
  refresh,
  notify,
  onTryModel,
  onDatasets,
}: {
  user: User;
  federations: Federation[];
  datasets: Dataset[];
  runtime: Overview["runtime"];
  refresh: () => Promise<void>;
  notify: (message: string) => void;
  onTryModel: (id: string) => void;
  onDatasets: () => void;
}) {
  const [selectedId, setSelectedId] = useState("");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [rounds, setRounds] = useState(2);
  const [steps, setSteps] = useState(2);
  const [datasetIds, setDatasetIds] = useState<Record<string, string>>({});
  const [consent, setConsent] = useState<Record<string, boolean>>({});
  const [shareConsent, setShareConsent] = useState<Record<string, boolean>>({});
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const federation =
    federations.find((item) => item.id === selectedId) || federations[0];
  const ownParticipant = federation?.participants.find(
    (participant) => participant.school_id === user.school_id,
  );
  const selectedDataset = federation
    ? datasetIds[federation.id] ||
      ownParticipant?.dataset_id ||
      datasets[0]?.id ||
      ""
    : "";
  const metrics = federation?.metrics;
  const isActive =
    federation && ["queued", "running"].includes(federation.status);

  async function act(
    key: string,
    action: () => Promise<unknown>,
    message: string,
  ) {
    if (pending) return;
    setPending(key);
    setError("");
    try {
      await action();
      await refresh();
      if (mounted.current) notify(message);
    } catch (failure) {
      if (mounted.current) setError((failure as Error).message);
    } finally {
      if (mounted.current) setPending("");
    }
  }
  async function create(event: React.FormEvent) {
    event.preventDefault();
    await act(
      "create",
      async () => {
        const result = await api<Federation>(
          "/federations",
          json({ name: name.trim(), rounds, local_steps: steps }),
        );
        if (mounted.current) {
          setSelectedId(result.id);
          setCreating(false);
          setName("");
        }
      },
      "Collaboration created. Join with your dataset, then invite another school to join.",
    );
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">LEARN TOGETHER, ROUND BY ROUND</div>
          <h1>Build a shared model.</h1>
          <p>
            Schools train on their own examples and combine adapter updates into
            one global model.
          </p>
        </div>
        {user.role === "contributor" && (
          <button
            className="button primary"
            onClick={() => setCreating(!creating)}
            aria-expanded={creating}
            aria-controls="federation-create"
          >
            <Plus size={17} />
            {creating ? "Close form" : "New collaboration"}
          </button>
        )}
      </div>
      <section
        className="federation-method"
        aria-label="Federated learning method"
      >
        <div className="federation-method-title">
          <GitMerge size={21} />
          <div>
            <strong>FedAvg · LoRA</strong>
            <span>Real training. One local computer.</span>
          </div>
        </div>
        <ol className="federation-cycle">
          <li>
            <span>1</span>Same global adapter
          </li>
          <li>
            <span>2</span>Train at each school
          </li>
          <li>
            <span>3</span>Weighted average
          </li>
          <li>
            <span>4</span>Evaluate & repeat
          </li>
        </ol>
        <p>
          Each round averages LoRA factors by each school&apos;s number of
          training examples. All schools start the next round from that same
          result. This simulates separate schools on one server; it does not
          provide differential privacy or secure aggregation.
        </p>
      </section>

      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}
      {creating && user.role === "contributor" && (
        <section className="panel" id="federation-create">
          <div className="section-title">
            <div>
              <h2>Start a collaboration</h2>
              <p>
                Create a draft, then let each school choose its own dataset.
              </p>
            </div>
            <Users size={20} />
          </div>
          <form onSubmit={create}>
            <div className="federation-create-fields">
              <label className="field">
                Collaboration name
                <input
                  required
                  maxLength={80}
                  value={name}
                  placeholder="Shared science teaching"
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label className="field">
                Global rounds
                <input
                  type="number"
                  min={1}
                  max={5}
                  required
                  value={rounds}
                  onChange={(event) => setRounds(Number(event.target.value))}
                />
              </label>
              <label className="field">
                Local steps per round
                <input
                  type="number"
                  min={1}
                  max={20}
                  required
                  value={steps}
                  onChange={(event) => setSteps(Number(event.target.value))}
                />
              </label>
            </div>
            <div className="federation-actions">
              <p className="text-muted small">
                Start with 2 rounds and 2 steps for a quick local demo.
              </p>
              <button
                className="button primary"
                disabled={!!pending || !name.trim()}
              >
                {pending === "create" ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Plus size={16} />
                )}
                Create draft
              </button>
            </div>
          </form>
        </section>
      )}

      {!federation ? (
        <section className="panel empty-state">
          <div className="empty-icon">
            <Network size={30} />
          </div>
          <h2>
            {user.role === "contributor"
              ? "Your first shared experiment"
              : "No shared federated models yet"}
          </h2>
          <p>
            {user.role === "contributor"
              ? "Create a collaboration, join with your dataset, then sign in as another school to join. At least two schools must participate."
              : "A completed collaboration will appear here when its owner enables shared access."}
          </p>
          {user.role === "contributor" && !creating && (
            <button
              className="button primary"
              onClick={() => setCreating(true)}
            >
              <Plus size={16} /> New collaboration
            </button>
          )}
        </section>
      ) : (
        <>
          <div className="evaluation-picker">
            <label className="field">
              Collaboration
              <select
                value={federation.id}
                onChange={(event) => {
                  setSelectedId(event.target.value);
                  setError("");
                }}
              >
                {federations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {item.status}
                    {item.is_owner ? " · You own this" : ""}
                  </option>
                ))}
              </select>
            </label>
            <span
              className={`tag ${federation.status === "completed" ? "success" : ""}`}
            >
              {federation.status}
            </span>
          </div>
          <section className="panel federation-workspace">
            <div className="section-title">
              <div>
                <h2>{federation.name}</h2>
                <p>
                  Coordinated by{" "}
                  {schoolNames[federation.owner_school_id] ||
                    federation.owner_school_id}
                  {federation.is_owner ? " (your school)" : ""} · Created{" "}
                  {when(federation.created)}
                </p>
              </div>
              <span className="badge">
                {federation.rounds}{" "}
                {federation.rounds === 1 ? "ROUND" : "ROUNDS"} ·{" "}
                {federation.local_steps} LOCAL{" "}
                {federation.local_steps === 1 ? "STEP" : "STEPS"}
              </span>
            </div>
            <div
              className="federation-members"
              aria-label="Participating schools"
            >
              {federation.participants.map((participant) => (
                <div className="federation-member" key={participant.school_id}>
                  <span className="federation-member-icon">
                    <Check size={16} />
                  </span>
                  <div>
                    <strong>
                      {schoolNames[participant.school_id] ||
                        participant.school_id}
                    </strong>
                    <small>
                      {participant.school_id === user.school_id
                        ? "Your school"
                        : "Joined with its own dataset"}
                    </small>
                  </div>
                </div>
              ))}
              {!federation.participants.length && (
                <p className="text-muted">No schools have joined yet.</p>
              )}
            </div>

            {federation.status === "draft" && user.role === "contributor" && (
              <div className="federation-join" key={federation.id}>
                <h3>
                  {ownParticipant ? "Your contribution" : "Join as your school"}
                </h3>
                {datasets.length ? (
                  <>
                    <label className="field">
                      Your school&apos;s dataset
                      <select
                        value={selectedDataset}
                        disabled={!!pending}
                        onChange={(event) => {
                          setDatasetIds({
                            ...datasetIds,
                            [federation.id]: event.target.value,
                          });
                          setConsent({ ...consent, [federation.id]: false });
                        }}
                      >
                        {datasets.map((dataset) => (
                          <option key={dataset.id} value={dataset.id}>
                            {dataset.name} · {dataset.row_count}{" "}
                            {dataset.row_count === 1 ? "example" : "examples"}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={!!consent[federation.id]}
                        onChange={(event) =>
                          setConsent({
                            ...consent,
                            [federation.id]: event.target.checked,
                          })
                        }
                      />
                      <span>
                        I approve using this dataset in local simulated
                        federated rounds. Other participants can access the
                        global model and numeric metrics. The owner may share
                        global inference and numeric metrics with signed-in
                        users. Model updates and outputs can reveal training
                        data.
                      </span>
                    </label>
                    <div className="federation-actions">
                      <span className="text-muted small">
                        <LockKeyhole size={13} /> Dataset contents remain scoped
                        to your school in the API.
                      </span>
                      <div className="federation-button-group">
                        {ownParticipant && (
                          <button
                            className="button"
                            disabled={!!pending}
                            onClick={() =>
                              act(
                                "withdraw",
                                () =>
                                  api(
                                    `/federations/${federation.id}/participants`,
                                    { method: "DELETE" },
                                  ),
                                "Your school left this draft collaboration.",
                              )
                            }
                          >
                            Withdraw from draft
                          </button>
                        )}
                        <button
                          className="button primary"
                          disabled={
                            !!pending ||
                            !selectedDataset ||
                            !consent[federation.id]
                          }
                          onClick={() =>
                            act(
                              "join",
                              () =>
                                api(
                                  `/federations/${federation.id}/participants`,
                                  json({
                                    dataset_id: selectedDataset,
                                    acknowledge_risk: true,
                                  }),
                                ),
                              "Your school's contribution is ready.",
                            )
                          }
                        >
                          {pending === "join" ? (
                            <LoaderCircle size={16} className="spin" />
                          ) : (
                            <Plus size={16} />
                          )}
                          {ownParticipant
                            ? "Update contribution"
                            : "Join collaboration"}
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="federation-actions">
                    <p>Add a dataset to your institution before joining.</p>
                    <button className="button" onClick={onDatasets}>
                      Open my datasets <ArrowRight size={16} />
                    </button>
                  </div>
                )}
              </div>
            )}
            {federation.status === "draft" && (
              <div className="federation-start">
                <div>
                  <strong>
                    {federation.participants.length}{" "}
                    {federation.participants.length === 1
                      ? "school"
                      : "schools"}{" "}
                    ready
                  </strong>
                  <p>
                    {federation.is_owner
                      ? "Join with your own dataset and have at least one other school join, then start the rounds."
                      : "The coordinating school starts training when at least two schools have joined."}
                    {federation.is_owner &&
                      " For this demo, sign out and switch schools to add another participant."}
                  </p>
                </div>
                {federation.is_owner && (
                  <button
                    className="button primary"
                    disabled={
                      !!pending ||
                      !federation.is_member ||
                      federation.participants.length < 2 ||
                      runtime.busy ||
                      !runtime.ml_available
                    }
                    onClick={() =>
                      act(
                        "start",
                        () =>
                          api(`/federations/${federation.id}/start`, json({})),
                        "Federated rounds started on this computer.",
                      )
                    }
                  >
                    {pending === "start" ? (
                      <LoaderCircle className="spin" size={16} />
                    ) : (
                      <Play size={16} />
                    )}
                    Start rounds
                  </button>
                )}
              </div>
            )}
            {isActive && (
              <div className="federation-progress" role="status">
                <LoaderCircle className="spin" size={20} />
                <div>
                  <strong>
                    Round {Math.max(1, federation.round)} of {federation.rounds}
                  </strong>
                  <p>{federation.phase || "Preparing local training"}</p>
                  <small>
                    This view updates automatically. Schools train sequentially
                    on this computer.
                  </small>
                </div>
              </div>
            )}
            {federation.status === "failed" && (
              <div className="error-box" role="alert">
                {federation.error ||
                  "This collaboration could not finish. Ask a participant to review the error."}
                <p>
                  Create a new collaboration to retry after resolving the issue.
                </p>
              </div>
            )}
            {federation.status === "completed" &&
              (federation.is_member || !!federation.shared) && (
                <div className="federation-actions">
                  <span className="tag success">
                    <Check size={13} /> Global adapter ready
                  </span>
                  <div className="federation-button-group">
                    <a
                      className="button"
                      href={`/api/federations/${federation.id}/evaluation`}
                    >
                      <Download size={16} /> Export report
                    </a>
                    <button
                      className="button primary"
                      onClick={() => onTryModel(federation.id)}
                    >
                      <ArrowRight size={16} /> Try global model
                    </button>
                  </div>
                </div>
              )}
            {federation.is_owner &&
              federation.status === "draft" &&
              (runtime.busy || !runtime.ml_available) && (
                <p className="federation-runtime-note">
                  {runtime.busy
                    ? "The local model is busy. Start this collaboration when the current job finishes."
                    : "Install the Python model dependencies to enable training."}
                </p>
              )}
          </section>

          {metrics && (
            <>
              <div className="metric-grid federation-metrics">
                <div className="metric">
                  <span>Base model loss</span>
                  <strong>{metrics.baseline.loss.toFixed(3)}</strong>
                  <small>Before collaborative training</small>
                </div>
                <div className="metric">
                  <span>Global model loss</span>
                  <strong>{metrics.tuned.loss.toFixed(3)}</strong>
                  <small>
                    After {federation.rounds}{" "}
                    {federation.rounds === 1 ? "round" : "rounds"} · lower is
                    better
                  </small>
                </div>
                <div className="metric">
                  <span>Perplexity</span>
                  <strong>{metrics.tuned.perplexity.toFixed(2)}</strong>
                  <small>
                    Base model: {metrics.baseline.perplexity.toFixed(2)}
                  </small>
                </div>
                <div className="metric">
                  <span>Held-out examples</span>
                  <strong>{metrics.eval_examples}</strong>
                  <small>
                    {metrics.train_examples} separate training{" "}
                    {metrics.train_examples === 1 ? "example" : "examples"}
                  </small>
                </div>
              </div>
              <p className="federation-metric-note">
                Measured on each school&apos;s held-out split. Loss is weighted
                by scored answer tokens; perplexity is derived from that loss.
                Small datasets do not establish general model quality.
              </p>
            </>
          )}
          {!!federation.history?.length && (
            <section className="panel">
              <div className="section-title">
                <div>
                  <h2>Round-by-round evidence</h2>
                  <p>
                    See how each local update contributes to the shared adapter.
                  </p>
                </div>
                <FlaskConical size={20} />
              </div>
              <div className="federation-rounds">
                {federation.history.map((round) => (
                  <details className="federation-round" key={round.round}>
                    <summary>
                      <span>
                        <strong>Round {round.round}</strong> ·{" "}
                        {round.clients.length}{" "}
                        {round.clients.length === 1 ? "school" : "schools"}
                      </span>
                      <span>
                        Global loss{" "}
                        <strong>{round.global.loss.toFixed(3)}</strong>
                      </span>
                    </summary>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>School</th>
                            <th>Training examples</th>
                            <th>FedAvg weight</th>
                            <th>Before local training</th>
                            <th>After local training</th>
                            <th>After aggregation</th>
                          </tr>
                        </thead>
                        <tbody>
                          {round.clients.map((client) => (
                            <tr key={client.school_id}>
                              <td>
                                {schoolNames[client.school_id] ||
                                  client.school_id}
                              </td>
                              <td>{client.train_examples}</td>
                              <td>{(client.weight * 100).toFixed(1)}%</td>
                              <td>{client.before.loss.toFixed(3)}</td>
                              <td>{client.local.loss.toFixed(3)}</td>
                              <td>{client.global.loss.toFixed(3)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p>
                      All loss values use that school&apos;s same held-out
                      split. FedAvg weights use training-example counts.
                      Aggregation can improve or worsen a school&apos;s result.
                    </p>
                  </details>
                ))}
              </div>
            </section>
          )}
          {federation.status === "completed" && federation.is_member && (
            <section className="panel">
              <div className="section-title">
                <div>
                  <h2>Global model access</h2>
                  <p>
                    {federation.shared
                      ? "Signed-in lab users can query this model and view numeric metrics."
                      : "Only participating schools can query this model and view numeric metrics."}
                  </p>
                </div>
                <Eye size={20} />
              </div>
              {federation.is_owner && !federation.shared && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={!!shareConsent[federation.id]}
                    onChange={(event) =>
                      setShareConsent({
                        ...shareConsent,
                        [federation.id]: event.target.checked,
                      })
                    }
                  />
                  <span>
                    I have reviewed the global model and approve sharing
                    inference and numeric metrics with signed-in lab users.
                    Model outputs may reveal training information. Sharing
                    provides no formal privacy guarantee.
                  </span>
                </label>
              )}
              <div className="federation-actions">
                <span className="text-muted small">
                  The owner can enable sharing. Any participating school can
                  revoke it.
                </span>
                {(federation.is_owner || !!federation.shared) && (
                  <button
                    className={`button ${federation.shared ? "" : "primary"}`}
                    disabled={
                      !!pending ||
                      (!federation.shared && !shareConsent[federation.id])
                    }
                    onClick={() =>
                      act(
                        "sharing",
                        () =>
                          api(
                            `/federations/${federation.id}/sharing`,
                            json(
                              {
                                shared: !federation.shared,
                                acknowledge_risk: !!shareConsent[federation.id],
                              },
                              "PATCH",
                            ),
                          ),
                        federation.shared
                          ? "Global model access returned to participating schools."
                          : "Global model is now available to signed-in lab users.",
                      )
                    }
                  >
                    {pending === "sharing"
                      ? "Updating…"
                      : federation.shared
                        ? "Revoke shared access"
                        : "Enable shared access"}
                  </button>
                )}
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}
