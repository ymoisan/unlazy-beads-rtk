#!/usr/bin/env python3
"""Render a mermaid flowchart from a beads manifest (JSON array of bead IDs).

Node labels are two lines: an identity line (tier tag · gate badge · WBS · bead
id) over a short, mermaid-safe description derived from the title. Chars that
break mermaid labels (<, >, &, |, ") are neutralised so the diagram never fails
to parse. A leading [w]/[m] tag marks a bead delegated to a worker/mid model
tier; no tag means the lead (controller) runs it.

Edge styling reads at a glance without a legend (shape + colour + weight):
  - parent-child : thin blue, circle head   (parent --o child)   "kin / owns"
  - blocks       : fat red,  arrow head     (blocker ==> blocked)
Only edges whose endpoints are both in the manifest are drawn.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _tiers():
    # {tier_name: entry} for ENABLED tiers, read symlink-safe next to this script.
    p = Path(os.path.realpath(__file__)).parent / "models.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text())
    return {t["name"]: t for t in data.get("tiers", []) if t.get("enabled") and t.get("name")}


def bd_json(args):
    out = subprocess.run(["bd", *args], capture_output=True, text=True)
    txt = out.stdout.strip()
    return json.loads(txt) if txt else []


def sanitize(node_id):
    return "n_" + re.sub(r"[^0-9a-zA-Z]", "_", node_id)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: render_mermaid.py <manifest.beads.json>")
    ids = json.load(open(sys.argv[1]))
    idset = set(ids)

    issues = {i["id"]: i for i in bd_json(["list", "--all", "--json"]) if i["id"] in idset}

    tiers = _tiers()

    def model_tag(nid):
        # [w]/[m] tag for a delegated tier; empty for lead (no model: label).
        for lab in issues.get(nid, {}).get("labels") or []:
            if lab.startswith("model:"):
                name = lab[6:]
                if name in ("lead", "none", ""):
                    return ""
                t = tiers.get(name)
                return f"[{t['tag'] if t else name[:1]}] "
        return ""

    def gate_badge(nid):
        # 🔒 = runnable gate, 👁 = manual (EVIDENCE) gate, none/absent = no badge.
        for lab in issues.get(nid, {}).get("labels") or []:
            if lab == "gate:run":
                return "🔒 "
            if lab == "gate:manual":
                return "👁 "
        return ""

    def wbs_of(nid):
        for lab in issues.get(nid, {}).get("labels") or []:
            if lab.startswith("wbs:"):
                return lab[4:]
        return ""

    def clean(text):
        # Drop the [WBS] title prefix and neutralise chars that break mermaid labels.
        text = re.sub(r"^\[[^\]]*\]\s*", "", text)
        text = text.replace("->", "→").replace("<-", "←")
        text = (text.replace('"', "'").replace("<", "(").replace(">", ")")
                    .replace("&", "+").replace("|", "/"))
        return re.sub(r"\s+", " ", text).strip()

    def subtitle(text, n=48):
        return text if len(text) <= n else text[: n - 1].rstrip() + "…"

    # Two-line node label: identity line (badge · WBS · id) over a short description.
    lines = ["flowchart LR"]
    for nid in ids:
        title = issues.get(nid, {}).get("title") or nid
        wbs = wbs_of(nid)
        ident = f"{model_tag(nid)}{gate_badge(nid)}{wbs + ' · ' if wbs else ''}{nid}"
        lines.append(f'  {sanitize(nid)}["{ident}<br/>{subtitle(clean(title))}"]')

    # Kin (parent-child) = thin blue with a circle head (UML-aggregation feel);
    # blocks = fat red arrow. Shape+colour+weight all differ, so no legend needed.
    KIN = "#2E86DE"
    BLOCK = "#E03131"

    seen = set()
    kin_idx, block_idx = [], []
    edge_no = 0
    for nid in ids:
        for dep in bd_json(["dep", "list", nid, "--json"]):
            src = dep.get("id")
            dtype = dep.get("dependency_type")
            if src not in idset:
                continue
            key = (src, nid, dtype)
            if key in seen:
                continue
            seen.add(key)
            if dtype == "parent-child":
                lines.append(f"  {sanitize(src)} --o {sanitize(nid)}")
                kin_idx.append(edge_no)
                edge_no += 1
            elif dtype == "blocks":
                lines.append(f"  {sanitize(src)} ==> {sanitize(nid)}")
                block_idx.append(edge_no)
                edge_no += 1

    if kin_idx:
        lines.append(f"  linkStyle {','.join(map(str, kin_idx))} stroke:{KIN},stroke-width:1.5px")
    if block_idx:
        lines.append(f"  linkStyle {','.join(map(str, block_idx))} stroke:{BLOCK},stroke-width:3px")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
