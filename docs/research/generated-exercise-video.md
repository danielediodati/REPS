# Generated exercise video: a multimodal loop, checked by pose

Research date: 2026-09-26. A proposal, to be studied before it reaches ROADMAP.md. It is here for what it shows: generation in a second modality under the same self-correcting loop as the planner.

## The idea

The user asks in the chat, *«mi fai un video dello stacco?»*. The entrance reaches a video graph as a tool (ADR-0006), which generates a clip from the exercise's two photos, start and end (session 16), checks it, and sends it. A clip that passed is kept and served again.

## Decided so far

| | |
|---|---|
| Trigger | the user's request in the chat, never a batch; a clip is generated the first time it is asked for and reused after |
| Input | the exercise's start and end photos as first and last frame; never text alone, which would invent the form |
| Check | pose estimation (e.g. MediaPipe), deterministic: first and last frame within a threshold of the photos; the joints that move are the exercise's `loaded_joints`. Rules, so 100% (ADR-0010); a vision model judging the form may add a declared bar, as a judgement |
| Loop | a LangGraph graph: generate, check, and on a failure the model reads what broke (*«at the last frame the elbow is 40° off the photo»*), rewrites its prompt and generates again, within bounded attempts |
| Scope | the 873 exercises with photos; an exercise found by [exercise discovery](exercise-discovery.md) has none, so later |

## Open

- Which video model takes first and last frame, and what a clip costs.
- The request is ambiguous (*«mi fai un video?»*): the entrance asks which exercise, or takes today's.
- How a clip reaches Telegram, and how long the user waits.
- What a clip that fails every attempt says to the user.
