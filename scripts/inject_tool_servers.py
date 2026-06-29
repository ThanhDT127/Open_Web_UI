#!/usr/bin/env python3
# ==============================================================================
# Script: inject_tool_servers.py
# Description: Inject 12 MCP Tool Server connections directly into PostgreSQL
# ==============================================================================

import os
import json
import psycopg2

def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable not found!")
        return

    print("Connecting to database...")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # Get current config
    cur.execute("SELECT id, data FROM config LIMIT 1;")
    row = cur.fetchone()
    if not row:
        print("No config row found in database!")
        cur.close()
        conn.close()
        return

    config_id, data = row
    
    # Parse existing JSON data
    if isinstance(data, str):
        data_json = json.loads(data)
    else:
        data_json = data

    # Define the 12 MCP servers
    servers = [
        ("figma", "Figma"),
        ("gmail", "Gmail"),
        ("office365", "Office 365"),
        ("google-calendar", "Google Calendar"),
        ("google-drive", "Google Drive"),
        ("github", "GitHub"),
        ("playwright", "Playwright"),
        ("gitlab", "GitLab"),
        ("notion", "Notion"),
        ("fetch", "Fetch"),
        ("postgres", "Postgres"),
        ("sequential-thinking", "Sequential Thinking")
    ]

    connections = []
    for s_id, s_name in servers:
        conn_obj = {
            "url": f"http://mcpo:8015/{s_id}",
            "path": "openapi.json",
            "type": "openapi",
            "auth_type": "bearer",
            "headers": None,
            "key": "",
            "config": {
                "enable": True,
                "function_name_filter_list": "",  # Empty to import all!
                "access_grants": [
                    {
                        "principal_type": "user",
                        "principal_id": "*",
                        "permission": "read"
                    }
                ]
            },
            "info": {
                "id": "",
                "name": s_name,
                "description": s_name
            },
            "spec_type": "url",
            "spec": ""
        }
        connections.append(conn_obj)

    # Update tool_server config key
    data_json["tool_server"] = {
        "connections": connections
    }

    # Save back to database
    cur.execute(
        "UPDATE config SET data = %s WHERE id = %s;",
        (json.dumps(data_json), config_id)
    )
    conn.commit()
    print(f"Successfully injected {len(connections)} MCP connections into the database!")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
