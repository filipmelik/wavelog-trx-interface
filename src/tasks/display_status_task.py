from application.constants import TOPIC_TRX_STATUS
from application.wifi_manager import WifiManager
from helpers.display_helper import DisplayHelper
from helpers.logger import Logger
from lib.asyncio.broker import Broker
from lib.asyncio.ringbuf_queue import RingbufQueue
from lib.omnirig import TrxStatus
from micropython import const

class DisplayStatusTask:
    
    NO_VALUE_PLACEHOLDER = const("---")
    
    def __init__(
        self,
        display: DisplayHelper,
        wifi_manager: WifiManager,
        logger: Logger,
        message_broker: Broker,
    ):
        self._display = display
        self._wifi_manager = wifi_manager
        self._logger = logger
        self._message_broker = message_broker
        self._queue = RingbufQueue(2)
        
        self._is_running = True
        
    async def run(self):
        self._message_broker.subscribe(topic=TOPIC_TRX_STATUS, agent=self._queue)
        async for topic, trx_status in self._queue:
            self._logger.debug(f"DisplayStatusTask: received message: {str(trx_status)}")
            self._display_status(
                trx_status=trx_status,
                wifi_manager=self._wifi_manager,
            )
            
    def stop(self):
        """
        Stop the running task
        """
        self._is_running = False
        self._message_broker.unsubscribe(topic=TOPIC_TRX_STATUS, agent=self._queue)
    
    def _display_status(
        self,
        trx_status: TrxStatus,
        wifi_manager: WifiManager,
    ):
        """
        Display current device status and values on the display
        """
        current_tx_frequency = trx_status.current_tx_frequency()
        current_rx_frequency = trx_status.current_rx_frequency()
        
        if not current_tx_frequency:
            tx_freq_string = self.NO_VALUE_PLACEHOLDER
        else:
            tx_f = current_tx_frequency / 1000000
            tx_freq_string = f"{tx_f:.6f}"
        
        if not current_rx_frequency:
            rx_freq_string = self.NO_VALUE_PLACEHOLDER
        else:
            rx_f = current_rx_frequency / 1000000
            rx_freq_string = f"{rx_f:.6f}"
        
        mode_string = (
            trx_status.mode
            if trx_status.mode is not ""
            else self.NO_VALUE_PLACEHOLDER
        )
        power_string = (
            f"{trx_status.rf_power} W"
            if trx_status.rf_power
            else self.NO_VALUE_PLACEHOLDER
        )
        
        try:
            wlan_strength = wifi_manager.get_signal_strength()
        except:
            wlan_strength = 999
            
        if wlan_strength == 999:
            wlan_human_readable = "NO WIFI"
        elif wlan_strength > -70:
            wlan_human_readable = f"Good ({wlan_strength})"
        elif wlan_strength > -80 and wlan_strength <= -70:
            wlan_human_readable = f"Fair ({wlan_strength})"
        else:
            wlan_human_readable = f"Poor ({wlan_strength})"
            
        if (
            current_rx_frequency
            and current_tx_frequency != current_rx_frequency
        ):
            # display rx freq only when we have it and only when it differs from TX freq
            text_rows = [
                f"RX f: {rx_freq_string}",
                f"TX f: {tx_freq_string}",
                f"Mode: {mode_string}",
                f"Power: {power_string}",
                f"Wifi: {wlan_human_readable}",
            ]
        else:
            text_rows = [
                f"Freq: {tx_freq_string}",
                f"Mode: {mode_string}",
                f"Power: {power_string}",
                f"Wifi: {wlan_human_readable}",
            ]
        self._display.display_text(text_lines=text_rows)