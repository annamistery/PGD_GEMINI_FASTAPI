from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import re

# Импорты ИСХОДНЫХ модулей
PGD_AVAILABLE = LLM_AVAILABLE = False
ai_manager = None

try:
    from pgd_bot import PGD_Person_Mod
    from personality_preprocessor import PersonalityCupProcessor
    from database import main_points, chashka, description_summarized
    PGD_AVAILABLE = True
    print("✅ PGD модули загружены")
except ImportError as e:
    print(f"⚠️ PGD импорт: {e}")

try:
    from ai_service import ModelProcessor
    ai_manager = ModelProcessor()
    if ai_manager.client:
        LLM_AVAILABLE = True
        print("✅ Groq LLM загружен")
    else:
        print("⚠️ GROQ_API_KEY не найден")
except Exception as e:
    print(f"⚠️ LLM импорт: {e}")

app = FastAPI(title="PGD Personality API v2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PersonalityRequest(BaseModel):
    name: str
    dob: str  # dd.MM.yyyy
    gender: str  # Ж/М

class ChatRequest(BaseModel):
    query: str
    context: str = ""
    user_name: str

def safe_json_string(text: str) -> str:
    """Очистка для JSON."""
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', str(text))
    text = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    return text[:8000]

@app.post("/analyze_personality")
async def analyze_personality(request: PersonalityRequest):
    try:
        if not PGD_AVAILABLE:
            return {"error": "PGD недоступен"}

        # 1. Расчёт точек
        person = PGD_Person_Mod(request.name, request.dob, request.gender)
        cup_dict = person.calculate_points()
        
        if isinstance(cup_dict, str):
            return {"error": safe_json_string(cup_dict)}

        # 2. Процессор (передаём весь nested dict)
        processor = PersonalityCupProcessor(cup_dict, main_points, request.gender)
        
        # full_result возвращает DICT с 3 ключами
        pgd_full = processor.full_result(chashka, description_summarized)
        
        chashka_desc = pgd_full.get("Основная чашка", {})
        rod_desc = pgd_full.get("Родовые данности", {})
        per_desc = pgd_full.get("Перекрёсток", {})

        # 3. Форматированный текст
        analysis = f"🌟 PGD-АНАЛИЗ\n👤 {request.name} | {request.dob} | {request.gender}\n\n"
        
        if chashka_desc:
            analysis += "📊 ОСНОВНАЯ ЧАШКА:\n"
            for k, v in list(chashka_desc.items())[:10]:
                analysis += f"• {k}: {str(v)[:150]}...\n"
            analysis += "\n"
        
        if rod_desc:
            analysis += "👥 РОДОВЫЕ ДАННОСТИ:\n"
            for k, v in rod_desc.items():
                analysis += f"• {k}: {str(v)[:150]}...\n"
            analysis += "\n"
        
        if per_desc:
            analysis += "🔄 ПЕРЕКРЁСТОК:\n"
            for k, v in per_desc.items():
                analysis += f"• {k}: {str(v)[:150]}...\n"

        # 4. LLM интерпретация
                # 4. LLM интерпретация (УЖЕ ЕСТЬ В ТВОЕМ КОДЕ)
        full_analysis = analysis
        llm_report_only = ""  # ← НОВОЕ: чистый отчет для чата
        
        if LLM_AVAILABLE and ai_manager and ai_manager.client:
            try:
                user_info = {"name": request.name, "dob": request.dob, "gender": request.gender}
                llm_report_only = ai_manager.get_llm_response(pgd_full, user_info)  # ← генерируем чистый отчет
                full_analysis += f"\n\n🧠 ИИ-ИНТЕРПРЕТАЦИЯ:\n{llm_report_only}"
            except Exception as llm_err:
                print(f"⚠️ LLM ошибка: {llm_err}")
                full_analysis += "\n\n💡 LLM временно недоступен"
        else:
            full_analysis += "\n\n💡 LLM недоступен (проверь GROQ_API_KEY в .env)"

        # ← ВОТ ТУТ НОВЫЙ РЕТЕРН (замени старый):
        return {
            "analysis": safe_json_string(full_analysis),
            "llm_report": safe_json_string(llm_report_only),  # ← ЧИСТЫЙ отчет БЕЗ префиксов для чата!
            "raw_pgd": {
                "Основная чашка": chashka_desc,
                "Родовые данности": rod_desc,
                "Перекрёсток": per_desc
            },
            "pgd_available": PGD_AVAILABLE,
            "llm_available": LLM_AVAILABLE
        }

@app.post("/chat")
async def chat(request: ChatRequest):
    if not LLM_AVAILABLE or not ai_manager or not ai_manager.client:
        return {"reply": "LLM недоступен"}
    
    try:
        # chat_with_report принимает report_text (строку с отчетом) и question (вопрос)
        report_text = request.context  # уже готовый отчет от /analyze_personality
        question = request.query        # новый вопрос пользователя
        
        print(f"💬 Чат: отчет={len(report_text)} символов, вопрос='{question}'")
        
        reply = ai_manager.chat_with_report(report_text, question)
        return {"reply": safe_json_string(reply)}
        
    except Exception as e:
        print(f"❌ Ошибка чата: {e}")
        import traceback
        traceback.print_exc()
        return {"reply": "Ошибка при обработке вопроса. Попробуйте еще раз."}



@app.get("/health")
async def health():
    return {
        "status": "ok",
        "pgd_available": PGD_AVAILABLE,
        "llm_available": LLM_AVAILABLE
    }

@app.get("/")
async def root():
    return {"message": "PGD API работает. Документация: /docs"}

if __name__ == "__main__":
    import uvicorn
    # ОТКЛЮЧАЕМ проблемную логику uvicorn
    uvicorn.run(
        app, 
        host="127.0.0.1", 
        port=8000, 
        reload=True,
        log_config=None  # ← КЛЮЧЕВОЕ: отключает конфликт
    )


