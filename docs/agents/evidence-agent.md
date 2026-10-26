# Evidence Agent

**Question it answers:** *"What am I looking at?"*

**Responsibility:** perception only. It turns one screenshot into structured, objective Evidence. It does not infer what the person wants.

Code: [`backend/app/agents/evidence.py`](../../backend/app/agents/evidence.py), mapping to storage in [`backend/app/ingestion/evidence_bridge.py`](../../backend/app/ingestion/evidence_bridge.py).

## Contract

| | |
| --- | --- |
| Input | One screenshot image |
| Output | `domain`, `summary` (objective, 1–2 sentences), `entities[]` (name, type, category, subcategory, brand, location, attributes), `sensitive`, `confidence` (`low`/`medium`/`high`) |
| Strictness | The parser rejects any output that does not match exactly these keys |
| Model | OpenAI GPT-4o-mini (vision), routed through Meterless Nightshift. The saved receipts show `requested_model = routed_model = gpt-4o-mini`, `provider = openai` |

The prompt treats text inside the image as data, never as instructions.

## Sensitive handling

If the screenshot visibly contains credentials, payment or ID numbers, health or private message content, the model sets `sensitive: true`. Downstream:

- the ingestion bridge stores no free-form attributes for sensitive Evidence;
- the Open Loop Agent returns `IGNORE` locally and never sends sensitive Evidence to a reasoning model;
- the Critic stays silent if any supporting Evidence is sensitive.

## Canonical example

Screenshot `IMG_8922.PNG` produced (abridged, from [`sample_data/evidence/IMG_8922.json`](../../sample_data/evidence/IMG_8922.json)):

```json
{
  "domain": "food",
  "summary": "The screenshot features a late-night halal burger spot in Melbourne CBD called OMB Burger, highlighting a promotion. It indicates the price is under $10.",
  "entities": [{"name": "OMB Burger", "type": "restaurant",
                "location": {"location_name": "Melbourne CBD", "city": "Melbourne", "country": "Australia"},
                "attributes": {"price": "under $10", "halal": "true", "late_night": "true"}}],
  "sensitive": false,
  "confidence": "high"
}
```

Note what is absent: no "wants to eat here", no "plans to visit". That is the Open Loop Agent's job.

## What it explicitly does NOT do

- No intention, goal, plan, or timing inference.
- No decision about whether anything is worth surfacing.
- No product-domain filtering. Evidence keeps whatever domain it sees (food, shopping, travel, health, event, …). Which domains are reasoned over is a separate, explicit policy in the Open Loop processing script.
- It never edits stored Evidence: Evidence is append-only.
