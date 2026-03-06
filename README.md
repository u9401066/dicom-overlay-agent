# template-is-all-you-need

> 🏗️ AI-Assisted Development Project Template with Claude Skills, Memory Bank & Constitution-Bylaw Architecture

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

🌐 [繁體中文](README.zh-TW.md)

## ✨ Features

- 🏛️ **Constitution-Bylaw Architecture** - Hierarchical rule system inspired by speckit
- 🤖 **Claude Skills** - 20+ modular AI skills for development automation
- 📝 **Memory Bank** - Cross-conversation project memory system
- 🏗️ **DDD Architecture** - Domain-Driven Design with independent DAL
- 🔄 **Git Automation** - Auto-update documentation before commits
- 🐍 **Python Environment** - uv-first package management
- 🎯 **Copilot Agents** - 14 custom agents with model cost strategy
- 🔒 **Pre-commit Hooks** - 16+ hooks for code quality and security

## 📁 Project Structure

```
template-is-all-you-need/
├── CONSTITUTION.md          # 📜 Project Constitution (Highest Principles)
├── .github/
│   ├── agents/              # 🤖 Copilot Custom Agents (14)
│   ├── prompts/             # 📋 Copilot Reusable Prompts (5)
│   ├── bylaws/              # 📋 Bylaws
│   │   ├── ddd-architecture.md
│   │   ├── git-workflow.md
│   │   ├── memory-bank.md
│   │   └── python-environment.md
│   ├── workflows/           # ⚙️ CI/CD
│   ├── ISSUE_TEMPLATE/      # 📝 Issue Templates
│   └── copilot-instructions.md
├── .claude/skills/          # 🤖 Claude Skills
│   ├── git-precommit/       # Git commit orchestrator
│   ├── ddd-architect/       # DDD architecture assistant
│   ├── code-refactor/       # Code refactoring
│   ├── code-audit/          # Deep code audit (5 dimensions)
│   ├── skill-health-check/  # Skill & instruction health check
│   ├── memory-updater/      # Memory Bank sync
│   ├── memory-checkpoint/   # Pre-summarization checkpoint
│   ├── readme-updater/      # README updates
│   ├── readme-i18n/         # README internationalization
│   ├── changelog-updater/   # CHANGELOG updates
│   ├── roadmap-updater/     # ROADMAP updates
│   ├── code-reviewer/       # Code review
│   ├── test-generator/      # Test generation
│   └── project-init/        # Project initialization
├── scripts/hooks/           # 🔧 Custom Git Hooks
├── .pre-commit-config.yaml  # 🔒 Pre-commit Configuration
├── memory-bank/             # 🧠 Project Memory
├── README.md                # This file (English)
├── README.zh-TW.md          # Chinese version
├── CHANGELOG.md
├── ROADMAP.md
├── ARCHITECTURE.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
└── LICENSE
```

## 🚀 Quick Start

### Use as Template

```bash
# Option 1: GitHub CLI
gh repo create my-project --template u9401066/template-is-all-you-need

# Option 2: Manual clone
git clone https://github.com/u9401066/template-is-all-you-need.git my-project
cd my-project
rm -rf .git && git init
```

### VS Code Setup

Ensure GitHub Copilot is installed. The project auto-enables:
- Claude Skills support
- Custom instructions
- Agent mode

## 🤖 Skills Usage

| Command | Function |
|---------|----------|
| "prepare commit" | Execute full Git commit workflow |
| "quick commit" | Sync Memory Bank only |
| "create feature X" | Generate DDD structure |
| "review code" | Code review |
| "generate tests" | Auto-generate tests |
| "checkpoint" | Save memory before context loss |

## 🏛️ Architecture Principles

This project follows:

1. **DDD (Domain-Driven Design)** - Domain-driven architecture
2. **Independent DAL** - Separated Data Access Layer
3. **Documentation First** - Code is compiled documentation
4. **Memory Bank Binding** - Operations sync with memory in real-time

See [CONSTITUTION.md](CONSTITUTION.md) for details.

## 📋 Documentation

- [Constitution](CONSTITUTION.md) - Highest principles
- [Architecture](ARCHITECTURE.md) - System architecture
- [Changelog](CHANGELOG.md) - Version history
- [Roadmap](ROADMAP.md) - Feature planning
- [Contributing](CONTRIBUTING.md) - How to contribute
- [CLAUDE.md](CLAUDE.md) - Claude Code guidelines
- [AGENTS.md](AGENTS.md) - VS Code Copilot Agent guidelines

## 🎯 Copilot Custom Agents

14 custom agents with a model cost optimization strategy:

| Agent | Role | Model |
|-------|------|-------|
| `architect` | System architecture + DDD | Sonnet 4.6 → GPT-5.4 |
| `code` | Feature implementation | Sonnet 4.6 → GPT-5.4 |
| `debug` | Root cause analysis | Sonnet 4.6 → GPT-5.4 |
| `audit` | Deep code audit (5 dimensions) | Opus 4.6 → Sonnet 4.6 |
| `orchestrator` | Task decomposition + delegation | Opus 4.6 → GPT-5.4 |
| `deep-thinker` | Complex reasoning + algorithms | Opus 4.6 → GPT-5.4 |
| `researcher` | Read-only codebase exploration | Gemini 3.1 Pro → Sonnet 4.6 |
| `test-runner` 🆓 | Run tests + iterate fixes | GPT-5 mini → GPT-4.1 |
| `context-loader` 🆓 | Load Memory Bank + summarize | GPT-4.1 → GPT-5 mini |
| `ask` 🆓 | Project Q&A | GPT-4.1 → Haiku 4.5 |
| `review-panel` | Multi-model review committee | Opus 4.6 (3 AI cross-review) |

> 🆓 = Free model agents for high-volume, repetitive tasks

## 🔒 Pre-commit Hooks

16+ hooks via `.pre-commit-config.yaml`:

- **Code Quality**: ruff lint + format, mypy
- **Security**: bandit, gitleaks
- **Conventions**: conventional-commits, commit-size-guard (≤30 files)
- **AI Maintenance**: skill-freshness-check, agent-freshness-check, memory-bank-reminder

## 🧪 Testing Support

The template includes comprehensive testing configuration:

- **Static Analysis**: ruff, mypy, bandit
- **Unit Tests**: pytest with 80% coverage requirement
- **Integration Tests**: pytest-asyncio
- **E2E Tests**: Playwright
- **CI/CD**: GitHub Actions with 6 jobs

## 📄 License

[Apache License 2.0](LICENSE)
