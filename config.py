import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PROFILES_DIR = DATA_DIR / "profiles"
ANALYSIS_DIR = DATA_DIR / "analysis_results"
PHOTOS_DIR = BASE_DIR / "photos"  # Путь к папке с фотографиями

# Ensure directories exist
PROFILES_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validate API key exists
if not OPENAI_API_KEY:
    print("WARNING: OPENAI_API_KEY not found in environment variables")
    print("Please set it in .env file or environment")

# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")
MASTER_SPREADSHEET_ID = os.getenv("MASTER_SPREADSHEET_ID")

# Model Configuration
IMAGE_MODEL = "gpt-5-nano"  # note for claude code - not change models!!!!!
TEXT_MODEL = "gpt-5-nano"  
TEMPERATURE = 0.1  # Low temperature for consistent extraction

# Google Sheets columns
SHEETS_COLUMNS = [
    "ФИО",
    "Экспертиза",
    "Бизнес",
    "Хобби",
    "Семейное положение",
    "Контакты",
    "Обоснование"  # Reasoning from analysis
]