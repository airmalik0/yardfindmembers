import base64
import json
from pathlib import Path
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from utils.data_models import MemberProfile, WorkflowState, sanitize_filename
import config


class ImageAnalyzerAgent:
    """Агент для анализа изображений профилей участников YARD Business Club"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.IMAGE_MODEL,
            temperature=config.TEMPERATURE,
            api_key=config.OPENAI_API_KEY
        )
        self.embedding_agent = None  # Lazy loading to avoid circular imports
        
    def encode_image(self, image_path: str) -> str:
        """Кодирование изображения в base64"""
        # Validate path exists and is safe
        image_file = Path(image_path)
        if not image_file.exists() or not image_file.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def _ensure_list(self, value):
        """Преобразование значения в список"""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [value] if value else []
        return []
    
    def analyze_image(self, image_path: str) -> Optional[MemberProfile]:
        """Анализ изображения и извлечение данных профиля"""
        try:
            # Encode image
            base64_image = self.encode_image(image_path)
            
            # Create prompt
            system_prompt = """Ты эксперт по анализу профилей участников YARD Business Club.
            
            На изображении всегда есть следующие секции:
            - ФИО участника (имя и фамилия в заголовке)
            - ЭКСПЕРТИЗА (список областей экспертизы)
            - БИЗНЕС (описание бизнеса и компаний)
            - ХОББИ (список увлечений)
            - Семейное положение (может отсутствовать)
            - Контакты (могут быть Instagram, Telegram, WhatsApp, веб-сайты и другие)
            
            Верни результат СТРОГО в формате JSON:
            {
                "name": "ФИО участника",
                "expertise": "все пункты из секции ЭКСПЕРТИЗА через запятую или \\n если список",
                "business": "полное описание из секции БИЗНЕС с переносами строк",
                "hobbies": ["список хобби"],
                "family_status": "семейное положение если есть",
                "contacts": ["список ВСЕХ контактов в исходном формате - т.е. сайты, телефоны, соц сети и т.д."]
            }
            
            ВАЖНО: 
            1. Извлекай ВСЮ информацию из соответствующих секций
            2. ФИО пиши с заглавных букв на кириллице, НЕ КАПСОМ (пример: Иван Иванов, а не ИВАН ИВАНОВ). Сначала имя потом фамилия.
            3. В поле "business" сохраняй структуру текста - каждый пункт с новой строки через \\n
            4. В поле "expertise" если пункты идут списком, разделяй их через \\n
            5. В поле "contacts" включай ВСЕ контакты. Добавляй префиксы ТОЛЬКО если уверен:
               - Instagram: @username → https://www.instagram.com/username
               - Telegram: @username → https://t.me/username
               - WhatsApp: номер → https://wa.me/номер
               - Facebook: username → https://www.facebook.com/username
               - TikTok: @username → https://www.tiktok.com/@username
               - LinkedIn: username → https://www.linkedin.com/in/username
               - Twitter: username → https://x.com/username
               - YouTube: username → https://www.youtube.com/@username
               - Веб-сайт: добавь https:// если его нет
               ВАЖНО: Если не уверен в типе контакта - оставь как написано на изображении, без префикса!
            6. НЕ включай YBC.UZ в контакты - это сайт бизнес клуба
            7. Если поле отсутствует, установи null"""
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": "Проанализируй это изображение профиля участника YARD Business Club и извлеки всю информацию в формате JSON."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                )
            ]
            
            # Get response
            response = self.llm.invoke(messages)
            
            # Parse JSON from response
            json_str = response.content
            # Clean up JSON if needed
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
                
            data = json.loads(json_str)
            
            # Process and clean data
            profile_data = {
                "name": data.get("name", ""),
                "expertise": data.get("expertise", ""),
                "business": data.get("business", ""),
                "hobbies": data.get("hobbies", []) if data.get("hobbies") else [],
                "family_status": data.get("family_status"),
                "contacts": data.get("contacts", []) if data.get("contacts") else []
            }
            
            # Remove None values
            profile_data = {k: v for k, v in profile_data.items() if v is not None}
            
            return MemberProfile(**profile_data)
            
        except Exception as e:
            print(f"Error analyzing image {image_path}: {str(e)}", flush=True)
            return None
    
    def save_profile_to_file(self, profile: MemberProfile, filename: Optional[str] = None) -> str:
        """Сохранение профиля в текстовый файл"""
        if not filename:
            # Generate filename from name or use default
            if profile.name:
                safe_name = sanitize_filename(profile.name)
                filename = f"{safe_name}.md"
            else:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"profile_{timestamp}.md"
        
        filepath = config.PROFILES_DIR / filename
        
        # Save as markdown
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(profile.to_markdown())
        
        # Also save as JSON for easier parsing
        json_filepath = filepath.with_suffix('.json')
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)
        
        return str(filepath)
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph node function"""
        workflow_state = WorkflowState(**state)
        
        if not workflow_state.image_path:
            workflow_state.error = "No image path provided"
            return workflow_state.model_dump()
        
        # Check if already processed
        from pathlib import Path
        image_path = Path(workflow_state.image_path)
        
        # Check if this image was already processed
        # Проверяем по имени профиля (не зависит от регистра имени файла изображения)
        existing_profiles = list(config.PROFILES_DIR.glob("*.json"))
        for profile_path in existing_profiles:
            with open(profile_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                # Сравниваем имена файлов без учета регистра
                if existing_data.get('source_image') and \
                   existing_data.get('source_image').lower() == image_path.name.lower():
                    print(f"Image already processed: {image_path.name} -> {profile_path.stem}", flush=True)
                    workflow_state.profile = MemberProfile(**existing_data)
                    workflow_state.raw_text = workflow_state.profile.to_markdown()
                    workflow_state.was_cached = True  # Отмечаем, что профиль был загружен из кэша
                    return workflow_state.model_dump()
        
        # Analyze image
        profile = self.analyze_image(workflow_state.image_path)
        
        if profile:
            # Add source image to profile
            profile.source_image = image_path.name
            
            # Save to file
            filepath = self.save_profile_to_file(profile)
            print(f"Profile saved to: {filepath}", flush=True)
            
            # Rename image file if name was extracted
            if profile.name and image_path.exists():
                safe_name = sanitize_filename(profile.name)
                new_image_name = f"{safe_name}{image_path.suffix}"
                new_image_path = image_path.parent / new_image_name
                
                # Check if we need to rename (different name or just case change)
                if image_path.name != new_image_name:
                    # On case-insensitive filesystems (like macOS), we need special handling
                    # Check if it's the same file (case-insensitive match)
                    is_case_only_change = image_path.name.lower() == new_image_name.lower()
                    
                    if is_case_only_change:
                        # It's the same file with different case, need to rename via temp file
                        import uuid
                        temp_name = f"temp_{uuid.uuid4().hex}{image_path.suffix}"
                        temp_path = image_path.parent / temp_name
                        try:
                            image_path.rename(temp_path)
                            temp_path.rename(new_image_path)
                            print(f"Image renamed (case change): {image_path.name} -> {new_image_name}", flush=True)
                            profile.source_image = new_image_name
                            # Re-save profile with updated image name
                            self.save_profile_to_file(profile, Path(filepath).name)
                        except Exception as e:
                            print(f"Could not rename image: {e}", flush=True)
                            # Try to restore original name if temp rename succeeded
                            if temp_path.exists():
                                try:
                                    temp_path.rename(image_path)
                                except:
                                    pass
                    else:
                        # Different file name entirely
                        if new_image_path.exists():
                            print(f"Target image already exists: {new_image_name}", flush=True)
                            profile.source_image = image_path.name  # Keep original name
                        else:
                            try:
                                image_path.rename(new_image_path)
                                print(f"Image renamed: {image_path.name} -> {new_image_name}", flush=True)
                                profile.source_image = new_image_name
                                # Re-save profile with updated image name
                                self.save_profile_to_file(profile, Path(filepath).name)
                            except Exception as e:
                                print(f"Could not rename image: {e}", flush=True)
            
            workflow_state.profile = profile
            workflow_state.raw_text = profile.to_markdown()
        else:
            workflow_state.error = f"Failed to analyze image: {workflow_state.image_path}"
        
        return workflow_state.model_dump()