from app import create_app
from app.utils.logger import logger

app = create_app()

if __name__ == "__main__":
    logger.info(f"启动 HTTP Server 监听端口 29090...")
    try:
        from waitress import serve
        logger.info("✅ 使用 Waitress 生产级服务器启动...")
        serve(app, host="0.0.0.0", port=29090)
    except ImportError:
        logger.warning("⚠️ 未安装 waitress，回退到 Flask 开发服务器...")
        logger.warning("建议安装: pip install waitress")
        app.run(host="0.0.0.0", port=29090)
