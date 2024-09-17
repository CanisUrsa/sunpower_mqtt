import asyncio
import configparser
from ipaddress import IPv4Network
import json
import time

import aiohttp
import netifaces
import nmap
import paho.mqtt.publish as publish
from pyModbusTCP.client import ModbusClient

config = configparser.ConfigParser()
config.read("config.ini")

PVS_SAMPLE_PERIOD = float(config["pvs"]["sample_period"])

ESS_ENABLED = config["ess"].getboolean("enabled")
ESS_SAMPLE_PERIOD = float(config["ess"]["sample_period"])
ESS_HOST = config["ess"]["host"]
ESS_PORT = int(config["ess"]["port"])
ESS_UNIT_ID = int(config["ess"]["unit_id"])
ESS_TIMEOUT = int(config["ess"]["timeout"])
ESS_BATTERY_COUNT = int(config["ess"]["battery_count"])

MQTT_ENABLED = config["mqtt"].getboolean("enabled")
MQTT_PUBLISH_PERIOD = float(config["mqtt"]["publish_period"])
MQTT_HOST = config["mqtt"]["host"]
MQTT_PORT = int(config["mqtt"]["port"])
MQTT_USERNAME = config["mqtt"]["username"]
MQTT_PASSWORD = config["mqtt"]["password"]
MQTT_TOPIC_PREFIX = config["mqtt"]["topic_prefix"]

HOMEASSISTANT_SEND_CONFIG = config["homeassistant"].getboolean("send_config")

SERIAL_TO_ID_ENABLED = config["serial_to_id"].getboolean("enabled")
SERIAL_TO_ID_MAP = { }
for key in config["serial_to_id"]:
    SERIAL_TO_ID_MAP[key] = config["serial_to_id"][key]


