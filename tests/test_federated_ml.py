"""Aggregation and multi-round invariants without downloading model weights."""

import math

import pytest

from backend.federated_ml import pooled_scores


def test_cross_school_evaluation_rejects_normalized_training_overlap():
    from types import SimpleNamespace
    from backend.federated_ml import ensure_disjoint_evaluation, instruction_key, FederationDataError
    key = instruction_key({"instruction": " Explain   GRAVITY. "})
    assert key == instruction_key({"instruction": "explain gravity."})
    first = SimpleNamespace(training_keys={key}, validation_keys={"unseen-a"})
    second = SimpleNamespace(training_keys={"other-training"}, validation_keys={key})
    with pytest.raises(FederationDataError, match="overlapping questions"):
        ensure_disjoint_evaluation([first, second])
    second.validation_keys = {"unseen-b"}
    ensure_disjoint_evaluation([first, second])


def test_pooled_loss_is_token_weighted_and_perplexity_is_recomputed():
    result = pooled_scores([
        {"loss": 1.0, "tokens": 10, "perplexity": math.exp(1)},
        {"loss": 3.0, "tokens": 30, "perplexity": math.exp(3)},
    ])
    assert result == {"loss": 2.5, "tokens": 40, "perplexity": round(math.exp(2.5), 3)}
    for invalid in ([], [{"loss": float("nan"), "tokens": 10}], [{"loss": 1, "tokens": 0}]):
        with pytest.raises(ValueError):
            pooled_scores(invalid)


def test_weighted_aggregation_is_exact_non_aliasing_and_validates_updates():
    torch = pytest.importorskip("torch")
    from backend.federated_ml import average_adapters
    left = {"A": torch.tensor([[1.0, 3.0]]), "B": torch.tensor([[2.0], [4.0]])}
    right = {"A": torch.tensor([[5.0, 7.0]]), "B": torch.tensor([[6.0], [8.0]])}
    result = average_adapters([(left, 1), (right, 3)])
    assert torch.equal(result["A"], torch.tensor([[4.0, 6.0]]))
    assert torch.equal(result["B"], torch.tensor([[5.0], [7.0]]))
    # Factor FedAvg is intentionally not advertised as exact dense-update averaging.
    assert not torch.equal(result["B"] @ result["A"], .25 * left["B"] @ left["A"] + .75 * right["B"] @ right["A"])
    result["A"].zero_()
    assert left["A"][0, 0] == 1 and right["A"][0, 0] == 5
    invalid_updates = [
        [], [({}, 1)], [(left, 0)], [(left, -1)], [(left, True)],
        [(left, 1), ({"A": right["A"]}, 1)],
        [(left, 1), ({"A": torch.ones(3), "B": right["B"]}, 1)],
        [(left, 1), ({"A": right["A"].double(), "B": right["B"]}, 1)],
        [({"A": torch.tensor([float("inf")])}, 1)],
        [({"A": torch.tensor([1])}, 1)],
    ]
    for invalid in invalid_updates:
        with pytest.raises(ValueError):
            average_adapters(invalid)


def test_every_client_receives_global_and_next_round_inherits_aggregate():
    torch = pytest.importorskip("torch")
    from backend.federated_ml import adapter_digest, run_rounds
    starts, checkpoints, reports = [], [], []

    class Client:
        eval_examples = 2
        def __init__(self, school, count, delta):
            self.school_id, self.train_examples, self.delta = school, count, delta
        def fit(self, state, steps, round_number):
            starts.append((self.school_id, round_number, state["A"].item()))
            # Deliberate mutation ensures the coordinator provided an independent copy.
            state["A"].add_(self.delta)
            return state
        def evaluate(self, state):
            return {"loss": 10 - state["A"].item(), "tokens": self.train_examples, "perplexity": 0}

    initial = {"A": torch.tensor([0.0])}
    result, history, baseline = run_rounds(
        initial, [Client("uga", 1, 1), Client("gatech", 3, 3)], 2, 2,
        lambda **report: reports.append(report),
        lambda r, state, record: checkpoints.append((r, state, record)),
    )
    assert starts == [("uga", 1, 0), ("gatech", 1, 0), ("uga", 2, 2.5), ("gatech", 2, 2.5)]
    assert initial["A"].item() == 0
    assert result["A"].item() == 5
    assert baseline["loss"] == 10
    assert [r["global"]["loss"] for r in history] == [7.5, 5]
    assert [c["weight"] for c in history[0]["clients"]] == [.25, .75]
    assert all(c["start_sha256"] == r["start_sha256"] for r in history for c in r["clients"])
    assert history[1]["start_sha256"] == history[0]["adapter_sha256"]
    assert history[-1]["adapter_sha256"] == adapter_digest(result)
    assert len(checkpoints) == 2
    assert checkpoints[0][1]["A"].item() == 2.5
    assert reports[-1]["history"] == history


