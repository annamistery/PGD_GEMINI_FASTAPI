import json
import re
from collections import Counter
# Предполагаем, что импорты остаются прежними
from chashka_points import chashka
from description_zones import description_summarized

# Обновленный словарь соответствия имен точек
main_points = {
    "Точка А": "Первый период 0-30 лет. Характерные уроки и этапы на этот возраст.",
    "Точка Б": "Второй период 30-60 лет. Характерные уроки и этапы на этот возраст.",
    "Точка В": "После 60ти лет. Характерные уроки и этапы на этот возраст.",
    "Точка Г": "Точка входа: то с чем человек пришёл в этот мир. Некий опыт, уже имеющийся с предыдущих жизней. Важно вспомнить и пользоваться им.",
    "Точка Д": {
        "Ж": "Инь, женская сущность. Женское проявленное в социальной сфере, общении, отношениях с другими женщинами.",
        "М": "Фильтр на партнёршу для мужчин"
    },
    "Точка Л": {
        "Ж": "Как проявляется профессионализм – для женской диагностики.",
        "М": "Ожидания в совместной жизни, чего вы хотите от партнёрши или как Вы будете себя с ней вести – для мужской диагностики"
    },
    "Точка Е": {
        "Ж": "Внутренний мужчина или фильтры при выборе партнёра в женской диагностике.",
        "М": "Ян, мужская сущность, проявленная в социальной сфере, общении, отношениях – для мужской диагностики."
    },
    "Точка К": {
        "Ж": "Ожидания от партнёра или поведение с ним - для женской диагностики.",
        "М": "Мужское проявленное в социальной сфере, общении, отношениях."
    },
    "Точка Ж": "Сущность.Способ действия.Самое сильное качество.",
    "Точка З": "Намерение/мотивация ЗАЧЕМ (ты это делаешь)? Характер, данность, пока не станешь осознанным.",
    "Точка И": "Уравновешивающее число. Дзен-сила. Выход. КУДА (реализуешь)?",
    "Точка Й": "Точка выхода. Урок, тот опыт, за которым ты пришёл в эту жизнь, чему нужно научиться во внешнем мире. Ключ к пониманию и представлению.",
    "Точка М": "Внутренняя личность. Внутренний мир. Для женской диагностики",
    "Точка Н": "Соединение внутреннего и внешнего мира. Урок. Для женской диагностики. Витаминчик.",
    "Точка О": "Внутренняя личность. Внутренний мир.Для мужской диагностики.",
    "Точка П": "Соединение внутреннего и внешнего мира. Урок. Для мужской диагностики."
}


class PersonalityCupProcessor:
    # УБРАНО значение по умолчанию для gender
    def __init__(self, cup_dict, main_points, gender):
        self.cup_dict = cup_dict
        self.main_points = main_points
        self.gender = gender
        self.points = []

    def dict_to_list(self):
        """Формирует список точек вида 'Точка А = 9'."""
        self.points = [
            f"{point} = {value}"
            for point, value in self.cup_dict['Основная чашка'].items()
            if value is not None
        ]
        return self.points

    @staticmethod
    def clean_text(text):
        """Очищает текст от лишних пробелов."""
        if not isinstance(text, str):
            return str(text)
        text = text.replace('\n', ' ').replace('\t', ' ')
        text = text.replace("'", "")
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def result(self, chashka_dict):
        """Создаёт словарь описаний с учётом номинала, пола и повторений."""
        temp_results = {}
        dict_list = self.dict_to_list()

        values = [int(item.split('=')[1].strip()) for item in dict_list]
        counts = Counter(values)

        # Точки, требующие проверки гендера внутри базы данных
        gender_sensitive = ["Точка Д", "Точка Л", "Точка Е", "Точка К"]

        for item in dict_list:
            key, val_str = item.split('=')
            key = key.strip()
            val = int(val_str.strip())
            repeat_count = counts.get(val, 0)

            # Правило номинала < 4
            if val < 4:
                index = 0
            else:
                index = 1 if repeat_count >= 4 else 0

            chashka_key = f"{key} = {val}"
            point_data = chashka_dict.get(chashka_key, {})

            # Получаем узел (строка или словарь М/Ж)
            description_node = point_data.get(
                index, f"Нет описания для {chashka_key}")

            # Проверка соответствия гендеру в данных
            if key in gender_sensitive and isinstance(description_node, dict):
                description_text = description_node.get(
                    self.gender, "Описание не найдено")
            else:
                description_text = description_node

            temp_results[key] = f"{val}: {description_text}"

        # ФИНАЛЬНАЯ СБОРКА: замена ключей на описания из main_points
        final_result = {}
        for old_key, description in temp_results.items():
            # Получаем название точки
            point_label_raw = self.main_points.get(old_key, old_key)

            # Если название точки зависит от пола (Д, Л, Е, К)
            if isinstance(point_label_raw, dict):
                point_label = point_label_raw.get(self.gender, old_key)
            else:
                point_label = point_label_raw

            final_result[point_label] = self.clean_text(description)

        return final_result

    def map_descriptions(self, description_dict):
        """Твоя функция — описания для Родовых/Перекрёстка"""
        rodovoy_result = {}
        perekrestok_result = {}
        
        for block_name, block_data in self.cup_dict.items():
            if block_name in ['Родовые данности', 'Перекрёсток']:
                for key, value in block_data.items():
                    if value is not None:
                        desc_text = description_dict.get(str(value), f'Нет описания для {value}')
                        desc = f"{value}: {desc_text}"
                    else:
                        desc = f"Нет значения для {key}"
                    
                    if block_name == 'Родовые данности':
                        rodovoy_result[key] = self.clean_text(desc)
                    else:
                        perekrestok_result[key] = self.clean_text(desc)
        
        return rodovoy_result, perekrestok_result

    def full_result(self, chashka_db, description_dict):
        """Полный результат = чашка + map_descriptions"""
        chashka_desc = self.result(chashka_db)  # старая логика для чашки
        rod_res, per_res = self.map_descriptions(description_dict)
        
        return {
            "Основная чашка": chashka_desc,
            "Родовые данности": rod_res,
            "Перекрёсток": per_res
        }



# ==== Пример запуска ====
if __name__ == '__main__':
    cup_dict = {
        'Основная чашка': {
            'Точка А': 4, 'Точка Б': 12, 'Точка В': 3, 'Точка Г': 19,
            'Точка Д': 6, 'Точка Л': 16, 'Точка Е': 15, 'Точка К': 7,
            'Точка Ж': 9, 'Точка З': 10, 'Точка И': 19, 'Точка Й': 17,
            'Точка М': None, 'Точка Н': None, 'Точка О': 1, 'Точка П': 18
        },
        'Родовые данности': {
            'Родовой способ действия': 12,
            'Родовые отношения с противоположным полом': 0,
            'Родовая цель отношений': 12,
            'Родовая уравновешивающая сила': 2
        },
        'Перекрёсток': {
            'Индивидуальный способ действия': 1,
            'Индивидуальные отношения с противоположным полом': 11,
            'Индивидуальная цель отношений': 12,
            'Индивидуальная уравновешивающая сила': 9
        }
    }

    # ОБЯЗАТЕЛЬНО передаем gender (Ж или М)
    # Обратите внимание: в вашем main_points используется кириллическая "М"
    processor = PersonalityCupProcessor(cup_dict, main_points, gender="М")

    chashka_desc = processor.result(chashka)
    rod_desc, per_desc = processor.map_descriptions(description_summarized)

    processor.save(chashka_desc, rod_desc, per_desc)
