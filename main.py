"""
main.py — PGD API (cleaned & fixed)
"""

import io
import os
import re
import time
import shutil
import tempfile
import threading
import traceback
from typing import Optional

import logging
import asyncio
from fastapi.responses import JSONResponse


from dotenv import load_dotenv
from fastapi import FastAPI, Response, UploadFile, File, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

# --- Optional imports (guarded) ---
DOCX_AVAILABLE = False
PDF_AVAILABLE = False
PIL_AVAILABLE = False
TESSERACT_AVAILABLE = False
BEAUTIFULSOUP_AVAILABLE = False
EDGE_TTS_AVAILABLE = False

try:
    import docx  # python-docx
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as extract_pdf_text
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except Exception:
    TESSERACT_AVAILABLE = False

try:
    import requests
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except Exception:
    BEAUTIFULSOUP_AVAILABLE = False

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
    print("✅ edge-tts загружен")
except Exception as e:
    EDGE_TTS_AVAILABLE = False
    print(f"⚠️ edge-tts импорт: {e}")

# --- PGD / LLM modules (optional) ---
PGD_AVAILABLE = LLM_AVAILABLE = False
ai_manager = None

try:
    from pgd_bot import PGD_Person_Mod
    from personality_preprocessor import PersonalityCupProcessor
    from database import main_points, chashka, description_summarized

    PGD_AVAILABLE = True
    print("✅ PGD модули загружены")
except Exception as e:
    PGD_AVAILABLE = False
    print(f"⚠️ PGD импорт: {e}")

try:
    from ai_service import ModelProcessor

    ai_manager = ModelProcessor()
    if getattr(ai_manager, "client", None):
        LLM_AVAILABLE = True
        print("✅ LLM загружен")
    else:
        LLM_AVAILABLE = False
        print("⚠️ LLM клиент не найден или не инициализирован")
except Exception as e:
    LLM_AVAILABLE = False
    print(f"⚠️ LLM импорт: {e}")

# --- FastAPI app ---
app = FastAPI(title="PGD Personality API (cleaned)")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    # Разрешаем запросы с вашего фронтенда
    allow_origins=[
        "https://pgd-gemini-fastapi.onrender.com",  # Ваш фронтенд на Render
        "http://localhost:5173",                   # Для локальной разработки (Vite)
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Разрешаем все методы (GET, POST, OPTIONS и т.д.)
    allow_headers=["*"],  # Разрешаем все заголовки
)

# --------------------
# Pydantic models
# --------------------


class PersonalityRequest(BaseModel):
    name: str
    dob: str  # dd.MM.yyyy
    gender: str  # Ж/М


class ChatRequest(BaseModel):
    query: str
    context: str = ""
    user_name: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    voice: str = "ru-RU-DariyaNeural"  # default ShortName


class ExtendedAnalysisRequest(BaseModel):
    base_report: str
    attachments_text: str = ""
    user_name: Optional[str] = None


# --------------------
# Utilities
# --------------------


def safe_json_string(text: str, max_len: int = 50000) -> str:
    if text is None:
        return ""
    s = re.sub(r"[\x00-\x1F\x7F-\x9F]", "", str(text))
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "")
    s = s.replace("\n", "\\n")
    return s[:max_len]


def safe_display_text(text: str, max_len: int = 50000) -> str:
    if text is None:
        return ""
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]", "", str(text))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s[:max_len]


# --------------------
# Analyze personality (base)
# --------------------


logger = logging.getLogger("uvicorn.error")

