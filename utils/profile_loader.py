"""Единый модуль для загрузки профилей"""
import json
from typing import Optional
from pathlib import Path
from utils.data_models import MemberProfile
import config


class ProfileLoader:
    """Utility класс для загрузки профилей"""
    
    @staticmethod
    def load_by_name(name: str) -> Optional[MemberProfile]:
        """
        Загрузка профиля по имени
        
        Args:
            name: Имя профиля
            
        Returns:
            MemberProfile или None если не найден
        """
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
    
    @staticmethod
    def exists(name: str) -> bool:
        """Проверка существования профиля"""
        return ProfileLoader.load_by_name(name) is not None