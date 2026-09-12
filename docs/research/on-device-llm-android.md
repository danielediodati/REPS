# On-device LLMs on Android, and where REPS's agent should run

Research date: 2026-09-11. Every claim cites its source inline; dates or versions are given where the source shows one. **[secondary]** marks a claim that only a non-primary source supports. **[inference]** marks my own reasoning from cited facts.

## Summary

1. **LangGraph cannot run inside an Android app today.** It depends on Rust wheels (pydantic-core, ormsgpack, orjson, uuid-utils), and none of them publishes an Android wheel on PyPI. Chaquopy's pydantic-core recipes are unmerged. LangGraph.js v1 breaks outside Node on `async_hooks`. Nobody documents doing either.
2. **Small on-device models cannot reliably run a multi-step, 10-tool agent.** On BFCL V4, multi-turn accuracy is 22% for Qwen3-4B-2507, 11% for Qwen3-1.7B and 4% for Llama-3.2-3B. On tau2, Gemma 4 E2B scores 24.5 against 76.9 for Gemma 4 31B.
3. **Runtimes:** Google's on-device stack is now **LiteRT-LM** (Kotlin API stable, tool calling, constrained decoding documented for C++). MediaPipe LLM Inference is maintenance-only.
4. **Gemini Nano (ML Kit Prompt API) is not an agent runtime.** It is beta, has no function calling, offers structured output only as alpha, runs only while the app is in the foreground under quotas, and only on listed flagships.
5. **Recommended architecture: (a) thin client.** A Kotlin APK talks HTTP/SSE to a Python LangGraph server that uses Ollama on the PC. Keep on-device AI to one optional, single-turn, schema-constrained feature, or none.
6. **The dev PC is the real bottleneck.** Ollama is *dropping* the Radeon 860M: the server log shows it, and it can be enabled with `OLLAMA_IGPU_ENABLE=1`. Ollama's default context is 4k tokens on under 24 GiB VRAM, which truncates agent tool results. Measured here: 35.8 tok/s prompt eval and 7.8 tok/s generation on CPU.

---

## 1. On-device LLM runtimes on Android

### Google AI Edge: LiteRT-LM (current)

