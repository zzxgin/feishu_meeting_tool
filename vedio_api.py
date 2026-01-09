import json
import os
import requests
import lark_oapi as lark
from lark_oapi.api.minutes.v1 import *

def load_config():
    """读取本地目录下的 config.json 配置文件"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    # 1. 加载配置文件
    config = load_config()
    
    # 2. 创建 Client
    # 使用 tenant_access_token，SDK 内部会自动获取并维护 token 有效期
    client = lark.Client.builder() \
        .app_id(config['app_id']) \
        .app_secret(config['app_secret']) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    save_dir = config['download_path']
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    print(f"--- 开始批量任务，共 {len(config['tokens'])} 个视频 ---")

    for m_token in config['tokens']:
        download_single_video(client, m_token, save_dir)

    print("\n--- 所有任务结束 ---")

def download_single_video(client, minute_token, save_dir):
    print(f"\n[处理中] Token: {minute_token}")

    # 3. 构造请求
    request = GetMinuteMediaRequest.builder() \
        .minute_token(minute_token) \
        .build()

    # SDK 自动使用 tenant_access_token 发起请求
    response: GetMinuteMediaResponse = client.minutes.v1.minute_media.get(request)

    if not response.success():
        print(f"失败: {response.msg} (Code: {response.code})")
        return

    # 4. 拿到链接后立即执行下载
    download_url = response.data.download_url
    file_path = os.path.join(save_dir, f"{minute_token}.mp4")

    print(f"正在下载文件...")
    try:
        # stream=True 开启流式下载
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    f.write(chunk)
        print(f"下载完成: {file_path}")
    except Exception as e:
        print(f"下载过程报错: {e}")

if __name__ == "__main__":
    main()
    