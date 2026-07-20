<p align="center">
  <img src="assets/z3r0-logo.png" width="156" alt="XuanMu Logo" />
</p>

<p align="center">
  <strong>English</strong> ·
  <a href="README_zh.md">中文</a>
</p>

<p align="center">
  <strong>Open-source red-team multi-agent collaboration platform with Blackboard-style shared reasoning graph.</strong>
</p>

<p align="center">
  <a href="#overview">Overview</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#blackboard">Blackboard</a> ·
  <a href="#quick-start">Quick Start</a>
</p>

---

> **Security Notice**
>
> This project is intended only for authorized security testing, risk assessment, and academic research.
> Unauthorized use against any system, network, or data is prohibited.
> **The authors are not responsible for any misuse or damages.**

---

## Overview

XuanMu (玄幕) is a **control-plane-oriented red-team multi-agent platform** built for authorized penetration testing, vulnerability discovery, code auditing, and security research.

It combines:
- A **React operator console** (Playground + project workspace)
- A **FastAPI control plane** (REST + WebSocket)
- A **session-based multi-agent runtime** (lead + specialist agents)
- A **structured evidence plane** (assets, findings, graph, attack paths)
- A **Blackboard shared reasoning graph** (Cairn-inspired Fact-Intent coordination)

The design goal is to make agent-assisted security work **operationally bounded and fully reviewable**. Conversations are not the only source of truth — project scope, assets, findings, relationship graphs, attack paths, replayable timelines, and **the agent's reasoning process** are all persisted as explicit application data.

---

## Architecture

```
                     ┌─────────────────────────────────────┐
                     │         React Operator Console       │
                     │    Playground  ·  Project Workspace  │
                     └──────────────┬──────────────────────┘
                                    │ REST + WebSocket
                     ┌──────────────▼──────────────────────┐
                     │        FastAPI Control Plane         │
                     │    System · Users · Agents · Projects │
                     └──────────────┬──────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
   ┌─────▼──────┐           ┌───────▼───────┐          ┌──────▼──────┐
   │ Agent      │           │  Blackboard   │          │  Evidence   │
   │ Runtime    │◄──────────►  Reasoning    │          │  Plane      │
   │ Session +  │   read /  │  Graph        │          │  Assets     │
   │ Delegation │   write   │  Fact/Intent  │          │  Findings   │
   │ CSO + 5    │           │  /Hint        │          │  GraphEdge  │
   │ Specialists│           │               │          │  AttackPath │
   └─────┬──────┘           └───────────────┘          └──────┬──────┘
         │                                                    │
         └──────────────────────┬─────────────────────────────┘
                                │
                     ┌──────────▼──────────┐
                     │      PostgreSQL     │
                     └─────────────────────┘
```

### Agent Team

| Code | Name | Role |
|------|------|------|
| `cso` | XuanMu (玄幕) | Security Lead — task decomposition, coordination, reasoning |
| `cae` | ShouZhuo (守拙) | Code Audit Engineer |
| `cie` | GuanXing (观星) | Intelligence & Recon Engineer |
| `cpe` | PoJun (破军) | Penetration Testing Engineer |
| `cre` | SuYuan (溯源) | Reverse Analysis Engineer |
| `cce` | PoZhen (破阵) | Cryptography Engineer |

### Execution

Commands run directly on the host via Python asyncio subprocess — **no Docker required**. The execution layer supports:

- Synchronous command execution with timeout
- Background async job management with notification on completion
- Output file reading by line range
- Skill system (reusable tool definitions in `.xuanmu/agents/skills/`)
- Knowledge base (structured methodology documents)

---

## Blackboard

The Blackboard is a **Cairn-inspired shared reasoning graph** that enables Stigmergy — agents coordinate through a shared board instead of talking over each other.

### Node Types

| Type | Meaning | Lifecycle |
|------|---------|-----------|
| **Fact** | A confirmed, objective finding | proposed → confirmed / rejected |
| **Intent** | A declared exploration direction | proposed → in_progress → confirmed / rejected / superseded |
| **Hint** | Human or agent guidance | persisted |

### How Agents Use It

```
1. read_blackboard()    — see the full picture
2. create_intent()      — declare direction before acting
3. [execute tools]
4. create_fact()        — record findings, link to parent intent
5. update_node_status() — mark dead ends as rejected
```

The Blackboard layer complements the existing evidence plane (Asset / Finding / GraphEdge): evidence records **what was found**, the blackboard records **why we looked, what we found, what's next**.

### REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/blackboard/{project_id}` | Read | Full blackboard graph snapshot |
| `POST /api/blackboard/{project_id}/nodes` | Create | New fact / intent / hint node |
| `PUT /api/blackboard/{project_id}/nodes/{node_id}` | Update | Change status / description |
| `DELETE /api/blackboard/{project_id}/nodes/{node_id}` | Delete | Remove a node |

---

## Technical Highlights

| Feature | Description |
|---------|-------------|
| Multi-agent orchestration | Lead agent coordinates specialists via delegation + blackboard |
| Structured evidence plane | Assets, findings, relationship graph, attack paths — all persisted |
| Blackboard reasoning graph | Cairn-style Fact-Intent graph for traceable agent reasoning |
| Replayable timeline | Normalized timeline events streamed live or loaded as history |
| No Docker required | Commands run directly on host via asyncio subprocess |
| Knowledge base | Structured methodology documents agents can reference |
| Full web UI | Chat playground + project workspace with graph visualization |
| Local-first LLM | Direct OpenAI-compatible API calls — works with DeepSeek, Qwen, GLM, etc. |

---

## Quick Start

### Prerequisites

- **Linux** (Kali / Debian recommended)
- **Python ≥ 3.12**
- **PostgreSQL** (installed automatically by setup script)
- **Node.js ≥ 18** (for frontend build)

### One-command setup

```bash
bash setup.sh
```

This will:
1. Install system dependencies (PostgreSQL, Node.js)
2. Configure the database
3. Create a Python virtual environment and install dependencies
4. Build the frontend
5. Create start/stop scripts

### Configure

```bash
vi .xuanmu/config.json
```

Fill in LLM API keys, base URLs, and model names for each agent role.
Example configuration uses DeepSeek — works with any OpenAI-compatible API.

### Start

```bash
bash start.sh
```

Open **http://localhost:8000** — login with `admin@admin.com` / `admin123`.

---

## Repository Layout

```
core/           Agent specs, runtime, delegation, context, tools
service/        Domain services (agents, users, projects, blackboard)
router/         FastAPI route declarations
handler/        HTTP and WebSocket request handling
model/          SQLModel database models
schema/         Pydantic API contracts
blackboard/     Shared reasoning graph module
  model/        Database model
  schema/       API contracts
  service/      Business logic
  handler/      HTTP handling
  router/       API routes
web/            React frontend (Playground + admin console)
.xuanmu/        Runtime config, agent prompts, knowledge files
```

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgments

- [Cairn](https://github.com/oritera/Cairn) — Fact-graph based collaborative exploration protocol, which inspired the Blackboard architecture
- [Z3r0](https://github.com/yv1ing/Z3r0) — The original open-source red-team collaboration workbench this project was forked from
