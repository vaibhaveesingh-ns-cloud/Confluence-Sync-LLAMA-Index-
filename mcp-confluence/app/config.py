import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Config:
    # JWT Settings
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
    
    # Confluence OAuth (Cloud)
    CONFLUENCE_CLIENT_ID = os.getenv("CONFLUENCE_CLIENT_ID")
    CONFLUENCE_CLIENT_SECRET = os.getenv("CONFLUENCE_CLIENT_SECRET")
    CONFLUENCE_REDIRECT_URI = os.getenv("CONFLUENCE_REDIRECT_URI", "http://localhost:8001/api/confluence/callback")

    # Confluence Server/Data Center or API Token auth
    CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
    CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
    CONFLUENCE_CLOUD_ID = os.getenv("CONFLUENCE_CLOUD_ID")
    CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")

    # LlamaCloud
    LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")
    LLAMA_CLOUD_PROJECT_ID = os.getenv("LLAMA_CLOUD_PROJECT_ID")

    # Sync settings
    DEFAULT_SYNC_INTERVAL_MINUTES = int(os.getenv("DEFAULT_SYNC_INTERVAL_MINUTES", "60"))
    TEMP_FILES_DIR = os.getenv("TEMP_FILES_DIR", "./temp_files")
    
    # API Settings
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8001"))

config = Config()