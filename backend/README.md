# Recall backend

Start with the [root judge guide](../README.md). The supported runtime is FastAPI, with all model calls going through `app/adapters/nightshift.py`. Evidence uses a Nightshift vision route; Open Loop, Context and Critic use Nemotron through Nightshift. Configure NVIDIA/OpenAI provider credentials inside Nightshift, not Recall.

- [API contract](../docs/api.md): screenshots, context, Check-in, runs, and recorded cases.
- [Agent contracts](../docs/agents/README.md) and [orchestration](../docs/architecture/agent-orchestration.md).
- [Zetaris setup](ZETARIS_INTEGRATION.md): JDBC repository and schema.
- [Operations](../docs/operations.md): local services, preflight, Tailscale.
- [Recorded examples](recordings/README.md): frozen inputs, captured replies, offline replay.
- `backend/.env.example`: placeholder-only live configuration. Sample mode needs no env file.
- `backend/legacy/`: historical direct-provider probe, excluded from the supported setup path.

Tests (from repository root):

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests
```

The suite includes four real H-MEM engine tests when Node and `engines/hmem/node_modules/.bin/tsx` are available. Two live Zetaris tests skip unless explicitly enabled. The test suite makes no live model calls.
