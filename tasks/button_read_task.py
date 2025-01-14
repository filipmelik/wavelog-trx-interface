import asyncio

from machine import Pin

from helpers.logger import Logger


class ButtonReadTask:
    
    def __init__(
        self,
        setup_button_pin: Pin,
        setup_button_pressed_event: asyncio.Event,
        logger: Logger,
    ):
        self._setup_button_pin = setup_button_pin
        self._setup_button_pressed_event = setup_button_pressed_event
        self._logger = logger
    
    async def run(self):
        while True:
            button_pressed = self._setup_button_pin.value() == 0
            if button_pressed:
                self._setup_button_pressed_event.set()
            await asyncio.sleep_ms(200)