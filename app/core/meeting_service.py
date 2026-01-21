import requests
import lark_oapi as lark
from app.utils.logger import logger
from app.utils.config import load_config
from app.utils.feishu_client import get_tenant_access_token
from app.data.token_store import token_store
from app.core.notification import send_auth_failed_notification

def refresh_user_token_for_user(user_id, current_refresh_token):
    """
    专门为指定用户刷新 Token
    (改用原生 HTTP 请求以避免 SDK 版本兼容性问题)
    """
    logger.info(f"--- [Token刷新] 正在为用户 {user_id} 刷新 Token... ---")
    
    # 1. 获取 Tenant Access Token (接口调用凭证)
    tenant_token = get_tenant_access_token()
    if not tenant_token:
        logger.error("--- [Token刷新失败] 无法获取 Tenant Access Token ---")
        return None, None

    # 2. 调用刷新接口
    url = "https://open.feishu.cn/open-apis/authen/v1/refresh_access_token"
    headers = {
        "Authorization": f"Bearer {tenant_token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    body = {
        "grant_type": "refresh_token",
        "refresh_token": current_refresh_token
    }

    try:
        resp = requests.post(url, headers=headers, json=body)
        data = resp.json()
        
        if data.get("code") != 0:
            logger.error(f"--- [Token刷新失败] Code: {data.get('code')}, Msg: {data.get('msg')} ---")
            return None, None
            
        # 3. 解析结果
        resp_data = data.get("data", {})
        new_access_token = resp_data.get("access_token")
        new_refresh_token = resp_data.get("refresh_token")
        expires_in = resp_data.get("expires_in")
        
        if not new_access_token:
             logger.error(f"--- [Token刷新异常] 响应中缺少 access_token: {data} ---")
             return None, None

        # 4. 保存到 TokenStore
        token_data = {
            "user_access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "expires_in": expires_in
        }
        token_store.save_user_token(user_id, token_data)
        
        logger.info(f"--- [Token刷新成功] 用户 {user_id} Token 已更新 ---")
        return new_access_token, new_refresh_token

    except Exception as e:
        logger.error(f"--- [Token刷新请求异常] {e} ---")
        return None, None

def get_recording_info(meeting_id, user_access_token, user_id=None):
    """
    通过 user_access_token 查询会议录制信息
    权限要求: vc:record:readonly
    增加了 Token 自动刷新机制
    """
    url = f"https://open.feishu.cn/open-apis/vc/v1/meetings/{meeting_id}/recording"
    
    def _do_request(token):
        headers = { "Authorization": f"Bearer {token}" }
        return requests.get(url, headers=headers)

    try:
        resp = _do_request(user_access_token)
        
        # 处理 Token 过期 (401 或 特定错误码)
        if resp.status_code == 401 or (resp.json().get('code') == 99991677):
            logger.warning(f"[API授权过期] 尝试刷新用户 {user_id} 的 Token...")
            if user_id:
                # 获取当前的 Refresh Token
                saved_data = token_store.get_user_token(user_id)
                if saved_data and saved_data.get("refresh_token"):
                    # 刷新
                    new_at, _ = refresh_user_token_for_user(user_id, saved_data["refresh_token"])
                    if new_at:
                        logger.info("[重试] 使用新 Token 重试 API 请求...")
                        resp = _do_request(new_at)
                    else:
                        logger.error("[刷新失败] 无法获取新 Token")
                        send_auth_failed_notification(user_id, meeting_id)
                else:
                    logger.error("[刷新失败] 未找到 Refresh Token")
                    send_auth_failed_notification(user_id, meeting_id)
            else:
                 logger.error("[刷新失败] 未提供 user_id，无法执行刷新")

        if resp.status_code == 200:
            return resp.json()
        else:
            logger.error(f"[获取录制信息失败] Status: {resp.status_code}, Body: {resp.text}")
            return None
    except Exception as e:
        logger.error(f"[API请求异常] {e}")
        return None

def get_meeting_detail(meeting_id, user_access_token):
    """
    获取会议详细信息 (用于生成文件名)
    """
    url = f"https://open.feishu.cn/open-apis/vc/v1/meetings/{meeting_id}"
    headers = {
        "Authorization": f"Bearer {user_access_token}"
    }
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()

        try:
             err_body = resp.json()
             if err_body.get('code') == 99991679:
                 logger.error(f"❌ [权限不足] 现有 Token 缺少 'vc:meeting:readonly' 权限。")
                 logger.error(f"👉 请务必重新访问授权页面 并点击授权，以更新 Token 权限。")
        except Exception:
             pass

        logger.error(f"[获取会议详情失败] Code: {resp.status_code}, Body: {resp.text}")
    except Exception as e:
        logger.error(f"[获取会议详情异常] {e}")
    return None

def get_user_info(user_id, user_access_token):
    """
    获取用户信息 (用于生成文件名)
    """
    url = "https://open.feishu.cn/open-apis/authen/v1/user_info"
    headers = {
        "Authorization": f"Bearer {user_access_token}"
    }
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        logger.error(f"[获取用户信息失败] Code: {resp.status_code} Body: {resp.text}")
    except Exception as e:
        logger.error(f"[获取用户信息异常] {e}")
    return None
