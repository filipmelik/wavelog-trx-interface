from helpers.logger import Logger
from machine import Pin, SoftI2C
from neopixel import NeoPixel
from lib import ssd1306

"""
SETUP BUTTON - REQUIRED
The pin number on ESP32 where the 'setup button' is connected
"""
SETUP_BUTTON_PIN_NUMBER = 0

"""
OLED DISPLAY - OPTIONAL, but highly recommended
The pin numbers that will be used for software-emulated I2C for communicating
with OLED display.
If you do not wish to have display, set both values to None
"""
OLED_DISPLAY_I2C_SCL_PIN_NUMBER = 15  # use None, if you do not wish to have display
OLED_DISPLAY_I2C_SDA_PIN_NUMBER = 2  # use None, if you do not wish to have display

"""
RGB STATUS LED - OPTIONAL
The pin number where the addressable RGB status LED (aka neopixel) is connected.
Some ESP32 development boards have it on board.
If you do not wish to use RGB LED, or your board does not have it, set value to None
"""
RGB_STATUS_LED_PIN_NUMBER = None  # use None, if you do not wish to have RGB LED

"""
Logging level setting for messages sent over board USB-to-UART interface.
Allowed values: Logger.DEBUG / Logger.INFO / Logger.EXCEPTION / Logger.NO_LOGGING
"""
LOG_LEVEL = Logger.DEBUG

class BoardConfig:
    """
    Wrapper around configuration of the board
    """
    
    def __init__(self):
        self.log_level = LOG_LEVEL
        
        self.setup_button_pin = Pin(SETUP_BUTTON_PIN_NUMBER, Pin.IN, Pin.PULL_UP)
        
        if not OLED_DISPLAY_I2C_SDA_PIN_NUMBER or not OLED_DISPLAY_I2C_SCL_PIN_NUMBER:
            self.oled_display = None
        else:
            i2c = SoftI2C(
                sda=Pin(OLED_DISPLAY_I2C_SDA_PIN_NUMBER),
                scl=Pin(OLED_DISPLAY_I2C_SCL_PIN_NUMBER),
            )
            self.oled_display = ssd1306.SSD1306_I2C(128, 64, i2c)
        
        if not RGB_STATUS_LED_PIN_NUMBER:
            self.on_board_rgb_led = None
        else:
            self.on_board_rgb_led = NeoPixel(
                Pin(RGB_STATUS_LED_PIN_NUMBER, Pin.OUT),
                1,  # 1 means one pixel
            )
