from machine import UART


class UARTSerialInterface:
    """
    Wrapper over UART serial interface
    """
    
    def __init__(
        self,
        uart: UART,
    ):
        self._uart = uart
        
    def flush_buffered_data(self):
        """
        Flush data from serial buffer by reading it
        """
        _ = self._uart.read()
        
    def read(self):
        """
        Read data from UART buffer
        """
        return self._uart.read()
    
    async def write(self, data):
        """
        Write data to UART
        """
        self._uart.write(data)