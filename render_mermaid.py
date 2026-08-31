#!/usr/bin/env python3
"""Render a mermaid flowchart from a beads manifest (JSON array of bead IDs).

Edge styling reads at a glance without a legend (shape + colour + weight):
  - parent-child : thin blue, circle head   (parent --o child)   "kin / owns"
  - blocks       : fat red,  arrow head     (blocker ==> blocked)
Only edges whose endpoints are both in the manifest are drawn.
"""
import json
import re
import subprocess
import sys


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

    titles = {i["id"]: i.get("title", "") for i in bd_json(["list", "--all", "--json"]) if i["id"] in idset}

    lines = ["flowchart LR"]
    for nid in ids:
        label = titles.get(nid, nid).replace('"', "'")
        lines.append(f'  {sanitize(nid)}["{nid}: {label}"]')

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
