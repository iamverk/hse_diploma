# Taxonomy-as-Code

Autonomous taxonomy construction using LLM coding agents and the Ralph loop pattern.

## Quick Start

```bash
conda activate taxonomy-as-code   # Python env with networkx + mcp
python tools/taxonomy_cli.py tree          # see current taxonomy
python tools/validate.py                   # check structure
python tools/metrics.py taxonomy.json reference/gold_standard.json  # quality score
```

## Run Ralph Loop

```bash
chmod +x ralph.sh

# Claude Code (default)
./ralph.sh 10

# Cursor Agent CLI — default model (gpt-5.3-codex-spark-preview-high)
./ralph.sh 10 --tool cursor

# Cursor Agent CLI — extra high model
./ralph.sh 10 --tool cursor --model gpt-5.3-codex-spark-preview-xhigh

# Amp
./ralph.sh 5 --tool amp
```

### Agent → instruction file mapping

| Agent | Reads | Why |
|-------|-------|-----|
| `claude` | `CLAUDE.md` | Claude Code convention |
| `amp` | `CLAUDE.md` | same prompt via stdin |
| `cursor` | `AGENTS.md` | Cursor natively respects AGENTS.md |

## Install cursor-agent CLI

```bash
curl https://cursor.com/install -fsSL | bash
cursor-agent login          # authenticate with your Cursor account
cursor-agent --version      # verify
```

## Use with Cursor Agent (MCP — interactive mode)

```bash
# .cursor/mcp.json is already configured
# Open project in Cursor — taxonomy tools appear automatically as MCP tools
```

## Project Structure

```
├── taxonomy.json              ← working taxonomy (agent edits this)
├── reference/
│   └── gold_standard.json     ← target taxonomy (47 nodes)
├── tools/
│   ├── taxonomy_core.py       ← shared logic (networkx)
│   ├── taxonomy_cli.py        ← CLI interface
│   ├── taxonomy_mcp_server.py ← MCP server for Cursor (interactive)
│   ├── validate.py            ← structure validator (exit 0/1)
│   ├── metrics.py             ← quality metrics vs reference
│   ├── lint.py                ← anomaly detector
│   └── diff.py                ← version comparator
├── AGENTS.md                  ← instructions for Cursor Agent (comprehensive)
├── CLAUDE.md                  ← instructions for Claude Code / Amp
├── prd.json                   ← task list for Ralph loop
├── progress.txt               ← persistent memory across iterations
├── ralph.sh                   ← the loop script (claude / amp / cursor)
├── hooks/pre-commit           ← git hook (validate before commit)
└── .cursor/mcp.json           ← Cursor MCP config
```

## Starting Point

- taxonomy.json: 4 nodes (root + 3 top-level categories)
- Edge F1 vs gold: 0.12
- Goal: reach edge F1 > 0.5 through autonomous agent iterations