- **Status:** open source, Apache-2.0, Android/iOS/Web/Desktop/IoT ([repo](https://github.com/google-ai-edge/LiteRT-LM)). Latest release is v0.17.0, 2026-09-09 ([GitHub releases API](https://api.github.com/repos/google-ai-edge/LiteRT-LM/releases)).
- **APIs:** Kotlin, C++, Python and CLI are *Stable*. Swift and JS are *Early Preview*. NPU on Android is preview ([overview, updated 2026-09-04](https://developers.google.com/edge/litert-lm/overview)).
- **Models** (from the overview model table): Gemma 4 E2B/E4B, Gemma 3n E2B/E4B, Gemma 3 1B, FunctionGemma 270M, Phi-4-mini, Qwen2.5 0.5B/1.5B, Qwen3 0.6B. The format is `.litertlm`.
- **Tool calling in Kotlin:** `@Tool` and `@ToolParam` annotations, plus an `automaticToolCalling` loop that is on by default ([Kotlin getting started](https://github.com/google-ai-edge/LiteRT-LM/blob/main/docs/api/kotlin/getting_started.md)).
- **Constrained decoding:** regex, JSON Schema, Lark grammar, or the tool-call format. Only one of these can be set per `Conversation`. **The doc covers the C++ API only**, and the Kotlin guide does not mention it ([constrained decoding doc](https://github.com/google-ai-edge/LiteRT-LM/blob/main/docs/api/cpp/constrained-decoding.md)).
- **Known bug:** Kotlin tool responses serialize empty for Qwen3. The issue has been open since 2025-11-26 ([#1027](https://github.com/google-ai-edge/LiteRT-LM/issues/1027)).
- **Speeds published by Google** (all on flagship phones; Google publishes **no ~8 GB mid-range phone numbers**):

| Model | Size on disk | Device | CPU prefill / decode tok/s | GPU prefill / decode tok/s | Memory |
|---|---|---|---|---|---|
| Gemma 4 E2B | 2583 MB | Galaxy S26 Ultra | 557 / 46.9 | 3808 / 52.1 | 1733 MB CPU, 676 MB GPU |
| Gemma 4 E4B | 3654 MB | Galaxy S26 Ultra | 195 / 18 | 1293 / 22 | n/p |
| Gemma 3n E4B | 4235 MB | Galaxy S24 Ultra | 74 / 9 | 548 / 9 | n/p |
| Phi-4-mini | 3906 MB | Galaxy S24 Ultra | 67 / 7 | 314 / 10 | n/p |
| Qwen3 0.6B | 586 MB | Vivo X300 Pro | 165 / 9 | 580 / 21 | n/p |
| FunctionGemma 270M | 289 MB | Galaxy S25 Ultra | 2238 / 154 | n/p | n/p |

The Gemma 4 E2B row comes from the [HF model card](https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm), measured at 2048 context. The other rows come from the [overview table](https://developers.google.com/edge/litert-lm/overview). n/p means not published.

### Google AI Edge: MediaPipe LLM Inference API and the FC SDK (legacy)

- **MediaPipe LLM Inference:** *"The MediaPipe LLM Inference API is in maintenance-only mode. We recommend migrating your Android projects to LiteRT-LM Android (Kotlin) API."* ([Android guide, updated 2026-06-12](https://developers.google.com/edge/mediapipe/solutions/genai/llm_inference/android)).
- **AI Edge Function Calling SDK:** built on LLM Inference, with Gemma, Llama and Hammer formatters. The official guide points to LiteRT-LM as the replacement ([FC SDK Android guide](https://developers.google.com/edge/mediapipe/solutions/genai/function_calling/android); I saw this in the search snippet and did not read the page in full). **Do not start new work on either.**
- **Reference app:** Google AI Edge Gallery is Apache-2.0, needs Android 12+, runs on LiteRT, and has "Agent Skills" plus "Mobile Actions" driven by a fine-tuned FunctionGemma 270M ([repo](https://github.com/google-ai-edge/gallery)).

### Gemini Nano via ML Kit GenAI / AICore

- **APIs:** Prompt (free-form text or image+text), Summarization, Proofreading, Rewriting, Image Description, Speech Recognition ([Gemini Nano page, updated 2026-09-08](https://developer.android.com/ai/gemini-nano)).
- **Prompt API status:** *Beta*, `genai-prompt:1.0.0-beta4`. Input should stay under about 4,000 tokens ([get started, updated 2026-09-08](https://developers.google.com/ml-kit/genai/prompt/android/get-started)). beta3 (2026-07-14) added structured output, system instructions, thinking mode and a 4,096-token output limit ([release notes](https://developers.google.com/ml-kit/release-notes)). **A free-form prompt API is available to third-party apps.**
- **Structured output is Alpha:** Kotlin only, via `@Generable` and `@Guide` annotations ([structured output, updated 2026-07-21](https://developers.google.com/ml-kit/genai/prompt/android/structured-output)).
- **No function calling** is documented anywhere in the Prompt API docs.
- **Restrictions:** *"GenAI API inference is permitted only when the app is the top foreground application"*. There is a per-app inference quota (`BUSY`) and a daily battery quota (`PER_APP_BATTERY_USE_QUOTA_EXCEEDED`) ([overview, updated 2026-09-10](https://developers.google.com/ml-kit/genai)). Devices with an unlocked bootloader are not supported ([get started](https://developers.google.com/ml-kit/genai/prompt/android/get-started)).
- **Devices:** the Prompt API runs on a device-specific list. nano-v2 through nano-v4 cover Pixel 9/10/11, Galaxy S26, Z Fold7/Fold8/Flip8, OnePlus 13/15, recent OPPO, vivo, Xiaomi, Honor and others, and outputs differ between Nano versions ([overview](https://developers.google.com/ml-kit/genai)). Model size, RAM and tok/s are not published, because the system manages the model.
- **Firebase AI Logic hybrid inference:** *Experimental*. The on-device path supports only single-turn text generation. It explicitly excludes chat, structured output and function calling ([Firebase hybrid Android, updated 2026-09-10](https://firebase.google.com/docs/ai-logic/hybrid/android/get-started); [Android hybrid page](https://developer.android.com/ai/hybrid)).

### llama.cpp on Android

- **Integration:**
  - an Android Studio sample (`examples/llama.android`) with a Kotlin `AiChat` facade and `Flow` token stream;
  - a Termux build;
  - NDK cross-compilation for arm64, API 28+ ([android.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md)).
  - The project also ships `llama-bXXXX-bin-android-arm64.tar.gz` binaries (release b10903, 2026-09-11, [releases API](https://api.github.com/repos/ggml-org/llama.cpp/releases)). License is MIT.
- **GPU:** OpenCL is supported on Adreno 750/810/830/840. *"A6x GPUs in phones likely aren't supported due to outdated drivers"* ([OPENCL.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENCL.md)).
- **Tools:** `llama-server --jinja` provides OpenAI-style tool calling with native handlers (Llama 3.x, Qwen 2.5, Hermes, Mistral Nemo, and more) and a generic fallback. The docs warn that extreme KV quantization degrades tool calling ([function-calling.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)).
- **React Native binding:** `llama.rn` (MIT) supports `tools` via Jinja, GBNF grammars, and `response_format` JSON schema converted to GBNF. It runs OpenCL on Adreno 700+ and has experimental Hexagon NPU support ([repo](https://github.com/mybigday/llama.rn)).
- **Models:** any GGUF, so Qwen3.x, Gemma 3/4, Llama 3.2, Phi-4-mini.
- **Phone speeds:** none published by the project.

### MLC LLM

- **Platform:** Apache-2.0, Android via OpenCL on Adreno and Mali ([repo](https://github.com/mlc-ai/mlc-llm)).
- **Integration:** a Java binding (`tvm4j_core.jar`). Building needs Rust, NDK 27 and a physical device, and the demo targets the Galaxy S23. No speeds are published ([Android docs, v0.1.0](https://llm.mlc.ai/docs/deploy/android.html)).
- **Tools and JSON:** the REST API documents `tools`/`tool_choice` and `response_format` `json_object` with an optional schema ([REST docs](https://llm.mlc.ai/docs/deploy/rest.html)). **Whether these work through the Android binding is unverified.**

### ExecuTorch (PyTorch)

- **Platform:** BSD license. Kotlin/Java AAR with `LlmModule`. Android backends are XNNPACK, Vulkan, Qualcomm, MediaTek and Samsung Exynos. LLMs: Llama 3.x, Qwen 3, Phi-4-mini, LFM2 ([repo](https://github.com/pytorch/executorch); [Android docs 1.3](https://docs.pytorch.org/executorch/stable/llm/llama-demo-android.html)).
- **Published phone speeds, on a OnePlus 12 flagship** ([llama README](https://github.com/pytorch/executorch/blob/main/examples/models/llama/README.md)):
  - Llama 3.2 1B SpinQuant: decode 50.2 tok/s, 1083 MiB on disk, RSS 1921 MiB.
  - Llama 3.2 3B: decode 19.7 tok/s, 2435 MiB.
  - Llama 3 8B on a Galaxy S24: about 11 tok/s.
- **Tools and structured output:** not documented.

### Ollama on Android

- **No official Android build.** Termux's main repository packages `ollama` 0.31.1, built with the Vulkan backend, excluding arm and i686 ([termux-packages build.sh](https://github.com/termux/termux-packages/blob/master/packages/ollama/build.sh)).
- **Not embeddable in an APK [inference]:** Termux is a separate app, so an APK could only call Termux's `localhost:11434`. That requires the user to install and run Termux, which makes it a demo trick, not an app architecture.
- **Setup guides are community-written [secondary]:** [example](https://github.com/n4od/Ollama-Android-Setup).

### Others

- **Cactus:** a hybrid edge-cloud engine with Kotlin, React Native and Flutter bindings, OpenAI-format tool calling, and Gemma/Qwen/Liquid models. Published benchmarks cover iPhone and Mac only (Gemma-4-E2B at 37 tok/s decode on iPhone 17 Pro). GitHub shows no SPDX license (NOASSERTION), so **check the license before use** ([repo](https://github.com/cactus-compute/cactus)).

---

## 2. Can the agent orchestration run on the phone?

| Option | Documented as supported | Blog-level evidence | Blockers found |
|---|---|---|---|
| **LangGraph Python via Chaquopy** | **No** | **None found** | Needs Rust extension wheels, and none has an Android wheel on PyPI (see below). Chaquopy issue [#1017 "pydantic v2"](https://github.com/chaquo/chaquopy/issues/1017) is open. PR [#1328 "Add pydantic core"](https://github.com/chaquo/chaquopy/pull/1328) was closed unmerged (2025-01-27). PR [#1413 "Recipe to build pydantic-core"](https://github.com/chaquo/chaquopy/pull/1413) has been open since 2025-10-30. Past LangChain installs on Chaquopy failed ([#1007](https://github.com/chaquo/chaquopy/issues/1007), [#975](https://github.com/chaquo/chaquopy/issues/975)). |
| **LangGraph Python via BeeWare/Briefcase** | **No** | **None found** | Briefcase's Android backend builds on Chaquopy, so it hits the same wheels. There is an open-issue trail on this: [briefcase#1544 "Crash loading pydantic_core on Android"](https://github.com/beeware/briefcase/issues/1544). |
| **LangGraph.js in React Native / Expo** | **No** | **None found** | v1 imports `AsyncLocalStorage` from `node:async_hooks`, and [langgraphjs#1699](https://github.com/langchain-ai/langgraphjs/issues/1699) about it is open. The 0.x `@langchain/langgraph/web` workaround ([#81](https://github.com/langchain-ai/langgraphjs/issues/81)) has no v1 docs ([docs#1177](https://github.com/langchain-ai/docs/issues/1177), open). A GitHub search of langgraphjs for "react native" returns no runtime-support issue ([search API](https://api.github.com/search/issues?q=repo:langchain-ai/langgraphjs+%22react+native%22)). |
| **JetBrains Koog (Kotlin)** | **Partly.** Android target since 0.4.2 (2025-09-15) ([CHANGELOG](https://github.com/JetBrains/koog/blob/main/CHANGELOG.md)). 1.0.0 (2026-05-21) added a *"LiteRT LLM client for running Google's LiteRT models locally"* and `runFromCheckpoint` ([release](https://github.com/JetBrains/koog/releases/tag/1.0.0)). Graph workflows, persistence and an Ollama provider are included ([repo](https://github.com/JetBrains/koog)). Apache-2.0; latest 1.2.0 (2026-08-28). | None found | Issue [#262 "Android local LLM support"](https://github.com/JetBrains/koog/issues/262) is still open, so there is no documented end-to-end on-device agent sample. |
| **LangChain4j on Android** | **No.** The docs target the JVM and server frameworks ([intro](https://docs.langchain4j.dev/intro/)). | None found | Issue [#1135](https://github.com/langchain4j/langchain4j/issues/1135) is closed without a documented Android answer. |
| **Google on-device agent tooling** | LiteRT-LM tool calling (Kotlin), the legacy FC SDK, and AI Edge Gallery "Agent Skills" | n/a | Google ships no on-device orchestration framework with graphs, checkpoints or interrupts. |

**Wheel check** (PyPI JSON API, 2026-09-11):

- `langgraph` 1.2.11 requires `pydantic>=2.7.4`, `xxhash`, `langgraph-checkpoint`→`ormsgpack`, `langgraph-sdk`→`orjson`, and `langchain-core`→`uuid-utils`.
- **No Android wheels:** `pydantic-core` 2.49.0 (2026-09-09), `ormsgpack` 1.12.2, `orjson` 3.12.0, `uuid-utils` 1.0.0, `jiter` 0.16.0.
- **Has Android wheels:** only `xxhash` 4.0.1 (`cp313-android_24_arm64_v8a`).
- **Upstream request deferred:** pydantic's request to publish Android/iOS wheels is open and labelled *Deferred* ([pydantic#12739](https://github.com/pydantic/pydantic/issues/12739), opened 2026-01-24).
- **Third-party wheels exist only for Termux, not for Chaquopy APKs [secondary]:** [Eutalix/android-pydantic-core](https://github.com/Eutalix/android-pydantic-core).

**Verdict:** a fully on-device agent means rewriting the orchestration in Kotlin (Koog or hand-written), and **it would no longer be a LangGraph project.**

---

## 3. Architectures

### (a) Thin client of a LangGraph server

- **`langgraph dev`:** an in-memory dev server on port 2024 with hot reload and no Docker. It needs Python 3.11+ and offers `--tunnel` for a public URL ([CLI docs](https://docs.langchain.com/langsmith/cli)).
- **`langgraph up`:** Docker plus Postgres. It *"requires a LangSmith API key"* for local testing and *"a license key for production use"* ([CLI docs](https://docs.langchain.com/langsmith/cli)).
- **Standalone self-hosted Agent Server:** needs `LANGGRAPH_CLOUD_LICENSE_KEY`, Postgres and Redis ([standalone server](https://docs.langchain.com/langsmith/deploy-standalone-server)). Self-hosting is tied to the Enterprise plan ([self-hosted](https://docs.langchain.com/langsmith/self-hosted); seen in the search snippet).
- **Client SDKs:** Python and JS/TS only. The JS SDK covers assistants, threads, runs, crons and the store, streaming over SSE with an optional WebSocket, and a React `useStream` hook ([npm `@langchain/langgraph-sdk`](https://www.npmjs.com/package/@langchain/langgraph-sdk), via search snippet because the page returned 403; [JS SDK reference](https://docs.langchain.com/langsmith/langgraph-js-ts-sdk)). **There is no Kotlin SDK**, so a native APK would call the HTTP API directly.
- **React Native streaming:** RN has no native `EventSource`, so SSE needs a polyfill or manual parsing of a streamed `fetch` [secondary: [getwireai blog](https://getwireai.com/blog/react-native-llm-streaming)].
- **Human-in-the-loop over the API:** `client.runs.wait` returns the interrupt payload. The client resumes with `Command(resume=...)` in Python or `{command: {resume: ...}}` in JS on the same thread ([HITL via server API](https://docs.langchain.com/langsmith/add-human-in-the-loop)). This maps 1:1 onto REPS's interrupts: clarify, confirm exclusion, refuse plan.
- **License-free option [inference]:** the `langgraph` library itself is MIT ([repo](https://github.com/langchain-ai/langgraph)). A small FastAPI app that owns the compiled graph, a checkpointer and a store avoids Agent Server licensing entirely.

### (b) Hybrid

A small on-device model (LiteRT-LM or Gemini Nano) handles some single-turn nodes, and the server handles the rest.

- **What the phone can do:** Google's own hybrid product (Firebase AI Logic) limits the on-device path to single-turn text with no tools and no JSON ([Firebase hybrid](https://firebase.google.com/docs/ai-logic/hybrid/android/get-started)). That is the realistic ceiling for phone-side nodes.
- **The cost [inference]:** a hybrid splits the LangGraph state across two runtimes. The phone node is outside the checkpointer unless it is modelled as a client-side "tool" whose result is sent back as an interrupt resume.

### (c) Fully on-device

- **What it requires:** Kotlin orchestration plus LiteRT-LM or llama.cpp, with a model of 4 GB or less.
- **Blockers:** LangGraph cannot run on the phone (section 2), and small models are unreliable at multi-turn tool use (section 4).

---

## 4. Reliability of small models for agentic tool use

### Independent: BFCL V4

Source: the [Berkeley Function Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html), last updated 2026-04-12, data from [data_overall.csv](https://gorilla.cs.berkeley.edu/data_overall.csv).

| Model (mode) | Overall | Multi-turn |
|---|---|---|
| Claude-Opus-4.5 (FC), rank 1 | 77.47 | 68.38 |
| Qwen3-235B-A22B-Instruct-2507 (Prompt) | 52.15 | 44.62 |
| xLAM-2-8b-fc-r (FC) | 46.68 | 70.00 |
| Qwen3-8B (FC) | 42.57 | 41.75 |
| xLAM-2-3b-fc-r (FC) | 41.22 | 58.38 |
| Qwen3-14B (FC) | 41.03 | 34.75 |
| Qwen3-4B-Instruct-2507 (FC) | 35.68 | **22.12** |
| xLAM-2-1b-fc-r (FC) | 30.44 | 36.00 |
| Gemma-3-12b-it (Prompt) | 30.43 | 5.75 |
| Qwen3-1.7B (FC) | 28.41 | **11.00** |
| Qwen3-0.6B (FC) | 23.93 | 3.62 |
| Llama-3.2-3B-Instruct (FC) | 21.95 | **4.00** |
| Llama-3.2-1B-Instruct (FC) | 10.82 | 0.00 |

The CSV has no rows for Gemma 4, Qwen3.5/3.6/3.8, gpt-oss-20b, Phi-4-mini or FunctionGemma.

### Self-reported: model cards

- **Qwen3.5, thinking mode:**
  - BFCL-V4: 9B 66.1, 4B 50.3, 2B 43.6, 0.8B 25.3.
  - TAU2: 9B 79.1, 4B 79.9, 2B 48.8, 0.8B 11.6.
  - The 2B card says the small sizes are meant for *"prototyping, task-specific fine-tuning"*.
  - Sources: [9B](https://huggingface.co/Qwen/Qwen3.5-9B), [4B](https://huggingface.co/Qwen/Qwen3.5-4B), [2B](https://huggingface.co/Qwen/Qwen3.5-2B).
- **Gemma 4, Tau2 averaged over 3 runs:** E2B 24.5, E4B 42.2, 12B 69.0, 26B-A4B 68.2, 31B 76.9. Native function calling ([model card, updated 2026-07-30](https://ai.google.dev/gemma/docs/core/model_card_4)).
- **Qwen3.6-35B-A3B:** MCPMark 37.0, TAU3-Bench 67.2 ([card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)).
- **FunctionGemma 270M, 0-shot BFCL:** simple 61.6, parallel-multiple 29.5. The card says it is *"not intended for use as a direct dialogue model"* and should be fine-tuned, which moved Mobile Actions from 58% to 85% ([card](https://ai.google.dev/gemma/docs/functiongemma/model_card)).
- **Llama 3.2 3B:** BFCL **V2** 67.0 ([card](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct)), against 21.95 overall on V4. The older single-turn benchmarks overstate agent ability.
- **Phi-4-mini (3.8B):** supports function calling but publishes no scores ([card](https://huggingface.co/microsoft/Phi-4-mini-instruct)).
- **gpt-oss-20b:** 21B total, 3.6B active, *"run within 16GB of memory"*. Function calling and structured outputs are supported, but no tool-use score is on the card ([card](https://huggingface.co/openai/gpt-oss-20b)).

### Verdict [inference from the tables above]

A 1-4B model can emit *syntactically* valid calls, and constrained decoding guarantees that much (LiteRT-LM, llama.cpp GBNF, Ollama `format`). It cannot reliably *choose* the right tool and arguments across several turns with about 10 tools: multi-turn accuracy is 4-22% for general small models on BFCL V4. That is not good enough for a planner that self-corrects on validator feedback. Only function-calling fine-tunes (xLAM-2-3b at 58% multi-turn) or 8B+ models get close.

### Ollama models with tools and structured outputs

- **Tool calling:** the Ollama docs use `qwen3` in every example, including parallel calls and agent loops ([tool calling](https://docs.ollama.com/capabilities/tool-calling)).
- **Structured outputs:** `format` takes a JSON schema. *"Ollama's Cloud currently does not support structured outputs"* ([structured outputs](https://docs.ollama.com/capabilities/structured-outputs); [blog, 2024-12-06](https://ollama.com/blog/structured-outputs)).
- **Context:** the default is **4k context below 24 GiB VRAM**. *"Tasks which require large context like ... agents ... should be set to at least 64000 tokens"*, set via `OLLAMA_CONTEXT_LENGTH` ([context length](https://docs.ollama.com/context-length)).

| Ollama model | Tags and size on disk | Tools / structured output | Source |
|---|---|---|---|
| qwen3 | 4b 2.5 GB, 8b 5.2 GB, 14b 9.3 GB, 30b 19 GB, 32b 20 GB | Tools (docs example); structured output via `format` | [library](https://ollama.com/library/qwen3) |
| qwen3.5 | 4b 3.4 GB, 9b 6.6 GB, 27b 17 GB, 35b 24 GB | Tools badge not shown on page (unverified) | [library](https://ollama.com/library/qwen3.5) |
| qwen3.6 | 27b 18 GB, 35b (A3B) 23 GB | Listed under tools | [library](https://ollama.com/library/qwen3.6), [tools search](https://ollama.com/search?c=tools) |
| qwen3.8 | 27b 18 GB | Listed under tools | [library](https://ollama.com/library/qwen3.8) |
| gemma4 | e2b 7.2 GB, e4b 9.6 GB, 12b 7.6 GB, 26b (A4B) 19 GB, 31b 20 GB | "native function-calling support" | [library](https://ollama.com/library/gemma4) |
| gpt-oss | 20b 14 GB (fits 16 GB), 120b 65 GB | Tools, thinking | [library](https://ollama.com/library/gpt-oss) |
| granite4.1 | 3b, 8b, 30b | Listed under tools | [tools search](https://ollama.com/search?c=tools) |

---

## 5. The dev PC: Ryzen AI 7 350, Radeon 860M, 32 GB, Windows 11, Ollama 0.33.3

### Measured on this machine (not a sourced claim)

- **Speed:** `ollama run llama3.1 --verbose` gives prompt eval **35.8 tok/s** and generation **7.8 tok/s**. `ollama ps` shows **100% CPU**. Reported by the coordinator on 2026-09-11.
- **Install:** the Ollama install contains `lib\ollama\vulkan\ggml-vulkan.dll` and `lib\ollama\rocm_v7_1\ggml-hip.dll`.
- **`%LOCALAPPDATA%\Ollama\server.log`, 2026-09-09:**
  - `msg="dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1" id=0 library=Vulkan compute=0.0 name=Vulkan0 description="AMD Radeon(TM) 860M Graphics"`
  - `inference compute ... library=cpu ... total="31.2 GiB" available="15.2 GiB"`
- **Cost per turn [inference]:** at the measured rates, a 4,000-token tool result takes about 112 s of prefill. A 500-token reply takes about 64 s. That is roughly 3 minutes per agent turn on CPU.

### (a) Can Ollama use the Radeon 860M?

- **Vulkan:** *"Vulkan is enabled by default when the backend is installed"* on Windows and Linux ([GPU docs](https://docs.ollama.com/gpu)). It was opt-in when it was introduced in v0.12.11 (2025-11-12, [release](https://github.com/ollama/ollama/releases/tag/v0.12.11)).
- **ROCm on Windows:** covers only Radeon RX 7000 and PRO W7000 cards with a ROCm v7 driver stack. The 860M is not listed ([GPU docs](https://docs.ollama.com/gpu)).
- **iGPU gate:** `OLLAMA_IGPU_ENABLE`, described as "Enable integrated GPUs" ([envconfig/config.go](https://github.com/ollama/ollama/blob/main/envconfig/config.go)). v0.30.2 (2026-06-03) states *"Radeon 8060S integrated GPUs are now allowed by default"* ([releases](https://github.com/ollama/ollama/releases)). Other iGPUs, including the 860M per the log above, are dropped unless you opt in.
- **Documented speedup for the 860M:** **none** from Ollama or AMD.
- **Nearest community measurements (not this GPU):**
  - Radeon 780M, llama.cpp Vulkan on Linux, Gemma-4-26B-A4B Q4_K_M: pp about 209, tg about 25 tok/s ([llama.cpp discussion #24222](https://github.com/ggml-org/llama.cpp/discussions/24222), 2026-06). The 780M is not the 860M, and the OS is Linux.
  - Radeon 890M: Qwen3-8B Q4_K_M 9.9-13.4 tok/s, gpt-oss-20b 23.4 tok/s [secondary: [blog](https://msf.github.io/blogpost/local-llm-performance-framework13.html)].
- **Where the gain would be [inference]:** an iGPU shares system RAM, so token generation stays bound by memory bandwidth. The larger gain is expected in prompt processing, which is exactly the agent-loop bottleneck.
- **Measured on this machine, 2026-09-11.** Setup:
  - The same `/api/generate` call went to two Ollama 0.33.3 servers: the default one on CPU, and a second with `OLLAMA_IGPU_ENABLE=1`. On the second, Vulkan picked up the 860M with 16.1 GiB shared, and `ollama ps` reported 100% GPU.
  - Model: `llama3.1` 8B. Input: a 2,356-token prompt (10k characters of TRAINER.md). Settings: `num_ctx` 8192, 150 generated tokens, temperature 0.
  - ROCm was dropped (`gfx1152` has no rocblas target).

  | backend | prompt eval | generation | one turn (prompt + 150 tokens) |
  |---|---|---|---|
  | CPU | 38.2 tok/s (61.6 s) | 6.7 tok/s (22.3 s) | ~84 s |
  | Vulkan iGPU | **63.9 tok/s** (36.9 s) | **8.1 tok/s** (18.4 s) | ~55 s |

  The iGPU is worth enabling: 1.7x on prompt eval, 1.2x on generation. It does not make a dense 8B model fast.

  **`gpt-oss:20b` on the same test and iGPU:**
  - Prompt eval **140.1 tok/s**, generation **11.6 tok/s**.
  - 12 GB loaded, 100% GPU, 19.7 s cold load.

  **Planner probe, same day, on the same setup:**
  - *Setup:*
    - The real `PLANNER` tool surface, `agent.PLANNING`, `think: low`, `num_ctx` 16384.
    - The request: 45 min, dumbbell, chest/shoulders/arms.
    - The existing `plan.validate`, with one retry that fed the refusal back to the model.
  - *Turn 1:* called `admissible_set`, 32 s. The result was **12,061 chars** (about 4k tokens).
  - *Turn 2:* called `allocate`, 38 s. It re-evaluated all 6,371 prompt tokens, so the prefix cache missed.
  - *Turn 3:* no tool call, but **1,044 generated tokens (92 s)** of prose before the emission was requested.
  - *Emit 1:* 74 s, another cache miss at 5,289 tokens. **Refused**: `Dumbbell_Curl` is not a catalog id. The planner door hides `name`, and the model invented a plausible id.
  - *Outcome:* about **4 minutes to a refused plan**. The OS then killed both the Ollama server and the probe for low memory, during the retry. 17 GB was free once both were gone. A 12 GB model plus a 16k context is at the edge of this 32 GB laptop with normal apps open.
  - *Levers this points at [inference]:*
    - make the tool results compact;
    - keep the history byte-stable, so the prefix cache hits;
    - build the emit schema's `exercise_id` as an enum of today's admissible ids, so constrained decoding cannot produce an invented id;
    - send the validator's feedback back to the model;
    - run asynchronously, so no one waits on the minutes.

  **Planner graph probe, same evening (ticket 6.1):**
  - *Setup:*
    - The LangGraph planner (`trainer.coach.planner`) on `gpt-oss:20b`, `reasoning: low`, a 16384 context set on the server, 12 GB loaded at 100% GPU.
    - The emit schema holds `exercise_id` to today's admissible ids. A refusal goes back to the planner, up to 3 attempts.
    - `python -m trainer.coach.probe`: one run per situation in `evaluation.py`, heavy apps closed.

  | situation | outcome | attempts | tool calls | wall time |
  |---|---|---|---|---|
  | no-equipment | valid | 1 | 2 | 299 s |
  | half-refused | valid | 2 | 2 | 313 s |
  | contradictory | refused | 3 | 2 | 474 s |
  | no-history | refused | 3 | 1 | 454 s |
  | refused, the plan turned down | valid | 1 | 2 | 89 s |
  | refused | valid | 3 | 3 | 576 s |
  | preference-against-the-split | valid | 1 | 1 | 84 s |

  - *Outcome:* 4 of 6 valid, 38 min in all. No invented id: the enum held.
  - *Refusals fed back:* 7, and 2 runs recovered from them.
    - 5 were the clock, 1-12 min over a 30 min budget.
    - 1 was a duplicate exercise, 1 a preference prescribed without `despite`.
    - `contradictory` still ended over the clock. `no-history` ended on a `despite` naming exercises nobody refused.
  - *Memory:* 12 GB loaded, as Ollama's `/api/ps` reports it, and free system memory fell to 1.9 GiB. Ollama's working set reads 0.1 GiB, because on the iGPU the weights sit in shared memory.
  - *Studio, same evening:* 45 min, dumbbell, chest/shoulders/arms through `langgraph dev`. Valid at the first attempt, 1 tool call, 182 s.

  **Second probe, 2026-09-12 (ticket 6.3), with every violation fed back at once:**
  - Four situations ran before Windows killed the probe for low memory: `no-equipment` valid at the first attempt (118 s), `half-refused` at the third (257 s), `contradictory` at the second (300 s), `no-history` at the second (234 s). The first plan of `refused` was valid in 59 s.
  - Both of the situations the first probe ended refused now reach a valid plan. `no-history` was refused once on the clock **and** an invented `despite` together, and fixed both in one attempt.
  - One refusal was a document that is not a plan: `despite` written onto the items, where the shape puts it on the plan.
  - Per node, from the run records: emit 40-62 s, a planner turn 9-88 s, validate 0.01 s. The clock is the model's, not the engine's.

### (b) Other runtimes on this hardware

| Runtime | Uses the 860M or NPU | OpenAI-compatible API | Tool calling | Structured output |
|---|---|---|---|---|
| llama.cpp (`llama-server`) | Vulkan: `llama-bXXXX-bin-win-vulkan-x64.zip` is shipped ([releases API](https://api.github.com/repos/ggml-org/llama.cpp/releases), b10903) | Yes | Yes with `--jinja` ([docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)) | GBNF / JSON schema |
| LM Studio | Runs llama.cpp. The official system requirements do not mention AMD or Vulkan ([docs](https://lmstudio.ai/docs/app/system-requirements)), so iGPU use is **unverified from a primary source** | Yes | Yes: native for some models, "default" prompt-based for others ([tools](https://lmstudio.ai/docs/developer/openai-compat/tools)) | JSON schema via llama.cpp grammar. *"Not all models are capable ... particularly LLMs below 7B"* ([structured output](https://lmstudio.ai/docs/developer/openai-compat/structured-output)) |
| AMD Lemonade Server | Backends `llamacpp` (Vulkan/ROCm), `flm` (NPU) and `ryzenai-llm` (XDNA2 NPU). Windows 11 and Linux. Apache-2.0 ([repo](https://github.com/lemonade-sdk/lemonade)) | Yes, port 13305; also Ollama- and Anthropic-compatible | `tools` documented on `/v1/chat/completions` ([API](https://lemonade-server.ai/docs/api/openai/)) | No `response_format` documented for chat |
| AMD ryzenai-server (Ryzen AI SW) | Hybrid NPU+iGPU, NPU-only or CPU on Ryzen AI 300/400. 16 GB minimum, 32 GB recommended. MIT source, AMD EULA on the DLLs ([repo](https://github.com/lemonade-sdk/ryzenai-server)) | Yes | Yes: "OpenAI-compatible function calling support" | Not documented |

AMD Ryzen AI Software 1.8.0 supports NPU and hybrid execution on Ryzen AI 300 (Strix/Krackan Point). Its listed architectures are Llama-2/3, Mistral, DeepSeek Distill, Qwen-2/2.5/3, Gemma-2 and Phi-3/3.5/4, as pre-converted ONNX, with no TPS figures in the doc ([LLM overview](https://ryzenai.docs.amd.com/en/latest/llm/overview.html)). The Ryzen AI 7 350 being Krackan Point, with an 8-core Radeon 860M and a 50 TOPS XDNA 2 NPU, is [secondary: [LaptopMedia](https://laptopmedia.com/processor/amd-ryzen-ai-7-350/)]; AMD's product page timed out.

### (c) Tool-calling models realistic at usable speed here [inference]

- **Dense 8B:** at the measured 7.8 tok/s on CPU, it is too slow for a multi-turn loop.
- **Best fit is MoE with about 3-4B active parameters.** Decode cost tracks active parameters, while quality tracks total parameters (the model card figures above).
  - **`gpt-oss:20b`:** 3.6B active, 14 GB, tools. The strongest candidate that fits comfortably.
  - **`gemma4:26b`:** A4B, 19 GB, Tau2 68.2.
  - **`qwen3.6:35b`:** A3B, 23 GB, TAU3 67.2.
  - **RAM caveat:** the 19-23 GB models are tight, because the log showed only 15.2 GiB available at that moment.
- **Small dense fallback:** `qwen3.5:9b` (6.6 GB, self-reported BFCL-V4 66.1) or `qwen3.5:4b` (3.4 GB) for the lighter supervisor role.
- **Context:** set `OLLAMA_CONTEXT_LENGTH` explicitly (16k-64k, as memory allows). The 4k default silently truncates tool results.

---

## 6. Runtime comparison

| Runtime | Status (2026-09) | Models | Tool calling | Constrained / JSON-schema output | Language | License | Published phone speed |
|---|---|---|---|---|---|---|---|
| **LiteRT-LM** | Stable (Kotlin, C++); Swift and JS preview | Gemma 4/3n/3, FunctionGemma, Phi-4-mini, Qwen2.5/3 | **Yes** (Kotlin `@Tool`) | **Yes in C++** (JSON Schema, regex, Lark); Kotlin not documented | Kotlin, C++, Python | Apache-2.0 | Gemma 4 E2B GPU 52 tok/s decode, E4B 22 (S26 Ultra) |
| MediaPipe LLM Inference | **Maintenance-only** | Gemma 3 1B, Gemma 3n, Phi-2 | Via legacy FC SDK | FC SDK constrained | Kotlin | Apache-2.0 | n/p |
| **Gemini Nano (ML Kit Prompt)** | **Beta**; structured output **Alpha**; **listed devices only** | Gemini Nano v2/v3/v4 (system-managed) | **No** | Alpha (`@Generable`) | Kotlin | GenAI API terms | n/p |
| **llama.cpp** | Mature; OpenCL on Adreno 7xx/8xx | Any GGUF | Yes (`--jinja`; `llama.rn`) | Yes (GBNF, JSON schema) | C++, Kotlin sample, RN (`llama.rn`) | MIT | n/p |
| MLC LLM | Active (last push 2026-08-17) | Converted HF models | REST documents `tools` (Android unverified) | `json_object` with optional schema | Java/Kotlin | Apache-2.0 | n/p |
| ExecuTorch | 1.3 docs | Llama 3.x, Qwen 3, Phi-4-mini, LFM2 | Not documented | Not documented | Kotlin/Java | BSD | Llama 3.2 1B 50 tok/s, 3B 20 tok/s (OnePlus 12) |
| Ollama (Termux) | **Unofficial on Android** | Ollama library | Yes (Ollama API) | Yes (`format`) | HTTP from a separate app | MIT (Ollama) | n/p |
| Cactus | Active | Gemma, Qwen, Liquid | Yes | Unverified | Kotlin, RN, Flutter | **Unclear** | iPhone only |

---

## 7. Architecture comparison

| | (a) Thin client + LangGraph server (PC/Ollama or hosted) | (b) Hybrid | (c) Fully on-device |
|---|---|---|---|
| Offline | No (needs LAN or tunnel to the PC) | Partial (single-turn features only) | Yes |
| Latency | Dominated by the PC. Currently about 3 min per turn on CPU (section 5); needs iGPU, an MoE model or a hosted model | Phone nodes fast for short prompts; the rest as (a) | Gemma 4 E2B ~52 tok/s decode on a flagship GPU; mid-range unpublished |
| Battery | Negligible on the phone | Moderate; Nano is quota-limited | High; Nano battery quota exists for a reason |
| Privacy | Stays on the user's PC with Ollama; leaves the network if hosted | Mixed | Best |
| Agent quality | 8B-35B models (BFCL/TAU above) | Phone nodes limited to single-turn, no tools on Nano | 1-4B models: 4-22% BFCL V4 multi-turn |
| LangGraph (checkpointer, store, `interrupt()`, supervisor on a different model) | **All of it, as designed** | Graph on the server; phone node sits outside the checkpointer unless modelled as an interrupt | **Not possible**: no Android wheels, LangGraph.js v1 `async_hooks`; needs a Koog rewrite |
| Portfolio signal | Strong on agentic engineering (graph, HITL over an API, persistence, evals) | Adds an "edge AI" talking point at significant complexity | Shows mobile ML, but abandons the LangGraph story |
| Build cost | Low-medium | High | Very high |

---

## 8. Recommendation for REPS

**Architecture: (a), a thin Android client of a Python LangGraph server running on the PC with Ollama.** It is the only option where every piece the portfolio is meant to show actually runs: StateGraph, the self-correcting planner, `interrupt()`, checkpointer and store, and a supervisor on a different model. The two alternatives are blocked by facts, not preference. LangGraph does not run on Android (section 2), and 1-4B models fail multi-turn tool use (section 4).

### On-device: nothing in the agent loop

- **Allowed:** at most one optional, single-turn, schema-shaped feature that works offline, for example turning a spoken or typed workout report into a JSON set log.
- **Runtime choice:** use LiteRT-LM with Gemma 4 E2B. That model is a 2.6 GB download, so make it an opt-in, not bundled in the APK.
- **Caveats:** constrained decoding is documented for C++ only, so validate on the phone or on the server. ML Kit's Prompt API would work only on listed flagships, and its structured output is alpha.
- **Default:** skip on-device until the server path is solid.

### Concrete stack

- **Server (Python):**
  - `langgraph` (MIT), with a planner node that loops on validator feedback and a separate supervisor graph.
  - Checkpointer on SQLite or Postgres, plus a long-term store.
  - Engine tools from `src/trainer/tools.py`.
  - Served by a small FastAPI app with SSE and resume endpoints. `langgraph dev` is fine during development; avoid depending on the licensed self-hosted Agent Server.
- **Models via Ollama:**
  - Planner: `gpt-oss:20b`, or `gemma4:26b` / `qwen3.6:35b` if RAM allows.
  - Supervisor: a *different* model, e.g. `qwen3.5:9b`. Or keep a hosted OpenAI-compatible endpoint (the existing Groq path) as the supervisor, which also proves the "different model" point.
  - Set `OLLAMA_CONTEXT_LENGTH` explicitly.
  - Structured plan via Ollama `format` with a JSON schema, validated by the engine.
- **PC first:** set `OLLAMA_IGPU_ENABLE=1` and re-measure. If the iGPU does not help, try the llama.cpp Vulkan build or Lemonade and compare tok/s. Both expose OpenAI-compatible tool calling.
- **Client:**
  - Kotlin + Jetpack Compose APK, with an HTTP/SSE client calling the server. There is no Kotlin LangGraph SDK; the API surface is small (threads, runs, stream, resume).
  - Each `interrupt()` payload renders as a native screen (question, exclusion confirmation, plan accept/refuse) and posts the resume value.
  - React Native plus `@langchain/langgraph-sdk` is the alternative if JS is preferred, but needs an SSE workaround.
- **Connectivity:** phone to PC over LAN, or a tunnel (`langgraph dev --tunnel` exists for development).

---

## Sources

- LiteRT-LM repo: https://github.com/google-ai-edge/LiteRT-LM
- LiteRT-LM releases (API): https://api.github.com/repos/google-ai-edge/LiteRT-LM/releases
- LiteRT-LM overview (2026-09-04): https://developers.google.com/edge/litert-lm/overview
- LiteRT-LM constrained decoding (C++): https://github.com/google-ai-edge/LiteRT-LM/blob/main/docs/api/cpp/constrained-decoding.md
- LiteRT-LM Kotlin getting started: https://github.com/google-ai-edge/LiteRT-LM/blob/main/docs/api/kotlin/getting_started.md
- LiteRT-LM issue #1027: https://github.com/google-ai-edge/LiteRT-LM/issues/1027
- Gemma 4 E2B LiteRT-LM card: https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm
- MediaPipe LLM Inference Android (2026-06-12): https://developers.google.com/edge/mediapipe/solutions/genai/llm_inference/android
- AI Edge Function Calling SDK Android: https://developers.google.com/edge/mediapipe/solutions/genai/function_calling/android
- AI Edge Gallery: https://github.com/google-ai-edge/gallery
- Gemini Nano (2026-09-08): https://developer.android.com/ai/gemini-nano
- ML Kit GenAI overview (2026-09-10): https://developers.google.com/ml-kit/genai
- ML Kit Prompt API get started (2026-09-08): https://developers.google.com/ml-kit/genai/prompt/android/get-started
- ML Kit Prompt API: https://developers.google.com/ml-kit/genai/prompt/android
- ML Kit structured output (2026-07-21): https://developers.google.com/ml-kit/genai/prompt/android/structured-output
- ML Kit release notes: https://developers.google.com/ml-kit/release-notes
- Firebase AI Logic hybrid Android (2026-09-10): https://firebase.google.com/docs/ai-logic/hybrid/android/get-started
- Android hybrid inference: https://developer.android.com/ai/hybrid
- llama.cpp Android: https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md
- llama.cpp OpenCL: https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENCL.md
- llama.cpp function calling: https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- llama.cpp releases (API): https://api.github.com/repos/ggml-org/llama.cpp/releases
- llama.cpp discussion #24222: https://github.com/ggml-org/llama.cpp/discussions/24222
- llama.rn: https://github.com/mybigday/llama.rn
- MLC LLM repo: https://github.com/mlc-ai/mlc-llm
- MLC LLM Android: https://llm.mlc.ai/docs/deploy/android.html
- MLC LLM REST: https://llm.mlc.ai/docs/deploy/rest.html
- ExecuTorch repo: https://github.com/pytorch/executorch
- ExecuTorch Android docs 1.3: https://docs.pytorch.org/executorch/stable/llm/llama-demo-android.html
- ExecuTorch Llama README: https://github.com/pytorch/executorch/blob/main/examples/models/llama/README.md
- Termux ollama build.sh: https://github.com/termux/termux-packages/blob/master/packages/ollama/build.sh
- Cactus: https://github.com/cactus-compute/cactus
- Chaquopy #1017: https://github.com/chaquo/chaquopy/issues/1017
- Chaquopy PR #1328: https://github.com/chaquo/chaquopy/pull/1328
- Chaquopy PR #1413: https://github.com/chaquo/chaquopy/pull/1413
- Chaquopy #1007: https://github.com/chaquo/chaquopy/issues/1007
- Chaquopy #975: https://github.com/chaquo/chaquopy/issues/975
- Briefcase #1544: https://github.com/beeware/briefcase/issues/1544
- pydantic #12739: https://github.com/pydantic/pydantic/issues/12739
- PyPI pydantic-core: https://pypi.org/project/pydantic-core/
- PyPI JSON API (langgraph, langgraph-checkpoint, langgraph-sdk, langchain-core, ormsgpack, orjson, uuid-utils, xxhash, jiter): https://pypi.org/pypi/langgraph/json
- android-pydantic-core [secondary]: https://github.com/Eutalix/android-pydantic-core
- langgraphjs #1699: https://github.com/langchain-ai/langgraphjs/issues/1699
- langgraphjs #81: https://github.com/langchain-ai/langgraphjs/issues/81
- docs #1177: https://github.com/langchain-ai/docs/issues/1177
- Koog repo: https://github.com/JetBrains/koog
- Koog CHANGELOG: https://github.com/JetBrains/koog/blob/main/CHANGELOG.md
- Koog 1.0.0: https://github.com/JetBrains/koog/releases/tag/1.0.0
- Koog #262: https://github.com/JetBrains/koog/issues/262
- LangChain4j intro: https://docs.langchain4j.dev/intro/
- LangChain4j #1135: https://github.com/langchain4j/langchain4j/issues/1135
- LangGraph CLI: https://docs.langchain.com/langsmith/cli
- Standalone Agent Server: https://docs.langchain.com/langsmith/deploy-standalone-server
- Self-hosted LangSmith: https://docs.langchain.com/langsmith/self-hosted
- HITL via server API: https://docs.langchain.com/langsmith/add-human-in-the-loop
- LangGraph JS SDK: https://www.npmjs.com/package/@langchain/langgraph-sdk
- LangGraph JS SDK reference: https://docs.langchain.com/langsmith/langgraph-js-ts-sdk
- LangGraph repo: https://github.com/langchain-ai/langgraph
- RN streaming [secondary]: https://getwireai.com/blog/react-native-llm-streaming
- BFCL leaderboard (2026-04-12): https://gorilla.cs.berkeley.edu/leaderboard.html
- BFCL data: https://gorilla.cs.berkeley.edu/data_overall.csv
- Qwen3.5-9B: https://huggingface.co/Qwen/Qwen3.5-9B
- Qwen3.5-4B: https://huggingface.co/Qwen/Qwen3.5-4B
- Qwen3.5-2B: https://huggingface.co/Qwen/Qwen3.5-2B
- Qwen3.6-35B-A3B: https://huggingface.co/Qwen/Qwen3.6-35B-A3B
- Qwen3.8: https://github.com/QwenLM/Qwen3.8
- Gemma 4 model card: https://ai.google.dev/gemma/docs/core/model_card_4
- FunctionGemma model card: https://ai.google.dev/gemma/docs/functiongemma/model_card
- Llama 3.2 3B: https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct
- Phi-4-mini: https://huggingface.co/microsoft/Phi-4-mini-instruct
- gpt-oss-20b: https://huggingface.co/openai/gpt-oss-20b
- Ollama tool calling: https://docs.ollama.com/capabilities/tool-calling
- Ollama structured outputs: https://docs.ollama.com/capabilities/structured-outputs
- Ollama structured outputs blog: https://ollama.com/blog/structured-outputs
- Ollama context length: https://docs.ollama.com/context-length
- Ollama GPU: https://docs.ollama.com/gpu
- Ollama releases: https://github.com/ollama/ollama/releases
- Ollama v0.12.11: https://github.com/ollama/ollama/releases/tag/v0.12.11
- Ollama envconfig: https://github.com/ollama/ollama/blob/main/envconfig/config.go
- Ollama tools search: https://ollama.com/search?c=tools
- Ollama library qwen3: https://ollama.com/library/qwen3
- Ollama library qwen3.5: https://ollama.com/library/qwen3.5
- Ollama library qwen3.6: https://ollama.com/library/qwen3.6
- Ollama library qwen3.8: https://ollama.com/library/qwen3.8
- Ollama library gemma4: https://ollama.com/library/gemma4
- Ollama library gpt-oss: https://ollama.com/library/gpt-oss
- LM Studio tools: https://lmstudio.ai/docs/developer/openai-compat/tools
- LM Studio structured output: https://lmstudio.ai/docs/developer/openai-compat/structured-output
- LM Studio system requirements: https://lmstudio.ai/docs/app/system-requirements
- Lemonade repo: https://github.com/lemonade-sdk/lemonade
- Lemonade OpenAI API: https://lemonade-server.ai/docs/api/openai/
- ryzenai-server: https://github.com/lemonade-sdk/ryzenai-server
- AMD Ryzen AI LLM overview (1.8.0): https://ryzenai.docs.amd.com/en/latest/llm/overview.html
- Ryzen AI 7 350 specs [secondary]: https://laptopmedia.com/processor/amd-ryzen-ai-7-350/
- Framework 13 / Radeon 890M benchmarks [secondary]: https://msf.github.io/blogpost/local-llm-performance-framework13.html
