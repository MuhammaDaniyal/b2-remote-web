# B2 Remote Web Controller

This project is a Flask-based web application for remotely controlling a Unitree B2 robot and an attached tree-planting device over a network. It provides a sleek UI to execute movement commands, run paths, and trigger tree planting operations via TCP.

## Prerequisites

Before running the application, make sure you have the following installed on your machine:
- **Python 3.8+**
- **Git** (optional, for cloning the repository)

## Installation & Virtual Environment Setup

It is highly recommended to run this application inside a Python Virtual Environment to keep dependencies isolated. 

### Linux / macOS
1. **Open a terminal** and navigate to this project folder.
2. **Create a virtual environment:**
   ```bash
   python3 -m venv .venv
   ```
3. **Activate the virtual environment:**
   ```bash
   source .venv/bin/activate
   ```
4. **Install the dependencies:**
   ```bash
   pip install Flask unitree_sdk2py
   ```

### Windows
1. **Open PowerShell or Command Prompt** and navigate to this project folder.
2. **Create a virtual environment:**
   ```cmd
   python -m venv .venv
   ```
3. **Activate the virtual environment:**
   ```cmd
   .venv\Scripts\activate
   ```
4. **Install the dependencies:**
   ```cmd
   pip install Flask unitree_sdk2py
   ```

## Running the Application

### Real Robot Mode
To connect to the physical Unitree B2 robot, you must specify the network interface that your computer uses to communicate with the robot (e.g., `eth0` for Ethernet, or `wlo1` / `wlan0` for Wi-Fi).

1. Ensure your virtual environment is activated.
2. Run the Flask server:
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
Once the server is running, open a web browser on any device connected to the same network and navigate to:
```
http://<YOUR_COMPUTER_IP>:8080
# Example: http://127.0.0.1:8080
```

## Testing the Tree Planter Integration

This app includes a feature to send TCP commands to a tree-planting device mounted on the robot. If you don't have the physical planter device available, you can simulate it using the provided mock script.

1. **Start the Mock Planter** 
   Open a *new* terminal window (leave the Flask server running in the first one) and run:
   ```bash
   python mock_planter.py
   ```
   *(This starts a local TCP server on port 5000 that listens for planting commands).*

2. **Test in the Web UI**
   - Open the Web UI (`http://127.0.0.1:8080`).
   - Scroll down to the **Tree Planter** section.
   - Enter `127.0.0.1` into the IP Address field and click **Set IP**.
   - Click the **Plant Tree** button.
   - The UI will say "Planting...", the mock script terminal will register the command, and 3 seconds later the UI will return to "Ready".

## Troubleshooting

- **`Address already in use` error when starting `app.py`:** 
  Port 8080 is already being used by another application (or an old instance of this app that didn't shut down properly). You can either kill the process using port 8080, or change the port by running `python app.py wlo1 --port 8081`.
- **`ModuleNotFoundError: No module named 'unitree_sdk2py'`:** 
  You forgot to activate your virtual environment before running the app. Run `source .venv/bin/activate` (Linux) or `.venv\Scripts\activate` (Windows) first.
