import asyncio
from typing import List, Dict, Any
from pathlib import Path
import sys

# Добавляем родительскую директорию в путь для импорта
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from agents.text_analyzer import TextAnalyzerAgent


async def analyze_profiles(criteria: str, search_type: str = "professional") -> List[Dict[str, Any]]:
    """
    Асинхронная обертка для анализа профилей
    
    Args:
        criteria: Критерий поиска
        search_type: Тип поиска ("professional" или "personal")
    
    Returns:
        Список результатов анализа
    """
    
    def _analyze():
        analyzer = TextAnalyzerAgent()
        
        results = analyzer.smart_analyze(
            criteria=criteria,
            search_type=search_type
        )
        
        return [
            {
                "profile_name": result.profile_name,
                "matches": result.matches,
                "reasoning": result.reasoning
            }
            for result in results
        ]
    
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _analyze)
    
    return results