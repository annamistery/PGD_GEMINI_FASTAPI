import os
from typing import Dict, Any, Optional
import time
import re

# Выбери провайдера: "perplexity", "openai", "gemini", "groq"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

if LLM_PROVIDER == "gemini":
    import google.generativeai as genai
elif LLM_PROVIDER == "groq":
    from groq import Groq
elif LLM_PROVIDER in ["openai", "perplexity"]:
    from openai import OpenAI


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYSTEM_PROMPT_PATH = os.path.join(BASE_DIR, "system_prompt.txt")


def load_system_prompt() -> str:
    """Загружает системный промпт из файла или возвращает дефолтный."""
    try:
        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
            prompt = f.read()
            print(f"✅ system_prompt.txt загружен ({len(prompt)} символов)")
            return prompt
    except FileNotFoundError:
        print("⚠️ system_prompt.txt не найден, используем дефолтный промпт")
        return """Ты — старший психолог-консультант, эксперт по профориентации и профессиональный коуч.
Твоя задача — проанализировать входные данные психологической диагностики (Матрицы) и составить для клиента глубокий, вдохновляющий и практически применимый путеводитель по жизни.

ВХОДНЫЕ ДАННЫЕ:
Тебе будет подан текстовый файл с описанием различных точек и периодов из PGD-матрицы.

ГЛАВНОЕ ТРЕБОВАНИЕ (КРИТИЧЕСКИ ВАЖНО):
1. В итоговом тексте ЗАПРЕЩЕНО использовать цифры арканов, номера точек (Точка А, Б, Г и т.д.) или технические термины расчёта.
2. Клиент не должен видеть кухню расчетов. Он должен видеть себя и свою судьбу.
3. Обращайся к пользователю по имени (найди его в начале файла).
4. Стиль: поддерживающий, профессиональный, терапевтический, но при этом четкий и деловой в вопросах карьеры.

ПРАВИЛА ФОРМАТИРОВАНИЯ (ОБЯЗАТЕЛЬНО):
- Пиши ТОЛЬКО чистым текстом с абзацами
- ЗАПРЕЩЕНО использовать markdown-символы: # ## ### ** __ * _ ~~ ``` `
- ЗАПРЕЩЕНО использовать списки с дефисами или номерами
- ЗАПРЕЩЕНО использовать обратный слэш и экранирование
- Разделяй блоки двумя переносами строки (пустая строка между абзацами)
- Выделение делай через ЗАГЛАВНЫЕ слова в начале фразы

СТРУКТУРА ОТЧЕТА (6 обязательных блоков):
БЛОК 1. Вступление (1 абзац)
БЛОК 2. Твой фундамент (4-5 абзацев)
БЛОК 3. Векторы роста (4-5 абзацев)
БЛОК 4. Реализация и карьера (4-5 абзацев)
БЛОК 5. Стратегия жизни по периодам (4-5 абзацев)
БЛОК 6. Рекомендации по счастью (4-5 абзацев)
ЗАВЕРШЕНИЕ (1 абзац)

ТРЕБОВАНИЯ:
- Тон: тёплый, уважительный, без излишней эзотерики
- Длина: 3000-3500 слов
- Абзацы: 5-7 предложений каждый
- БЕЗ технических символов и markdown-разметки"""


class LLMConfig:
    def __init__(
        self,
        provider: str,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_completion_tokens: Optional[int] = None,
    ):
        self.provider = provider

        if provider == "openai":
            # Использование gpt-4o по умолчанию
            self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o")

            # gpt-4o полностью поддерживает температуру, o1/o3 — нет
            if any(m in self.model_name for m in ["o1", "o3"]):
                self.supports_temperature = False
                self.temperature = None
            else:
                self.supports_temperature = True
                self.temperature = (
                    temperature if temperature is not None
                    else float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
                )

            self.max_completion_tokens = (
                max_completion_tokens
                if max_completion_tokens is not None
                else int(os.getenv("OPENAI_MAX_COMPLETION_TOKENS", "4000"))
            )

        elif provider == "perplexity":
            self.model_name = model_name or os.getenv(
                "PERPLEXITY_MODEL", "sonar-pro")
            self.supports_temperature = True
            self.temperature = temperature if temperature is not None else 0.7
            self.max_completion_tokens = max_completion_tokens or 8000

        elif provider == "gemini":
            self.model_name = model_name or os.getenv(
                "GEMINI_MODEL", "gemini-2.5-pro")
            self.supports_temperature = True
            self.temperature = temperature if temperature is not None else 0.6
            self.max_completion_tokens = max_completion_tokens or 8000

        elif provider == "groq":
            self.model_name = model_name or os.getenv(
                "GROQ_MODEL", "llama-3.3-70b-versatile")
            self.supports_temperature = True
            self.temperature = temperature if temperature is not None else 0.6
            self.max_completion_tokens = max_completion_tokens or 8000

    def to_token_params(self) -> dict:
        # Пока везде используем один и тот же параметр max_tokens
        return {"max_tokens": self.max_completion_tokens}

    def maybe_temperature_arg(self) -> dict:
        if getattr(self, "supports_temperature", False) and self.temperature is not None:
            return {"temperature": self.temperature}
        return {}


