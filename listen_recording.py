import re
import threading
import lark_oapi as lark
from lark_oapi.adapter.flask import *
from lark_oapi.api.vc.v1 import *
from flask import Flask, request
import vedio_api

app = Flask(__name__)

def do_download_task(token):
    """
    具体的下载任务，在独立线程中运行
    """
    try:
        # 每次下载时重新读取配置
        config = vedio_api.load_config()
        
        # 创建 Client
        client = lark.Client.builder() \
            .app_id(config['app_id']) \
            .app_secret(config['app_secret']) \
            .log_level(lark.LogLevel.INFO) \
            .build()
            
        save_dir = config['download_path']
        
        print(f"--- [后台线程] 开始下载 Token: {token} ---")
        vedio_api.download_single_video(client, token, save_dir)
        print(f"--- [后台线程] Token: {token} 下载任务结束 ---")
    except Exception as e:
        print(f"[后台线程] 下载异常: {e}")

def do_p2_recording_ready(data: P2VcMeetingRecordingReadyV1) -> None:
    # 1. 获取事件内容
    print(f"[收到事件] 会议录制完成: {lark.JSON.marshal(data)}")
    
    event_url = data.event.url
    print(f"URL: {event_url}")
    
    # 2. 提取 minute_token
    match = re.search(r'(obcn[a-z0-9]+)', event_url)
    if match:
        token = match.group(1)
        print(f"提取到 Token: {token}，正在启动后台下载线程...")
        
        # 3. 启动线程进行下载，不阻塞主监听进程
        t = threading.Thread(target=do_download_task, args=(token,))
        t.start()
        
    else:
        print("未能从 URL 中提取到 token")

def main():
    config = vedio_api.load_config()
    encrypt_key = config.get('encrypt_key', '')
    verification_token = config.get('verification_token', '')

    # 1. 构造事件 Dispatcher
    handler = lark.EventDispatcherHandler.builder(encrypt_key, verification_token, lark.LogLevel.INFO) \
        .register_p2_vc_meeting_recording_ready_v1(do_p2_recording_ready) \
        .build()

    # 2. 注册 Flask 路由
    # 飞书后台配置的“请求地址 URL”需要填写: http://你的公网IP:端口/webhook/event
    @app.route("/webhook/event", methods=["POST"])
    def event():
        print(f"\n[{threading.current_thread().name}] === 收到 HTTP 请求 ===")
        print(f"Headers: {dict(request.headers)}")
        # 尝试读取并打印 Body (注意：get_data() 可能会影响后续流读取，但在 Flask 中通常会被缓存)
        try:
            body = request.get_data() 
            print(f"Body: {body.decode('utf-8')}")
        except Exception as e:
            print(f"读取 Body 失败: {e}")
        
        resp = handler.do(parse_req())
        return parse_resp(resp)

    # 3. 启动 HTTP Server
    port = 29090
    print(f"启动 HTTP Server 监听端口 {port}...")
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
