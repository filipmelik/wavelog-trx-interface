import asyncio
from lib import ssd1306
from application.config_manager import ConfigManager
from application.constants import DEFAULT_DEVICE_NAME
from application.main_app import MainApp
from application.wifi_manager import WifiManager
from helpers.display_helper import DisplayHelper
from helpers.omnirig_helper import OmnirigHelper
from application.setup_manager import SetupManager
from machine import UART, Pin, SoftI2C
from neopixel import NeoPixel
from helpers.logger import Logger
from lib.omnirig import OmnirigCommandExecutor, OmnirigValueDecoder, OmnirigValueEncoder

LOG_LEVEL = Logger.DEBUG

# Hardware configuration
setup_button_pin = Pin(0, Pin.IN, Pin.PULL_UP)
on_board_rgb_led_pin = Pin(48, Pin.OUT)
i2c = SoftI2C(sda=Pin(7), scl=Pin(6))
oled_display = ssd1306.SSD1306_I2C(128, 64, i2c)
on_board_rgb_led = NeoPixel(on_board_rgb_led_pin, 1) # 1 means one pixel
uart = UART(2) # UART number 2

def set_global_exception_handler():
    """
    Debug aid, for more info see:
    https://github.com/peterhinch/micropython-async/blob/master/v3/docs/TUTORIAL.md#224-a-typical-firmware-app
    """
    def handle_exception(loop, context):
        import sys
        sys.print_exception(context["exception"])
        sys.exit()
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_exception)

async def main():
    """
    Main entrypoint
    """
    logger = Logger(log_level=LOG_LEVEL)
    logger.info(f"Starting {DEFAULT_DEVICE_NAME}")
    set_global_exception_handler()
    
    config_manager = ConfigManager()
    omnirig_helper = OmnirigHelper(logger=logger)
    wifi_manager = WifiManager(config_manager=config_manager, logger=logger)
    display_helper = DisplayHelper(oled_display=oled_display)
    setup_manager = SetupManager(
        logger=logger,
        display=display_helper,
        config_manager=config_manager,
        neopixel=on_board_rgb_led,
    )
    omnirig_command_executor = OmnirigCommandExecutor(
        value_decoder=OmnirigValueDecoder(),
        value_encoder=OmnirigValueEncoder(),
        uart=uart,
        logger=logger,
    )
    
    device_is_already_configured = config_manager.config_file_exists()
    if device_is_already_configured:
        logger.debug("Device has existing config file, proceeding to normal startup")
        logger.info("Starting up main application")
        main_app = MainApp(
            uart=uart,
            setup_button_pin=setup_button_pin,
            neopixel=on_board_rgb_led,
            logger=logger,
            display=display_helper,
            config_manager=config_manager,
            wifi_manager=wifi_manager,
            setup_manager=setup_manager,
            omnirig_helper=omnirig_helper,
            omnirig_command_executor=omnirig_command_executor,
        )
        await main_app.run()
    else:
        logger.debug("Device was not yet configured, launching setup")
        logger.info("Starting up setup")
        access_point_ssid = DEFAULT_DEVICE_NAME
        logger.debug(f"Creating wi-fi access point with ssid '{access_point_ssid}'")
        device_ip_address = wifi_manager.create_wifi_access_point(
            essid=access_point_ssid
        )
        setup_manager.display_setup_mode_active_message(
            setup_server_ip_address=device_ip_address,
            ssid=access_point_ssid,
        )
        await setup_manager.run_setup_server(device_ip_address=device_ip_address)
    
try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()  # Clear retained state