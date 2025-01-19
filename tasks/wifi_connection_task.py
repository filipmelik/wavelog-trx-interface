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
            
            # connect to wifi and intentionally block until connected by using "time.sleep"
            self._logger.info("Connecting to Wi-fi")
            self._display_wifi_reconnecting_message()
            try:
                self._wifi_manager.connect_to_wifi()
            except:
                # this resets internal wifi state and prevents errors when
                #  device loses connection and is reconnecting
                self._logger.debug(
                    "Got error when connecting to Wi-fi, disconnecting Wi-fi and will try again"
                )
                self._wifi_manager.disconnect_wifi()
                continue
                
            self._logger.info("Wi-fi connected")
            self._display_wifi_connected_message(wifi_manager=self._wifi_manager)
            time.sleep(WIFI_CONNECTED_SCREEN_WAIT_TIME)
            
            await asyncio.sleep_ms(200)
            
    def stop(self):
        """
        Stop the running task
        """
        self._is_running = False
            
    def _display_wifi_reconnecting_message(self):
        """
        Display Wi-fi connecting message
        """
        text_rows = ["No wifi", "", "Connecting..."]
        self._display.display_text(text_rows)
    
    def _display_wifi_connected_message(self, wifi_manager: WifiManager):
        """
        Display Wi-fi connected message
        """
        text_rows = ["Wifi connected!", "", f"IP: {wifi_manager.get_device_ip_address()}"]
        self._display.display_text(text_rows)