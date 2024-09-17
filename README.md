# SunPower Home Assistant Interface
An application that reads data from the PVS and ESS to publish data to an MQTT server for usage with Home Assistant.

# Installing
1. Make a copy of `config_template.ini` and name it `config.ini`.
2. Populate the `mqtt` section with your MQTT host, port. Username and password can be left blank if not configured. You can also change the topic prefix if desired, this can be useful if you have multiple PVS installations.
3. If you have an ESS, populate the `ess` section by setting `enabled` to `True` and setting `battery_count` to the number of batteries your system has.
4. If you do not want to enable home assistant configuration data it can be disabled by setting `send_config` to `False`.
5. Under the default configuration each device name will have its serial number in its name which can make the names very long. You can populate `serial_to_id` section to rename specific serial numbers. The template gives the example of a panel with the serial number `E01234567890ABCDE` which would have a device name of `Panel E01234567890ABCDE` being renamed to `A1` which would then have a device name of `Panel A1`. Additionally this can be used to remove the serial number from a name for devices like the PVS.
6. Give `run.sh` the ability to be executed using `chmod`.

# Executing
1. Run `run.sh` which will create the python virtual environment and install all required dependencies if required and run the application.

