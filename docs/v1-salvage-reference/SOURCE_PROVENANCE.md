# Manual V1 Source Provenance

## Canonical Google Drive package

Folder:

`https://drive.google.com/drive/folders/1OYeKejBX6B1QOA1a0-ulhTEH4TrGfxo1`

Observed package files:

| File | Drive file ID | Size | Role |
|---|---|---:|---|
| `AlgoFortis_FINAL.zip` | `1GVlGemBl5V0MhNG0YT3YloJd7PbCi4x5` | 392,803,279 bytes | canonical complete archive |
| `AlgoFortis_FINAL.part001` | `1WU_Dj6CobIoeZLMCgvFZ6-M4y9gv0ByN` | 199,229,440 bytes | split archive part 1 |
| `AlgoFortis_FINAL.part002` | `1Asb6lX-emG4pXn8CQhXysOj7NaPpkPxz` | 193,573,839 bytes | split archive part 2 |

The split sizes sum to the complete archive size.

## Final manual V1 certification identity

The preserved final certification evidence recorded:

- Product: `AlgoFortis Trading Research & Risk OS`
- Manual V1 working HEAD: `3b84c035a051aab5334c8677165e2c4bd6ba01b8`
- Branch at certification: `feature/multi-broker-live-foundation`
- Final verified manifest entries: `394`
- Manifest self-digest: `b4952e48b954d960e0a579c69488c3bffc1a7d5a1ebe67fe650474b54acafbc6`
- Production security DB size during certification: `397,312` bytes
- Production security DB SHA-256: `99230AA96ECCF58B0460667647DA4D294C6AE040B95D38339CCA532B9AC2DCF5`
- Production DB mutation during final certification: `ZERO`

The final evidence also recorded `394/394` manifest keys byte-identical, with `0` missing and `0` mismatches.

## Important Git/history distinction

The manual final V1 was certified from a local working tree and its final certification explicitly recorded:

- `GIT COMMIT = NO`
- `GIT PUSH = NO`

Therefore, **do not assume every final manual-V1 byte exists in GitHub history** merely because earlier V1 ancestors exist there.

This is why the Drive package remains the raw-source authority for any exact manual-V1 file that cannot be reconstructed from current Git history.

## Archive retrieval policy

Normal development should **not** redownload/re-audit the entire archive.

Use this branch first:

1. Read `ADOPTION_MATRIX.md` to determine whether the capability is wanted.
2. Read `PATH_AND_CAPABILITY_MAP.md` for likely source path/component.
3. Check current Git history/tree for the same implementation or descendant.
4. Retrieve from Drive only if an exact final manual-V1 source file is still required.

## Why the raw ZIP is not committed here

The canonical package is ~393 MB and contains source plus generated/history/duplicate material. Committing the archive to Git would:

- bloat repository history;
- duplicate generated artifacts;
- make accidental migration of `.kilo/worktrees`, caches, installer binaries and build output easier;
- blur the boundary between evidence and current production source.

So this branch stores the **verified knowledge, provenance and salvage map**, not the binary archive itself.
