import json
import os
import requests
import lark_oapi as lark
from token_manager import token_manager
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

def get_tenant_access_token():
    """
    获取 tenant access token (用于机器人发消息)
    """
    config = load_config()
    client = lark.Client.builder() \
        .app_id(config.get("app_id")) \
        .app_secret(config.get("app_secret")) \
        .build()
    
    # 使用 Internal/Old 方式构建 (适配不同版本的 SDK)
    # 如果是 SDK v2.x 或 v1.x，结构可能是 lark.api.authen.v1.model.CreateTenantAccessTokenReq
    # 这里使用万能的 raw request 方式，避免 SDK 版本差异
    
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
            print(f"[Tenant Token Error] {data}")
            return None
    except Exception as e:
         print(f"[Tenant Token Exception] {e}")
         return None

def send_success_notification(user_id, file_name):
    """
    发送下载成功通知卡片
    """
    token = get_tenant_access_token()
    if not token:
        return

    # 卡片内容
    card_content = {
        "config": {
            "wide_screen_mode": True
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "content": f"✅ **会议录制已自动存档**\n📄 文件名：{file_name}",
                    "tag": "lark_md"
                }
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "content": "文件已保存至服务器 downloads 目录",
                        "tag": "lark_md"
                    }
                ]
            }
        ],
        "header": {
            "template": "blue",
            "title": {
                "content": "下载完成通知",
                "tag": "plain_text"
            }
        }
    }

    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    params = {"receive_id_type": "user_id"}
    body = {
        "receive_id": user_id,
        "msg_type": "interactive",
        "content": json.dumps(card_content)
    }

    try:
        resp = requests.post(url, headers=headers, params=params, json=body)
        if resp.status_code != 200:
             print(f"[消息发送失败] {resp.json()}")
        else:
             print(f"[消息发送成功] 通知已发送给用户 {user_id}")
    except Exception as e:
        print(f"[消息发送异常] {e}")

def refresh_user_token_for_user(client, user_id, current_refresh_token):
    """
    专门为指定用户刷新 Token
    """
    print(f"--- [Token刷新] 正在为用户 {user_id} 刷新 Token... ---")
    
    # 构建请求
    req = lark.api.authen.v1.RefreshAccessTokenReq.builder() \
        .body(lark.api.authen.v1.RefreshAccessTokenReqBody.builder()
            .grant_type("refresh_token")
            .refresh_token(current_refresh_token)
            .build()) \
        .build()

    # 发起请求
    try:
        resp = client.authen.v1.access_token.refresh(req)
    except Exception as e:
        print(f"--- [Token刷新异常] {e} ---")
        return None, None

    if not resp.success():
        print(f"--- [Token刷新失败] {resp.code}, {resp.msg}, log_id: {resp.get_log_id()} ---")
        return None, None

    # 解析结果
    new_access_token = resp.data.access_token
    new_refresh_token = resp.data.refresh_token
    expires_in = resp.data.expires_in
    
    # 保存到 TokenManager
    token_data = {
        "user_access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "expires_in": expires_in
    }
    token_manager.save_user_token(user_id, token_data)
    
    print(f"--- [Token刷新成功] 用户 {user_id} Token 已更新 ---")
    return new_access_token, new_refresh_token

def download_single_video(object_token, user_id, user_access_token=None, meeting_id=None):
    """
    下载单个视频
    """
    config = load_config()
    
    # 如果没有传 Token（比如还没登录），就无法下载私有视频
    if not user_access_token:
        print(f"[错误] 缺少 User Token，无法下载用户 {user_id} 的视频")
        return

    # 创建 API Client (用于刷新 Token)
    client = lark.Client.builder() \
        .app_id(config.get("app_id")) \
        .app_secret(config.get("app_secret")) \
        .build()

    print(f"[处理中] 妙计Token: {object_token} | Owner: {user_id}")
    
    # --- 1. 获取文件名所需的元数据 (用户+会议名+时间) ---
    file_name_prefix = object_token # 默认用 token
    try:
        if meeting_id:
            meeting_info = get_meeting_detail(meeting_id, user_access_token)
            user_info = get_user_info(user_id, user_access_token)
            
            # 获取用户姓名
            user_name = user_id
            if user_info and user_info.get("code") == 0:
                # authen/v1/user_info 的返回结构直接在 data 下 (data.name)
                # 而 contact/v3 是在 data.user.name
                user_name = user_info.get("data", {}).get("name", user_id)
            
            # 获取会议主题和时间
            if meeting_info and meeting_info.get("code") == 0:
                m_data = meeting_info.get("data", {}).get("meeting", {})
                topic = m_data.get("topic", "未命名会议")
                start_time_ts = int(m_data.get("start_time", 0))
                
                # 转换时间戳
                import time
                time_str = time.strftime("%Y%m%d_%H%M", time.localtime(start_time_ts))
                
                # 组合文件名: 用户名_会议名_时间
                # 去除非法字符
                safe_topic = "".join([c for c in topic if c.isalnum() or c in (' ', '-', '_')]).strip()
                file_name_prefix = f"{user_name}_{safe_topic}_{time_str}"
                print(f"[文件名构建] {file_name_prefix}")
    except Exception as e:
        print(f"[文件名构建失败] 使用默认Token命名. Err: {e}")
    # -----------------------------------------------------

    # 使用妙计媒体 API 获取下载链接（直接用Token，不查会议ID）
    file_url = _get_download_url(object_token, user_access_token)
    
    # 如果Token过期，尝试刷新
    if file_url == "RenewToken":
        print("[Token过期] 尝试刷新 Token...")
        saved_data = token_manager.get_user_token(user_id)
        if saved_data and saved_data.get("refresh_token"):
            new_at, new_rt = refresh_user_token_for_user(client, user_id, saved_data["refresh_token"])
            if new_at:
                user_access_token = new_at
                file_url = _get_download_url(object_token, user_access_token)
                # 刷新后重新尝试获取元数据（如果之前失败了也没关系，尽力而为）
                if meeting_id and file_name_prefix == object_token: 
                     # 这里可以重试获取元数据，但非必须，简化逻辑略过
                     pass
            else:
                print("[放弃] Token 刷新失败，无法下载。")
                return
        else:
            print("[放弃] 找不到 Refresh Token，无法下载。")
            return
    
    print(f"[调试] 获取到下载链接: {file_url}")
    if not file_url:
        print(">>> 无法获取下载链接，跳过。")
        return

    # 下载文件
    download_dir = config.get("download_path", "./downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    # 最终文件名
    final_file_name = f"{file_name_prefix}.mp4"
    file_path = os.path.join(download_dir, final_file_name)

    # 去重检查... (略)
    
    print(f"正在下载文件到: {file_path}")
    try:
        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"下载完成: {file_path}")
        
        # 发送通知
        send_success_notification(user_id, final_file_name)
        
    except Exception as e:
        print(f"下载异常: {e}")

