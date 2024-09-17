# SunPower Home Assistant Interface

An application that reads data from the PVS and ESS to publish data to an MQTT server for usage with Home Assistant.

This code merges [hass-sunpower](https://github.com/krbaker/hass-sunpower) for sampling PVS data and [sunpower-ess-monitor](https://github.com/webdeck/sunpower-ess-monitor) for sampling ESS data and publishes the data to an MQTT server. Additionally it publishes the MQTT Home Assistant configuration data for automatic device and entity generation.

This code is intended to run on a Raspberry PI Zero under the configuration described in [PVS6 Access and API.pdf](https://starreveld.com/PVS6%20Access%20and%20API.pdf).

It is recommended to keep the sampling period of PVS data above 120 seconds (the default has been set to 300 seconds) as users of [hass-sunpower](https://github.com/krbaker/hass-sunpower) have encountered issues with periods shorter than that.

The modbus interface utilized to get ESS data seems to be much more stable an can go significantly faster than the PVS but has been defaulted to 60 seconds. The default utilized by [sunpower-ess-monitor](https://github.com/webdeck/sunpower-ess-monitor) is 15 seconds.

# Installing

1. Make a copy of `config_template.ini` and name it `config.ini`.
2. Populate the `mqtt` section with your MQTT host, port. Username and password can be left blank if not configured. You can also change the topic prefix if desired, this can be useful if you have multiple PVS installations.
3. If you have an ESS, populate the `ess` section by setting `enabled` to `True` and setting `battery_count` to the number of batteries your system has.
4. If you do not want to enable home assistant configuration data it can be disabled by setting `send_config` to `False`.
5. Under the default configuration each device name will have its serial number in its name which can make the names very long. You can populate `serial_to_id` section to rename specific serial numbers. The template gives the example of a panel with the serial number `E01234567890ABCDE` which would have a device name of `Panel E01234567890ABCDE` being renamed to `A1` which would then have a device name of `Panel A1`. Additionally this can be used to remove the serial number from a name for devices like the PVS.
6. Give `run.sh` the ability to be executed using `chmod`.
7. Install `nmap` using `sudo apt install nmap`.

# Executing

1. Execute `run.sh`. This will create the python virtual environment and install all required python dependencies if required and then run the application.

# Setting up a service

The code can be setup to run as a service by creating a service file, enabling the service, and finally starting the service. Before this is done you should manually execute `run.sh` to make sure the virtual environment is created properly and is publishing data. After ensuring everything is working cancel the script with **CTRL+C** before continuing.

1. Generate the system file `/lib/systemd/system/sunpower_mqtt.service`.
Note you may need to change the **ExecStart** field in the service file.
```
[Unit]
Description=SunPower MQTT Interface
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
Restart=always
RestartSec=15
User=root
ExecStart=/home/pi/code/sunpower_mqtt/run.sh

[Install]
WantedBy=multi-user.target
```
2. Reload the daemon with `sudo systemctl daemon-reload`.
3. Enable the service with `sudo systemctl enable sunpower_mqtt.service`
4. Start the service with `sudo systemctl start sunpower_mqtt.service`
5. Verify the service is running by watching `systemctl status sunpower_mqtt.service` and making sure **Active** indicates **running** and it has been running for at least 5 minutes.

# Known Issues
- PVS sampling periods less than 120 seconds can cause communication issues between your PVS and the SunPower cloud services.
- 