@app.post("/analyze_personality")
async def analyze_personality(request: PersonalityRequest):
    logger.info("analyze_personality START payload=%s", request.dict())
    try:
        if not PGD_AVAILABLE:
            logger.warning("PGD not available")
            return JSONResponse({"error": "PGD модуль недоступен на сервере."})

        person = PGD_Person_Mod(request.name, request.dob, request.gender)
        logger.info("PGD_Person_Mod created for name=%s dob=%s gender=%s", request.name, request.dob, request.gender)

        cup_dict = person.calculate_points()
        logger.info("calculate_points returned type=%s", type(cup_dict).__name__)
        if isinstance(cup_dict, str):
            logger.warning("calculate_points returned error string")
            return JSONResponse({"error": safe_json_string(cup_dict)})

        processor = PersonalityCupProcessor(cup_dict, main_points, request.gender)
        pgd_full = processor.full_result(chashka, description_summarized)
        logger.info("processor.full_result produced keys=%s", list(pgd_full.keys()))

        # Сбор технического анализа (оставляем как есть)
        analysis_technical = (
            f"PGD RAW STRUCTURE\nName: {request.name}\nDOB: {request.dob}\nGender: {request.gender}\n\n"
        )
        # (здесь оставьте существующий код сборки analysis_technical)
        # ...
        llm_report_only = ""
        display_text = ""

        user_info = {"name": request.name, "dob": request.dob, "gender": request.gender}

        if LLM_AVAILABLE and ai_manager and getattr(ai_manager, "client", None):
            logger.info("LLM_AVAILABLE True, calling ai_manager.get_llm_response; ai_manager_client=%s", bool(getattr(ai_manager, "client", None)))
            try:
                maybe = ai_manager.get_llm_response(pgd_full, user_info)
                if asyncio.iscoroutine(maybe):
                    llm_report_only = await maybe
                else:
                    llm_report_only = maybe
                logger.info("LLM returned type=%s len=%s", type(llm_report_only).__name__, len(str(llm_report_only or "")))
                display_text = safe_display_text(llm_report_only or "")
                logger.info("display_text length after safe_display_text=%s", len(display_text or ""))
            except Exception:
                logger.exception("LLM error")
                # fallback: собрать краткий PGD-анализ (как у тебя сейчас)
                # (вставь существующий fallback-код сюда)
                ...
        else:
            logger.info("LLM not available — building fallback summary")
            # (вставь существующий fallback-код сюда)
            ...

        # Диагностическая проверка перед возвратом
        if not display_text:
            logger.warning("display_text is empty; returning diagnostic payload")
            return JSONResponse({
                "display_text": display_text,
                "analysis": safe_json_string(analysis_technical),
                "llm_report": safe_json_string(llm_report_only),
                "debug": {
                    "pgd_keys": list(pgd_full.keys()),
                    "chashka_len": len(str(pgd_full.get('Основная чашка', {}))) if pgd_full else 0,
                    "rod_len": len(str(pgd_full.get('Родовые данности', {}))) if pgd_full else 0,
                    "per_len": len(str(pgd_full.get('Перекрёсток', {}))) if pgd_full else 0,
                    "llm_available": LLM_AVAILABLE,
                    "ai_manager_client": bool(getattr(ai_manager, "client", None))
                }
            })

        logger.info("Returning normal response, display_text length=%s", len(display_text))
        return {
            "display_text": display_text,
            "analysis": safe_json_string(analysis_technical),
            "llm_report": safe_json_string(llm_report_only),
            "raw_pgd": {
                "Основная чашка": pgd_full.get("Основная чашка", {}),
                "Родовые данности": pgd_full.get("Родовые данности", {}),
                "Перекрёсток": pgd_full.get("Перекрёсток", {}),
            },
            "pgd_available": PGD_AVAILABLE,
            "llm_available": LLM_AVAILABLE,
        }

    except Exception as e:
        logger.exception("analyze_personality top-level exception")
        return JSONResponse({"error": safe_json_string(f"Ошибка: {str(e)}")})



# --------------------
# Chat endpoint with per-session limit
# --------------------
MAX_QUESTIONS = 15
SESSION_TTL = 24 * 3600  # seconds

_session_counters = {}
_session_lock = threading.Lock()


def _cleanup_sessions():
    now = time.time()
    with _session_lock:
        expired = [
            sid
            for sid, v in _session_counters.items()
            if now - v.get("last_seen", 0) > SESSION_TTL
        ]
        for sid in expired:
            del _session_counters[sid]


def _increment_session(session_id: str) -> int:
    now = time.time()
    with _session_lock:
        entry = _session_counters.get(session_id)
        if not entry:
            entry = {"count": 0, "last_seen": now}
            _session_counters[session_id] = entry
        entry["count"] += 1
        entry["last_seen"] = now
        return entry["count"]


def _get_session_count(session_id: str) -> int:
    with _session_lock:
        entry = _session_counters.get(session_id)
        return entry["count"] if entry else 0


