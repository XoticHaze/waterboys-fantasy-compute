# First delivered agent code artifact: five verified synthetic helpers

**State:** source-only, static-reviewed, public-fictional. Not a production code patch, autonomous recovery, live trade, device operation or model promotion.

| Human question | Answer |
| --- | --- |
| What is this? | The **exact five Python function outputs** from an NVIDIA Poolside model run, preserved as a reviewable source artifact rather than just a green score. |
| Is it for me? | For reviewers assessing whether inexpensive agent models can produce bounded code artifacts with reproducible correctness. Not a library to install into live CommandCenter. |
| Why should I trust it? | Public [GitHub run 44499189813](https://github.com/XoticHaze/waterboys-fantasy-compute/actions/runs/44499189813), job `135474137996`; five `NVIDIA_ROLE_VERIFIED_SYNTHETIC_PATCH` records, source SHA-256 `65411e83e826bd039729c381e9b895d8ad83f3f954ee14b01d72122a369f6ac0`, pinned Worker source `abd8fcac5299aaf5308e831db6a1fcfcd5066898`. Check exact source and independent score; workflow success alone is not a model-quality grade. |
| What do I do first? | Review `model_generated_functions.py`, then run `python experiments/nvidia-agent-artifact-v1/verify_artifact.py` from the public repository root. |
| What happens next? | The validator verifies fixed source bytes and uses the existing AST-only interpreter for 150 independently predetermined behavior cases. A passing result creates **no** production permissions. |
| Did it work? | The originating run reported 150/150. The new replay must independently reproduce all five 30/30 checks. Real patch application, execution and self-correction remain unproven. |
| What can I change or undo? | Any source byte change fails the frozen SHA-256 identity check; propose a new version and requalify instead of modifying this evidence. Delete or revert this isolated source-only experiment without touching production. |
| Where do I get help? | `ARTIFACT_SOURCE_HASH_MISMATCH`, `ARTIFACT_FUNCTION_IDENTITY_MISMATCH`, `ARTIFACT_AST_REJECTED` and failing check rows indicate why an attempted replay is rejected. Discuss follow-up in [CommandCenter #1206](https://github.com/XoticHaze/CommandCenter/issues/1206). |

## Separation of evidence and execution

The model-generated source is never imported, compiled or evaluated as Python. The reusable `scripts/nvidia_fixed_code_repair_work.py` AST interpreter scores safe expressions only. Exact original run/job identity must still be checked against GitHub separately; the file's self-reported IDs are not a cryptographic attestation. The source and README are public fictional examples only; the target future agent-artifact lifecycle will need a sandbox, independent tests, feedback revision, authorizing consumer and durable receipt before real-world use.
