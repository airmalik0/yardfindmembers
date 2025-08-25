from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import re


def sanitize_filename(text: str, max_length: int = 100) -> str:
    """
    Унифицированная санитизация имен файлов
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина результата
        
    Returns:
        Безопасное имя файла
    """
    if not text:
        return "unnamed"
    
    # Удаляем специальные символы, оставляем буквы, цифры, пробелы, дефисы, подчеркивания
    safe_name = re.sub(r'[^\w\s-]', '', text)
    # Заменяем множественные пробелы/дефисы на одно подчеркивание
    safe_name = re.sub(r'[-\s]+', '_', safe_name)
    # Обрезаем до максимальной длины
    safe_name = safe_name[:max_length]
    # Убираем подчеркивания в начале и конце
    safe_name = safe_name.strip('_')
    
    return safe_name if safe_name else "unnamed"


class MemberProfile(BaseModel):
    """Модель профиля участника YARD Business Club"""
    
    name: str = Field(default="", description="ФИО участника")
    expertise: str = Field(default="", description="Экспертиза")
    business: str = Field(default="", description="Бизнес")
    hobbies: List[str] = Field(default_factory=list, description="Хобби")
    family_status: Optional[str] = Field(None, description="Семейное положение")
    contacts: List[str] = Field(default_factory=list, description="Контакты (Instagram, Telegram, WhatsApp, веб-сайты и др.)")
    source_image: Optional[str] = Field(None, description="Исходное изображение")
    
    def to_markdown(self) -> str:
        """Конвертация профиля в Markdown формат"""
        md = f"# {self.name}\n\n"
        
        if self.expertise:
            md += "## Экспертиза\n"
            md += f"{self.expertise}\n\n"
        
        if self.business:
            md += "## Бизнес\n"
            md += f"{self.business}\n\n"
        
        if self.hobbies:
            md += "## Хобби\n"
            for hobby in self.hobbies:
                md += f"- {hobby}\n"
            md += "\n"
        
        if self.family_status:
            md += f"## Семейное положение\n{self.family_status}\n\n"
        
        if self.contacts:
            md += "## Контакты\n"
            for contact in self.contacts:
                md += f"- {contact}\n"
        
        if self.source_image:
            md += f"\n---\n*Источник: {self.source_image}*\n"
        
        return md
    
    def to_sheets_row(self) -> List[str]:
        """Конвертация профиля в строку для Google Sheets (базовые поля)"""
        return [
            self.name,
            self.expertise,
            self.business,
            ", ".join(self.hobbies),
            self.family_status or "",
            ", ".join(self.contacts)
        ]


class AnalysisRequest(BaseModel):
    """Запрос на анализ профилей"""
    criteria: str = Field(..., description="Критерии поиска (например: 'связан с отелями')")
    
    
class AnalysisResult(BaseModel):
    """Результат анализа профиля"""
    profile_name: str
    matches: bool
    reasoning: str = Field(default="", description="Обоснование решения")
    similarity_score: float = Field(default=0.0, description="Косинусная близость к критерию поиска")
    

class WorkflowState(BaseModel):
    """Состояние workflow в LangGraph"""
    image_path: Optional[str] = None
    raw_text: Optional[str] = None
    profile: Optional[MemberProfile] = None
    analysis_request: Optional[AnalysisRequest] = None
    analysis_result: Optional[AnalysisResult] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    was_cached: bool = False  # Флаг, показывающий что профиль был загружен из кэша