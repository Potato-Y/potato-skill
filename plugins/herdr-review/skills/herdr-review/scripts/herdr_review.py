#!/usr/bin/env python3
"""Helpers for the herdr-review skill.

  detect                          latest models per provider
  config [--reviewer LINE ...]    the reviewers to run: --reviewer lines, else the
                                  rule file written by /setup-herdr-review, else defaults
  selftest                        build a tiny repo with one planted bug, for setup tests
  prepare --repo R [--base B --head H] [--exclude GLOB ...]
                                  build a disposable review worktree whose
                                  uncommitted changes are exactly the review target
  cleanup --repo R --worktree W   remove that worktree

All output is JSON on stdout. Stdlib only.
"""
import argparse
import datetime
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")
# Fixed, short root: short paths avoid Windows MAX_PATH failures, and a stable
# worktree path means a reviewer CLI's folder-trust answer is remembered next run.
ROOT = os.path.join(HOME, ".herdr-review")

# Files never handed to an outside model. Matched against the basename, case-insensitive.
SECRET_GLOBS = [
    ".env", ".env.*", "*.env", "*.pem", "*.key", "*.pfx", "*.p12", "*.keystore",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", "*secret*", "*credential*", ".npmrc", ".pypirc",
]

# Written by /setup-herdr-review. One reviewer per line: "<cli> <model> <effort>: <skill>".
RULE_FILE = os.path.join(HOME, ".claude", "rules", "herdr-review.md")
RULE_LINE = re.compile(r"(\w+)\s+(\S+)\s+(\S+)\s*:\s*(.+)")
# Each CLI's own review command, used for the skill value "provider".
PROVIDER_REVIEW = {"claude": "/code-review high", "codex": "/review", "grok": "/review --local"}
SKILL_NAME = re.compile(r"[\w.-]+(:[\w.-]+)?")  # "my-review" or "plugin:my-review"


def git(repo, *args, text=True, check=True):
    r = subprocess.run(["git", "-c", "core.longpaths=true", "-c", "core.quotepath=false", *args],
                       cwd=repo, capture_output=True, text=text, encoding="utf-8" if text else None)
    if check and r.returncode != 0:
        err = r.stderr if text else r.stderr.decode("utf-8", "replace")
        fail(f"git {' '.join(args)} failed: {err.strip()}")
    return r.stdout


def fail(msg):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def is_secret(path, extra):
    name = os.path.basename(path).lower()
    return any(fnmatch.fnmatch(name, g.lower()) for g in SECRET_GLOBS) or \
        any(fnmatch.fnmatch(path.lower(), g.lower()) for g in extra)


def version_key(slug):
    return [int(n) for n in re.findall(r"\d+", slug)]


def detect(_args):
    print(json.dumps(detect_info(), ensure_ascii=False))


def detect_info():
    out = {"codex": None, "grok": None, "claude": "opus"}
    try:
        c = json.load(open(os.path.join(HOME, ".codex", "models_cache.json"), encoding="utf-8"))
        sols = [m["slug"] for m in c.get("models", [])
                if m.get("visibility") == "list" and m["slug"].endswith("-sol")]
        out["codex"] = max(sols, key=version_key) if sols else None
    except (OSError, ValueError, KeyError):
        pass
    try:
        g = json.load(open(os.path.join(HOME, ".grok", "models_cache.json"), encoding="utf-8"))
        # plain "grok-X.Y" only: variants like "-build-fast" are not the flagship
        names = [k for k, v in g.get("models", {}).items()
                 if re.fullmatch(r"grok-[\d.]+", k) and not v.get("info", {}).get("hidden")]
        out["grok"] = max(names, key=version_key) if names else None
    except (OSError, ValueError, AttributeError):
        pass
    return out


