# Meeting Copilot

A small always-on-top desktop overlay that listens to a meeting, translates what the other person says into Korean, and drafts replies for you to say. Upload your resume and it can ground its answers in your real background, which is useful for interview practice.

Built with a FastAPI backend, local speech-to-text on Apple Silicon, the Claude API for translation and replies, and an Electron window.

## Features

- **Translation**: either "listen, then press Translate" (whole turns, better quality) or live sentence-by-sentence mode
- **Reply suggestions**: five different stances for every utterance (agree, agree + example, nuanced, polite disagreement, next step)
- **Reply instructions**: type or tap what you want ("answer their question", "ask about the schedule") and get three versions in different tones
- **Resume-aware answers**: upload a PDF, DOCX, TXT or MD resume; answers use only what it contains and never invent experience
- **Compact translucent overlay**: frameless, always on top, adjustable opacity, collapsible
- **Audio input**: system audio via BlackHole, or the microphone (browser mode also supports tab audio)
- **Meeting languages**: English, Japanese, Chinese, Spanish, French (replies and translations are in Korean)

## How it works

```
system audio ─▶ BlackHole ─▶ Electron window ─▶ speech segments ─▶ FastAPI
                                                                    │
                                    local Whisper (mlx-whisper) ◀───┤
                                    Claude API (translation + replies) ◀─┘
```

Speech is transcribed locally. Only the transcribed text (and your resume text, if uploaded) is sent to the Claude API.

## Requirements

- macOS (developed on an Apple Silicon MacBook)
- Python 3.9+
- Node.js
- [BlackHole 2ch](https://existential.audio/blackhole/) for capturing system audio
- An Anthropic API key from console.anthropic.com

## Setup

```bash
git clone https://github.com/JasonKim2006/meeting-copilot.git
cd meeting-copilot

# Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install mlx-whisper

# Node
npm install
```

Create a `.env` file in the project folder:

```
ANTHROPIC_API_KEY=your-key-here
```

### Audio routing (one time)

1. Install BlackHole: `brew install --cask blackhole-2ch`, then restart the Mac.
2. Open **Audio MIDI Setup**, click **+**, choose **Create Multi-Output Device**.
3. Check your speakers or headphones and **BlackHole 2ch**, and enable **Drift Correction** for BlackHole.
4. Send the audio you want to translate to that Multi-Output Device. Either set it as the Mac's sound output (all computer audio), or set only your meeting app's speaker to it.

## Run

```bash
npm start
```

The overlay opens and the server starts automatically. On first use the speech model downloads once (about 1.6 GB) and microphone access must be allowed.

Browser-only mode: `uvicorn main:app --reload`, then open `http://localhost:8000` in Chrome.

## Usage

1. Press **듣기 시작** (Start listening).
2. When the other person finishes, press **통역하기** (Translate) to get the translation and reply options.
3. Use the buttons or the text box at the bottom to steer the reply.
4. Open the gear icon to change language, input, mode, opacity, upload a resume, and describe the meeting (for an interview, write the company and role).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MODEL` | `claude-sonnet-5-5` | Claude model used for translation and replies |
| `MLX_MODEL` | `mlx-community/whisper-large-v3-turbo` | Speech model (use `mlx-community/whisper-small-mlx` for a smaller one) |
| `WHISPER_MODEL` | `small` | Fallback model if `mlx-whisper` is not installed |

## Project structure

```
main.py             FastAPI server: transcription, translation, replies, resume
electron-main.js    Electron window and server launcher
preload.js          Bridge for the close and collapse buttons
static/index.html   The interface
requirements.txt    Python dependencies
```

## Privacy

- Audio is transcribed on your machine.
- Transcribed text and your resume text are sent to the Claude API with each request.
- The resume is stored as plain text in `data/` (git-ignored). Delete it from the app at any time.
- Never commit `.env` or `data/`.

## Responsible use

Many interviews and meetings have rules about AI assistance or recording. Check them before using this tool, and tell participants where required. The overlay is visible if you share your whole screen, so share a specific window instead.

## Known limitations

- Tested only on macOS; the audio routing relies on BlackHole.
- The Multi-Output Device does not respond to the keyboard volume keys.
- Overlapping speakers are transcribed as one stream.
