---
name: herdr-review
description: Multi-model code review through herdr. Runs the reviewer agents configured by /setup-herdr-review (default Codex, Grok and Claude, each with its provider's own review) in hc terminals on a disposable worktree, then verifies their findings, rates them by severity, merges them and cleans up. Use only when the user invokes it.
disable-model-invocation: true
argument-hint: "[target: uncommitted | last commit | <branch> | <A..B> | <path>] [models: e.g. 'codex gpt-6.2-sol, opus'] [skill: provider | <skill name> | /command]"
---

# herdr-review

Several models from different vendors review the same change, each in its own
persistent hc terminal, and you merge what they find. Different models catch
different bugs (in practice one finds an issue all others miss), so the value is
in the union of findings, checked against the real code.

Needs herdr-core's `hc` CLI. Check `hc --version` first; if `hc` is missing,
tell the user to install herdr-core and stop. Then read the manual that ships
with the installed `hc`, once per session before the first `hc` command:
`hc --skill`. It is version-matched, so no separate herdr skill is needed. Use
a POSIX shell (Git Bash on Windows) for the commands below.

Script: `S="<this skill's base directory>/scripts/herdr_review.py"`. Every
subcommand prints JSON.

## 1. Decide target, reviewers and skill

**Target.** What the user named wins. Translate it to `--base`/`--head` revs:
- a branch: `--base $(git merge-base <default-branch> <branch>) --head <branch>`
  (default branch: `git symbolic-ref --short refs/remotes/origin/HEAD`, else `main`)
- a commit `X`: `--base X~1 --head X`; a range `A..B`: `--base A --head B`
- a PR: fetch its head ref, then treat it as a branch
- a path or file subset: build the target as usual, then name the paths in the
  reviewer prompt as the focus

Nothing named: omit both flags. The script reviews uncommitted changes
(staged, unstaged and untracked), or the last commit when the tree is clean.

The repo is the git repo the user is working in. If the working directory holds
several repos and it is unclear which one, ask.

**Reviewers and skill.** Run `python "$S" config`. It returns `reviewers`, one
entry per agent with `cli`, `model`, `effort`, `skill`, `skill_line` (what the
prompt starts with), `cmd` (the launch command before the prompt), `label` and
`terminal`. `source` says where they came from:
- the rule file `~/.claude/rules/herdr-review.md`, written by
  `/setup-herdr-review` after a passing self-test. Tell the user the list.
- `defaults` when there is no rule file: codex newest `*-sol` at high, grok
  newest `grok-X.Y` at medium, claude `opus` at high, each with its CLI's own
  review (`provider`). Mention once that `/setup-herdr-review` can save a
  tested list.

When the user names reviewers for this run, they replace the list: use exactly
those and only those ("opus만" means one reviewer). Rerun with one
`--reviewer "<cli> <model> <effort>: <skill>"` per reviewer. Map a name to its
CLI: `claude-*` and Claude family names (opus, sonnet, haiku, ...) → claude;
`gpt-*` and OpenAI model names → codex; `grok-*` → grok. Use a model id the
CLI lists (`grok models`, `~/.codex/models_cache.json`, claude aliases or
full ids), never a guessed one. Effort: the user's, else the
configured entry for that CLI, else the defaults above. Always pass effort
explicitly: model defaults differ and silently change the comparison. `<skill>`
is `provider` (the CLI's own review: claude `/code-review high`, codex
`/review`, grok `/review --local`), a skill name such as `my-review` or
`plugin:my-review` (claude runs `/<name>`, codex and grok are asked in words to
use that skill), or a literal slash command or instruction. A one-off `--reviewer` is untested, so a failure
there is not a broken config.

Report every line in `errors` to the user and leave those reviewers out. If no
reviewer is left, stop.

## 2. Prepare the worktree

```sh
python "$S" prepare --repo <repo> [--base B --head H] [--exclude 'glob' ...]
```

It creates `~/.herdr-review/wt/<repo-name>` at the base commit and applies the
target there as uncommitted changes. Every reviewer skill reviews "my
uncommitted changes" by default, so all models see exactly the same diff. It
also returns `reports` (a fresh folder for this run), `files`, and `excluded`.

`excluded` lists secret-looking files (`.env*`, keys, `*secret*`,
`*credential*`, ...). They are kept out of the worktree so their contents never
reach an outside model. Tell the user which files were excluded. Add
`--exclude` for other sensitive config the user mentions. If the script says
nothing is left to review, report that and stop.

## 3. Launch reviewers

One `hc run --bg` per reviewer, all with `--cwd <worktree>`. Prefix the
commands with `MSYS_NO_PATHCONV=1`: without it Git Bash rewrites an argument
like `/review` into `C:/Program Files/Git/review`. `$HC_TERMINAL_ID` expands in
your shell to your own address, which is where reports should go.

One prompt per reviewer, starting with its `skill_line` (a slash command must
come first to run as a command):

```sh
P="<skill_line> Scope: the uncommitted changes in this worktree (git diff HEAD plus untracked files)<, focus: paths>. This is a disposable copy of <repo> at <base>. Read-only: do not edit, commit, push, post, or start other agents. Write the report to <reports>/<label>.md: for each finding give file:line, severity, what breaks with a concrete failure scenario, and the fix; end with a verdict and what you did not check. Then run: hc send $HC_TERMINAL_ID \"done <reports>/<label>.md\""

MSYS_NO_PATHCONV=1 hc run --bg --name <terminal> --cwd "$WT" <cmd> "$P"
```

For example `<cmd>` is `codex --no-daemon -m gpt-6.2-sol -c model_reasoning_effort=high`.
Put `MSYS_NO_PATHCONV=1` on the `hc` command only, never `export` it: it also
stops Git Bash from translating `$HOME` paths for `python`.

Only the first prompt of `hc run` and keys typed with `hc keys` arrive as
typed. `hc send` wraps text in `<hc from=...>` tags, so a slash command sent
that way arrives as plain text and does not run.

**A command that opens a menu** (the entry has `picker`, or the test shows a
menu waiting for input). Launch without the prompt
(`hc run --bg --name <terminal> --cwd "$WT" <cmd>`) and handle startup screens
until the prompt is idle. Type the command one key per character, for example
`MSYS_NO_PATHCONV=1 hc keys <t> / r e v i e w enter` (`hc keys --help` names
other keys, such as the one for a space). Read the menu
(`hc read <t> --lines 0`), find the option whose label matches the request
(`picker` names it; with no `picker`, the option for the uncommitted changes,
since that is the review target), move to it with `down`/`up` from the `›`
marker, press `enter`, and read again to confirm the review started. Menus
change between CLI versions, so go by the label, never by a remembered
position. When that review finishes (`hc wait <t>`), send the rest of `$P`
with `hc send`: from "Scope:" on, asking it to write its review to the report
file and send `done`. Only ask the user when no option matches the request.

Check each launch after about 20 seconds (`hc get <t>`, `hc read <t> --lines 0`)
and handle startup screens:
- **Folder trust dialog** (any CLI): auto mode refuses to let you answer these,
  and that is correct, because trusting a folder is the user's call. Show the
  user the exact keys to send themselves, for example
  `! hc keys <t> down enter` (claude), `! hc keys <t> y` (grok) or
  `! hc keys <t> enter` (codex), and continue after they confirm. Trust sticks
  to the fixed worktree path (claude) or the repo root (codex, grok), so this
  is usually a one-time step per repo.
- **Codex "Hooks need review"** (after trusting a folder): `hc keys <t> esc`
  continues without trusting the hooks. Trusting them is the user's call.
- **Codex update notice**: `hc keys <t> esc` skips it.
- **Launch task not delivered** (`first_message.sent: false`): read the
  screen first, since it may still have arrived. A prompt that starts with
  plain words can be sent with `hc send` once the prompt is idle. A prompt that
  starts with a slash command cannot (see above): kill the terminal and launch
  it again.

## 4. Wait and collect

```sh
hc wait --children all --timeout 590
```

Repeat until every reviewer is done. A `reason: message` return means a
`done <path>` report arrived; wait again for the rest. When a reviewer is
`blocked`, read its screen. Grok's own auto-review sometimes blocks the final
`hc send`. If the report file already exists, the review is finished. If a
reviewer wrote no file, take its final answer from `hc read <t> --lines 150`.

## 5. Verify, rate and merge

The reviewer prompt names no severity scale on purpose: a scale handed to
reviewers steers what they look for and how they rate it, and the value of
several models is their independent analysis. You rate the findings, after
reading the results.

Read every report and merge findings that describe the same problem, keeping
every reviewer who found it. A reviewer's own label (critical, P1, important,
nit, or none) is a hint, not the answer: rate each finding by what its failure
scenario does to users.

