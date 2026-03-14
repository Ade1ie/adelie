# Adelie Loop Manual (Runbook)

This document defines the operational procedures for the Adelie self-communicating AI loop system.

---

## Loop States

| State | Description | What Expert AI reads |
|---|---|---|
| `normal` | Default operation | `skills/`, `logic/`, `dependencies/` |
| `error` | An exception occurred | `errors/`, `skills/` |
| `new_logic` | Bootstrapping new commands | `skills/`, `dependencies/`, `logic/` |
| `export` | Producing output | `exports/`, `logic/` |
| `maintenance` | Paused for health check | `maintenance/`, `logic/` |
| `shutdown` | Graceful stop | — |

---

## Error Handling

When an error occurs:
1. The Orchestrator auto-writes an error report to `workspace/errors/error_<timestamp>.md`
2. The KB index is updated
3. On the NEXT cycle, Expert AI **situationally loads `errors/`** to read the report
4. Expert AI produces a `RECOVER` action with specific recovery commands
5. Writer AI updates `workspace/skills/` with recovery steps if new knowledge was gained

### Manual recovery
```bash
# Check recent errors
ls workspace/errors/

# Force a fresh normal loop after manual fix
python run.py --once
```

---

## Exporting Results

Expert AI can decide to export by setting `"action": "EXPORT"` and populating `"export_data"`.
The Orchestrator writes the export to `workspace/exports/export_<timestamp>.json`.

To trigger a manual export:
```bash
python run.py --once --goal "Export a summary of all current logic"
```

---

## Adding New Logic

To bootstrap new command logic:
1. Set `next_situation` to `new_logic` in Expert AI's output, OR
2. Run:
```bash
python run.py --once --goal "Create new logic for <your feature>"
```
Writer AI will write to `workspace/skills/` and `workspace/dependencies/`.
Expert AI will read those on the next cycle and produce the corresponding `logic/` file.

---

## Maintenance Window

```bash
# Write a maintenance note and exit
python run.py --maintenance

# Or rely on Expert AI to request a pause (action: PAUSE)
# The loop will sleep for 2× the normal interval then resume
```

---

## Knowledge Base Categories

| Folder | Purpose | Author |
|---|---|---|
| `skills/` | Step-by-step how-to guides the Expert AI can follow | Writer AI |
| `dependencies/` | External APIs, libraries, services with usage notes | Writer AI |
| `errors/` | Known errors, root causes, recovery steps | Orchestrator + Writer AI |
| `logic/` | Command logic patterns and decision templates | Expert AI output |
| `exports/` | Results and output data | Expert AI via Orchestrator |
| `maintenance/` | Health status, scheduled tasks, system notes | Writer AI + manual |

---

## Starting the System

```bash
# 1. Set up environment
cp .env.example .env
# Edit .env — add your GEMINI_API_KEY

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run a single test cycle
python run.py --once

# 4. Start the endless loop
python run.py --loop

# 5. Custom goal
python run.py --loop --goal "Monitor and improve the Adelie project features"
```

---

## Stopping the System

Press **Ctrl+C** at any time. The loop will finish the current cycle cleanly before stopping.

---

## File Structure

```
Adelie/
├── run.py                  # Entry point
├── requirements.txt
├── .env.example
├── adelie/
│   ├── config.py           # Configuration
│   ├── orchestrator.py     # Endless loop state machine
│   ├── agents/
│   │   ├── writer_ai.py    # Knowledge writer
│   │   └── expert_ai.py    # Decision maker
│   └── kb/
│       └── retriever.py    # Situational KB access
└── workspace/              # Knowledge Base (auto-created)
    ├── index.json          # Master KB index
    ├── skills/
    ├── dependencies/
    ├── errors/
    ├── logic/
    ├── exports/
    └── maintenance/
```
