from neopixel import NeoPixel

class StatusLedHelper:
    
    def __init__(
        self,
        on_board_rgb_led: NeoPixel,
    ):
        self._on_board_rgb_led = on_board_rgb_led
        
    def signal_api_radio_status_up_to_date(self):
        """
        Signal that all data is up-to-date and was already sent to API
        """
        if not self._on_board_rgb_led:
            return
        
        self._on_board_rgb_led[0] = (0, 10, 0)  # green, low brightness
        self._on_board_rgb_led.write()
    
    def signal_api_radio_status_not_up_to_date(self):
        """
        Signal that radio status has changed and was not yet sent to API
        """
        if not self._on_board_rgb_led:
            return
        
        self._on_board_rgb_led[0] = (10, 0, 0)  # red, low brightness
        self._on_board_rgb_led.write()
    
    def signal_setup_mode_active(self):
        """
        Signal that the device is in setup mode
        """
        if not self._on_board_rgb_led:
            return
        
        self._on_board_rgb_led[0] = (10, 0, 10) # purple, low brightness
        self._on_board_rgb_led.write()
    
    def blue_color(self):
        """
        Light up blue color
        """
        if not self._on_board_rgb_led:
            return
        
        self._on_board_rgb_led[0] = (0, 0, 10)  # blue, low brightness
        self._on_board_rgb_led.write()
    
    def is_blue_color_lit(self) -> bool:
        """
        Light up blue color
        """
        if not self._on_board_rgb_led:
            return False
        
        r, g, b = self._on_board_rgb_led[0]
        
        return r == 0 and g == 0 and b > 0
    
    def led_off(self):
        """
        Turn the LED off
        """
        if not self._on_board_rgb_led:
            return
        
        self._on_board_rgb_led[0] = (0, 0, 0)
        self._on_board_rgb_led.write()