import streamlit as st
import asyncio
import edge_tts
import os
import re
from datetime import datetime

# Импорт твоих модулей
from personality_preprocessor import PersonalityCupProcessor
from pgd_bot import PGD_Person_Mod
from chashka_points import chashka

# Импорт нашего нового класса
from model_preprocessor import ModelProcessor

# Настройки
# "gemini-1.5-flash" "qwen3-coder:480b-cloud"
MODEL_ID = "gemini-2.5-pro"

# Инициализируем класс в session_state
if 'ai_manager' not in st.session_state:
    st.session_state.ai_manager = ModelProcessor(model_name=MODEL_ID)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---


def clean_text_for_speech(text):
    """Очистка текста от Markdown и спецсимволов для качественной озвучки"""
    # Удаляем жирный шрифт, курсив, заголовки
    text = re.sub(r'[\*\#\_\-\>\<\`]', ' ', text)
    # Удаляем лишние пробелы и переносы
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def generate_voice(text, filename="speech.mp3"):
    """Генерация аудиофайла через Microsoft Edge TTS"""
    if os.path.exists(filename):
        os.remove(filename)

    # Очищаем текст и берем до 5000 символов для полной озвучки
    clean_text = clean_text_for_speech(text)
    final_text = clean_text[:6000]

    if not final_text:
        return None

    communicate = edge_tts.Communicate(final_text, "ru-RU-SvetlanaNeural")
    await communicate.save(filename)
    return filename

# --- ИНТЕРФЕЙС STREAMLIT ---
st.set_page_config(page_title="PGD Диагностика", layout="wide")

st.title("🌟 Проективная психогенетическая карта личности")

with st.expander("📖 Инструкция по применению", expanded=False):
    st.write("""
    1. **Введите данные**: Имя, дату рождения (можно ввести вручную или выбрать в календаре) и пол.
    2. **Анализ**: Нажмите 'Запустить полный анализ'.
    3. **Результат**: Система подготовит текстовый разбор и аудио-версию.
    4. **Чат**: Вы можете задать уточняющие вопросы ИИ внизу страницы.
    """)

# Инициализация состояний
if 'ai_analysis' not in st.session_state:
    st.session_state.ai_analysis = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

with st.sidebar:
    st.header("📋 Данные пользователя")
    name = st.text_input("Имя", value="Анна")

    # Дата рождения с возможностью очистки (крестик)
    dob = st.date_input("Дата рождения", value=None,
                        min_value=datetime(1900, 1, 1), format="DD.MM.YYYY")
    gender = st.radio("Пол", ('Женский', 'Мужской'), horizontal=True)
    process_btn = st.button("🚀 Запустить полный анализ",
                            use_container_width=True)

# --- ЛОГИКА ОБРАБОТКИ ---
if process_btn:
    if not dob or not name:
        st.error("Пожалуйста, введите имя и дату рождения!")
    else:
        progress_bar = st.progress(0)
        with st.status("Выполняю обработку. Это может занять 2-3 минуты..", expanded=True) as status:

            # 1. Расчеты
            st.write("📐 Расчет параметров матрицы...")
            date_str = dob.strftime('%d.%m.%Y')
            sex_char = 'Ж' if gender == "Женский" else 'М'
            person = PGD_Person_Mod(name, date_str, sex_char)
            main_data = person.calculate_points()
            progress_bar.progress(20)

            # 2. Препроцессор
            st.write("🔍 Сбор текстовых описаний...")
            processor = PersonalityCupProcessor(main_data, {}, gender=sex_char)
            raw_description = str(processor.result(chashka))
            progress_bar.progress(40)

            # 3. Нейросеть
            st.write(f"🧠 Сервис формирует отчет для {name}...")
            # Мы добавляем имя пользователя прямо в начало данных, чтобы ИИ его увидел
            # В блоке обработки (кнопка):
            data_with_context = f"ИМЯ ПОЛЬЗОВАТЕЛЯ: {name}\nДАННЫЕ ДИАГНОСТИКИ:\n{raw_description}"
            ai_text = st.session_state.ai_manager.get_llm_response(
                data_with_context)
            st.session_state.ai_analysis = ai_text
            progress_bar.progress(80)

            # 4. Голос и сохранение (Озвучиваем ПОЛНЫЙ текст до 5к символов)
            st.write("🎙 Синтез речи и сохранение файла...")
            st.session_state.ai_manager.save_report(ai_text, name)
            asyncio.run(generate_voice(ai_text))

            progress_bar.progress(100)
            status.update(label="✅ Обработка успешно завершена!",
                          state="complete")
        st.balloons()

# --- ВЫВОД РЕЗУЛЬТАТОВ ---
if st.session_state.ai_analysis:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📄 Ваш персональный анализ")
        st.markdown(st.session_state.ai_analysis)

    with col2:
        st.subheader("📥 Результаты")
        if os.path.exists("speech.mp3"):
            st.write("🎵 Аудио-версия отчета:")
            st.audio("speech.mp3")

        st.download_button(
            label="💾 Скачать текстовый отчет",
            data=st.session_state.ai_analysis,
            file_name=f"Result_{name}_{datetime.now().strftime('%d%m%Y')}.txt",
            mime="text/plain"
        )

    st.divider()

    # --- ЧАТ ---
    st.subheader("💬 Диалог с вашим профилем")
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if query := st.chat_input("Задайте уточняющий вопрос..."):
        st.session_state.chat_history.append(
            {"role": "user", "content": query})
        with st.chat_message("user"):
            st.write(query)

        with st.chat_message("assistant"):
            with st.spinner("Анализирую..."):
                chat_context = f"Это диагностика пользователя {name}: {st.session_state.ai_analysis}. Ответь на вопрос: {query}"
                response = st.session_state.ai_manager.get_llm_response(
                    chat_context, is_chat=True)
                st.write(response)
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": response})
