"use strict";

const statusElement = document.getElementById("status");
const commandButtons = [...document.querySelectorAll("[data-command]")];
const stopButton = document.getElementById("stop-button");
const linearSpeedInput = document.getElementById("linear-speed");
const yawSpeedInput = document.getElementById("yaw-speed");
const durationInput = document.getElementById("duration");

let requestInFlight = false;
let localCooldownUntil = 0;

function setButtonsDisabled(disabled) {
    commandButtons.forEach(button => { button.disabled = disabled; });
}

function setStatus(message, state = "") {
    statusElement.textContent = message;
    statusElement.dataset.state = state;
}

function applyStatus(data) {
    const coolingDown = Date.now() < localCooldownUntil;
    const disabled = requestInFlight || coolingDown || !data.robot_ready || data.busy;
    setButtonsDisabled(disabled);

    if (!data.robot_ready) setStatus("Robot not ready", "error");
    else if (data.busy) setStatus(`Executing ${data.last_command || "command"}…`, "busy");
    else if (coolingDown) setStatus("Ready shortly…", "busy");
    else setStatus("Ready", "ready");
}

async function refreshStatus() {
    try {
        const response = await fetch("/api/status", { cache: "no-store" });
        const data = await response.json();
        applyStatus(data);
    } catch (_) {
        setStatus("Controller unreachable", "error");
        setButtonsDisabled(true);
    }
}

async function sendCommand(command) {
    if (requestInFlight || Date.now() < localCooldownUntil) return;
    requestInFlight = true;
    setButtonsDisabled(true);

    const isYawCommand = command.startsWith("yaw_");
    const speedInput = isYawCommand ? yawSpeedInput : linearSpeedInput;
    const speed = Number(speedInput.value);
    const duration_seconds = Number(durationInput.value);

    if (!speedInput.checkValidity() || !durationInput.checkValidity()) {
        setStatus("Enter values within the shown limits", "error");
        requestInFlight = false;
        refreshStatus();
        return;
    }

    setStatus(`Sending ${command}…`, "busy");

    try {
        const response = await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command, speed, duration_seconds }),
        });
        const data = await response.json();

        if (!response.ok) {
            if (response.status === 429) {
                localCooldownUntil = Date.now() + Math.max(data.retry_after_ms || 350, 350);
                setStatus("Rate limited; pause briefly", "error");
            } else if (response.status === 409) {
                setStatus("Robot is still busy", "busy");
            } else {
                setStatus(data.error || "Command failed", "error");
            }
            return;
        }

        localCooldownUntil = Date.now() + 350;
        setStatus(`Accepted: ${command} for ${duration_seconds}s`, "busy");
    } catch (_) {
        setStatus("Command request failed", "error");
    } finally {
        requestInFlight = false;
        refreshStatus();
    }
}

commandButtons.forEach(button => {
    button.addEventListener("click", () => sendCommand(button.dataset.command));
});

stopButton.addEventListener("click", async () => {
    requestInFlight = true;
    setButtonsDisabled(true);
    setStatus("Stopping…", "busy");
    try {
        await fetch("/api/stop", { method: "POST" });
        localCooldownUntil = Date.now() + 250;
        setStatus("Stop sent", "ready");
    } catch (_) {
        setStatus("Stop request failed", "error");
    } finally {
        requestInFlight = false;
        refreshStatus();
    }
});

window.setInterval(refreshStatus, 250);
refreshStatus();
