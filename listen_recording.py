import re
import threading
import json
import requests
import lark_oapi as lark
from lark_oapi.adapter.flask import *
from lark_oapi.api.vc.v1 import *
from flask import Flask, request
import vedio_api
from token_manager import token_manager

app = Flask(__name__)

def do_download_task(token, user_id):
    """
    具体的下载任务，在独立线程中运行
    """
    try:
        print(f"--- [后台线程] 开始处理任务 | FileToken: {token} | OwnerID: {user_id} ---")

        # 1. 尝试从 TokenManager 获取该用户的 Token
        user_data = token_manager.get_user_token(user_id)
        user_access_token = None
        
        if user_data:
            user_access_token = user_data.get("user_access_token")
            print(f"--- [后台线程] 找到用户 Token: {user_access_token[:10]}... ---")
        else:
            print(f"--- [后台线程] [警告] 未找到用户 {user_id} 的 Token！无法下载私有视频。请让该用户先进行授权。---")
            # 这里可以扩展：尝试用机器人 Token 发消息给用户提醒授权
            return

        # 2. 调用 vedio_api 进行下载
        # 注意：这里我们不再需要 passing client, vedio_api 内部会创建
        vedio_api.download_single_video(token, user_id, user_access_token)
        
        print(f"--- [后台线程] 任务结束 ---")
    except Exception as e:
        print(f"[后台线程] 下载异常: {e}")

def do_p2_recording_ready(data: P2VcMeetingRecordingReadyV1) -> None:
    # 1. 获取事件内容
    # print(f"[收到事件] {lark.JSON.marshal(data)}")
    
    event_url = data.event.url
    
    # 提取 User ID (Owner)
    try:
        owner_id = data.event.meeting.owner.id.user_id
    except AttributeError:
        print("[错误] 无法从事件中提取 meeting.owner.id.user_id")
        owner_id = "unknown"
        
    print(f"[事件侦测] 录制完成 | URL: {event_url} | Owner: {owner_id}")
    
    # 2. 提取 minute_token
    match = re.search(r'(obcn[a-z0-9]+)', event_url)
    if match:
        token = match.group(1)
        print(f"提取到 Token: {token}，正在启动后台下载线程...")
        
        # 3. 启动线程进行下载
        print(f"等待 60 秒后开始下载，给妙计生成预留时间...")
        t = threading.Timer(60.0, do_download_task, args=(token, owner_id))
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
    @app.route("/webhook/event", methods=["POST"])
    def event():
        # print(f"\n[{threading.current_thread().name}] === 收到 HTTP 请求 ===")
        try:
            handler.do(parse_req())
        except Exception as e:
            # 这里的 handler.do 可能会因为 parse 失败抛错，我们捕获它但不阻断返回
            # Flask adapter 会自动处理异常返回，但如果我们需要自定义 logging
            print(f"Handler Error: {e}")
            pass
        
        # 飞书要求返回 200 Keep-Alive，lark-oapi 自动处理
        return parse_resp(handler.do(parse_req()))

    # --- 新增：Auth 授权路由 ---
    @app.route("/auth/start", methods=["GET"])
    def auth_start():
        scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
        host = request.headers.get('X-Forwarded-Host', request.host)
        if "ngrok" in host and scheme == "http":
            scheme = "https"
            
        redirect_uri = f"{scheme}://{host}/auth/callback"
        
        # 权限范围
        # 回退去掉了 drive 权限，尝试只用 minutes 权限下载
        scope = "minutes:minutes:readonly minutes:minutes.media:export contact:user.id:readonly" 
        app_id = config['app_id']
        
        from urllib.parse import quote
        encoded_redirect_uri = quote(redirect_uri, safe='')
        
        url = f"https://open.feishu.cn/open-apis/authen/v1/authorize?app_id={app_id}&redirect_uri={encoded_redirect_uri}&scope={scope}&state=RANDOMSTATE"
        return f'''
        <div style="text-align:center; margin-top: 50px;">
            <h1>Feishu Auto-Downloader Authorization</h1>
            <p>点击下方按钮，授权机器人自动下载您的会议录像。</p>
            <br/>
            <a href="{url}" style="background-color: #3370ff; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 18px;">授权开启 (Login & Authorize)</a>
            <p style="margin-top:20px; color: #888; font-size: 12px;">Redirect URI: {redirect_uri}</p>
        </div>
        '''

    @app.route("/auth/callback", methods=["GET"])
    def auth_callback():
        code = request.args.get("code")
        if not code:
            return "Missing code", 400
        
        client = lark.Client.builder() \
            .app_id(config['app_id']) \
            .app_secret(config['app_secret']) \
            .build()
            
        req = lark.api.authen.v1.CreateAccessTokenRequest.builder() \
            .request_body(lark.api.authen.v1.CreateAccessTokenRequestBody.builder()
                .grant_type("authorization_code")
                .code(code)
                .build()) \
            .build()
            
        try:
            # 1. 换取 Token
            resp = client.authen.v1.access_token.create(req)
            if not resp.success():
                return f"❌ 授权失败 (Token): {resp.code} - {resp.msg}"
            
            data = resp.data
            access_token = data.access_token
            refresh_token = data.refresh_token
            expires_in = data.expires_in
            
            # 2. 获取用户信息 (User ID)
            # 需要在 Scope 里添加 token:user.id:readonly 或者 contact:user.id:readonly，或者直接用 Authen API
            # 使用 https://open.feishu.cn/open-apis/authen/v1/user_info
            
            user_info_url = "https://open.feishu.cn/open-apis/authen/v1/user_info"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_resp = requests.get(user_info_url, headers=headers)
            user_json = user_resp.json()
            
            if user_json.get("code") != 0:
                return f"❌ 获取用户信息失败: {user_json}"
                
            user_id = user_json.get("data", {}).get("user_id")
            name = user_json.get("data", {}).get("name", "Unknown")
            
            if not user_id:
                return "❌ 无法获取 User ID，请检查权限 Scope。"

            # 3. 保存到 TokenManager
            token_data = {
                "user_access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "name": name
            }
            token_manager.save_user_token(user_id, token_data)
                
            return f"""
            <div style="text-align:center; margin-top: 50px;">
                <h1 style="color:green">✅ 授权成功!</h1>
                <p>你好，<b>{name}</b> (ID: {user_id})</p>
                <p>你的 Token 已保存。今后你的会议录制结束后，机器人将自动为你下载。</p>
            </div>
            """

        except Exception as e:
            print(f"[Auth Callback Error] {e}")
            return f"❌ 内部异常: {str(e)}"

    print(f"启动 HTTP Server 监听端口 29090...")
    app.run(host="0.0.0.0", port=29090)

if __name__ == "__main__":
    main()
