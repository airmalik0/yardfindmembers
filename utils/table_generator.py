import csv
import tempfile
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from pathlib import Path
import json
import sys

parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from utils.data_models import MemberProfile, AnalysisResult
from utils.profile_loader import ProfileLoader
import config


class TableGenerator:
    """Единый генератор таблиц для CSV и Google Sheets"""
    
    @staticmethod
    def prepare_table_data(
        analysis_results: List[AnalysisResult],
        criteria: str,
        mode: str,
        include_all_profiles: bool = True
    ) -> Tuple[List[List[str]], Dict[str, any]]:
        """
        Подготавливает данные для таблицы
        
        Args:
            analysis_results: Результаты анализа с similarity_score
            criteria: Критерий поиска
            mode: Режим поиска (professional/personal)
            include_all_profiles: Включать ли все профили или только подходящие
            
        Returns:
            Tuple[rows, metadata] - строки таблицы и метаданные
        """
        
        # Сортируем результаты:
        # 1. Сначала подходящие (matches=True) по similarity_score
        # 2. Затем остальные по similarity_score
        matched = [r for r in analysis_results if r.matches]
        unmatched = [r for r in analysis_results if not r.matches]
        
        # Сортируем каждую группу по similarity_score (убывание)
        matched.sort(key=lambda x: x.similarity_score, reverse=True)
        unmatched.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # Объединяем в финальный список
        if include_all_profiles:
            sorted_results = matched + unmatched
        else:
            sorted_results = matched
        
        # Загружаем полные профили
        profiles_with_results = []
        for result in sorted_results:
            profile = TableGenerator._load_profile(result.profile_name)
            if profile:
                profiles_with_results.append((profile, result))
        
        # Создаем метаданные
        # Подсчитываем сколько профилей было проанализировано через AI (те у которых есть reasoning)
        analyzed_count = sum(1 for r in analysis_results if r.reasoning)
        
        metadata = {
            'criteria': criteria,
            'mode': 'Профессиональный' if mode == 'professional' else 'Персональный',
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_profiles': len(analysis_results),
            'matched_profiles': len(matched),
            'top_analyzed': analyzed_count  # Количество профилей, проанализированных через LLM
        }
        
        # Формируем строки таблицы
        rows = []
        
        # Заголовок зависит от режима
        if mode == 'professional':
            headers = [
                '№',
                'ФИО',
                'Экспертиза', 
                'Бизнес',
                'Хобби',
                'Семейное положение',
                'Контакты',
                'Обоснование',
                'Косинусная близость',
                'Соответствие'
            ]
        else:  # personal mode
            headers = [
                '№',
                'ФИО',
                'Хобби',
                'Семейное положение',
                'Контакты',
                'Обоснование',
                'Косинусная близость',
                'Соответствие'
            ]
        rows.append(headers)
        
        # Данные
        for i, (profile, result) in enumerate(profiles_with_results, 1):
            if mode == 'professional':
                row = [
                    str(i),
                    profile.name,
                    profile.expertise,
                    profile.business,
                    ', '.join(profile.hobbies) if profile.hobbies else '',
                    profile.family_status or '',
                    ', '.join(profile.contacts) if profile.contacts else '',
                    result.reasoning if result.reasoning else '',
                    f"{result.similarity_score:.3f}" if result.similarity_score else '',
                    '✓' if result.matches else ''
                ]
            else:  # personal mode
                row = [
                    str(i),
                    profile.name,
                    ', '.join(profile.hobbies) if profile.hobbies else '',
                    profile.family_status or '',
                    ', '.join(profile.contacts) if profile.contacts else '',
                    result.reasoning if result.reasoning else '',
                    f"{result.similarity_score:.3f}" if result.similarity_score else '',
                    '✓' if result.matches else ''
                ]
            rows.append(row)
        
        return rows, metadata
    
    @staticmethod
    def generate_csv(
        analysis_results: List[AnalysisResult],
        criteria: str,
        mode: str,
        include_all_profiles: bool = True
    ) -> str:
        """
        Генерирует CSV файл с результатами
        
        Returns:
            Путь к созданному CSV файлу
        """
        rows, metadata = TableGenerator.prepare_table_data(
            analysis_results, criteria, mode, include_all_profiles
        )
        
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(
            mode='w', 
            delete=False, 
            suffix='.csv', 
            encoding='utf-8-sig'
        ) as f:
            writer = csv.writer(f)
            
            # Записываем метаданные
            writer.writerow(['Критерий поиска:', metadata['criteria']])
            writer.writerow(['Режим:', metadata['mode']])
            writer.writerow(['Дата анализа:', metadata['analysis_date']])
            writer.writerow(['Всего профилей:', metadata['total_profiles']])
            writer.writerow(['Найдено соответствий:', metadata['matched_profiles']])
            writer.writerow(['Проанализировано через AI:', metadata['top_analyzed']])
            writer.writerow([])  # Пустая строка
            
            # Записываем таблицу
            for row in rows:
                writer.writerow(row)
            
            return f.name
    
    @staticmethod
    def prepare_sheets_data(
        analysis_results: List[AnalysisResult],
        criteria: str,
        mode: str,
        include_all_profiles: bool = True
    ) -> List[List[str]]:
        """
        Подготавливает данные для Google Sheets
        
        Returns:
            Список строк для записи в Google Sheets
        """
        rows, metadata = TableGenerator.prepare_table_data(
            analysis_results, criteria, mode, include_all_profiles
        )
        
        # Для Google Sheets добавляем метаданные в начало
        sheets_data = []
        
        # Метаданные
        sheets_data.append(['Критерий поиска:', metadata['criteria']])
        sheets_data.append(['Режим:', metadata['mode']])
        sheets_data.append(['Дата анализа:', metadata['analysis_date']])
        sheets_data.append(['Всего профилей:', str(metadata['total_profiles'])])
        sheets_data.append(['Найдено соответствий:', str(metadata['matched_profiles'])])
        sheets_data.append(['Проанализировано через AI:', str(metadata['top_analyzed'])])
        sheets_data.append([])  # Пустая строка
        
        # Добавляем основные данные
        sheets_data.extend(rows)
        
        return sheets_data
    
    @staticmethod
    def _load_profile(name: str) -> Optional[MemberProfile]:
        """Загружает профиль по имени"""
        return ProfileLoader.load_by_name(name)