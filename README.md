# 飞书视频会议录制自动归档工具 (Feishu Meeting Auto-Downloader)

## 项目简介
这是一个基于 Python Flask + Waitress 开发的自动化工具，旨在解决飞书/Lark 会议录制文件的自动归档问题。

当会议结束或录制生成时，本服务会自动接收飞书事件回调，使用用户的授权 Token 下载妙记音视频文件，并将其重命名为易读格式（姓名+会议名+时间），最后通过飞书卡片通知用户。

项目支持 **Docker 容器化** 及 **GitLab CI/CD** 全自动部署。

## 核心功能
*   **📡 自动监听**: 实时响应飞书 `all_meeting_ended` (会议结束) 事件，并自动轮询录制状态 (智能阶梯式检测策略，覆盖 30 分钟)。
*   **📥 智能下载**: 自动提取录制 Token，调用妙记 API 高速下载 MP4 视频。
*   **🏷️ 自动命名**: 下载文件自动重命名为 `姓名_会议主题_时间.mp4` 格式。(如 `张三_周会_20260119_1000.mp4`)。
*   **📂 NAS 智能分发**:
    *   **个人归档**: 根据 UserID 或姓名，自动归类至 `/nas_data/{UserID}` 或 `/nas_data/{User_Name}`。
    *   **团队归档**: 自动读取用户所属的部门信息 (支持多部门)，将文件副本分发至 `/nas_data/@team/{部门名称}/` 目录，实现团队文件共享。
*   **📢 消息通知**: 
    *   下载成功：发送包含文件名和路径的绿色通知卡片。
    *   授权失效：发送红色警告卡片，用户点击卡片上的按钮即可一键重新授权。
    *   **自动补录**：用户完成授权后，系统会自动触发回调，立即重新下载本次错过的会议录制，并自动接管后续所有新会议的下载任务，全程无缝衔接。
*   **🔐 授权管理**: 提供独立的 OAuth2 授权页面，Token 安全存储并支持自动刷新。
*   **💾 数据持久化**: 视频文件、用户 Token 数据及运行日志通过 Docker Volume 持久化存储，重启不丢失。

## 目录结构
```text
feishu_minute/
├── app/                  # [核心代码包]
│   ├── __init__.py       # Flask 应用工厂函数
│   ├── api/              # [API 层] Web 接口与路由
│   │   ├── routes.py     # 授权与回调路由
│   │   └── event_handler.py # 事件处理逻辑
│   ├── core/             # [业务逻辑层] 
│   │   ├── downloader.py # 视频下载核心 (含防重、原子写入)
│   │   ├── meeting_service.py # 飞书 API 业务调用
│   │   ├── nas_manager.py   # [新增] NAS 路径映射与分发管理
│   │   └── notification.py # 飞书卡片构建与发送
│   ├── data/             # [数据访问层]
│   │   └── token_store.py # Token 持久化存储
│   └── utils/            # [工具层] 配置、日志、异常
├── run.py                # [启动入口] 程序启动文件
├── export_feishu_users.py # [新增] 通讯录导出工具 (辅助生成 NAS 映射)
├── Dockerfile            # 容器构建文件
├── docker-compose.yml    # Docker 编排配置
├── config.json           # 飞书应用配置文件
├── .gitlab-ci.yml        # CI/CD 流水线配置
└── requirements.txt      # Python 依赖
```

## 快速开始

