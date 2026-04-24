# Next Steps

If I continued the project, these are the first upgrades I would make.

## 1. Prebuilt deterministic artifacts for repeatable exact answers

Right now the model can generate artifacts dynamically, which is flexible, but it also means some artifact experiences can vary from user to user.

The clearest improvement is duty cycle.

Because duty cycle answers come from a verified structured table, I would move duty-cycle artifact generation into deterministic server-side rendering with a prebuilt polished component or HTML template.

That would give:

- the same verified experience for every user
- a more polished artifact because it would be designed once instead of regenerated each time
- less token waste, because the model would not need to rebuild the same calculator repeatedly

I would likely do the same over time for polarity and wiring diagrams and some troubleshooting flows.

## 2. Better long-session memory

Today the backend only forwards the last 10 messages to the model.

That is good for speed and cost, but not ideal for longer support conversations where the user may already have shared:

- material type
- thickness
- wire or rod choice
- gas setup
- prior troubleshooting steps

The next step would be a hybrid memory layer:

- keep recent turns verbatim
- summarize older state
- preserve structured setup facts across the session

## 3. Faster artifact generation

Artifacts are one of the most useful parts of the experience, but also one of the more expensive and variable parts of generation.

The fastest path would be to reduce how often the model has to invent artifact payloads from scratch.

The main directions I would pursue are:

- cache artifacts by deterministic inputs
- render common artifact types directly in application code
- use reusable templates for tables, diagrams, and calculators
- return text immediately and attach heavier artifacts as a second stage when needed

That would improve:

- latency
- consistency
- token efficiency
- polish
