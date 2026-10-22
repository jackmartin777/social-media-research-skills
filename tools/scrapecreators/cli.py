"""Command line interface: scrapecreators <platform> <command> --param value."""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

from .client import Client, ScrapeCreatorsError

ALIASES = {"x": "twitter", "tt": "tiktok", "ig": "instagram", "yt": "youtube", "fb": "facebook"}
ENDPOINTS_FILE = Path(__file__).with_name("endpoints.json")


def load_endpoints():
    return json.loads(ENDPOINTS_FILE.read_text(encoding="utf-8"))


def find_items(data):
    """Return the biggest list of dicts inside a response (the 'rows')."""
    best = []

    def walk(node):
        nonlocal best
        if isinstance(node, list):
            if node and all(isinstance(i, dict) for i in node) and len(node) > len(best):
                best = node
            for i in node:
                walk(i)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)

    walk(data)
    return best


def flatten(obj, prefix=""):
    flat = {}
    for k, v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(flatten(v, key + "."))
        elif isinstance(v, list):
            flat[key] = json.dumps(v, ensure_ascii=False)
        else:
            flat[key] = v
    return flat


def render(pages, fmt):
    """pages: list of response dicts."""
    if fmt == "json":
        data = pages[0] if len(pages) == 1 else pages
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    items = [i for p in pages for i in (find_items(p) or [p] if isinstance(p, dict) else [])]
    if fmt == "jsonl":
        return "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items)
    rows = [flatten(i) for i in items]
    columns = list(dict.fromkeys(k for r in rows for k in r))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def cmd_list(endpoints, platform=None):
    if platform is None:
        for p, cmds in endpoints.items():
            print(f"{p:<22}{len(cmds)} commands")
        return 0
    platform = resolve_platform(endpoints, platform)
    for name, e in endpoints[platform].items():
        print(f"{name:<34}{e['summary']}")
    return 0


def cmd_describe(endpoints, platform, name):
    e = endpoints[platform][name]
    print(f"{platform} {name}  (GET {e['path']})\n")
    print(e["description"] + "\n")
    for p in e["params"]:
        req = "required" if p["required"] else "optional"
        print(f"  --{p['name']} ({p['type']}, {req}): {p['description']}")
    return 0


def resolve_platform(endpoints, platform):
    platform = ALIASES.get(platform.lower(), platform.lower())
    if platform not in endpoints:
        raise ScrapeCreatorsError(f"Unknown platform '{platform}'. Try: scrapecreators list")
    return platform


def resolve_input_param(spec, name):
    names = [p["name"] for p in spec["params"]]
    if name:
        if name not in names:
            raise ScrapeCreatorsError(f"--input-param '{name}' is not a parameter of this command")
        return name
    required = [p["name"] for p in spec["params"] if p["required"]]
    if not required:
        raise ScrapeCreatorsError("This command has no required param; pass --input-param")
    return required[0]


