import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

def load_config():
    """
    读取环境变量配置 (支持 .env 文件)
    """
    return {
        "app_id": os.getenv("APP_ID"),
        "app_secret": os.getenv("APP_SECRET"),
        # 不再使用加密 Key
        "encrypt_key": "", 
        "verification_token": os.getenv("APP_VERIFICATION_TOKEN", os.getenv("VERIFICATION_TOKEN")),
        "download_path": os.getenv("DOWNLOAD_PATH", "./downloads")
    }
