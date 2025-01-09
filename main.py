import gc
import json
import time
import network
import ssd1306
import requests
import os
from micropython import const
from machine import UART, Pin, SoftI2C, Timer, reset
from neopixel import NeoPixel
from lib.http_server import (HTTPResponse, HTTPServer, STOP_SERVER)
from omnirig import (
    OmnirigConfigParser,
    OmnirigStatusCommand,
    OmnirigCommandExecutor,
    OmnirigValueDecoder,
    TrxStatus,
)

gc.collect()  # memory cleanup after imports

DEBUG = True # debug mode on/off - will print messages to console

DEVICE_NAME = const("WLTrxInterface")
CONFIG_FILE_NAME = const("config.json")
RADIO_DRIVER_FILE_NAME = const("radio_driver.ini")
SPLASH_SCREEN_WAIT_TIME = const(3)  # seconds
WIFI_CONNECTED_SCREEN_WAIT_TIME = const(2)  # seconds
API_HEARTBEAT_TIME = const(20)  # seconds

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
    "pmRfPower" # RF Output power
]

NO_VALUE_PLACEHOLDER = const("---")

setup_button_pin = Pin(6, Pin.IN, Pin.PULL_UP)
on_board_rgb_led_pin = Pin(48, Pin.OUT)

i2c = SoftI2C(sda=Pin(1), scl=Pin(2))
display = ssd1306.SSD1306_I2C(128, 64, i2c)
on_board_rgb_led = NeoPixel(on_board_rgb_led_pin, 1)
uart = UART(2)
value_decoder = OmnirigValueDecoder()
command_executor = OmnirigCommandExecutor(value_decoder=value_decoder, debug=DEBUG)

wifi_station_interface = network.WLAN(network.WLAN.IF_STA)
wifi_ap_interface = network.WLAN(network.WLAN.IF_AP)
setup_http_server = HTTPServer(port=80, timeout=5)

commands_to_execute = None
status_values_supported_by_trx = None
is_setup_mode_active = False
force_reboot = False
cfg = None
trx_status_read_timer: Timer = None
trx_status_read_timer_ticked = False
trx_status_api_call_timer: Timer = None
trx_status_api_call_timer_ticked = False
trx_status = None
last_heartbeat_time = 0
last_reported_mode = None
last_reported_trx_tx_frequency = 0
last_reported_trx_rx_frequency = 0
last_reported_rf_power = None


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
    rf_power: int,
):
    gc.collect()  # free up memory before POST, as it is apparently resource heavy
    
    payload = {
        'mode_rx': mode,
        'mode': mode,
        'frequency_rx': str(rx_freq),
        'key': config[CFG_KEY_WAVELOG_API_KEY],
        'power': None if rf_power is None else rf_power,
        'frequency': str(tx_freq),
        'radio': config[CFG_KEY_RADIO_NAME],
    }
    timeout = float(config[CFG_KEY_WAVELOG_API_CALL_TIMEOUT])
    url = config[CFG_KEY_WAVELOG_API_URL]
    r = requests.post(url, json=payload, timeout=timeout)
    debug_print(r.text)
    r.close()

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
    power_string = f"{trx_status.rf_power} W" if trx_status.rf_power else NO_VALUE_PLACEHOLDER
    
    wlan_strength = wlan.status("rssi")
    if wlan_strength > -70:
        wlan_human_readable = f"Good ({wlan_strength})"
    elif wlan_strength > -80 and wlan_strength <= -70:
        wlan_human_readable = f"Fair ({wlan_strength})"
    else:
        wlan_human_readable = f"Poor ({wlan_strength})"
    
    display.fill(0)
    display.text(f'RX f: {rx_freq_string}', 0, 0, 1)
    display.text(f'TX f: {tx_freq_string}', 0, 12, 1)
    display.text(f'Mode: {mode_string}', 0, 24, 1)
    display.text(f'Power: {power_string}', 0, 36, 1)
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

def display_wifi_connected_message(display):
    display.fill(0)
    display.text("Wifi connected!", 0, 0, 1)
    display.show()
    
def display_data_saved_message(display):
    display.fill(0)
    display.text("Config saved!", 0, 0, 1)
    display.text("rebooting...", 0, 24, 1)
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
    
