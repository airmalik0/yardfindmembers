import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import sys

# Добавляем корневую директорию проекта в sys.path
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
from utils.data_models import MemberProfile, sanitize_filename
import config


class EmbeddingAgent:
    """Агент для работы с эмбеддингами профилей через ChromaDB"""
    
    def __init__(self):
        # Инициализация эмбеддингов OpenAI
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=config.OPENAI_API_KEY
        )
        
        # Путь к ChromaDB
        self.persist_directory = str(config.DATA_DIR / "chroma_db")
        
        # Инициализация двух коллекций
        self.professional_db = Chroma(
            collection_name="professional_profiles",
            embedding_function=self.embeddings,
            persist_directory=f"{self.persist_directory}/professional"
        )
        
        self.personal_db = Chroma(
            collection_name="personal_profiles",
            embedding_function=self.embeddings,
            persist_directory=f"{self.persist_directory}/personal"
        )
    
    def _create_professional_text(self, profile: MemberProfile) -> str:
        """Создание текста для профессионального эмбеддинга"""
        parts = []
        
        # Имя всегда добавляем
        parts.append(f"Имя: {profile.name}")
        
        # Бизнес - самое важное для профессионального поиска
        if profile.business:
            parts.append(f"Бизнес и деятельность: {profile.business}")
        
        # Экспертиза тоже важна
        if profile.expertise:
            parts.append(f"Экспертиза и навыки: {profile.expertise}")
        
        # Контакты меньше влияют на семантический поиск
        if profile.contacts and len(profile.contacts) > 0:
            # Берем только названия компаний/сайтов из контактов
            company_contacts = [c for c in profile.contacts if not c.startswith('+') and '@' not in c]
            if company_contacts:
                parts.append(f"Связанные компании: {', '.join(company_contacts)}")
        
        return " ".join(parts)
    
    def _create_personal_text(self, profile: MemberProfile) -> str:
        """Создание текста для личного эмбеддинга"""
        parts = [profile.name]
        
        if profile.hobbies:
            parts.extend(profile.hobbies)
        
        if profile.family_status:
            parts.append(profile.family_status)
        
        return " ".join(parts)
    
    def index_profile(self, profile: MemberProfile) -> None:
        """Индексация одного профиля в обе коллекции"""
        # Создаем тексты для эмбеддингов
        professional_text = self._create_professional_text(profile)
        personal_text = self._create_personal_text(profile)
        
        # Создаем уникальный ID на основе имени (для предотвращения дубликатов)
        profile_id = sanitize_filename(profile.name, max_length=100)
        
        # Метаданные профиля
        metadata = {
            "name": profile.name,
            "source": profile.source_image or "unknown"
        }
        
        # Создаем документы с явным ID
        professional_doc = Document(
            page_content=professional_text,
            metadata={**metadata, "type": "professional"}
        )
        
        personal_doc = Document(
            page_content=personal_text,
            metadata={**metadata, "type": "personal"}
        )
        
        # Используем upsert через add_documents с ID для предотвращения дубликатов
        # ChromaDB автоматически заменит документ с тем же ID
        self.professional_db.add_documents([professional_doc], ids=[f"prof_{profile_id}"])
        self.personal_db.add_documents([personal_doc], ids=[f"pers_{profile_id}"])
        
        print(f"Indexed profile: {profile.name}", flush=True)
    
    def batch_index_all_profiles(self) -> int:
        """Индексация всех профилей из директории"""
        json_files = list(config.PROFILES_DIR.glob("*.json"))
        indexed_count = 0
        self._profile_count = len(json_files)  # Сохраняем для оптимизации поиска
        
        print(f"Found {len(json_files)} profiles to index", flush=True)
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                    profile = MemberProfile(**profile_data)
                    self.index_profile(profile)
                    indexed_count += 1
            except Exception as e:
                print(f"Error indexing {json_file}: {str(e)}", flush=True)
        
        # В новой версии ChromaDB изменения сохраняются автоматически
        
        print(f"Successfully indexed {indexed_count} profiles", flush=True)
        return indexed_count
    
    def search_similar(self, query: str, search_type: str = "professional", k: int = 30, save_all_scores: bool = True) -> List[Tuple[str, float]]:
        """
        Поиск похожих профилей
        
        Args:
            query: Текст запроса
            search_type: "professional" или "personal"
            k: Количество результатов
            save_all_scores: Сохранять ли все scores в файл
            
        Returns:
            Список кортежей (имя_профиля, score)
        """
        # Выбираем базу
        db = self.professional_db if search_type == "professional" else self.personal_db
        
        # Получаем профили с их scores
        if save_all_scores:
            # Получаем все профили для полной картины
            # Используем большое число, чтобы получить все профили из базы
            max_results = self._profile_count if hasattr(self, '_profile_count') else 1000
            all_results = db.similarity_search_with_score(query, k=max_results)
        else:
            all_results = db.similarity_search_with_score(query, k=k)
        
        # Извлекаем имена и scores
        all_profile_scores = []
        profile_scores = []
        seen_names = set()
        
        for doc, score in all_results:
            name = doc.metadata.get("name")
            if name and name not in seen_names:
                all_profile_scores.append((name, score))
                if len(profile_scores) < k:
                    profile_scores.append((name, score))
                seen_names.add(name)
        
        # Сохраняем все scores в файл
        if save_all_scores and all_profile_scores:
            self._save_embedding_scores(query, search_type, all_profile_scores)
        
        return profile_scores
    
    def _save_embedding_scores(self, query: str, search_type: str, scores: List[Tuple[str, float]]) -> None:
        """Сохранение всех embedding scores в файл для анализа"""
        from datetime import datetime
        
        # Создаем директорию для scores если нужно
        scores_dir = config.DATA_DIR / "embedding_scores"
        scores_dir.mkdir(exist_ok=True)
        
        # Создаем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = sanitize_filename(query, max_length=50)
        filename = f"scores_{search_type}_{safe_query}_{timestamp}.json"
        
        filepath = scores_dir / filename
        
        # Сортируем по score (меньше = лучше для cosine distance)
        sorted_scores = sorted(scores, key=lambda x: x[1])
        
        # Готовим данные для сохранения
        data = {
            "query": query,
            "search_type": search_type,
            "timestamp": timestamp,
            "total_profiles": len(sorted_scores),
            "scores": [
                {
                    "rank": i + 1,
                    "name": name,
                    "score": float(score),
                    "similarity_percent": max(0, (1 - float(score)) * 100)  # Конвертируем distance в similarity %
                }
                for i, (name, score) in enumerate(sorted_scores)
            ]
        }
        
        # Сохраняем
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"Saved all embedding scores to: {filepath}", flush=True)
    
    def clear_all_indexes(self) -> None:
        """Очистка всех индексов (для отладки)"""
        # Используем альтернативный подход - очищаем коллекции без удаления директорий
        
        try:
            # Получаем все ID документов и удаляем их
            # Для professional_db
            try:
                prof_ids = self.professional_db.get()["ids"]
                if prof_ids:
                    self.professional_db.delete(ids=prof_ids)
                    print(f"Deleted {len(prof_ids)} documents from professional index", flush=True)
            except Exception as e:
                print(f"Note: Could not clear professional index: {e}", flush=True)
            
            # Для personal_db
            try:
                pers_ids = self.personal_db.get()["ids"]
                if pers_ids:
                    self.personal_db.delete(ids=pers_ids)
                    print(f"Deleted {len(pers_ids)} documents from personal index", flush=True)
            except Exception as e:
                print(f"Note: Could not clear personal index: {e}", flush=True)
                
        except Exception as e:
            print(f"Warning during index clearing: {e}", flush=True)
            # Если что-то пошло не так, пробуем пересоздать с нуля
            import shutil
            import os
            
            # Удаляем всю директорию ChromaDB как fallback
            if os.path.exists(self.persist_directory):
                try:
                    shutil.rmtree(self.persist_directory)
                except Exception as rm_error:
                    print(f"Could not remove directory: {rm_error}", flush=True)
            
            # Пересоздаем базы
            professional_dir = f"{self.persist_directory}/professional"
            personal_dir = f"{self.persist_directory}/personal"
            
            self.professional_db = Chroma(
                collection_name="professional_profiles",
                embedding_function=self.embeddings,
                persist_directory=professional_dir
            )
            
            self.personal_db = Chroma(
                collection_name="personal_profiles",
                embedding_function=self.embeddings,
                persist_directory=personal_dir
            )
        
        print("All indexes cleared", flush=True)