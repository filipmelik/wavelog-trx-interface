import os
import lib.async_http_server as tinyweb
import time

from machine import reset
from application.constants import (
    SETUP_FILE_PATH,
    CFG_KEY_RADIO_DRIVER_NAME,
    CFG_KEY_RADIO_REPLY_TIMEOUT,
    CFG_KEY_WAVELOG_API_CALL_TIMEOUT,
    RADIO_DRIVER_FILE_PATH,
    CFG_KEY_RADIO_POLLING_INTERVAL,
)
from application.config_manager import ConfigManager
from helpers.display_helper import DisplayHelper
from helpers.logger import Logger
from helpers.status_led_helper import StatusLedHelper


class SetupManager:
    """
    This class encapsulates functionality needed for configuring the device
    for cases of:
    1) First launch of the device, when configuration was not yet performed
    2) When user wants to change already existing configuration parameters
    """
    
    def __init__(
        self,
        logger: Logger,
        display: DisplayHelper,
        config_manager: ConfigManager,
        status_led_helper: StatusLedHelper,
    ):
        self._logger = logger
        self._display = display
        self._config_manager = config_manager
        self._status_led_helper = status_led_helper
        
    async def run_setup_server(self, device_ip_address: str):
        """
        Run the setup web server
        """
        self._logger.debug(f"Starting setup web server at {device_ip_address}")
        self._status_led_helper.signal_setup_mode_active()
        server = tinyweb.webserver()
        server.add_route('/', self._setup_page_handler, methods=['GET'])
        server.add_route(
            '/save',
            self._save_config_handler,
            methods=['POST'],
            save_headers=['Content-Length', 'Content-Type'],
        )
        server.add_route('/reboot', self._reboot_handler, methods=['GET'])
        server.run(host='0.0.0.0', port=80, loop_forever=True)
        
    def display_setup_mode_active_message(
        self,
        is_ap_setup_mode: bool,
        is_connected_to_wifi: bool,
        setup_server_ip_address: str,
        ssid: str,
    ):
        """
        Display on screen that setup mode is active along with info how to access it
        """
        if is_ap_setup_mode:
            screen_title = " AP SETUP MODE"
            text_rows = [
                screen_title,
                "Connect to WiFi:",
                ssid,
                "Open in browser:",
                setup_server_ip_address,
            ]
        else:
            screen_title = "   SETUP MODE"
            if is_connected_to_wifi:
                text_rows = [
                    screen_title,
                    "Connect to WiFi:",
                    ssid,
                    "Open in browser:",
                    setup_server_ip_address,
                ]
            else:
                text_rows = [
                    screen_title,
                    "No WiFi",
                    "Long press to",
                    "launch AP Setup ",
                    "mode",
                ]
            
        self._display.display_text(text_rows)
    
    async def _setup_page_handler(self, request, response):
        """
        Server handler for serving setup HTML page
        """
        self._logger.debug("Running setup page handler")
        await response.start_html()
        
        with open(SETUP_FILE_PATH, "r") as fp:
            setup_html = fp.read()

        config = self._config_manager.get_config()
        
        # fix the value of radioDriverName so it is not empty string in on the setup page
        if not config.get(CFG_KEY_RADIO_DRIVER_NAME):
            config[CFG_KEY_RADIO_DRIVER_NAME] = "None"

        # replace variable placeholders in setup html file with actual config values
        for key, val in config.items():
            setup_html = setup_html.replace(f"{{{{{key}}}}}", str(val))
        
        await response.send(setup_html)
        
    async def _save_config_handler(self, request, response):
        """
        Server handler for saving values entered on setup HTML page
        """
        self._logger.debug("Running config save handler")
        headers_with_lowercased_keys = {
            key.lower(): val for key, val in request.headers.items()
        }
        content_type = headers_with_lowercased_keys.get(b"content-type").decode()
        content_length = int(headers_with_lowercased_keys.get(b"content-length").decode())
        
        if "multipart/form-data" not in content_type:
            message = f"unexpected content-type: '{content_type}'"
            self._logger.exception(message)
            raise Exception(message)
        
        from lib.multipart_parser import PushMultipartParser, MultipartSegment, MultipartPart
        
        self._logger.debug("Parsing received config data and updating their values")
        read_chunk_size = 100
        bytes_read = 0
        radio_driver_temp_file_name = "radio_driver_file_buffer.tmp"
        radio_driver_file_buffer = open(radio_driver_temp_file_name, "wb")
        uploaded_radio_driver_file_name = None
        config = self._config_manager.get_config()
        boundary = content_type.split("boundary=", 1)[1]
        parser = PushMultipartParser(boundary=boundary, content_length=content_length)
        
        part = None
        while bytes_read != content_length:
            chunk = await request.reader.read(read_chunk_size)
            bytes_read += len(chunk)
            
            for segment in parser.parse(chunk):
                if isinstance(segment, MultipartSegment):
                    # Detected start of new multipart-part
                    part = MultipartPart(segment=segment)
                    if part.name == "radioDriver" and part.filename:
                        part._set_alternative_buffer(radio_driver_file_buffer)
                elif segment:
                    # Non-empty bytearray - append to current "in-progress" part
                    part._write(segment)
                else:
                    # None - signalizes end of the multipart-part
                    if part.name == "radioDriver" and part.filename:
                        # finalize reading of radio driver file
                        radio_driver_file_buffer.close()
                        uploaded_radio_driver_file_name = part.filename
                    else:
                        # finalize reading of config parameter parts and update relevant cfg values
                        part._mark_complete()
                        if (
                            part.name == CFG_KEY_RADIO_REPLY_TIMEOUT
                            or part.name == CFG_KEY_RADIO_POLLING_INTERVAL
                            or part.name == CFG_KEY_WAVELOG_API_CALL_TIMEOUT
                        ):
                            # replace decimal comma for point due to possible browser locale setting
                            config[part.name] = str(part.value.replace(",", ".")).strip()
                        else:
                            config[part.name] = str(part.value).strip()
                    
                    part = None  # free up the resources
        parser.close()
        
        temp_driver_file_size = os.stat(radio_driver_temp_file_name)[6]
        if temp_driver_file_size > 0:
            # rename temp file to the resulting file name when received data was not empty
            # and update relevant cfg value
            self._logger.debug(f"Radio driver was uploaded: {uploaded_radio_driver_file_name}")
            self._logger.debug("Renaming temp radio driver file to final name")
            os.rename(radio_driver_temp_file_name, RADIO_DRIVER_FILE_PATH)
            config[CFG_KEY_RADIO_DRIVER_NAME] = uploaded_radio_driver_file_name.split(".ini")[0]
        else:
            self._logger.debug(
                "No radio driver file received - leaving the old driver "
                "intact and deleting temp file"
            )
            # received no data - delete the temp file
            os.remove(radio_driver_temp_file_name)
        
        self._logger.debug("Saving config values")
        self._config_manager.save_config(config=config)
        self._logger.debug("Config values saved")
        self._display_setup_complete_message()
        
        await response.redirect("/reboot")
        
    async def _reboot_handler(self, request, response):
        """
        Server handler for issuing device reboot
        """
        self._logger.debug("Running reboot handler")
        
        await response.start_html()
        await response.send("<h1>Config succesfully saved</h1><p>The device will now reboot</p>")
        await response.writer.aclose() # manually close the writer the forcefully send the response
        
        time.sleep(2) # wait a little so the system has time to send a response and then reboot
        self._logger.debug("Issuing hard device reboot")
        reset()
        
    def _display_setup_complete_message(self):
        """
        Display info on screen that config values were successfully stored,
        and that we are going to restart the device
        """
        text_rows = [
            "Config saved!",
            "",
            "rebooting...",
        ]
        self._display.display_text(text_rows)
