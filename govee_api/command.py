import abc
import enum


class _AbstractCommand(abc.ABC):
    """ Defines an abstract Govee command """

    @abc.abstractmethod
    def get_iot_payload(self):
        """ Gets the IOT-specific payload """

        pass

    @abc.abstractmethod
    def get_bt_payload(self):
        """ Gets the Bluetooth-specific payload """

        pass


class StatusCommand(_AbstractCommand):
    """ Command to change retrieve the status of an Govee device """

    def get_iot_payload(self):
        # I have found out that I can fetch the status of the devices by sending an empty
        # (=no data) `turn` command to them. I do not know how the official app does it and
        # I don't want to decompile it for legal reasons.
        return ('turn', {})

    def get_bt_payload(self):
        # TODO: Is this somehow supported?
        return None


class TurnCommand(_AbstractCommand):
    """ Command to change the status (on/off) of an Govee device """

    def __init__(self, val):
        self.__val = val

    def get_iot_payload(self):
        return ('turn', {
            'val': self.__val
        })

    def get_bt_payload(self):
        boolean = 0x00
        if (self.__val):
            boolean = 0x01
        return (0x01, [boolean])


class ColorCommand(_AbstractCommand):
    """ Command to change the color of an Govee device """

    def __init__(self, red, green, blue):
        self.__red = red
        self.__green = green
        self.__blue = blue

    def get_iot_payload(self):
        return 'color', {
            'red': self.__red,
            'green': self.__green,
            'blue': self.__blue
        }

    def get_bt_payload(self):
        return (0x05, [
            0x02, # Manual mode
            0xff, 0xff, 0xff, 0x01, # RGB color
            self.__red, self.__green, self.__blue
        ])


class ColorTemperatureCommand(_AbstractCommand):
    """ Command to change the color temperature of an Govee device """

    def __init__(self, color_temperature, red, green, blue):
        self.__color_temperature = color_temperature
        self.__red = red
        self.__green = green
        self.__blue = blue

    def get_iot_payload(self):
        return 'colorTem', {
            'color': {
                'red': self.__red,
                'green': self.__green,
                'blue': self.__blue
            },
            'colorTemInKelvin': self.__color_temperature
        }

    def get_bt_payload(self):
        # TODO: Separate flag/data for color temperature?
        return (0x05, [
            0x02, # Manual mode
            0xff, 0xff, 0xff, 0x01, # RGB color
            self.__red, self.__green, self.__blue
        ])


class BrightnessCommand(_AbstractCommand):
    """ Command to change the brightness of an Govee device """

    def __init__(self, val):
        self.__val = val

    def get_iot_payload(self):
        return ('brightness', {
            'val': self.__val
        })

    def get_bt_payload(self):
        return (0x04, [self.__val & 0xFF])