# Feishu Meeting Auto-Downloader (飞书会议自动录制下载器)

这是一个基于飞书开放平台 (Lark Open Platform) 的企业级自动化工具。旨在解决企业会议归档痛点，自动监听并下载员工的会议录制文件。

## ✨ 核心特性

- **🤖 全自动监听**：无需人工干预，通过 Webhook 实时监听“会议录制完成”事件。
- **🔐 多用户/多租户支持**：
    - 支持企业内多位员工同时使用。
    - 严格遵循隐私安全原则，**谁的会议用谁的身份下载**。
    - 采用 **OAuth2 User Token** 模式，由员工授权，应用自动代理下载。
- **⚡️ 极速直连下载**：
    - 破解传统 API 迷宫，直接通过妙计 Token (`obcn...`) 获取下载直链。
    - 摒弃繁琐的“查会议ID -> 查文档权限”旧流程，效率提升且权限依赖更少。
- **🔄 Token 自动续期**：内置 Token 自动刷新机制，一次授权，永久有效。
- **🛡 安全合规**：
    - 仅申请最小必要权限 (`minutes:minutes.media:export`)。
    - 所有下载操作基于用户明确授权，可审计追溯。

---

## 🏗 架构原理

本项目采用 **Webhook 事件驱动 + OAuth2 授权代理** 架构：

1.  **事件触发**：飞书会议结束并完成云端转码后，向本服务推送 `vc.meeting.recording_ready_v1` 事件。
2.  **身份识别**：服务解析事件，提取 `owner_id` (会议拥有者) 和 `minute_token` (妙计标识)。
3.  **智能代理**：
    - 从本地持久化存储 (`user_tokens.json`) 中查找该 Owner 的 Access Token。
    - 如果 Token 过期，自动使用 Refresh Token 进行无感刷新。
4.  **直连下载**：使用 Owner 的身份凭证，调用妙计 API 获取 MP4 直链并流式下载到本地。

---

## 🚀 快速开始

### 1. 飞书开发者后台配置

1.  **创建应用**：在 [飞书开发者后台](https://open.feishu.cn/app) 创建一个**企业自建应用**。
2.  **开通权限**：
    *   `下载妙记的音视频文件` (minutes:minutes.media:export) —— *核心下载权限*
    *   `获取用户 user ID` (contact:user.id:readonly) —— *用于识别会议归属*
3.  **事件订阅**：
    *   配置请求网址 URL（开发环境可使用 Ngrok 等内网穿透工具）。
    *   添加事件：`录制完成` (vc.meeting.recording_ready_v1)。
4.  **安全设置**：
    *   在“重定向 URL”中添加回调地址：`https://你的域名/auth/callback`。
5.  **发布版本**：所有配置完成后，务必在该页面创建版本并申请发布。

---

### 2. 本地环境部署

**环境要求**：Python 3.8+

1.  **安装依赖**：
    ```bash
    pip install flask requests lark-oapi
    ```

2.  **配置文件**：
    创建 `config.json`：
    ```json
    {
        "app_id": "cli_xxxxxxxx",
        "app_secret": "xxxxxxxx",
        "encrypt_key": "",
        "verification_token": "xxxxxxxx",
        "download_path": "./downloads"
    }
    ```

3.  **启动服务**：
    ```bash
    python3 listen_recording.py
    ```
    服务默认监听 `29090` 端口。

---

### 3. 使用流程 (User Journey)

**Step 1: 员工授权 (首次必需)**
为了保护隐私，应用不能随意下载员工的会议。员工需进行一次性授权：
*   访问 `https://你的域名/auth/start`
*   点击“授权开启”
*   *成功后，应用获得该员工的长期“代理下载权”。*

**Step 2: 正常使用**
*   员工正常使用飞书开会、录制。
*   会议结束后，录制文件会自动下载到服务器的 `./downloads` 目录，文件名为 `obcn_xxxx.mp4`。
*   (可选) 你可以进一步开发脚本，将下载好的文件上传到 NAS 或对象存储。

---

## ❓ 常见问题 (FAQ)

**Q: 为什么要用 User Token 而不是 Tenant Token (机器人身份)?**
A: 飞书的安全机制决定了机器人默认**不可见**员工的私有会议录制。使用 User Token 可以完美解决“可见性”问题，实现零感知的自动化下载，且符合“谁授权下谁的数据”的安全原则。

**Q: Token 会过期吗？**
A: `user_access_token` 有效期仅 2 小时，但通过我们的 `refresh_token` 机制（有效期 30 天且滚动刷新），只要应用保持运行或定期有任务触发，理论上授权永久有效。

**Q: 下载失败提示 Token 无效？**
A: 请让该员工重新访问 `/auth/start` 页面重新授权一次即可。

---

## 📂 项目结构
*   `listen_recording.py`: 主服务，负责 Webhook 监听与 OAuth 授权流程。
*   `vedio_api.py`: 核心下载引擎，封装了妙计 API 和 Token 刷新逻辑。
*   `token_manager.py`: 身份凭证管理，负责 Token 的安全存储与读取。
*   `create_api_meeting.py`: (测试用) 快速创建 API 会议用于验证功能。
