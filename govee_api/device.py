import govee_api.api as gapi
import govee_api.command as command
import abc
import colour
import math
import enum

class IotConnectionStatus(enum.Enum):
    """ Govee device IOT connection status """
    UNKNOWN = enum.auto()
    ONLINE = enum.auto()
    OFFLINE = enum.auto()
    NO_IOT = enum.auto()

class ConnectionStatus(enum.Flag):
    """ Govee device connection status """
    OFFLINE = enum.auto()
    IOT_CONNECTED = enum.auto()
    BT_CONNECTED = enum.auto()


class GoveeDevice(abc.ABC):
    """ Govee Smart device """
    
    def __init__(self, govee, identifier, topic, sku, name, iot_connected):
        """ Creates a new Govee device """

        super(GoveeDevice, self).__init__()

        self.__govee = govee
        self.__identifier = identifier
        self.__topic = topic
        self.__sku = sku
        self.__name = name
        self.__iot_device = iot_connected != IotConnectionStatus.NO_IOT
        if iot_connected == IotConnectionStatus.ONLINE:
            self.__connection_status = ConnectionStatus.IOT_CONNECTED
        else:
            self.__connection_status = ConnectionStatus.OFFLINE


    @property
    def identifier(self):
        """ Gets the device identifier """

        return self.__identifier

    @property
    def _topic(self):
        """ Gets the device topic """

        return self.__topic

    @property
    def sku(self):
        """ Gets the device SKU """

        return self.__sku

    @property
    def name(self):
        """ Gets the device name """

        if not self.__name: # Should never happen, but..
            return '<no name> {} @ {}'.format(self.__sku, self.__identifier)
        else:
            return self.__name

    @name.setter
    def _name(self, val):
        """ Sets the device name """

        self.__name = val

    @property
    @abc.abstractmethod
    def friendly_name(self):
        """ Gets the devices' friendly name """

        pass

    @property
    def _bt_address(self):
        """ Gets the device's Bluetooth MAC address """
        
        return self.__identifier[6:]

    @property
    def _iot_device(self):
        """ Gets the device has IOT (MQTT) capabilities """
        
        return self.__iot_device

    @property
    def connection_status(self):
        """ Gets the device's connection status """

        return self.__connection_status

    @abc.abstractmethod
    def request_status(self):
        """ Request device status """

        pass    

    def _update_state(self, state):
        """ Update device state """

        conn = state['connected']
        if (isinstance(conn, bool) and conn) or conn == 'true' :
            self._add_connection_status(ConnectionStatus.IOT_CONNECTED)
        else:
            self._remove_connection_status(ConnectionStatus.IOT_CONNECTED)

    def _add_connection_status(self, status):
        """ Add connection status to device """

        status_changed = self.__connection_status & status != status

        self.__connection_status = self.__connection_status | status
        if status != ConnectionStatus.OFFLINE:
              self.__connection_status = self.__connection_status & ~ConnectionStatus.OFFLINE
              status_changed = True

        return status_changed

    def _remove_connection_status(self, status):
        """ Remove connection status from device """

        status_changed = self.__connection_status & status == status

        self.__connection_status = self.__connection_status & ~status
        if not self.__connection_status:
              self.__connection_status = ConnectionStatus.OFFLINE
              status_changed = True

        return status_changed


    def _publish_command(self, command):
        """ Build command to control Govee Smart device """

        self.__govee._publish_command(self, command)


class ToggleableGoveeDevice(GoveeDevice):
    """ Toggleable Govee Smart device """
    
    def __init__(self, govee, identifier, topic, sku, name, connection_status):
        """ Creates a new toggleable Govee device """

        super(ToggleableGoveeDevice, self).__init__(govee, identifier, topic, sku, name, connection_status)

        self.__on = None
    
    @property
    def on(self):
        """ Gets if the device is on or off """

        return self.__on

    @on.setter
    def on(self, val):
        """ Turns the device on or off """

        self.__turn(val)

    def toggle(self):
        """ Toggles the device status """

        self.__turn(not self.on)

    def __turn(self, val):
        """ Turn the device on or off """

        if val != self.__on:
            self._publish_command(command.TurnCommand(val))

    def request_status(self):
        """ Request device status """

        self._publish_command(command.StatusCommand())

    def _update_state(self, state):
        """ Update device state """

        super(ToggleableGoveeDevice, self)._update_state(state)

        self.__on = state['onOff'] == 1


class GoveeLight(ToggleableGoveeDevice):
    """ Represents a Govee light of any type """

    def __init__(self, govee, identifier, topic, sku, name, iot_connected):
        """ Creates a new abstract Govee light device """

        super(GoveeLight, self).__init__(govee, identifier, topic, sku, name, iot_connected)

        self.__brightness = None

    def __calc_brightness(self, brightness):
        val = 0
        if brightness:
            val = max(min(int(round(brightness * 255)), 255), 0)
        return val

    @property
    def brightness(self):
        """ Gets the light brightness  """

        return self.__brightness

    @brightness.setter
    def brightness(self, val):
        """ Sets the light brightness """

        if val != self.__brightness:
            self._publish_command(command.BrightnessCommand(self.__calc_brightness(val)))

    def _update_state(self, state):
        """ Update device state """

        super(GoveeLight, self)._update_state(state)

        self.__brightness = max(min(state['brightness'] / 255, 1.0), 0.0)


