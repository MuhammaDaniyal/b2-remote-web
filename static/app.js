"use strict";

const statusElement = document.getElementById("status");
const commandButtons = [...document.querySelectorAll("[data-command], [data-sit], [data-stand]")];
const stopButton = document.getElementById("stop-button");
const sitButton = document.getElementById("sit-button");
const standButton = document.getElementById("stand-button");
const linearSpeedInput = document.getElementById("linear-speed");
const yawSpeedInput = document.getElementById("yaw-speed");
const durationInput = document.getElementById("duration");

let requestInFlight = false;
let localCooldownUntil = 0;

function setButtonsDisabled(disabled) {
    commandButtons.forEach(button => { button.disabled = disabled; });
    if (typeof runPathBtn !== 'undefined') runPathBtn.disabled = disabled;
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
    if (button.dataset.command) {
        button.addEventListener("click", () => sendCommand(button.dataset.command));
    }
});

async function sendPostureAction(action, label) {
    if (requestInFlight || Date.now() < localCooldownUntil) return;
    requestInFlight = true;
    setButtonsDisabled(true);
    setStatus(`Requesting ${label}…`, "busy");

    try {
        const response = await fetch(`/api/${action}`, { method: "POST" });
        const data = await response.json();
        if (!response.ok) {
            setStatus(data.error === "busy" ? "Robot is still busy" : (data.error || `${label} request failed`), "error");
            return;
        }

        localCooldownUntil = Date.now() + 350;
        setStatus(`${label} accepted`, "busy");
    } catch (_) {
        setStatus(`${label} request failed`, "error");
    } finally {
        requestInFlight = false;
        refreshStatus();
    }
}

sitButton.addEventListener("click", () => sendPostureAction("sit", "slow sit"));
standButton.addEventListener("click", () => sendPostureAction("stand", "stand up"));

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

// Path Planner Logic
const pathSelect = document.getElementById("path-command-select");
const addPathStepBtn = document.getElementById("add-path-step");
const pathListEl = document.getElementById("path-list");
const clearPathBtn = document.getElementById("clear-path");
const runPathBtn = document.getElementById("run-path");

let currentPath = [];

function renderPathList() {
    pathListEl.innerHTML = "";
    currentPath.forEach((step, index) => {
        const li = document.createElement("li");
        let text = step.command;
        if (step.command !== "sit" && step.command !== "stand") {
            text += ` (${step.speed} ${step.command.startsWith('yaw') ? 'rad/s' : 'm/s'}, ${step.duration_seconds}s)`;
        }
        li.textContent = text;
        
        const removeBtn = document.createElement("button");
        removeBtn.textContent = "Remove";
        removeBtn.className = "remove-step";
        removeBtn.onclick = () => {
            currentPath.splice(index, 1);
            renderPathList();
        };
        
        li.appendChild(removeBtn);
        pathListEl.appendChild(li);
    });
}

addPathStepBtn.addEventListener("click", () => {
    const cmd = pathSelect.value;
    const step = { command: cmd };
    
    if (cmd !== "sit" && cmd !== "stand") {
        const isYaw = cmd.startsWith("yaw_");
        const speedInput = isYaw ? yawSpeedInput : linearSpeedInput;
        step.speed = Number(speedInput.value);
        step.duration_seconds = Number(durationInput.value);
        
        if (!speedInput.checkValidity() || !durationInput.checkValidity()) {
            setStatus("Enter values within limits to add to path", "error");
            return;
        }
    }
    
    currentPath.push(step);
    renderPathList();
});

clearPathBtn.addEventListener("click", () => {
    currentPath = [];
    renderPathList();
});

runPathBtn.addEventListener("click", async () => {
    if (currentPath.length === 0) {
        setStatus("Path is empty", "error");
        return;
    }
    
    if (requestInFlight || Date.now() < localCooldownUntil) return;
    requestInFlight = true;
    setButtonsDisabled(true);
    setStatus(`Executing path (${currentPath.length} steps)…`, "busy");

    try {
        const response = await fetch("/api/path", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(currentPath),
        });
        const data = await response.json();

        if (!response.ok) {
            setStatus(data.error === "busy" ? "Robot is still busy" : (data.error || "Path request failed"), "error");
            return;
        }

        localCooldownUntil = Date.now() + 350;
        setStatus(`Path accepted`, "busy");
    } catch (_) {
        setStatus("Path request failed", "error");
    } finally {
        requestInFlight = false;
        refreshStatus();
    }
});
