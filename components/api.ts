export type User = {
  id: string;
  name: string;
  role: "contributor" | "user";
  school_id: string | null;
};
export type School = {
  id: string;
  name: string;
  short: string;
  city: string;
  color: string;
  focus: string;
  shared_models: number;
};
export type Dataset = {
  id: string;
  name: string;
  row_count: number;
  created: number;
  synthetic: number;
};
export type Scores = { loss: number; perplexity: number; tokens: number };
export type Metrics = {
  baseline: Scores;
  tuned: Scores;
  train_examples: number;
  eval_examples: number;
  device: string;
  seconds: number;
  seed: number;
  model: string;
  revision: string;
  samples?: {
    instruction: string;
    expected: string;
    baseline: string;
    tuned: string;
  }[];
};
export type Run = {
  id: string;
  school_id: string;
  name: string;
  status: string;
  steps: number;
  step: number;
  phase: string;
  shared: number;
  created: number;
  finished: number | null;
  dataset_id?: string;
  error?: string;
  history?: { step: number; loss: number }[];
  metrics?: Metrics | null;
};
export type Overview = {
  schools: School[];
  runtime: {
    ok: boolean;
    ml_available: boolean;
    busy: boolean;
    model: string;
    mode: string;
  };
};
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    cache: "no-store",
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((x: { msg: string }) => x.msg).join("; ")
          : "Something went wrong. Please retry.",
    );
  }
  return data;
}
export const json = (data: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});
export const when = (seconds: number) =>
  new Date(seconds * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const schoolNames: Record<string, string> = {
  uga: "University of Georgia",
  gatech: "Georgia Tech",
  emory: "Emory University",
};
