import gc
import json
import time
from machine import UART, Pin, SoftI2C, Timer, reset
import network
import ssd1306
import urequests
from httpserver import (HTTPResponse, HTTPServer)
import os

from multipart_parser import PushMultipartParser, MultipartSegment, MultipartPart
from omnirig import (
    OmnirigConfigParser,
    OmnirigStatusCommand,
    OmnirigCommandExecutor,
    OmnirigValueDecoder, TrxStatus,
)

DEBUG = True # debug mode on/off - will print messages to console

DEVICE_NAME = "WLTrxInterface"
CONFIG_FILE_NAME = "config.json"
RADIO_DRIVER_FILE_NAME = "radio_driver.ini"
SPLASH_SCREEN_WAIT_TIME = 3  # seconds
WIFI_CONNECTED_SCREEN_WAIT_TIME = 2  # seconds

CFG_KEY_WIFI_NAME = "wifiName"
CFG_KEY_WIFI_PASS = "wifiPass"
CFG_KEY_WAVELOG_API_URL = "wavelogApiUrl"
CFG_KEY_WAVELOG_API_KEY = "wavelogApiKey"
CFG_KEY_WAVELOG_API_CALL_TIMEOUT = "wavelogApiCallTimeout"
CFG_KEY_WAVELOG_API_CALL_INTERVAL= "wavelogApiCallInterval"
CFG_KEY_RADIO_NAME = "radioName"
CFG_KEY_RADIO_BAUD_RATE = "radioBaudRate"
CFG_KEY_RADIO_DATA_BITS = "radioDataBits"
CFG_KEY_RADIO_PARITY = "radioParity"
CFG_KEY_RADIO_STOP_BITS = "radioStopBits"
CFG_KEY_RADIO_REPLY_TIMEOUT = "radioReplyTimeout"
CFG_KEY_RADIO_POLLING_INTERVAL = "radioPollingInterval"
CFG_KEY_RADIO_DRIVER_NAME = "radioDriverName"

VALUES_OF_INTEREST = [
    "pmFreq",  # operating frequency
    "pmFreqA",  # VFO A frequency
    "pmFreqB",  # VFO B frequency
    "pmVfoAA",  # receive and transmit on VFO A
    "pmVfoAB",  # receive on VFO A, transmit on VFO B
    "pmVfoBA",  # receive on VFO B, transmit on VFO A
    "pmVfoBB",  # receive and transmit on VFO B
    "pmVfoA",   # receive on VFO A, transmit VFO unknown
    "pmVfoB",   # receive on VFO B, transmit VFO unknown
    "pmSplitOn",  # enable split operation
    "pmSplitOff",  # disable split operation
    "pmRitOffset", # RIT offset frequency
    "pmRitOn",  # enable RIT
    "pmRitOff", # disable RIT
    "pmXitOn",  # enable XIT
    "pmXitOff", # disable XIT
    "pmCW_U",   # CW mode, upper sideband
    "pmCW_L",   # CW mode, lower sideband
    "pmSSB_U",  # USB mode
    "pmSSB_L",  # LSB mode
    "pmDIG_U",  # Digital mode (RTTY, FSK, etc.), upper sideband
    "pmDIG_L",  # Digital mode, lower sideband
    "pmAM",     # AM mode
    "pmFM",     # FM mode
]

NO_VALUE_PLACEHOLDER = "---"


setup_button = Pin(15, Pin.IN, Pin.PULL_UP)

i2c = SoftI2C(sda=Pin(4), scl=Pin(5))
display = ssd1306.SSD1306_I2C(128, 64, i2c)

uart = UART(2)
value_decoder = OmnirigValueDecoder()
command_executor = OmnirigCommandExecutor(value_decoder=value_decoder, debug=DEBUG)

wifi_station_interface = network.WLAN(network.WLAN.IF_STA)
wifi_ap_interface = network.WLAN(network.WLAN.IF_AP)
setup_http_server = HTTPServer(port=80, timeout=5)

commands_to_execute = None
status_values_supported_by_trx = None
is_setup_mode_active = False
cfg = None
trx_status_read_timer: Timer = None
trx_status_read_timer_ticked = False
trx_status_api_call_timer: Timer = None
trx_status_api_call_timer_ticked = False
trx_status = None
last_reported_trx_tx_frequency = 0
last_reported_trx_rx_frequency = 0


def debug_print(value):
    if DEBUG:
        print(f"DEBUG: {value}")

def trx_status_read_timer_tick(timer):
    global trx_status_read_timer_ticked
    trx_status_read_timer_ticked = True
    
