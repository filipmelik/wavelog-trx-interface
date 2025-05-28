import asyncio
import time

from application.constants import WIFI_CONNECTED_SCREEN_WAIT_TIME
from application.wifi_manager import WifiManager
from helpers.display_helper import DisplayHelper
from helpers.logger import Logger

class WifiConnectionTask:
    
    def __init__(
        self,
        display: DisplayHelper,
        wifi_manager: WifiManager,
        logger: Logger,
    ):
        self._display = display
        self._wifi_manager = wifi_manager
        self._logger = logger
        
        self._is_running = True
        
    async def run(self):
        while self._is_running:
            if self._wifi_manager.is_connected():
                await asyncio.sleep_ms(5000)
                continue
            
            # reconnect to wi-fi and intentionally block until reconnected
            self._logger.info("Reconnecting to Wi-fi")
            try:
                await self._wifi_manager.connect_to_wifi_and_wait_until_connected(
                    blocking_wait_for_connect=True
                )
            except:
                # this resets internal wi-fi state and prevents errors when
                #  device loses connection and is reconnecting
                self._logger.debug(
                    "Got error when connecting to Wi-fi, disconnecting Wi-fi and will try again"
                )
                self._wifi_manager.disconnect_wifi()
                continue
                
            self._logger.info("Wi-fi connected")
            self._wifi_manager.display_wifi_connected_message()
            time.sleep(WIFI_CONNECTED_SCREEN_WAIT_TIME)
            
            await asyncio.sleep_ms(200)
            
    def stop(self):
        """
        Stop the running task
        """
        self._is_running = False
        