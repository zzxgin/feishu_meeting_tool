# Feishu Meeting Auto-Downloader (飞书会议自动录制下载器)

这是一个基于飞书开放平台 (Lark Open Platform) 的企业级自动化工具。旨在解决企业会议归档痛点，自动监听并下载员工的会议录制文件，并通过飞书机器人发送完成通知。

## ✨ 核心特性

- **🤖 全自动监听**：无需人工干预，通过 Webhook 实时监听“会议结束”事件，自动轮询录制文件。
- **🔐 多用户/多租户支持**：
    - 支持企业内多位员工同时使用。
    - 严格遵循隐私安全原则，**谁的会议用谁的身份下载**。
    - 采用 **OAuth2 User Token** 模式，由员工授权，应用自动代理下载。
- **⚡️ 极速直连下载**：
    - 直接通过妙计 Token 接口获取高清 MP4 直链，无需处理复杂的云文档权限。
    - 支持断点续传（基础版），流式写入，节省服务器内存。
- **✅ 全场景覆盖**：
    - **API 预约会议**：完美支持。
    - **手动发起会议**：完美支持（通过会议结束事件 + 智能轮询机制实现）。
- **🔔 智能消息通知**：
    - 下载完成后，机器人会自动给会议拥有者发送飞书卡片消息。
    - 消息包含文件名、大小及耗时信息。
- **🔄 Token 自动续期**：内置 Token 自动刷新机制，一次授权，长期有效。
- **🛡 安全合规**：
    - 仅申请最小必要权限。
    - 所有的下载操作都有迹可循。

---

## 🏗 架构原理

本项目采用 **Webhook 事件驱动 + 智能轮询 + OAuth2 授权代理** 架构：

1.  **事件触发**：飞书会议结束 (`vc.meeting.all_meeting_ended_v1`) 后，向本服务推送事件。
2.  **智能轮询**：服务收到结束信号后，启动后台任务，每隔一段时间查询录制文件是否生成（兼容手动和自动会议）。
3.  **身份识别**：提取 `owner_id` (会议拥有者) ，并从本地持久化存储 (`user_tokens.json`) 中查找该 Owner 的 User Access Token。
4.  **智能代理**：
    - 如果 Token 过期，自动使用 Refresh Token 进行无感刷新。
5.  **直连下载**：使用 Owner 的身份凭证，获取 MP4 直链并下载到本地。
6.  **结果反馈**：调用机器人 API 向 Owner 发送“下载完成”通知。

---

## 🚀 快速开始

### 1. 飞书开发者后台配置

1.  **创建应用**：在 [飞书开发者后台](https://open.feishu.cn/app) 创建一个**企业自建应用**。
2.  **开通权限**：
    *   `下载妙记的音视频文件` (minutes:minutes.media:export) —— *用于下载*
    *   `获取用户 user ID` (contact:user.id:readonly) —— *用于识别会议归属*
    *   `获取会议录制信息` (vc:record:readonly) —— *用于查询手动会议录制*
    *   `以应用身份自建发送消息` (im:message:send_as_bot) —— *用于发送通知*
3.  **事件订阅**：
    *   配置请求网址 URL。
    *   添加事件：`会议结束` (vc.meeting.all_meeting_ended_v1)。
    *   *(可选) 移除 `录制完成` 事件以避免重复日志。*
4.  **安全设置**：
    *   在“安全设置” -> “重定向 URL”中添加回调地址：`https://你的域名/auth/callback`。
5.  **发布版本**：
    *   **重要**：所有配置完成后，必须在“版本管理与发布”页面创建版本并发布，配置才会生效。

### 3. CI/CD 自动化部署 (GitLab CI)

本项目已配置 GitLab CI/CD 流程。当您把代码推送到 `main` 分支时，会自动部署到您的服务器。

#### 前置准备
1.  **服务器准备**：确保您的云服务器安装了 `python3`, `pip`, `venv`。
2.  **创建目录**：在服务器上创建目录 `mkdir -p /opt/feishu_minute` 并确保您的 SSH 用户有读写权限。

#### GitLab CI/CD 变量配置
请在 GitLab 仓库的 **Settings** -> **CI/CD** -> **Variables** 中添加以下 Key/Value（记得取消勾选 "Protect variable" 除非你的分支也是受保护的）：

| Key (变量名) | 说明 | 类型 |
| :--- | :--- | :--- |
| `PRODUCTION_HOST` | 服务器 IP 地址 | Variable |
| `PRODUCTION_USER` | SSH 用户名 (如 root) | Variable |
| `SSH_PRIVATE_KEY` | SSH 私钥内容 (cat ~/.ssh/id_rsa) | Variable (File 类型也可，需微调配置) |
| `PRODUCTION_APP_ID` | 飞书应用 App ID | Variable |
| `PRODUCTION_APP_SECRET` | 飞书应用 App Secret | Variable |
| `PRODUCTION_VERIFICATION_TOKEN` | 飞书事件验证 Token | Variable |

配置完成后，每次 `git push` 即可自动发布。

### 4. 本地环境部署 (开发用)

**环境要求**：Python 3.8+

1.  **安装依赖**：
    ```bash
    pip install -r requirements.txt
    ```

2.  **配置文件**：
    创建 `.env` 文件 (可参考 `.env.example`)，填入你的应用凭证：
    ```bash
    APP_ID=cli_xxxxxxxx
    APP_SECRET=xxxxxxxx
    ENCRYPT_KEY=
    VERIFICATION_TOKEN=xxxxxxxx
    DOWNLOAD_PATH=./downloads
    ```
    *注：`ENCRYPT_KEY` 如果在后台开启了加密则需填写，否则留空。*

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
