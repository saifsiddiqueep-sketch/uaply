# Public GitHub add-ons worth installing (researched 2026-10-28)

Rule: measure first, add one thing at a time, read every hook before installing (plugins and hooks run code on your machine).
Star counts and claims are from the repo pages; "self-reported" = the author's number, not independently tested.

## Install now (low risk, high value)
| Tool | Why | Install |
|---|---|---|
| [ccusage](https://github.com/ryoppippi/ccusage) | Shows real token use per day/session/model, so you can prove Lite saves anything | `npx ccusage@latest` (weekly: `npx ccusage@latest weekly`) |
| [claude-hud](https://github.com/jarrodwatts/claude-hud) | Context bar + rate limits. Optional: Lite's own status line already shows this; pick one | `/plugin marketplace add jarrodwatts/claude-hud` then `/plugin install claude-hud` (Node 18+) |
| [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) | Anthropic's plugin directory, built into Claude Code: `/plugin` → Discover | built in |

## Try later, only if ccusage shows the matching leak
| Tool | When | Evidence |
|---|---|---|
| [caveman](https://github.com/JuliusBrussee/caveman) | Replies too wordy | Third-party test: −37% on one task, ~0 on agentic work. Set `DO_NOT_TRACK=1` (telemetry on by default) |
| [rtk](https://github.com/rtk-ai/rtk) | Huge test/log output in chat | Self-reported 60–90% on bash output; one independent test found 0%. Lite's `runner` bot already covers this |
| [VoltAgent subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | Want a specialist (debugger, security auditor) | Hand-copy 1–2 files into `.claude/agents/`, keep the `model:` line. Don't bulk-install |
| [wshobson/agents](https://github.com/wshobson/agents) | Want a domain pack (e.g. python-development) | Install single plugins only; each one adds tokens to every session |
| [Serena](https://github.com/oraios/serena) | Codebase gets big (code search without reading whole files) | Self-reported; GPL-3.0; runs an MCP server |

## Catalog website
[aitmpl.com](https://aitmpl.com) (source: [davila7/claude-code-templates](https://github.com/davila7/claude-code-templates)) — ~1,900 agents/hooks/commands.
OK to browse; install one item at a time with `npx claude-code-templates@latest --agent <path>`, never with `--yes`.

## Skip
- superpowers / spec-kit / BMAD: heavy multi-step processes; more rounds, no published savings (spec-kit used ~16× the tokens of superpowers in the one public comparison).
- claude-mem: 6 hooks + local services + cloud sign-up push + promotes a crypto token.
- Anything with a noncommercial licence (e.g. alexgreensh/token-optimizer) or no commits in months.
- Unofficial "Anthropic" marketplaces — only `github.com/anthropics/*` is official.
