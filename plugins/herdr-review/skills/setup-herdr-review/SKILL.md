---
name: setup-herdr-review
description: Configure which models /herdr-review runs and which review skill each one uses (for example opus with /code-review, grok with its own /review or an installed review skill), prove each choice works with a short real hc review of a planted bug, and save only what passed. Use for /setup-herdr-review, "configure herdr-review", "change the herdr-review reviewers/models/skills", or resetting herdr-review to its defaults.
argument-hint: "[reviewers: e.g. 'opus /code-review, grok provider'] | reset"
---

# Setup herdr-review

Writes `~/.claude/rules/herdr-review.md`: one reviewer per line, in the form
`<cli> <model> <effort>: <skill>`. `/herdr-review` reads it through its script,
so a change applies to the next run. Claude Code also loads it into new
sessions, which is why the file says it is only for `/herdr-review`.

A line is saved only after that exact CLI, model, effort and skill finished a
real review in an hc terminal. The point is that `/herdr-review` never finds
out mid-review that a model id is wrong, a skill is not installed, or a slash
command opens a picker.

This skill ships together with `herdr-review`, which sits beside it:
`H="<this skill's base directory>/../herdr-review"`. If `$H/SKILL.md` is
missing, tell the user to install herdr-review next to this skill and stop.
`S="$H/scripts/herdr_review.py"`, and every subcommand prints JSON. Follow the
`hc` check and manual loading at the top of `$H/SKILL.md` (no separate herdr
skill is needed). Launch, wait and cleanup follow its sections 3, 4 and 6.
Read those sections before the test.

## 1. Current state

Run `python "$S" config` and `python "$S" detect`. `config.source` is the rule
file when one exists, else `defaults`. Show the user the current reviewer list
in the line format. Available models: `detect`, `grok models`, the slugs in
`~/.codex/models_cache.json`, and for claude the aliases
opus/sonnet/haiku/fable or the full ids in `~/.claude/settings.json`.

`reset` as the argument: show the current file, confirm, delete it, run
`python "$S" config` to show the defaults now in effect, and stop.

## 2. Choose the reviewers

Use the reviewers in the argument. Otherwise ask with one AskUserQuestion that
has exactly these two options, and add no others, so every run asks the same
question:
1. **Keep the current list**: the description shows the current lines.
2. **Custom setup**: the description tells the user to type their reviewers
   in the free-text field below (the "Other"/"Type something" entry), one
   reviewer per item, each as model plus optional effort and skill. Example:
   `opus /code-review high, grok-4.7 provider, gpt-6.2-sol high my-review`.
   Skill choices: `provider` (the CLI's own review), the name of an installed
   review skill, or a slash command or instruction. Any omitted part takes
   its default.

If the user picks option 2 without typing anything, ask for the list in plain
text with the same guide. Free text, from either path, is a draft: turn each
reviewer into a line as below, and leave validation to the `config` check and
the self-test.

Turn each reviewer into a line:
- **cli** and **model**: map names as in `$H/SKILL.md` section 1, to a model
  id the CLI lists. For example "opus5.5" means `claude-opus-5-5`, and
  "grok 4.7" means `grok-4.7`.
- **effort**: the user's, else codex `high`, grok `medium`, claude `high`.
- **skill**: `provider` for the CLI's own review, also when none is given. A skill the user installed
  is written as its bare name, without a slash, even when typed with one
  (`/my-review` → `my-review`, a plugin skill as `plugin:my-review`), because
  only claude runs skills as slash commands and the script asks codex and grok
  in words. Anything else, a built-in slash command or an instruction, stays as
  typed.

A command that opens a menu (codex `/review` picks a review preset) is kept
as the user chose it. You operate the menu through hc, choosing the option
that matches the request, as `$H/SKILL.md` section 3 describes. The script
marks the known case with `picker`. An unknown one shows up in the test as a
menu on screen: handle it the same way, and tell the user which option you
chose. Ask only when no option matches the request.

Check the lines with
`python "$S" config --reviewer "<line>" --reviewer "<line>" ...`. Fix each
entry in `errors` with the user. Then show the final lines and confirm before
the test, because the test runs paid agents for a few minutes.

## 3. Self-test

```sh
python "$S" selftest     # -> repo, planted_bug
python "$S" prepare --repo <repo>     # -> worktree, reports
```

The self-test repo has one uncommitted change in `items.py` that makes every
call raise IndexError. Launch every reviewer at once as in herdr-review
section 3, using the `config --reviewer` output from step 2 and its prompt
with this added at the end:

> This is a setup self-test of a one-line change: keep the review short. Start
> the report with the line `skill: <the skill or command you actually ran, or none>`.

Handle startup screens the way section 3 describes. A folder trust dialog
usually appears only on the first test, because the self-test paths are fixed.
Wait as in section 4, for at most two `hc wait` rounds (about 10 minutes).

Grade each reviewer:
- **pass**: `<reports>/<label>.md` exists and is not empty, its `skill:` line
  names the configured skill, and the screen shows no error.
- **fail**: no report, or an error on screen (unknown model, unknown command,
  plugin missing, auth, a picker or prompt waiting for input), or `skill: none`
  or another skill. Quote the relevant lines from `hc read <t> --lines 60`.
- Also note whether the report found the planted IndexError. Missing it is not
  a failure on its own, but tell the user, since it says something about that
  model and skill.

Clean up as in section 6 with the self-test repo and worktree, then remove
the test files: `rm -rf ~/.herdr-review/selftest <reports>`. Do this even when
the test fails or stops part-way.

## 4. Save

Show a table with one row per reviewer: line, pass/fail, the planted bug found,
and the reason for each failure. Write only lines that passed:
- all passed: write them.
- some failed: ask whether to fix and retest the failed ones, save only the
  passing ones, or save nothing.
- none passed: write nothing, and keep the old file.

Save each line in the form `config` returned (codex `/review` is saved as
`provider`). Overwrite the whole file so reruns stay idempotent:

```
# herdr-review reviewers. Used only by /herdr-review; ignore this file otherwise.
# Written by /setup-herdr-review on <YYYY-MM-DD>; every line passed a self-test review.
# One reviewer per line: <cli> <model> <effort>: <skill>
# skill: provider (the CLI's own review), a skill name (my-review, plugin:my-review), or a literal slash command or instruction.
claude claude-opus-5-5 high: /code-review high
grok grok-4.7 medium: my-review
```

Then run `python "$S" config` and confirm that `source` is the rule file and
the reviewers match. Tell the user it was saved, that the next
`/herdr-review` uses it, and that rerunning this skill changes it or
`/setup-herdr-review reset` returns to the defaults.
