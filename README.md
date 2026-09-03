# B2 Remote Web Controller

This project is a Flask-based web application for remotely controlling a Unitree B2 robot and an attached tree-planting device over a network. It provides a sleek UI to execute movement commands, run paths, and trigger tree planting operations via TCP.

This document serves as an end-to-end handoff guide to get the project running from scratch on a new machine.

---

## 1. System Architecture

- **Backend:** Python Flask server (`app.py`) that handles HTTP REST requests from the UI.
- **Robot Control:** Uses `unitree_sdk2py` to send movement and posture commands to the B2 via DDS auto-discovery.
- **Tree Planter:** Communicates asynchronously over a raw TCP socket connection on port 5000 (`planter_controller.py`).
- **Frontend:** Vanilla HTML/CSS/JS with asynchronous polling for robot state.

## 2. Remote Access (Tailscale Setup)

Because the robot operates in the field (or on an isolated network), we use **Tailscale** to securely SSH into the robot's onboard PC and access the web dashboard remotely from anywhere.

1. Install Tailscale on the robot's PC and your client machine:
   - Linux: `curl -fsSL https://tailscale.com/install.sh | sh`
   - Windows/macOS: Download from [tailscale.com](https://tailscale.com)
2. Authenticate both devices to the same Tailscale network:
   ```bash
   sudo tailscale up
   ```
3. You can now SSH into the robot using its Tailscale IP address (e.g., `100.x.y.z`), and access the web UI via `http://<TAILSCALE_IP>:8080`.

## 3. Cloning & Setup

Before running the application, make sure you have **Python 3.8+** installed.

### Step 3.1: Clone the Repository
```bash
git clone https://github.com/trovadoreu-arch/b2-remote-web
cd b2-remote-web
```

### Step 3.2: Virtual Environment & Dependencies
It is highly recommended to run this application inside a Python Virtual Environment to keep dependencies isolated.

The provided `requirements.txt` file handles installing all necessary packages (such as `Flask` for the web server and `unitree_sdk2py` for robot communication).

**On Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**On Windows:**
```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Environment Variables

If you do not want to pass the network interface as a command-line argument every time, you can set it as an environment variable. 

Create a `.env` file or export this variable in your system:
- `B2_IFACE`: The network interface connected to the robot (e.g., `wlo1`, `eth0`). If not provided in the environment, it must be passed via the command line.

*(Note: Do not commit `.env` files containing private IPs or tokens. Add `.env` to `.gitignore`)*

## 5. Running the Application

### Real Robot Mode
To connect to the physical Unitree B2 robot, you must specify the network interface that your computer uses to communicate with the robot.

Ensure your virtual environment is activated, then start the server:

```bash
# On Linux (replace wlo1 with your actual network interface)
python app.py wlo1

# Or using the provided bash script (Linux/macOS only)
./run.sh
```

### Mock Mode (Testing without the Robot)
If you run the application on a network interface that the robot is not connected to (or if you are just testing the UI on your laptop), the app will automatically gracefully fall back to **Mock Mode**. 
- In Mock Mode, the UI will be fully functional and will accept commands, but no physical movements will occur.

### Accessing the Web UI
Once the server is running, open a web browser and navigate to:
```
http://<SERVER_IP>:8080
# Example: http://127.0.0.1:8080 (if running locally)
# Example: http://100.x.y.z:8080 (if accessing via Tailscale)
```

## 6. Testing the Tree Planter Integration

This app includes a feature to send TCP commands to a tree-planting device mounted on the robot. If you don't have the physical planter device available for testing, you can simulate it using the provided mock script.

1. **Start the Mock Planter** 
   Open a *new* terminal window (leave the Flask server running in the first one) and run:
   ```bash
   python mock_planter.py
   ```
   *(This starts a local TCP server on port 5000 that mimics the hardware responses).*

2. **Test in the Web UI**
   - Open the Web UI (`http://127.0.0.1:8080`).
   - Scroll down to the **Tree Planter** section.
   - Enter `127.0.0.1` into the IP Address field and click **Set IP**.
   - Click the **Plant Tree** button.
   - The UI will say "Planting...", the mock script terminal will register the command, and 3 seconds later the UI will return to "Ready".

## 7. Troubleshooting

- **`Address already in use` error when starting `app.py`:** 
  Port 8080 is already being used by another application. Kill the existing process, or start the server on a different port using `python app.py wlo1 --port 8081`.
- **`ModuleNotFoundError: No module named 'unitree_sdk2py'`:** 
  You forgot to activate your virtual environment before running the app. Run `source .venv/bin/activate` first.
- **Robot not moving (Error 3104):**
  This usually means the robot's built-in autonomous services are fighting for control. You may need to stop the conflicting service via the robot's SSH interface before sending remote commands.
