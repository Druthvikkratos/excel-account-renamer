"""
desktop.py
Wraps your existing Gradio app (app.py) into a native desktop window.
Run locally with: python desktop.py
Package into an .exe with: pyinstaller --onefile --windowed --name AccountRenamer desktop.py
"""

import time
import socket
import webview

# Must match app.py's filename and the Gradio Blocks variable name
from app import demo


LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 7860


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def find_free_port(start_port: int = 7860, tries: int = 20) -> int:
    port = start_port
    for _ in range(tries):
        if port_is_free(LOCAL_HOST, port):
            return port
        port += 1
    raise RuntimeError("No free port found for the local Gradio server.")


def wait_for_server(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_is_free(host, port):
            return True
        time.sleep(0.2)
    return False


def main():
    port = find_free_port(LOCAL_PORT)

    # IMPORTANT: launch on the MAIN thread. prevent_thread_lock=True makes
    # this call return immediately instead of blocking, so no separate
    # thread is needed — and none should be used, since Gradio's internal
    # SIGINT handler registration only works on the main thread.
    demo.launch(
        server_name=LOCAL_HOST,
        server_port=port,
        prevent_thread_lock=True,
        inbrowser=False,
        show_error=True,
    )

    if not wait_for_server(LOCAL_HOST, port):
        raise RuntimeError("Gradio server did not start in time.")

    webview.create_window(
        title="Excel / CSV Account Renamer",
        url=f"http://{LOCAL_HOST}:{port}",
        width=1100,
        height=800,
        resizable=True,
    )
    webview.start()


if __name__ == "__main__":
    main()