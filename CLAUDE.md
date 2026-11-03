@AGENTS.md

# Claude Code Project Context

- **Global Workflow & Engineering Rules:** `~/.config/ai-workflow/GLOBAL_RULES.md` (enforced via `~/.claude/CLAUDE.md`).
- **Mandatory Spec Gate:** Start in Plan Mode. Read `AGENTS.md` and `specs/<change>/spec.md`. Do not write implementation code unless `specs/<change>/spec.md` has `Status: Approved`.
- **Commands:** Resolve all test, lint, typecheck, and build commands from `AGENTS.md` (`## Commands`).
