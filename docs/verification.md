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
- Nine API regression tests and one live website proxy integration test passed, including role and institution boundaries, sharing/revocation, evaluation download authorization and redaction, request validation, deterministic splitting, exclusive model access, and interrupted-run recovery.
- Source review identified and fixed a frontend stale-session race, selected-evaluation navigation, revoked-model selection, backend localhost cross-port Origin handling, and deeply nested JSONL handling.
- Shell startup scripts pass Bash syntax validation.
- The live proxy test sends the browser Origin and Sec-Fetch-Site headers, verifies login, multipart upload, deletion and logout, and rejects a cross-port Origin.
- UI routes were compiled and served locally, then exercised in the Codex in-app browser. Desktop and 390px mobile screenshots were inspected. The manual interaction results are recorded below.
- The experimental read-only WebMCP tool is feature-detected; no supported browser context was used to validate it.
- CUDA and CPU full training were not exercised on this machine. The actual verified training path is Apple MPS.

## Browser interaction checks

| Area | Verified behavior |
| --- | --- |
| Landing | No missing-module overlay after a fresh load; generic workspace copy, animation pause/resume, home link and role selection work. |
| Authentication | Incorrect password feedback, all three example Contributor accounts, User account, desktop and mobile sign-out work. Switching accounts clears chat state. |
| Navigation | All five Contributor tabs and four User tabs work. Overview shortcuts, institution cards, logo, privacy shortcut, and recent activity reach their intended screens. |
| URLs | Refresh and Back/Forward preserve the tab and selected evaluation. A User opening `#institution` returns to Playground. A private evaluation link shows unavailable rather than an unrelated result. |
| Data | Uploaded six synthetic JSONL examples through the file chooser, checked selection, then deleted only that test upload. Template download, upload shortcut, Cancel and Close work. |
| Training | Started and completed a real two-step TinyLlama run through the UI. Its in-progress activity opened the institution view. Completed runs link to their own evaluations. |
| Evaluation | Experiment picker, reference-answer disclosure, owner JSON download and redacted User JSON download work. Unavailable evaluations link back to accessible results. |
| Sharing | Enabled and revoked access to the existing synthetic smoke-test adapter, restoring its private state. User does not see model-management controls. |
| Playground | Base and shared-adapter inference returned real MPS responses. Suggestions, model selection, Cmd+Enter, Clear session and tab switching during generation work. |
| External link | The embedding-inversion research link opened the intended arXiv paper. |
| Mobile | Exercised all navigation links at 390px. Found the development launcher covered Sign out; disabling that launcher restored the button. Build/runtime error reporting remains enabled. |

The browser pass found and fixed the evaluation Blob download failure, tab state loss on refresh, incorrect unfinished-run destinations, lost in-flight chat on tab changes, keyboard submission while disabled, and the mobile sign-out obstruction. The earlier missing `knowledge-flow` overlay came from the development edit interval; the component is tracked, the app was rebuilt/restarted, and a fresh browser load was verified. These are manual checks, not a committed automated browser suite.

## Reproduce

```bash
./scripts/setup.sh
./scripts/dev.sh
# In a second terminal:
.venv/bin/python scripts/smoke-local.py --steps 8
```

This adds real sample runs and enables sharing for the synthetic UGA verification adapter. No website deployment or remote model publishing occurs.