class GoveeRgbLight(GoveeLight):
    """ Represents a Govee RGB light of any type """

    def __init__(self, govee, identifier, topic, sku, name, iot_connected):
        """ Creates a new abstract Govee RGB light device """

        super(GoveeRgbLight, self).__init__(govee, identifier, topic, sku, name, iot_connected)

        self.__color = None
        self.__color_temperature = None

    def __fix_color_temperature(self, color_temperature):
        fixed = 0
        if color_temperature:
            fixed = max(min(color_temperature, 9000), 2000)
        return fixed

    @property
    def color(self):
        """ Gets the light color  """

        return self.__color

    @color.setter
    def color(self, val):
        """ Sets the light color """

        if val:
            color = self._calc_color(val)
            if color:
                red, green, blue = color
                self._publish_command(command.ColorCommand(red, green, blue))

    def _calc_color(self, val):
        red = 0
        green = 0
        blue = 0

        if isinstance(val, colour.Color):
            if val == self.__color:
                return None
            red = int(round(val.red * 255))
            green = int(round(val.green * 255))
            blue = int(round(val.blue * 255))
        elif isinstance(val, tuple) and len(val) == 3:
            if self.__color and \
               int(round(self.__color.red * 255)) == val[0] and \
               int(round(self.__color.green * 255)) == val[1] and \
               int(round(self.__color.blue * 255)) == val[2]:
                return None
            red = val[0]
            green = val[1]
            blue = val[2]
        else:
            raise gapi.GoveeException('Invalid color value provided')
        
        return (red, green, blue)

    @property
    def color_temperature(self):
        """ Gets the light's color temperature  """

        return self.__color_temperature

    @color_temperature.setter
    def color_temperature(self, val):
        """ Sets the light's color temperature """

        color_temp = self.__fix_color_temperature(val)
        if color_temp > 0 and color_temp != self.__color_temperature:
            red, green, blue = self.__kelvin_to_color(color_temp)
            self._publish_command(command.ColorTemperatureCommand(color_temp, red, green, blue))

    def __kelvin_to_color(self, color_temperature):
        """ Calculate RGB color based on color temperature """

        """
        This code is based on a algorithm published by Tanner Helland on
        https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html
        """

        # Minimum temperature is 1000, maximum temperature is 40000
        color_temp = min(max(color_temperature, 1000), 40000) / 100

        # Calculate red
        if color_temp <= 66:
            red = 255
        else:
            red = min(max(329.698727446 * pow(color_temp - 60, -0.1332047592), 0), 255)
        
        # Calculate green
        if color_temp <= 66:
            green = min(max(99.4708025861 * math.log(color_temp) - 161.1195681661, 0), 255)
        else:
            green = min(max(288.1221695283 * pow(color_temp - 60, -0.0755148492), 0), 255)

        # Calculate blue
        if color_temp >= 66:
            blue = 255
        elif color_temp <= 19:
            blue = 0
        else:
            blue = min(max(138.5177312231 * math.log(color_temp - 10) - 305.0447927307, 0), 255)

        return (int(round(red)),int(round(green)), int(round(blue)))

    def _update_state(self, state):
        """ Update device state """

        super(GoveeRgbLight, self)._update_state(state)

        if 'colorTemInKelvin' in state.keys():
            self.__color_temperature = self.__fix_color_temperature(state['colorTemInKelvin'])
        else:
            self.__color_temperature = None

        if 'color' in state.keys():
            color = state['color']
            self.__color = colour.Color(rgb = (color['r'] / 255.0, color['g'] / 255.0, color['b'] / 255.0))
        else:
            self.__color = None


class GoveeWhiteBulb(GoveeLight):
    """ Represents a Govee bulb """

    def __init__(self, govee, identifier, topic, sku, name, iot_connected):
        """ Creates a new Govee white bulb device """

        super(GoveeWhiteBulb, self).__init__(govee, identifier, topic, sku, name, iot_connected)

    @property
    def friendly_name(self):
        """ Gets the devices' friendly name """

        return 'White bulb'


class GoveeBulb(GoveeRgbLight):
    """ Represents a Govee RGB bulb """

    def __init__(self, govee, identifier, topic, sku, name, iot_connected):
        """ Creates a new Govee RGB bulb device """

        super(GoveeBulb, self).__init__(govee, identifier, topic, sku, name, iot_connected)

    @property
    def friendly_name(self):
        """ Gets the devices' friendly name """

        return 'RGB bulb'

class GoveeLedStrip(GoveeRgbLight):
    """ Represents a Govee LED strip """

    def __init__(self, govee, identifier, topic, sku, name, iot_connected):
        """ Creates a new Govee LED strip device """

        super(GoveeLedStrip, self).__init__(govee, identifier, topic, sku, name, iot_connected)

    @property
    def friendly_name(self):
        """ Gets the devices' friendly name """

        return 'RGB LED strip'