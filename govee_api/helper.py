import platform
import shutil
import pygatt

def can_use_bt_gatttool():
    """ Returns if we can theoretically (if installed) use Bluetooth with Linux' `gatttool` (Bluez) """

    # Must be on Linux  (not Windows WSL) and gatttool must be installed
    return platform.system() == 'Linux' and not 'Microsoft' in platform.uname().release and \
        shutil.which('gatttool') is not None

def try_get_best_possible_bluetooth_adapter():
    """ Try to get the best possible, working Bluetooth adapter for the current environment """

    if can_use_bt_gatttool():
        return pygatt.GATTToolBackend()
    else:
        return pygatt.BGAPIBackend()