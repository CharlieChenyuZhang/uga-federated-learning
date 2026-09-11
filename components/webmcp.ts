"use client";
import { useEffect } from "react";
import { api, Run } from "./api";
interface ModelContext {
  registerTool(
    tool: {
      name: string;
      description: string;
      inputSchema: object;
      annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
      execute: (input: unknown) => Promise<unknown>;
    },
    options: { signal: AbortSignal },
  ): void | Promise<void>;
}
/** Optional, read-only mirror of the model picker. Authentication stays in the API. */
export function useModelTools(signedIn: boolean) {
  useEffect(() => {
    if (!signedIn) return;
    const context = (document as Document & { modelContext?: ModelContext })
      .modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      void Promise.resolve(
        context.registerTool(
          {
            name: "list_available_campus_models",
            description:
              "List the base model and school adapters available to the signed-in lab account. Does not train, share, or modify anything.",
            inputSchema: {
              type: "object",
              properties: {},
              additionalProperties: false,
            },
            annotations: { readOnlyHint: true, untrustedContentHint: true },
            execute: async (input) => {
              if (
                !input ||
                typeof input !== "object" ||
                Array.isArray(input) ||
                Object.keys(input).length
              )
                throw new Error("Expected an empty object.");
              const models = await api<Run[]>("/models");
              return [
                { id: "base", name: "TinyLlama base" },
                ...models.map((m) => ({
                  id: m.id,
                  name: m.name,
                  school_id: m.school_id,
                  shared: !!m.shared,
                })),
              ];
            },
          },
          { signal: lifecycle.signal },
        ),
      ).catch(() => {});
    } catch {
      /* Unsupported experimental browsers keep the ordinary interface. */
    }
    return () => lifecycle.abort();
  }, [signedIn]);
}
