# Notice

`src/`, `test/`, `conformance/`, `package.json`, `tsconfig.json` and `LICENSE` are the **unmodified** H-MEM reference implementation and
conformance suite from [Meterless/Meterless](https://github.com/Meterless/Meterless), `engines/hmem`, at commit `1742dec56a66e58eef9dda2d2b865823758ca8cd`, licensed under
the Apache License 2.0 (see `LICENSE`). They are included as permitted by that license.

Added by Recall (our work, not part of the Meterless distribution):

- `server.ts`: a small HTTP face over the engine (`add`, `query`, `feedback`, ledger, reset). It contains no memory logic.
- `README.md` (this folder) and the Python integration in `backend/app/hmem.py`.

The reference files were audited before use: no network, process or `eval` APIs; the only system access is `node:fs`/`node:path`, to persist JSON
and the ledger into a directory the caller chooses.