def reviewer(cli, model, effort, skill):
    """One reviewer entry: what to launch and what its prompt starts with."""
    key = skill
    if cli == "codex" and key.split()[0] == "/review":
        key = "provider"
    if key == "provider":
        line = PROVIDER_REVIEW[cli]
    elif SKILL_NAME.fullmatch(key):  # a skill by name: claude runs it as a command, others are asked in words
        line = f"/{key}" if cli == "claude" else f"Use your {key} skill."
    else:  # a slash command or instruction, sent as typed
        line = key
    q = shlex.quote
    cmd = {"claude": f"claude --model {q(model)} --effort {q(effort)}",
           "codex": f"codex --no-daemon -m {q(model)} -c model_reasoning_effort={q(effort)}",
           "grok": f"grok -m {q(model)} --reasoning-effort {q(effort)}"}[cli]
    out = {"cli": cli, "model": model, "effort": effort, "skill": key, "skill_line": line, "cmd": cmd}
    if (cli, line) == ("codex", "/review"):
        out["picker"] = "Review uncommitted changes"  # the preset to choose on its menu
    return out


def config(args):
    lines, source = args.reviewer, "arguments"
    if not lines and os.path.exists(RULE_FILE):
        lines, source = open(RULE_FILE, encoding="utf-8").read().splitlines(), RULE_FILE
    out, errors = [], []
    if lines:
        for raw in lines:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            m = RULE_LINE.fullmatch(s)
            if not m or m.group(1) not in ("claude", "codex", "grok"):
                errors.append(f"not '<claude|codex|grok> <model> <effort>: <skill>': {s}")
                continue
            out.append(reviewer(*m.groups()))
    else:
        source, d = "defaults", detect_info()
        for cli, model, effort in (("codex", d["codex"], "high"), ("grok", d["grok"], "medium"),
                                   ("claude", "opus", "high")):
            if model:
                out.append(reviewer(cli, model, effort, "provider"))
            else:
                errors.append(f"{cli}: no model detected; name one")
    seen = {}
    for r in out:
        label = f"{r['cli']}-{r['model']}"
        seen[label] = seen.get(label, 0) + 1
        r["label"] = label if seen[label] == 1 else f"{label}-{seen[label]}"
        r["terminal"] = "rv-" + re.sub(r"[^A-Za-z0-9-]", "-", r["label"])
    print(json.dumps({"source": source.replace("\\", "/"), "reviewers": out, "errors": errors},
                     ensure_ascii=False))


def selftest(_args):
    """A tiny repo whose uncommitted change has one obvious bug (IndexError on every call)."""
    repo = os.path.join(ROOT, "selftest", "herdr-selftest")
    shutil.rmtree(repo, ignore_errors=True)
    os.makedirs(repo)
    src = os.path.join(repo, "items.py")
    with open(src, "w", encoding="utf-8", newline="\n") as f:
        f.write('def last_item(items):\n    """Return the last element of a non-empty list."""\n'
                '    return items[-1]\n')
    git(repo, "init", "-q")
    git(repo, "add", "items.py")
    git(repo, "-c", "user.name=herdr-review", "-c", "user.email=herdr-review@localhost",
        "commit", "-q", "-m", "add last_item")
    with open(src, "w", encoding="utf-8", newline="\n") as f:
        f.write('def last_item(items):\n    """Return the last element of a non-empty list."""\n'
                '    return items[len(items)]\n')
    print(json.dumps({"repo": repo.replace("\\", "/"),
                      "planted_bug": "items.py:3 indexes items[len(items)], so every call raises IndexError"}))


