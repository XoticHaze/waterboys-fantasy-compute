# Agent Fabric: public fictional visual QA, fixture 01

**Status:** Source and ground-truth fixture only; **no accepted NVIDIA vision-model inference**, no real private screenshots, no device/broker state or commands.

Use this to distinguish image description from practical operator intelligence. Open `fictional_dashboard.html` at a 1200 x 760 viewport and render a screenshot. The frozen screenshot's SHA-256 is in `gold_truth.json` (rendered in headless Chromium); rendering on another browser/version may change pixels and must be independently hashed. The current PNG is retained in the Manual Worker artifact Library, not assumed deployed.

The task is to read the screenshot and compare it against `gold_truth.json`, separately reporting **what appears on screen** versus **what source evidence actually supports**. The fictional display intentionally contains four problems: last-known connected gateway misrepresented as current when stale; unknown bars displayed as zero; code test success mislabeled as model learning; and overlapping audit text. The correct zero-admissions and explicitly unknown API freshness cards are controls, not defects.

## Acceptance rubric

- The model locates all three high-severity source-versus-screen factual discrepancies without inventing status, values, logs, or credentials.
- It locates and explains the overlap region and proposes a readable layout correction.
- It explicitly distinguishes unverified/missing from numerically verified zero; treats the 60/60 functional source score as **zero proven corrections**.
- The output includes evidence-region references, proposed labels, reason and a human-readable remediation; deterministic truth and human review remain final.
- It recommends no retry, live trade, root or HAOS command and has no authorization to perform one.

**First model candidate to probe, not admitted:** `nvidia/nemotron-nano-12b-v2-vl`, documented by NVIDIA as supporting OpenAI-compatible image inputs. Provider availability, image limits, data residency, elapsed time and cost under the existing account have not been verified.

The existing text-only public synthetic NVIDIA fixed-task pipeline does **not** automatically authorize image-input access; stage a separate bounded synthetic image request and source-pinned private binding before model scoring. This fixture is not commercial product validation or a live user screenshot.

Parent: [CommandCenter #1206](https://github.com/XoticHaze/CommandCenter/issues/1206). Research execution policy and source-authenticated approvals remain authoritative. Run `python -m unittest discover -s tests -p 'test_agent_fabric_vision_fixture.py' -v` from repository root to verify the source fixture.

Manual Worker `MW-20261121121226848`.
