class FeishuDownloaderError(Exception):
    """Base exception for Feishu Downloader App"""
    pass

class TokenExpiredError(FeishuDownloaderError):
    """Raised when token is expired and refresh fails"""
    pass

class DownloadError(FeishuDownloaderError):
    """Raised when download fails"""
    pass
