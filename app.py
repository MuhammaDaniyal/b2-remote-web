#!/usr/bin/env python3

import argparse
import atexit
import math
import os
from flask import Flask, jsonify, render_template, request

from robot_controller import B2Controller
from rate_limiter import CommandRateLimiter


MAX_DURATION_SECONDS = 30.0
MAX_LINEAR_SPEED_MPS = 5.0
MAX_YAW_SPEED_RADPS = 1.0
MIN_SPEED = 0.01
MIN_DURATION_SECONDS = 0.01


def valid_number(value, minimum: float, maximum: float) -> bool:
    """Accept JSON numbers only when they are finite and within the given range."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and minimum <= value <= maximum
    )


def create_app(interface: str) -> Flask:
    app = Flask(__name__)

    controller = B2Controller(interface=interface)
    limiter = CommandRateLimiter(
        min_interval_seconds=0.5,
        max_commands_per_window=10,
        window_seconds=10.0,
    )

    controller.start()
    app.extensions["b2_controller"] = controller
    atexit.register(controller.shutdown)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify({
            "ok": True,
            "robot_ready": controller.ready,
            "busy": controller.busy,
            "queue_depth": controller.queue_depth,
            "last_command": controller.last_command,
            "allowed_commands": sorted(controller.allowed_commands),
            "cooldown_ms": int(limiter.min_interval_seconds * 1000),
            "motion_limits": {
                "duration_seconds": {"min": MIN_DURATION_SECONDS, "max": MAX_DURATION_SECONDS},
                "linear_speed_mps": {"min": MIN_SPEED, "max": MAX_LINEAR_SPEED_MPS},
                "yaw_speed_radps": {"min": MIN_SPEED, "max": MAX_YAW_SPEED_RADPS},
            },
        })

    @app.post("/api/command")
    def command():
        payload = request.get_json(silent=True) or {}
        command_name = payload.get("command")
        speed = payload.get("speed")
        duration_seconds = payload.get("duration_seconds")

        if command_name not in controller.allowed_commands:
            return jsonify({
                "ok": False,
                "error": "invalid_command",
            }), 400

        max_speed = MAX_YAW_SPEED_RADPS if command_name.startswith("yaw_") else MAX_LINEAR_SPEED_MPS
        if not valid_number(speed, MIN_SPEED, max_speed):
            return jsonify({
                "ok": False,
                "error": "invalid_speed",
                "message": f"speed must be between {MIN_SPEED} and {max_speed}",
            }), 400
        if not valid_number(duration_seconds, MIN_DURATION_SECONDS, MAX_DURATION_SECONDS):
            return jsonify({
                "ok": False,
                "error": "invalid_duration",
                "message": f"duration_seconds must be between {MIN_DURATION_SECONDS} and {MAX_DURATION_SECONDS}",
            }), 400

        allowed, retry_after = limiter.allow(request.remote_addr or "unknown")
        if not allowed:
            response = jsonify({
                "ok": False,
                "error": "rate_limited",
                "retry_after_ms": int(retry_after * 1000),
            })
            response.status_code = 429
            response.headers["Retry-After"] = f"{retry_after:.2f}"
            return response

        accepted, reason = controller.enqueue(command_name, float(speed), float(duration_seconds))
        if not accepted:
            status_code = 409 if reason == "busy" else 503
            return jsonify({
                "ok": False,
                "error": reason,
            }), status_code

        return jsonify({
            "ok": True,
            "accepted": command_name,
            "speed": speed,
            "duration_seconds": duration_seconds,
        }), 202

    @app.post("/api/stop")
    def stop():
        controller.emergency_stop()
        return jsonify({"ok": True})

    @app.post("/api/path")
    def path():
        sequence = request.get_json(silent=True)
        if not isinstance(sequence, list):
            return jsonify({"ok": False, "error": "invalid_payload", "message": "Expected a JSON array"}), 400

        valid_commands = controller.allowed_commands.union({"sit", "stand"})
        
        for step in sequence:
            if not isinstance(step, dict):
                return jsonify({"ok": False, "error": "invalid_step", "message": "Each step must be an object"}), 400
                
            command_name = step.get("command")
            if command_name not in valid_commands:
                return jsonify({"ok": False, "error": "invalid_command", "message": f"Unknown command: {command_name}"}), 400
                
            if command_name not in {"sit", "stand"}:
                speed = step.get("speed", 0.15)
                duration = step.get("duration_seconds", 1.0)
                
                max_speed = MAX_YAW_SPEED_RADPS if command_name.startswith("yaw_") else MAX_LINEAR_SPEED_MPS
                if not valid_number(speed, MIN_SPEED, max_speed):
                    return jsonify({"ok": False, "error": "invalid_speed"}), 400
                if not valid_number(duration, MIN_DURATION_SECONDS, MAX_DURATION_SECONDS):
                    return jsonify({"ok": False, "error": "invalid_duration"}), 400

        allowed, retry_after = limiter.allow(request.remote_addr or "unknown")
        if not allowed:
            response = jsonify({
                "ok": False,
                "error": "rate_limited",
                "retry_after_ms": int(retry_after * 1000),
            })
            response.status_code = 429
            response.headers["Retry-After"] = f"{retry_after:.2f}"
            return response

        accepted, reason = controller.enqueue_path(sequence)
        if not accepted:
            status_code = 409 if reason == "busy" else 503
            return jsonify({"ok": False, "error": reason}), status_code

        return jsonify({"ok": True, "accepted": "path", "steps": len(sequence)}), 202

    @app.post("/api/sit")
    def sit():
        return enqueue_action("sit", controller.enqueue_sit)

    @app.post("/api/stand")
    def stand():
        return enqueue_action("stand", controller.enqueue_stand)

    def enqueue_action(action_name, enqueue):
        allowed, retry_after = limiter.allow(request.remote_addr or "unknown")
        if not allowed:
            response = jsonify({
                "ok": False,
                "error": "rate_limited",
                "retry_after_ms": int(retry_after * 1000),
            })
            response.status_code = 429
            response.headers["Retry-After"] = f"{retry_after:.2f}"
            return response

        accepted, reason = enqueue()
        if not accepted:
            status_code = 409 if reason == "busy" else 503
            return jsonify({"ok": False, "error": reason}), status_code

        return jsonify({"ok": True, "accepted": action_name}), 202

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="B2 six-command web remote")
    parser.add_argument(
        "interface",
        nargs="?",
        default=os.environ.get("B2_IFACE"),
        help="B2-facing network interface, e.g. eth0",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if not args.interface:
        parser.error("Provide the interface or set B2_IFACE.")

    app = create_app(args.interface)
    controller = app.extensions["b2_controller"]

    try:
        app.run(
            host=args.host,
            port=args.port,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        print("\nCtrl+C received; stopping robot and shutting down.")
    finally:
        controller.shutdown()
        print("B2 web remote stopped.")


if __name__ == "__main__":
    main()