def handle_api_call_status_led():
    if trx_status is None:
        return
    
    if radio_status_is_not_up_to_date():
        # radio status has changed and was not yet sent to API
        on_board_rgb_led[0] = (10, 10, 0) # yellow, low brightness
    else:
        # all data is up-to-date and was already sent to API
        on_board_rgb_led[0] = (0, 10, 0)  # green, low brightness
        
    on_board_rgb_led.write()

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
    from multipart_parser import PushMultipartParser, MultipartSegment, MultipartPart

    content_type = request.header.get(b"content-type").decode()
    content_length = int(request.header.get(b"content-length").decode())

    if "multipart/form-data" not in content_type:
        raise Exception(f"unexpected content-type: '{content_type}'")

    cfg = read_config()

    debug_print("Parsing received config data and updating their values")
    boundary = content_type.split("boundary=", 1)[1]
    read_chunk_size = 100
    bytes_read = 0
    radio_driver_temp_file_name = "radio_driver_file_buffer"
    radio_driver_file_buffer = open(radio_driver_temp_file_name, "wb")
    uploaded_radio_driver_file_name = None
    parser = PushMultipartParser(boundary=boundary, content_length=content_length)
    
    part = None
    while bytes_read != content_length:
        chunk = conn.recv(read_chunk_size)
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
                    if part.name == CFG_KEY_RADIO_REPLY_TIMEOUT or part.name == CFG_KEY_WAVELOG_API_CALL_TIMEOUT:
                        # replace decimal comma for point due to possible browser locale setting
                        cfg[part.name] = str(part.value.replace(",", "."))
                    else:
                        cfg[part.name] = str(part.value)
                        
                part = None  # free up the resources
    parser.close()
        
    temp_driver_file_size = os.stat(radio_driver_temp_file_name)[6]
    if temp_driver_file_size > 0:
        # rename temp file to the resulting file name when received data was not empty
        # and update relevant cfg value
        debug_print("Renaming temp radio driver file to final name")
        os.rename(radio_driver_temp_file_name, RADIO_DRIVER_FILE_NAME)
        cfg[CFG_KEY_RADIO_DRIVER_NAME] = uploaded_radio_driver_file_name.split(".ini")[0]
    else:
        debug_print("No radio driver file received - deleting temp file")
        # received no data - delete the temp file
        os.remove(radio_driver_temp_file_name)

    debug_print("Saving config values")
    save_config(config=cfg)
    debug_print("Config values saved")
    display_data_saved_message(display=display)
    time.sleep(2)
    global force_reboot
    force_reboot = True
    
    return STOP_SERVER

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
    rf_power = None
    
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
            
        # rf power
        if item == "pmRfPower":
            rf_power = int(round(val))
        
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
        rf_power=rf_power,
    )
    
def radio_driver_is_missing(config: dict) -> bool:
    # this assumes that file is in root dir
    driver_file_exists = RADIO_DRIVER_FILE_NAME in os.listdir()
    config_entry_exists = config.get(CFG_KEY_RADIO_DRIVER_NAME)
    return not driver_file_exists or not config_entry_exists

def radio_status_is_not_up_to_date() -> bool:
    """
    Compare current radio status values to the ones that were already sent to API
    and return True in case current values differ to the values that were sent to API
    """
    current_tx_frequency = trx_status.current_tx_frequency(
        status_values_supported_by_trx=status_values_supported_by_trx
    )
    current_rx_frequency = trx_status.current_rx_frequency(
        status_values_supported_by_trx=status_values_supported_by_trx
    )
    frequency_has_changed = (
        last_reported_trx_tx_frequency != current_tx_frequency
        or last_reported_trx_rx_frequency != current_rx_frequency
    )
    mode_has_changed = last_reported_mode != trx_status.mode
    rf_power_has_changed = last_reported_rf_power != trx_status.rf_power
    
    return (
        frequency_has_changed
        or mode_has_changed
        or rf_power_has_changed
    )
    
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
    display_wifi_connected_message(display=display)
    time.sleep(WIFI_CONNECTED_SCREEN_WAIT_TIME)
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
    
    if not radio_driver_is_missing(config=cfg):
        commands_to_execute = get_commands_for_execution()
        status_values_supported_by_trx = get_status_values_supported_by_trx(
            commands=commands_to_execute
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
    
gc.collect()  # memory cleanup after init

# main loop
while True:
    # force reboot handling
    if force_reboot:
        debug_print("Force rebooting")
        reset()
    
    # setup mode button handling
    if not is_setup_mode_active and setup_button_pin.value() == 0:
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
            is_power_command_supported = "pmRfPower" in status_values_supported_by_trx
            power_value_ok = (
                True if not is_power_command_supported else trx_status.rf_power is not None
            )
            heartbeat_threshold_passed = (time.time() - last_heartbeat_time) > API_HEARTBEAT_TIME
            
            if (
                current_tx_frequency
                and trx_status.mode
                and power_value_ok
                and (radio_status_is_not_up_to_date() or heartbeat_threshold_passed)
            ):
                debug_print("Sending data to wavelog")
                send_data_to_wavelog(
                    config=cfg,
                    mode=trx_status.mode,
                    tx_freq=current_tx_frequency,
                    rx_freq=current_rx_frequency,
                    rf_power=trx_status.rf_power,
                )
                last_heartbeat_time = time.time()
                last_reported_trx_tx_frequency = current_tx_frequency
                last_reported_trx_rx_frequency = current_rx_frequency
                last_reported_mode = trx_status.mode
                last_reported_rf_power = trx_status.rf_power
                debug_print("Sent!")
        except Exception as e:
            print(e)
        trx_status_api_call_timer_ticked = False
        
    # API call status LED handling
    handle_api_call_status_led()
    
    # todo restructure app to have simple main with error handling and reset as in micropython best practices
    # todo rewrite to async to support xml rpc server for cloudlog offline and bluetooth
    # todo hypothesis - mpy-cross compilation - frozen modules
    