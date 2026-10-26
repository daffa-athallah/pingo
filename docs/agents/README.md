# Recall agents

| Agent | Question | Model (via Meterless Nightshift) | Doc |
| --- | --- | --- | --- |
| Evidence | What am I looking at? | OpenAI GPT-4o-mini (vision) | [evidence-agent.md](evidence-agent.md) |
| Open Loop | What is this person still trying to do? | NVIDIA Nemotron 3 Ultra | [open-loop-agent.md](open-loop-agent.md) |
| Context | Does something happening now make it relevant? | NVIDIA Nemotron 3 Ultra | [context-agent.md](context-agent.md) |
| Critic | Is this worth bothering the user about? | NVIDIA Nemotron 3 Ultra | [critic-agent.md](critic-agent.md) |

How they work together, including the revision and verification branches, bounds and explainability: [Agent orchestration](../architecture/agent-orchestration.md).

Sponsor roles: **Zetaris** is the grounded shared data/state layer (Evidence, entities, relationships, Open Loops); it is not an agent. **Meterless Nightshift** is the model gateway and router. **NVIDIA Nemotron** does the reasoning. **OpenAI GPT-4o-mini** does screenshot perception.
