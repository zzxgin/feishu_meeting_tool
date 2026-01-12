# Feishu Meeting Auto-Downloader (飞书会议自动录制下载器)

这是一个基于飞书开放平台 (Lark Open Platform) 的企业级自动化工具。旨在解决企业会议归档痛点，自动监听并下载员工的会议录制文件，并通过飞书机器人发送完成通知。

## ✨ 核心特性

- **🤖 全自动监听**：无需人工干预，通过 Webhook 实时监听“会议录制完成”事件。
- **🔐 多用户/多租户支持**：
    - 支持企业内多位员工同时使用。
    - 严格遵循隐私安全原则，**谁的会议用谁的身份下载**。
    - 采用 **OAuth2 User Token** 模式，由员工授权，应用自动代理下载。
- **⚡️ 极速直连下载**：
    - 直接通过妙计 Token 接口获取高清 MP4 直链，无需处理复杂的云文档权限。
    - 支持断点续传（基础版），流式写入，节省服务器内存。
- **🔔 智能消息通知**：
    - 下载完成后，机器人会自动给会议拥有者发送飞书卡片消息。
    - 消息包含文件名、大小及耗时信息。
- **🔄 Token 自动续期**：内置 Token 自动刷新机制，一次授权，长期有效。
- **🛡 安全合规**：
    - 仅申请最小必要权限。
    - 所有的下载操作都有迹可循。

---

## 🏗 架构原理

本项目采用 **Webhook 事件驱动 + OAuth2 授权代理** 架构：

1.  **事件触发**：飞书会议结束并完成云端转码后，向本服务推送 `vc.meeting.recording_ready_v1` 事件。
2.  **身份识别**：服务解析事件，提取 `owner_id` (会议拥有者) 和 `minute_token` (妙计标识)。
3.  **智能代理**：
    - 从本地持久化存储 (`user_tokens.json`) 中查找该 Owner 的 User Access Token。
    - 如果 Token 过期，自动使用 Refresh Token 进行无感刷新。
4.  **直连下载**：使用 Owner 的身份凭证，调用妙计 API 获取 MP4 直链并下载到本地。
5.  **结果反馈**：调用机器人 API 向 Owner 发送“下载完成”通知。

---

## 🚀 快速开始

### 1. 飞书开发者后台配置

1.  **创建应用**：在 [飞书开发者后台](https://open.feishu.cn/app) 创建一个**企业自建应用**。
2.  **开通权限**：
    *   `下载妙记的音视频文件` (minutes:minutes.media:export) —— *核心下载权限*
    *   `获取用户 user ID` (contact:user.id:readonly) —— *用于识别会议归属*
    *   `以应用身份自建发送消息` (im:message:send_as_bot) —— *用于发送通知*
3.  **事件订阅**：
    *   配置请求网址 URL（开发环境可使用 Ngrok 地址，例如 `https://xxxx.ngrok-free.app/webhook/event`）。
    *   添加事件：`录制完成` (vc.meeting.recording_ready_v1)。
4.  **安全设置**：
    *   在“安全设置” -> “重定向 URL”中添加回调地址：`https://你的域名/auth/callback`。
5.  **发布版本**：
    *   **重要**：所有配置完成后，必须在“版本管理与发布”页面创建版本并发布，配置才会生效。

### 2. 本地环境部署

**环境要求**：Python 3.8+

1.  **安装依赖**：
    ```bash
    pip install -r requirements.txt
    ```

2.  **配置文件**：
    创建或修改 `config.json`，填入你的应用凭证：
    ```json
    {
        "app_id": "cli_xxxxxxxx",
        "app_secret": "xxxxxxxx",
        "encrypt_key": "",
        "verification_token": "xxxxxxxx",
        "download_path": "./downloads"
    }
    ```
    *注：`encrypt_key` 如果在后台开启了加密则需填写，否则留空。*

3.  **启动服务**：
    ```bash
    python3 listen_recording.py
    ```
    服务默认监听 `29090` 端口。

---

## 📖 使用手册

### 第一步：员工初始化授权（仅需一次）

由于会议录制通常属于隐私数据，机器人默认无法访问。需要员工本人进行一次授权。

1.  让员工在浏览器访问服务的授权页面：
    `https://你的域名/auth/start`
2.  如果通过 Ngrok 测试，URL 可能是 `https://xxxx.ngrok-free.app/auth/start`。
3.  点击页面上的“授权开启”按钮。
4.  跳转至飞书登录页（如已登录则自动跳过），确认授权。
5.  看到“Authorized successfully”提示即代表授权完成。
    *此后，该员工名下的所有会议录制，都会被系统自动捕获并下载。*

### 第二步：日常使用

无感化运行。员工只需正常开会：

1.  **开启录制**：在飞书会议中点击“录制”（云端录制）。
2.  **等待转码**：会议结束几分钟后，飞书云端处理完毕。
3.  **收到通知**：
    *   你的服务器会自动开始下载。
    *   下载完成后，飞书中的“**你的应用机器人**”会给该员工发送一条卡片消息：
        > ✅ **下载完成通知**
        > 📄 文件：`2024-03-20_Weekly_Meeting.mp4`
        > 💾 大小：`150.MB`
        > ⏱ 耗时：`45s`

---

## 🛳 生产环境部署建议

当你要从开发环境（Ngrok）切换到生产服务器时：

1.  **准备公网服务器**：确保服务器有公网 IP 或域名。
2.  **反向代理 (推荐)**：使用 Nginx 将域名 `https://minutes.your-company.com` 转发到本地 `29090` 端口。
3.  **更新后台配置**：
    *   将飞书后台的“请求网址 URL”更新为生产环境地址。
    *   将“重定向 URL”更新为生成环境地址。
4.  **后台运行**：
    不要直接用 `python` 运行，建议使用 `nohup` 或 `systemd` 守护进程：
    ```bash
    # 简单示例
    nohup python3 listen_recording.py > app.log 2>&1 &
    ```
5.  **发布新版本**：如果修改了后台配置（如 URL），记得在飞书后台重新发布版本。

---

## ❓ 常见问题 (FAQ)

**Q: 为什么要用 User Token?**
A: 这是为了权限隔离。机器人无法直接通过 API 下载所有人的妙计文件，必须代表“会议拥有者”去下载。

**Q: 代码中为什么会有 `vedio_api.py` 的手动 HTTP 请求？**
A: 我们修复了官方 SDK 在获取 Tenant Token 时的一个属性错误问题，改为使用原生 `requests` 库以保证稳定性。

**Q: 下载的文件在哪里？**
A: 默认在项目根目录的 `downloads/` 文件夹下。你可以在 `config.json` 中修改 `download_path`。

---

## 📂 核心文件说明
*   `listen_recording.py`: **服务入口**，Flask Web 服务器，处理 Webhook 事件和 Auth 路由。
*   `vedio_api.py`: **业务逻辑核心**，包含下载器、Token 管理器、消息发送器。
*   `token_manager.py`: **持久化层**，负责读写 `user_tokens.json`。
*   `requirements.txt`: **依赖列表**。
