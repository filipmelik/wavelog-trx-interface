from aioble.core import register_irq_handler
from micropython import const

from application.icom_bt_connection_manager import IcomBTConnectionManager
from helpers.logger import Logger


_IRQ_GATTC_NOTIFY = const(18)
_ICOM_MESSAGE_PREAMBLE = "FEFE"


class IcomBTSerialInterface:
    """
    Wrapper over Bluetooth-backed serial-like interface
    """
    
    def __init__(
        self,
        icom_bt_connection_manager: IcomBTConnectionManager,
        logger: Logger,
    ):
        self._logger = logger
        self._icom_bt_connection_manager = icom_bt_connection_manager
        
        register_irq_handler(self._bt_interrupt_request_handler, None)
        
        self._data_buffer = bytearray()
        
    def flush_buffered_data(self):
        """
        Make the received data buffer empty
        """
        self._data_buffer = bytearray()
        
    def read(self):
        """
        Read data from buffer and flush it, to simulate UART class behavior
        """
        data = self._data_buffer
        self.flush_buffered_data()
        return data
    
    async def write(self, data):
        """
        Write data to BT and wait for reply with timeout.
        The reply will be stored in our buffer
        """
        if not self._icom_bt_connection_manager.bt_is_ready():
            self._logger.info("BT not connected/ready, skipping write")
            return
        
        bt_characteristic = self._icom_bt_connection_manager.get_icom_serial_characteristic()
        await bt_characteristic.write(data, response=True)
        
    
    def _bt_interrupt_request_handler(self, event, data):
        """
        Bluetooth interrupt request handler
        """
        if event == _IRQ_GATTC_NOTIFY:
            # we are interested only in data packets that irqs
            conn_handle, value_handle, notify_data = data
            
            if notify_data:
                hex_interpreted_data = bytes(notify_data).hex().upper()
                if hex_interpreted_data[0:4] == _ICOM_MESSAGE_PREAMBLE:
                    self._data_buffer.extend(bytes(notify_data))
                else:
                    self._logger.debug(
                        f"message received from BT ({bytes(notify_data).hex().upper()}) "
                        f"does not start with icom message preamble ({_ICOM_MESSAGE_PREAMBLE}), "
                        "skipping"
                    )
        else:
            pass