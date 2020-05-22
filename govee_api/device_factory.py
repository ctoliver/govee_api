import govee_api.device as dev

import abc

class _AbstractGoveeDeviceFactory(abc.ABC):
    """ Declare an interface for operations that create abstract Govee devices """

    @abc.abstractmethod
    def build(self, govee, identifier, topic, sku, name, iot_connected):
        """ Build Govee device """

        pass


class _GoveeBulbFactory(_AbstractGoveeDeviceFactory):
    """ Implement the operations to build Govee bulb devices """

    def build(self, govee, identifier, topic, sku, name, iot_connected):
        if sku == 'H6085':
            return dev.GoveeWhiteBulb(govee, identifier, topic, sku, name, iot_connected)
        else:
            return dev.GoveeBulb(govee, identifier, topic, sku, name, iot_connected)


class _GoveeLedStripFactory(_AbstractGoveeDeviceFactory):
    """ Implement the operations to build Govee LED strip devices """

    def build(self, govee, identifier, topic, sku, name, iot_connected):
        return dev.GoveeLedStrip(govee, identifier, topic, sku, name, iot_connected)


#class _GoveeStringLightFactory(_AbstractGoveeDeviceFactory):
#    """ Implement the operations to build Govee string light devices """

#    def build(self, govee, identifier, topic, sku, name, iot_connected):
#        if sku == 'H7022':
#            return dev.H7022GoveeStringLight(govee, identifier, topic, sku, name, iot_connected)
#        return None