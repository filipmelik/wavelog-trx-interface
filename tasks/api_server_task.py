import lib.async_http_server as tinyweb
from application.constants import TOPIC_TRX_STATUS
from application.wifi_manager import WifiManager

from helpers.logger import Logger
from lib.asyncio.broker import Broker
from lib.asyncio.ringbuf_queue import RingbufQueue
from lib.omnirig import TrxStatus


class ApiServerTask:
    
    def __init__(
        self,
        logger: Logger,
        wifi_manager: WifiManager,
        message_broker: Broker,
    ):
        self._logger = logger
        self._wifi_manager = wifi_manager
        self._message_broker = message_broker
        
        self.trx_status: TrxStatus = None
        
    async def run_general_api_server(self):
        """
        Run the general-purpose web server so this device can be controlled externally
        """
        device_ip_address = self._wifi_manager.get_device_ip_address()
        port = 54321 # todo this should be pulled out from config
        self._logger.debug(f"Starting general API server at {device_ip_address} port {port}")
        server = tinyweb.webserver()
        server.add_route('/qsy/<frequency>', self._qsy_request_handler, methods=['GET'])
        server.run(host='0.0.0.0', port=port, loop_forever=False)
        
    async def run_trx_status_messages_subscriber(self):
        """
        Run subscriber that will read the current TRX status messages
        """
        queue = RingbufQueue(2)
        self._message_broker.subscribe(TOPIC_TRX_STATUS, queue)
        async for topic, trx_status in queue:
            self.trx_status = trx_status
        
    async def run_cloudlog_offline_xml_rpc_server(self):
        """
        Run the XML-RPC server for the "Cloudlog Offline" application
        """
        device_ip_address = self._wifi_manager.get_device_ip_address()
        port = 12345 # todo this should be pulled out from config
        self._logger.debug(
            f"Starting Cloudlog Offline XML-RPC server at {device_ip_address} port {port}"
        )
        server = tinyweb.webserver()
        server.add_route(
            url='/',
            f=self._xml_rpc_request_handler,
            methods=['POST'],
            save_headers=['Content-Length', 'Content-Type'],
        )
        server.run(host='0.0.0.0', port=port, loop_forever=False)
    
    async def _qsy_request_handler(self, request, response, frequency_string):
        """
        Server handler for triggering QSY to given frequency
        """
        self._logger.debug("ApiServerTask: Running QSY request handler")
        
        try:
            frequency = int(frequency_string)
        except ValueError:
            error_message =  f"error: invalid frequency supplied: {frequency_string}"
            self._logger.exception(error_message)
            await response.error(400, error_message)
            return
        
        self._logger.debug(f"ApiServerTask: QSY to {frequency}")
        # todo actual QSY code here
        
        response_payload = '{"result": "success"}'
        response.version = '1.1'
        response.add_header('Connection', 'close')
        response.add_header('Content-Type', 'application/json')
        response.add_header('Content-Length', len(response_payload))
        response.add_access_control_headers()
        await response._send_headers()
        await response.send(response_payload)
    
    async def _xml_rpc_request_handler(self, request, response):
        """
        Server handler for handling XML-RPC requests from Cloudlog Offline mobile app
        """
        self._logger.debug("ApiServerTask: XML-RPC Cloudlog Offline request handler")
        
        if not self.trx_status:
            self._logger.debug(
                "ApiServerTask: XML-RPC Cloudlog Offline - TRX status not ready, sending 404"
            )
            await response.error(code=404, msg="TRX status not ready")
        
        headers_with_lowercased_keys = {
            key.lower(): val for key, val in request.headers.items()
        }
        content_length = int(headers_with_lowercased_keys.get(b"content-length").decode())
        
        read_chunk_size = 20
        bytes_read = 0
        received_data = b""
        while bytes_read != content_length:
            chunk = await request.reader.read(read_chunk_size)
            bytes_read += len(chunk)
            received_data += chunk
        
        # this trick removes all whitespace characters (space, tab, newline, and so on)
        compacted_command = ''.join(received_data.decode().split())
        
        if "<methodName>rig.get_vfo</methodName>" in compacted_command:
            frequency = str(self.trx_status.current_tx_frequency())
            self._logger.debug(f"Sending reply to 'rig.get_vfo': {frequency}")
            await self._send_xml_rpc_response(response=response, content=frequency)
        elif "<methodName>rig.get_mode</methodName>" in compacted_command:
            mode = self.trx_status.mode
            self._logger.debug(f"Sending reply to 'rig.get_mode': {mode}")
            await self._send_xml_rpc_response(response=response, content=mode)
        else:
            response.add_header('Content-Type', 'text/plain')
            await response.error(code=400, msg="Unknown method")
        
    async def _send_xml_rpc_response(self, response, content: str):
        """
        Send XML-RPC response for the Cloudlog Offline mobile app
        """
        response_data = (
            f"<methodResponse><params><param><value>"
            f"{content}"
            f"</value></param></params></methodResponse>"
        )
        response.add_header('Connection', 'close')
        response.add_header('Content-Type', 'text/xml')
        response.add_header("Content-Length", str(len(response_data)))
        await response._send_headers()
        await response.send(response_data)