"""Real TinyLlama LoRA training and inference, serialized by the API's model lock."""

import gc
import importlib.util
import math
import os
import time

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
# Pinned upstream revision makes base-model comparisons reproducible.
MODEL_REVISION = "fe8a4ea1ffedaf415f4da2f062534de366a451e6"
_MODEL = None
_TOKENIZER = None
_DEVICE = None
MAX_LENGTH = 256


def available():
    return all(
        importlib.util.find_spec(name) is not None
        for name in ["torch", "transformers", "peft"]
    )


def load():
    global _MODEL, _TOKENIZER, _DEVICE
    if _MODEL is not None:
        return _MODEL, _TOKENIZER, _DEVICE
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model

    _DEVICE = (
        "mps"
        if torch.backends.mps.is_available()
        else "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    tokenizer.pad_token = tokenizer.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        dtype=torch.float32,
        attn_implementation="eager",
        use_safetensors=True,
    )
    model = get_peft_model(
        base,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["q_proj", "v_proj"],
            task_type="CAUSAL_LM",
        ),
    )
    model.to(_DEVICE)
    _MODEL, _TOKENIZER = model, tokenizer
    return model, tokenizer, _DEVICE


def encode(tokenizer, row, device):
    import torch

    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": row["instruction"]}],
        tokenize=False,
        add_generation_prompt=True,
    )
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    answer_ids = tokenizer(
        row["response"] + tokenizer.eos_token, add_special_tokens=False
    )["input_ids"]
    if len(prompt_ids) + len(answer_ids) > MAX_LENGTH:
        raise ValueError(
            "An example exceeds the 256-token context budget. Shorten its instruction or response and upload again; this POC does not silently truncate evaluation data."
        )
    ids = prompt_ids + answer_ids
    labels = [-100] * len(prompt_ids) + answer_ids
    padding = MAX_LENGTH - len(ids)
    return {
        "input_ids": torch.tensor(
            [ids + [tokenizer.pad_token_id] * padding], device=device
        ),
        "attention_mask": torch.tensor([[1] * len(ids) + [0] * padding], device=device),
        "labels": torch.tensor([labels + [-100] * padding], device=device),
    }


def score(model, encoded):
    import torch

    model.eval()
    weighted_loss, tokens = 0.0, 0
    with torch.no_grad():
        for batch in encoded:
            n = int((batch["labels"][:, 1:] != -100).sum())
            loss = float(model(**batch).loss)
            if not math.isfinite(loss):
                raise ValueError(
                    "Non-finite evaluation loss. Retry with shorter examples."
                )
            weighted_loss += loss * n
            tokens += n
    loss = weighted_loss / tokens
    return {
        "loss": round(loss, 5),
        "perplexity": round(math.exp(min(loss, 20)), 3),
        "tokens": tokens,
    }


def generate(model, tokenizer, device, prompt, max_new_tokens=96):
    import torch

    text = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(text, return_tensors="pt", add_special_tokens=False).to(device)
    if inputs["input_ids"].shape[1] > 512:
        raise ValueError("Please shorten your prompt to fewer than 512 tokens.")
    model.eval()
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            use_cache=True,
            pad_token_id=tokenizer.pad_token_id,
        )
    return tokenizer.decode(
        output[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True
    ).strip()


def train(run, rows, output_path, report):
    import torch
    from .data import split_dataset

    report(phase="Loading TinyLlama (first run downloads 2.2 GB)")
    model, tokenizer, device = load()
    # Start each school run from an identical adapter initialization, never the prior school's update.
    torch.manual_seed(42)
    for name, parameter in model.named_parameters():
        if "lora_A" in name:
            torch.nn.init.kaiming_uniform_(parameter, a=math.sqrt(5))
        elif "lora_B" in name:
            torch.nn.init.zeros_(parameter)
    model.set_adapter("default")
    training, validation = split_dataset(rows)
    encoded_train = [encode(tokenizer, row, device) for row in training]
    encoded_eval = [encode(tokenizer, row, device) for row in validation]
    report(phase="Evaluating the base model")
    with model.disable_adapter():
        baseline = score(model, encoded_eval)
        base_answer = generate(model, tokenizer, device, validation[0]["instruction"])
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=2e-4
    )
    history = []
    started = time.monotonic()
    model.config.use_cache = False
    try:
        for step in range(run["steps"]):
            model.train()
            optimizer.zero_grad()
            loss_sum = 0.0
            for micro in range(2):
                batch = encoded_train[(step * 2 + micro) % len(encoded_train)]
                loss = model(**batch).loss
                if not torch.isfinite(loss):
                    raise ValueError(
                        "Training produced non-finite loss. No adapter was published."
                    )
                (loss / 2).backward()
                loss_sum += float(loss.detach()) / 2
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            history.append({"step": step + 1, "loss": round(loss_sum, 5)})
            report(phase="Training the school adapter", step=step + 1, history=history)
        report(phase="Evaluating the tuned model")
        tuned = score(model, encoded_eval)
        answer = generate(model, tokenizer, device, validation[0]["instruction"])
        output_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        model.save_pretrained(output_path, safe_serialization=True)
        return {
            "baseline": baseline,
            "tuned": tuned,
            "train_examples": len(training),
            "eval_examples": len(validation),
            "device": device,
            "seconds": round(time.monotonic() - started, 1),
            "seed": 42,
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "samples": [
                {
                    "instruction": validation[0]["instruction"],
                    "expected": validation[0]["response"],
                    "baseline": base_answer,
                    "tuned": answer,
                }
            ],
            "privacy": "Not certified. PII screening only; no differential privacy or secure aggregation.",
        }
    finally:
        model.config.use_cache = True
        optimizer.zero_grad(set_to_none=True)
        del optimizer, encoded_train, encoded_eval
        gc.collect()
        if device == "mps":
            torch.mps.empty_cache()


def infer(prompt, adapter_path=None):
    model, tokenizer, device = load()
    start = time.monotonic()
    if adapter_path:
        from safetensors.torch import load_file
        from peft import set_peft_model_state_dict

        weights = load_file(str(adapter_path / "adapter_model.safetensors"))
        set_peft_model_state_dict(model, weights, adapter_name="default")
        model.set_adapter("default")
        answer = generate(model, tokenizer, device, prompt)
    else:
        with model.disable_adapter():
            answer = generate(model, tokenizer, device, prompt)
    return {
        "answer": answer,
        "seconds": round(time.monotonic() - start, 2),
        "device": device,
    }
