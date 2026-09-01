# unlazy-beads-rtk

A small **AI tooling repo**: clone it once, it bootstraps an AI coding
environment (completion gates + durable traces + token-lean tooling), then you
point it at your actual project repos.

It wires together three ideas:

- **beads (`bd`)** — durable, dependency-aware issue tracking backed by Dolt.
  You install and configure beads yourself; beads owns Dolt (embedded or
  server, your choice). This repo never installs or manages Dolt.
- **unlazy gates** — a bead cannot be closed until its acceptance CHECK passes,
  enforced by a Stop hook / session-start doctor so "half-done" can't slip through.
  This is the part this repo provides.
- **rtk** — an optional token-optimized CLI wrapper used for heavy commands.

> Status: works today as a **VS Code / Copilot**-oriented toolkit. The core
> scripts are tool-agnostic shell; the VS Code wiring lives in a thin install
> layer so other tools (Copilot CLI, Claude Code, Codex) can be adapted later.

## Which runner? (why VS Code / Copilot caps out)

This repo runs today under **VS Code / Copilot**, but that is the *least*
automatable host for beads — worth knowing before you invest in heavy-duty,
many-agent workflows, which it **cannot** do.

**What stock VS Code / Copilot *can* do** — no CLI, no MCP, all local and
policy-friendly:

- Run the shell tools (`gate`, `hook-doctor`, `stale-beads`) in the integrated
  terminal, plus the **git-native devlog hooks** that fire on every `git commit`.
  None of this needs a server, MCP, or elevated permissions.
- Drive beads from an agent-mode session — the agent can loop `bd create` /
  `--claim` / `bd close` and run `gate <id> --close` within one conversation.
- Bake the discipline into `copilot-instructions.md` / `AGENTS.md` so the agent
  *self-runs* `hook-doctor` at session start and `gate --close` before closing —
  a prompt-level stand-in for the Stop hook it can't fire.

**What it *can't* do:**

- **Stop hooks don't execute**, so there's no fail-closed "you can't stop with an
  unmet gate" enforcement — only the pull-based `hook-doctor` you invoke.
- It's a **single interactive session**, not a headless orchestrator. The
  many-agents-draining-a-ready-queue pattern (parallel claims across worktrees,
  hooks firing between steps) isn't reachable here.

**What a CLI runner unlocks** — Claude Code, Codex CLI, Copilot CLI:

- They **execute Stop hooks**, so the gate becomes real fail-closed enforcement.
- They run **headless and in parallel**, so multiple agents can fan out against
  beads' dependency-aware ready queue (`bd ready` → claim → close, in a loop).
  This is the "beads at scale" automation you may have seen from heavy users.
- beads is **runner-agnostic** — the automation ceiling is set by the *runner*,
  not by beads or this repo. Point a CLI runner at the same `.beads/` and the
  fleet tier opens up, gates and all.

**Org reality.** Many orgs disable Copilot-CLI, MCP, and similar, leaving you on
stock VS Code / Copilot. If that's you, the fleet tier is out of reach — but the
combination above (git hooks + shell scripts + strong custom instructions) is a
real step up from unstructured chat, and every piece is local and
policy-friendly. The adapter seam is deliberately thin, so the day your
toolchain allows a CLI runner, the same `.beads/` and gates carry over unchanged.

## Usage at a glance

Two independent halves — pick per project:

| | **Full usage** | **Light usage** |
|---|---|---|
| Track work as beads | ✅ | ✅ |
| Commit trailer + rolling `.beads/DEVLOG.md` | ✅ | ✅ |
| How a bead closes | `gate <id> --close` — reverifies the acceptance CHECK, then `bd close` **only if it passes** (refuses otherwise) | `bd close <id>` — you close it directly; *you* are the reviewer |
| Stop-hook enforcement (blocks a "done" that isn't) | ✅ *(only where Stop hooks run)* | — |
| Best for | long / agent-driven work | small / chat-only work |

**Nothing ever closes a bead by itself.** Even full usage is *you* running
`gate --close`; the automation is a *verified* close, not a *background* one.

**Seeing when to intervene is pull, not push.** The only push is the Stop hook
firing — and that fires only in runners that execute Stop hooks (Claude Code,
Codex), **not VS Code / Copilot**. Everywhere else you poll: run `hook-doctor`
at session start (armed / heartbeat / stale beads / unmet gates), plus
`bd ready` / `bd list --status in_progress`. Treat it like a manual daemon you
check periodically.

## Layout

| Path | Role |
|------|------|
| `gate`, `hooks/stop-gate` | enforce a bead's acceptance CHECK before close / at session end |
| `hook-doctor` | session-start health report (armed / heartbeat / verdict) |
| `stale-beads` | list in-progress beads older than `UNLAZY_STALE_HOURS` |
| `install-stop-hook` | arm/disarm the Stop hook + user commands (VS Code adapter) |
| `install-devlog-hooks`, `hooks/*` | optional git commit-message / devlog hooks |
| `GATES.template.md` | starting point for a project's gate policy |
| `WALKTHROUGH.md` | the deep-dive: how gates, the Stop hook, and the doctor fit together |
| `env.sh.example` | copy to `env.sh` (git-ignored) to set `UNLAZY_HOME` |

Machine-specific, generated files (`env.sh`, `agent-hooks.json`, runtime state
under `~/.unlazy/`) are git-ignored and never committed.

## Prerequisites

You provide these; this repo does **not** install them:

| Prerequisite | Required? | Notes |
|--------------|-----------|-------|
| **beads (`bd`)** on `PATH` | required | Installing beads includes **Dolt**. Configure the Dolt mode you want (embedded / `sql-server`) via beads — this repo just talks to whatever `bd` you set up. |
| **unlazy** (this repo) | required | The gate + trace machinery. Nothing to install beyond cloning and `install-stop-hook`. |
| **rtk** | optional | Token-lean command wrapper. If absent, call the underlying commands directly. |
| **Archify** | optional (docs only) | Only to *regenerate* the diagrams under `docs/architecture/`. Install as a skill: `npx skills add tt-a1i/archify -g`. Readers need nothing — the generated HTML is committed and self-contained. |

## Quick start

```bash
# 1. clone to a stable location
git clone <this-repo> ~/.agents/unlazy-beads-rtk
cd ~/.agents/unlazy-beads-rtk
cp env.sh.example env.sh          # sets UNLAZY_HOME=$HOME

# 2. bootstrap the environment (VS Code / Copilot today)
./install-stop-hook               # arms the Stop hook + symlinks hook-doctor, stale-beads

# 3. in a project repo, initialize beads + a gate policy
cd /path/to/your/project
bd init                           # creates .beads/ (Dolt-backed issue store)
cp ~/.agents/unlazy-beads-rtk/GATES.template.md GATES.md
```

See [WALKTHROUGH.md](WALKTHROUGH.md) for the full model, the trace/verdict
mechanics, and the full-vs-light usage details (§11).

## License

MIT — see [LICENSE](LICENSE).
