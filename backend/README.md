# NVIDIA verification milestone

This directory contains developer verification tools and a small production model adapter. There is no FastAPI server, agent, orchestrator, or data integration. No existing Python backend/environment was present; `.venv` is the single Python environment for this work.

## Status

- Preferred candidate: `nvidia/nemotron-3.5-super-vl-120b-a12b`.
- Credentialed access and exact-marker text inference: **passed on 2026-10-25**.
- Vision: **passed** using one actual local screenshot. Its parsed JSON matched the visible content. The endpoint reported `private/nvidia/nemotron-3.5-super-120b-a12b` as its response alias; this is recorded separately from the requested catalog ID.
- No raw OCR/description result is saved in the repository.
- Local validation: offline mocked protocol tests, including credential protection and actual image-byte encoding. These do not establish model availability or capability.
- Production adapter: **implemented after direct NVIDIA verification**, in `app/adapters/nightshift.py`. It uses only Nightshift credentials and refuses direct NVIDIA endpoint configuration.
- Nightshift routing to this exact NVIDIA model: **not verified**; instance URL, token, and routing configuration are not supplied.

## Setup

Run from the repository root with Python 3.10+:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
# Only if backend/.env does not already exist:
cp -n backend/.env.example backend/.env
chmod 600 backend/.env
```

Put the real `NVIDIA_API_KEY` in the ignored `backend/.env`, or export it in your local shell. Never paste it into source, command arguments, logs, or chat. Environment variables take precedence over the file. The file loader reads exactly `backend/.env`, regardless of the working directory.

A blank `NVIDIA_MODEL` attempts the preferred candidate; this is a test candidate, not a guaranteed entitlement. No other model is selected automatically. `NVIDIA_BASE_URL` is restricted to the official NVIDIA HTTPS inference endpoint to prevent accidental credential forwarding.

## Run the direct NVIDIA tests

Text first, with no image transmission:

```sh
backend/.venv/bin/python backend/scripts/test_nvidia.py --text-only
```

One actual local screenshot, after text succeeds:

```sh
backend/.venv/bin/python backend/scripts/test_nvidia.py --image screenshot/0d113036-4275-46f7-bea5-f9deebfdbc09.JPG
```

With no arguments, the script selects the first suitable file from `sample_data/screenshots/`, then the existing `screenshot/` directory. It checks file signatures for PNG/JPEG/WebP and sends only image bytes and a fixed prompt; neither filenames nor paths are included in the model request. The selected file above was visually reviewed for exposed credentials before any potential request. No manual classification is sent to the model.

The image is encoded as a data URL and sent directly to NVIDIA. There is no public upload or storage service. Images larger than the local 20 MiB guard are refused; an endpoint may impose a smaller limit. The script never switches models or uploads an image elsewhere after an error.

The response must parse as `{description: string, visible_text: string[], possible_entities: string[]}`. Its content is suppressed by default because screenshots can contain private text. Add `--show-result` to display the parsed JSON locally. No result files are saved. A model accepting an image and returning valid JSON establishes a protocol check; inspect its description to judge whether it understood the visible content.

On a missing/unavailable model, inspect catalog entries:

```sh
backend/.venv/bin/python backend/scripts/test_nvidia.py --list-models
```

Listing is not proof of entitlement, inference, or vision. Select another NVIDIA Nemotron candidate explicitly only after checking its image support. Authentication, model/endpoint availability, rate limits, timeouts, rejected image formats/sizes, empty responses, truncated output, and malformed JSON all fail visibly. Error bodies/request objects are not logged. The script makes no automatic retries.

## Production path: Nightshift

The intended path is `Recall agent -> ModelGateway -> Meterless Nightshift -> NVIDIA Nemotron`. `NVIDIA_API_KEY` belongs exclusively to the developer smoke test; agents must use Nightshift credentials instead. Configure the NVIDIA provider key inside Nightshift.

`app/adapters/nightshift.py` exposes async `ModelGateway.complete(messages, max_tokens=...) -> str` using `METERLESS_BASE_URL`, `METERLESS_API_KEY`, and an explicitly discovered `METERLESS_MODEL`. It checks the selected ID against Nightshift discovery before its first completion, preserves text/image message content, and never falls back to direct NVIDIA. Missing credentials, unreachable runtime, unadvertised routes, rejected requests, and incomplete responses produce concise errors without response dumps. Use it as an async context manager to close connections.

For example, after loading your deployment environment:

```python
from backend.app.adapters.nightshift import ModelGateway

async with ModelGateway.from_env() as model:
    answer = await model.complete([{
        "role": "user", "content": "Describe this saved intention briefly."
    }])
```

Configure the Nightshift URL and token first, then discover its routing IDs:

```sh
backend/.venv/bin/python backend/scripts/test_nightshift.py --list-models
```

Set `METERLESS_MODEL` to an exact advertised `meterless/*` ID, configure that route to Nemotron inside Nightshift, then run:

```sh
backend/.venv/bin/python backend/scripts/test_nightshift.py
backend/.venv/bin/python backend/scripts/test_nightshift.py --image screenshot/0d113036-4275-46f7-bea5-f9deebfdbc09.JPG
```

These checks currently stop with `Missing METERLESS_BASE_URL`; no runtime configuration has been supplied. The adapter reads no `.env` file on import and never reads `NVIDIA_API_KEY`. The developer CLI explicitly loads `backend/.env`.

Nightshift's OpenAI-compatible contract requires instance model discovery and request headers `meterless-app: recall` and `meterless-scope: user`. Public Runtime documentation uses routing IDs such as `meterless/vision`; those names do not establish which underlying provider handled a request. Use the instance's actual model listing and routing configuration, then inspect provider/route evidence to confirm Nemotron execution. Never silently use an unconstrained auto route and claim NVIDIA use. No Nightshift installation or provider configuration is changed by this setup.

Verification completed before the adapter was implemented:

- The exact text marker passed with the configured local NVIDIA credential.
- One screenshot was sent as actual image bytes, without its filename.
- JSON parsing and visual comparison confirmed a relevant description and visible text.
- The Nightshift adapter and its error/routing behavior passed offline tests.

Remaining gates before Evidence Agent implementation:

1. Supply the Nightshift instance URL/token and discover its supported vision route.
2. Configure that route to the verified Nemotron model and confirm actual NVIDIA execution through Nightshift; route discovery alone is not sufficient.
3. Run the Nightshift text and image commands above, then update the routing-verification status here and in `metadata.json`.
4. Start the Evidence Agent as a separate milestone; no agents have been implemented here.

## Offline checks

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -v
```

The 18 tests cover the NVIDIA smoke protocol and Nightshift gateway. All HTTP calls in these tests use an in-memory mock transport. They never send screenshots or credentials over the network. Direct test requests use the OpenAI Python client against NVIDIA, as shown in NVIDIA's catalog; the SDK name does not make OpenAI the inference provider.

## Official references

- [NVIDIA hosted API example and modalities](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b)
- [NVIDIA model card](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b/modelcard)
- [NVIDIA local-media data URL examples](https://catalog.ngc.nvidia.com/orgs/nim/nvidia/models/nemotron-3.5-super-vl-120b-a12b/-)
- [Meterless integration contract](https://www.meterless.ai/engines.html)
