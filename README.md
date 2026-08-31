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

See [WALKTHROUGH.md](WALKTHROUGH.md) for the full model and the trace/verdict
mechanics.

## License

MIT — see [LICENSE](LICENSE).
