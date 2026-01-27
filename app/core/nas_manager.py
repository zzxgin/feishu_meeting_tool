import os
import json
import shutil
from pypinyin import lazy_pinyin
from app.utils.logger import logger

class NasManager:
    # 容器映射路径 (对应宿主机 /vol1)
    NAS_ROOT = "/nas_data"
    MAPPING_FILE = "app/data/nas_mapping.json"

    @staticmethod
    def _load_mapping():
        if os.path.exists(NasManager.MAPPING_FILE):
            try:
                with open(NasManager.MAPPING_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    @staticmethod
    def get_nas_folder(user_name, user_id):
        """
        根据用户姓名寻找 NAS 目录
        优先级:
        1. 手动映射表 (app/data/nas_mapping.json)
        2. 全拼匹配 (张三 -> zhangsan)
        3. 英文名直接匹配 (Shelly -> shelly)
        4. 首字母匹配 (张三 -> zs) - 可选，暂不开启防止误判
        """
        if not user_name:
            return None

        # 1. 查映射表
        mapping = NasManager._load_mapping()
        # 支持按 user_id 查
        if user_id in mapping:
            folder = mapping[user_id]
            if os.path.exists(os.path.join(NasManager.NAS_ROOT, folder)):
                return folder

        # 清洗名字 (去掉空格，转小写)
        clean_name = user_name.strip().lower()

        # 2. 尝试全拼 (张三 -> zhangsan)
        # lazy_pinyin 会把 "张三" 变成 ['zhang', 'san']，"Shelly" 还是 ['Shelly']
        pinyin_list = lazy_pinyin(clean_name)
        pinyin_name = "".join(pinyin_list).lower()
        
        target_path = os.path.join(NasManager.NAS_ROOT, pinyin_name)
        if os.path.exists(target_path):
            return pinyin_name

        # 3. 尝试直接匹配 (针对纯英文名的情况，如 "Shelly")
        # 如果 lazy_pinyin 没变（说明是英文），上面其实已经覆盖了，但为保险再查一次原名
        target_path_raw = os.path.join(NasManager.NAS_ROOT, clean_name)
        if os.path.exists(target_path_raw):
            return clean_name

        return None

    @staticmethod
    def archive_file(local_file_path, user_name, user_id):
        """
        将文件归档到 NAS
        返回: (是否成功, 最终路径, 匹配到的文件夹名)
        """
        folder_name = NasManager.get_nas_folder(user_name, user_id)
        
        if not folder_name:
            logger.warning(f"[NAS归档] 未找到用户 {user_name} ({user_id}) 的NAS目录")
            return False, local_file_path, None

        try:
            filename = os.path.basename(local_file_path)
            # 目标: /nas_data/zhangsan/filename.mp4
            nas_path = os.path.join(NasManager.NAS_ROOT, folder_name, filename)
            
            # 移动文件
            shutil.move(local_file_path, nas_path)
            
            # 修改权限 (确保 NAS 用户能读写，通常设为 6666 或 777)
            # 注意：在 Docker 挂载卷中 chown 可能无效，但 chmod 通常可以
            try:
                os.chmod(nas_path, 0o666)
            except Exception as e:
                logger.warning(f"修改文件权限失败: {e}")

            logger.info(f"[NAS归档] 成功移动文件: {local_file_path} -> {nas_path}")
            return True, nas_path, folder_name
            
        except Exception as e:
            logger.error(f"[NAS归档] 移动失败: {e}")
            return False, local_file_path, None