### 1. 飞书开放平台配置
在 [飞书开发者后台](https://open.feishu.cn/app) 创建企业自建应用，并配置：

1.  **开启机器人能力**。
2.  **权限管理 (Scopes)**:
    *   `minutes:minutes.media:export`: 导出和下载妙记 (核心)
    *   `contact:user.id:readonly`: 获取用户 User ID
    *   `contact:user.base:readonly`: 获取用户姓名 (用于文件名)
    *   `vc:record:readonly`: 获取录制信息
    *   `vc:meeting:readonly`: 获取会议主题和时间 (用于文件名)
3.  **事件订阅**:
    *   视频会议 -> 会议结束 (`vc.meeting.all_meeting_ended_v1`)
    *   请求地址配置为: `https://你的域名/webhook/event`
    *   **加密策略**: 建议关闭 (Encrypt Key 留空)。
4.  **安全设置**:
    *   重定向 URL 添加: `https://你的域名/auth/callback`

### 2. 环境变量配置
复制 `.env.example` 为 `.env`，并填入你的应用信息：
```env
APP_ID=cli_xxxxxxxxxxxx
APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
APP_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxx
# APP_ENCRYPT_KEY=  <-- 建议注释掉或留空
DOWNLOAD_PATH=./downloads
```

### 3. 本地运行
```bash
# 1. 安装依赖
pip3 install -r requirements.txt

# 2. 启动服务 (自动选择 Waitress 生产服务器或 Flask 开发服务器)
python3 run.py
```
服务默认监听端口: `29090`。

### 4. 用户授权
服务启动后，用户需进行一次性授权：
访问 `http://localhost:29090/auth/start` (或你的生产域名)，点击“授权开启”。

## Docker 部署

我们推荐使用 `docker-compose` 进行更管理化的部署，它可以自动读取 `.env` 并管理挂载目录。

### 1. 启动容器
```bash
docker compose up -d
```

### 2. 停止容器
```bash
docker compose down
```

如果不使用 Compose (手动模式):
```bash
docker build -t feishu-minute .
docker run -d \
  --name feishu-minute \
  --restart always \
  -p 29090:29090 \
  -v $(pwd)/downloads:/app/downloads \
  -v $(pwd)/user_token:/app/user_token \
  -v $(pwd)/logs:/app/logs \
  -v /etc/localtime:/etc/localtime:ro \
  --env-file .env \
  feishu-minute
```
*   `/app/downloads`: 映射本地目录存储视频。
*   `/app/user_token`: 映射本地目录存储 `user_tokens.json`。
*   `/etc/localtime`: 挂载宿主机时间，确保日志时间正确。

## GitLab CI/CD 自动化部署

本项目已配置完整的 CI/CD 流程 (Test -> Build -> Deploy)，适配 **Harbor 镜像仓库** 和 **SSH 远程部署**。

### 1. GitLab Variables 配置
在 GitLab 项目 -> Settings -> CI/CD -> Variables 中添加：

| 变量名 | 说明 |
| :--- | :--- |
| `APP_ID` | 飞书 App ID |
| `APP_SECRET` | 飞书 App Secret |
| `APP_VERIFICATION_TOKEN` | 飞书 Verification Token |
| `HARBOR_URL` | Harbor 仓库地址 (如 `harbor.example.com`) |
| `HARBOR_USER` | Harbor 用户名 |
| `HARBOR_PASSWORD` | Harbor 密码 |
| `HARBOR_PROJECT` | Harbor 项目名 |
| `SERVER_IP` | 生产服务器 IP |
| `SERVER_USER` | SSH 登录用户 (通常为 `root`) |
| `SSH_PRIVATE_KEY` | SSH 私钥 (用于 Runner 登录服务器) |
| `DEPLOY_ENV` | 部署环境标识 (可选)。设为 `test` 时自动部署，其他情况需手动确认。 |
| `VERSION` | 镜像版本号 (可选)。设为如 `v1.0.0`，构建时会同时打上该版本标签和 `latest`。 |

### 2. 部署流程
1.  **提交代码**: 推送代码到 `main` 分支触发流水线。
2.  **Test 阶段**: 自动进行 `flake8` 代码质量检查和依赖安装测试 (配置了阿里云镜像加速)。
3.  **Build 阶段**: 
    *   使用 `docker:dind` 构建轻量级镜像。
    *   支持**双标签构建**: 同时推送指定版本 (`$VERSION`) 和 `latest` 标签到 Harbor。
4.  **Deploy 阶段**:
    *   **安全部署**: 默认采用 **Manual** (手动点击) 模式防止误发生产。仅当 `DEPLOY_ENV=test` 时自动执行。
    *   自动处理容器命名冲突: 部署前强制停止并删除旧容器。
    *   将 `docker-compose.yml` 模板发送至服务器。
    *   将 GitLab Variables 注入并生成 `.env` 配置文件。
    *   执行 `docker compose up -d` 平滑更新服务。

## 工程化规范
*   **Atomic Write**: 下载时先写入 `.temp` 文件，校验通过后才重命名为 `.mp4`，防止网络中断产生损坏文件。
*   **.dockerignore**: 已排除 `__pycache__`, `.env`, `.git` 等无关文件，确保镜像小巧安全。
*   **Docker Compose**: 采用 `docker-compose.yml` 管理服务编排，支持一键启动和持久化挂载配置。
*   **安全机制**: 敏感配置全流程不落地，仅在部署时通过 CI 注入生产服务器内存/临时文件，不在代码库中明文存储。
*   **Token 自动刷新**: 内置 Token 续期机制，当监测到 Token 过期 (401 错误) 时，会自动使用 Refresh Token 换取新令牌并静默重试下载任务，确保持续服务稳定性。

## 注意事项
1.  **权限发布**: 在飞书开发者后台申请权限后，必须创建并发布新的 **应用版本**，经管理员审核通过后，正式版环境才会生效。
2.  **挑战验证**: 首次配置飞书请求地址时，需确保服务已启动且能访问。如果飞书报错 "Challenge code没有返回"，请检查是否错误配置了 Encrypt Key。
3.  **妙记权限**: 必须确保已开通 `minutes:minutes.media:export` 权限，否则无法下载视频文件。此权限通常默认未开通，需单独申请。

## 性能评估
*   **事件并发**: 使用 Waitress 多线程服务器，可轻松处理每秒数百次的飞书事件回调 (TPS > 200)，足以应对大型企业的会议结束高峰。
*   **下载并发**: 视频下载属于网络 IO 密集型任务。单节点建议同时下载并发数控制在 **10-20 个** 左右，具体取决于服务器的网络带宽和磁盘写入速度。
*   **扩展性**: 支持水平扩展。若负载过高，可增加 Docker 容器副本数，并配合 Nginx 负载均衡即可线性提升处理能力。