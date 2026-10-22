# Repository instructions

These instructions apply to the entire repository.

## Documentation first and documentation sync

Documentation is the primary source for approved architectural decisions,
public contracts, component ownership, and project status. Historical task
documents remain evidence of their original scope, but do not override newer
approved decision and status documents.

Before every substantial development task:

1. Read the current documentation relevant to the affected components and
   compare it with the actual code and tests.
2. Record and resolve any material conflict before implementing work that
   depends on the disputed assumption. Do not silently assume either code or
   documentation is correct.
3. Do not derive new work from superseded task descriptions or historical
   contracts when a newer approved decision exists.

During implementation:

1. Update documentation in the same change as any modification to architecture,
   public data contracts, component ownership, persistence, or supported
   deployment behavior.
2. Propose and obtain approval for a new material architectural decision before
   implementing it.
3. Keep status explicit: distinguish **IMPLEMENTED**, **ACCEPTED/TARGET**,
   **PROPOSED**, **ABSENT**, and **UNVERIFIED** claims and provide evidence where
   appropriate.
4. Preserve public workspace contracts and processor ownership unless the task
   explicitly includes an approved compatibility change.

Before completing a substantial milestone:

1. Synchronize the relevant `STATUS.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
   `ROADMAP.md`, and user documentation with the behavior actually delivered.
2. Verify documentation links, configuration examples, startup commands, and
   claims about implemented behavior.
3. Include a code-versus-documentation consistency check in the final
   verification. A milestone is incomplete while its material behavior is not
   documented.

Keep documentation changes proportional. CSS-only fixes, typo corrections, and
internal refactors with no behavioral or ownership impact do not require broad
architecture-document rewrites.

Documentation must describe actual state, not present planned or incomplete
work as implemented.
