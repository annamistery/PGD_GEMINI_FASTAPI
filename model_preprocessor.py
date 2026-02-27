import os
import streamlit as st
from groq import Groq
import datetime


class ModelProcessor:
    def __init__(self, model_name=None):
        raw_key = os.getenv("GOOGLE_API_KEY")
        self.api_key = str(raw_key).replace('"', '').replace("'", "").strip()

        self.client = Groq(api_key=self.api_key)

        # Обновленный ID модели (актуально на 2026 год)
        self.model_id = "gemini-2.5-pro"
        self.prompt_path = "system_prompt.txt"

    def _load_system_instruction(self):
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "Ты профессиональный психолог и маркетолог."

    def get_llm_response(self, user_data):
        system_instruction = self._load_system_instruction()

        try:
            # Запрос к Groq Cloud
            completion = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Проанализируй данные: {user_data}"}
                ],
                temperature=0.7,
                max_tokens=2048
            )
            return completion.choices[0].message.content

        except Exception as e:
            return f"Ошибка Groq API: {str(e)}"

    def save_report(self, text, user_name):
        if not os.path.exists("reports"):
            os.makedirs("reports")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reports/{user_name}_{timestamp}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        return filename
