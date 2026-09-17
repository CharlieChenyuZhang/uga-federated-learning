# Federated LoRA training

The POC implements synchronous, sample-weighted FedAvg over TinyLlama's LoRA parameters. Schools explicitly enroll their own datasets. A coordinator trains all enrolled schools sequentially on one computer, aggregates their updates, and repeats. Training and aggregation are real; separate institutional servers are simulated.

## Method

1. Initialize one rank-8 LoRA adapter with seed 42 on the pinned TinyLlama 1.1B Chat base. Base weights remain frozen. All clients use identical adapter configuration.
2. Split each school's dataset once into training and held-out examples. Every round restores the same current global adapter before each school's local training.
3. Train locally using a fresh AdamW optimizer, learning rate `2e-4`, two examples per optimizer step, and gradient clipping at 1.0. The UI allows 1–5 rounds and 1–20 local steps per round. A short run may visit only part of a school's training split.
4. For school `k`, set `p_k = n_k / sum(n_j)`, where `n_k` is its full training-split example count, excluding held-out examples. Average every LoRA A and B tensor: `A_next = sum(p_k * A_k)` and `B_next = sum(p_k * B_k)`.
5. Evaluate the aggregate on every school's unchanged held-out split. Save a round only after every client and global evaluation succeeds. All schools begin the next round from that saved aggregate.

This applies [FedAvg's sample-weighted parameter averaging](https://proceedings.mlr.press/v54/mcmahan17a.html) to LoRA factors. **Factor averaging is not exact averaging of the dense `B @ A` updates:** multiplying the averaged factors introduces cross terms. It is a simple baseline with fixed rank, not FLoRA, FedProx, or a claim of full-weight FedAvg equivalence. [FLoRA](https://arxiv.org/abs/2409.05976) discusses this limitation and an alternative aggregation approach.

## Evaluation and artifacts

The report shows each school's training count, aggregation weight, pre-round loss, local-update loss, and global-model loss. Pooled loss is weighted by held-out answer-token counts, and perplexity is computed from pooled loss, capped at `exp(20)` for numerical stability. Metrics are measured, not simulated. Small synthetic splits cannot establish general quality or privacy.

Identical instructions are grouped within each school's split. Federation also rejects normalized exact instruction overlap between any participating training and evaluation split. This check does not detect semantic paraphrases. Cross-school duplicates within training or within evaluation are permitted, so pooled results can include repeated evaluation questions.

Round reports include adapter SHA-256 digests to trace common initialization and inheritance. They are diagnostics, not signed attestations. Checkpoints and the final inference adapter live under ignored `.local/federations/<id>/`. Reports contain numeric metrics and configuration, with no prompt/answer samples or dataset IDs. Training failure does not expose an incomplete global model; interrupted jobs are marked failed on restart. Resume is not implemented.

## Access and trust boundaries

- Contributors can discover collaboration metadata. Each school can enroll, replace, or withdraw only its own dataset while a collaboration is a draft.
- Only the coordinating school can start, with its own contribution and at least one other school. Membership and datasets are then fixed. Enrolled datasets cannot be deleted.
- Participants can query the completed model and view numeric reports. Enrollment explicitly allows the owner to later enable access for signed-in lab users.
- The owner must acknowledge sharing before enabling it. Any participant can revoke current guest access. This is not a permanent veto: the owner can subsequently enable sharing again under the enrollment consent.
- Private API operations remain school-scoped. The coordinator and all simulated clients nevertheless share one process, database, and machine. This is not institution-owned data custody or isolation from the server operator.
- No secure aggregation, differential privacy, poisoning resistance, remote transport, or formal privacy guarantee is implemented. Updates, numeric metrics, and generated outputs can reveal training information. Use synthetic or approved de-identified data only.

The numerical coordinator is in [backend/federated_ml.py](../backend/federated_ml.py); authorization and lifecycle handling are in [backend/federation.py](../backend/federation.py). Existing independent school runs remain available.

## Reproduce a real run

With `./scripts/dev.sh` running:

```bash
.venv/bin/python scripts/smoke-federated.py --rounds 2 --steps 2
```

This uploads new synthetic datasets, enrolls three schools with unequal sample counts, trains two rounds, verifies round inheritance and real global inference, tests guest sharing, then revokes guest access. It retains artifacts and the numeric report in ignored `.local/federated-verification.json`. Nothing is published remotely.
