import threading
import re
from app.utils.logger import logger
from app.data.token_store import token_store
from app.core.meeting_service import get_recording_info
from app.core.notification import send_auth_failed_notification
from app.core.downloader import download_single_video
from lark_oapi.api.vc.v1 import P2VcMeetingAllMeetingEndedV1

def do_download_task(token, user_id, meeting_id=None):
    """
    具体的下载任务，在独立线程中运行
    """
    try:
        # 1. 尝试从 TokenStore 获取该用户的 Token
        user_data = token_store.get_user_token(user_id)
        user_access_token = None
        
        if user_data:
            user_access_token = user_data.get("user_access_token")
        else:
            logger.warning(f"[跳过] 用户 {user_id} 未授权")
            return

        # 2. 调用 downloader 进行下载
        download_single_video(token, user_id, user_access_token, meeting_id)
        
    except Exception as e:
        logger.error(f"[下载异常] {e}")

def check_recording_loop(meeting_id, owner_id, attempt=1):
    """
    轮询检查录制是否生成 (适用于手动创建的会议)
    采取阶梯式重试策略，最大覆盖约 30 分钟。
    """
    # [策略配置]
    # 阶段1 (0-5分): 60秒一次, attempt 1-5 (每次日志)
    # 阶段2 (5-30分): 300秒一次, attempt 6-10 (每次日志)
    # 超时: >30分 (停止)
    
    interval = 60
    silent = False
    
    if attempt <= 5:
        interval = 60
        silent = False        # 前5分钟: 每60秒一次
    elif attempt <= 10:
        interval = 300        # 5-30分钟: 每300秒(5分钟)一次
        silent = False        # 每次都打印
    else:
        logger.warning(f"[监测停止] 会议 {meeting_id} 超过30分钟未生成录制文件，判定为无录制，停止任务。")
        return
    
    # 1. Token 检查
    user_data = token_store.get_user_token(owner_id)
    if not user_data:
        # 如果用户未授权，输出错误日志并发送通知卡片
        logger.error(f"[权限错误] 用户 {owner_id} 的会议 {meeting_id} 已结束，但在系统中找不到该用户的 Token。无法下载。")
        send_auth_failed_notification(owner_id, meeting_id)
        return
        
    user_token = user_data.get("user_access_token")
    
    # 2. 调用 API 查询 (需 vc:recording:readonly 权限)
    # 传递 owner_id 以支持自动 Token 刷新
    # 传递 silent 参数控制日志噪音
    res = get_recording_info(meeting_id, user_token, user_id=owner_id, silent=silent)
    
    # 3. 结果判断
    # 成功拿到 url
    if res and res.get('code') == 0 and res.get('data', {}).get('recording', {}).get('url'):
        url = res['data']['recording']['url']
        
        # 提取 token 并下载
        match = re.search(r'(obcn[a-z0-9]+)', url)
        if match:
             token = match.group(1)
             logger.info(f"[✅ 录制就绪] Token: {token} | 准备下载...")
             # 传递 meeting_id
             do_download_task(token, owner_id, meeting_id)
        return
        
    # 失败则重试
    t = threading.Timer(float(interval), check_recording_loop, args=(meeting_id, owner_id, attempt + 1))
    t.start()

def do_p2_meeting_ended(data: P2VcMeetingAllMeetingEndedV1) -> None:
    try:
        # 修正：根据 SDK 结构，meeting_id 和 owner 信息在 data.event.meeting 下
        meeting_id = data.event.meeting.id  
        owner_id = data.event.meeting.owner.id.user_id
        
        logger.info(f"[事件侦测] 会议结束 (All Meeting Ended) | ID: {meeting_id} | Owner: {owner_id} | 启动查询...")
        
        # 延迟 30秒开始第一次检查
        t = threading.Timer(30.0, check_recording_loop, args=(meeting_id, owner_id))
        t.start()
        
    except Exception as e:
        logger.error(f"[事件处理错误] {e}")
