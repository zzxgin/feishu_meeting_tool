import re
import threading
import json
import requests
import logging
import logging.handlers
import lark_oapi as lark
from lark_oapi.adapter.flask import *
from lark_oapi.api.vc.v1 import *
from flask import Flask, request
import vedio_api
from token_manager import token_manager
import os

# 0. 配置日志 (同时输出到文件和控制台)
# 确保日志目录存在
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_file = os.path.join(log_dir, "app.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def do_download_task(token, user_id, meeting_id=None):
    """
    具体的下载任务，在独立线程中运行
    """
    try:
        # 1. 尝试从 TokenManager 获取该用户的 Token
        user_data = token_manager.get_user_token(user_id)
        user_access_token = None
        
        if user_data:
            user_access_token = user_data.get("user_access_token")
        else:
            logger.warning(f"[跳过] 用户 {user_id} 未授权")
            return

        # 2. 调用 vedio_api 进行下载
        # 传递 meeting_id 以获取更多元数据生成文件名
        vedio_api.download_single_video(token, user_id, user_access_token, meeting_id)
        
    except Exception as e:
        logger.error(f"[下载异常] {e}")

def check_recording_loop(meeting_id, owner_id, attempt=1):
    """
    轮询检查录制是否生成 (适用于手动创建的会议)
    """
    if attempt > 10: # 最多尝试 10 分钟
        # logger.info(f"[停止轮询] 会议 {meeting_id} 录制未生成或超时") # 可选：静默停止
        return

    # logger.debug(f"[轮询检查] 第 {attempt} 次 (Meeting: {meeting_id})") # 保持静默，除非调试
    
    # 1. Token 检查
    user_data = token_manager.get_user_token(owner_id)
    if not user_data:
        # 如果用户未授权，输出错误日志并发送通知卡片
        logger.error(f"[权限错误] 用户 {owner_id} 的会议 {meeting_id} 已结束，但在系统中找不到该用户的 Token。无法下载。")
        vedio_api.send_auth_failed_notification(owner_id, meeting_id)
        return
        
    user_token = user_data.get("user_access_token")
    
    # 2. 调用 API 查询 (需 vc:recording:readonly 权限)
    res = vedio_api.get_recording_info(meeting_id, user_token)
    
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
    # logger.info(f"[等待] 录制尚未准备好，60秒后重试...")
    t = threading.Timer(60.0, check_recording_loop, args=(meeting_id, owner_id, attempt + 1))
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

def main():
    config = vedio_api.load_config()
    encrypt_key = ""  # 强制关闭加密
    verification_token = config.get('verification_token', '')

    # 1. 构造事件 Dispatcher
    handler = lark.EventDispatcherHandler.builder(encrypt_key, verification_token, lark.LogLevel.INFO) \
        .register_p2_vc_meeting_all_meeting_ended_v1(do_p2_meeting_ended) \
        .build()

    # 2. 注册 Flask 路由
    @app.route("/webhook/event", methods=["POST"])
    def event():
        # logger.debug(f"\n[{threading.current_thread().name}] === 收到 HTTP 请求 ===")
        # 飞书要求返回 200 Keep-Alive，lark-oapi 自动处理
        # 修复：直接返回处理结果，不要重复调用 handler.do()
        return parse_resp(handler.do(parse_req()))

    # --- 新增：Auth 授权路由 ---
    @app.route("/auth/start", methods=["GET"])
    def auth_start():
        scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
        host = request.headers.get('X-Forwarded-Host', request.host)
        if "ngrok" in host and scheme == "http":
            scheme = "https"
            
        redirect_uri = f"{scheme}://{host}/auth/callback"
        
        # 0. 尝试获取 query 中的 meeting_id（用于补录）
        meeting_id = request.args.get('meeting_id', '')
        # 如果有 meeting_id，将其放入 OAuth state 中，格式：meeting_123456
        state = f"meeting_{meeting_id}" if meeting_id else "init_auth"
        
        # 权限范围：
        # 1. minutes:minutes.media:export -> 直接下载妙计音视频文件（核心权限）
        # 2. contact:user.id:readonly -> 获取用户身份
        # 3. vc:record:readonly -> 获取会议录制信息 (用于手动会议)
        # 4. contact:user.base:readonly -> 新增：获取用户基本信息(姓名)
        # 5. vc:meeting:readonly -> 新增：获取会议详情(主题、时间)
        scope = "minutes:minutes.media:export contact:user.id:readonly vc:record:readonly contact:user.base:readonly vc:meeting:readonly" 
        app_id = config['app_id']
        
        from urllib.parse import quote
        encoded_redirect_uri = quote(redirect_uri, safe='')
        
        # 将 state 传入 OAuth URL
        url = f"https://open.feishu.cn/open-apis/authen/v1/authorize?app_id={app_id}&redirect_uri={encoded_redirect_uri}&scope={scope}&state={state}"
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
        state = request.args.get("state", "")
        
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
            
            # 4. 检查是否需要补录 (如果 state 包含 meeting_id)
            remedy_info = ""
            if state and state.startswith("meeting_"):
                # 提取会议ID
                missed_meeting_id = state.replace("meeting_", "")
                if missed_meeting_id:
                     logger.info(f"[补录逻辑] 检测到授权补录请求，会议ID: {missed_meeting_id}")
                     # 启动补录线程
                     # 注意：check_recording_loop 内部有重试机制，很适合这里
                     t = threading.Thread(target=check_recording_loop, args=(missed_meeting_id, user_id))
                     t.start()
                     remedy_info = f"<p style='color: blue'>🔁 正在尝试为你补下载刚才错过的会议 ({missed_meeting_id})，请留意飞书通知。</p>"

            return f"""
            <div style="text-align:center; margin-top: 50px;">
                <h1 style="color:green">✅ 授权成功!</h1>
                <p>你好，<b>{name}</b> (ID: {user_id})</p>
                <p>你的 Token 已保存。今后你的会议录制结束后，机器人将自动为你下载。</p>
                {remedy_info}
            </div>
            """

        except Exception as e:
            logger.error(f"[Auth Callback Error] {e}")
            return f"❌ 内部异常: {str(e)}"

    # 区分开发环境和生产环境
    # 如果是本地调试，直接运行 main() 则使用 Flask 自带服务器
    # 如果是生产环境，通常通过 python listen_recording.py 运行，但也推荐用 waitress
    logger.info(f"启动 HTTP Server 监听端口 29090...")
    
    # 尝试使用 waitress (生产级 WSGI 服务器)
    try:
        from waitress import serve
        logger.info("✅ 使用 Waitress 生产级服务器启动...")
        serve(app, host="0.0.0.0", port=29090)
    except ImportError:
        logger.warning("⚠️ 未安装 waitress，回退到 Flask 开发服务器...")
        logger.warning("建议安装: pip install waitress")
        app.run(host="0.0.0.0", port=29090)

if __name__ == "__main__":
    main()
