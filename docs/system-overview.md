# Media pipeline system overview

The implemented system currently has two components: Media Ingest Tool v1 and
Session Grouper v1. Everything else in this overview is explicitly future work.

```text
MEDIA SOURCES
    |
    v
[FUTURE: Media Collector -- NOT IMPLEMENTED]
    external/local source -> collect/download -> provenance -> local inbox
    |
    v
Media Ingest Tool v1 -- IMPLEMENTED
    scan -> content identity -> metadata -> image previews
    |
    v
Standardized media workspace -- IMPLEMENTED
    workspace.json -> metadata/catalog.json -> public asset artifacts
    |
    +--> Session Grouper v1 -- IMPLEMENTED
    |      time-continuity grouping; session is not an event
    |
    +--> FUTURE independent processors -- NOT IMPLEMENTED
           Similarity | Vision | Faces | OCR | Quality | Audio
              |
              v
           FUTURE Knowledge layer -- NOT IMPLEMENTED
              |
              v
           FUTURE Creative layer -- NOT IMPLEMENTED
```

## Stable boundaries

Media Ingest owns source discovery, immutable-original handling, SHA-256 asset
identity, normalized metadata, image previews, and publication of the public
workspace contract. SQLite is private transactional state; JSON is the boundary
between components.

Session Grouper is an independent consumer. It reads only the public JSON
contract and writes only beneath `analysis/session-grouper/`. It groups media by
time continuity but does not infer real-world events.

Each future processor is expected to read public artifacts and own a versioned
namespace under `analysis/<processor>/`. A model, configuration, or processor
version change must produce a distinct result path instead of overwriting old
results. Expensive AI does not belong in ingest.

The future Media Collector has one intended responsibility: move or download
content from an external or local source into a local inbox while preserving
collection provenance. Its API, storage design, and orchestration are not
defined here.

## Architectural decisions

- Originals are immutable input, never processor output.
- `SOURCE` is provenance; `ASSET` is unique SHA-256 content identity.
- Multiple sources may reference one asset and must not duplicate processing.
- Metadata values retain source and timezone provenance.
- SQLite is an internal Media Ingest implementation detail.
- `workspace.json` and referenced JSON artifacts form the public boundary.
- Independent processors do not import Media Ingest internals.
- Processor output belongs only under `analysis/<processor>/`.
- Changed models, recipes, configurations, or semantic versions do not silently
  overwrite older results.
- A session is a probable temporal block, not an identified event.

## What another developer or agent must know before changing this system

Start from [workspace-contract.md](workspace-contract.md), then read the
component document relevant to the change. Do not infer consumer behavior from
SQLite or Python classes. Preserve asset identity and source history, do not
modify originals, retain timestamp provenance, and version any change that
alters artifact meaning. A new processor must stay in its own `analysis/`
namespace. Runtime behavior, public JSON fields, and path semantics require
tests and an explicit compatibility decision; they must not be changed inside a
documentation-only commit.

## Logical milestones

- Media Ingest M1 completion:
  `499baa429021f5fee33205cfdadc1ba3331a0569`
- Public workspace contract:
  `e02e47d6d3578b223c3136f88d574ecf0ebdf750`
- Session Grouper v1 implementation:
  `e2409978cd499488c344c3553bb014d710a974c5`
- Tiled HEIC preview correction:
  `34ffefafcd28318513cd24be78f0ad007f0553a9`
- Capture-time `metadata-v2` correction:
  `1b8b944a08d34a312cc509ec9f25628ff75516aa`
- Session Grouper v1 integration into main:
  `2f525fef984bea8cde64458d24e1134e71b6ebd6`

`main` is the stable integrated checkpoint. Larger components are developed on
feature branches and merged after verification. Commits should represent
logical, tested units. Force push is not part of the normal workflow.
