# Campus: Collaborative AI Lab

A local app for campuses and research teams to fine-tune TinyLlama, evaluate results, and share model access. Includes three example institutions; workspace creation is not implemented yet.

**Stack:** Next.js + TypeScript, FastAPI + SQLite, and PyTorch + PEFT LoRA. No API key is required.

## Quick start

Requires Node.js 20.9+ and Python 3.10+ (3.12 recommended), or `uv` to provision Python.

```bash
./scripts/setup.sh
./scripts/dev.sh
```

Open [the local app](http://127.0.0.1:3000). For later sessions, run only `./scripts/dev.sh`. Ports 3000 and 8000 must be available.

First use downloads approximately 2.2 GB of model weights, then reuses the cache. Tested on Apple M2 Max with 64 GB RAM; CPU and CUDA paths are unverified.

## Try the demo

All demo accounts use the password **`local-lab`**.

| Role | Workspace | Capabilities |
| --- | --- | --- |
| Contributor | University of Georgia, Georgia Tech, or Emory University | Upload, train, evaluate, and manage sharing |
| User | Research Guest | Try the base model and shared adapters; view shared metrics |

1. Sign in as a Contributor and open **My institution**.
2. Use the synthetic sample dataset or upload a CSV/JSONL file.
3. Select **Quick experiment · 8 steps** and start fine-tuning.
4. Open **Evaluations** to compare measured base/tuned loss, perplexity, and responses.
5. Enable model access in **Sharing & privacy**, then sign in as User to try it in **Model playground**.

## Dataset format

Upload UTF-8 CSV or JSONL with `instruction` and `response` fields:

```json
{"instruction":"Explain gravity.","response":"Gravity attracts objects with mass."}
```

Limits: 6–500 unique instructions, 2 MB per file, 1,500 characters per field, and 256 tokens per formatted training example. Use synthetic or approved de-identified data; automated screening is incomplete.

## Model and privacy

Each run trains an independent LoRA adapter on [TinyLlama 1.1B Chat](https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0). One model job runs at a time. Data and adapters stay in ignored `.local/` storage.

This single-computer POC shares inference access and numeric metrics, not datasets or adapter downloads. Embedding export is disabled. Model outputs can still reveal training data. Distributed federated training, differential privacy, secure aggregation, and production authentication are not implemented. Keep the demo on localhost.

## Checks

```bash
npm run build
npm run format:check
.venv/bin/python -m pytest tests -q
```

See [verification results](docs/verification.md) for model measurements and browser checks, and [backend/ml.py](backend/ml.py) for the pinned model revision and training settings.