def prepare(args):
    repo = git(args.repo, "rev-parse", "--show-toplevel").strip()
    name = os.path.basename(repo)
    if args.base and args.head:
        mode = "range"
        base = git(repo, "rev-parse", "--verify", args.base + "^{commit}").strip()
        head = git(repo, "rev-parse", "--verify", args.head + "^{commit}").strip()
    elif args.base or args.head:
        fail("pass both --base and --head, or neither")
    elif git(repo, "status", "--porcelain"):
        mode, base, head = "uncommitted", git(repo, "rev-parse", "HEAD").strip(), None
    else:
        mode, head = "last-commit", git(repo, "rev-parse", "HEAD").strip()
        # shortcut: a root commit (no parent) is not supported; review it with an explicit range instead
        base = git(repo, "rev-parse", "--verify", "HEAD~1").strip()

    # --no-renames: a rename becomes delete+add, so both paths survive the per-path filter
    diff_args = ["diff", "--binary", "--no-color", "--no-renames", base] + ([head] if head else [])
    changed = [p for p in git(repo, *diff_args, "--name-only").splitlines() if p]
    untracked = []
    if mode == "uncommitted":
        untracked = [p for p in git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p]

    excluded = sorted({p for p in changed + untracked if is_secret(p, args.exclude)})
    keep = [p for p in changed if p not in excluded]
    keep_untracked = [p for p in untracked if p not in excluded]
    if not keep and not keep_untracked:
        fail("nothing left to review" + (f" after excluding {excluded}" if excluded else ""))

    wt = os.path.join(ROOT, "wt", name)
    reports = os.path.join(ROOT, "reports", f"{name}-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    # A worktree left at our fixed path belongs to an earlier run of this skill; reclaim it.
    if os.path.exists(wt):
        git(repo, "worktree", "remove", "--force", wt, check=False)
        shutil.rmtree(wt, ignore_errors=True)
    git(repo, "worktree", "prune")
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    os.makedirs(reports, exist_ok=True)
    git(repo, "worktree", "add", "--detach", wt, base)
    git(wt, "config", "core.longpaths", "true")

    if keep:
        patch = git(repo, *diff_args, "--", *keep, text=False)
        r = subprocess.run(["git", "apply", "--binary", "--whitespace=nowarn"], cwd=wt, input=patch,
                           capture_output=True)
        if r.returncode != 0:
            fail("git apply failed: " + r.stderr.decode("utf-8", "replace").strip())
    for p in keep_untracked:
        dst = os.path.join(wt, p)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(repo, p), dst)

    print(json.dumps({
        "repo": repo, "mode": mode, "base": base, "head": head or "working tree",
        "worktree": wt.replace("\\", "/"), "reports": reports.replace("\\", "/"),
        "files": keep + keep_untracked, "excluded": excluded,
    }, ensure_ascii=False))


def cleanup(args):
    wt = os.path.abspath(args.worktree)
    if not os.path.normcase(wt).startswith(os.path.normcase(os.path.join(ROOT, "wt"))):
        fail(f"refusing to remove {wt}: not under {os.path.join(ROOT, 'wt')}")
    git(args.repo, "worktree", "remove", "--force", wt, check=False)
    shutil.rmtree(wt, ignore_errors=True)
    git(args.repo, "worktree", "prune")
    left = [l for l in git(args.repo, "worktree", "list", "--porcelain").splitlines()
            if l.startswith("worktree ") and os.path.normcase(os.path.abspath(l[9:])) == os.path.normcase(wt)]
    print(json.dumps({"removed": not os.path.exists(wt) and not left, "worktree": wt.replace("\\", "/")}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect")
    sub.add_parser("config").add_argument(
        "--reviewer", action="append", default=[], help="'<cli> <model> <effort>: <skill>', overrides the rule file")
    sub.add_parser("selftest")
    p = sub.add_parser("prepare")
    p.add_argument("--repo", required=True)
    p.add_argument("--base")
    p.add_argument("--head")
    p.add_argument("--exclude", action="append", default=[], help="extra path glob to keep away from reviewers")
    c = sub.add_parser("cleanup")
    c.add_argument("--repo", required=True)
    c.add_argument("--worktree", required=True)
    a = ap.parse_args()
    {"detect": detect, "config": config, "selftest": selftest,
     "prepare": prepare, "cleanup": cleanup}[a.cmd](a)


if __name__ == "__main__":
    main()
