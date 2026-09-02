import socket
import json
import threading

class PlanterController:
    def __init__(self):
        self.ip = None
        self.port = 5000
        self.status = "disconnected"
        self._lock = threading.Lock()
        
    def set_device(self, ip, port=5000):
        with self._lock:
            self.ip = ip
            self.port = port
            self.status = "ready"
            
    def get_status(self):
        with self._lock:
            return self.status
            
    def plant(self):
        with self._lock:
            if not self.ip:
                return False, "No IP configured"
            if self.status == "planting":
                return False, "Already planting"
            self.status = "planting"
            
        thread = threading.Thread(target=self._plant_thread)
        thread.daemon = True
        thread.start()
        return True, "accepted"
        
    def _plant_thread(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0) # wait up to 10s for connect
            
            with self._lock:
                ip = self.ip
                port = self.port
                
            sock.connect((ip, port))
            sock.settimeout(None) # blocking for responses
            
            message = json.dumps({"cmd": "plant"}) + "\n"
            sock.sendall(message.encode("utf-8"))
            
            while True:
                data = sock.recv(4096)
                if not data:
                    with self._lock:
                        self.status = "disconnected"
                    break
                    
                messages = data.decode("utf-8").splitlines()
                for msg in messages:
                    try:
                        response = json.loads(msg)
                        if response.get("status") == "done":
                            with self._lock:
                                self.status = "ready"
                            return
                        if response.get("type") == "error":
                            with self._lock:
                                self.status = "error"
                            return
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            with self._lock:
                self.status = "error"
