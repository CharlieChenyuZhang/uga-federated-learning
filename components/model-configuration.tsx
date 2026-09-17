"use client";

import { useId } from "react";

export default function ModelConfiguration() {
  const helpId = useId();

  return (
    <div className="model-configuration" role="group" aria-label="Model setup">
      <div className="model-option-grid">
        <label className="field">
          Base model
          <select defaultValue="tinyllama" aria-describedby={helpId}>
            <option value="tinyllama">TinyLlama 1.1B Chat</option>
            <option value="llama-3.2" disabled>
              Llama 3.2 1B Instruct · Coming soon
            </option>
            <option value="qwen-2.5" disabled>
              Qwen2.5 0.5B Instruct · Coming soon
            </option>
          </select>
        </label>
        <label className="field">
          Fine-tuning method
          <select defaultValue="lora" aria-describedby={helpId}>
            <option value="lora">LoRA · rank 8</option>
            <option value="qlora" disabled>
              QLoRA · Coming soon
            </option>
            <option value="full" disabled>
              Full fine-tuning · Coming soon
            </option>
          </select>
        </label>
      </div>
      <p className="field-help" id={helpId}>
        TinyLlama + LoRA is available now, with a 256-token training context.
        Options marked Coming soon are not available yet.
      </p>
    </div>
  );
}
