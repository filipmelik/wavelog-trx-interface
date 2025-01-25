import asyncio
from application.config_manager import ConfigManager
from application.constants import DEFAULT_DEVICE_NAME
from application.main_app import MainApp
from application.wifi_manager import WifiManager
from board_config import BoardConfig
from helpers.display_helper import DisplayHelper
from helpers.omnirig_helper import OmnirigHelper
from application.setup_manager import SetupManager
from helpers.logger import Logger
from helpers.status_led_helper import StatusLedHelper
from lib.omnirig import OmnirigCommandExecutor, OmnirigValueDecoder, OmnirigValueEncoder


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
    board_config = BoardConfig()
    
    logger = Logger(log_level=board_config.log_level)
    logger.info(f"Starting {DEFAULT_DEVICE_NAME}")
    set_global_exception_handler()
    
    config_manager = ConfigManager()
    omnirig_helper = OmnirigHelper(logger=logger)
    display_helper = DisplayHelper(oled_display=board_config.oled_display)
    status_led_helper = StatusLedHelper(on_board_rgb_led=board_config.on_board_rgb_led)
    wifi_manager = WifiManager(
        display=display_helper,
        config_manager=config_manager,
        logger=logger
    )
    setup_manager = SetupManager(
        logger=logger,
        display=display_helper,
        config_manager=config_manager,
        status_led_helper=status_led_helper,
    )
    omnirig_command_executor = OmnirigCommandExecutor(
        value_decoder=OmnirigValueDecoder(),
        value_encoder=OmnirigValueEncoder(),
        uart=board_config.uart,
        logger=logger,
    )
    
    device_is_already_configured = config_manager.config_file_exists()
    if device_is_already_configured:
        logger.debug("Device has existing config file, proceeding to normal startup")
        logger.info("Starting up main application")
        main_app = MainApp(
            board_config=board_config,
            uart=board_config.uart,
            setup_button_pin=board_config.setup_button_pin,
            status_led_helper=status_led_helper,
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
            is_ap_setup_mode=True,
            is_connected_to_wifi=wifi_manager.is_connected(),
            setup_server_ip_address=device_ip_address,
            ssid=access_point_ssid,
        )
        await setup_manager.run_setup_server(device_ip_address=device_ip_address)
    
try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()  # Clear retained state