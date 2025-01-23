import time
import requests

from application.config_manager import ConfigManager
from application.constants import (
    TOPIC_TRX_STATUS,
    CFG_KEY_WAVELOG_API_KEY,
    CFG_KEY_RADIO_NAME,
    CFG_KEY_WAVELOG_API_CALL_TIMEOUT,
    CFG_KEY_WAVELOG_API_URL,
    CFG_KEY_WAVELOG_API_CALL_HEARTBEAT_TIME,
)
from helpers.logger import Logger
from helpers.omnirig_helper import OmnirigHelper
from lib.asyncio.broker import Broker
from lib.asyncio.ringbuf_queue import RingbufQueue
from lib.omnirig import TrxStatus
from neopixel import NeoPixel


class WavelogApiCallTask:
    
    def __init__(
        self,
        logger: Logger,
        config_manager: ConfigManager,
        omnirig_helper: OmnirigHelper,
        neopixel: NeoPixel,
        message_broker: Broker,
    ):
        self._logger = logger
        self._message_broker = message_broker
        self._omnirig_helper = omnirig_helper
        self._neopixel = neopixel
        
        self._status_values_supported_by_trx = (
            self._omnirig_helper.get_status_values_supported_by_trx()
        )
        self._config = config_manager.get_config()
        self._last_heartbeat_time = 0
        self._last_reported_mode = None
        self._last_reported_trx_tx_frequency = 0
        self._last_reported_trx_rx_frequency = 0
        self._last_reported_rf_power = None
        
        self._queue = RingbufQueue(2)
        self._is_running = True
        
    async def run(self):
        self._message_broker.subscribe(topic=TOPIC_TRX_STATUS, agent=self._queue)
        async for topic, trx_status in self._queue:
            self._logger.debug(f"WavelogApiCallTask: received message: {str(trx_status)}")
            
            heartbeat_seconds = int(self._config[CFG_KEY_WAVELOG_API_CALL_HEARTBEAT_TIME])
            heartbeat_threshold_passed = (
                    (time.time() - self._last_heartbeat_time) > heartbeat_seconds
            )
            if heartbeat_threshold_passed:
                self._logger.debug("WavelogApiCallTask: heartbeat threshold passed")
            
            radio_status_is_not_up_to_date = self._radio_status_is_not_up_to_date(
                trx_status=trx_status
            )
            if radio_status_is_not_up_to_date:
                self._logger.debug("WavelogApiCallTask: TRX status has changed")
            
            self._update_status_led(
                neopixel=self._neopixel,
                radio_status_is_not_up_to_date=radio_status_is_not_up_to_date,
            )
            
            try:
                current_tx_frequency = trx_status.current_tx_frequency()
                current_rx_frequency = trx_status.current_rx_frequency()
                is_power_command_supported = "pmRfPower" in self._status_values_supported_by_trx
                power_value_ok = (
                    True if not is_power_command_supported else trx_status.rf_power is not None
                )
                
                if (
                    current_tx_frequency
                    and trx_status.mode
                    and power_value_ok
                    and (radio_status_is_not_up_to_date or heartbeat_threshold_passed)
                ):
                    self._logger.debug("WavelogApiCallTask: Sending data to wavelog")
                    await self._send_data_to_wavelog(
                        config=self._config,
                        mode=trx_status.mode,
                        tx_freq=current_tx_frequency,
                        rx_freq=current_rx_frequency,
                        rf_power=trx_status.rf_power,
                    )
                    self._logger.debug("WavelogApiCallTask: Wavelog API call OK!")
                    
                    self._last_heartbeat_time = time.time()
                    self._last_reported_trx_tx_frequency = current_tx_frequency
                    self._last_reported_trx_rx_frequency = current_rx_frequency
                    self._last_reported_mode = trx_status.mode
                    self._last_reported_rf_power = trx_status.rf_power
            except Exception as e:
                self._logger.exception(f"WavelogApiCallTask: {str(e)}")
                
    def stop(self):
        """
        Stop the running task
        """
        self._is_running = False
        self._message_broker.unsubscribe(topic=TOPIC_TRX_STATUS, agent=self._queue)
    
    async def _send_data_to_wavelog(
        self,
        config: dict,
        mode: str,
        tx_freq: int,
        rx_freq: int,
        rf_power: int,
    ):
        """
        Perform and Wavelog API call to report the current TRX status
        """
        payload = {
            'mode_rx': mode,
            'mode': mode,
            'frequency_rx': str(rx_freq),
            'key': config[CFG_KEY_WAVELOG_API_KEY],
            'power': None if rf_power is None else rf_power,
            'frequency': str(tx_freq),
            'radio': config[CFG_KEY_RADIO_NAME],
        }
        timeout = float(config[CFG_KEY_WAVELOG_API_CALL_TIMEOUT])
        url = config[CFG_KEY_WAVELOG_API_URL]
        r = requests.post(url, json=payload, timeout=timeout)
        self._logger.debug(f"WavelogApiCallTask: Wavelog API call result: {str(r.text)}")
        r.close()
        
    def _update_status_led(
            self,
            neopixel: NeoPixel,
            radio_status_is_not_up_to_date: bool,
    ):
        if radio_status_is_not_up_to_date:
            # radio status has changed and was not yet sent to API
            neopixel[0] = (10, 0, 0)  # red, low brightness
        else:
            # all data is up-to-date and was already sent to API
            neopixel[0] = (0, 10, 0)  # green, low brightness
        
        neopixel.write()
    
    def _radio_status_is_not_up_to_date(self, trx_status: TrxStatus) -> bool:
        """
        Compare current radio status values to the ones that were already sent to API
        and return True in case current values differ to the values that were sent to API
        """
        current_tx_frequency = trx_status.current_tx_frequency()
        current_rx_frequency = trx_status.current_rx_frequency()
        frequency_has_changed = (
            self._last_reported_trx_tx_frequency != current_tx_frequency
            or self._last_reported_trx_rx_frequency != current_rx_frequency
        )
        mode_has_changed = self._last_reported_mode != trx_status.mode
        rf_power_has_changed = self._last_reported_rf_power != trx_status.rf_power
        
        return (
            frequency_has_changed
            or mode_has_changed
            or rf_power_has_changed
        )