import os
import csv
import json
import logging
import requests
from app.utils.feishu_client import get_tenant_access_token
from app.utils.config import load_config
from app.utils.logger import logger

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_all_users_in_department(access_token, department_id="0", parent_dept_name=""):
    """
    递归获取部门下的所有用户
    API: GET /open-apis/contact/v3/users
    """
    users = []
    
    # 1. 获取本部门直属用户
    url = "https://open.feishu.cn/open-apis/contact/v3/users"
    params = {
        "department_id": department_id,
        "page_size": 50,
        "department_id_type": "open_department_id"
    }
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        has_more = True
        page_token = ""
        while has_more:
            if page_token:
                params["page_token"] = page_token
            
            resp = requests.get(url, headers=headers, params=params)
            data = resp.json()
            
            if data.get("code") != 0:
                logging.error(f"获取部门用户失败: {data.get('msg')}")
                break
                
            items = data.get("data", {}).get("items", [])
            for item in items:
                users.append({
                    "user_id": item.get("user_id", "无权限获取"),
                    "open_id": item.get("open_id"),
                    "name": item.get("name"),
                    "en_name": item.get("en_name", ""),
                    "email": item.get("email", ""),
                    "department": parent_dept_name or "根部门"
                })
            
            has_more = data.get("data", {}).get("has_more", False)
            page_token = data.get("data", {}).get("page_token", "")
            
    except Exception as e:
        logging.error(f"请求用户列表异常: {e}")

    # 2. 递归获取子部门的用户
    # API: GET /open-apis/contact/v3/departments/:department_id/children
    try:
        sub_url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children"
        sub_params = {
            "page_size": 50,
            "department_id_type": "open_department_id",
            "fetch_child": True # 关键参数: 递归获取所有子部门
        }
        
        # 注意：上面的接口是获取子部门列表，然后我们需要遍历子部门去拿用户。
        # 但飞书其实有一个更简单的接口：Scope 获取。或者我们直接遍历部门树。
        # 简单方案：先获取子部门列表
        
        has_more_dept = True
        page_token_dept = ""
        
        while has_more_dept:
             if page_token_dept:
                 sub_params["page_token"] = page_token_dept
                 
             resp = requests.get(sub_url, headers=headers, params=sub_params)
             data = resp.json()
             
             if data.get("code") == 0:
                 sub_depts = data.get("data", {}).get("items", [])
                 for dept in sub_depts:
                     # 优先使用 open_department_id，以匹配 department_id_type=open_department_id 参数
                     dept_id = dept.get("open_department_id")
                     if not dept_id:
                         # 如果没有 open_department_id，尝试使用 department_id，但通常这两个字段应该是对应的
                         dept_id = dept.get("department_id")
                         
                     dept_name = dept.get("name")
                     logging.info(f"正在抓取子部门: {dept_name} ({dept_id})")
                     # 递归调用
                     users.extend(get_all_users_in_department(access_token, dept_id, dept_name))
                 
                 has_more_dept = data.get("data", {}).get("has_more", False)
                 page_token_dept = data.get("data", {}).get("page_token", "")
             else:
                 logging.warning(f"获取子部门失败: {data.get('msg')}")
                 break

    except Exception as e:
        logging.error(f"遍历子部门异常: {e}")
    
    return users

def export_users_to_csv():
    """
    导出所有用户信息到 CSV
    """
    config = load_config()
    if not config.get("app_id") or not config.get("app_secret"):
        logging.error("请确保环境变量 APP_ID 和 APP_SECRET 已设置 (在 .env 文件中)")
        return

    logging.info("正在获取 Tenant Access Token...")
    token = get_tenant_access_token()
    if not token:
        logging.error("获取 Token 失败，无法继续")
        return

    logging.info("正在拉取全员信息 (默认部门ID=0)...")
    # department_id="0" 通常代表根部门/全公司
    # 注意: 需要开通权限 contact:user.base:readonly 和 contact:department.base:readonly
    all_users = get_all_users_in_department(token, department_id="0")
    
    if not all_users:
        logging.warning("未获取到任何用户，请检查应用的权限范围 (通讯录权限)")
        return

    # 去重逻辑：根据 user_id 去重，但合并部门信息
    unique_users_map = {}
    for u in all_users:
        uid = u.get("user_id")
        if uid:
            if uid not in unique_users_map:
                unique_users_map[uid] = u
            else:
                # 如果用户已存在，检查是否需要合并部门信息
                existing_dept = unique_users_map[uid].get("department", "")
                new_dept = u.get("department", "")
                
                # 如果新部门不为空，且还没记录过，就追加上去
                if new_dept and new_dept not in existing_dept:
                    unique_users_map[uid]["department"] = f"{existing_dept}; {new_dept}"
    
    final_users = list(unique_users_map.values())

    csv_file = "feishu_users.csv"
    headers = ["name", "user_id", "open_id", "email", "en_name", "department"]
    
    try:
        with open(csv_file, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for u in final_users:
                writer.writerow(u)
        
        logging.info(f"✅ 成功导出 {len(final_users)} 名用户到文件: {csv_file} (已去重)")
        print(f"\n文件路径: {os.path.abspath(csv_file)}")
        
    except Exception as e:
        logging.error(f"写入 CSV 失败: {e}")

if __name__ == "__main__":
    export_users_to_csv()
