# Laya upstream workspace

This directory owns the project-local copy of the upstream Laya runtime.

- `UPSTREAM.lock.json` is committed and pins the approved upstream source/model identity.
- `upstream/` is populated locally by `scripts/laya/bootstrap_laya.py` and is intentionally ignored by Git.
- Upstream source remains third-party code under Apache-2.0; AlgoFortis integration code lives separately under `engine/ai/laya/`.
- AlgoFortis uses Laya's direct single-model SDK path only. Laya is not an AlgoFortis agent router/orchestrator.
- Broker mutation, order placement, Live arming, and execution imports are prohibited from the Laya integration boundary.

The source checkout is kept physically inside the AlgoFortis project so the runtime can be inspected, pinned, updated, and replaced without mixing third-party files into AlgoFortis domain modules.
