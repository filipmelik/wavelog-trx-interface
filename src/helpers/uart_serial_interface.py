from machine import UART

from application.config_manager import ConfigManager
from application.constants import (
    CFG_KEY_RADIO_BAUD_RATE,
    CFG_KEY_RADIO_DATA_BITS,
    CFG_KEY_RADIO_STOP_BITS,
    CFG_KEY_RADIO_PARITY,
    CFG_KEY_RADIO_UART_INVERT_RX,
    CFG_KEY_RADIO_UART_INVERT_TX,
)
from board_config import BoardConfig
from helpers.logger import Logger


class UARTSerialInterface:
    """
    Wrapper over UART serial interface
    """
    
    def __init__(
        self,
        uart: UART,
        board_config: BoardConfig,
        config_manager: ConfigManager,
        logger: Logger,
    ):
        self._board_config = board_config
        self._config_manager = config_manager
        self._logger = logger
        self._uart = uart
    
    def configure_uart(self):
        """
        Configure UART interface for communication with transceiver with values from config
        """
        self._logger.info("Configuring UART")

        config = self._config_manager.get_config()
        
        uart_baudrate = int(config.get(CFG_KEY_RADIO_BAUD_RATE))
        uart_bits = int(config.get(CFG_KEY_RADIO_DATA_BITS))
        uart_stop_bits = int(config.get(CFG_KEY_RADIO_STOP_BITS))
        uart_parity = config.get(CFG_KEY_RADIO_PARITY)
        
        if uart_parity == 'odd':
            parity = 1
            parity_str = 'O'
        elif uart_parity == 'even':
            parity = 0
            parity_str = 'E'
        else:
            parity = None
            parity_str = 'N'
        
        uart_should_invert_rx = config.get(CFG_KEY_RADIO_UART_INVERT_RX) == "yes"
        uart_should_invert_tx = config.get(CFG_KEY_RADIO_UART_INVERT_TX) == "yes"
        
        if uart_should_invert_rx and uart_should_invert_tx:
            inversion_config = UART.INV_TX | UART.INV_RX
        elif uart_should_invert_rx:
            inversion_config = UART.INV_RX
        elif uart_should_invert_tx:
            inversion_config = UART.INV_TX
        else:
            inversion_config = 0  # no inversion
        
        self._uart.init(
            baudrate=uart_baudrate,
            bits=uart_bits,
            parity=parity,
            stop=uart_stop_bits,
            tx=self._board_config.uart_tx_pin,
            rx=self._board_config.uart_rx_pin,
            invert=inversion_config,
        )
        self._logger.debug(
            f"UART for TRX communication configured with values from config: "
            f"{uart_baudrate}-{uart_bits}-{parity_str}-{uart_stop_bits}"
        )
        
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