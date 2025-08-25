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
from utils.profile_loader import ProfileLoader
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
    
    def analyze_profile(self, profile: MemberProfile, criteria: str, search_type: str = "professional") -> AnalysisResult:
        """Анализ профиля на соответствие критериям
        
        Args:
            profile: Профиль для анализа
            criteria: Критерии поиска
            search_type: "professional" или "personal" - определяет какие поля анализировать
        """
        
        # Prepare profile text based on search type
        if search_type == "personal":
            # Для личного поиска - только личные данные
            profile_text = f"""
            Имя: {profile.name}
            Хобби: {', '.join(profile.hobbies) if profile.hobbies else 'не указаны'}
            Семейное положение: {profile.family_status or 'не указано'}
            """
            system_prompt = """Ты эксперт по анализу личных интересов и предпочтений.
        Твоя задача - определить, соответствует ли профиль заданным личным критериям (хобби, семья)."""
        else:
            # Для профессионального поиска - бизнес данные
            profile_text = f"""
            Имя: {profile.name}
            Экспертиза: {profile.expertise}
            Бизнес: {profile.business}
            """
            system_prompt = """Ты эксперт по анализу бизнес-профилей.
        Твоя задача - определить, соответствует ли профиль заданным профессиональным критериям."""
        
        # Добавляем формат JSON к промпту
        system_prompt += """
        
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
        return ProfileLoader.load_by_name(name)
    
    def smart_analyze(self, criteria: str, search_type: str = "professional", top_k: int = 10) -> List[AnalysisResult]:
        """
        Умный анализ с использованием эмбеддингов
        Анализирует топ-K профилей через LLM, но возвращает ВСЕ профили с их косинусной близостью
        
        Args:
            criteria: Критерии поиска
            search_type: "professional" или "personal"
            top_k: Количество профилей для анализа через LLM (по умолчанию 10)
        """
        results = []
        
        print(f"Getting all profiles with similarity scores ({search_type} mode)...", flush=True)
        
        # 1. Получаем ВСЕ профили с их косинусной близостью
        all_profiles_with_scores = self.embedding_agent.get_all_profiles_with_scores(
            query=criteria,
            search_type=search_type
        )
        
        print(f"Found {len(all_profiles_with_scores)} total profiles", flush=True)
        
        # 2. Создаем словарь для быстрого доступа к scores
        scores_dict = {name: score for name, score in all_profiles_with_scores}
        
        # 3. Анализируем только топ-K через LLM
        top_k_for_llm = all_profiles_with_scores[:top_k]
        analyzed_names = set()
        
        print(f"Analyzing top {len(top_k_for_llm)} candidates with LLM...", flush=True)
        
        for profile_name, similarity_score in top_k_for_llm:
            profile = self.load_profile_by_name(profile_name)
            
            if profile:
                result = self.analyze_profile(profile, criteria, search_type)
                result.similarity_score = similarity_score  # Добавляем косинусную близость
                results.append(result)
                analyzed_names.add(profile_name)
                
                print(f"Analyzed {profile.name}: {'✓' if result.matches else '✗'} (similarity: {similarity_score:.3f})", flush=True)
        
        # 4. Добавляем все остальные профили БЕЗ анализа через LLM
        print(f"Adding remaining {len(all_profiles_with_scores) - len(analyzed_names)} profiles without LLM analysis...", flush=True)
        
        for profile_name, similarity_score in all_profiles_with_scores:
            if profile_name not in analyzed_names:
                # Создаем результат без LLM анализа
                result = AnalysisResult(
                    profile_name=profile_name,
                    matches=False,  # По умолчанию не подходит (не анализировали через LLM)
                    reasoning="",  # Пустое обоснование (не анализировали)
                    similarity_score=similarity_score
                )
                results.append(result)
        
        print(f"Total results: {len(results)} profiles", flush=True)
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