def _get_download_url(object_token, access_token):
    """
    使用妙计媒体 API 直接获取下载链接
    API: GET /open-apis/minutes/v1/minutes/:minute_token/media
    接口权限: minutes:minutes.media:export (下载妙记的音视频文件)
    返回: url 字符串, 或者 "RenewToken", 或者 None
    """
    url = f"https://open.feishu.cn/open-apis/minutes/v1/minutes/{object_token}/media"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    try:
        resp = requests.get(url, headers=headers)
        
        # 处理 Token 过期的情况
        if resp.status_code == 401:
             return "RenewToken"
            
        data = resp.json()
        print(f"[API返回调试] Code: {data.get('code')} | Msg: {data.get('msg')} | Data Keys: {list(data.get('data', {}).keys()) if data.get('data') else 'None'}")
        
        if data.get("code") == 0:
            # 兼容：有时返回 download_url (文档未写明但实际返回这个)
            # 有时返回 data.video.url
            # 有时返回 data.url
            
            # 1. 尝试直接获取 download_url (本次调试发现的)
            download_url = data.get("data", {}).get("download_url")
            if download_url:
                return download_url
            
            # 2. 尝试获取 video url
            video_url = data.get("data", {}).get("video", {}).get("url")
            if video_url:
                return video_url
            
            # 3. 尝试直接获取 url
            media_url = data.get("data", {}).get("url")
            if media_url:
                return media_url
        else:
            print(f"[妙计API错误] {data.get('msg')} (Code: {data.get('code')})")
            
    except Exception as e:
        print(f"[请求异常] {e}")
    
    return None

def get_recording_info(meeting_id, user_access_token):
    """
    通过 user_access_token 查询会议录制信息
    权限要求: vc:record:readonly
    """
    url = f"https://open.feishu.cn/open-apis/vc/v1/meetings/{meeting_id}/recording"
    headers = {
        "Authorization": f"Bearer {user_access_token}"
    }
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[获取录制信息失败] Status: {resp.status_code}, Body: {resp.text}")
            return None
    except Exception as e:
        print(f"[获取录制信息异常] {e}")
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

        # 增加对权限不足的友好提示
        try:
             err_body = resp.json()
             if err_body.get('code') == 99991679:
                 print(f"❌ [权限不足] 现有 Token 缺少 'vc:meeting:readonly' 权限。")
                 print(f"👉 请务必重新访问授权页面 (http://<HOST>:29090/auth/start) 并点击授权，以更新 Token 权限。")
        except Exception:
             pass

        print(f"[获取会议详情失败] Code: {resp.status_code}, Body: {resp.text}")
    except Exception as e:
        print(f"[获取会议详情异常] {e}")
    return None

def get_user_info(user_id, user_access_token):
    """
    获取用户信息 (用于生成文件名)
    """
    # 修正：使用 OAuth2/Authen 接口获取当前 Token 用户的基本信息 (包含姓名)
    url = "https://open.feishu.cn/open-apis/authen/v1/user_info"
    headers = {
        "Authorization": f"Bearer {user_access_token}"
    }
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        print(f"[获取用户信息失败] Code: {resp.status_code} Body: {resp.text}")
    except Exception as e:
        print(f"[获取用户信息异常] {e}")
    return None
