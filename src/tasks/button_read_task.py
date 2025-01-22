import asyncio

from machine import Pin

from helpers.logger import Logger


class ButtonReadTask:
    
    TASK_CYCLE_MS = 200
    
    # how many task cycles needs to pass until button press is considered to be "long press"
    LONG_PRESS_CYCLE_COUNT = 15
    
    def __init__(
        self,
        setup_button_pin: Pin,
        setup_button_short_press_event: asyncio.Event,
        setup_button_long_press_event: asyncio.Event,
        logger: Logger,
    ):
        self._setup_button_pin = setup_button_pin
        self._setup_button_short_press_event = setup_button_short_press_event
        self._setup_button_long_press_event = setup_button_long_press_event
        self._logger = logger
        
        self._button_pressed_cycle_count = 0
        self._is_running = True
    
    async def run(self):
        while self._is_running:
            button_pressed = self._setup_button_pin.value() == 0
            if button_pressed:
                self._button_pressed_cycle_count += 1
            else:
                if (
                    0 < self._button_pressed_cycle_count < ButtonReadTask.LONG_PRESS_CYCLE_COUNT
                ):
                    # short press
                    self._logger.debug(
                        f"ButtonReadTask: short press: {self._button_pressed_cycle_count} cycles "
                        f"({self._button_pressed_cycle_count * ButtonReadTask.TASK_CYCLE_MS}ms) "
                        f"passed"
                    )
                    self._setup_button_short_press_event.set()
                if (
                    0 < self._button_pressed_cycle_count > ButtonReadTask.LONG_PRESS_CYCLE_COUNT
                ):
                    # long press
                    self._logger.debug(
                        f"ButtonReadTask: long press: {self._button_pressed_cycle_count} cycles "
                        f"({self._button_pressed_cycle_count * ButtonReadTask.TASK_CYCLE_MS}ms) "
                        f"passed"
                    )
                    self._setup_button_long_press_event.set()
                
                if self._button_pressed_cycle_count > 0:
                    # reset the counter
                    self._button_pressed_cycle_count = 0
        
            await asyncio.sleep_ms(ButtonReadTask.TASK_CYCLE_MS)
            
    def stop(self):
        """
        Stop the running task
        """
        self._is_running = False