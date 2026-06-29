import os
import sys
import json
import uuid
import time
import urllib.request

SANDBOX_URL = "http://code-sandbox:8888"

def test_sandbox_connection():
    print("Testing connection to Jupyter Kernel Gateway...")
    try:
        req = urllib.request.Request(f"{SANDBOX_URL}/api/kernels", method="GET")
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode())
            print(f"Connection OK. Active kernels: {len(data)}")
            return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

def test_code_execution():
    print("\nTesting code execution inside sandbox...")
    try:
        import websocket
    except ImportError:
        print("Installing websocket-client inside container first...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
        import websocket

    # 1. Create kernel
    req = urllib.request.Request(f"{SANDBOX_URL}/api/kernels", data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as res:
        kernel_data = json.loads(res.read().decode())
        kernel_id = kernel_data["id"]
        print(f"Created kernel: {kernel_id}")

    # 2. Connect websocket
    ws_url = f"ws://code-sandbox:8888/api/kernels/{kernel_id}/channels"
    ws = websocket.create_connection(ws_url, timeout=10)
    
    session_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())
    
    # Simple code with output and math
    code = "print(10 + 20)"
    
    execute_msg = {
        "header": {
            "msg_id": msg_id,
            "username": "openwebui",
            "session": session_id,
            "msg_type": "execute_request",
            "version": "5.0"
        },
        "metadata": {},
        "content": {
            "code": code,
            "silent": False,
            "store_history": True,
            "user_expressions": {},
            "allow_stdin": False
        },
        "parent_header": {}
    }
    
    ws.send(json.dumps(execute_msg))
    
    stdout_output = ""
    while True:
        msg = json.loads(ws.recv())
        msg_type = msg.get("header", {}).get("msg_type")
        content = msg.get("content", {})
        parent_msg_id = msg.get("parent_header", {}).get("msg_id")
        
        if parent_msg_id != msg_id:
            continue
            
        if msg_type == "stream" and content.get("name") == "stdout":
            stdout_output += content.get("text", "")
        elif msg_type == "status" and content.get("execution_state") == "idle":
            break
            
    ws.close()
    
    # 3. Clean up kernel
    req_delete = urllib.request.Request(f"{SANDBOX_URL}/api/kernels/{kernel_id}", method="DELETE")
    with urllib.request.urlopen(req_delete) as res:
        print(f"Deleted kernel: {kernel_id}")
        
    print(f"Execution output: {stdout_output.strip()}")
    if stdout_output.strip() == "30":
        print("Code execution test: PASSED")
        return True
    else:
        print("Code execution test: FAILED")
        return False

def test_shared_volume_and_plots():
    print("\nTesting plotting and shared volume output...")
    # Inject matplotlib plot code
    try:
        import websocket
    except ImportError:
        import websocket
        
    req = urllib.request.Request(f"{SANDBOX_URL}/api/kernels", data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as res:
        kernel_data = json.loads(res.read().decode())
        kernel_id = kernel_data["id"]
        
    ws_url = f"ws://code-sandbox:8888/api/kernels/{kernel_id}/channels"
    ws = websocket.create_connection(ws_url, timeout=15)
    
    session_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())
    
    # matplotlib drawing code that saves image to /tmp/outputs
    code = """import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Draw simple line plot
x = np.linspace(0, 10, 100)
y = np.sin(x)
plt.plot(x, y)
plt.title('Test Sin Wave')

# Save to shared directory
os.makedirs('/tmp/outputs', exist_ok=True)
plt.savefig('/tmp/outputs/sin_wave_test.png')
plt.close()
print("Saved chart successfully")
"""
    
    execute_msg = {
        "header": {
            "msg_id": msg_id,
            "username": "openwebui",
            "session": session_id,
            "msg_type": "execute_request",
            "version": "5.0"
        },
        "metadata": {},
        "content": {
            "code": code,
            "silent": False,
            "store_history": True,
            "user_expressions": {},
            "allow_stdin": False
        },
        "parent_header": {}
    }
    
    ws.send(json.dumps(execute_msg))
    
    stdout_output = ""
    while True:
        msg = json.loads(ws.recv())
        msg_type = msg.get("header", {}).get("msg_type")
        content = msg.get("content", {})
        parent_msg_id = msg.get("parent_header", {}).get("msg_id")
        
        if parent_msg_id != msg_id:
            continue
            
        if msg_type == "stream" and content.get("name") == "stdout":
            stdout_output += content.get("text", "")
        elif msg_type == "status" and content.get("execution_state") == "idle":
            break
            
    ws.close()
    
    req_delete = urllib.request.Request(f"{SANDBOX_URL}/api/kernels/{kernel_id}", method="DELETE")
    with urllib.request.urlopen(req_delete) as res:
        pass

    # Verify if file was written to the shared volume path inside openwebui-app
    openwebui_path = "/app/backend/data/static/outputs/sin_wave_test.png"
    print(f"Checking for output file at: {openwebui_path}")
    if os.path.exists(openwebui_path):
        print(f"File exists. Size: {os.path.getsize(openwebui_path)} bytes")
        print("Shared volume test: PASSED")
        return True
    else:
        print("Shared volume test: FAILED (file not found)")
        return False

if __name__ == "__main__":
    c = test_sandbox_connection()
    if not c:
        sys.exit(1)
    e = test_code_execution()
    if not e:
        sys.exit(1)
    v = test_shared_volume_and_plots()
    if not v:
        sys.exit(1)
    print("\nAll integration checks completed successfully!")
    sys.exit(0)
