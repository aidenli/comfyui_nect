# 启动nodejs服务
import subprocess
import os
import time
import atexit
import requests
import threading
from dotenv import load_dotenv
load_dotenv()

# 服务端口，默认 3000（与 main.js 保持一致）
PORT = os.getenv("PORT", "11880")
BASE_URL = f"http://localhost:{PORT}"

node_process = None

def start_node_server():
    global node_process

    # 如果已有服务在运行，直接跳过启动（在线程中执行，避免阻塞）
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=1)
        if r.ok:
            return
    except Exception:
        pass

    # 构建启动命令
    main_js_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.js')
    cmd = ['node', main_js_path, '--serve']

    # 启动子进程（继承环境并显式设定 PORT）
    env = os.environ.copy()
    env["PORT"] = str(PORT)
    node_process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=0,  # 保持简单；如果需要隐藏窗口可调整
    )
    print(f"Nect server started on port {PORT}")
    
    # 退出时清理子进程
    def _cleanup():
        try:
            if node_process and node_process.poll() is None:
                print("Terminating Nect server process")
                node_process.terminate()
        except Exception:
            print("Error terminating Nect server process")
            pass

    atexit.register(_cleanup)