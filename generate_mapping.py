import os
import pwd
import json
import sys

# 该脚本由 GitHub Copilot 生成，用于在宿主机运行以生成 UID->User 映射
# 解决容器内无法解析宿主机用户的问题

# 默认配置 (根据您的环境调整)
NAS_ROOT_DEFAULT = "/vol1" 
MAPPING_FILE = "user_token/nas_mapping.json"

def main():
    # 允许通过命令行参数指定扫描路径
    nas_root = sys.argv[1] if len(sys.argv) > 1 else NAS_ROOT_DEFAULT
    
    print(f"正在准备生成映射文件...")
    print(f"- 扫描目录: {nas_root}")
    print(f"- 输出文件: {MAPPING_FILE}")

    # 1. 读取现有映射 (保留人工配置)
    data = {}
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"已加载现有映射: {len(data)} 条")
        except Exception as e:
            print(f"读取现有文件失败 (将创建新文件): {e}")

    # 2. 扫描目录并更新映射
    if not os.path.exists(nas_root):
        print(f"错误: 扫描目录不存在: {nas_root}")
        return

    count = 0
    skipped = 0
    
    try:
        items = os.listdir(nas_root)
        print(f"找到 {len(items)} 个项目，开始分析归属...")
        
        for item in items:
            full_path = os.path.join(nas_root, item)
            
            # 只处理目录
            if not os.path.isdir(full_path):
                continue
                
            try:
                # 获取 UID
                stat_info = os.stat(full_path)
                uid = stat_info.st_uid
                
                # 获取用户名
                try:
                    pw_entry = pwd.getpwuid(uid)
                    username = pw_entry.pw_name
                    
                    # 核心逻辑: 建立 "用户名 -> 目录名" 的映射
                    # 同时保存 原名 和 全小写名，确保匹配成功率
                    
                    # 1. 原名 (e.g. Shelly -> 1001)
                    data[username] = item
                    
                    # 2. 小写名 (e.g. shelly -> 1001)
                    lower_name = username.lower()
                    if lower_name != username:
                        data[lower_name] = item
                        
                    count += 1
                    # print(f"  [匹配] {username} (UID: {uid}) -> {item}")
                    
                except KeyError:
                    # UID 在系统中没有对应的用户名
                    skipped += 1
                    pass
                    
            except Exception as item_err:
                print(f"  [错误] 处理 {item} 时出错: {item_err}")
                
    except Exception as e:
        print(f"扫描过程中发生错误: {e}")
        return

    # 3. 写入文件
    try:
        # 确保存放目录存在
        os.makedirs(os.path.dirname(MAPPING_FILE), exist_ok=True)
        
        with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        print(f"\n成功! 映射文件已更新: {MAPPING_FILE}")
        print(f"- 新增/更新用户目录映射: {count}")
        print(f"- 跳过无名UID目录: {skipped}")
        print(f"- 总条目数: {len(data)}")
        print("注意: 容器内的程序会自动读取此文件，无需重启容器。")
        
    except Exception as e:
        print(f"写入文件失败: {e}")

if __name__ == "__main__":
    main()
