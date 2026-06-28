#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
ENV_FILE = BASE / ".env.ibkr_paper.local"
RUNTIME_DIR = BASE / "ibkr_runtime"
PRIVATE_DIR = RUNTIME_DIR / "private"
SETTINGS_DIR = RUNTIME_DIR / "ib_settings" / "paper"
LOG_DIR = RUNTIME_DIR / "logs"
STATE_FILE = RUNTIME_DIR / "runtime_state.json"
CONFIG_FILE = PRIVATE_DIR / "config.paper.ini"


@dataclass
class RuntimeState:
    generated_at: str
    config_file: str
    settings_dir: str
    log_dir: str
    trading_mode: str
    read_only_api: str
    api_port: str
    command_server_port: str


def load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"missing env file: {path}")
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        data[key.strip()] = value
    return data


def get_value(env: dict[str, str], key: str, default: str = "") -> str:
    return os.getenv(key, env.get(key, default)).strip()


def ensure_dirs() -> None:
    for path in (PRIVATE_DIR, SETTINGS_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def render_config(env: dict[str, str]) -> str:
    username = get_value(env, "IBKR_PAPER_USERNAME")
    password = get_value(env, "IBKR_PAPER_PASSWORD")
    if not username or not password:
        raise ValueError("IBKR_PAPER_USERNAME or IBKR_PAPER_PASSWORD is missing")

    second_factor_device = get_value(env, "IBKR_SECOND_FACTOR_DEVICE")
    trading_mode = get_value(env, "IBKR_TRADING_MODE", "paper") or "paper"
    read_only = "yes" if get_value(env, "IBKR_READ_ONLY", "no").lower() in {"1", "yes", "true", "on"} else "no"
    accept_incoming = get_value(env, "IBKR_ACCEPT_INCOMING", "accept") or "accept"
    existing_session = get_value(env, "IBKR_EXISTING_SESSION_ACTION", "primaryoverride") or "primaryoverride"
    command_server_port = get_value(env, "IBKR_COMMAND_SERVER_PORT", "7462") or "7462"
    control_from = get_value(env, "IBKR_CONTROL_FROM", "127.0.0.1,localhost") or "127.0.0.1,localhost"
    api_port = get_value(env, "IBKR_OVERRIDE_API_PORT", "7497") or "7497"
    master_client_id = get_value(env, "IBKR_OVERRIDE_MASTER_CLIENT_ID", "98") or "98"
    auto_restart = get_value(env, "IBKR_AUTO_RESTART_TIME")
    cold_restart = get_value(env, "IBKR_COLD_RESTART_TIME")
    closedown_at = get_value(env, "IBKR_CLOSEDOWN_AT")

    return "\n".join(
        [
            "FIX=no",
            f"IbLoginId={username}",
            f"IbPassword={password}",
            f"SecondFactorDevice={second_factor_device}",
            "ReloginAfterSecondFactorAuthenticationTimeout=yes",
            "SecondFactorAuthenticationExitInterval=60",
            "SecondFactorAuthenticationTimeout=180",
            f"TradingMode={trading_mode}",
            "AcceptNonBrokerageAccountWarning=yes",
            "LoginDialogDisplayTimeout=60",
            f"IbDir={SETTINGS_DIR}",
            "StoreSettingsOnServer=no",
            "MinimizeMainWindow=yes",
            f"ExistingSessionDetectedAction={existing_session}",
            f"OverrideTwsApiPort={api_port}",
            f"OverrideTwsMasterClientID={master_client_id}",
            "ReadOnlyLogin=no",
            f"ReadOnlyApi={read_only}",
            f"AcceptIncomingConnectionAction={accept_incoming}",
            f"AutoRestartTime={auto_restart}",
            f"ColdRestartTime={cold_restart}",
            f"ClosedownAt={closedown_at}",
            f"CommandServerPort={command_server_port}",
            f"ControlFrom={control_from}",
            "",
        ]
    )


def main() -> int:
    env = load_env_file(ENV_FILE)
    ensure_dirs()
    config_body = render_config(env)
    CONFIG_FILE.write_text(config_body)

    state = RuntimeState(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        config_file=str(CONFIG_FILE),
        settings_dir=str(SETTINGS_DIR),
        log_dir=str(LOG_DIR),
        trading_mode=get_value(env, "IBKR_TRADING_MODE", "paper") or "paper",
        read_only_api="yes" if get_value(env, "IBKR_READ_ONLY", "no").lower() in {"1", "yes", "true", "on"} else "no",
        api_port=get_value(env, "IBKR_OVERRIDE_API_PORT", "7497") or "7497",
        command_server_port=get_value(env, "IBKR_COMMAND_SERVER_PORT", "7462") or "7462",
    )
    STATE_FILE.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2))

    print("IBKR Paper Runtime Prepared")
    print("=" * 60)
    print(f"config_file: {CONFIG_FILE}")
    print(f"settings_dir: {SETTINGS_DIR}")
    print(f"log_dir: {LOG_DIR}")
    print(f"trading_mode: {state.trading_mode}")
    print(f"read_only_api: {state.read_only_api}")
    print(f"api_port: {state.api_port}")
    print(f"command_server_port: {state.command_server_port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
