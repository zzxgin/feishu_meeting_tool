from flask import Blueprint, request
import requests
import threading
import lark_oapi as lark
from lark_oapi.adapter.flask import *
from app.utils.config import load_config
from app.utils.logger import logger
from app.data.token_store import token_store
from app.api.event_handler import do_p2_meeting_ended, check_recording_loop

api_bp = Blueprint('api', __name__)

# 全局 Handler，需要在 app init 时初始化，或是 lazy init
# 为了简单，这里 lazy init 或直接 init
config = load_config()
encrypt_key = ""  # 强制关闭加密
verification_token = config.get('verification_token', '')

handler = lark.EventDispatcherHandler.builder(encrypt_key, verification_token, lark.LogLevel.INFO) \
    .register_p2_vc_meeting_all_meeting_ended_v1(do_p2_meeting_ended) \
    .build()

@api_bp.route("/webhook/event", methods=["POST"])
def event():
    # 飞书要求返回 200 Keep-Alive，lark-oapi 自动处理
    return parse_resp(handler.do(parse_req()))

@api_bp.route("/auth/start", methods=["GET"])
def auth_start():
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
    host = request.headers.get('X-Forwarded-Host', request.host)
    if "ngrok" in host and scheme == "http":
        scheme = "https"
        
    redirect_uri = f"{scheme}://{host}/auth/callback"
    
    # 0. 尝试获取 query 中的 meeting_id（用于补录）
    meeting_id = request.args.get('meeting_id', '')
    # 如果有 meeting_id，将其放入 OAuth state 中
    state = f"meeting_{meeting_id}" if meeting_id else "init_auth"
    
    # 权限范围
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

@api_bp.route("/auth/callback", methods=["GET"])
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

        # 3. 保存到 TokenStore
        token_data = {
            "user_access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "name": name
        }
        token_store.save_user_token(user_id, token_data)
        
        # 4. 检查是否需要补录 (如果 state 包含 meeting_id)
        remedy_info = ""
        if state and state.startswith("meeting_"):
            # 提取会议ID
            missed_meeting_id = state.replace("meeting_", "")
            if missed_meeting_id:
                 logger.info(f"[补录逻辑] 检测到授权补录请求，会议ID: {missed_meeting_id}")
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
