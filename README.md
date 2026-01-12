# 飞书会议自动归档助手 (Feishu Meeting Auto-Downloader)

这是一个基于飞书开放平台 API 开发的企业级自动化工具，专为公司内部部署设计。它能够自动监听、识别并下载全公司已授权员工的飞书妙计（会议录制）视频到本地服务器，实现会议资产的自动归档与备份。

## ✨ 核心功能亮点

*   **🔒 企业级多用户支持**
    *   **权限隔离**：采用 OAuth 2.0 用户授权模式。机器人自动识别会议的“拥有者”，并使用该员工自己的 Token 进行下载，完美解决跨部门/私有会议的 `Permission Deny` 问题。
    *   **一次授权，永久有效**：内置 Token 自动刷新机制，员工只需首次点击链接授权，后续无需任何操作。

*   **🔄 双轨制自动下载策略**
    *   **轨道一：实时推送 (Webhook)**
        *   针对 API 创建的会议，监听 `vc.meeting.recording_ready_v1` 事件，实现毫秒级响应，录制结束即刻下载。
    *   **轨道二：智能巡检 (Auto Polling)**
        *   内置后台巡检服务（Polling Service），每 5 分钟自动检查一次已授权员工的最近会议。
        *   **完美解决痛点**：填补了飞书官方“手动创建会议不触发 Webhook”的缺陷，确保任何形式（手动发起、日程会议）的录制都能被抓取。

*   **🛡 隐私与安全**
    *   **本地存储**：所有视频文件直接保存至服务器本地目录（`./downloads`），数据不经过第三方云存储。
    *   **最小权限原则**：仅申请妙计只读权限 (`minutes:minutes:readonly`)，自动剥离了敏感的云文档全局读取权限 (`drive:drive:readonly`)，更符合企业安全规范。

---

## 🛠 技术架构

*   **语言**: Python 3.9+
*   **Web 框架**: Flask (用于接收 Webhook 回调及处理 OAuth 授权)
*   **API 交互**: Requests + Lark Open Platform SDK
*   **数据管理**:
    *   `token_manager.py`: 线程安全的 Token 存取与自动刷新逻辑。
    *   `user_tokens.json`: 轻量级本地 JSON 存储（无数据库依赖，部署极简）。

## 📂 项目结构说明

```text
.
├── listen_recording.py    # [主程序] Web服务器入口，处理 Webhook 事件与用户授权
├── vedio_api.py           # [核心逻辑] 封装飞书 API 调用、视频流下载、Token 刷新
├── polling_service.py     # [后台服务] 自动轮询线程，负责抓取手动创建的会议
├── token_manager.py       # [数据层] 管理多用户的 Token 读取与写入
├── config.json            # [配置文件] 存放 AppID、Secret 等应用配置
├── user_tokens.json       # [自动生成] 存储已授权用户的 Token 数据 (勿删)
├── download_history.json  # [自动生成] 记录已下载过的会议 ID，防止重复下载
├── requirements.txt       # 依赖包列表
└── downloads/             # 视频文件下载目录
```

---

## 🚀 部署指南 (Deploy)

### 1. 环境准备
确保服务器已安装 Python 3.9 或以上版本。
```bash
git clone [你的仓库地址]
cd feishu_minute
# 建议创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate
# 安装依赖
pip install -r requirements.txt
```

### 2. 应用配置
编辑 `config.json` 文件，填入飞书开放平台的信息：
```json
{
    "app_id": "cli_xxxxxxxxxxxx",
    "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxx",
    "encrypt_key": "",
    "verification_token": "xxxxxxxxxxxxxxxxxxxxxxxx",
    "download_path": "./downloads"
}
```
*   *注意：`encrypt_key` 如果后台没开启加密可留空。*

### 3. 飞书后台配置
登录 [飞书开放平台](https://open.feishu.cn/app)，进入你的应用：
1.  **权限管理** -> 开通以下权限并**发布版本**：
    *   `minutes:minutes:readonly` (查看妙计内容)
    *   `minutes:minutes.media:export` (导出妙计媒体)
    *   `contact:user.id:readonly` (获取用户 User ID)
2.  **事件订阅** -> 配置请求地址：
    *   `http://你的公网IP:29090/webhook/event`
3.  **安全设置** -> 配置重定向 URL：
    *   `http://你的公网IP:29090/auth/callback`

### 4. 启动服务
建议在生产环境使用 `nohup` 后台运行：
```bash
nohup python3 listen_recording.py > server.log 2>&1 &
```
服务启动后将监听 `0.0.0.0:29090`。

---

## 👥 员工使用手册

### 步骤一：全员授权 (仅需一次)
管理员将授权链接分发给公司员工：
> **授权链接**: `http://你的服务器IP:29090/auth/start`

员工点击链接 -> 点击“授权开启” -> 看到成功提示即可。
*这一步是为了让机器人获取下载该员工名下会议的权限。*

### 步骤二：日常使用
员工无需任何操作。只需正常使用飞书开会并录制，会议结束后（约 5-10 分钟内），视频文件会自动出现在服务器的 `downloads` 目录下。

---

## ❓ 常见问题 (Q&A)

**Q1: 为什么手动开的会没有立即下载？**
A: 手动会议不触发 Webhook，依赖后台巡检服务。巡检每 5 分钟运行一次，所以可能会有几分钟的延迟，这是正常现象。

**Q2: 如何重新下载已下载过的视频？**
A: 修改 `download_history.json`，删除对应的 `object_token`，系统会在下一次巡检时重新下载。

**Q3: Token 过期了怎么办？**
A: 系统会在下载前自动检查 Token 有效期并自动刷新，无需员工重新登录。

---

*Developed for internal efficiency optimization.*
