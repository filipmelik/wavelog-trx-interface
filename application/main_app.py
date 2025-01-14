import asyncio
import time
import os
from application.config_manager import ConfigManager
from application.constants import (
    DEVICE_NAME,
    CFG_KEY_RADIO_DRIVER_NAME,
    CFG_KEY_WIFI_NAME,
    CFG_KEY_RADIO_BAUD_RATE,
    CFG_KEY_RADIO_DATA_BITS,
    CFG_KEY_RADIO_STOP_BITS,
    CFG_KEY_RADIO_PARITY,
    SPLASH_SCREEN_WAIT_TIME,
    WIFI_CONNECTED_SCREEN_WAIT_TIME, RADIO_DRIVER_FILE_PATH,
)
from application.setup_manager import SetupManager
from application.wifi_manager import WifiManager
from helpers.display_helper import DisplayHelper
from helpers.logger import Logger
from machine import UART, Pin

from helpers.omnirig_helper import OmnirigHelper
from lib.asyncio.broker import Broker
from tasks.button_read_task import ButtonReadTask
from tasks.display_status_task import DisplayStatusTask
from tasks.api_server_task import ApiServerTask
from tasks.rig_read_uart_task import RigReadUartTask
from tasks.wavelog_api_call_task import WavelogApiCallTask
from neopixel import NeoPixel


