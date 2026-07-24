"use strict";

const statusElement = document.getElementById("status");
const commandButtons = [...document.querySelectorAll("[data-command]")];
const stopButton = document.getElementById("stop-button");

let locked = false;
let cooldownMs = 900;

function setLocked(value) {
    locked = value;
    commandButtons.forEach(button => {
        button.disabled = value;
    });
}

function setStatus(message, state = "") {
    statusElement.textContent = message;
    statusElement.dataset.state = state;
}

async function refreshStatus() {
    try {
        const response = await fetch("/api/status", { cache: "no-store" });
        const data = await response.json();

        cooldownMs = Math.max(data.cooldown_ms || 900, 900);

        if (!data.robot_ready) {
            setStatus("Robot not ready", "error");
            setLocked(true);
        } else if (data.busy) {
            setStatus(`Executing ${data.last_command || "command"}…`, "busy");
            setLocked(true);
        } else if (!locked) {
            setStatus("Ready", "ready");
        }
    } catch (error) {
        setStatus("Controller unreachable", "error");
        setLocked(true);
    }
}

async function sendCommand(command) {
    if (locked) {
        return;
    }

    setLocked(true);
    setStatus(`Sending ${command}…`, "busy");

    try {
        const response = await fetch("/api/command", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ command }),
        });

        const data = await response.json();

        if (!response.ok) {
            if (response.status === 429) {
                setStatus("Rate limited; pause briefly", "error");
            } else if (response.status === 409) {
                setStatus("Robot is still busy", "busy");
            } else {
                setStatus(data.error || "Command failed", "error");
            }
            return;
        }

        setStatus(`Accepted: ${command}`, "busy");
    } catch (error) {
        setStatus("Command request failed", "error");
    } finally {
        window.setTimeout(() => {
            locked = false;
            refreshStatus();
        }, cooldownMs);
    }
}

commandButtons.forEach(button => {
    button.addEventListener("click", () => {
        sendCommand(button.dataset.command);
    });
});

stopButton.addEventListener("click", async () => {
    setLocked(true);
    setStatus("Stopping…", "busy");

    try {
        await fetch("/api/stop", { method: "POST" });
        setStatus("Stop sent", "ready");
    } catch (error) {
        setStatus("Stop request failed", "error");
    } finally {
        window.setTimeout(() => {
            locked = false;
            refreshStatus();
        }, 500);
    }
});

window.setInterval(refreshStatus, 750);
refreshStatus();
