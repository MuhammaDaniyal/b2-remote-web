import socket
import json
import time

def mock_planter(host="127.0.0.1", port=5000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(1)
    print(f"Mock planter listening on {host}:{port}")

    while True:
        conn, addr = server.accept()
        print(f"Connected by {addr}")
        data = conn.recv(1024)
        if not data:
            continue

        try:
            msg = json.loads(data.decode("utf-8").strip())
            print(f"Received: {msg}")
            
            if msg.get("cmd") == "plant":
                print("Starting to plant...")
                time.sleep(3)
                print("Done planting.")
                response = json.dumps({"status": "done"}) + "\n"
                conn.sendall(response.encode("utf-8"))
        except Exception as e:
            print(f"Error: {e}")
        
        conn.close()

if __name__ == "__main__":
    mock_planter()
