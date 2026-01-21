from flask import Flask
from app.utils.logger import logger
from app.api.routes import api_bp

def create_app():
    app = Flask(__name__)
    
    # 注册路由 Blueprint
    app.register_blueprint(api_bp)
    
    logger.info("Flask App Initialized")
    return app
