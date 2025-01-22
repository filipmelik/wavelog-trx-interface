import asyncio

import network

from application.config_manager import ConfigManager
from application.constants import CFG_KEY_WIFI_PASS, CFG_KEY_WIFI_NAME
from helpers.display_helper import DisplayHelper
from helpers.logger import Logger


class WifiManager:
    
    _wifi_station_interface: network.WLAN = None
    
    def __init__(
        self, logger: Logger,
        config_manager: ConfigManager,
        display: DisplayHelper,
    ):
        self._display = display
        self._config_manager = config_manager
        self._logger = logger
        
        self._wifi_access_point_interface = network.WLAN(network.WLAN.IF_AP)
        self._wifi_station_interface = network.WLAN(network.WLAN.IF_STA)
    
    
    def create_wifi_access_point(self, essid: str):
        """
        Create wi-fi access point, wait until it is ready and return its IP address
        """
        if self._wifi_station_interface.isconnected():
            self._wifi_station_interface.disconnect()
            
        self._wifi_station_interface.active(False)
        self._wifi_access_point_interface.active(True)
        self._wifi_access_point_interface.config(essid=essid)
        
        while self._wifi_access_point_interface.active() == False:
            pass  # wait for AP to become ready
        
        server_ip_address = self._wifi_access_point_interface.ifconfig()[0]
        
        return server_ip_address
    
    def setup_wifi_as_client(self):
        """
        Setup wi-fi for station mode (as a client that will connect to the router)
        """
        dhcp_hostname = self._config_manager.get_device_id()
        
        self._logger.debug(
            f"Activating wifi interface, setting to station mode "
            f"with DHCP hostname '{dhcp_hostname}'"
        )
        self._wifi_station_interface.active(True)
        self._wifi_access_point_interface.active(False)
        self._wifi_station_interface.config(dhcp_hostname=dhcp_hostname)
    
    async def connect_to_wifi_and_wait_until_connected(
        self,
        blocking_wait_for_connect: bool,
    ):
        """
        Connect to wi-fi saved in config and wait until connected
        """
        self.disconnect_wifi()
        
        config = self._config_manager.get_config()
        ssid = config[CFG_KEY_WIFI_NAME]
        password = config[CFG_KEY_WIFI_PASS]
        
        self._logger.debug(f"Connecting to wi-fi '{ssid}'")
        if not self._wifi_station_interface.isconnected():
            self._wifi_station_interface.connect(ssid, password)
            while not self._wifi_station_interface.isconnected():
                if blocking_wait_for_connect:
                    # "forcibly" stay in the loop not giving asyncio
                    #  scheduler chance to work on other running asyncio tasks
                    pass
                else:
                    # stay in the loop until connected, but let scheduler
                    # chance to work on other running asyncio tasks
                    await asyncio.sleep_ms(100)
                    
    
    def disconnect_wifi(self):
        """
        Disconnect wi-fi station (client) interface
        """
        self._wifi_station_interface.disconnect()
            
    def is_connected(self) -> bool:
        """
        Check if station (client) interface is connected to an AP (wireless router)
        """
        return self._wifi_station_interface.isconnected()
        
    def get_device_ip_address(self) -> str:
        """
        Get IP address of currently active interface
        """
        if self._wifi_station_interface.active:
            return self._wifi_station_interface.ifconfig()[0]
        
        if self._wifi_access_point_interface.active:
            return self._wifi_access_point_interface.ifconfig()[0]
    
    def get_device_ssid(self) -> str:
        """
        Get SSID of currently active interface
        """
        if self._wifi_station_interface.active:
            return self._wifi_station_interface.config('ssid')
        
        if self._wifi_access_point_interface.active:
            return self._wifi_access_point_interface.config('ssid')
        
    def get_signal_strength(self) -> int:
        """
        Get signal strength of station (client) interface
        """
        return self._wifi_station_interface.status("rssi")
    
    def display_wifi_connecting_message(self):
        """
        Display Wi-fi connecting message
        """
        config = self._config_manager.get_config()
        ssid = config[CFG_KEY_WIFI_NAME]
        
        text_rows = [
            "No wifi",
            "",
            "Connecting:",
            ssid,
        ]
        self._display.display_text(text_rows)
    
    def display_wifi_connected_message(self):
        """
        Display Wi-fi connected message
        """
        text_rows = [
            "Wifi connected!",
            "",
            "IP address: ",
            f"{self.get_device_ip_address()}"
        ]
        self._display.display_text(text_rows)