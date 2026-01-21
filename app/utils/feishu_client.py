import requests
import lark_oapi as lark
from app.utils.config import load_config
from app.utils.logger import logger

def get_tenant_access_token():
    """
    获取 tenant access token (用于机器人发消息)
    """
    config = load_config()
    # 虽然这里构建了 Client，但主要是为了配置，实际请求用的 requests raw call
    # 也可以直接用 client.auth.v3.tenant_access_token.internal(...) 如果版本匹配
    
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    body = {
        "app_id": config.get("app_id"),
        "app_secret": config.get("app_secret")
    }
    
    try:
        resp = requests.post(url, headers=headers, json=body)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("tenant_access_token")
        else:
            logger.error(f"[Tenant Token Error] {data}")
            return None
    except Exception as e:
         logger.error(f"[Tenant Token Exception] {e}")
         return None