# List of all PVS (includes ESS) data that is published to the MQTT server (where applicable).
# This includes information home assistant configuration data which is published when enabled.
PVS_METADATA = {
    "pvs": {
        "name": "PVS",
        "fields": {
            "model":               { "name": "Model",               "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "serial_number":       { "name": "Serial Number",       "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "hardware_version":    { "name": "Hardware Version",    "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "software_version":    { "name": "Software Version",    "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "error_count":         { "name": "Error Count",         "state_class": None, "device_class": "measurement", "unit_of_measurement": None },
            "communication_error": { "name": "Communication Error", "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "skipped_scans":       { "name": "Skipped Scans",       "state_class": None, "device_class": "measurement", "unit_of_measurement": None },
            "scan_time":           { "name": "Scan Time",           "state_class": None, "device_class": "duration",    "unit_of_measurement": "s" },
            "untransmitted":       { "name": "Untransmitted",       "state_class": None, "device_class": "measurement", "unit_of_measurement": None },
            "uptime":              { "name": "Uptime",              "state_class": None, "device_class": "duration",    "unit_of_measurement": "s" },
            "cpu_load":            { "name": "CPU Load",            "state_class": None, "device_class": "measurement", "unit_of_measurement": None },
            "memory_used":         { "name": "Memory Used",         "state_class": None, "device_class": "data_size",   "unit_of_measurement": "kB" },
            "flash_available":     { "name": "Flash Available",     "state_class": None, "device_class": "data_size",   "unit_of_measurement": "kB" },
        },
    },
    "hubplus": {
        "name": "Hub+",
        "fields": {
            "model":            { "name": "Model",            "state_class": None, "device_class": None, "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None, "device_class": None, "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None, "device_class": None, "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None, "device_class": None, "unit_of_measurement": None },
        },
    },
    "ess_hub": {
        "name": "ESS Hub",
        "fields": {
            "model":            { "name": "Model",            "state_class": None,          "device_class": None,          "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None,          "device_class": None,          "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None,          "device_class": None,          "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None,          "device_class": None,          "unit_of_measurement": None },
            "temperature":      { "name": "Temperature",      "state_class": "measurement", "device_class": "temperature", "unit_of_measurement": "°C" },
            "humidity":         { "name": "Humidity",         "state_class": "measurement", "device_class": "humidity",    "unit_of_measurement": "%" },
            "firmware_error":   { "name": "Firmware Error",   "state_class": None,          "device_class": None,          "unit_of_measurement": None },
            "event_history":    { "name": "Event History",    "state_class": None,          "device_class": "measurement", "unit_of_measurement": None },
        },
    },
    "pv_disconnect": {
        "name": "PV Disconnect",
        "fields": {
            "model":            { "name": "Model",            "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "event_history":    { "name": "Event History",    "state_class": None, "device_class": "measurement", "unit_of_measurement": None },
            "firmware_error":   { "name": "Firmware Error",   "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "relay_mode":       { "name": "Relay Mode",       "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "relay1_state":     { "name": "Relay 1 State",    "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "relay2_state":     { "name": "Relay 2 State",    "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "relay1_error":     { "name": "Relay 1 Error",    "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "relay2_error":     { "name": "Relay 2 Error",    "state_class": None, "device_class": None,          "unit_of_measurement": None },
            "relay1_counter":   { "name": "Relay 1 Counter",  "state_class": None, "device_class": "measurement", "unit_of_measurement": None },
            "relay2_counter":   { "name": "Relay 2 Counter",  "state_class": None, "device_class": "measurement", "unit_of_measurement": None },
        },
    },
    "gateway": {
        "name": "Gateway",
        "fields": {
            "model":            { "name": "Model",            "state_class": None,               "device_class": None,     "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None,               "device_class": None,     "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None,               "device_class": None,     "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None,               "device_class": None,     "unit_of_measurement": None },
            "inverter_total":   { "name": "Inverter Total",   "state_class": "total_increasing", "device_class": "energy", "unit_of_measurement": "kWh" }, # Comes from modbus register
            "charge_total":     { "name": "Charge Total",     "state_class": "total_increasing", "device_class": "energy", "unit_of_measurement": "kWh" }, # Comes from modbus register
            "power":            { "name": "Power",            "state_class": "measurement",      "device_class": "power",  "unit_of_measurement": "kW" }, # Comes from modbus register
        },
    },
    "storage_inverter": {
        "name": "Storage Inverter",
        "fields": {
            "model":            { "name": "Model",            "state_class": None, "device_class": None, "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None, "device_class": None, "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None, "device_class": None, "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None, "device_class": None, "unit_of_measurement": None },
        },
    },
    "ess_bms": {
        "name": "ESS BMS",
        "fields": {
            "model":            { "name": "Model",            "state_class": None,               "device_class": None,          "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None,               "device_class": None,          "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None,               "device_class": None,          "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None,               "device_class": None,          "unit_of_measurement": None },
            "charge_total":     { "name": "Charge Total",     "state_class": "total_increasing", "device_class": "energy",      "unit_of_measurement": "kWh" }, # Comes from modbus register
            "inverter_total":   { "name": "Inverter Total",   "state_class": "total_increasing", "device_class": "energy",      "unit_of_measurement": "kWh" }, # Comes from modbus register
            "charge":           { "name": "Charge",           "state_class": None,               "device_class": "battery",     "unit_of_measurement": "%" }, # Comes from modbus register
            "health":           { "name": "Health",           "state_class": None,               "device_class": "measurement", "unit_of_measurement": "%" }, # Comes from modbus register
        },
    },
    "power_meter": {
        "name": "Power Meter",
        "fields": {
            "model":            { "name": "Model",            "state_class": None,               "device_class": None,     "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None,               "device_class": None,     "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None,               "device_class": None,     "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None,               "device_class": None,     "unit_of_measurement": None },
            "power_total":      { "name": "Power Total",      "state_class": "total_increasing", "device_class": "energy", "unit_of_measurement": "kWh" },
            "grid_power_total": { "name": "To Grid",          "state_class": "total_increasing", "device_class": "energy", "unit_of_measurement": "kWh" },
            "home_power_total": { "name": "To Home",          "state_class": "total_increasing", "device_class": "energy", "unit_of_measurement": "kWh" },
        },
    },
    "battery": {
        "name": "Battery",
        "fields": {
            "model":            { "name": "Model",            "state_class": None, "device_class": None, "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None, "device_class": None, "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None, "device_class": None, "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None, "device_class": None, "unit_of_measurement": None },
        },
    },
    "energy_storage_system": {
        "name": "ESS",
        "fields": {
            "model":            { "name": "Model",            "state_class": None, "device_class": None, "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None, "device_class": None, "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None, "device_class": None, "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None, "device_class": None, "unit_of_measurement": None },
        },
    },
    "inverter": {
        "name": "Panel",
        "fields": {
            "model":            { "name": "Model",            "state_class": None,               "device_class": None,          "unit_of_measurement": None },
            "serial_number":    { "name": "Serial Number",    "state_class": None,               "device_class": None,          "unit_of_measurement": None },
            "hardware_version": { "name": "Hardware Version", "state_class": None,               "device_class": None,          "unit_of_measurement": None },
            "software_version": { "name": "Software Version", "state_class": None,               "device_class": None,          "unit_of_measurement": None },
            "power_total":      { "name": "Power Total",      "state_class": "total_increasing", "device_class": "energy",      "unit_of_measurement": "kWh" },
            "power":            { "name": "Power",            "state_class": "measurement",      "device_class": "power",       "unit_of_measurement": "kW" },
            "voltage":          { "name": "Voltage",          "state_class": "measurement",      "device_class": "voltage",     "unit_of_measurement": "V" },
            "amperage":         { "name": "Amperage",         "state_class": "measurement",      "device_class": "current",     "unit_of_measurement": "A" },
            "temperature":      { "name": "Temperature",      "state_class": "measurement",      "device_class": "temperature", "unit_of_measurement": "°C" },
        },
    },
}

# List of all ESS modbus registers to read on the 503 port.
# - address = modbus address
# - type = type of data at address, supported types are int16, uint16, int32, uint32, and stringX (where X is the number of characters)
# - field_name = function to get the field name from the register name
# - transform = function to transform the data from the register
ESS_REGISTERS = {
    "device_name":         { "address": 0x0000, "type": "string16", "field_name": lambda x: x,                "transform": lambda x: x }, # Not particularly useful information
    "firmware_version":    { "address": 0x001E, "type": "string20", "field_name": lambda x: x,                "transform": lambda x: x }, 
    "serial_number":       { "address": 0x002B, "type": "string16", "field_name": lambda x: x,                "transform": lambda x: x },
    "utc_time":            { "address": 0x003A, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x }, # Has the time as UNIX (s)
    "system_status":       { "address": 0x0040, "type": "uint16",   "field_name": lambda x: x,                "transform": lambda x: x }, # Unknown
    "system_faults":       { "address": 0x0041, "type": "uint16",   "field_name": lambda x: x,                "transform": lambda x: x }, # Unknown
    "generator_state":     { "address": 0x0042, "type": "uint16",   "field_name": lambda x: x,                "transform": lambda x: x }, # Unknown
    "system_warnings":     { "address": 0x0043, "type": "uint16",   "field_name": lambda x: x,                "transform": lambda x: x }, # Unknown
    "dc_input_today":      { "address": 0x00A4, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 }, # Sum of bat*_invert_today
    "dc_input_total":      { "address": 0x00B4, "type": "uint32",   "field_name": lambda x: "inverter_total", "transform": lambda x: x * 0.001 }, # Sum of bat*_invert_total
    "dc_output_today":     { "address": 0x00BC, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 }, # Sum of bat*_charge_today
    "dc_output_total":     { "address": 0x00CC, "type": "uint32",   "field_name": lambda x: "charge_total",   "transform": lambda x: x * 0.001 }, # Sum of bat*_charge_total
    "grid_input_today":    { "address": 0x00D4, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 }, # Something (appears to be to the battery, slightly different from dc_output_today)
    "grid_output_today":   { "address": 0x00EC, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 }, # Something (appears to be from the battery to grid/house, slightly different from dc_input_today)
    "battery_power_net":   { "address": 0x0158, "type": "int32",    "field_name": lambda x: "power",          "transform": lambda x: x * 0.001 }, # Negative = Powering Home, Position = Charging Battery, 0 = Nothing is happening
    "bat1_charge_hour":    { "address": 0x0280, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_charge_today":   { "address": 0x0282, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_charge_week":    { "address": 0x0284, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_charge_month":   { "address": 0x0286, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_charge_year":    { "address": 0x0288, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_charge_total":   { "address": 0x028A, "type": "uint32",   "field_name": lambda x: "charge_total",   "transform": lambda x: x * 0.001 },
    "bat1_invert_hour":    { "address": 0x0298, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_invert_today":   { "address": 0x029A, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_invert_week":    { "address": 0x029C, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_invert_month":   { "address": 0x029E, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_invert_year":    { "address": 0x02A0, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat1_invert_total":   { "address": 0x02A2, "type": "uint32",   "field_name": lambda x: "inverter_total", "transform": lambda x: x * 0.001 },
    "bat2_charge_hour":    { "address": 0x02B0, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_charge_today":   { "address": 0x02B2, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_charge_week":    { "address": 0x02B4, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_charge_month":   { "address": 0x02B6, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_charge_year":    { "address": 0x02B8, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_charge_total":   { "address": 0x02BA, "type": "uint32",   "field_name": lambda x: "charge_total",   "transform": lambda x: x * 0.001 },
    "bat2_invert_hour":    { "address": 0x02C8, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_invert_today":   { "address": 0x02CA, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_invert_week":    { "address": 0x02CC, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_invert_month":   { "address": 0x02CE, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_invert_year":    { "address": 0x02C0, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat2_invert_total":   { "address": 0x02C2, "type": "uint32",   "field_name": lambda x: "inverter_total", "transform": lambda x: x * 0.001 },
    "bat3_charge_hour":    { "address": 0x02E0, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_charge_today":   { "address": 0x02E2, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_charge_week":    { "address": 0x02E4, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_charge_month":   { "address": 0x02E6, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_charge_year":    { "address": 0x02E8, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_charge_total":   { "address": 0x02EA, "type": "uint32",   "field_name": lambda x: "charge_total",   "transform": lambda x: x * 0.001 },
    "bat3_invert_hour":    { "address": 0x02F8, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_invert_today":   { "address": 0x02FA, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_invert_week":    { "address": 0x02FC, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_invert_month":   { "address": 0x02FE, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_invert_year":    { "address": 0x0300, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat3_invert_total":   { "address": 0x0302, "type": "uint32",   "field_name": lambda x: "inverter_total", "transform": lambda x: x * 0.001 },
    "bat4_charge_hour":    { "address": 0x0310, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_charge_today":   { "address": 0x0312, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_charge_week":    { "address": 0x0314, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_charge_month":   { "address": 0x0316, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_charge_year":    { "address": 0x0318, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_charge_total":   { "address": 0x031A, "type": "uint32",   "field_name": lambda x: "charge_total",   "transform": lambda x: x * 0.001 },
    "bat4_invert_hour":    { "address": 0x0328, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_invert_today":   { "address": 0x032A, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_invert_week":    { "address": 0x032C, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_invert_month":   { "address": 0x032E, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_invert_year":    { "address": 0x0330, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat4_invert_total":   { "address": 0x0332, "type": "uint32",   "field_name": lambda x: "inverter_total", "transform": lambda x: x * 0.001 },
    "bat5_charge_hour":    { "address": 0x0340, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_charge_today":   { "address": 0x0342, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_charge_week":    { "address": 0x0344, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_charge_month":   { "address": 0x0346, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_charge_year":    { "address": 0x0348, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_charge_total":   { "address": 0x034A, "type": "uint32",   "field_name": lambda x: "charge_total",   "transform": lambda x: x * 0.001 },
    "bat5_invert_hour":    { "address": 0x0358, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_invert_today":   { "address": 0x035A, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_invert_week":    { "address": 0x035C, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_invert_month":   { "address": 0x035E, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_invert_year":    { "address": 0x0360, "type": "uint32",   "field_name": lambda x: x,                "transform": lambda x: x * 0.001 },
    "bat5_invert_total":   { "address": 0x0362, "type": "uint32",   "field_name": lambda x: "inverter_total", "transform": lambda x: x * 0.001 },
    "bat1_soc":            { "address": 0x03C8, "type": "uint32",   "field_name": lambda x: "charge",         "transform": lambda x: x }, # State of charge
    "bat2_soc":            { "address": 0x03D2, "type": "uint32",   "field_name": lambda x: "charge",         "transform": lambda x: x },
    "bat3_soc":            { "address": 0x03DC, "type": "uint32",   "field_name": lambda x: "charge",         "transform": lambda x: x },
    "bat4_soc":            { "address": 0x03E6, "type": "uint32",   "field_name": lambda x: "charge",         "transform": lambda x: x },
    "bat5_soc":            { "address": 0x03F0, "type": "uint32",   "field_name": lambda x: "charge",         "transform": lambda x: x },
    "bat1_soh":            { "address": 0x041E, "type": "uint32",   "field_name": lambda x: "health",         "transform": lambda x: x }, # State of health
    "bat2_soh":            { "address": 0x0420, "type": "uint32",   "field_name": lambda x: "health",         "transform": lambda x: x },
    "bat3_soh":            { "address": 0x0422, "type": "uint32",   "field_name": lambda x: "health",         "transform": lambda x: x },
    "bat4_soh":            { "address": 0x0424, "type": "uint32",   "field_name": lambda x: "health",         "transform": lambda x: x },
    "bat5_soh":            { "address": 0x0426, "type": "uint32",   "field_name": lambda x: "health",         "transform": lambda x: x },
}

# List of base registers to read from the ESS.
ESS_BASE_REGISTERS = [
    "dc_input_total",
    "dc_output_total",
    "battery_power_net",
]

# List of battery registers to read from the ESS for each battery.
ESS_BATTERY_REGISTERS = [
    "bat%d_charge_total",
    "bat%d_invert_total",
    "bat%d_soc",
    "bat%d_soh",
]

ESS_REGISTERS_TO_READ = [] + ESS_BASE_REGISTERS

for battery in range(ESS_BATTERY_COUNT):
    for register in ESS_BATTERY_REGISTERS:
        ESS_REGISTERS_TO_READ.append(register % (battery+1))

PVS_DATA = {}
ESS_DATA = {}

def pvs_process_response(response):
    global PVS_DATA
    global ESS_DATA
    battery_index = 1
    for device in response['devices']:
        device_type = get_safe_name(device['DEVICE_TYPE'])
        device_type = device_type.replace("+", "plus")
        serial_number = device['SERIAL']
        device_key = f"{device_type}_{serial_number}"
        if device_key not in PVS_DATA:
            PVS_DATA[device_key] = {}
        PVS_DATA[device_key]['last_sample_time'] = time.time()
        PVS_DATA[device_key]['model'] = device['MODEL']
        PVS_DATA[device_key]['serial_number'] = device['SERIAL']
        PVS_DATA[device_key]['hardware_version'] = "N/A"
        if "HWVER" in device:
            PVS_DATA[device_key]['hardware_version'] = device['HWVER']
        elif "hw_version" in device:
            PVS_DATA[device_key]['hardware_version'] = device['hw_version']
        PVS_DATA[device_key]['software_version'] = 'N/A'
        if "SWVER" in device:
            PVS_DATA[device_key]['software_version'] = device['SWVER']
        if device_type == "pvs":
            PVS_DATA[device_key]['error_count'] = int(device['dl_err_count'])
            PVS_DATA[device_key]['communication_error'] = int(device['dl_comm_err'])
            PVS_DATA[device_key]['skipped_scans'] = int(device['dl_skipped_scans'])
            PVS_DATA[device_key]['scan_time'] = int(device['dl_scan_time'])
            PVS_DATA[device_key]['untransmitted'] = int(device['dl_untransmitted'])
            PVS_DATA[device_key]['uptime'] = int(device['dl_uptime'])
            PVS_DATA[device_key]['cpu_load'] = float(device['dl_cpu_load'])
            PVS_DATA[device_key]['memory_used'] = int(device['dl_mem_used'])
            PVS_DATA[device_key]['flash_available'] = int(device['dl_flash_avail'])
        elif device_type == "hubplus":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['slave'] = device['slave']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            pass
        elif device_type == "ess_hub":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['slave'] = device['slave']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            PVS_DATA[device_key]['temperature'] = float(device['t_degc'])
            PVS_DATA[device_key]['humidity'] = float(device['humidity'])
            # PVS_DATA[device_key]['v_dcdc_spply_v'] = device['v_dcdc_spply_v']
            # PVS_DATA[device_key]['v_spply_v'] = device['v_spply_v']
            # PVS_DATA[device_key]['v_gateway_v'] = device['v_gateway_v']
            # PVS_DATA[device_key]['fan_actv_fl'] = device['fan_actv_fl']
            PVS_DATA[device_key]['firmware_error'] = int(device['fw_error'])
            PVS_DATA[device_key]['event_history'] = int(device['event_history'])
        elif device_type == "pv_disconnect":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['slave'] = device['slave']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            PVS_DATA[device_key]['event_history'] = int(device['event_history'])
            PVS_DATA[device_key]['firmware_error'] = int(device['fw_error'])
            PVS_DATA[device_key]['relay_mode'] = int(device['relay_mode'])
            PVS_DATA[device_key]['relay1_state'] = int(device['relay1_state'])
            PVS_DATA[device_key]['relay2_state'] = int(device['relay2_state'])
            PVS_DATA[device_key]['relay1_error'] = int(device['relay1_error'])
            PVS_DATA[device_key]['relay2_error'] = int(device['relay2_error'])
            PVS_DATA[device_key]['relay1_counter'] = int(device['relay1_counter'])
            PVS_DATA[device_key]['relay2_counter'] = int(device['relay2_counter'])
            # PVS_DATA[device_key]['v1n_grid_v'] = device['v1n_grid_v']
            # PVS_DATA[device_key]['v2n_grid_v'] = device['v2n_grid_v']
            # PVS_DATA[device_key]['v1n_pv_v'] = device['v1n_pv_v']
            # PVS_DATA[device_key]['v2n_pv_v'] = device['v2n_pv_v']
        elif device_type == "gateway":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['mac_address'] = device['mac_address']
            # PVS_DATA[device_key]['slave'] = device['slave']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            contains_vault = True
            for register in ESS_BASE_REGISTERS:
                if register not in ESS_DATA:
                    contains_vault = False
                    break
            if contains_vault:
                for register in ESS_BASE_REGISTERS:
                    PVS_DATA[device_key][ESS_REGISTERS[register]["field_name"](register)] = ESS_DATA[register]
            pass
        elif device_type == "storage_inverter":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['mac_address'] = device['mac_address']
            # PVS_DATA[device_key]['slave'] = device['slave']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            pass
        elif device_type == "ess_bms":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['mac_address'] = device['mac_address']
            # PVS_DATA[device_key]['slave'] = device['slave']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            contains_battery = True
            for register in ESS_BATTERY_REGISTERS:
                register_name = register % battery_index
                if register_name not in ESS_DATA:
                    contains_battery = False
                    break
            if contains_battery:
                for register in ESS_BATTERY_REGISTERS:
                    register_name = register % battery_index
                    PVS_DATA[device_key][ESS_REGISTERS[register_name]["field_name"](register_name)] = ESS_DATA[register_name]
                battery_index += 1
            pass
        elif device_type == "power_meter":
            subtype = device['subtype']
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['subtype'] = device['subtype']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            # PVS_DATA[device_key]['ct_scl_fctr'] = device['ct_scl_fctr']
            PVS_DATA[device_key]['power_total'] = float(device['net_ltea_3phsum_kwh'])
            # PVS_DATA[device_key]['p_3phsum_kw'] = device['p_3phsum_kw']
            # PVS_DATA[device_key]['q_3phsum_kvar'] = device['q_3phsum_kvar']
            # PVS_DATA[device_key]['s_3phsum_kva'] = device['s_3phsum_kva']
            # PVS_DATA[device_key]['tot_pf_rto'] = device['tot_pf_rto']
            # PVS_DATA[device_key]['freq_hz'] = device['freq_hz']
            if subtype == "GROSS_PRODUCTION_SITE":
                # PVS_DATA[device_key]['i_a'] = device['i_a']
                pass
            elif subtype == "NET_CONSUMPTION_LOADSIDE":
                PVS_DATA[device_key]['grid_power_total'] = float(device['neg_ltea_3phsum_kwh'])
                PVS_DATA[device_key]['home_power_total'] = float(device['pos_ltea_3phsum_kwh'])
                # PVS_DATA[device_key]['i1_a'] = device['i1_a']
                # PVS_DATA[device_key]['i2_a'] = device['i2_a']
                # PVS_DATA[device_key]['v1n_v'] = device['v1n_v']
                # PVS_DATA[device_key]['v2n_v'] = device['v2n_v']
                # PVS_DATA[device_key]['p1_kw'] = device['p1_kw']
                # PVS_DATA[device_key]['p2_kw'] = device['p2_kw']
            # PVS_DATA[device_key]['v12_v'] = device['v12_v']
            # PVS_DATA[device_key]['CAL0'] = device['CAL0']
        elif device_type == "battery":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            pass
        elif device_type == "energy_storage_system":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            PVS_DATA[device_key]['operational_ac_kW'] = float(device['operational_ac_kW'])
            PVS_DATA[device_key]['operational_ac_kWh'] = float(device['operational_ac_kWh'])
            PVS_DATA[device_key]['rated_ac_kW'] = float(device['rated_ac_kW'])
            PVS_DATA[device_key]['rated_ac_kWh'] = float(device['rated_ac_kWh'])
        elif device_type == "inverter":
            # PVS_DATA[device_key]['interface'] = device['interface']
            # PVS_DATA[device_key]['PANEL'] = device['PANEL']
            # PVS_DATA[device_key]['PORT'] = device['PORT']
            # PVS_DATA[device_key]['MOD_SN'] = device['MOD_SN']
            # PVS_DATA[device_key]['NMPLT_SKU'] = device['NMPLT_SKU']
            PVS_DATA[device_key]['power_total'] = float(device['ltea_3phsum_kwh'])
            # PVS_DATA[device_key]['p_3phsum_kw'] = device['p_3phsum_kw']
            # PVS_DATA[device_key]['vln_3phavg_v'] = device['vln_3phavg_v']
            # PVS_DATA[device_key]['i_3phsum_a'] = device['i_3phsum_a']
            PVS_DATA[device_key]['power'] = float(device['p_mppt1_kw'])
            PVS_DATA[device_key]['voltage'] = float(device['v_mppt1_v'])
            PVS_DATA[device_key]['amperage'] = float(device['i_mppt1_a'])
            PVS_DATA[device_key]['temperature'] = float(device['t_htsnk_degc'])
            # PVS_DATA[device_key]['freq_hz'] = device['freq_hz']
            # PVS_DATA[device_key]['stat_ind'] = device['stat_ind']


async def pvs_sample():
    target_time = time.time() + PVS_SAMPLE_PERIOD
    while True:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://192.168.1.13/cgi-bin/dl_cgi?Command=DeviceList", timeout=120) as response:
                pvs_process_response(await response.json())
        sleep_time = target_time - time.time()
        await asyncio.sleep(sleep_time)
        target_time += PVS_SAMPLE_PERIOD


def ess_determine_subnet():
    addr = netifaces.ifaddresses('eth0')[netifaces.AF_INET][0]
    ip = addr['addr']
    cidr = IPv4Network('0.0.0.0/' + addr['netmask']).prefixlen
    return str(ip) + "/" + str(cidr)


def ess_find_host(modbusPort):
    nm = nmap.PortScanner()
    args = "-p " + str(modbusPort) + " -sT"
    nm.scan(hosts=ess_determine_subnet(), arguments=args)
    for host in nm.all_hosts():
        for proto in nm[host].all_protocols():
            if proto == "tcp":
                for port in nm[host][proto].keys():
                    if port == modbusPort and nm[host][proto][port]['state'] == 'open':
                        print(f"host is {host}")
                        return host
    return None


def ess_read_register(modbus, register):
    def to_uint(values):
        if values is None:
            print(f"{register['address']} is None")
        sum = 0
        for v in values:
            sum = (sum << 16) + v
        return register["transform"](sum)

    def to_int(values):
        if values is None:
            print(f"{register['address']} is None")
        sum = 0
        for v in values:
            sum = (sum << 16) + v
        if sum & (1 << (len(values)*16) - 1) > 0:
            sum = sum - (1 << len(values)*16)
        return register["transform"](sum)
    
    def to_string(values):
        if values is None:
            print(f"{register['address']} is None")
        sum = b''
        for v in values:
            sum += v.to_bytes(2, 'big')
        return register["transform"](sum.decode('utf-8'))

    if register["type"].startswith("string"):
        registers = int(register["type"].replace("string", "")) / 2
        return to_string(modbus.read_holding_registers(register["address"], registers))
    elif register["type"] == "uint32":
        return to_uint(modbus.read_holding_registers(register["address"], 2))
    elif register["type"] == "int32":
        return to_int(modbus.read_holding_registers(register["address"], 2))
    elif register["type"] == "int16":
        return to_int(modbus.read_holding_registers(register["address"], 1))
    elif register["type"] == "uint16":
        return to_uint(modbus.read_holding_registers(register["address"], 1))
    else:
        raise ValueError(f"Unknown register type {register['type']}")


async def ess_read_registers(modbus, registers):
    data = {}
    for register_name in registers:
        register = ESS_REGISTERS[register_name]
        data[register_name] = ess_read_register(modbus, register)
        await asyncio.sleep(0.01)
    return data


async def ess_sample():
    if not ESS_ENABLED:
        return
    global PVS_DATA
    global ESS_DATA
    host = ESS_HOST
    if host == "":
        host = ess_find_host(ESS_PORT)
    modbus = ModbusClient(host=host, port=ESS_PORT, auto_open=True, auto_close=True, unit_id=ESS_UNIT_ID, timeout=ESS_TIMEOUT)
    target_time = time.time() + ESS_SAMPLE_PERIOD
    while True:
        ESS_DATA = await ess_read_registers(modbus, ESS_REGISTERS_TO_READ)
        sunpower_has_been_sampled = len([x for x in PVS_DATA]) > 0
        if sunpower_has_been_sampled:
            battery_index = 1
            for device_key in PVS_DATA:
                if device_key.startswith("gateway"):
                    for register in ESS_BASE_REGISTERS:
                        PVS_DATA[device_key][ESS_REGISTERS[register]["field_name"](register)] = ESS_DATA[register]
                elif device_key.startswith("ess_bms"):
                    for register in ESS_BATTERY_REGISTERS:
                        register_name = register % battery_index
                        PVS_DATA[device_key][ESS_REGISTERS[register_name]["field_name"](register_name)] = ESS_DATA[register_name]
                    battery_index += 1
        sleep_time = target_time - time.time()
        await asyncio.sleep(sleep_time)
        target_time += ESS_SAMPLE_PERIOD


def get_safe_name(name):
    return name.lower().replace(" ", "_")


def homeassistant_device_config(device_key, model, name, serial_number):
    return {
        # "connections": [["mac", address]],
        # "hw_version" "",
        "identifiers": [get_safe_name(f"{MQTT_TOPIC_PREFIX}_{device_key}")],
        "manufacturer": "SunPower",
        "model": model,
        # "model_id": "",
        "name": name,
        "serial_number": serial_number,
        # "suggested_area": "",
        # "sw_version": "",
        # "via_device": "",
    }


def homeassistant_config(device_config, device_key, field, name, state_class, device_class, unit_of_measurement):
    payload_json = {
        "unique_id": f"{MQTT_TOPIC_PREFIX}_{device_key}_{field}",
        "object_id": f"{MQTT_TOPIC_PREFIX}_{device_key}_{field}",
        "name": name,
        "state_topic": f"{MQTT_TOPIC_PREFIX}/{device_key}/data",
        "value_template": "{{ value_json." + field + " }}",
        "device": device_config,
        "availability_topic": f"{MQTT_TOPIC_PREFIX}/{device_key}/data",
        "availability_template": "{{ value_json.available }}",
    }
    if state_class is not None:
        payload_json["state_class"] = state_class
    if device_class is not None:
        payload_json["device_class"] = device_class
    if unit_of_measurement is not None:
        payload_json["unit_of_measurement"] = unit_of_measurement
    return {
        "topic": f"homeassistant/sensor/{MQTT_TOPIC_PREFIX}_{device_key}/{field}/config",
        "payload": json.dumps(payload_json)
    }


async def mqtt_publish():
    global PVS_DATA
    global ESS_DATA
    available_time = max(PVS_SAMPLE_PERIOD, ESS_SAMPLE_PERIOD) * 1.50
    target_time = time.time() + MQTT_PUBLISH_PERIOD
    while True:
        if not MQTT_ENABLED:
            printed = False
            for device_key, data in PVS_DATA.items():
                printed = True
                if device_key.startswith("gateway"):
                    print(f"GTW: {data['charge_total']:0.3f},{data['inverter_total']:0.3f},{data['power']:0.3f}")
                elif device_key.startswith("ess_bms"):
                    print(f"BMS: {data['charge_total']:0.3f},{data['inverter_total']:0.3f},{data['charge']}")
                elif device_key.startswith("inverter"):
                    print(f"INV: {data['power_total']:0.3f},{data['power']:0.3f},{data['temperature']}")
            if printed:
                print(PVS_DATA)
        else:
            messages = []
            for device_key, data in PVS_DATA.items():
                data['available'] = 'online' if (time.time() - data['last_sample_time']) < available_time else 'offline'
                for prefix in PVS_METADATA:
                    if device_key.startswith(prefix):
                        device_name = PVS_METADATA[prefix]['name']
                        id = data['serial_number'].lower()
                        if SERIAL_TO_ID_ENABLED and id in SERIAL_TO_ID_MAP:
                            id = SERIAL_TO_ID_MAP[id]
                        device_config = homeassistant_device_config(device_key, data['model'], f"{device_name} {id}".strip(), data['serial_number'])
                        for field in PVS_METADATA[prefix]['fields']:
                            if field not in data:
                                continue
                            field_data = PVS_METADATA[prefix]['fields'][field]
                            field_config = homeassistant_config(device_config, device_key, field, field_data['name'], field_data['state_class'], field_data['device_class'], field_data['unit_of_measurement'])
                            if HOMEASSISTANT_SEND_CONFIG:
                                messages.append(field_config)
                messages.append({ "topic": f"{MQTT_TOPIC_PREFIX}/{device_key}/data", "payload": json.dumps(data) })
            if len(messages) > 0:
                auth = None
                if MQTT_USERNAME != "":
                    auth = { "username": MQTT_USERNAME, "password": MQTT_PASSWORD }
                publish.multiple(messages, hostname=MQTT_HOST, port=MQTT_PORT, auth=auth)
        sleep_time = target_time - time.time()
        await asyncio.sleep(sleep_time)
        target_time += MQTT_PUBLISH_PERIOD


async def main():
    await asyncio.gather(pvs_sample(), ess_sample(), mqtt_publish())


asyncio.run(main())

