import json, os, re, threading
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from anthropic import AsyncAnthropic

MODEL = os.getenv("MODEL", "claude-haiku-5-5")  # 빠른 응답용. 품질을 높이려면 claude-sonnet-5-5
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
print("KEY LOADED:", bool(os.getenv("ANTHROPIC_API_KEY")), flush=True)
client = AsyncAnthropic()
app = FastAPI()


class Turn(BaseModel):
    speaker: str  # "them" | "me"
    text: str


class Req(BaseModel):
    text: str = ""            # 방금 들린 상대방 발화
    idea: str = ""            # (선택) 내가 하고 싶은 말을 내 언어로 대충 적은 것
    my_lang: str = "Korean"
    meeting_lang: str = "English"
    context: str = ""         # 미팅 배경 / 내 역할
    history: list[Turn] = []
    want_replies: bool = True
    length: str = "medium"    # short | medium | long


SYSTEM = """You are a real-time meeting interpreter and reply assistant.
You receive JSON with: my_lang, meeting_lang, context, history, text (what the other person just said), idea (optional: what I want to say, in my_lang).

Return ONLY a JSON object, no markdown fences:
{
  "translation": "<text translated into my_lang; empty string if text is empty>",
  "replies": [
    {"label": "<2-4 word intent label in my_lang>", "text": "<reply written in meeting_lang, natural spoken style, 2-4 sentences>", "gloss": "<same reply translated to my_lang so I know what I'm saying>"}
  ]
}

Rules:
- Translate faithfully and naturally; keep names, numbers and technical terms accurate.
- If want_replies is false, return "replies": [].
- If idea is empty: give exactly 5 replies. Every reply must be a substantive statement or direct answer to what the other person said, NOT a question. If they asked a question, each reply answers it from a different stance. Use these 5 stances, one each: (1) agree and support, (2) agree and add a concrete point or example, (3) share a cautious or nuanced view, (4) politely disagree or raise a concern, (5) commit to a concrete next step (use placeholders like [date] if details are missing).
- If idea is non-empty, it is my instruction in my_lang about the reply I want. It is either what I want to say, or a directive about the kind of reply (e.g. answer their question, ask a question about what they said, agree and add my opinion, push back politely, buy time). Follow it exactly. Base the reply on the most recent 'them' turn in history (text may be empty). Give exactly 3 versions in meeting_lang that differ in tone or length (casual, neutral, formal). Obey any length or tone request inside the instruction. If the instruction asks me to ask a question, the replies must be questions. Do not add commitments or facts I did not provide; use placeholders like [date] where needed.
- Never invent facts, dates, or promises that are not in the context or history. If a reply needs info you lack, use a safe placeholder like [date].
"""


def parse_json(raw: str) -> dict:
    a, b = raw.find("{"), raw.rfind("}")
    if a == -1 or b == -1:
        raise json.JSONDecodeError("no json", raw, 0)
    return json.loads(raw[a:b + 1])


@app.post("/api/process")
async def process(req: Req):
    payload = req.model_dump()
    payload["history"] = payload["history"][-8:]
    try:
        msg = await client.messages.create(
            model=MODEL,
            max_tokens=6000,
            system=system_prompt(req.length),
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return parse_json(text)
    except json.JSONDecodeError:
        raise HTTPException(502, "모델 응답을 해석하지 못했어요. 다시 시도해 주세요.")
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")



# ---- 이력서 저장 (data/ 폴더에 텍스트로 보관) ----
DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
RESUME_TXT = DATA / "resume.txt"
RESUME_META = DATA / "resume.json"

RESUME_RULES = """
MY RESUME is provided below. Use it to ground replies about my background (interview-style questions about experience, skills, projects, education, motivation).
- Answer in first person as me, using concrete details from the resume (projects, tools, results). For behavioral questions, use a brief situation-action-result structure when the resume supports it.
- Never invent employers, dates, numbers, skills, or achievements that are not in the resume. If the question goes beyond the resume, answer truthfully using the closest real experience, or use a placeholder like [detail].
- Fit the answer to the role or interview described in the meeting context.
"""


def load_resume():
    return RESUME_TXT.read_text(encoding="utf-8") if RESUME_TXT.exists() else ""


LENGTHS = {
    "short": "Keep every reply to ONE short sentence (under about 20 words). The gloss is equally short.",
    "medium": "Keep every reply to 2-3 sentences.",
    "long": "Make every reply detailed: 4-6 sentences (about 80-120 words) with a reason or a concrete example. The gloss mirrors it.",
}


def length_rule(length):
    return "\nREPLY LENGTH RULE (overrides any sentence count stated above): " + LENGTHS.get(length, LENGTHS["medium"]) + "\n"


def system_prompt(length="medium"):
    s = SYSTEM + length_rule(length)
    r = load_resume()
    if r:
        s += "\n" + RESUME_RULES + "\n--- RESUME ---\n" + r
    return s


def extract_text(name, raw):
    import io
    ext = name.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        from pypdf import PdfReader
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(raw)).pages)
    if ext == "docx":
        import docx
        return "\n".join(pp.text for pp in docx.Document(io.BytesIO(raw)).paragraphs)
    return raw.decode("utf-8", errors="ignore")


