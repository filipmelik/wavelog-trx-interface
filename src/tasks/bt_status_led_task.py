import asyncio

from application.icom_bt_connection_manager import IcomBTConnectionManager
from helpers.logger import Logger
from helpers.status_led_helper import StatusLedHelper


class BTStatusLedTask:
    
    def __init__(
        self,
        status_led_helper: StatusLedHelper,
        bt_connection_manager: IcomBTConnectionManager,
        logger: Logger,
    ):
        self._logger = logger
        self._status_led_helper = status_led_helper
        self._bt_connection_manager = bt_connection_manager
        
        self._is_running = True
        self._led_is_lit = False
        
    async def run(self):
        while self._is_running:
            
            if not self._bt_connection_manager.bt_is_ready():
                # blink until BT ready
                if self._led_is_lit:
                    self._set_bt_led_off()
                else:
                    self._set_bt_led_on()
            else:
                # turn off led when connected to BT
                if self._status_led_helper.is_blue_color_lit():
                    self._set_bt_led_off()
                
            await asyncio.sleep_ms(1000)
            
    def stop(self):
        """
        Stop the running task
        """
        self._set_bt_led_off()
        self._is_running = False
    
    def _set_bt_led_on(self):
        """
        Set Bluetooth LED on
        """
        self._led_is_lit = True
        self._status_led_helper.blue_color()
        
    def _set_bt_led_off(self):
        """
        Set Bluetooth LED off
        """
        self._led_is_lit = False
        self._status_led_helper.led_off()
        