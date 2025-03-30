from helpers.logger import Logger


class IcomBTConnectionManager:
    
    def __init__(
        self,
        logger: Logger,
    ):
        self._logger = logger
        self._connection = None
        self._icom_rx_tx_characteristic = None
        self._civ_access_granted = False
        
    def get_device_connection(self):
        return self._connection
        
    def set_device_connection(self, connection):
        self._connection = connection
    
    def reset_device_connection(self):
        self._connection = None
        
    def get_icom_serial_characteristic(self):
        return self._icom_rx_tx_characteristic
        
    def set_icom_serial_characteristic(self, characteristic):
        self._icom_rx_tx_characteristic = characteristic
        
    def reset_icom_serial_characteristic(self):
        self._icom_rx_tx_characteristic = None
        
    def set_icom_civ_access_granted(self):
        self._civ_access_granted = True
        
    def reset_icom_civ_access_granted(self):
        self._civ_access_granted = False
        
    def bt_is_ready(self) -> bool:
        return (
            self._connection
            and self._connection.is_connected()
            and self._icom_rx_tx_characteristic
            and self._civ_access_granted
        )