def trx_status_api_call_timer_tick(timer):
    global trx_status_api_call_timer_ticked
    trx_status_api_call_timer_ticked = True

def send_data_to_wavelog(
    config: dict,
    mode: str,
    tx_freq: int,
    rx_freq: int,
):
    payload = {
        'mode_rx': mode,
        'mode': mode,
        'frequency_rx': str(rx_freq),
        'key': config[CFG_KEY_WAVELOG_API_KEY],
        'power': None,
        'frequency': str(tx_freq),
        'radio': config[CFG_KEY_RADIO_NAME],
    }
    timeout = float(config[CFG_KEY_WAVELOG_API_CALL_TIMEOUT])
    url = config[CFG_KEY_WAVELOG_API_URL]
    r = urequests.post(url, json=payload, timeout=timeout)
    r.close()
    
    global last_reported_trx_tx_frequency
    last_reported_trx_tx_frequency = tx_freq

def do_wifi_connect(wlan: network.WLAN, ssid: str, password: str):
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            pass

def display_status(trx_status: TrxStatus, trx_supported_values: set, display, wlan):
    current_tx_frequency = trx_status.current_tx_frequency(
        status_values_supported_by_trx=trx_supported_values
    )
    current_rx_frequency = trx_status.current_rx_frequency(
        status_values_supported_by_trx=trx_supported_values
    )

    if not current_tx_frequency:
        tx_freq_string = NO_VALUE_PLACEHOLDER
    else:
        tx_f = current_tx_frequency / 1000000
        tx_freq_string = f"{tx_f:.6f}"
        
    if not current_rx_frequency:
        rx_freq_string = NO_VALUE_PLACEHOLDER
    else:
        rx_f = current_rx_frequency / 1000000
        rx_freq_string = f"{rx_f:.6f}"
        

    mode_string = trx_status.mode if trx_status.mode is not "" else NO_VALUE_PLACEHOLDER
    
    wlan_strength = wlan.status("rssi")
    if wlan_strength > -50:
        wlan_human_readable = f"Good ({wlan_strength})"
    elif wlan_strength > -60 and wlan_strength <= -50:
        wlan_human_readable = f"Fair ({wlan_strength})"
    else:
        wlan_human_readable = f"Poor ({wlan_strength})"
        
    if last_reported_trx_tx_frequency == current_tx_frequency:
        api_success_flag = "X"
    else:
        api_success_flag = " "
    
    display.fill(0)
    display.text(f'RX f: {rx_freq_string}', 0, 0, 1)
    display.text(f'TX f: {tx_freq_string}', 0, 12, 1)
    display.text(f'Mode: {mode_string}', 0, 24, 1)
    display.text(f'API call: ({api_success_flag})', 0, 36, 1)
    display.text(f'Wifi: {wlan_human_readable}', 0, 48, 1)
    display.show()

def display_setup_mode_active_message(display, ip: str, ssid: str):
    display.fill(0)
    display.text("   SETUP MODE", 0, 0, 1)
    display.text("Connect to WiFi:", 0, 12, 1)
    display.text(ssid, 0, 24, 1)
    display.text("Open in browser:", 0, 36, 1)
    display.text(str(ip), 0, 48, 1)
    display.show()

def display_wifi_connecting_message(display, ssid: str):
    display.fill(0)
    display.text("Wifi not connected", 0, 0, 1)
    display.text("", 0, 12, 1)
    display.text("Connecting to:", 0, 24, 1)
    display.text(ssid, 0, 36, 1)
    display.show()

def display_wifi_connected_message(display, ssid: str):
    display.fill(0)
    display.text("Wifi connected!", 0, 0, 1)
    display.show()
    
def display_data_saved_message(display):
    display.fill(0)
    display.text("Config saved!", 0, 0, 1)
    display.text("Please reboot", 0, 24, 1)
    display.text("the device", 0, 36, 1)
    display.show()
    
def display_splash_screen(display, config: dict):
    uart_baudrate = int(cfg.get(CFG_KEY_RADIO_BAUD_RATE))
    uart_bits = int(cfg.get(CFG_KEY_RADIO_DATA_BITS))
    uart_stop_bits = int(cfg.get(CFG_KEY_RADIO_STOP_BITS))
    uart_parity = cfg.get(CFG_KEY_RADIO_PARITY)
    
    if uart_parity == 'odd':
        parity = 'O'
    elif uart_parity == 'even':
        parity = 'E'
    else:
        parity = 'N'
    
    display.fill(0)
    display.text(DEVICE_NAME, 0, 0, 1)
    display.text("", 0, 12, 1)
    display.text(f"Radio: {config.get(CFG_KEY_RADIO_DRIVER_NAME)}", 0, 24, 1)
    display.text(f"Wifi: {config.get(CFG_KEY_WIFI_NAME)}", 0, 36, 1)
    display.text(f"UART: {uart_baudrate}-{uart_bits}{parity}{uart_stop_bits}", 0, 48, 1)
    display.show()
    