class MainApp:
    
    def __init__(
        self,
        uart: UART,
        setup_button_pin: Pin,
        neopixel: NeoPixel,
        logger: Logger,
        display: DisplayHelper,
        config_manager: ConfigManager,
        wifi_manager: WifiManager,
        setup_manager: SetupManager,
        omnirig_helper: OmnirigHelper,
    ):
        self._uart = uart
        self._setup_button_pin = setup_button_pin
        self._neopixel = neopixel
        self._logger = logger
        self._display = display
        self._config_manager = config_manager
        self._wifi_manager = wifi_manager
        self._setup_manager = setup_manager
        self._omnirig_helper = omnirig_helper
        
        self._setup_button_pressed_event = asyncio.Event()
        self._message_broker = Broker()
        self._tasks_to_stop_when_setup_is_launched = []
        
    async def run(self):
        self._run_startup_sequence()
        
        self._logger.debug("Starting async tasks...")
        # setup button & setup server related tasks
        self._logger.debug("Starting setup button read task")
        setup_button_read_task_execution = ButtonReadTask(
            setup_button_pin=self._setup_button_pin,
            logger=self._logger,
            setup_button_pressed_event=self._setup_button_pressed_event,
        )
        setup_button_read_task = asyncio.create_task(setup_button_read_task_execution.run())
        self._logger.debug("Starting setup button pressed event wait task")
        setup_button_pressed_waiter = asyncio.create_task(
            self._wait_for_setup_button_pressed_event(event=self._setup_button_pressed_event)
        )
        
        # failsafe check that radio driver exists
        if self._radio_driver_is_missing(config_manager=self._config_manager):
            self._logger.info("Radio driver is missing! Launch setup and upload it")
            self._display_radio_driver_missing_message()
            while True:
                # in case radio driver is missing, intentionally block here so the
                # only action user can take is pressing the button and launching the setup
                await asyncio.sleep_ms(0)

        self._logger.debug("Starting rig status UART reader task")
        rig_read_uart_task_execution = RigReadUartTask(
            uart=self._uart,
            logger=self._logger,
            config_manager=self._config_manager,
            omnirig_helper=self._omnirig_helper,
            message_broker=self._message_broker,
        )
        rig_read_uart_task = asyncio.create_task(rig_read_uart_task_execution.run())
        self._tasks_to_stop_when_setup_is_launched.append(rig_read_uart_task)
        
        self._logger.debug("Starting display status task")
        display_status_task_execution = DisplayStatusTask(
            display=self._display,
            wifi_manager=self._wifi_manager,
            logger=self._logger,
            message_broker=self._message_broker,
        )
        display_status_task = asyncio.create_task(display_status_task_execution.run())
        self._tasks_to_stop_when_setup_is_launched.append(display_status_task)
        
        self._logger.debug("Starting Wavelog API call task")
        wavelog_api_call_task_execution = WavelogApiCallTask(
            logger=self._logger,
            config_manager=self._config_manager,
            omnirig_helper=self._omnirig_helper,
            neopixel=self._neopixel,
            message_broker=self._message_broker,
        )
        wavelog_api_call_task = asyncio.create_task(wavelog_api_call_task_execution.run())
        self._tasks_to_stop_when_setup_is_launched.append(wavelog_api_call_task)
        
        self._logger.debug("Starting general API server task")
        api_server_task_execution = ApiServerTask(
            logger=self._logger,
            wifi_manager=self._wifi_manager,
            message_broker=self._message_broker,
        )
        api_server_task = asyncio.create_task(api_server_task_execution.run_general_api_server())
        self._tasks_to_stop_when_setup_is_launched.append(api_server_task)
        cloudlog_offline_xml_rpc_server_task = (
            asyncio.create_task(api_server_task_execution.run_cloudlog_offline_xml_rpc_server())
        )
        self._tasks_to_stop_when_setup_is_launched.append(
            cloudlog_offline_xml_rpc_server_task
        )
        api_server_trx_status_messages_subscriber_task = (
            asyncio.create_task(api_server_task_execution.run_trx_status_messages_subscriber())
        )
        self._tasks_to_stop_when_setup_is_launched.append(
            api_server_trx_status_messages_subscriber_task
        )
        
        # todo ensure wifi task
        # todo server for cloudlog offline - conditional based on config?
        # todo server for wavelog bandlist
        # todo garbage collect task?
        
        await asyncio.gather(rig_read_uart_task, ) # todo for testing only - this will block forever
        
    async def _wait_for_setup_button_pressed_event(self, event: asyncio.Event):
        """
        "Subtask" that is waiting for "Setup button pressed" event
        """
        await event.wait()  # wait here until event is set
        self._logger.debug('Setup button pressed event activated')
        event.clear()  # Flag caller and enable re-use of the event
        
        self._logger.debug('Stopping tasks that do not need to run while setup is active')
        for task_to_stop in self._tasks_to_stop_when_setup_is_launched:
            task_to_stop.cancel()
        
        device_ip_address = self._wifi_manager.get_device_ip_address()
        ssid = self._wifi_manager.get_device_ssid()
        self._setup_manager.display_setup_mode_active_message(
            setup_server_ip_address=device_ip_address,
            ssid=ssid,
        )
        await self._setup_manager.run_setup_server(device_ip_address=device_ip_address)
        
    
    def _run_startup_sequence(self):
        """
        Perform necessary initialization tasks
        """
        config = self._config_manager.read_config()
        self._display_splash_screen(config=config)
        time.sleep(SPLASH_SCREEN_WAIT_TIME)
        
        self._logger.info("Setting up wi-fi")
        self._wifi_manager.setup_wifi()
        self._wifi_manager.connect_to_wifi()
        self._logger.info("Wi-fi connected")
        self._display_wifi_connected_message()
        time.sleep(WIFI_CONNECTED_SCREEN_WAIT_TIME)
        self._configure_uart(config=config)
    
    def _radio_driver_is_missing(self, config_manager: ConfigManager) -> bool:
        """
        Check if radio driver was not yet set up by user on the setup screen
        """
        config = config_manager.read_config()
        radio_driver_file_exists = RADIO_DRIVER_FILE_PATH in os.listdir()
        config_entry_exists = config.get(CFG_KEY_RADIO_DRIVER_NAME)
        return not radio_driver_file_exists or not config_entry_exists
    
    def _display_radio_driver_missing_message(self):
        """
        Display message that upload of radio driver is needed
        """
        text_rows = [
            "No radio driver",
            "",
            "Open setup",
            "and upload",
            "radio driver",
        ]
        self._display.display_text(text_rows)
        
    def _configure_uart(self, config: dict):
        """
        Configure UART interface for communication with transceiver with values from config
        """
        uart_baudrate = int(config.get(CFG_KEY_RADIO_BAUD_RATE))
        uart_bits = int(config.get(CFG_KEY_RADIO_DATA_BITS))
        uart_stop_bits = int(config.get(CFG_KEY_RADIO_STOP_BITS))
        uart_parity = config.get(CFG_KEY_RADIO_PARITY)
        
        if uart_parity == 'odd':
            parity = 1
            parity_str = 'O'
        elif uart_parity == 'even':
            parity = 0
            parity_str = 'E'
        else:
            parity = None
            parity_str = 'N'
        
        self._uart.init(
            baudrate=uart_baudrate,
            bits=uart_bits,
            parity=parity,
            stop=uart_stop_bits,
        )
        self._logger.debug(
            f"UART for TRX communication configured with values from config: "
            f"{uart_baudrate}-{uart_bits}-{parity_str}-{uart_stop_bits}"
        )
    
    def _display_wifi_connected_message(self):
        """
        Display Wi-fi connected message
        """
        text_rows = ["Wifi connected!"]
        self._display.display_text(text_rows)
    
    def _display_splash_screen(self, config: dict):
        """
        Display splash (startup) screen with some useful info
        """
        uart_baudrate = int(config.get(CFG_KEY_RADIO_BAUD_RATE))
        uart_bits = int(config.get(CFG_KEY_RADIO_DATA_BITS))
        uart_stop_bits = int(config.get(CFG_KEY_RADIO_STOP_BITS))
        uart_parity = config.get(CFG_KEY_RADIO_PARITY)
        
        if uart_parity == 'odd':
            parity = 'O'
        elif uart_parity == 'even':
            parity = 'E'
        else:
            parity = 'N'
        
        text_rows = [
            DEVICE_NAME,
            "",
            f"Radio: {config.get(CFG_KEY_RADIO_DRIVER_NAME)}",
            f"Wifi: {config.get(CFG_KEY_WIFI_NAME)}",
            f"UART: {uart_baudrate}-{uart_bits}{parity}{uart_stop_bits}",
        ]
        self._display.display_text(text_rows)