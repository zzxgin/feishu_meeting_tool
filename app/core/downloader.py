import os
import requests
import lark_oapi as lark
from app.utils.logger import logger
from app.utils.config import load_config
from app.utils.feishu_client import get_tenant_access_token # 添加这个引用
from app.data.token_store import token_store
from app.core.nas_manager import NasManager
from app.core.notification import send_auth_failed_notification, send_success_notification
from app.core.meeting_service import (
    get_meeting_detail, 
    get_user_info, 
    refresh_user_token_for_user, 
    get_meeting_participants,
    get_user_departments_from_api 
)
# from app.utils.user_cache import UserCache # 移除缓存引用

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
        logger.debug(f"[API返回调试] Code: {data.get('code')} | Msg: {data.get('msg')} | Data Keys: {list(data.get('data', {}).keys()) if data.get('data') else 'None'}")
        
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
            logger.error(f"[妙计API错误] {data.get('msg')} (Code: {data.get('code')})")
            
    except Exception as e:
        logger.error(f"[请求异常] {e}")
    
    return None

def download_single_video(object_token, user_id, user_access_token=None, meeting_id=None):
    """
    下载单个视频
    """
    config = load_config()
    
    # 如果没有传 Token（比如还没登录），就无法下载私有视频
    if not user_access_token:
        logger.error(f"[错误] 缺少 User Token，无法下载用户 {user_id} 的视频")
        return

    # 创建 API Client (用于刷新 Token - 虽然我们现在不用 SDK client 刷新了，但保留 config 逻辑)
    # 真正刷新用的是 http request

    logger.info(f"[处理中] 妙计Token: {object_token} | Owner: {user_id}")
    
    # --- 1. 获取文件名所需的元数据 (用户+会议名+时间) ---
    file_name_prefix = object_token # 默认用 token
    try:
        if meeting_id:
            meeting_info = get_meeting_detail(meeting_id, user_access_token)
            user_info = get_user_info(user_id, user_access_token)
            
            # 获取用户姓名
            user_name = user_id
            if user_info and user_info.get("code") == 0:
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
                logger.debug(f"[文件名构建] {file_name_prefix}")
    except Exception as e:
        logger.warning(f"[文件名构建失败] 使用默认Token命名. Err: {e}")
    # -----------------------------------------------------

    # 使用妙计媒体 API 获取下载链接（直接用Token，不查会议ID）
    file_url = _get_download_url(object_token, user_access_token)
    
    # 如果Token过期，尝试刷新
    if file_url == "RenewToken":
        logger.info("[Token过期] 尝试刷新 Token...")
        saved_data = token_store.get_user_token(user_id)
        if saved_data and saved_data.get("refresh_token"):
            new_at, new_rt = refresh_user_token_for_user(user_id, saved_data["refresh_token"])
            if new_at:
                user_access_token = new_at
                file_url = _get_download_url(object_token, user_access_token)
            else:
                logger.error("[放弃] Token 刷新失败，无法下载。")
                send_auth_failed_notification(user_id, meeting_id)
                return
        else:
            logger.error("[放弃] 找不到 Refresh Token，无法下载。")
            send_auth_failed_notification(user_id, meeting_id)
            return
    
    logger.debug(f"[调试] 获取到下载链接: {file_url}")
    if not file_url:
        logger.error(">>> 无法获取下载链接，跳过。")
        return

    # 下载文件
    download_dir = config.get("download_path", "./downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    # 最终文件名
    final_file_name = f"{file_name_prefix}.mp4"
    file_path = os.path.join(download_dir, final_file_name)

    # 去重检查: 如果文件已存在 (且大小 > 0)，则视为下载成功，不做重复下载
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        logger.info(f"[跳过下载] 文件已存在: {file_path}")
        send_success_notification(user_id, final_file_name)
        return

    logger.info(f"正在下载文件到: {file_path}")
    try:
        # 使用临时文件下载，防止中断导致残留不完整文件
        temp_file_path = file_path + ".downloading"
        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            with open(temp_file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # 下载完成后重命名
        os.rename(temp_file_path, file_path)
        logger.info(f"下载完成: {file_path}")

        # --- 1. NAS 个人归档 (Move) ---
        # 优先执行个人归档，因为 Move 会改变文件路径
        display_path = None
        current_file_path = file_path # 追踪当前文件的实际位置
        
        is_archived, archived_path, nas_folder = NasManager.archive_file(file_path, user_name, user_id)
        if is_archived:
            display_path = f"NAS/{nas_folder}"  # 卡片上显示: NAS/zhangsan
            current_file_path = archived_path # 更新路径，后续操作使用归档后的文件
            logger.info(f"[流程] 文件已归档至个人目录: {current_file_path}")
        else:
             logger.info(f"[流程] 个人归档未成功，继续使用下载目录文件: {current_file_path}")

        # --- 2. NAS 团队归档 (Copy) ---
        # 现在从 current_file_path 复制到团队目录
        try:
            target_team_folders = set()
            tenant_token = get_tenant_access_token() # 获取 Tenant Token 用于调用通讯录API
            
            if tenant_token:
                # A. 归属到 Owner 的部门 (使用 API 实时查询)
                logger.info("[API查询] 正在查询 Owner 部门...")
                owner_depts = get_user_departments_from_api(user_id, tenant_token)
                if owner_depts:
                    logger.info(f"[API查询] Owner {user_name} 所属部门: {owner_depts}")
                    target_team_folders.update(owner_depts)
                
                # B. 检测 "Skyris人力资源部" 逻辑 (HR 参会检测)
                # 只有当会议ID存在时才能检测
                if meeting_id:
                    # 获取参会人 (需要 User Token)
                    participants = get_meeting_participants(meeting_id, user_access_token)
                    has_hr = False
                    
                    if participants:
                        logger.info(f"[HR检测] 正在检查 {len(participants)} 名参会人的部门...")
                        for p in participants:
                            pid = p.get('user_id')
                            if pid:
                                # 对每个参会人查 API (注意性能，如果不频繁开会还好)
                                # 优化：只要命中一个 HR 就停止
                                p_depts = get_user_departments_from_api(pid, tenant_token)
                                if any("Skyris人力资源部" in d for d in p_depts):
                                    has_hr = True
                                    logger.info(f"[HR检测] 发现 HR 参会: {p.get('user_name', pid)}")
                                    break
                    
                    if has_hr:
                        logger.info(f"[团队归档] 检测到 HR 参会，追加 Skyris人力资源部")
                        target_team_folders.add("Skyris人力资源部")
            else:
                logger.error("[团队归档] 无法获取 Tenant Token，跳过部门查询")

            # 执行复制
            if target_team_folders:
                if os.path.exists(current_file_path):
                    NasManager.save_to_team_folder(current_file_path, list(target_team_folders))
                else:
                     logger.error(f"[团队归档失败] 源文件不存在: {current_file_path}")
            else:
                logger.info("[团队归档] 未匹配到任何团队文件夹，跳过")
                
        except Exception as e:
            logger.error(f"[团队归档异常] {e}")

        
        # 发送通知
        # 将 set 转为 list 传递给通知
        team_paths_list = list(target_team_folders) if 'target_team_folders' in locals() and target_team_folders else None
        send_success_notification(user_id, final_file_name, nas_path=display_path, team_paths=team_paths_list)
        
    except Exception as e:
        logger.error(f"下载异常: {e}")
        # 清理可能的临时文件
        if os.path.exists(temp_file_path):
             try: os.remove(temp_file_path)
             except: pass
