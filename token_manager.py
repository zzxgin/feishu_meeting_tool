import json
import os
import time
import threading
import logging

# 获取 Logger
logger = logging.getLogger(__name__)

# 修改：将 Token 文件存放在 user_token 目录下，方便 Docker 挂载持久化
DATA_DIR = "user_token"
TOKEN_FILE = os.path.join(DATA_DIR, "user_tokens.json")
lock = threading.Lock()

class TokenManager:
    def __init__(self):
        # 确保 user_token 目录存在
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "w") as f:
                json.dump({}, f)

    def save_user_token(self, user_id, token_data):
        """保存用户的 Token"""
        with lock:
            tokens = self._load_tokens()
            # 记录保存时间，方便计算过期
            token_data['updated_at'] = int(time.time())
            tokens[user_id] = token_data
            with open(TOKEN_FILE, "w") as f:
                json.dump(tokens, f, indent=4)
            logger.info(f"[TokenManager] 已保存用户 {user_id} 的 Token")

    def get_user_token(self, user_id):
        """获取用户的 Token，如果不存在返回 None"""
        with lock:
            tokens = self._load_tokens()
            return tokens.get(user_id)

    def _load_tokens(self):
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

# 全局单例
token_manager = TokenManager()
