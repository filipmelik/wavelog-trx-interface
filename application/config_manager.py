import os
import json
from application.constants import (
    CONFIG_FILE_PATH,
    CFG_KEY_WIFI_NAME,
    CFG_KEY_WIFI_PASS,
    CFG_KEY_WAVELOG_API_URL,
    CFG_KEY_WAVELOG_API_KEY,
    CFG_KEY_WAVELOG_API_CALL_TIMEOUT,
    CFG_KEY_WAVELOG_API_CALL_INTERVAL,
    CFG_KEY_RADIO_NAME,
    CFG_KEY_RADIO_BAUD_RATE,
    CFG_KEY_RADIO_DATA_BITS,
    CFG_KEY_RADIO_PARITY,
    CFG_KEY_RADIO_STOP_BITS,
    CFG_KEY_RADIO_DRIVER_NAME,
    CFG_KEY_RADIO_REPLY_TIMEOUT,
    CFG_KEY_RADIO_POLLING_INTERVAL,
    DEVICE_NAME,
    CFG_KEY_DNS_NAME,
)


class ConfigManager:
    
    def read_config(self) -> dict:
        """
        Read configuration from config file. In case config file not
        """
        default_values = {  # default values
            CFG_KEY_DNS_NAME: DEVICE_NAME.lower(),
            CFG_KEY_WIFI_NAME: "",
            CFG_KEY_WIFI_PASS: "",
            CFG_KEY_WAVELOG_API_URL: "",
            CFG_KEY_WAVELOG_API_KEY: "",
            CFG_KEY_WAVELOG_API_CALL_TIMEOUT: "1",
            CFG_KEY_WAVELOG_API_CALL_INTERVAL: "2",
            CFG_KEY_RADIO_NAME: "",
            CFG_KEY_RADIO_BAUD_RATE: "19200",
            CFG_KEY_RADIO_DATA_BITS: "8",
            CFG_KEY_RADIO_PARITY: "no",
            CFG_KEY_RADIO_STOP_BITS: "1",
            CFG_KEY_RADIO_DRIVER_NAME: "",
            CFG_KEY_RADIO_REPLY_TIMEOUT: "0.5",
            CFG_KEY_RADIO_POLLING_INTERVAL: "1",
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