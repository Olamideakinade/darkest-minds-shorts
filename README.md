# Mhide Story Intelligence — Autonomous YouTube Shorts Channel Operator

> **A real, persistent, zero-cost autonomous AI agent system engineered for macOS local execution to operate and grow an existing YouTube Shorts channel independently.**

---

## 1. System Overview & Autonomous Architecture

**Mhide Story Intelligence** is an autonomous AI channel operator designed to manage an existing YouTube Shorts channel in storytelling niches (*Strange History, Unsolved Mysteries, Documented Real-Life Curiosities*).

### The Autonomous Paradigm
Unlike chatbots or prompt-assisted tools, Mhide Story Intelligence operates **independently without requiring manual daily prompts, topic approvals, or upload initiation**:
1. **Autonomous Scheduled Research**: Continuously monitors competitor channels and search queries via YouTube Data API v3.
2. **Autonomous Decision Engine**: Selects promising storytelling opportunities based on research evidence, active strategy weights, and past performance.
3. **High-Quality Original Storytelling (Phase 3)**: Generates 3-Act narrative scripts with scene directions, factual claim verification, and anti-cliché filters.
4. **Local Voiceover & Media Assembly**: Synthesizes natural narration using free neural TTS (`edge-tts`) and renders vertical 9:16 Shorts via native `FFmpeg`.
5. **Quality & Safety Assurance**: Performs automated audio, video, factual, and originality checks prior to publication.
6. **Autonomous Publishing Policy**: Supports 3 distinct operating modes (`disabled`, `private_test`, `autonomous_public`) with daily upload limits, duplicate prevention, and auto-pause on failures.
7. **Empirical Learning Feedback Loop**: Analyzes eligible video performance at comparable observation ages (24h, 48h, 7d) to update content strategy weights empirically.
8. **Persistent Scheduler Daemon**: Survives restarts, limits concurrency to 1 render job, monitors disk space, and runs unattended.
9. **Telegram as Control Room**: Telegram provides monitoring, daily digests, alerts, and remote pause/resume controls—it is NOT the agent's brain or required trigger.

---

## 2. Hardware Profile & Resource Management

The system operates locally on macOS using free, open-source, and local-first tools:

| Component | Detected Specification | Architecture Decision |
| :--- | :--- | :--- |
| **Operating System** | macOS 15.8.2 (Darwin x86_64) | Native macOS local backend |
| **CPU** | Intel Core i7-8850H @ 2.60GHz (12 cores) | 1 concurrent render job to preserve thermal headroom |
| **Memory (RAM)** | 16.0 GB RAM | Optimal for `llama3.2:1b` (1.3GB footprint, high CPU throughput) |
| **Disk Space** | 96.2 GB available | Auto-pauses if free space drops below 10.0 GB threshold |
| **Local LLM** | Ollama running at `127.0.0.1:11434` | Models: `llama3.2:1b` (fast story), `qwen2.5-coder:7b` (reasoning) |
| **Local TTS** | Edge-TTS (100% free neural speech) | Voices: `en-US-ChristopherNeural`, `en-US-GuyNeural` |
| **FFmpeg** | FFmpeg 9.0.1 with libx264/mp3lame | 1080x1920 9:16 vertical video rendering |
| **Spending Guard** | Zero Cost Guarantee | Paid APIs strictly disabled (`PAID_APIS_ENABLED=false`) |

---

## 3. Autonomous Operating Modes & Lifecycle

### Publishing Modes
- `disabled`: Safe local production only. Videos are rendered and quality-checked, remaining in `READY` state.
- `private_test`: Videos upload to the authenticated owner channel as `private` for manual inspection.
- `autonomous_public`: Once the owner's existing channel is authenticated and this mode is explicitly enabled, qualifying videos that pass all QA checks publish automatically.

```
[SCHEDULED RESEARCH]
        │
        ▼
[DECISION ENGINE] ──► Selects best topic + logs rationale to decision_logs
        │
        ▼
[STORY & SCRIPT]  ──► 3-Act narrative, scene visual cues, factual claims verified
        │
        ▼
[NARRATION (TTS)] ──► Neural speech generated + word-boundary timestamps
        │
        ▼
[MEDIA ASSEMBLY]  ──► 1080x1920 vertical video rendered via FFmpeg
        │
        ▼
[QUALITY ASSURANCE] (Audio, visual, pacing, originality, factual score)
        │
        ├── FAILS QA ──► [NEEDS_REVIEW] / [FAILED] + Alert owner
        └── PASSES QA ──► Check Publishing Mode:
                             ├── disabled          ──► [READY] (local only)
                             ├── private_test      ──► [UPLOADING] (private video)
                             └── autonomous_public ──► [UPLOADING] (public Shorts)
                                                             │
                                                             ▼
                                                    [EMPIRICAL LEARNING LOOP]
                                                    (Evaluates 24h/48h/7d metrics,
                                                     updates strategy weights)
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

