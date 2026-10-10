# Setup & Configuration Guide — Mhide Story Intelligence

This guide explains how to configure, verify, and run **Mhide Story Intelligence** on macOS.

---

## 1. Local Hardware & Zero-Cost Stack Summary

| Subsystem | Selected Tool | Cost | Hardware Profile on This Machine |
| :--- | :--- | :--- | :--- |
| **Language Model** | Ollama (`llama3.2:1b`) | $0 | Fast story generation on Intel 6-Core i7 CPU with 16GB RAM |
| **Voiceover Engine** | Edge-TTS (`en-US-ChristopherNeural`) | $0 | High-quality neural speech synthesis with word timestamps |
| **Video Assembly** | FFmpeg 9.0.1 + FFprobe | $0 | 9:16 vertical 1080x1920 video encoding with H.264 & AAC |
| **State Storage** | SQLite 3 (WAL Mode) | $0 | Zero-dependency, durable local ACID state |
| **Research API** | YouTube Data API v3 | $0 | Free quota (10,000 units/day) from Google Cloud Console |
| **Control Room** | Telegram Bot API | $0 | Free remote notifications and command dispatch |

---

## 2. Environment Setup

### 2.1 Verify Local Dependencies
The application requires Python 3.11+, FFmpeg, and Ollama. On this machine, these are all installed:
```bash
python3 --version
ffmpeg -version
ollama --version
```

### 2.2 Initialize Virtual Environment
Dependencies are pre-configured in `.venv`:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.3 Verify System Health
Run the built-in system health inspection:
```bash
./run.sh health
```

---

## 3. Configuration (.env)

The application reads configuration from `.env`. A complete template is provided in `.env.example`.

Key settings:

```ini
# Core Configuration
APP_ENV=local
LOG_LEVEL=INFO
TIMEZONE=Africa/Lagos
MIN_DISK_FREE_GB=10.0

# Local AI (Ollama)
MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:1b
OLLAMA_REASONING_MODEL=qwen2.5-coder:7b
PAID_APIS_ENABLED=false

# Local Voiceover (TTS)
TTS_PROVIDER=edge-tts
TTS_VOICE=en-US-ChristopherNeural
TTS_RATE=+0%

# YouTube Integration (Default: Safe local mode)
YOUTUBE_PUBLISH_MODE=disabled
YOUTUBE_DEFAULT_PRIVACY=private
```

---

## 4. Verification Milestone Checks (Phase 1)

Execute these commands to confirm that Phase 1 is functioning end-to-end:

1. **Run Unit & Integration Tests**:
   ```bash
   .venv/bin/pytest -v
   ```
   *(Expected: 15 passed)*

2. **Test Free Local Voiceover Synthesis**:
   ```bash
   ./run.sh test-tts
   ```
   *(Expected: Audio generated at `output/sample_voiceover.mp3`)*

3. **Test Local LLM Reasoning**:
   ```bash
   ./run.sh test-llm
   ```
   *(Expected: Response returned from local Ollama model `llama3.2:1b`)*

4. **Verify Persistent Job Lifecycle**:
   ```bash
   ./run.sh enqueue-test
   ./run.sh status
   ./run.sh run
   ./run.sh status
   ```
   *(Expected: Job moves through QUEUED -> RESEARCHING -> SCRIPTING -> NARRATING -> ASSEMBLING -> QA -> READY)*

---

## 5. Next Steps for Phase 2: YouTube Research Engine

To prepare for **Phase 2 (Competitor Research & Trend Intelligence)**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `Mhide-Story-Intelligence`).
3. Under **APIs & Services**, enable **YouTube Data API v3**.
4. Under **Credentials**, click **Create Credentials** -> **API Key**.
5. Copy the API key and paste it into `.env`:
   ```ini
   YOUTUBE_API_KEY=your_actual_key_here
   ```
*(Note: If you do not yet have an API key, Phase 2 will provide a transparent configuration prompt while unit tests validate the data models and scoring algorithms offline).*