@app.post("/api/resume")
async def upload_resume(request: Request, name: str = "resume.txt"):
    raw = await request.body()
    try:
        text = extract_text(name, raw).strip()
    except Exception as e:
        raise HTTPException(400, f"파일을 읽지 못했어요: {e}")
    if len(text) < 50:
        raise HTTPException(400, "글자를 거의 읽지 못했어요. 이미지로 스캔한 PDF라면 텍스트가 있는 PDF나 docx로 올려 주세요.")
    text = text[:15000]
    RESUME_TXT.write_text(text, encoding="utf-8")
    RESUME_META.write_text(json.dumps({"name": name, "chars": len(text)}, ensure_ascii=False))
    return {"name": name, "chars": len(text)}


@app.get("/api/resume")
async def get_resume():
    return json.loads(RESUME_META.read_text()) if RESUME_META.exists() else {}


@app.delete("/api/resume")
async def delete_resume():
    for f in (RESUME_TXT, RESUME_META):
        f.unlink(missing_ok=True)
    return {}

_whisper = None
_lock = threading.Lock()
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")  # 더 빠르게: base / 더 정확하게: medium


MLX_MODEL = os.getenv("MLX_MODEL", "mlx-community/whisper-large-v3-turbo")  # 가볍게: mlx-community/whisper-small-mlx
_backend = None


def _transcribe(audio, lang):
    global _whisper, _backend
    with _lock:
        if _backend in (None, "mlx"):
            try:
                import mlx_whisper
                if _backend is None:
                    print("STT: mlx-whisper (Apple GPU) -", MLX_MODEL, flush=True)
                    _backend = "mlx"
                r = mlx_whisper.transcribe(
                    audio, path_or_hf_repo=MLX_MODEL, language=lang,
                    condition_on_previous_text=False)
                return r["text"].strip()
            except ImportError:
                print("STT: mlx-whisper 없음 -> faster-whisper(CPU) 사용", flush=True)
                _backend = "fw"
        if _whisper is None:
            from faster_whisper import WhisperModel
            _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segs, _ = _whisper.transcribe(audio, language=lang, vad_filter=True, beam_size=1)
        return " ".join(x.text.strip() for x in segs).strip()


@app.post("/api/transcribe")
async def transcribe(request: Request, lang: str = "en"):
    raw = await request.body()  # 16kHz mono int16 PCM
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if len(audio) < 8000:
        return {"text": ""}
    text = await run_in_threadpool(_transcribe, audio, lang)
    return {"text": text}


# ---- Claude와 대화 (답변을 같이 다듬기) ----
class Msg(BaseModel):
    role: str
    content: str


class ChatReq(BaseModel):
    messages: list[Msg]
    context: str = ""
    meeting_lang: str = "English"
    length: str = "medium"
    history: list[Turn] = []
    replies: list[dict] = []


CHAT_SYSTEM = """You are the assistant built into my live meeting copilot. I talk to you in Korean while a meeting is going on, to refine what I will say.
You can: rewrite or adjust the current reply options (shorter, longer, warmer, firmer, more formal, different stance), write new replies for a direction I describe, explain what the other person meant, suggest what to say or ask, and answer quick questions about the meeting.

Return ONLY a JSON object, no markdown fences:
{"message": "<short Korean answer, 1-3 sentences, no filler>", "replies": null}
- If I ask to change, rewrite, or produce replies, set "replies" to a list of 1-5 objects {"label": "<2-4 word Korean label>", "text": "<reply in the meeting language, natural spoken style>", "gloss": "<Korean translation of that reply>"}. Otherwise set "replies" to null.
- When I refer to a reply by number ("2번"), use the numbering of CURRENT REPLY OPTIONS. If I only ask to change one, return just the revised one unless I ask for all.
- Follow length and tone requests in my message. Otherwise obey the default REPLY LENGTH RULE.
- Never invent facts, dates, numbers, or commitments I have not given you; use placeholders like [date].
- Be concise: the message is read in the middle of a meeting.
"""


def chat_prompt(req):
    conv = "\n".join(("THEM: " if t.speaker == "them" else "ME: ") + t.text for t in req.history[-12:]) or "(nothing yet)"
    cur = json.dumps(req.replies, ensure_ascii=False) if req.replies else "(none yet)"
    s = (CHAT_SYSTEM + length_rule(req.length)
         + f"\nMEETING LANGUAGE: {req.meeting_lang}\nMEETING CONTEXT: {req.context or '(not provided)'}"
         + f"\n\nRECENT CONVERSATION (translated originals):\n{conv}\n\nCURRENT REPLY OPTIONS (numbered in order):\n{cur}\n")
    r = load_resume()
    if r:
        s += "\n" + RESUME_RULES + "\n--- RESUME ---\n" + r
    return s


@app.post("/api/chat")
async def chat(req: ChatReq):
    msgs = [{"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in req.messages if m.content.strip()]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        raise HTTPException(400, "메시지가 비어 있어요.")
    try:
        msg = await client.messages.create(model=MODEL, max_tokens=6000, system=chat_prompt(req), messages=msgs)
        text = "".join(b.text for b in msg.content if b.type == "text")
        try:
            return parse_json(text)
        except json.JSONDecodeError:
            return {"message": text.strip(), "replies": None}   # JSON이 아니어도 대화는 보여준다
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
