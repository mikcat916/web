from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PYDEPS_DIR = ROOT_DIR / ".pydeps"
if PYDEPS_DIR.exists():
    sys.path.insert(0, str(PYDEPS_DIR))

import paramiko


REMOTE_DIR = "/home/pi/project4-iot"
SERVICE_NAME = "project4-iot.service"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy iot_client.py to a Raspberry Pi and register a systemd service.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="pi")
    parser.add_argument("--password", required=True)
    parser.add_argument("--server", required=True, help="Backend base URL, e.g. http://192.168.31.46:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--point-id", type=int, default=0)
    parser.add_argument("--route-id", type=int, default=0)
    parser.add_argument("--gps-timeout", type=int, default=5)
    parser.add_argument("--gps-serial-device", default="")
    parser.add_argument("--gps-serial-baud", type=int, default=9600)
    parser.add_argument("--gps-log-every", type=int, default=10)
    parser.add_argument("--network-locate-enabled", action="store_true")
    parser.add_argument("--network-provider", default="google")
    parser.add_argument("--network-api-key", default="")
    parser.add_argument("--network-api-url", default="https://www.googleapis.com/geolocation/v1/geolocate")
    parser.add_argument("--network-timeout", type=int, default=10)
    parser.add_argument("--network-interface", default="wlan0")
    parser.add_argument("--network-consider-ip", type=int, default=1)
    return parser.parse_args()


def sftp_write_text(sftp: paramiko.SFTPClient, remote_path: str, content: str) -> None:
    with sftp.file(remote_path, "w") as remote_file:
        remote_file.write(content)


def main() -> int:
    args = parse_args()
    local_client = ROOT_DIR / "scripts" / "iot_client.py"
    if not local_client.exists():
        print(f"Missing file: {local_client}", file=sys.stderr)
        return 1

    config_text = "\n".join(
        [
            "[client]",
            f"server = {args.server}",
            f"token = {args.token}",
            f"interval = {args.interval}",
            f"point_id = {args.point_id}",
            f"route_id = {args.route_id}",
            f"gps_timeout = {args.gps_timeout}",
            f"gps_serial_device = {args.gps_serial_device}",
            f"gps_serial_baud = {args.gps_serial_baud}",
            f"gps_log_every = {args.gps_log_every}",
            f"network_locate_enabled = {1 if args.network_locate_enabled else 0}",
            f"network_provider = {args.network_provider}",
            f"network_api_key = {args.network_api_key}",
            f"network_api_url = {args.network_api_url}",
            f"network_timeout = {args.network_timeout}",
            f"network_interface = {args.network_interface}",
            f"network_consider_ip = {args.network_consider_ip}",
            "",
        ]
    )
    service_text = "\n".join(
        [
            "[Unit]",
            "Description=Project4 IoT Client",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={REMOTE_DIR}",
            f"ExecStart=/usr/bin/python3 {REMOTE_DIR}/iot_client.py --config {REMOTE_DIR}/iot_client.conf",
            "Restart=always",
            "RestartSec=5",
            f"User={args.user}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=args.host, username=args.user, password=args.password, timeout=10, banner_timeout=10, auth_timeout=10)
    try:
        sftp = client.open_sftp()
        try:
            client.exec_command(f"mkdir -p {REMOTE_DIR}")
            sftp.put(str(local_client), f"{REMOTE_DIR}/iot_client.py")
            sftp_write_text(sftp, f"{REMOTE_DIR}/iot_client.conf", config_text)
        finally:
            sftp.close()

        commands = [
            f"chmod +x {REMOTE_DIR}/iot_client.py",
            f"printf '%s\\n' \"{args.password}\" | sudo -S apt-get update -y",
            f"printf '%s\\n' \"{args.password}\" | sudo -S apt-get install -y python3",
            f"cat > /tmp/{SERVICE_NAME} <<'EOF'\n{service_text}EOF",
            f"printf '%s\\n' \"{args.password}\" | sudo -S mv /tmp/{SERVICE_NAME} /etc/systemd/system/{SERVICE_NAME}",
            f"printf '%s\\n' \"{args.password}\" | sudo -S systemctl daemon-reload",
            f"printf '%s\\n' \"{args.password}\" | sudo -S systemctl enable {SERVICE_NAME}",
            f"printf '%s\\n' \"{args.password}\" | sudo -S systemctl restart {SERVICE_NAME}",
            f"printf '%s\\n' \"{args.password}\" | sudo -S systemctl status {SERVICE_NAME} --no-pager",
        ]
        for command in commands:
            stdin, stdout, stderr = client.exec_command(command, get_pty=True)
            output = stdout.read().decode("utf-8", "replace")
            error = stderr.read().decode("utf-8", "replace")
            if output:
                print(output)
            if error:
                print(error, file=sys.stderr)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
