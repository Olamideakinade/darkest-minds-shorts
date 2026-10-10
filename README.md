# Mhide Story Intelligence — Autonomous YouTube Shorts Agent

> **A real, extensible, zero-cost autonomous AI storytelling channel operator engineered for macOS local execution and future cloud scalability.**

---

## 1. System Overview

**Mhide Story Intelligence** is an autonomous AI agent system engineered to produce high-retention faceless YouTube Shorts in storytelling niches (*Strange History, Unsolved Mysteries, Documented Real-Life Curiosities*).

It operates locally on macOS using free, open-source, and zero-cost local tools:
- **Local Language Model**: Ollama (`llama3.2:1b` fast story generation / `qwen2.5-coder:7b` reasoning).
- **Natural Voiceover (TTS)**: Free neural text-to-speech engine (`edge-tts`) with studio-grade voices and word boundary timing.
- **Media Processing**: Native `FFmpeg 9.0.1` and `FFprobe` for 9:16 vertical video assembly.
- **Durable Local State**: SQLite in WAL mode with atomic transactions, crash recovery, and persistent job queue.
- **Channel Growth & Publishing**: Official YouTube Data API v3 and OAuth 2.0 with strict publishing safety guards.

---

## 2. Hardware Inspection & Architecture Profile

The system automatically inspected the host machine and configured optimal parameters:

| Component | Detected Specification | Architecture Decision |
| :--- | :--- | :--- |
| **Operating System** | macOS 15.8.2 (Darwin x86_64) | Native macOS local backend |
| **CPU** | Intel Core i7-8850H @ 2.60GHz (12 cores) | 1 concurrent render job to preserve thermal headroom |
| **Memory (RAM)** | 16.0 GB RAM | Optimal for `llama3.2:1b` (1.3GB footprint, high CPU throughput) |
| **Disk Space** | 96.2 GB available | Sufficient for video caching (guard threshold set to 10GB) |
| **Local LLM** | Ollama running at `127.0.0.1:11434` | Models: `llama3.2:1b`, `qwen2.5-coder:7b` |
| **Local TTS** | Edge-TTS (100% free neural speech) | High quality voices (`en-US-ChristopherNeural`, `en-US-GuyNeural`) |
| **FFmpeg** | FFmpeg 9.0.1 with libx264/mp3lame | 1080x1920 9:16 vertical video rendering |

---

## 3. Production Lifecycle & State Machine

Every video proceeds through an explicit state machine with job locking and crash recovery:

```
[QUEUED] ──► [RESEARCHING] ──► [SCRIPTING] ──► [NARRATING] ──► [ASSEMBLING] ──► [QA] ──► [READY]
                                                                                           │
                                  ┌────────────────────────────────────────────────────────┘
                                  ▼
                     [YOUTUBE_PUBLISH_MODE]
                     ├── "disabled"        ──► Stays in [READY] (safe local render only)
                     ├── "review-required" ──► Moves to [NEEDS_REVIEW] (awaits Telegram/Owner approval)
                     └── "autonomous"      ──► [UPLOADING] ──► [PUBLISHED]
```

### Safety & Crash Recovery
- **Crash Recovery**: If the system or Mac restarts mid-job, in-flight jobs in `RESEARCHING`–`QA` are automatically reset to `RETRYING`. In-flight jobs in `UPLOADING` are moved to `NEEDS_REVIEW` to strictly prevent duplicate uploads.
- **Publishing Guard**: Publishing defaults to `disabled` with `private` visibility. No content is published publicly without explicit configuration.
- **Zero Cost Guarantee**: `PAID_APIS_ENABLED=false` prevents any unexpected cloud charges.

---

## 4. Quickstart & CLI Commands

The runner script `./run.sh` executes all commands inside the local virtual environment:

### Health Check
Verify hardware, FFmpeg, Ollama, TTS, database, and safety settings:
```bash
./run.sh health
```

### Test Voiceover (TTS)
Generate a test voice clip (`output/sample_voiceover.mp3`) using the free neural speech engine:
```bash
./run.sh test-tts
```

### Test Local LLM
Test story reasoning with the local Ollama model:
```bash
./run.sh test-llm
```

### Enqueue and Process a Test Job
```bash
./run.sh enqueue-test
./run.sh status
./run.sh run
```

### Run Automated Test Suite
```bash
.venv/bin/pytest -v
```

---

## 5. Modular Project Structure

```
Mhie intellingenc(YT)/
├── app/
│   ├── main.py              # CLI entry point and health monitor
│   ├── config.py            # Typed settings, validation, and secret redaction
│   ├── orchestrator.py      # State machine coordinator and crash recovery
│   ├── database/
│   │   ├── db.py            # SQLite repository, transactions, and WAL mode
│   │   ├── models.py        # Domain models (Job, StoryIdea, Script, Asset, QA)
│   │   └── migrations.py    # Schema versioning and table migrations
│   ├── intelligence/
│   │   ├── model_provider.py# Abstract provider interface
│   │   └── ollama_client.py # Local Ollama HTTP client with transparent fallback
│   ├── utils/
│   │   ├── hardware.py      # Hardware profiling and suitability advisor
│   │   └── logger.py        # Structured logging with secret redaction filter
│   ├── research/            # (Phase 2) YouTube competitor and trend research
│   ├── scripts/             # (Phase 3) Original story generation and factual check
│   ├── narration/           # (Phase 4) Local TTS voiceover synthesis and audio sync
│   ├── visuals/             # (Phase 5) Image assets and visual rhythm provider
│   ├── editing/             # (Phase 5) FFmpeg video assembly and subtitle burner
│   ├── quality/             # (Phase 5) Automated QA inspection rules
│   ├── telegram/            # (Phase 6) Telegram control room bot
│   ├── youtube/             # (Phase 7) Official YouTube Data API v3 publisher
│   ├── analytics/           # (Phase 8) Authorized channel performance feedback
│   ├── scheduler/           # (Phase 9) Autonomous time-aware job scheduler
│   └── dashboard/           # Lightweight local monitoring dashboard
├── tests/                   # Full unit and integration test suite
├── data/                    # SQLite database (mhide.db) and persistent state
├── output/                  # Rendered media assets and audio previews
├── logs/                    # Rotating log files (mhide.log)
├── credentials/             # OAuth client credentials and tokens (git-ignored)
├── .env.example             # Complete configuration template
├── .gitignore               # Protection for keys, database, media, and logs
├── requirements.txt         # Tested pinned dependencies
├── run.sh                   # Native execution helper
└── SETUP.md                 # Setup walkthrough and Phase roadmap
```

---

## 6. Implementation Roadmap

- [x] **Phase 1: Environment, Hardware Detection, DB, State Machine, & Skeleton** *(Delivered)*
- [x] **Phase 2: YouTube Research Engine & Trend Opportunity Scoring** *(Delivered)*
- [ ] **Phase 3: Original Storytelling & Factual Verification Pipeline**
- [ ] **Phase 4: Natural Local Voiceover & Audio Mastering**
- [ ] **Phase 5: Professional 9:16 Shorts Video Assembly & Automated QA**
- [ ] **Phase 6: Telegram Remote Control Room & Notifications**
- [ ] **Phase 7: YouTube Data API v3 Upload & OAuth Verification (Existing Owner Channel)**
- [ ] **Phase 8: Analytics Feedback Loop & Story Optimization**
- [ ] **Phase 9: Autonomous Persistent Scheduling & Production Limits**
- [ ] **Phase 10: Cloud Deployment Container & Worker Readiness**