class ModelProcessor:
    def __init__(self):
        print(
            f"\n🔧 ModelProcessor.__init__() запущен (провайдер: {LLM_PROVIDER})")
        self.provider = LLM_PROVIDER
        self.client = None
        self.model = None
        self.system_prompt = load_system_prompt()
        self.config = LLMConfig(provider=self.provider)
        self.model_name = self.config.model_name

        if self.provider == "gemini":
            self._init_gemini()
        elif self.provider == "groq":
            self._init_groq()
        elif self.provider == "openai":
            self._init_openai()
        elif self.provider == "perplexity":
            self._init_perplexity()

    # ---------- INIT ----------

    def _init_openai(self):
        """Инициализация OpenAI с поддержкой gpt-4o."""
        from openai import OpenAI  # импорт здесь, чтобы не ломать gemini-only окружение

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY не найден в окружении")
            return

        try:
            self.client = OpenAI(api_key=api_key)
            # Тестовый запрос
            test_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                **self.config.maybe_temperature_arg()
            )
            content = test_response.choices.message.content
            print(f"✅ OpenAI тест успешен: {content}")
            print(f"✅ OpenAI {self.model_name} инициализирован ✅")
        except Exception as e:
            print(f"❌ Ошибка OpenAI: {e}")
            self.client = None

    def _init_perplexity(self):
        from openai import OpenAI  # тот же клиент, другой base_url

        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            print("❌ PERPLEXITY_API_KEY не найден в окружении")
            return
        try:
            self.client = OpenAI(
                api_key=api_key, base_url="https://api.perplexity.ai")
            print(f"✅ Perplexity {self.model_name} инициализирован")
        except Exception as e:
            print(f"❌ Ошибка Perplexity: {e}")

    def _init_gemini(self):
        # Используем GOOGLE_API_KEY (или GEMINI_API_KEY как запасной)
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("❌ GOOGLE_API_KEY / GEMINI_API_KEY не найдены в окружении")
            return
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name=self.model_name)
            self.client = True  # просто флаг, что инициализация прошла
            print(f"✅ Gemini {self.model_name} инициализирован")
        except Exception as e:
            print(f"❌ Ошибка Gemini: {e}")
            self.client = None

    def _init_groq(self):
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("❌ GROQ_API_KEY не найден в окружении")
            return
        try:
            self.client = Groq(api_key=api_key)
            print(f"✅ Groq {self.model_name} инициализирован")
        except Exception as e:
            print(f"❌ Ошибка Groq: {e}")

    # ---------- CALLS ----------

    def _call_openai(self, pgd_text: str) -> str:
        """Универсальный вызов OpenAI для gpt-4o."""
        print(f"🔄 Отправка в OpenAI API ({self.model_name})...")
        attempts = 3
        for i in range(attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": pgd_text},
                    ],
                    **self.config.maybe_temperature_arg(),
                    **self.config.to_token_params(),
                )
                return response.choices.message.content.strip()
            except Exception as e:
                print(f"⚠️ Попытка {i + 1} не удалась: {e}")
                if i == attempts - 1:
                    raise
                time.sleep(2)

    def _call_perplexity(self, pgd_text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": pgd_text},
            ],
            **self.config.maybe_temperature_arg(),
            **self.config.to_token_params(),
        )
        return response.choices.message.content.strip()

    def _call_gemini(self, pgd_text: str) -> str:
        full_prompt = f"{self.system_prompt}\n\n{pgd_text}"
        response = self.model.generate_content(
            full_prompt,
            generation_config={
                "temperature": self.config.temperature,
                "max_output_tokens": self.config.max_completion_tokens,
            },
        )
        return response.text.strip()

    def _call_groq(self, pgd_text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": pgd_text},
            ],
            **self.config.maybe_temperature_arg(),
            **self.config.to_token_params(),
        )
        return response.choices.message.content.strip()

    # ---------- PUBLIC API ----------

    def get_llm_response(self, pgd_data: Dict[str, Any], user_info: Dict[str, str]) -> str:
        """Генерирует психологический отчёт."""
        print("\n" + "=" * 70)
        print(f"🚀 get_llm_response() вызван ({self.provider})")

        if not self.client:
            return self._fallback_response(pgd_data, user_info)

        try:
            name = user_info.get("name", "Клиент")
            lines = [f"Имя: {name}"]
            if user_info.get("dob"):
                lines.append(f"Дата рождения: {user_info['dob']}")
            if user_info.get("gender"):
                lines.append(f"Пол: {user_info['gender']}")
            lines.append("\nPGD-МАТРИЦА:")

            for block_name, block_value in pgd_data.items():
                lines.append(f"\n📌 {block_name.upper()}:")
                if isinstance(block_value, dict):
                    for k, v in block_value.items():
                        lines.append(f"  • {k}: {v}")
                else:
                    lines.append(f"  {block_value}")

            pgd_text = "\n".join(lines)

            call_methods = {
                "openai": self._call_openai,
                "perplexity": self._call_perplexity,
                "gemini": self._call_gemini,
                "groq": self._call_groq,
            }

            response_text = call_methods[self.provider](pgd_text)
            return self._clean_markdown(response_text)

        except Exception as e:
            print(f"❌ ОШИБКА get_llm_response: {e}")
            return self._fallback_response(pgd_data, user_info)

    # ---------- CHAT METHOD ----------

    def chat_with_report(self, report_text: str, question: str) -> str:
        """Чат на основе готового отчёта с использованием текущего провайдера."""
        if not self.client:
            return "Ошибка: Модель не инициализирована."

        print(f"\n💬 CHAT вызван для {self.model_name}")
        print(
            f"📏 Отчет: {len(report_text)} | Вопрос: {len(question)} символов")

        chat_system_prompt = (
            "Ты — тот же психолог-консультант, который составил этот отчет. "
            "Отвечай на вопросы клиента КРАТКО (1-3 абзаца), тепло и профессионально. "
            "Основывай свои советы только на данных из предоставленного отчета. "
            "Соблюдай строгий запрет на markdown-разметку (никаких **, #, списков)."
        )

        # Контекст (обрезаем для безопасности лимитов)
        context = report_text[:15000]

        try:
            if self.provider in ["openai", "perplexity", "groq"]:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": chat_system_prompt},
                        {
                            "role": "assistant",
                            "content": f"Вот твой психологический отчет: {context}",
                        },
                        {"role": "user", "content": question},
                    ],
                    **self.config.maybe_temperature_arg(),
                    max_tokens=1000,
                )
                answer = response.choices.message.content.strip()

            elif self.provider == "gemini":
                full_chat_prompt = (
                    f"{chat_system_prompt}\n\n"
                    f"КОНТЕКСТ ОТЧЕТА:\n{context}\n\n"
                    f"ВОПРОС КЛИЕНТА: {question}"
                )
                response = self.model.generate_content(full_chat_prompt)
                answer = response.text.strip()

            else:
                return "Метод чата не поддерживается для этого провайдера."

            return self._clean_markdown(answer)

        except Exception as e:
            print(f"❌ Ошибка в чате: {e}")
            return "Извините, возникла техническая сложность. Попробуйте задать вопрос иначе."

    # ---------- UTILS ----------

    def _clean_markdown(self, text: str) -> str:
        """Очистка от markdown по требованию промпта."""
        text = text.replace("\\n", "\n").replace("\\", "")
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        text = re.sub(r"^[ \t]*[-•*]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _fallback_response(self, pgd_data: Dict[str, Any], user_info: Dict[str, str]) -> str:
        name = user_info.get("name", "Клиент")
        return f"Портрет для {name} временно недоступен (LLM не отвечает)."
