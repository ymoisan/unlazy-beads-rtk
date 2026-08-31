# Gates: <BEAD-ID>

BEAD: <BEAD-ID>
OWNS: <repository-relative globs this leaf may write, e.g. src/api/**, tests/api/**>

Scope: <one sentence naming the complete deliverable this bead represents>

<!--
One gate per independently observable outcome. Keep leaf <-> gate 1:1.
A runnable gate needs BOTH an indented CHECK: and EXPECT:. A manual gate has
neither (only EVIDENCE). Success = process exit 0 AND EXPECT matches output.
Make EXPECT a success-only marker printed only after every assertion passes;
never copy a supplied number in as its own proof.

Route CHECK commands through rtk where a wrapper exists, and write `rtk`
explicitly (its rewrite hook does not fire under Copilot/Cursor). Approvals
bind the exact command string, so keep the rtk-vs-raw choice stable.

Per-repo CHECK conventions:
  Monorepo (Rush)  CHECK: rushx test        or  rush build
  Rust repos       CHECK: rtk cargo test <target>
  JS repos         CHECK: rtk npm test      or  rtk vitest run
-->

- [ ] G1: <observable outcome measured directly from the artifact>
  CHECK: rtk cargo test <target>
  EXPECT: test result: ok
  EVIDENCE: pending

- [ ] G2: <outcome that runs in a subproject>
  CHECK: rushx test
  EXPECT: Tests:  <N> passed
  CWD: packages/<name>
  EVIDENCE: pending

- [ ] G3: <manual outcome no command can decide>
  EVIDENCE: pending

<!--
If a gate becomes genuinely impossible, keep it and add:

    ABANDON: G<n> <non-empty reason and handoff>

Surface every abandonment as a non-successful handoff. Do not close the bead
(`gate <BEAD-ID> --close`) while any gate is unmet, abandoned, or pending.
-->