@app.post("/chat")
async def chat(
    request: Request, payload: ChatRequest, x_session_id: Optional[str] = Header(None)
):
    try:
        _cleanup_sessions()
    except Exception:
        pass

    if x_session_id:
        session_id = x_session_id.strip()
    elif payload.user_name:
        session_id = f"user:{payload.user_name}"
    else:
        client_host = request.client.host if request.client else "unknown"
        minute_bucket = int(time.time() // 60)
        session_id = f"ip:{client_host}:{minute_bucket}"

    if not LLM_AVAILABLE or not ai_manager or not getattr(ai_manager, "client", None):
        return {"reply": "LLM недоступен"}

    current_count = _get_session_count(session_id)
    if current_count >= MAX_QUESTIONS:
        return {
            "reply": (
                f"Достигнут лимит в {MAX_QUESTIONS} вопросов для этой сессии. "
                "Чтобы продолжить, очистите историю чата или начните новую сессиию."
            ),
            "session_id": session_id,
            "questions_used": current_count,
            "limit": MAX_QUESTIONS,
        }

    try:
        report_text = (payload.context or "").strip()
        question = (payload.query or "").strip()
        print(
            f"💬 /chat — session={session_id}, context_len={len(report_text)}, question='{question[:200]}'"
        )

        new_count = _increment_session(session_id)

        if hasattr(ai_manager, "chat_with_report"):
            reply = ai_manager.chat_with_report(report_text, question)
        else:
            prompt = (
                f"Контекст:\n{report_text}\n\nВопрос:\n{question}\n\n"
                "Ответь подробно и практично."
            )
            reply = ai_manager.get_llm_response(prompt)

        return {
            "reply": safe_display_text(reply),
            "session_id": session_id,
            "questions_used": new_count,
            "limit": MAX_QUESTIONS,
        }
    except Exception:
        traceback.print_exc()
        return {"reply": "Ошибка при обработке вопроса. Попробуйте ещё раз."}


# --------------------
# Extended analysis
# --------------------


@app.post("/extended_analysis")
async def extended_analysis(req: ExtendedAnalysisRequest):
    if not LLM_AVAILABLE or not ai_manager or not getattr(ai_manager, "client", None):
        return {"extended": "LLM недоступен"}

    try:
        base = req.base_report or ""
        attachments_text = req.attachments_text or ""
        prompt = (
            f"Базовый отчет:\n{base}\n\n"
            f"Дополнительные данные:\n{attachments_text}\n\n"
            "Задача: на основе базового отчёта и дополнительных данных дай рекомендации по карьерному росту, "
            "сильные стороны, слабые места и практические шаги. Ответь структурированно: "
            "Ключевые сильные стороны, Риски/ограничения, Конкретные шаги (1-3 месяца, 3-12 месяцев), Ресурсы и обучение."
        )

        if hasattr(ai_manager, "generate_recommendations"):
            recommendations = ai_manager.generate_recommendations(
                prompt, user_name=req.user_name
            )
        else:
            recommendations = ai_manager.get_llm_response(prompt)

        return {
            "extended": safe_display_text(recommendations),
            "technical": safe_json_string(recommendations),
        }
    except Exception:
        traceback.print_exc()
        return {
            "error": safe_json_string("Ошибка при генерации расширённого анализа.")
        }


# --------------------
# TTS helpers and endpoints
# --------------------


async def synthesize_edge_tts_bytes(text: str, voice: str) -> bytes:
    if not EDGE_TTS_AVAILABLE:
        raise RuntimeError("edge-tts не установлен на сервере.")
    buf = io.BytesIO()
    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            data = chunk.get("data")
            if isinstance(data, (bytes, bytearray)):
                buf.write(data)
    return buf.getvalue()


@app.post("/tts")
async def tts(request: TTSRequest):
    try:
        text = (request.text or "").strip()
        if not text:
            return {"error": "Текст не может быть пустым"}

        if not EDGE_TTS_AVAILABLE:
            return {
                "error": "edge-tts не установлен на сервере. Установите пакет edge-tts."
            }

        voice = (request.voice or "").strip() or "ru-RU-DariyaNeural"

        audio_bytes = await synthesize_edge_tts_bytes(text, voice)
        if not audio_bytes:
            return {"error": "TTS вернуло пустой результат"}

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"inline; filename=tts_{voice}.mp3"},
        )
    except Exception as e:
        traceback.print_exc()
        return {"error": f"Ошибка TTS на сервере: {e}"}