def test_failed_client_does_not_commit_a_partial_round():
    torch = pytest.importorskip("torch")
    from backend.federated_ml import run_rounds
    committed = []
    class Client:
        train_examples = 2
        eval_examples = 2
        def __init__(self, school):
            self.school_id = school
        def evaluate(self, state):
            return {"loss": 1.0, "perplexity": math.e, "tokens": 2}
        def fit(self, state, steps, round_number):
            if self.school_id == "gatech":
                raise ValueError("School worker failed")
            return state
    with pytest.raises(ValueError, match="School worker failed"):
        run_rounds({"A": torch.tensor([0.0])}, [Client("uga"), Client("gatech")], 2, 1,
                   lambda **_: None, lambda *args: committed.append(args))
    assert committed == []


@pytest.mark.parametrize("failure", ["aggregate_evaluation", "second_round"])
def test_later_failures_preserve_only_fully_evaluated_checkpoints(failure):
    torch = pytest.importorskip("torch")
    from backend.federated_ml import run_rounds
    committed = []
    class Client:
        train_examples = 2
        eval_examples = 2
        def __init__(self, school, delta):
            self.school_id, self.delta = school, delta
        def fit(self, state, steps, number):
            if failure == "second_round" and number == 2 and self.school_id == "gatech":
                raise ValueError("School worker failed")
            state["A"].add_(self.delta)
            return state
        def evaluate(self, state):
            if failure == "aggregate_evaluation" and state["A"].item() == 2:
                raise ValueError("Evaluation failed")
            return {"loss": 10.0, "tokens": 2, "perplexity": 0}
    with pytest.raises(ValueError):
        run_rounds({"A": torch.tensor([0.0])}, [Client("uga", 1), Client("gatech", 3)], 2, 1,
                   lambda **_: None, lambda number, *_: committed.append(number))
    assert committed == ([] if failure == "aggregate_evaluation" else [1])


def test_real_lora_training_freezes_base_and_global_snapshot_can_be_reloaded(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    pytest.importorskip("peft")
    from transformers import LlamaConfig, LlamaForCausalLM
    from peft import LoraConfig, get_peft_model
    from safetensors.torch import load_file
    from backend import ml
    from backend.federated_ml import LocalSchoolClient, adapter_state, restore_adapter, average_adapters

    torch.manual_seed(42)
    model = get_peft_model(LlamaForCausalLM(LlamaConfig(
        vocab_size=32, hidden_size=16, intermediate_size=32, num_hidden_layers=1,
        num_attention_heads=2, num_key_value_heads=1, max_position_embeddings=64,
    )), LoraConfig(r=2, lora_alpha=4, lora_dropout=0.0, target_modules=["q_proj", "v_proj"], task_type="CAUSAL_LM"))
    ml.reset_adapter(model)
    frozen = {n: p.detach().clone() for n, p in model.named_parameters() if "lora_" not in n}
    initial = adapter_state(model)
    batch = {"input_ids": torch.tensor([[1, 3, 4, 2]]), "attention_mask": torch.ones(1, 4, dtype=torch.long), "labels": torch.tensor([[-100, -100, 4, 2]])}
    client = object.__new__(LocalSchoolClient)
    client.school_id, client.train_examples, client.eval_examples = "uga", 2, 1
    client._training, client._validation, client.model = [batch, batch], [batch], model
    one = client.fit(initial, 2, 1)
    assert any(not torch.equal(initial[n], one[n]) for n in initial)
    assert all(torch.equal(frozen[n], p) for n, p in model.named_parameters() if n in frozen)
    global_state = average_adapters([(initial, 1), (one, 3)])
    restore_adapter(model, global_state)
    expected_score = client.evaluate(global_state)
    model.save_pretrained(tmp_path, safe_serialization=True)
    reloaded = load_file(str(tmp_path / "adapter_model.safetensors"))
    assert all(torch.equal(global_state[n], reloaded[n]) for n in global_state)
    assert client.evaluate(reloaded) == expected_score
    assert all(torch.equal(frozen[n], p) for n, p in model.named_parameters() if n in frozen)
    # Ordinary training may run after federation and must still start from zero B.
    ml.reset_adapter(model)
    assert all(torch.count_nonzero(p) == 0 for n, p in model.named_parameters() if "lora_B" in n)
