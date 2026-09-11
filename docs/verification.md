# Local verification

Verified on September 10, 2026 on an Apple M2 Max with 64 GiB unified memory, using Python 3.12, PyTorch 2.10, MPS, and the pinned TinyLlama revision documented in the README.

## Measured model results

The complete website proxy and backend were exercised with `scripts/smoke-local.py --steps 8`. Each school used its own 24 synthetic instruction-response examples, with 19 training examples and 5 held-out examples. Each run initialized an independent rank-8 LoRA adapter from the same base model and seed.

| School | Baseline answer loss | Tuned answer loss | Baseline perplexity | Tuned perplexity | Held-out answer tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| University of Georgia | 3.96762 | 3.18478 | 52.859 | 24.162 | 186 |
| Georgia Tech | 5.09883 | 4.17827 | 163.830 | 65.253 | 175 |
| Emory University | 4.71079 | 3.86454 | 111.140 | 47.681 | 171 |

These are actual local measurements on small synthetic datasets. They are not benchmarks of general quality, evidence of teaching effectiveness, or privacy guarantees. Results across schools use different examples and are not directly comparable rankings. An earlier two-step smoke test improved held-out loss but left its displayed greedy answer unchanged, reinforcing the need to inspect outputs as well as metrics.

The smoke test also generated an answer from each saved adapter, enabled UGA model access, generated an answer as the User role, verified that User cannot list datasets, verified that User cannot invoke Georgia Tech's private adapter, and checked that shared metrics do not contain held-out prompt/answer samples. Numeric results remain in the ignored `.local/verification.json`; full dataset text and adapter files are not in this repository.

## Software checks

- Optimized Next.js build and TypeScript compilation passed.
- Prettier formatting check passed.
- Eight API regression tests and one live website proxy integration test passed, including role and institution boundaries, sharing/revocation, request validation, deterministic splitting, exclusive model access, and interrupted-run recovery.
- Source review identified and fixed a frontend stale-session race, selected-evaluation navigation, revoked-model selection, backend localhost cross-port Origin handling, and deeply nested JSONL handling.
- Shell startup scripts pass Bash syntax validation.
- The live proxy test sends the browser Origin and Sec-Fetch-Site headers, verifies login, multipart upload, deletion and logout, and rejects a cross-port Origin.
- UI routes were compiled and served locally. No browser interaction, screenshot, or visual regression testing was performed.
- The experimental read-only WebMCP tool is feature-detected; no supported browser context was used to validate it.
- CUDA and CPU full training were not exercised on this machine. The actual verified training path is Apple MPS.

## Reproduce

```bash
./scripts/setup.sh
./scripts/dev.sh
# In a second terminal:
.venv/bin/python scripts/smoke-local.py --steps 8
```

This adds real sample runs and enables sharing for the synthetic UGA verification adapter. No website deployment or remote model publishing occurs.
