import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    # Lấy thông tin kết nối từ biến môi trường DATABASE_URL
    # Nếu không có, sử dụng chuỗi kết nối mặc định dựa trên cấu hình dự án
    db_url = os.environ.get(
        'DATABASE_URL', 
        'postgresql://openwebui_user:YOUR_DB_PASSWORD@postgres:5432/openwebui'
    )
    
    print(f"Connecting to database...")
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Đọc cấu hình hiện tại
        cursor.execute("SELECT id, data FROM config;")
        configs = cursor.fetchall()
        
        if not configs:
            print("No config records found in the database.")
            return
            
        print(f"Found {len(configs)} config record(s).")
        
        # Danh sách 5 MCP servers muốn giữ lại
        allowed_servers = ['office365', 'playwright', 'fetch', 'postgres', 'sequential-thinking']
        
        for row in configs:
            config_id = row['id']
            data = row['data']
            
            if not data or 'tool_server' not in data or 'connections' not in data['tool_server']:
                print(f"Record {config_id} does not contain tool_server connections. Skipping.")
                continue
                
            connections = data['tool_server']['connections']
            print(f"Record {config_id} original connections count: {len(connections)}")
            
            # Lọc connections
            new_connections = []
            removed_connections = []
            
            for conn_item in connections:
                url = conn_item.get('url', '')
                # Xác định server key từ URL (ví dụ: http://mcpo:8015/github -> github)
                server_name = url.split('/')[-1] if '/' in url else url
                
                if server_name in allowed_servers:
                    new_connections.append(conn_item)
                else:
                    removed_connections.append(server_name)
            
            print(f"Removed connections: {removed_connections}")
            print(f"Remaining connections ({len(new_connections)}): {[c.get('url').split('/')[-1] for c in new_connections]}")
            
            # Cập nhật lại data
            data['tool_server']['connections'] = new_connections
            
            # Cập nhật vào DB
            cursor.execute(
                "UPDATE config SET data = %s WHERE id = %s;",
                (json.dumps(data), config_id)
            )
            print(f"Successfully updated config record {config_id} in Database.")
            
        # Commit giao dịch
        conn.commit()
        print("Database transaction committed successfully.")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        if 'conn' in locals() and conn:
            conn.rollback()
            print("Database transaction rolled back.")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main()