| Severity | When | Action |
|---|---|---|
| Critical | security hole, data loss or corruption, or breaks most users | fix before merge |
| High | wrong result or failure on a normal path | fix before merge |
| Medium | only under specific conditions (edge input, concurrency), or limited impact | fix now or in a follow-up |
| Low | no behavior impact: naming, readability, maintainability | optional |

Before reporting a finding as Critical, High or Medium, open the cited code and
confirm the failure path yourself. Reviewers are often confidently wrong, and
the user acts on what you report. Label each finding confirmed, refuted (say
why) or unverified; a Low finding may stay unverified. Rate from what you
confirmed, not from the reviewers' labels. When your rating differs from a
reviewer's label, note both so the user sees why.

A problem you find yourself while verifying is a finding too: confirm it the
same way, rate it on the same scale and credit it to `verification`, so the
user sees every issue in one ranking.

Report to the user:
1. The verdict: which confirmed issues need fixing, in one or two sentences,
   then the confirmed counts, for example `Critical 1 · High 2 · Medium 0 · Low 3`.
2. The scope: repo, target mode, files, excluded files, and the
   reviewer/model/effort/skill list.
3. The confirmed findings grouped by severity, Critical first, each group
   headed with its action from the table (for example
   `Critical: fix before merge`). For each finding give `file:line`, who found
   it, the fix, and the failure scenario as short steps (the input, the path
   through the code, what breaks) rather than one long sentence: the user scans
   this section to decide what to fix. Write the rating as the severity alone
   on its own line, with the reason (and any reviewer label that differs) on
   an indented line below it, so the level reads at a glance.
   A refuted claim about the same code or problem goes inside that finding:
   say what was wrong and whether anything still needs fixing, so each issue
   reaches one conclusion in one place.
4. Unverified findings, in their own section.
5. A comparison table with one row per reviewer and fixed columns (verdict,
   findings caught per severity) when two or more reviewers ran. Never add a
   column per finding: the table grows unreadable as findings pile up.
6. What nobody checked (no app run, etc.) and where the reports are
   (`<reports>`; they are kept).
7. Refuted claims that match no finding, last, one line each: `file:line`,
   the reviewer, and why it is wrong.

## 6. Clean up

Always clean up, also when the run fails or is stopped part-way:

```sh
for t in <terminal> ...; do hc kill $t; hc rm $t; done   # every reviewer's `terminal`
python "$S" cleanup --repo <repo> --worktree <worktree>
git -C <repo> worktree list
```

`cleanup` refuses paths outside `~/.herdr-review/wt`. Confirm in your report
that `removed` is true and no `rv-*` terminal is left. Keep the reports folder.
