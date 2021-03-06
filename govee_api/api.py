import govee_api.device_factory as dev_factory
import govee_api.device as dev
import govee_api.helper as helper
import govee_api.command as cmd

import requests
import time
import uuid
import hashlib
import jwt
import pathlib
import os
import ssl
import AWSIoTPythonSDK.MQTTLib
import json
import pygatt
import enum
import binascii
import traceback



_GOVEE_API_PROTOCOL = 'https'
_GOVEE_API_HOST = 'app.govee.com'
_GOVEE_APP_VERSION = '3.2.1'
_GOVEE_CLIENT_TYPE = '0'
_GOVEE_API_KEY = 'm20xwttRNzBIKE8KP8wP5Mz7S61aSFa8x9cYOTU9'
_GOVEE_MQTT_PROTOCOL_NAME = 'x-amzn-mqtt-ca'
_GOVEE_MQTT_BROKER_HOST = 'aqm3wd1qlc3dy-ats.iot.us-east-1.amazonaws.com'
_GOVEE_MQTT_BROKER_PORT = 8883
_GOVEE_BTLE_UUID_CONTROL_CHARACTERISTIC = '00010203-0405-0607-0809-0a0b0c0d2b11'



class GoveeException(Exception):
    """ Govee API error """

    def __init__(self, *args):
        """ Creates a new Govee exception """

        super(GoveeException, self).__init__()

        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        """ Get exception text """

        if self.message:
            return self.message
        else:
            return 'GoveeException has been raised'


