"""Synchronous, sample-weighted FedAvg over LoRA factors on one local worker.

Clients keep their training/evaluation examples inside LocalSchoolClient. The
coordinator receives adapter tensors, sample counts, and numeric scores only.
This is a single-process simulation, not remote data custody or secure aggregation.
"""

import gc
import hashlib
import json
import math
import random
import time
from pathlib import Path

from . import ml, store
from .data import split_dataset

METHOD = "fedavg_lora"
SEED = 42


class FederationDataError(ValueError):
    """Safe, static input-validation messages that contain no private examples."""


def instruction_key(row):
    normalized = " ".join(row["instruction"].casefold().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def ensure_disjoint_evaluation(clients):
    # Internal hashes detect exact normalized overlap, not semantic paraphrases.
    training = set().union(*(c.training_keys for c in clients))
    evaluation = set().union(*(c.validation_keys for c in clients))
    if training & evaluation:
        raise FederationDataError(
            "A question appears in one school's training data and another school's evaluation data. "
            "Remove overlapping questions across the participating datasets and create a new collaboration."
        )


def clone_state(state):
    # PEFT exposes tensor references. A CPU copy alone would still alias on CPU.
    return {name: value.detach().cpu().clone() for name, value in state.items()}


def adapter_digest(state):
    digest = hashlib.sha256()
    for name, value in sorted(state.items()):
        value = value.detach().cpu().contiguous()
        digest.update(json.dumps([name, list(value.shape), str(value.dtype)]).encode())
        digest.update(value.numpy().tobytes())
    return digest.hexdigest()


def average_adapters(updates):
    """Average LoRA A/B parameters using each client's training example count.

    This is parameter-space FedAvg, not exact averaging of the dense B @ A updates.
    Inputs are never mutated and results never alias a client's snapshot.
    """
    import torch

    if not updates:
        raise ValueError("At least one adapter update is required.")
    reference = updates[0][0]
    if not reference:
        raise ValueError("Adapter updates cannot be empty.")
    total = 0
    for state, count in updates:
        if type(count) is not int or count <= 0:
            raise ValueError("Client training counts must be positive integers.")
        if state.keys() != reference.keys():
            raise ValueError("Client adapter parameter keys do not match.")
        for name, value in state.items():
            expected = reference[name]
            if not isinstance(value, torch.Tensor) or not value.is_floating_point():
                raise ValueError("Adapter parameters must be floating-point tensors.")
            if value.shape != expected.shape or value.dtype != expected.dtype:
                raise ValueError("Client adapter shapes and dtypes must match.")
            if not torch.isfinite(value).all():
                raise ValueError("An adapter update contains non-finite values.")
        total += count
    result = {name: torch.zeros_like(value, device="cpu") for name, value in reference.items()}
    for state, count in updates:
        for name, value in state.items():
            result[name].add_(value.detach().cpu(), alpha=count / total)
    if any(not torch.isfinite(value).all() for value in result.values()):
        raise ValueError("Aggregation produced non-finite parameters.")
    return result


def pooled_scores(scores):
    """Pool answer-token NLL; perplexity is exp(pooled loss), not a mean."""
    if not scores or any(
        type(s["tokens"]) is not int or s["tokens"] <= 0
        or not math.isfinite(s["loss"]) or s["loss"] < 0
        for s in scores
    ):
        raise ValueError("Evaluation requires finite losses and positive token counts.")
    tokens = sum(s["tokens"] for s in scores)
    loss = sum(s["loss"] * s["tokens"] for s in scores) / tokens
    return {"loss": round(loss, 5), "perplexity": round(math.exp(min(loss, 20)), 3), "tokens": tokens}


def run_rounds(initial_state, clients, rounds, local_steps, report, checkpoint):
    """Coordinator independent of model loading, with an injectable client boundary."""
    if len(clients) < 2 or len({c.school_id for c in clients}) != len(clients):
        raise ValueError("Federation requires at least two distinct schools.")
    if not 1 <= rounds <= 5 or not 1 <= local_steps <= 20:
        raise ValueError("Use 1–5 rounds and 1–20 local steps per round.")
    if any(type(c.train_examples) is not int or c.train_examples <= 0 for c in clients):
        raise ValueError("Each school needs training examples.")
    global_state = clone_state(initial_state)
    report(phase="Evaluating the shared starting model", round=0)
    current_scores = [c.evaluate(clone_state(global_state)) for c in clients]
    baseline = pooled_scores(current_scores)
    history = []
    total_examples = sum(c.train_examples for c in clients)
    for round_number in range(1, rounds + 1):
        start_digest = adapter_digest(global_state)
        updates, entries = [], []
        for client, before in zip(clients, current_scores):
            report(phase=f"Round {round_number}: training {client.school_id}", round=round_number)
            # No client ever receives the preceding client's local result.
            update = clone_state(client.fit(clone_state(global_state), local_steps, round_number))
            local_score = client.evaluate(clone_state(update))
            updates.append((update, client.train_examples))
            entries.append({
                "school_id": client.school_id,
                "train_examples": client.train_examples,
                "eval_examples": client.eval_examples,
                "weight": client.train_examples / total_examples,
                "before": before,
                "local": local_score,
                "start_sha256": start_digest,
                "update_sha256": adapter_digest(update),
            })
        report(phase=f"Round {round_number}: aggregating adapters", round=round_number)
        candidate = average_adapters(updates)
        report(phase=f"Round {round_number}: evaluating the global adapter", round=round_number)
        next_scores = [c.evaluate(clone_state(candidate)) for c in clients]
        for entry, score in zip(entries, next_scores):
            entry["global"] = score
        record = {
            "round": round_number,
            "global": pooled_scores(next_scores),
            "clients": entries,
            "start_sha256": start_digest,
            "adapter_sha256": adapter_digest(candidate),
        }
        # Persist a round only after every client trained and evaluated successfully.
        checkpoint(round_number, clone_state(candidate), record)
        global_state, current_scores = candidate, next_scores
        history.append(record)
        report(history=list(history), round=round_number, phase=f"Round {round_number} complete")
    return global_state, history, baseline


def adapter_state(model):
    from peft import get_peft_model_state_dict
    return clone_state(get_peft_model_state_dict(model, adapter_name="default"))


def restore_adapter(model, state):
    from peft import set_peft_model_state_dict
    model.set_adapter("default")
    # Inference and local training share a cached model; restore gradient flags explicitly.
    for name, parameter in model.named_parameters():
        parameter.requires_grad_("lora_A" in name or "lora_B" in name)
    set_peft_model_state_dict(model, state, adapter_name="default")


class LocalSchoolClient:
    """A school worker boundary simulated on the same machine and model instance."""

    def __init__(self, participant, model, tokenizer, device):
        self.school_id = participant["school_id"]
        dataset = store.one(
            "SELECT rows FROM datasets WHERE id=? AND school_id=?",
            (participant["dataset_id"], self.school_id),
        )
        if not dataset:
            raise FederationDataError("An enrolled dataset is no longer available. Create a new collaboration with available datasets.")
        training, validation = split_dataset(json.loads(dataset["rows"]))
        self.train_examples, self.eval_examples = len(training), len(validation)
        self.training_keys = {instruction_key(row) for row in training}
        self.validation_keys = {instruction_key(row) for row in validation}
        try:
            self._training = [ml.encode(tokenizer, row, device) for row in training]
            self._validation = [ml.encode(tokenizer, row, device) for row in validation]
        except ValueError:
            raise FederationDataError(
                "A training example exceeds the 256-token budget. Shorten the instructions and answers, "
                "upload the corrected dataset, and create a new collaboration."
            ) from None
        self.model = model

    def evaluate(self, state):
        restore_adapter(self.model, state)
        return ml.score(self.model, self._validation)

    def fit(self, state, steps, round_number):
        import torch
        restore_adapter(self.model, state)
        school_seed = int(hashlib.sha256(self.school_id.encode()).hexdigest()[:8], 16)
        seed = SEED + round_number * 1000 + school_seed
        torch.manual_seed(seed)
        rng = random.Random(seed)
        optimizer = torch.optim.AdamW(
            [p for p in self.model.parameters() if p.requires_grad], lr=2e-4
        )
        order = []
        try:
            for _ in range(steps):
                self.model.train()
                optimizer.zero_grad(set_to_none=True)
                for _ in range(2):
                    if not order:
                        order = list(range(self.train_examples))
                        rng.shuffle(order)
                    batch = self._training[order.pop()]
                    loss = self.model(**batch).loss
                    if not torch.isfinite(loss):
                        raise ValueError("Local training produced a non-finite loss.")
                    (loss / 2).backward()
                torch.nn.utils.clip_grad_norm_(
                    [p for p in self.model.parameters() if p.requires_grad], 1.0
                )
                optimizer.step()
            return adapter_state(self.model)
        finally:
            optimizer.zero_grad(set_to_none=True)
            del optimizer


def train(federation, participants, output_path, report):
    import torch
    report(phase="Loading TinyLlama for federated training", round=0)
    started = time.monotonic()
    model, tokenizer, device = ml.load()
    original_cache = model.config.use_cache
    clients = []
    try:
        ml.reset_adapter(model, SEED)
        initial = adapter_state(model)
        model.config.use_cache = False
        clients = [LocalSchoolClient(p, model, tokenizer, device) for p in participants]
        ensure_disjoint_evaluation(clients)
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True, mode=0o700)

        def save_adapter(path, state):
            restore_adapter(model, state)
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            model.save_pretrained(path, safe_serialization=True)

        def checkpoint(number, state, record):
            path = output_path / f"round-{number:03d}"
            save_adapter(path, state)
            (path / "metrics.json").write_text(json.dumps(record, indent=2, allow_nan=False))

        final, history, baseline = run_rounds(
            initial, clients, federation["rounds"], federation["local_steps"], report, checkpoint
        )
        save_adapter(output_path / "global", final)
        return {
            "baseline": baseline,
            "tuned": history[-1]["global"],
            "train_examples": sum(c.train_examples for c in clients),
            "eval_examples": sum(c.eval_examples for c in clients),
            "device": device,
            "seconds": round(time.monotonic() - started, 1),
            "seed": SEED,
            "model": ml.MODEL_ID,
            "revision": ml.MODEL_REVISION,
            "method": METHOD,
        }
    finally:
        model.config.use_cache = original_cache
        model.zero_grad(set_to_none=True)
        clients.clear()
        gc.collect()
        if device == "mps":
            torch.mps.empty_cache()
