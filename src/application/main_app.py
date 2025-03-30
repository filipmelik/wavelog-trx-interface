import asyncio
import time
import os
from application.icom_bt_connection_manager import IcomBTConnectionManager
from application.config_manager import ConfigManager
from application.constants import (
    DEFAULT_DEVICE_NAME,
    CFG_KEY_RADIO_DRIVER_NAME,
    CFG_KEY_WIFI_NAME,
    RADIO_DRIVER_FILE_PATH,
    CFG_KEY_STARTUP_SCREEN_WAIT_TIME,
    WIFI_CONNECTED_SCREEN_WAIT_TIME, CFG_KEY_RADIO_BLUETOOTH_NAME,
)
from application.setup_manager import SetupManager
from application.wifi_manager import WifiManager
from board_config import BoardConfig
from helpers.display_helper import DisplayHelper
from helpers.logger import Logger
from machine import Pin

from helpers.omnirig_helper import OmnirigHelper
from helpers.status_led_helper import StatusLedHelper
from lib.asyncio.broker import Broker
from lib.omnirig import OmnirigCommandExecutor
from tasks.bt_status_led_task import BTStatusLedTask
from tasks.button_read_task import ButtonReadTask
from tasks.display_status_task import DisplayStatusTask
from tasks.api_server_task import ApiServerTask
from tasks.garbage_collect_task import GarbageCollectTask
from tasks.icom_bt_connection_task import IcomBTConnectionTask
from tasks.rig_data_read_task import RigDataReadTask
from tasks.wavelog_api_call_task import WavelogApiCallTask

from tasks.websocket_client_task import WebsocketClientTask
from tasks.wifi_connection_task import WifiConnectionTask


class MainApp:
    
    def __init__(
        self,
        board_config: BoardConfig,
        setup_button_pin: Pin,
        status_led_helper: StatusLedHelper,
        logger: Logger,
        display: DisplayHelper,
        config_manager: ConfigManager,
        wifi_manager: WifiManager,
        setup_manager: SetupManager,
        omnirig_helper: OmnirigHelper,
        omnirig_command_executor: OmnirigCommandExecutor,
        bt_connection_manager: IcomBTConnectionManager,
    ):
        self._board_config = board_config
        self._setup_button_pin = setup_button_pin
        self._status_led_helper = status_led_helper
        self._logger = logger
        self._display = display
        self._config_manager = config_manager
        self._wifi_manager = wifi_manager
        self._setup_manager = setup_manager
        self._omnirig_helper = omnirig_helper
        self._omnirig_command_executor = omnirig_command_executor
        self._bt_connection_manager = bt_connection_manager
        
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
        
        # wait until wi-fi is connected, but by using 'blocking_wait_for_connect=False'
        # it also lets asyncio scheduler to handle the asyncio tasks called above this line
        # especially the button handler task, which allows us to enter setup in case it
        # is needed, for example to possibly correct the wi-fi username/password
        self._wifi_manager.display_wifi_connecting_message()
        await self._wifi_manager.connect_to_wifi_and_wait_until_connected(
            blocking_wait_for_connect=False
        )
        self._logger.info("Wi-fi connected")
        self._wifi_manager.display_wifi_connected_message()
        time.sleep(WIFI_CONNECTED_SCREEN_WAIT_TIME)
        
        # task that checks that device is connected to wi-fi and reconnects if not
        self._logger.debug("Starting wi-fi connection task")
        wifi_connection_task = WifiConnectionTask(
            display=self._display,
            wifi_manager=self._wifi_manager,
            logger=self._logger,
        )
        asyncio.create_task(wifi_connection_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(wifi_connection_task)
        
        self._logger.debug("Setting up TRX commands")
        self._omnirig_helper.setup()
        
        self._logger.debug("Starting rig data read task")
        rig_data_read_task = RigDataReadTask(
            logger=self._logger,
            config_manager=self._config_manager,
            omnirig_helper=self._omnirig_helper,
            message_broker=self._message_broker,
            omnirig_command_executor=self._omnirig_command_executor,
        )
        asyncio.create_task(rig_data_read_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(rig_data_read_task)
        
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
            status_led_helper=self._status_led_helper,
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
            message_broker=self._message_broker,
            omnirig_helper=self._omnirig_helper,
            omnirig_command_executor=self._omnirig_command_executor,
            config_manager=self._config_manager,
        )
        asyncio.create_task(websocket_client_task.run())
        asyncio.create_task(websocket_client_task.run_trx_status_messages_subscriber())
        self._tasks_to_stop_when_setup_is_launched.append(websocket_client_task)
        
        self._logger.debug("Starting Icom bluetooth connection task")
        icom_bt_connection_task = IcomBTConnectionTask(
            bt_connection_manager=self._bt_connection_manager,
            config_manager=self._config_manager,
            logger=self._logger,
        )
        asyncio.create_task(icom_bt_connection_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(icom_bt_connection_task)
        
        self._logger.debug("Starting bluetooth status LED task")
        bt_status_led_task = BTStatusLedTask(
            status_led_helper=self._status_led_helper,
            bt_connection_manager=self._bt_connection_manager,
            logger=self._logger,
        )
        asyncio.create_task(bt_status_led_task.run())
        self._tasks_to_stop_when_setup_is_launched.append(bt_status_led_task)
        
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
            is_ap_setup_mode=False,
            is_connected_to_wifi=self._wifi_manager.is_connected(),
            setup_server_ip_address=device_ip_address,
            ssid=ssid,
        )
        if self._wifi_manager.is_connected():
            await self._setup_manager.run_setup_server(device_ip_address=device_ip_address)
        else:
            self._logger.debug(
                'Not launching setup server, because device is not connected to wifi'
            )
            
    
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
        
        access_point_ssid = DEFAULT_DEVICE_NAME
        self._logger.debug(f"Creating wi-fi access point with ssid '{access_point_ssid}'")
        device_ip_address = self._wifi_manager.create_wifi_access_point(
            essid=access_point_ssid
        )
        self._setup_manager.display_setup_mode_active_message(
            is_ap_setup_mode=True,
            is_connected_to_wifi=self._wifi_manager.is_connected(),
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
        config = self._config_manager.get_config()
        self._display_splash_screen(config_manager=self._config_manager)
        time.sleep(int(config[CFG_KEY_STARTUP_SCREEN_WAIT_TIME]))
        
        self._logger.info("Setting up wi-fi")
        self._wifi_manager.setup_wifi_as_client()
    
    def _radio_driver_is_missing(self, config_manager: ConfigManager) -> bool:
        """
        Check if radio driver was not yet set up by user on the setup screen
        """
        config = config_manager.get_config()
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

    
    def _display_splash_screen(self, config_manager: ConfigManager):
        """
        Display splash (startup) screen with some useful info
        """
        config = config_manager.get_config()
        device_id = config_manager.get_device_id()
        
        radio_bluetooth_name = config.get(CFG_KEY_RADIO_BLUETOOTH_NAME)
        
        text_rows = [
            device_id,
            "",
            f"Radio: {config.get(CFG_KEY_RADIO_DRIVER_NAME)}",
            f"Wifi: {config.get(CFG_KEY_WIFI_NAME)}",
            f"Radio BT name: {radio_bluetooth_name}",
        ]
        self._display.display_text(text_rows)