from micropython import const

DEFAULT_DEVICE_NAME = const("WLTrxInterface")
CONFIG_FILE_PATH = const("config.json")
RADIO_DRIVER_FILE_PATH = const("radio_driver.ini")
SETUP_FILE_PATH = const("setup_page/setup.html")

WIFI_CONNECTED_SCREEN_WAIT_TIME = const(2)  # seconds

# Config keys
CFG_KEY_USER_CALLSIGN = const("userCallsign")
CFG_KEY_STARTUP_SCREEN_WAIT_TIME = const("startupScreenWaitTime")
CFG_KEY_WIFI_NAME = const("wifiName")
CFG_KEY_WIFI_PASS = const("wifiPass")
CFG_KEY_SECONDARY_WIFI_NAME = const("wifiName2")
CFG_KEY_SECONDARY_WIFI_PASS = const("wifiPass2")
CFG_KEY_TERTIARY_WIFI_NAME = const("wifiName3")
CFG_KEY_TERTIARY_WIFI_PASS = const("wifiPass3")
CFG_KEY_WAVELOG_API_URL = const("wavelogApiUrl")
CFG_KEY_WAVELOG_API_KEY = const("wavelogApiKey")
CFG_KEY_WAVELOG_API_CALL_TIMEOUT = const("wavelogApiCallTimeout")
CFG_KEY_WAVELOG_API_CALL_HEARTBEAT_TIME = const("wavelogApiCallHeartbeatTime")
CFG_KEY_RADIO_NAME = const("radioName")
CFG_KEY_RADIO_REPLY_TIMEOUT = const("radioReplyTimeout")
CFG_KEY_RADIO_POLLING_INTERVAL = const("radioPollingInterval")
CFG_KEY_RADIO_DRIVER_NAME = const("radioDriverName")
CFG_KEY_XML_RPC_SERVER_PORT = const("xmlRpcServerPort")
CFG_KEY_GENERAL_API_SERVER_PORT = const("generalApiServerPort")
CFG_KEY_WEBSOCKET_SERVER_ENDPOINT_URL = const("websocketServerEndpointUrl")
CFG_KEY_RADIO_BLUETOOTH_NAME = const("radioBluetoothName")

# Message broker topics
TOPIC_TRX_STATUS = const("trx_status")