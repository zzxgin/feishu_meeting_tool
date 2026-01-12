import lark_oapi as lark
from lark_oapi.api.vc.v1 import *
import vedio_api

def create_meeting_by_no(mobile_or_email):
    config = vedio_api.load_config()
    
    # 1. 创建 Client
    client = lark.Client.builder() \
        .app_id(config['app_id']) \
        .app_secret(config['app_secret']) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    print(f"正在查找用户: {mobile_or_email} ...")
    
    # 2. 获取 User ID (需要 Contact 权限: contact:user.id:readonly 或 contact:user:readonly)
    # 这里尝试通过手机号或邮箱获取 user_id
    user_id = None
    try:
        # 尝试作为手机号查询
        # 正确构建 RequestBody 和 Request，lark SDK 的结构比较深
        req_body = lark.api.contact.v3.BatchGetIdUserRequestBody.builder() \
            .mobiles([mobile_or_email]) \
            .build()
            
        req = lark.api.contact.v3.BatchGetIdUserRequest.builder() \
            .user_id_type("user_id") \
            .request_body(req_body) \
            .build()
            
        resp = client.contact.v3.user.batch_get_id(req)
        
        if resp.success() and resp.data and resp.data.user_list:
            user_id = resp.data.user_list[0].user_id
            print(f"找到用户 ID (按手机): {user_id}")
    except Exception as e:
        print(f"手机号查询失败: {e}")

    if not user_id:
        try:
            # 尝试作为邮箱查询
            # 正确构建 RequestBody 和 Request
            req_body = lark.api.contact.v3.BatchGetIdUserRequestBody.builder() \
                .emails([mobile_or_email]) \
                .build()
                
            req = lark.api.contact.v3.BatchGetIdUserRequest.builder() \
                .user_id_type("user_id") \
                .request_body(req_body) \
                .build()
                
            resp = client.contact.v3.user.batch_get_id(req)
            if resp.success() and resp.data and resp.data.user_list:
                user_id = resp.data.user_list[0].user_id
                print(f"找到用户 ID (按邮箱): {user_id}")
            #else:
                #print(f"[debug] 邮箱查询响应: {resp.code} {resp.msg} {resp.error}")

        except Exception as e:
            print(f"邮箱查询失败: {e}")

    if not user_id:
        print("❌ 未找到该用户，请确认：\n1. 输入的手机号/邮箱正确\n2. 应用已开通 '通讯录(contact:user:readonly)' 权限并发布版本")
        return

    # 3. 创建预约会议 (Open API 会议)
    print(f"正在为用户 {user_id} 创建 API 会议...")
    import time
    end_time_ts = str(int(time.time()) + 3600) # 1小时后结束
    
    request = ApplyReserveRequest.builder() \
        .user_id_type("user_id") \
        .request_body(ApplyReserveRequestBody.builder()
            .end_time(end_time_ts)
            .owner_id(user_id) # 会议拥有者
            .meeting_settings(ReserveMeetingSetting.builder()
                .topic("API 测试录制事件会议")
                .auto_record(True) # 尝试开启自动录制 (可选)
                .build())
            .build()) \
        .build()

    resp = client.vc.v1.reserve.apply(request)

    if not resp.success():
        print(f"❌ 创建会议失败: {resp.code} - {resp.msg}")
        return

    meeting = resp.data.reserve
    print("\n✅ API 会议创建成功！")
    # print(f"会议主题: {meeting.meeting_settings.topic}") # 某些情况下 setting 可能不返回
    print(f"会议 URL: {meeting.url}")
    print(f"会议 ID: {meeting.id}")
    print("\n请点击上方 URL 入会，进行录制并结束会议，即可验证事件推送。")

if __name__ == "__main__":
    # 请在运行前，输入你的飞书手机号或企业邮箱
    target_user = input("请输入你的飞书注册手机号或企业邮箱: ")
    create_meeting_by_no(target_user)
