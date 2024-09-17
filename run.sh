#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
VENV_DIR="${SCRIPT_DIR}/.venv"

if [ ! -d "$VENV_DIR" ]; then
  python -m venv $VENV_DIR
  source "${VENV_DIR}/bin/activate"
  pip install paho-mqtt
  pip install netifaces
  pip install python-nmap
  pip install pyModbusTCP
  pip install aiohttp
fi

if [ -d "$VENV_DIR" ]; then
  source "${VENV_DIR}/bin/activate"
  python "${SCRIPT_DIR}/sunpower_mqtt.py"
fi
