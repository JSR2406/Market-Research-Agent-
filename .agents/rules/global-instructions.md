---
name: global-instructions
description: Global engineering instructions for memory, architecture, and constraints
trigger: always_on
---

# Global Instructions

## Default engineering preferences
- Prefer TypeScript, Next.js App Router, Supabase, PostgreSQL, and Tailwind CSS when appropriate.
- Use strict typing and clear module boundaries.
- Use lucide-react for interface icons; do not use emojis as icons.
- Inspect the repository before making architectural decisions.
- Preserve existing behavior unless the user requests a change.
- Run relevant lint, typecheck, test, and build commands after implementation.

## Generalized memory
- Use Mem0 only for durable, useful context.
- Global memory user ID: janmejay_singh-default.
- Project memory user ID: janmejay_singh-<current-workspace-folder>.
- Store cross-project preferences in the global memory scope.
- Store architecture decisions and repository conventions in the project scope.
- Never store API keys, passwords, tokens, private credentials, or secrets.
- Search relevant memory before major architectural changes.
- Do not save temporary assumptions or unverified information.
