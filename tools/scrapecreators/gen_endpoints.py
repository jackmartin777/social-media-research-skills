#!/usr/bin/env python3
"""Regenerate endpoints.json from the ScrapeCreators OpenAPI spec.

Usage: python3 gen_endpoints.py [openapi.json | URL]
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

SPEC_URL = "https://docs.scrapecreators.com/openapi.json"


def kebab(segment):
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", segment).replace("_", "-").lower()


def load(src):
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=30) as r:
            return json.load(r)
    return json.loads(Path(src).read_text(encoding="utf-8"))


def build(spec):
    out = {}
    for path, item in spec["paths"].items():
        op = item.get("get")
        if not op:
            continue
        parts = path.strip("/").split("/")
        version, platform, rest = parts[0], parts[1], parts[2:]
        name = "-".join(kebab(p) for p in rest) or "default"
        params = [
            {
                "name": p["name"],
                "required": bool(p.get("required")),
                "description": (p.get("description") or "").strip(),
                "type": (p.get("schema") or {}).get("type", "string"),
            }
            for p in op.get("parameters", [])
            if p.get("in", "query") == "query"
        ]
        entry = {
            "path": path,
            "summary": op.get("summary", ""),
            "description": (op.get("description") or "").strip(),
            "params": params,
        }
        cmds = out.setdefault(platform, {})
        if name in cmds:  # same name under different versions
            name = f"{name}-{version}"
        cmds[name] = entry
    return {p: dict(sorted(c.items())) for p, c in sorted(out.items())}


if __name__ == "__main__":
    data = build(load(sys.argv[1] if len(sys.argv) > 1 else SPEC_URL))
    target = Path(__file__).with_name("endpoints.json")
    target.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {sum(len(v) for v in data.values())} endpoints to {target}")
