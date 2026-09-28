# Local Laya model workspace

`models/laya/original/` is the project-local checkpoint directory populated by `scripts/laya/bootstrap_laya.py`.

The large checkpoint files are intentionally not committed to Git. The committed authority is `third_party/laya/UPSTREAM.lock.json`, which pins the model identity and SHA-256 digest.

AlgoFortis loads this checkpoint through `engine/ai/laya/runtime.py` using Laya's direct single-model SDK. The model is restricted to market-intelligence research/shadow use and has no broker or execution authority.
