import os
import json
from application.constants import (
    CONFIG_FILE_PATH,
    CFG_KEY_WIFI_NAME,
    CFG_KEY_WIFI_PASS,
    CFG_KEY_WAVELOG_API_URL,
    CFG_KEY_WAVELOG_API_KEY,
    CFG_KEY_WAVELOG_API_CALL_TIMEOUT,
    CFG_KEY_WAVELOG_API_CALL_HEARTBEAT_TIME,
    CFG_KEY_RADIO_NAME,
    CFG_KEY_RADIO_BAUD_RATE,
    CFG_KEY_RADIO_DATA_BITS,
    CFG_KEY_RADIO_PARITY,
    CFG_KEY_RADIO_STOP_BITS,
    CFG_KEY_RADIO_DRIVER_NAME,
    CFG_KEY_RADIO_REPLY_TIMEOUT,
    CFG_KEY_RADIO_POLLING_INTERVAL,
    CFG_KEY_USER_CALLSIGN,
    CFG_KEY_STARTUP_SCREEN_WAIT_TIME,
    CFG_KEY_XML_RPC_SERVER_PORT,
    CFG_KEY_GENERAL_API_SERVER_PORT,
    CFG_KEY_WEBSOCKET_SERVER_ENDPOINT_URL,
)


class ConfigManager:
    
    def __init__(self):
        self._config = self._read_config()
    
    def get_config(self) -> dict:
        """
        Return cached config
        """
        return self._config
    
    def _read_config(self) -> dict:
        """
        Read configuration from config file. In case config file not
        """
        default_values = {  # default values
            CFG_KEY_USER_CALLSIGN: "",
            CFG_KEY_STARTUP_SCREEN_WAIT_TIME: "3",
            CFG_KEY_WIFI_NAME: "",
            CFG_KEY_WIFI_PASS: "",
            CFG_KEY_WAVELOG_API_URL: "",
            CFG_KEY_WAVELOG_API_KEY: "",
            CFG_KEY_WAVELOG_API_CALL_TIMEOUT: "1",
            CFG_KEY_WAVELOG_API_CALL_HEARTBEAT_TIME: "30",
            CFG_KEY_RADIO_NAME: "",
            CFG_KEY_RADIO_BAUD_RATE: "19200",
            CFG_KEY_RADIO_DATA_BITS: "8",
            CFG_KEY_RADIO_PARITY: "no",
            CFG_KEY_RADIO_STOP_BITS: "1",
            CFG_KEY_RADIO_DRIVER_NAME: "",
            CFG_KEY_RADIO_REPLY_TIMEOUT: "0.5",
            CFG_KEY_RADIO_POLLING_INTERVAL: "1",
            CFG_KEY_XML_RPC_SERVER_PORT: "12345",
            CFG_KEY_GENERAL_API_SERVER_PORT: "54321",
            CFG_KEY_WEBSOCKET_SERVER_ENDPOINT_URL: "",
        }
        
        config = {}
        config.update(default_values) # populate with defaults
        
        if self.config_file_exists():
            # in case config file already exists, replace default
            # values with those saved in config file
            with open(CONFIG_FILE_PATH, "rb") as cfg_file:
                loaded_config_dict = json.loads(cfg_file.read())
                config.update(loaded_config_dict)
        
        return config
    
    def get_device_id(self) -> str:
        """
        Get device ID
        """
        callsign = self._config[CFG_KEY_USER_CALLSIGN].lower()
        radio_name = self._config[CFG_KEY_RADIO_NAME].lower()
        
        return f"{callsign}-{radio_name}"
    
    def save_config(self, config: dict):
        """
        Save given dictionary with device configuration parameters
        """
        serialized = json.dumps(config)
        f = open(CONFIG_FILE_PATH, "w")
        f.write(serialized)
        f.close()
        
    def config_file_exists(self) -> bool:
        """
        Check if config file was already created on the device
        """
        return CONFIG_FILE_PATH in os.listdir()