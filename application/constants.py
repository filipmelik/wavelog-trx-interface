from micropython import const

DEVICE_NAME = const("WLTrxInterface")
CONFIG_FILE_PATH = const("config.json")
RADIO_DRIVER_FILE_PATH = const("radio_driver.ini")
SETUP_FILE_PATH = const("setup.html")

SPLASH_SCREEN_WAIT_TIME = const(3)  # seconds
WIFI_CONNECTED_SCREEN_WAIT_TIME = const(2)  # seconds

API_HEARTBEAT_TIME = const(20)  # seconds

# Config keys
CFG_KEY_DNS_NAME = const("dnsName")
CFG_KEY_WIFI_NAME = const("wifiName")
CFG_KEY_WIFI_PASS = const("wifiPass")
CFG_KEY_WAVELOG_API_URL = const("wavelogApiUrl")
CFG_KEY_WAVELOG_API_KEY = const("wavelogApiKey")
CFG_KEY_WAVELOG_API_CALL_TIMEOUT = const("wavelogApiCallTimeout")
CFG_KEY_WAVELOG_API_CALL_INTERVAL= const("wavelogApiCallInterval")
CFG_KEY_RADIO_NAME = const("radioName")
CFG_KEY_RADIO_BAUD_RATE = const("radioBaudRate")
CFG_KEY_RADIO_DATA_BITS = const("radioDataBits")
CFG_KEY_RADIO_PARITY = const("radioParity")
CFG_KEY_RADIO_STOP_BITS = const("radioStopBits")
CFG_KEY_RADIO_REPLY_TIMEOUT = const("radioReplyTimeout")
CFG_KEY_RADIO_POLLING_INTERVAL = const("radioPollingInterval")
CFG_KEY_RADIO_DRIVER_NAME = const("radioDriverName")

# Message broker topics
TOPIC_TRX_STATUS = const("trx_status")