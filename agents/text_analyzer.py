import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import sys

# Добавляем корневую директорию проекта в sys.path
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from utils.data_models import MemberProfile, AnalysisRequest, AnalysisResult, WorkflowState, sanitize_filename
from agents.embedding_agent import EmbeddingAgent
import config


class TextAnalyzerAgent:
    """Агент для анализа и фильтрации профилей по заданным критериям"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.TEXT_MODEL,
            temperature=config.TEMPERATURE,
            api_key=config.OPENAI_API_KEY
        )
        self.embedding_agent = EmbeddingAgent()
    
    def analyze_profile(self, profile: MemberProfile, criteria: str) -> AnalysisResult:
        """Анализ профиля на соответствие критериям"""
        
        # Prepare profile text for analysis
        profile_text = f"""
        Имя: {profile.name}
        Экспертиза: {profile.expertise}
        Бизнес: {profile.business}
        Хобби: {', '.join(profile.hobbies)}
        Семейное положение: {profile.family_status or 'не указано'}
        """
        
        # Create analysis prompt
        system_prompt = """Ты эксперт по анализу бизнес-профилей.
        Твоя задача - определить, соответствует ли профиль заданным критериям.
        
        Верни результат СТРОГО в формате JSON:
        {
            "reasoning": "краткое обоснование решения",
            "matches": true/false
        }
        
        Будь внимателен к деталям."""
        
        user_prompt = f"""Проанализируй профиль на соответствие критерию: "{criteria}"
        
        Профиль:
        {profile_text}
        """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            
            # Parse JSON response
            json_str = response.content
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            
            data = json.loads(json_str)
            
            return AnalysisResult(
                profile_name=profile.name,
                matches=data.get("matches", False),
                reasoning=data.get("reasoning", "")
            )
            
        except Exception as e:
            print(f"Error analyzing profile {profile.name}: {str(e)}", flush=True)
            return AnalysisResult(
                profile_name=profile.name,
                matches=False,
                reasoning=f"Ошибка анализа: {str(e)}"
            )
    
    def load_profile_by_name(self, name: str) -> Optional[MemberProfile]:
        """Загрузка профиля по имени"""
        # Пробуем найти файл с этим именем
        safe_name = name.replace(" ", "_")
        json_file = config.PROFILES_DIR / f"{safe_name}.json"
        
        if json_file.exists():
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                    return MemberProfile(**profile_data)
            except Exception as e:
                print(f"Error loading profile {name}: {str(e)}", flush=True)
        
        # Если не нашли по точному имени, ищем во всех файлах
        for json_file in config.PROFILES_DIR.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                    if profile_data.get("name") == name:
                        return MemberProfile(**profile_data)
            except Exception:
                continue
        
        return None
    
    def smart_analyze(self, criteria: str, search_type: str = "professional") -> List[AnalysisResult]:
        """
        Умный анализ с использованием эмбеддингов
        
        Args:
            criteria: Критерии поиска
            search_type: "professional" или "personal"
        """
        results = []
        
        print(f"Searching with embeddings ({search_type} mode)...", flush=True)
        
        # 1. Поиск топ-30 похожих профилей через эмбеддинги
        similar_profiles = self.embedding_agent.search_similar(
            query=criteria,
            search_type=search_type,
            k=30,
            save_all_scores=True  # Сохраняем все scores для анализа
        )
        
        print(f"Found {len(similar_profiles)} candidates, analyzing with LLM...", flush=True)
        
        # 2. Для каждого кандидата проверяем через LLM
        for profile_name, score in similar_profiles:
            profile = self.load_profile_by_name(profile_name)
            
            if profile:
                result = self.analyze_profile(profile, criteria)
                results.append(result)
                
                print(f"Analyzed {profile.name}: {'✓' if result.matches else '✗'} (similarity: {score:.2f})", flush=True)
        
        return results
    
    def batch_analyze(self, criteria: str) -> List[AnalysisResult]:
        """Анализ всех сохраненных профилей"""
        results = []
        
        # Load all profiles from JSON files
        json_files = list(config.PROFILES_DIR.glob("*.json"))
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                    profile = MemberProfile(**profile_data)
                    
                    result = self.analyze_profile(profile, criteria)
                    results.append(result)
                    
                    print(f"Analyzed {profile.name}: {'✓' if result.matches else '✗'}", flush=True)
                    
            except Exception as e:
                print(f"Error loading profile from {json_file}: {str(e)}", flush=True)
        
        return results
    
    def save_analysis_results(self, results: List[AnalysisResult], criteria: str) -> str:
        """Сохранение результатов анализа"""
        from datetime import datetime
        
        # Create filename with underscores instead of spaces
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_criteria = sanitize_filename(criteria, max_length=50)
        filename = f"analysis_{safe_criteria}_{timestamp}.json"
        
        filepath = config.ANALYSIS_DIR / filename
        
        # Save results
        results_data = {
            "criteria": criteria,
            "timestamp": timestamp,
            "total_profiles": len(results),
            "matched_profiles": sum(1 for r in results if r.matches),
            "results": [r.model_dump() for r in results]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
        
        print(f"Analysis results saved to: {filepath}", flush=True)
        return str(filepath)
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph node function"""
        workflow_state = WorkflowState(**state)
        
        if not workflow_state.analysis_request:
            workflow_state.error = "No analysis request provided"
            return workflow_state.model_dump()
        
        if not workflow_state.profile:
            workflow_state.error = "No profile provided for analysis"
            return workflow_state.model_dump()
        
        # Analyze profile
        result = self.analyze_profile(
            workflow_state.profile,
            workflow_state.analysis_request.criteria
        )
        
        workflow_state.analysis_result = result
        
        return workflow_state.model_dump()