class Govee(object):
    """ Govee API client allowing us to communicate with Govee and thus with Govee Smart products """

    def __init__(self, email, passwd, client_id = None, bluetooth_adapter = None):
        """ Creates a new Govee API client """

        super(Govee, self).__init__()

        # User e-mail and password
        self.__email = email
        self.__passwd = passwd
        self.__login_token = None

        # Storage for our client id and login token
        self.__client_id = client_id
        if not self.__client_id or not isinstance(self.__client_id, str) or len(self.__client_id) != 32:
            # In case no or no valid client_id was provided, create a new one
            self.__client_id = hashlib.md5((str(uuid.uuid4()) + str(self.__current_milli_time())).encode('utf-8')).hexdigest()

        # HTTP default headers
        self.__http_default_headers = {
            'x-api-key': _GOVEE_API_KEY,
            'country': 'US',
            'Accept-Language': 'en',
            'timezone': 'America/Los_Angeles',
            'appVersion': _GOVEE_APP_VERSION,
            'clientId': self.__client_id,
            'clientType': _GOVEE_CLIENT_TYPE,
            'User-Agent': 'okhttp/3.12.0'
        }

        # AWS IoT MQTT client and helpers
        self.__mqtt_connection = None
        self.__mqtt_cert_file = None
        self.__mqtt_topic = None
        self.__mqtt_root_ca = os.path.join(pathlib.Path(__file__).parent.absolute(), 'cert', 'AmazonRootCA1.pem')

        # Bluetooth adapter
        self.__bluetooth_adapter = bluetooth_adapter
        if not self.__bluetooth_adapter:
            # Try to get the `post possible` Bluetooth adapter in case no adapter was provided
            self.__bluetooth_adapter = helper.try_get_best_possible_bluetooth_adapter()
        self.__init_bluetooth_if_required()

        # Device caches
        self.__devices = {}
        self.__bluetooth_connections = {}

        # Events
        self.on_new_device = self.__empty_event_handler
        self.on_device_update = self.__empty_event_handler
        self.on_error = self.__empty_error_event_handler

    def __del__(self):
        """ Destroys the Govee API client """

        # Disconnect from MQTT
        if self.__mqtt_connection:
            try:
                self.__mqtt_connection.disconnect()
            except:
                pass

        # Disconnect from all Bluetooth devices
        for con in self.__bluetooth_connections.values():
            try:
                con.disconnect()
            except:
                pass

        # Stop Bluetooth service
        if self.__bluetooth_adapter:
            self.__bluetooth_adapter.stop()

    @property
    def client_id(self):
        """ Gets the Govee client id """

        return self.__client_id

    @property
    def devices(self):
        """ Gets all known Govee devices """

        return self.__devices

    def __current_milli_time(self):
        """ Returns the current time in milliseconds """

        return int(round(time.time() * 1000))

    def __empty_event_handler(self, govee, device, raw_data):
        """ Empty event handler that should be overwritten by the client """

        pass

    def __empty_error_event_handler(self, govee, device, message, exception):
        """ Empty error event handler that should be overwritten by the client """

        pass

    def login(self):
        """ Login to Govee Home with the provided parameters `email`, `password` and `client_id` """

        self.__login_if_required()

    def __login_if_required(self):
        """ If required, login to Govee Home with the provided parameters `email`, `password` and `client_id` """

        mqtt_certs = None
        require_mqtt_reconnect = False
        if not self.__token_is_valid() or not self.__mqtt_cert_file or not self.__mqtt_topic:
            # Do the login request as we do not have a valid JWT yet

            require_mqtt_reconnect = True

            req = {
                'client': self.__client_id,
                'email': self.__email,
                'key': '',
                'password': self.__passwd,
                'transaction': self.__current_milli_time(),
                'view': 0
            }
            res = self.__http_post(req, '/account/rest/account/v1/login', False)

            # Response:
            """
            {
                "client": {
                    "A": "testiot.cert",
                    "B": "testIot",
                    "accountId": 78440,
                    "client": "4182b33c732fd9c54e7b6e9ef47613cf",
                    "clientType": "0",
                    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7InNpZCI6Im12cEJzR2hCUjdQZ0NwNGdrMzdiM3FDN2dWRUVMbmliIn0sImlhdCI6MTU4ODMxMzYwNSwiZXhwIjoxNTkwOTA1NjA1fQ.lfz20GRPpMg9uuX4JuxDiM1_zD0ht9cgc09IYdG4kaU",
                    "topic": "GA/abfe75884b7aff2cc0e5b6d91a028d25"
                },
                "message": "Login successful",
                "status": 200
            }
            """

            # Check response status
            if res['status'] != 200:
                raise GoveeException('Govee answered with login status {}'.format(res['status']))
            
            # Verify received JWT
            self.__login_token = res['client']['token']
            if not self.__token_is_valid():
                raise GoveeException('Govee sent us an invalid JWT: {}'.format(self.__login_token))

            # Check if we possess the MQTT certificate
            self.__mqtt_cert_file = res['client']['A']
            mqtt_certs = self.__get_absolute_cert_files()
            if not mqtt_certs or \
               not os.path.exists(mqtt_certs[0]) or not os.path.exists(mqtt_certs[1]) or \
               not os.path.isfile(mqtt_certs[0]) or not os.path.isfile(mqtt_certs[1]):
                raise GoveeException('Govee requires the certificate {} which is not known to us'.format(self.__mqtt_cert_file))
    
            # Get MQTT topic
            self.__mqtt_topic = res['client']['topic']

        if require_mqtt_reconnect:
            # Get certificates
            if not mqtt_certs:
                mqtt_certs = self.__get_absolute_cert_files()

            # Disconnect from MQTT broker
            if self.__mqtt_connection:
                try:
                    self.__mqtt_connection.disconnect()
                except:
                    pass
            
            # Remove IOT-connected flag from devices
            for gdev in self.__devices.values():
                if gdev._remove_connection_status(dev.ConnectionStatus.IOT_CONNECTED):
                    self.on_device_update(self, gdev, None)

            # Setup MQTT broker connection
            self.__mqtt_connection = AWSIoTPythonSDK.MQTTLib.AWSIoTMQTTClient(self.__client_id)
            self.__mqtt_connection.configureEndpoint(_GOVEE_MQTT_BROKER_HOST, _GOVEE_MQTT_BROKER_PORT)
            self.__mqtt_connection.configureCredentials(self.__mqtt_root_ca, mqtt_certs[1], mqtt_certs[0])
            self.__mqtt_connection.configureAutoReconnectBackoffTime(1, 32, 20)
            self.__mqtt_connection.configureOfflinePublishQueueing(-1)
            self.__mqtt_connection.configureDrainingFrequency(2)
            self.__mqtt_connection.configureConnectDisconnectTimeout(10)

            # Connect to MQTT broker
            self.__mqtt_connection.connect()

            # Subscribe to topic
            self.__mqtt_connection.subscribe(self.__mqtt_topic, 0, self.__mqtt_topic_callback)

        return True

    def update_device_list(self):
        """
        Get the list of devices assigned to the current account and updates the internal device cache as well.
        Will raise events of type `on_new_device` for every new device found.
        """

        # Update devices via HTTP request (basic device data - no status)
        self.__http_update_device_list()

        # Fetch status for each known device via MQTT
        for gdev in self.__devices.values():
            gdev.request_status()

    def __http_update_device_list(self):
        """
        Get the list of devices assigned to the current account via HTTP and updates the internal device cache
        as well. Will raise events of type `on_new_device` for every new device found.
        """

        # Make sure we are (still) logged in
        self.__login_if_required()

        # Fetch all devices from Govee
        req = {
            'key': '',
            'transaction': self.__current_milli_time(),
            'view': 0
        }
        res = self.__http_post(req, '/device/rest/devices/v1/list')

        # Response:
        """
        {
            "devices": [
                {
                    "device": "AA:BB:CC:DD:EE:FF:11:22",
                    "deviceExt": {
                        "deviceSettings": "{\"wifiName\":\"MyWifi\",\"address\":\"CC:DD:EE:FF:11:22\",\"bleName\":\"ihoment_H6159_XXXX\",\"topic\":\"GD/123467890123467890123467890\",\"sku\":\"H6159\",\"device\":\"AA:BB:CC:DD:EE:FF:11:22\",\"deviceName\":\"Kitchen light\",\"versionHard\":\"1.00.01\",\"versionSoft\":\"1.02.14\"}",
                        "extResources": "{\"skuUrl\":\"\",\"headOnImg\":\"\",\"headOffImg\":\"\",\"ext\":\"\"}",
                        "lastDeviceData": "{\"online\":false}"
                    },
                    "deviceName": "Kitchen light",
                    "goodsType": 0,
                    "sku": "H6159",
                    "versionHard": "1.00.01",
                    "versionSoft": "1.02.14"
                },
                {
                    "device": "A2:B2:C3:D4:E5:F6:77:88",
                    "deviceExt": {
                        "deviceSettings": "{\"wifiName\":\"MyWifi\",\"address\":\"C3:D4:E5:F6:77:88\",\"bleName\":\"ihoment_H6163_YYYY\",\"topic\":\"GD/123467890123467890123467890\",\"sku\":\"H6163\",\"device\":\"A2:B2:C3:D4:E5:F6:77:88\",\"deviceName\":\"Living room\",\"versionHard\":\"1.00.01\",\"versionSoft\":\"1.02.14\"}",
                        "extResources": "{\"skuUrl\":\"\",\"headOnImg\":\"\",\"headOffImg\":\"\",\"ext\":\"\"}",
                        "lastDeviceData": "{\"online\":false}"
                    },
                    "deviceName": "Living room",
                    "goodsType": 0,
                    "sku": "H6163",
                    "versionHard": "1.00.01",
                    "versionSoft": "1.02.14"
                }
            ],
            "message": "",
            "status": 200
        }
        """

        # Check response status
        if res['status'] != 200:
            raise GoveeException('Govee answered with device list status {}'.format(res['status'])) 

        for raw_device in res['devices']:
            identifier = raw_device['device']
            sku = raw_device['sku']
            if not identifier or not sku:
                continue
            name = raw_device['deviceName']
            device_settings = json.loads(raw_device['deviceExt']['deviceSettings'])
            device_settings_keys = device_settings.keys()
            if not 'address' in device_settings_keys and not 'topic' in device_settings_keys:
                continue
            topic = device_settings['topic']

            if identifier in self.__devices.keys():
                device = self.__devices[identifier]
                device._name = name
            else:
                device_factory = self.__get_device_factory(sku)
                if not device_factory:
                    continue
                last_device_data = json.loads(raw_device['deviceExt']['lastDeviceData'])
                if 'online' in last_device_data.keys():
                    if last_device_data['online']:
                        iot_connected = dev.IotConnectionStatus.ONLINE
                    else:
                        iot_connected = dev.IotConnectionStatus.OFFLINE
                elif not 'wifiName' in device_settings:
                    iot_connected = dev.IotConnectionStatus.NO_IOT
                else:
                    iot_connected = dev.IotConnectionStatus.UNKNOWN
                device = device_factory.build(self, identifier, topic, sku, name, iot_connected)
                if device:
                    self.__devices[identifier] = device
                    self.on_new_device(self, device, raw_device)

    def __get_device_factory(self, sku):
        """ Tries to determine the device factory based on the SKU """

        # Check length and for prefix `H`
        if len(sku) < 5 or sku[0] != 'H':
            return None
        
        # Extract the type id/SKU and map it to device class
        type_id = sku[1:3]
        if type_id == '60':
            return dev_factory._GoveeBulbFactory()
        elif type_id == '61':
            return dev_factory._GoveeLedStripFactory()
        #elif type_id == '70':
        #    return dev_factory._GoveeStringLightFactory()
        else:
            return None

    def __token_is_valid(self):
        """ Checks if our internal JWT login token is (still) valid. """

        if not self.__login_token or len(self.__login_token) < 10:
            # Token is not set or totally invalid
            return False

        try:
            jwt.decode(self.__login_token, verify = False)
            return True
        except:
            # Most likely the token is expired as `exp` is in the past
            return False

    def __mqtt_topic_callback(self, client, userdata, message):
        """" Called when a new message was received via MQTT """

        res = message.payload.decode('utf-8')
        raw_json = json.loads(res)

        # Response:
        """
        {
            "proType":0,
            "msg":"{\"transaction\":\"1234567890\",\"sku\":\"H6163\",\"device\":\"A2:B2:C3:D4:E5:F6:77:88\",\"type\":0,\"cmd\":\"status\",\"data\":\"{\\\"softversion\\\":\\\"1.02.17\\\",\\\"wifiSoftVersion\\\":\\\"1.00.33\\\",\\\"turn\\\":1,\\\"brightness\\\":133,\\\"mode\\\":2,\\\"timer\\\":{\\\"enable\\\":0,\\\"time\\\":[{\\\"openHour\\\":18,\\\"openMin\\\":0,\\\"closeHour\\\":23,\\\"closeMin\\\":59}]},\\\"color\\\":{\\\"red\\\":255,\\\"green\\\":215,\\\"blue\\\":0},\\\"colorTemInKelvin\\\":0}\"}",
            "state":{
                "onOff":1,
                "brightness":133,
                "color":{
                    "r":255,
                    "g":215,
                    "b":0
                },
                "colorTemInKelvin":0,
                "connected":"true",
                "sku":"H6163",
                "device":"A2:B2:C3:D4:E5:F6:77:88"
            }
        }

        OR

        {
            "proType":0,
            "msg":"{\"transaction\":\"1234567890\",\"sku\":\"H6163\",\"device\":\"A2:B2:C3:D4:E5:F6:77:88\",\"type\":0,\"cmd\":\"color\",\"data\":\"{\\\"red\\\":0,\\\"green\\\":0,\\\"blue\\\":0}\"}",
            "state":{
                "onOff":1,
                "brightness":159,
                "connected":"true",
                "sku":"H6163",
                "device":"A2:B2:C3:D4:E5:F6:77:88"
            }
        }
        """

        if not 'state' in raw_json:
            return
        state = raw_json['state']

        # Get device
        device_identifer = state['device']
        if not device_identifer in self.__devices:
            self.__http_update_device_list()
            if not device_identifer in self.__devices:
                return
        device = self.__devices[device_identifer]

        # Update device status
        device._update_state(state)
        self.on_device_update(self, device, raw_json)

    def __init_bluetooth_if_required(self):
        """ Initialize Bluetooth in case if was not initialized yet """

        if self.__bluetooth_adapter and ((self.__bluetooth_adapter._running and not self.__bluetooth_adapter._running.is_set()) or not self.__bluetooth_adapter._running):
            try:
                self.__bluetooth_adapter.start()
                return self.__bluetooth_adapter._running.is_set()
            except Exception:
                self.on_error(self, None, 'Unable to initialize Bluetooth adapter', traceback.format_exc())
                return False
        if self.__bluetooth_adapter and self.__bluetooth_adapter._running:
            return self.__bluetooth_adapter._running.is_set()
        else:
            return False

    def _publish_command(self, device, command):
        """ Publish command to device """

        # At first, check if device is connected with IOT (or in case of an status command: if the device is theoretically capable of handling IOT messages).
        # If yes, send message via MQTT
        iot_sent = False
        if device._iot_device and (device.connection_status & dev.ConnectionStatus.IOT_CONNECTED == dev.ConnectionStatus.IOT_CONNECTED or
                isinstance(command, cmd.StatusCommand)):
            iot_sent = self.__publish_iot_payload(device, command)

        # In case nothing was sent via MQTT, do data transfer via Bluetooth connection
        if not iot_sent:
            self.__publish_bt_payload(device, command)


    def __publish_bt_payload(self, device, command):
        """ Publish Bluetooth message to device """
    
        if not self.__init_bluetooth_if_required():
            # Unable to initialize Bluetooth
            return

        payload = command.get_bt_payload()
        if not payload:
            return

        if len(payload[1]) > 17:
            raise GoveeException('Bluetooth data payload too long. Command: {}, Data: {}'.format(payload[0], binascii.hexlify(payload[1])))

        bt = None
        if device._bt_address in self.__bluetooth_connections.keys():
            # Use already existing BT connection
            bt = self.__bluetooth_connections[device._bt_address]
        else:
            retries = 0
            last_exception = None
            while retries < 10:
                try:
                    # Connect to device via Bluetooth
                    if isinstance(self.__bluetooth_adapter, pygatt.GATTToolBackend):
                        bt = self.__bluetooth_adapter.connect(device._bt_address, timeout=2, auto_reconnect=True)
                    else:
                        bt = self.__bluetooth_adapter.connect(device._bt_address, timeout=2)
                    self.__bluetooth_connections[device._bt_address] = bt

                    # Set BT-connected flag on device
                    if device._add_connection_status(dev.ConnectionStatus.BT_CONNECTED):
                        self.on_device_update(self, device, None)

                    break
                except Exception:
                    last_exception = traceback.format_exc()
                    retries = retries + 1
            if retries == 10:
                self.on_error(self, device, 'Unable to connect to device via Bluetooth', last_exception)
                return

        # Build Bluetooth packet data and pad it to a length of 19 bytes
        packet = bytes([0x33, payload[0]]) + bytes(payload[1])
        packet += bytes([0x00] * (19 - len(packet)))

        # Calculate checksum by XORing all data bytes and add it to the end of the packet
        checksum = 0
        for byte in packet:
            checksum ^= byte
        packet += bytes([checksum & 0xFF])

        # Send data
        try:
            bt.char_write(_GOVEE_BTLE_UUID_CONTROL_CHARACTERISTIC, bytearray(packet), wait_for_response=False)
        except Exception:
            self.on_error(self, device, 'Unable to send data ({}) via Bluetooth'.format(binascii.hexlify(packet).decode('utf-8') ), \
                          traceback.format_exc())
                          
            # Remove BT-connected flag from device
            if device._remove_connection_status(dev.ConnectionStatus.BT_CONNECTED):
                self.on_device_update(self, device, None)

            if bt:
                try:
                    bt.disconnect()
                except:
                    pass

    def __publish_iot_payload(self, device, command):
        """ Publish IOT/MQTT message to device """

        int_payload = command.get_iot_payload()

        payload = {
            'msg': {
                'accountTopic': self.__mqtt_topic,
                'cmd': int_payload[0],
                'cmdVersion': 0,
                'data': int_payload[1],
                'transaction': str(self.__current_milli_time()),
                'type': 1
            }
        }

        json_payload = json.dumps(payload, separators=(',', ':'))

        # May result in something like:
        """
        "msg": {
            "accountTopic": "GA/abfe75884b7aff2cc0e5b6d91a028d25",
            "cmd": "color",
            "cmdVersion": 0,
            "data": {
                "red": 255,
                "green": 0,
                "blue": 255
            },
            "transaction": "1234567890",
            "type": 1
        }
        """

        try:
            self.__mqtt_connection.publish(device._topic, json_payload, 0)
            return True
        except Exception:
            self.on_error(self, device, 'Unable to send data ({}) via MQTT'.format(json_payload), traceback.format_exc())
            
            # Remove IOT-connected flag from device
            if device._remove_connection_status(dev.ConnectionStatus.IOT_CONNECTED):
                self.on_device_update(self, device, None)

            return False

    def __get_absolute_cert_files(self):
        """ Gets the absolute paths to the to-be-used cert file and private key """

        abs_path = None
        if self.__mqtt_cert_file:
            root = pathlib.Path(__file__).parent.absolute()
            abs_path = (os.path.join(root, 'cert', self.__mqtt_cert_file + '.pem'),
                        os.path.join(root, 'cert', self.__mqtt_cert_file + '.pkey'))
        return abs_path

    def __http_post(self, data, url_path, with_authentication = True):
        """ Does an HTTP POST request to Govee servers """

        res = requests.post(self.__http_build_url(url_path), json = data, headers = self.__http_build_headers(with_authentication))
        res.raise_for_status()
        return res.json()

    def __http_build_headers(self, with_authentication):
        """ Build headers for outgoing API requests """

        dynamic_headers =  {
            'timestamp': str(self.__current_milli_time())
        }
        if with_authentication and self.__login_token:
            dynamic_headers['Authorization'] = 'Bearer ' + self.__login_token
        
        dynamic_headers.update(self.__http_default_headers)
        return dynamic_headers

    def __http_build_url(self, url_path):
        """ Build the API server URL for outgoing requests """

        return '{}://{}{}'.format(_GOVEE_API_PROTOCOL, _GOVEE_API_HOST, url_path)