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

def get_meeting_participants(meeting_id, user_access_token):
    """
    获取会议参会人列表 (用于判断是否有HR)
    [折中方案] 使用 GET /open-apis/vc/v1/meetings/{meeting_id}
    如果 API 返回 participants 字段，则使用它（通常是部分数据，但对检测 HR 足够了）
    """
    url = f"https://open.feishu.cn/open-apis/vc/v1/meetings/{meeting_id}"
    headers = {
        "Authorization": f"Bearer {user_access_token}"
    }
    # 部分接口版本支持 with_participants 参数，尝试加上
    params = {
        "with_participants": "true" 
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params)
        data = resp.json()
        
        if data.get("code") == 0:
            # 尝试提取参会人
            # 结构可能是 data.meeting.participants 或 data.meeting.participant_list
            meeting_data = data.get("data", {}).get("meeting", {})
            participants = meeting_data.get("participants", [])
            
            if participants:
                logger.info(f"[HR检测] 从会议详情中获取到 {len(participants)} 名参会人")
                return participants
            else:
                 logger.warning("[HR检测] 会议详情未返回 participants 字段")
        else:
            logger.warning(f"[HR检测] 获取会议详情失败: {data.get('msg')}")
            
        return []
        
    except Exception as e:
        logger.error(f"[获取参会人异常] {e}")
        return []

def get_department_names_by_ids(department_ids, tenant_access_token):
    """
    批量/多次查询部门名称
    """
    names = []
    if not department_ids:
        return names

    # 简单实现：循环查询 (如果部门多可以考虑优化，但一般人只有1-2个部门)
    # API: GET /open-apis/contact/v3/departments/:department_id
    headers = {"Authorization": f"Bearer {tenant_access_token}"}
    
    for dept_id in department_ids:
        # 缓存优化: 实际项目中这里应该加个 LRU 缓存避免重复查
        url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{dept_id}"
        params = {"department_id_type": "open_department_id"}
        try:
            resp = requests.get(url, headers=headers, params=params)
            data = resp.json()
            if data.get("code") == 0:
                name = data.get("data", {}).get("department", {}).get("name")
                if name:
                    names.append(name)
            else:
                logger.warning(f"[查询部门失败] ID: {dept_id}, Msg: {data.get('msg')}")
        except Exception as e:
            logger.error(f"[查询部门异常] {e}")
    return names

def get_user_departments_from_api(user_id, tenant_access_token):
    """
    从 API 获取用户的部门名称列表
    API: GET /open-apis/contact/v3/users/:user_id
    """
    if not tenant_access_token:
        return []
        
    url = f"https://open.feishu.cn/open-apis/contact/v3/users/{user_id}"
    headers = {"Authorization": f"Bearer {tenant_access_token}"}
    
    # 动态判断 ID 类型: 以 "ou_" 开头则是 open_id，否则默认为 user_id
    id_type = "open_id" if str(user_id).startswith("ou_") else "user_id"
    
    params = {
        "user_id_type": id_type, 
        "department_id_type": "open_department_id"
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params)
        data = resp.json()
        if data.get("code") == 0:
            user_data = data.get("data", {}).get("user", {})
            dept_ids = user_data.get("department_ids", [])
            # 再去查部门详情
            return get_department_names_by_ids(dept_ids, tenant_access_token)
        else:
            logger.warning(f"[API查用户部门失败] Code: {data.get('code')}, Msg: {data.get('msg')}")
            return []
    except Exception as e:
        logger.error(f"[API查用户部门异常] {e}")
        return []

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
