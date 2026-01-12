# 飞书会议自动归档助手 (Feishu Meeting Auto-Downloader)

这是一个基于飞书开放平台 API 开发的自动化工具，能够自动监听并下载飞书妙计（会议录制）视频到本地服务器。支持多用户模式，适合企业内部部署，实现全员会议自动归档。

## ✨ 核心功能

*   **全自动下载**：
    *   **实时推送**：通过 Webhook 监听 API 创建的会议，录制完成后立即下载。
*   **企业级多用户**：
    *   支持无限数量的员工授权。
    *   自动识别会议拥有者 (Owner)，使用对应的 User Token 下载，**解决 permissions deny 问题**。
    *   Token 自动续期，无需人工干预。
*   **私有化部署**：视频直接下载到本地或服务器硬盘，保障数据隐私。

## 🛠 技术栈

*   **语言**: Python 3.9+
*   **框架**: Flask (Web服务), Requests (API交互)
*   **SDK**: Lark Open Platform SDK
*   **存储**: 本地 JSON 文件 (无数据库依赖，轻量级)

## 🚀 快速开始

### 1. 环境准备
```bash
# 克隆项目
git clone [你的仓库地址]
cd feishu_minute

# 安装依赖
pip install -r requirements.txt