# 测试用哑占位：绑住 18765 若干秒（模拟退出中的旧实例：占端口但不答 health）
import socket
import sys
import time

hold = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
s = socket.socket()
s.bind(("127.0.0.1", 18765))
s.listen(1)
print(f"holding 18765 for {hold}s", flush=True)
time.sleep(hold)
s.close()
print("released", flush=True)
