from helpers.logger import Logger


class IcomBTConnectionManager:
    
    BT_ERRORS_RESET_THRESHOLD = 5
    
    def __init__(
        self,
        logger: Logger,
    ):
        self._logger = logger
        self._connection = None
        self._icom_rx_tx_characteristic = None
        self._civ_access_granted = False
        self._bt_error_count = 0
        
    def get_device_connection(self):
        return self._connection
        
    def set_device_connection(self, connection):
        self._connection = connection
        
    def get_icom_serial_characteristic(self):
        return self._icom_rx_tx_characteristic
        
    def set_icom_serial_characteristic(self, characteristic):
        self._icom_rx_tx_characteristic = characteristic
        
    def set_icom_civ_access_granted(self):
        self._civ_access_granted = True
        
    def reset_bt(self):
        self._connection = None
        self._icom_rx_tx_characteristic = None
        self._civ_access_granted = False
        
    async def disconnect(self):
        if self._connection:
            await self._connection.disconnect()
        
    def bt_is_ready(self) -> bool:
        return (
            self._connection
            and self._connection.is_connected()
            and self._icom_rx_tx_characteristic
            and self._civ_access_granted
        )
    
    def increment_bt_error_counter(self):
        self._bt_error_count += 1
    
    def reset_bt_error_counter(self):
        self._bt_error_count = 0
    
    def had_too_many_consecutive_bt_errors(self) -> bool:
        return self._bt_error_count > self.BT_ERRORS_RESET_THRESHOLD