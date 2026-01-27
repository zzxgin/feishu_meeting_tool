import json
import os
import requests
from app.utils.logger import logger
from app.utils.feishu_client import get_tenant_access_token

def send_success_notification(user_id, file_name, nas_path=None):
    """
    发送下载成功通知卡片
    """
    token = get_tenant_access_token()
    if not token:
        return

    # 构建提示文本
    if nas_path:
        # 如果归档到了 NAS
        location_text = f"📂 **已归档至个人NAS目录**: `{nas_path}`"
    else:
        location_text = "💾 文件已保存至服务器 downloads 目录"

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
                "tag": "div",
                "text": {
                    "content": location_text,
                    "tag": "lark_md"
                }
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
             logger.error(f"[消息发送失败] {resp.json()}")
        else:
             logger.info(f"[消息发送成功] 通知已发送给用户 {user_id}")
    except Exception as e:
        logger.error(f"[消息发送异常] {e}")

def send_auth_failed_notification(user_id, meeting_id=None):
    """
    发送授权失败/过期通知，引导用户重新授权
    meeting_id: 这里传入是为了在用户点击授权时，透传回 callback 进行补发下载
    """
    token = get_tenant_access_token()
    if not token:
        return
    
    # 优先从环境变量获取外部地址，否则使用默认 (用户请求的 IP)
    # TODO: 这里写死了 IP，最好放到 Config 里
    base_url = os.getenv("EXTERNAL_URL", "http://223.254.147.69:29090") 
    
    # 构建带 meeting_id 的授权链接
    auth_url = f"{base_url}/auth/start"
    if meeting_id:
        auth_url += f"?meeting_id={meeting_id}"

    card_content = {
        "config": { "wide_screen_mode": True },
        "header": {
            "template": "red",
            "title": { "content": "❌ 自动归档失败 (需要重新授权)", "tag": "plain_text" }
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "content": f"检测到您的飞书授权已失效或 Token 已过期，机器人无法自动下载会议录制。\n\n请点击下方按钮重新授权：",
                    "tag": "plain_text"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": { "content": "🔐 点击重新授权", "tag": "plain_text" },
                        "type": "primary",
                        "url": auth_url
                    }
                ]
            }
        ]
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
             logger.error(f"[授权失败通知发送失败] {resp.json()}")
        else:
             logger.info(f"[授权失败通知发送成功] 已通知用户 {user_id}")
    except Exception as e:
        logger.error(f"[授权失败通知发送异常] {e}")
