import asyncio
import json

from application.config_manager import ConfigManager
from application.constants import TOPIC_TRX_STATUS, CFG_KEY_RADIO_REPLY_TIMEOUT, CFG_KEY_WEBSOCKET_SERVER_ENDPOINT_URL
from helpers.logger import Logger
from helpers.omnirig_helper import OmnirigHelper
from lib.async_websocket_client import AsyncWebsocketClient
from lib.asyncio.broker import Broker
from lib.asyncio.ringbuf_queue import RingbufQueue
from lib.omnirig import TrxStatus, OmnirigCommandExecutor


class WebsocketClientTask:
    
    SOCKET_RW_DELAY_MS = 20 # delay for read/write operations on socket
    WS_SERVER_RECONNECT_SECS = 15 # seconds to wait before reconnect in case the server is down
    
    def __init__(
        self,
        logger: Logger,
        message_broker: Broker,
        omnirig_helper: OmnirigHelper,
        omnirig_command_executor: OmnirigCommandExecutor,
        config_manager: ConfigManager,
    ):
        self._logger = logger
        self._message_broker = message_broker
        self._omnirig_helper = omnirig_helper
        self._omnirig_command_executor = omnirig_command_executor
        self._config_manager = config_manager
        self._config = config_manager.get_config()
        self._queue = RingbufQueue(2)
        
        self._ws_client = None
        self.trx_status: TrxStatus = None
        self._is_running = True
    
    async def run(self):
        ws_server_uri = self._config[CFG_KEY_WEBSOCKET_SERVER_ENDPOINT_URL]
        if not ws_server_uri:
            self._logger.debug(
                f"Websocket client will not be started, because websocket "
                f"server was not specified in device settings"
            )
            return
            
        self._ws_client = AsyncWebsocketClient(
            ms_delay_for_read=WebsocketClientTask.SOCKET_RW_DELAY_MS,
        )
        
        while self._is_running:
            try:
                ws_server_uri = ws_server_uri.strip("/") # strip possible trailing slash
                device_id = self._config_manager.get_device_id()
                ws_endpoint = f"{ws_server_uri}/{device_id}"
                
                self._logger.debug(
                    f"WebsocketClient: Connecting to websocket server at: {ws_endpoint}"
                )
                if not await self._ws_client.handshake(ws_endpoint):
                    raise Exception('Handshake error')
                
                self._logger.debug("WebsocketClient: Connection successful")
                while await self._ws_client.open():
                    data = await self._ws_client.recv()
                    
                    if data is not None:
                        self._logger.debug(f"WebsocketClient: Data received: '{str(data)}'")
                        await self.execute_received_command(received_data=data)
                    else:
                        self._logger.debug("WebsocketClient: Empty data received.")
                    
                    await asyncio.sleep_ms(50)
                
            except Exception as e:
                self._logger.exception(f"WebsocketClient: Connection error: {str(e)}")
            
            self._logger.debug(
                "WebsocketClient: No connection, waiting {} secs".format(
                    WebsocketClientTask.WS_SERVER_RECONNECT_SECS
                )
            )
            await asyncio.sleep(WebsocketClientTask.WS_SERVER_RECONNECT_SECS)
            
    async def run_trx_status_messages_subscriber(self):
        """
        Run subscriber that will read the current TRX status messages
        """
        self._message_broker.subscribe(topic=TOPIC_TRX_STATUS, agent=self._queue)
        async for topic, trx_status in self._queue:
            self.trx_status = trx_status
            
    async def execute_received_command(self, received_data: str):
        """
        Parse and execute command received over websocket connection
        """
        decoded = json.loads(received_data)
        command = decoded.get("command")
        params = decoded.get("params")
        
        if command == "qsy":
            frequency = params.get("frequency")
            await self._perform_qsy(frequency=frequency)
        else:
            error_message = f"WebsocketClient: unknown command received: '{command}'"
            self._logger.exception(error_message)
            raise Exception(error_message)
        
    async def _perform_qsy(self, frequency: int):
        """
        Perform QSY to given frequency
        """
        self._logger.debug(f"WebsocketClient: QSY to {frequency}")
        
        if not self.trx_status:
            # failsafe
            self._logger.debug(
                "WebsocketClient: QSY API request handler - TRX status not ready, nothing to do"
            )
            return
        
        # actual qsy code
        cmd = self._omnirig_helper.get_frequency_set_command_for_currently_active_vfo(
            trx_status=self.trx_status
        )
        if not cmd:
            self._logger.info(
                "ApiServerTask: QSY API request handler - TRX status not ready "
                "or command for setting frequency not supported, nothing to do"
            )
            return
        
        success = await self._omnirig_command_executor.execute_write_command(
            cmd=cmd,
            value=frequency,
            reply_timeout_secs=float(self._config[CFG_KEY_RADIO_REPLY_TIMEOUT]),
        )
        
        if success:
            self._logger.debug(f"WebsocketClient: QSY to {frequency} successful")
        else:
            self._logger.debug(f"WebsocketClient: QSY to {frequency} failed")
    
    def stop(self):
        """
        Stop the running task
        """
        self._message_broker.unsubscribe(topic=TOPIC_TRX_STATUS, agent=self._queue)
        
        # close only in case websocket client was started
        if self._ws_client:
            self._ws_client.close()
            
        self._is_running = False