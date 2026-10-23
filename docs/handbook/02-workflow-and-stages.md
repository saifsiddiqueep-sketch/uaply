# 02 Workflow and stages

## The path of every change

```
 Idea --> Trello card --> work branch --> PR into sandbox --> review + merge --> preview check
                                                                                    |
     live site <-- deploy + live checks <-- merge PR sandbox -> dev (release) <-----+
          |
          +--> tag v1.0.0-rc.N, CHANGELOG entry
```

Rule from `CONTRIBUTING.md` and `HANDOFF.md`: work moves **sandbox, then dev**, always through a pull request. Nothing is pushed straight to `dev` or `main`. `main` changes only when the owner decides.

## Stage by stage

### 1. Idea

Anyone can raise one: a founder, a tester (`docs/tester-guide.md`), a review finding (`docs/reviews/`), a user's feedback (`/feedback`, owner only).

### 2. Trello card

- Board: **UAply Team Board**, https://trello.com/b/TUiuK5fz/uaply-team-board (`HANDOFF.md` calls it "the live record of tasks").
- One card per task. Put the goal, the area (front end, server, feeds, mobile, docs) and what "done" means.
- Open cards are numbered **001, 002, ...** in the order to do them. Steps that need a person or money come first so their waiting overlaps other work.
- Lists: "General – unassigned", "Mohammed – to do", "Saif – to do", **Doing**, **Waiting on someone**, **Completed**, and the two heads-up columns.
- **Heads-up columns.** The two rightmost lists are **"Mohammed is working on"** and **"Saif is working on"**. While a side has work on a branch, it keeps one card there named `<Name>: <branch>` (for example `Saif: dev`) with what and since when. When the work merges, the card is archived (automatic once the GitHub heads-up automation is installed; until then, by hand). These lists are a heads-up only. They do not lock anything. Before you touch a branch, look at the other side's column. If a card names your branch, tell your founder so the two founders can talk; do not block, wait silently or post warnings.
- Move your card to Doing when you start. Add the PR link as a comment when you open the PR.

### 3. Work branch

- Branch from the newest `sandbox`: `git fetch origin && git checkout -b my-idea origin/sandbox` (`README.md`).
- Name it after the task, short and plain (examples in history: `signin-gate`, `location-phone-words`, `stale-server-fix`).
- Stay in your area (page 00). A change to server, feeds, hosting, email or the app frame needs Saif's side to agree first; front end, card UI, mobile and docs go to Mohammed.
- Run `node check.js` and `python tools/audit-files.py` before every push; run `bash tools/run-all-tests.sh` before asking for review (page 03).

### 4. Pull request into `sandbox`

- Title: `<area>: <what changed, in plain words>` (`CONTRIBUTING.md`).
- Fill in `.github/pull_request_template.md`: Summary, Where it is going, What changed, What users will notice, How it was tested, Risks, Not done. Write for someone who joins in a year. Show proof: test counts, log lines, screenshots (`HANDOFF.md`).
- Add plain-English bullets for non-engineers: what, why, where, how it was checked.
- CI ("Check the code", `.github/workflows/check.yml`) runs on every push and PR. It must be green.
- Add your entry under `## Unreleased (sandbox)` in `CHANGELOG.md` (that is what every recent sandbox change does).

### 5. Review and merge into `sandbox`

- Who approves: the owner of the area (page 00). `README.md`: "The owner reviews and merges." `HANDOFF.md` asks for independent reviewer passes on each change before its PR (lost or doubled data; security and races; broken behaviour or tests that test nothing).
- Before any commit lands on `sandbox` or `dev`, Mohammed asks to see every change listed as plain bullets and to give an OK first (team rule from Mohammed). Follow it for his areas; for Saif's areas, **TO CONFIRM with Saif/Mohammed**.
- Use a merge commit (the history shows `Merge branch '...' into sandbox`).

### 6. Preview check

- Within minutes of a merge into `sandbox`, the Render static site **uaply-sandbox-preview** rebuilds from the `sandbox` branch: https://uaply-sandbox-preview.onrender.com/sandbox.html and /dev.html. Note that /dev.html there is the dev page **as it is on the sandbox branch**, not the live site.
- While the repository is public, GitHub Pages also publishes https://saifsiddiqueep-sketch.github.io/uaply/sandbox.html and dev.html (`.github/workflows/pages.yml`). These go away when the repository is made private (`docs/runbook-launch.md` step 1.5).
- The previews have no server: example jobs, no accounts. For real behaviour run `python serve.py 8766 sandbox --api` locally.

### 7. Release: pull request `sandbox` into `dev`

- Owner: Saif's side ("releases" in `HANDOFF.md`). A release PR goes `--base dev --head sandbox`, titled `Release candidate N: <headline>` (`docs/runbook-launch.md` section 1).
- The full suite must be green on the chosen `sandbox` commit; nothing new merges into `sandbox` during the release ("Freeze").
- Hiring mode and the sandbox-only sign-up stay off on dev by themselves (the code checks the instance name), so nothing has to be cut out.
- Merging into `dev` **is a production release**: the live site runs `dev`.

### 8. Deploy, check, tag

See page 04. In short: confirm the deploy started (often it must be started by hand), read the start-up log line, run `bash tools/launch-smoke.sh https://uaply.net`, tag `v1.0.0-rc.N`, move the CHANGELOG's Unreleased items under the new version heading.

## Who approves what

| Step | Who approves |
|---|---|
| Starting a card in someone else's area | That area's founder (page 00) |
| Merge into `sandbox` | The area owner after review |
| Release `sandbox` into `dev` | Saif |
| Anything in `main` | The owner only (`README.md`) |
| Render settings, Cloudflare DNS, Stripe, Google Cloud, Brevo | Saif only (`HANDOFF.md`: "What the owner must do himself") |
| Anything that costs money | Saif, before it happens (`HANDOFF.md`: "Ask before any purchase") |
| Turning Hiring mode or sandbox-only features on in dev | The owner (`HANDOFF.md`) |
| Legal page wording | The owner and the attorney (`LEGAL-REVIEW.md`) |

## Definition of done

A task is done when all of these are true:

1. The change is merged into `sandbox` through a PR in the template shape, with proof.
2. `node check.js`, `python tools/audit-files.py` and the relevant tests pass; `bash tools/run-all-tests.sh` shows `ALL TESTS PASSED` for anything that changes behaviour.
3. New behaviour has a test that fails before the change and passes after (the CHANGELOG records this for most fixes, for example "each fails on 512bf84").
4. `CHANGELOG.md` has an entry under "Unreleased (sandbox)".
5. Docs that describe the changed behaviour are updated (`DEPLOY.md`, `docs/`, help articles, this space).
6. The preview or a local server was checked in a browser at phone size (390x844) and computer size.
7. The Trello card is in Completed with the PR link, and your heads-up card is archived.

For a release, also: the live site reports the new commit, `live-check.py --expect all` has no FAIL, the tag exists, and the CHANGELOG has the version heading.
