import asyncio
from typing import List, Dict, Any
from pathlib import Path
import sys

# Добавляем родительскую директорию в путь для импорта
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from agents.text_analyzer import TextAnalyzerAgent


async def analyze_profiles(criteria: str, search_type: str = "professional", top_k: int = 10):
    """
    Асинхронная обертка для анализа профилей
    Теперь возвращает ВСЕ профили с их косинусной близостью
    
    Args:
        criteria: Критерий поиска
        search_type: Тип поиска ("professional" или "personal")
        top_k: Количество профилей для анализа через AI (0-30, по умолчанию 10)
    
    Returns:
        Список объектов AnalysisResult (со всеми полями включая similarity_score)
    """
    
    def _analyze():
        analyzer = TextAnalyzerAgent()
        
        results = analyzer.smart_analyze(
            criteria=criteria,
            search_type=search_type,
            top_k=top_k
        )
        
        # Возвращаем результаты как есть (с similarity_score)
        return results
    
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _analyze)
    
    return results