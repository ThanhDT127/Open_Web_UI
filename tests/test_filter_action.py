"""
Integration tests for Action and Filter approval custom functions.
Runs inside the openwebui-app container.
"""

import os
import sys
import asyncio
import json
import requests

# Add /tmp to python path so it can import the tools copied there
sys.path.insert(0, "/tmp")

from filter_approval_handler import Filter
from action_approval_ui import Action


async def run_tests():
    print("Running Filter and Action integration tests...")
    
    # 1. Instantiate Filter and Action
    f = Filter()
    a = Action()
    
    # Override valves for internal docker testing
    f.valves.middleware_url = "http://middleware:5000/v1"
    f.valves.admin_token = "YOUR_SUBKEY_ADMIN"
    
    a.valves.MW_BASE_URL = "http://middleware:5000/v1"
    a.valves.SUBKEY_ADMIN = "YOUR_SUBKEY_ADMIN"
    
    # 2. Query reconciliation to find a valid matched user
    recon = requests.get(
        "http://middleware:5000/v1/_mw/admin/users/reconciliation",
        headers={"X-Admin-Key": "YOUR_ADMIN_KEY"}
    ).json()
    
    mw_user_id = None
    openwebui_user_id = None
    for item in recon.get("matched", []):
        if item.get("openwebui") and item.get("openwebui").get("email") == "admin@example.com":
            mw_user_id = item.get("middleware", {}).get("user_id")
            openwebui_user_id = item.get("openwebui", {}).get("id")
            break
            
    if not mw_user_id or not openwebui_user_id:
        for item in recon.get("matched", []):
            mw_user_id = item.get("middleware", {}).get("user_id")
            openwebui_user_id = item.get("openwebui", {}).get("id")
            break
            
    if not openwebui_user_id:
        raise Exception("No matched OpenWebUI user found in reconciliation report")
        
    print(f"Using matched test user: mw_user_id={mw_user_id}, openwebui_user_id={openwebui_user_id}")
    
    approval_id = "test_filter_action_001"
    user_id = openwebui_user_id  # openwebui_user_id is the user_id inside OpenWebUI filters
    tool_name = "google_gmail_tool"
    payload = {
        "recipient": "test_recv@example.com",
        "subject": "Test Subject",
        "body": "Test Body content..."
    }
    
    headers = {"Authorization": "Bearer YOUR_SUBKEY_ADMIN"}
    
    print("Creating pending approval request...")
    res = requests.post(
        "http://middleware:5000/v1/_mw/approvals",
        headers=headers,
        json={
            "id": approval_id,
            "tool_name": tool_name,
            "user_id": user_id,
            "payload": payload
        },
        timeout=5
    )
    if res.status_code != 200:
        raise Exception(f"Failed to create pending approval: {res.text}")
        
    print("Pending approval created. Testing Action UI scanning...")
    
    # Test Action
    body_action = {
        "messages": [
            {"role": "user", "content": "Send email"},
            {"role": "assistant", "content": f"Here is the request: [PENDING_APPROVAL:{approval_id}]"}
        ]
    }
    
    # Mock events
    events_called = []
    async def mock_event_call(event):
        events_called.append(event)
        return {"status": "ok"}
        
    async def mock_event_emitter(event):
        pass
        
    await a.action(
        body=body_action,
        __event_call__=mock_event_call,
        __event_emitter__=mock_event_emitter
    )
    
    if not events_called or events_called[0].get("type") != "execute":
        raise Exception("Action failed to trigger JS execution event")
        
    print("Action UI test: PASSED")
    
    # Test Filter - Reject
    print("Testing Filter reject command...")
    body_filter_reject = {
        "messages": [
            {"role": "user", "content": f"/reject {approval_id}"}
        ]
    }
    
    user_info = {"id": user_id}
    
    res_body = await f.inlet(body_filter_reject, __user__=user_info)
    last_msg_content = res_body["messages"][-1]["content"]
    
    if "Người dùng từ chối" not in last_msg_content:
        raise Exception(f"Filter reject failed. Output: {last_msg_content}")
        
    # Check status in db
    res_status = requests.get(f"http://middleware:5000/v1/_mw/approvals/{approval_id}", headers=headers)
    if res_status.json().get("status") != "rejected":
        raise Exception("Status not updated to rejected in database")
        
    print("Filter Reject test: PASSED")
    
    # Test Filter - Approve
    print("Setting up mock Google Gmail connection for test user...")
    # Callback to connect
    res_cb = requests.get(
        f"http://middleware:5000/v1/_mw/oauth/callback?code=mock-code&state=google_gmail:ow_user_id:{user_id}"
    )
    print(f"Callback response: {res_cb.status_code}")
    
    # Create another approval request
    approval_id_2 = "test_filter_action_002"
    requests.post(
        "http://middleware:5000/v1/_mw/approvals",
        headers=headers,
        json={
            "id": approval_id_2,
            "tool_name": tool_name,
            "user_id": user_id,
            "payload": payload
        }
    )
    
    print("Testing Filter approve command...")
    body_filter_approve = {
        "messages": [
            {"role": "user", "content": f"/approve {approval_id_2}"}
        ]
    }
    
    res_body_app = await f.inlet(body_filter_approve, __user__=user_info)
    last_msg_content_app = res_body_app["messages"][-1]["content"]
    
    print(f"Filter approve output content: {last_msg_content_app}")
    if "Hành động đã được phê duyệt" not in last_msg_content_app:
        raise Exception(f"Filter approve failed to execute. Output: {last_msg_content_app}")
        
    print("Filter Approve test: PASSED")
    print("All integration checks completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