def read_input(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    values = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    if not values:
        raise ScrapeCreatorsError(f"No values found in {path}")
    return values


def credit_summary(pages):
    charged = sum(p.get("credits_charged", 0) or 0 for p in pages if isinstance(p, dict))
    remaining = [p["credits_remaining"] for p in pages if isinstance(p, dict) and "credits_remaining" in p]
    msg = f"{len(pages)} request(s), {charged} credit(s) charged"
    return msg + (f", {remaining[-1]} remaining" if remaining else "")


def parse_params(extra, spec, preset=None):
    """Turn leftover '--key value' / 'key=value' tokens into a params dict."""
    known = {p["name"]: p["name"] for p in spec["params"]}
    known.update({p["name"].lower().replace("_", "-"): p["name"] for p in spec["params"]})
    params, i = dict(preset or {}), 0
    while i < len(extra):
        tok = extra[i]
        if tok.startswith("--"):
            key, eq, val = tok[2:].partition("=")
            if not eq:
                i += 1
                if i >= len(extra):
                    raise ScrapeCreatorsError(f"Missing value for --{key}")
                val = extra[i]
        elif "=" in tok:
            key, _, val = tok.partition("=")
        else:
            raise ScrapeCreatorsError(f"Unexpected argument '{tok}'. Use --name value.")
        name = known.get(key) or known.get(key.lower().replace("_", "-"))
        if name is None:
            valid = ", ".join(f"--{p['name']}" for p in spec["params"]) or "(none)"
            raise ScrapeCreatorsError(f"Unknown parameter '{key}'. Valid: {valid}")
        params[name] = val
        i += 1
    missing = [p["name"] for p in spec["params"] if p["required"] and p["name"] not in params]
    if missing:
        raise ScrapeCreatorsError("Missing required: " + ", ".join(f"--{m}" for m in missing))
    return params


def build_parser():
    ap = argparse.ArgumentParser(
        prog="scrapecreators",
        description="Scrape public social media data via the ScrapeCreators API.",
        epilog="Examples:\n  scrapecreators list tiktok\n"
        "  scrapecreators describe tiktok profile-videos\n"
        "  scrapecreators tiktok profile --handle charlidamelio\n"
        "  scrapecreators youtube channel-videos --handle MrBeast --all-pages --format csv -o out.csv\n"
        "Platform aliases: " + ", ".join(f"{k}={v}" for k, v in ALIASES.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("target", nargs="+", help="'list [platform]', 'describe <platform> <command>', or '<platform> <command>'")
    ap.add_argument("--format", choices=["json", "jsonl", "csv"], default="json")
    ap.add_argument("-o", "--output", help="write to a file instead of stdout")
    ap.add_argument("--all-pages", action="store_true", help="follow pagination cursors")
    ap.add_argument("--max-pages", type=int, default=10, help="page cap for --all-pages (default 10)")
    ap.add_argument("--input", help="file with one value per line (handles, URLs...); runs the command once per line")
    ap.add_argument("--input-param", help="param the --input values fill (default: the first required param)")
    ap.add_argument("--api-key", help="override SCRAPECREATORS_API_KEY")
    return ap


def main(argv=None, client=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = build_parser()
    args, extra = ap.parse_known_args(argv)
    try:
        endpoints = load_endpoints()
        t = args.target
        if t[0] == "list":
            return cmd_list(endpoints, t[1] if len(t) > 1 else None)
        if len(t) < 2 and t[0] != "describe":
            ap.error("expected: <platform> <command>")
        if t[0] == "describe":
            if len(t) != 3:
                ap.error("expected: describe <platform> <command>")
            platform = resolve_platform(endpoints, t[1])
            if t[2] not in endpoints[platform]:
                raise ScrapeCreatorsError(f"Unknown command '{t[2]}'. Try: scrapecreators list {platform}")
            return cmd_describe(endpoints, platform, t[2])
        platform = resolve_platform(endpoints, t[0])
        if t[1] not in endpoints[platform]:
            raise ScrapeCreatorsError(f"Unknown command '{t[1]}'. Try: scrapecreators list {platform}")
        if len(t) > 2:
            ap.error(f"unexpected argument(s): {' '.join(t[2:])}")
        spec = endpoints[platform][t[1]]
        accepted = {p["name"] for p in spec["params"]}
        values, input_param = [None], None
        if args.input:
            input_param = resolve_input_param(spec, args.input_param)
            values = read_input(args.input)
        params = parse_params(extra, spec, preset={input_param: ""} if input_param else None)
        client = client or Client(api_key=args.api_key)
        pages, failures = [], 0
        if args.all_pages:
            print(f"note: --all-pages fetches up to {args.max_pages} pages per run; each page costs credits.", file=sys.stderr)
        for value in values:
            call = dict(params)
            if input_param:
                call[input_param] = value
            try:
                if args.all_pages:
                    pages.extend(client.paginate(spec["path"], call, args.max_pages, accepted))
                else:
                    pages.append(client.get(spec["path"], call))
            except ScrapeCreatorsError as e:
                if not args.input:
                    raise
                failures += 1
                print(f"error ({value}): {e}", file=sys.stderr)
        text = render(pages, args.format)
        print(credit_summary(pages), file=sys.stderr)
    except ScrapeCreatorsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 1 if failures else 0
