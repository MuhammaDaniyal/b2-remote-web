#!/usr/bin/env python3

import argparse
import atexit
import os
from flask import Flask, jsonify, render_template, request

from robot_controller import B2Controller
from rate_limiter import CommandRateLimiter


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
        })

    @app.post("/api/command")
    def command():
        payload = request.get_json(silent=True) or {}
        command_name = payload.get("command")

        if command_name not in controller.allowed_commands:
            return jsonify({
                "ok": False,
                "error": "invalid_command",
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

        accepted, reason = controller.enqueue(command_name)
        if not accepted:
            status_code = 409 if reason == "busy" else 503
            return jsonify({
                "ok": False,
                "error": reason,
            }), status_code

        return jsonify({
            "ok": True,
            "accepted": command_name,
        }), 202

    @app.post("/api/stop")
    def stop():
        controller.emergency_stop()
        return jsonify({"ok": True})

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