def display_wifi_connecting_screen(display, config: dict):
    display.fill(0)
    display.text("No WiFi", 0, 0, 1)
    display.text("", 0, 12, 1)
    display.text(f"Reconnecting to:", 0, 24, 1)
    display.text("", 0, 36, 1)
    display.text(str(config.get(CFG_KEY_WIFI_NAME)), 0, 48, 1)
    display.show()

def display_radio_driver_missing_message(display):
    display.fill(0)
    display.text("No radio driver", 0, 0, 1)
    display.text("Open setup", 0, 24, 1)
    display.text("and upload", 0, 36, 1)
    display.text("radio driver", 0, 48, 1)
    display.show()

def config_file_exists() -> bool:
    # this assumes that file is in root dir
    return CONFIG_FILE_NAME in os.listdir()

def read_config() -> dict:
    cfg = {  # defaults
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
    if config_file_exists():
        with open(CONFIG_FILE_NAME, "rb") as fp:
            cfg_file_content = fp.read()
            cfg_from_file = json.loads(cfg_file_content)
            cfg.update(cfg_from_file) 
    
    return cfg

def save_config(config: dict):
    serialized = json.dumps(config)
    f = open(CONFIG_FILE_NAME, "w")
    f.write(serialized)
    f.close()

@setup_http_server.route("GET", "/")
def setup_page_handler(conn, request):
    response = HTTPResponse(200, "text/html")
    response.send(conn)
    with open("setup.html", "r") as fp:
        setup_html = fp.read()
        
        cfg = read_config()
        # fix the value of radioDriverName so it is not empty string in on the setup page
        if not cfg.get(CFG_KEY_RADIO_DRIVER_NAME):
            cfg[CFG_KEY_RADIO_DRIVER_NAME] = "None"
            
        # replace variable placeholders in html with actual config values
        for key, val in cfg.items():
            setup_html = setup_html.replace(f"{{{{{key}}}}}", str(val))
        
        conn.write(setup_html)

@setup_http_server.route("POST", "/save")
def save_cfg_handler(conn, request):
    content_type = request.header.get(b"content-type").decode()
    content_length = int(request.header.get(b"content-length").decode())
    
    if "multipart/form-data" not in content_type:
        raise Exception(f"unexpected content-type: '{content_type}'")
    
    debug_print("Parsing received config data")
    boundary = content_type.split("boundary=", 1)[1]
    chunk_size = 100
    bytes_read = 0
    multipart_parts = []
    with PushMultipartParser(boundary=boundary, content_length=content_length) as parser:
        part = None
        while bytes_read != content_length:
            chunk = conn.recv(chunk_size)
            bytes_read += len(chunk)
            
            for segment in parser.parse(chunk):
                if isinstance(segment, MultipartSegment):  # Start of new part
                    part = MultipartPart(segment=segment)
                elif segment:  # Non-empty bytearray
                    part._write(segment)
                else:  # None
                    part._mark_complete()
                    multipart_parts.append(part)
                    part = None
        parser.close()
    
    debug_print("Updating config values")
    cfg = read_config()
    for p in multipart_parts:
        if p.name == "radioDriver" and p.filename and p.value:
            f = open(RADIO_DRIVER_FILE_NAME, "w")
            f.write(p.value)
            f.close()
            cfg[CFG_KEY_RADIO_DRIVER_NAME] = p.filename.split(".ini")[0]
        else:
            if p.name == CFG_KEY_RADIO_REPLY_TIMEOUT or p.name == CFG_KEY_WAVELOG_API_CALL_TIMEOUT:
                # replace decimal comma for point due to possible browser locale setting
                cfg[p.name] = str(p.value.replace(",","."))
            else:
                cfg[p.name] = str(p.value)
    
    debug_print("Saving config values")
    save_config(config=cfg)
    debug_print("Config values saved")
    display_data_saved_message(display=display)


@setup_http_server.route("GET", "/reboot")
def reboot_handler(conn, request):
    reset() # reset the ESP32
    
def get_commands_for_execution():
    # read all STATUS commands from driver file
    parser = OmnirigConfigParser()
    sections = parser.extract_status_commands_sections(filepath=RADIO_DRIVER_FILE_NAME)
    commands = []
    for status_cmd_section in sections:
        cmd = OmnirigStatusCommand(status_command_data=status_cmd_section)
        commands.append(cmd)
    
    # filter out just commands that provides values we are interested in
    relevant_commands = []
    for cmd in commands:
        for val_of_interest in VALUES_OF_INTEREST:
            if val_of_interest in cmd.command_values_retrieved:
                relevant_commands.append(cmd)
                break
    
    return relevant_commands

def get_status_values_supported_by_trx(commands: list) -> set:
    """Get status values supported by TRX from provided commands"""
    values = set()
    for cmd in commands:
        for val_name in cmd.command_values_retrieved:
            values.add(val_name)
    return values

def read_trx_status():
    """Execute commands to get status data from TRX"""
    results = {}
    for cmd in commands_to_execute:
        cmd_results = command_executor.execute_status_command(
            cmd=cmd,
            reply_timeout_secs=float(cfg[CFG_KEY_RADIO_REPLY_TIMEOUT]),
            uart=uart
        )
        if not cmd_results:
            continue
        else:
            results.update(cmd_results)
    
    mode = ""
    active_vfo = ""
    split_enabled = False
    rit_enabled = False
    xit_enabled = False
    freq = None
    freq_a = None
    freq_b = None
    rit_offset_freq = None
    
    for item, val in results.items():
        # mode
        if (item == "pmCW_U" and val == True) or (item == "pmCW_L" and val == True):
            mode = "CW"
        if item == "pmSSB_U" and val == True:
            mode = "USB"
        if item == "pmSSB_L" and val == True:
            mode = "LSB"
        if (item == "pmDIG_U" and val == True) or (item == "pmDIG_L" and val == True):
            mode = "DATA"
        if item == "pmAM" and val == True:
            mode = "AM"
        if item == "pmFM" and val == True:
            mode = "FM"
        
        # split
        if item == "pmSplitOn" and val == True:
            split_enabled = True
            
        # rit
        if item == "pmRitOn" and val == True:
            rit_enabled = True
        
        # xit
        if item == "pmXitOn" and val == True:
            xit_enabled = True
        
        # frequency
        if item == "pmFreq":
            freq = int(val)
        if item == "pmFreqA":
            freq_a = int(val)
        if item == "pmFreqB":
            freq_b = int(val)
        
        # rit offset frequency
        if item == "pmRitOffset":
            rit_offset_freq = int(val)
            
        # active vfo
        if item == "pmVfoAA" and val == True:
            active_vfo = "pmVfoAA"
        if item == "pmVfoAB" and val == True:
            active_vfo = "pmVfoAB"
        if item == "pmVfoBA" and val == True:
            active_vfo = "pmVfoBA"
        if item == "pmVfoBB" and val == True:
            active_vfo = "pmVfoBB"
        if item == "pmVfoA" and val == True:
            active_vfo = "pmVfoA"
        if item == "pmVfoB" and val == True:
            active_vfo = "pmVfoB"
    
    return TrxStatus(
        mode=mode,
        freq=freq,
        freq_a=freq_a,
        freq_b=freq_b,
        split_enabled=split_enabled,
        rit_enabled=rit_enabled,
        xit_enabled=xit_enabled,
        rit_offset_freq=rit_offset_freq,
        active_vfo=active_vfo,
    )
        
def radio_driver_is_missing(config: dict) -> bool:
    return not config.get(CFG_KEY_RADIO_DRIVER_NAME)
    
    
# init code here
if config_file_exists():
    # device has already went through the "initial" setup, do the normal init
    cfg = read_config()
    display_splash_screen(display=display, config=cfg)
    time.sleep(SPLASH_SCREEN_WAIT_TIME)
    is_setup_mode_active = False
    wifi_ap_interface.active(False)
    wifi_station_interface.active(True)
    wifi_station_interface.config(dhcp_hostname=DEVICE_NAME.lower())
    display_wifi_connecting_screen(display=display, config=cfg)
    do_wifi_connect(
        wlan=wifi_station_interface,
        ssid=cfg[CFG_KEY_WIFI_NAME],
        password=cfg[CFG_KEY_WIFI_PASS],
    )
    display_wifi_connected_message(display=display, ssid=cfg[CFG_KEY_WIFI_NAME])
    time.sleep(WIFI_CONNECTED_SCREEN_WAIT_TIME)
    commands_to_execute = get_commands_for_execution()
    status_values_supported_by_trx = get_status_values_supported_by_trx(
        commands=commands_to_execute
    )
    uart_baudrate = int(cfg.get(CFG_KEY_RADIO_BAUD_RATE))
    uart_bits = int(cfg.get(CFG_KEY_RADIO_DATA_BITS))
    uart_stop_bits = int(cfg.get(CFG_KEY_RADIO_STOP_BITS))
    uart_parity = cfg.get(CFG_KEY_RADIO_PARITY)

    if uart_parity == 'odd':
        parity = 1
    elif uart_parity == 'even':
        parity = 0
    else:
        parity = None

    uart.init(
        baudrate=uart_baudrate,
        bits=uart_bits,
        parity=parity,
        stop=uart_stop_bits,
    )
    trx_status_read_timer = Timer(0)
    radio_polling_frequency = 1 / float(cfg[CFG_KEY_RADIO_POLLING_INTERVAL])
    trx_status_read_timer.init(
        mode=Timer.PERIODIC,
        freq=radio_polling_frequency,
        callback=trx_status_read_timer_tick,
    )
    
    trx_status_api_call_timer = Timer(1)
    api_call_frequency = 1 / float(cfg[CFG_KEY_WAVELOG_API_CALL_INTERVAL])
    trx_status_api_call_timer.init(
        mode=Timer.PERIODIC,
        freq=api_call_frequency,
        callback=trx_status_api_call_timer_tick,
    )
else:
    # this is executed until user setup the device for the first time
    is_setup_mode_active = True
    wifi_station_interface.active(False)
    wifi_ap_interface.active(True)
    wifi_ap_interface.config(essid=DEVICE_NAME)
    while wifi_ap_interface.active() == False:
        pass # wait for AP to become ready
    server_ip_address = wifi_ap_interface.ifconfig()[0] 
    
    display_setup_mode_active_message(
        display=display,
        ip=server_ip_address,
        ssid=DEVICE_NAME,
    )
    setup_http_server.start()

# main loop
while True:
    # setup mode button handling
    if setup_button.value() == 0:
        if not is_setup_mode_active:
            ip_address = wifi_station_interface.ifconfig()[0]
            display_setup_mode_active_message(
                display=display,
                ip=ip_address,
                ssid=cfg.get(CFG_KEY_WIFI_NAME),
            )
            trx_status_read_timer.deinit()
            is_setup_mode_active = True
            debug_print("Setup mode is active")
            setup_http_server.start()  # this is blocking call
        else:
            debug_print("Rebooting")
            reset()  # reset the ESP32
    
    # ensure radio driver is available
    if radio_driver_is_missing(config=cfg):
        display_radio_driver_missing_message(display=display)
        continue
    
    # ensure wifi is connected
    if not wifi_station_interface.isconnected():
        display_wifi_connecting_screen(display=display, config=cfg)
        do_wifi_connect(
            wlan=wifi_station_interface,
            ssid=cfg[CFG_KEY_WIFI_NAME],
            password=cfg[CFG_KEY_WIFI_PASS],
        )
        continue
    
    # read TRX status
    if trx_status_read_timer_ticked and not is_setup_mode_active:
        try:
            trx_status = read_trx_status()
            display_status(
                trx_status=trx_status,
                trx_supported_values=status_values_supported_by_trx,
                display=display,
                wlan=wifi_station_interface
            )
        except Exception as e:
            print(e)
        trx_status_read_timer_ticked = False
    
    # report TRX status to API
    if trx_status_api_call_timer_ticked and not is_setup_mode_active:
        try:
            current_tx_frequency = trx_status.current_tx_frequency(
                status_values_supported_by_trx=status_values_supported_by_trx
            )
            current_rx_frequency = trx_status.current_rx_frequency(
                status_values_supported_by_trx=status_values_supported_by_trx
            )
            if current_tx_frequency and last_reported_trx_tx_frequency != current_tx_frequency:
                # todo OR if 20 secs elapsed - to keep wavelog knowing the radio is alive???
                debug_print("Sending data to wavelog")
                send_data_to_wavelog(
                    config=cfg,
                    mode=trx_status.mode,
                    tx_freq=current_tx_frequency,
                    rx_freq=current_rx_frequency,
                )
                debug_print("Sent!")
        except Exception as e:
            print(e)
        trx_status_api_call_timer_ticked = False
        
    #todo hypothesis: test get request - does it also timeout?
    #todo hypothesis: LCD jamming?
    #todo hypothesis: try to flash old version of program to debug timeouts?
    
    gc.collect() # this needs to stay