# --------------------
# File upload and text extraction
# --------------------
MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB


@app.post("/upload_file")
async def upload_file(file: UploadFile = File(...)):
    try:
        suffix = os.path.splitext(file.filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(file.file, tmp)

        text = ""
        try:
            if suffix in [".txt", ".md", ".csv"]:
                with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            elif suffix == ".pdf":
                if not PDF_AVAILABLE:
                    raise HTTPException(
                        status_code=500,
                        detail="pdfminer.six не установлен на сервере.",
                    )
                text = extract_pdf_text(tmp_path)
            elif suffix == ".docx":
                if not DOCX_AVAILABLE:
                    raise HTTPException(
                        status_code=500,
                        detail="python-docx не установлен на сервере.",
                    )
                doc = docx.Document(tmp_path)
                text = "\n".join([p.text for p in doc.paragraphs])
            elif suffix in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
                if not PIL_AVAILABLE:
                    raise HTTPException(
                        status_code=500, detail="Pillow не установлен на сервере."
                    )
                if not TESSERACT_AVAILABLE:
                    raise HTTPException(
                        status_code=500,
                        detail="pytesseract не установлен или Tesseract OCR не доступен.",
                    )
                img = Image.open(tmp_path)
                text = pytesseract.image_to_string(img, lang="rus+eng")
            else:
                try:
                    with open(
                        tmp_path, "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        text = f.read()
                except Exception:
                    text = ""
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        return {"text": text, "filename": file.filename}
    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail="Ошибка при обработке файла на сервере."
        )


# --------------------
# Fetch URL text
# --------------------


def _http_get_text(url: str, timeout: int = 20) -> str:
    if not BEAUTIFULSOUP_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="requests/beautifulsoup не установлены на сервере.",
        )
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PGD-Bot/1.0; +https://example.local/)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        r = requests.get(url, headers=headers,
                         timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except requests.exceptions.HTTPError as e:
        raise HTTPException(
            status_code=502, detail=f"Ошибка при загрузке URL: {e}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=504, detail=f"Сетевая ошибка при доступе к URL: {e}"
        )


@app.post("/fetch_url_text")
async def fetch_url_text(payload: dict):
    if not BEAUTIFULSOUP_AVAILABLE:
        return {"error": "requests и beautifulsoup4 не установлены на сервере."}

    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="No url provided")

    url = url.replace(" ", "%20")

    m = re.search(
        r"https?://(?:docs|drive)\.google\.com/(?:document/d/|document/u/\d+/d/)([a-zA-Z0-9_-]+)",
        url,
    )
    if m:
        doc_id = m.group(1)
        export_url = (
            f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
        )
        try:
            txt = _http_get_text(export_url)
            if "<!doctype html" in txt.lower() or "<html" in txt.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Документ Google Docs требует доступа (не публичный).",
                )
            return {"text": txt}
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=500, detail="Ошибка при получении Google Docs."
            )

    m2 = re.search(r"https?://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if m2:
        file_id = m2.group(1)
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        try:
            txt = _http_get_text(download_url)
            if "<html" in txt.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Файл на Google Drive требует доступа или не является текстовым.",
                )
            return {"text": txt}
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=500, detail="Ошибка при получении Google Drive файла."
            )

    if "drive.google.com/drive/folders" in url:
        raise HTTPException(
            status_code=400,
            detail="Ссылка ведёт на папку Google Drive. Откройте конкретный документ или загрузите файл.",
        )

    try:
        html = _http_get_text(url)
        soup = BeautifulSoup(html, "html.parser")
        for s in soup(["script", "style", "noscript", "header", "footer", "nav", "form"]):
            s.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = "\n".join(lines)
        if not text:
            raise HTTPException(
                status_code=422, detail="Не удалось извлечь текст из страницы."
            )
        return {"text": text}
    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail="Ошибка при извлечении текста."
        )


# --------------------
# Health endpoint
# --------------------


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "pgd_available": PGD_AVAILABLE,
        "llm_available": LLM_AVAILABLE,
        "edge_tts_available": EDGE_TTS_AVAILABLE,
    }
