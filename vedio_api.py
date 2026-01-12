import json
import os
import requests
import lark_oapi as lark
from lark_oapi.api.minutes.v1 import *
from token_manager import token_manager

def load_config():
    """读取本地目录下的 config.json 配置文件"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

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

def download_single_video(object_token, user_id, user_access_token=None):
    """
    下载单个视频，支持多用户模式
    :param object_token: 视频的 Token
    :param user_id: 视频拥有者的 User ID (用于刷新 Token)
    :param user_access_token: 用户的 Access Token
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

    print(f"[处理中] Token: {object_token} (Owner: {user_id})")
    
    # 1. 获取下载链接 (尝试直接请求)
    file_url = _get_download_url(object_token, user_access_token)
    
    # 2. 如果失效 (401)，尝试刷新 Token 再重试
    if file_url == "RenewToken":
        print("[Token过期] 尝试刷新 Token...")
        # 从 TokenManager 获取最新的 refresh_token
        saved_data = token_manager.get_user_token(user_id)
        if saved_data and saved_data.get("refresh_token"):
            new_at, new_rt = refresh_user_token_for_user(client, user_id, saved_data["refresh_token"])
            if new_at:
                user_access_token = new_at
                file_url = _get_download_url(object_token, user_access_token)
            else:
                print("[放弃] Token 刷新失败，无法下载。")
                return
        else:
             print("[放弃] 找不到 Refresh Token，无法下载。")
             return

    if not file_url:
        print(">>> 无法获取下载链接，跳过。")
        return

    # 3. 下载文件
    download_dir = config.get("download_path", "./downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    file_path = os.path.join(download_dir, f"{object_token}.mp4")
    
    print("正在下载文件...")
    try:
        # 使用流式下载，避免大文件占用过多内存
        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
        print(f"下载完成: {file_path}")
    except Exception as e:
        print(f"下载出错: {e}")


def _get_download_url(object_token, access_token):
    """
    内部帮助函数：通过 requests 直接调用下载接口
    返回: url 字符串, 或者 "RenewToken", 或者 None
    """
    url = f"https://open.feishu.cn/open-apis/drive/v1/medias/batch_get_tmp_download_url?file_tokens={object_token}"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    try:
        resp = requests.get(url, headers=headers)
        
        # 处理 Token 过期的情况
        if resp.status_code == 401 or (resp.json().get("code") in [99991663, 99991668]): # 典型的 AccessToken 失效码
            return "RenewToken"
            
        data = resp.json()
        if data.get("code") == 0:
            tmp_infos = data.get("data", {}).get("tmp_download_urls", [])
            if tmp_infos:
                return tmp_infos[0].get("tmp_download_url")
        else:
            print(f"[API错误] {data}")
    except Exception as e:
        print(f"[请求异常] {e}")
    
    return None
