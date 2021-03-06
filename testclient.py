#!/usr/bin/env python

from govee_api import api, device, helper
import time
import colour
import pygatt

def main():
    # Create Bluetooth adapter
    if helper.can_use_bt_gatttool():
        # Use Linux gatttool service
        bluetooth_adapter = pygatt.GATTToolBackend()
    else:
        # On Windows, you may need to explicitly define the serial port of your BGAPI-compatible device,
        # e.g. pygatt.BGAPIBackend(serial_port = 'COM9')
        bluetooth_adapter = pygatt.BGAPIBackend()

    # HINT: If the bluetooth_adapter is None, the API will try to determine the best matching adapter for you. This may
    # work or may cause errors, most likely on Windows. Thus, I would recommend you to manually set the adapter everytime
    # it is possible

    # Create Govee client and configure event handlers
    govee_cli = api.Govee('your_email', 'your_password', 'your_client_id_or_EMPTY', bluetooth_adapter)
    # BEWARE: This will create a new Govee Client ID with every login. It is recommended to provide an existing client ID
    # within the `Govee` contructor. You can fetch your generated client ID via `govee.client_id` after your successful login

    # Event raised when a new device is discovered
    govee_cli.on_new_device = _on_new_device

    # Event raised when a device status was updated
    govee_cli.on_device_update = _on_device_update

    # Event raised when an API/connection error occurs
    govee_cli.on_error = _on_error

    # Login to Govee
    govee_cli.login()

    # Print out the used client ID
    print('Current client ID is: {}'.format(govee_cli.client_id))

    # Fetch known devices from server
    govee_cli.update_device_list()

    print('Preparing for action :-)')
    # Don't do this in real life. Use the callbacks (e.g. "new device found") the client provides to you!
    time.sleep(10)

    # Loop over all devices
    for dev in govee_cli.devices.values():
        print('Fun with device {} ...'.format(dev.name))

        # Turn on device
        dev.on = True

        # Wait a second
        time.sleep(1)

        # Save initial brightness
        brightness_backup = dev.brightness

        # Set brightness to 50%
        dev.brightness = 0.5

        # Wait a second
        time.sleep(1)

        # Set brightness to 100%
        dev.brightness = 1.0

        # Wait a second
        time.sleep(1)

        if isinstance(dev, device.GoveeRgbLight):
            # Save initial color
            color_backup = dev.color

            # Set color temperature to 2100 kelvin (warm white)
            dev.color_temperature = 2100

            # Wait a second
            time.sleep(1)

            # Set color to green
            dev.color = colour.Color('green')

            # Wait a second
            time.sleep(1)

            # Set color to red
            dev.color = (255, 0, 0)

            # Wait a second
            time.sleep(1)

            # Set color to white
            dev.color = colour.Color('#ffffff')

            # Wait a second
            time.sleep(1)

            # Set color to dodgerblue
            dev.color = colour.Color('dodgerblue')

            # Wait a second
            time.sleep(1)

            # Restore color
            if color_backup:
                dev.color = color_backup

        # Wait a second
        time.sleep(1)

        # Restore initial brightness
        dev.brightness = brightness_backup

        # Wait a second
        time.sleep(1)

        # Turn the device off
        dev.on = False

    print('All done!')

    time.sleep(10) # Wait for last event



# Event handlers
def _on_new_device(govee_cli, dev, raw_data):
    """ New device event """

    print('NEW DEVICE [{}][{} {}] {} -> Connected: {}'.format(dev.identifier, dev.sku, dev.friendly_name, dev.name, \
         dev.connection_status))

def _on_device_update(govee_cli, dev, raw_data):
    """ Device update event """

    on_str = 'No'
    if dev.on:
        on_str = 'Yes'

    if isinstance(dev, device.GoveeRgbLight):
        color_str = 'Non-RGB'
        if dev.color:
            color_str = dev.color.hex_l
        elif dev.color_temperature and dev.color_temperature > 0:
            color_str = '{} Kelvin'.format(dev.color_temperature)
        print('DEVICE UPDATE [{}][{} {}] {} -> Connected: {}, On: {}, Brightness: {}, Color: {}'.format(dev.identifier, \
            dev.sku, dev.friendly_name, dev.name, dev.connection_status, on_str, dev.brightness, color_str))
    else:
        print('DEVICE UPDATE [{}][{} {}] {} -> Connected: {}, On: {}, Brightness: {}'.format(dev.identifier, dev.sku, \
            dev.friendly_name, dev.name, dev.connection_status, on_str, dev.brightness))

def _on_error(govee_cli, dev, message, exception):
    """ API error event """

    if dev:
        print('ERROR [{}][{} {}][{}] -> {}'.format(dev.identifier, dev.sku, dev.friendly_name, dev.name, message))
    else:
        print('ERROR -> {}'.format(message))
    if exception:
        print('   -> {}'.format(exception))


if __name__ == '__main__':
    main()