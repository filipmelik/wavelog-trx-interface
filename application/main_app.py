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
    RADIO_DRIVER_FILE_PATH,
)
from application.setup_manager import SetupManager
from application.wifi_manager import WifiManager
from helpers.display_helper import DisplayHelper
from helpers.logger import Logger
from machine import UART, Pin

from helpers.omnirig_helper import OmnirigHelper
from lib.asyncio.broker import Broker
from lib.omnirig import OmnirigCommandExecutor
from tasks.button_read_task import ButtonReadTask
from tasks.display_status_task import DisplayStatusTask
from tasks.api_server_task import ApiServerTask
from tasks.garbage_collect_task import GarbageCollectTask
from tasks.rig_read_uart_task import RigReadUartTask
from tasks.wavelog_api_call_task import WavelogApiCallTask
from neopixel import NeoPixel

from tasks.websocket_client_task import WebsocketClientTask
from tasks.wifi_connection_task import WifiConnectionTask


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
        omnirig_command_executor: OmnirigCommandExecutor,
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
        self._omnirig_command_executor = omnirig_command_executor
        
        self._setup_button_short_press_event = asyncio.Event()
        self._setup_button_long_press_event = asyncio.Event()
        self._message_broker = Broker()
        self._tasks_to_stop_when_setup_is_launched = []
        
    async def run(self):
        """
        Main app entrypoint
        """
        self._run_startup_sequence()
        self._logger.debug("Starting async tasks...")
        
        self._logger.debug("Starting periodical garbage collection task")
        gc_task = GarbageCollectTask(logger=self._logger)
        asyncio.create_task(gc_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(gc_task)
        
        # setup button & setup server related tasks
        self._logger.debug("Starting setup button press read task")
        setup_button_read_task = ButtonReadTask(
            setup_button_pin=self._setup_button_pin,
            logger=self._logger,
            setup_button_short_press_event=self._setup_button_short_press_event,
            setup_button_long_press_event=self._setup_button_long_press_event,
        )
        asyncio.create_task(setup_button_read_task.run())
        
        self._logger.debug("Starting setup button press event wait task")
        asyncio.create_task(
            self._wait_for_setup_button_short_press_event(
                short_press_event=self._setup_button_short_press_event,
            )
        )
        asyncio.create_task(
            self._wait_for_setup_button_long_press_event(
                long_press_event=self._setup_button_long_press_event,
            )
        )
        
        # failsafe check that radio driver exists
        if self._radio_driver_is_missing(config_manager=self._config_manager):
            self._logger.info("Radio driver is missing! Launch setup and upload it")
            self._display_radio_driver_missing_message()
            while True:
                # in case radio driver is missing, intentionally block here so the
                # only action user can take is pressing the button and launching the setup
                await asyncio.sleep_ms(0)
                
        # task that checks that device is connected to wifi and reconnect if not
        self._logger.debug("Starting wifi connection task")
        wifi_connection_task = WifiConnectionTask(
            display=self._display,
            wifi_manager=self._wifi_manager,
            logger=self._logger,
        )
        asyncio.create_task(wifi_connection_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(wifi_connection_task)

        self._logger.debug("Starting rig status UART reader task")
        rig_read_uart_task = RigReadUartTask(
            uart=self._uart,
            logger=self._logger,
            config_manager=self._config_manager,
            omnirig_helper=self._omnirig_helper,
            message_broker=self._message_broker,
            omnirig_command_executor=self._omnirig_command_executor,
        )
        asyncio.create_task(rig_read_uart_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(rig_read_uart_task)
        
        self._logger.debug("Starting display status task")
        display_status_task = DisplayStatusTask(
            display=self._display,
            wifi_manager=self._wifi_manager,
            logger=self._logger,
            message_broker=self._message_broker,
        )
        asyncio.create_task(display_status_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(display_status_task)
        
        self._logger.debug("Starting Wavelog API call task")
        wavelog_api_call_task = WavelogApiCallTask(
            logger=self._logger,
            config_manager=self._config_manager,
            omnirig_helper=self._omnirig_helper,
            neopixel=self._neopixel,
            message_broker=self._message_broker,
        )
        asyncio.create_task(wavelog_api_call_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(wavelog_api_call_task)
        
        self._logger.debug("Starting general API server tasks")
        api_server_task = ApiServerTask(
            logger=self._logger,
            wifi_manager=self._wifi_manager,
            message_broker=self._message_broker,
            omnirig_helper=self._omnirig_helper,
            omnirig_command_executor=self._omnirig_command_executor,
            config_manager=self._config_manager,
        )
        asyncio.create_task(api_server_task.run_general_api_server())
        asyncio.create_task(api_server_task.run_cloudlog_offline_xml_rpc_server())
        asyncio.create_task(api_server_task.run_trx_status_messages_subscriber())
        self._tasks_to_stop_when_setup_is_launched.append(api_server_task)
        
        self._logger.debug("Starting websocket client task")
        websocket_client_task=WebsocketClientTask(
            logger=self._logger,
        )
        asyncio.create_task(websocket_client_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(websocket_client_task)

        # todo server for cloudlog offline - conditional based on config?
        # todo websocket client for wavelog bandlist???
        
        asyncio.get_event_loop().run_forever()
        
    async def _wait_for_setup_button_short_press_event(
        self,
        short_press_event: asyncio.Event,
    ):
        """
        "Subtask" that is waiting for "Setup button short press" event
        """
        await short_press_event.wait()  # wait here until event is set
        self._logger.debug('Setup button short press event activated')
        short_press_event.clear()  # Flag caller and enable re-use of the event
        
        self._stop_tasks_that_dont_need_to_run_when_setup_is_launched()
        
        device_ip_address = self._wifi_manager.get_device_ip_address()
        ssid = self._wifi_manager.get_device_ssid()
        self._setup_manager.display_setup_mode_active_message(
            setup_server_ip_address=device_ip_address,
            ssid=ssid,
        )
        await self._setup_manager.run_setup_server(device_ip_address=device_ip_address)
    
    async def _wait_for_setup_button_long_press_event(
        self,
        long_press_event: asyncio.Event,
    ):
        """
        "Subtask" that is waiting for "Setup button long press" event
        """
        await long_press_event.wait()  # wait here until event is set
        self._logger.debug('Setup button long press event activated')
        long_press_event.clear()  # Flag caller and enable re-use of the event
        
        self._stop_tasks_that_dont_need_to_run_when_setup_is_launched()
        
        access_point_ssid = DEVICE_NAME
        self._logger.debug(f"Creating wi-fi access point with ssid '{access_point_ssid}'")
        device_ip_address = self._wifi_manager.create_wifi_access_point(
            essid=access_point_ssid
        )
        self._setup_manager.display_setup_mode_active_message(
            setup_server_ip_address=device_ip_address,
            ssid=access_point_ssid,
        )
        await self._setup_manager.run_setup_server(device_ip_address=device_ip_address)
        
    def _stop_tasks_that_dont_need_to_run_when_setup_is_launched(self):
        """
        Stop the tasks that should be stopped while user enters the setup after
        the device is already configured
        """
        self._logger.debug('Stopping tasks that do not need to run while setup is active')
        for task_to_stop in self._tasks_to_stop_when_setup_is_launched:
            task_to_stop.stop()
    
    def _run_startup_sequence(self):
        """
        Perform necessary initialization tasks
        """
        config = self._config_manager.read_config()
        self._display_splash_screen(config=config)
        time.sleep(SPLASH_SCREEN_WAIT_TIME) # TODO configurable?
        
        self._logger.info("Setting up wi-fi")
        self._wifi_manager.setup_wifi_as_client()
        self._logger.info("Setting up UART")
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