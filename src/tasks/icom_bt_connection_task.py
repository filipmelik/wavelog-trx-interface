import asyncio
import binascii

import aioble
import bluetooth

from application.config_manager import ConfigManager
from application.constants import CFG_KEY_RADIO_BLUETOOTH_NAME
from helpers.logger import Logger

from application.icom_bt_connection_manager import IcomBTConnectionManager

_BT_DEVICE_CONNECT_TIMEOUT = 3000

ICOM_705_SERVICE_UUID = bluetooth.UUID("14cf8001-1ec2-d408-1b04-2eb270f14203")
ICOM_705_RX_TX_CHARACTERISTIC_UUID = bluetooth.UUID("14cf8002-1ec2-d408-1b04-2eb270f14203")
GATT_CLIENT_CHARACTERISTIC_CONFIGURATION_UUID = bluetooth.UUID(0x2902)
OUR_DEVICE_NAME = "IC705 WAVELOG-IF"  # Name must be exactly 16 bytes!

class IcomBTConnectionTask:
    
    def __init__(
        self,
        bt_connection_manager: IcomBTConnectionManager,
        config_manager: ConfigManager,
        logger: Logger,
    ):
        self._logger = logger
        self._bt_connection_manager = bt_connection_manager
        
        config = config_manager.get_config()
        self._icom_bt_device_name = config[CFG_KEY_RADIO_BLUETOOTH_NAME]
        
        self._is_running = True
        
    async def run(self):
        while self._is_running:
            
            if self._bt_connection_manager.bt_is_ready():
                # we are connected and have a characteristic, nothing to do
                self._logger.debug(
                    "BTConnectionTask: BT connection is established, nothing to do, sleeping..."
                )
                await asyncio.sleep_ms(5000)
                continue  # go to the beginning again
                
            self._logger.info(
                f"No connection with radio, trying to reconnect to "
                f"'{self._icom_bt_device_name}'"
            )

            try:
                self._logger.info(
                    f"Starting search for '{self._icom_bt_device_name}'"
                )
                bt_device = await self._find_icom_device()
                
                if not bt_device:
                    self._logger.info(
                        f"Device of interest not found, will try again in a moment"
                    )
                    self._bt_connection_manager.reset_device_connection()
                    self._bt_connection_manager.reset_icom_serial_characteristic()
                    self._bt_connection_manager.reset_icom_civ_access_granted()
                    await asyncio.sleep_ms(1000)
                    continue
                else:
                    self._logger.info("BT Device found, connecting...")
                    bt_connection = await bt_device.connect(
                        timeout_ms=_BT_DEVICE_CONNECT_TIMEOUT
                    )
                    self._logger.info("Connected to BT device")
                    self._bt_connection_manager.set_device_connection(connection=bt_connection)
            except Exception as e:
                self._logger.debug(
                    f"Got error '{type(e)}: {str(e)}' when connecting to BT device, "
                    f"will try again in a moment",
                )
                self._bt_connection_manager.reset_device_connection()
                self._bt_connection_manager.reset_icom_serial_characteristic()
                self._bt_connection_manager.reset_icom_civ_access_granted()
                continue
            
            try:
                # find BT service and characteristic we are interested in
                icom_uart_service = await bt_connection.service(uuid=ICOM_705_SERVICE_UUID)
                rx_tx_characteristic = await icom_uart_service.characteristic(
                    uuid=ICOM_705_RX_TX_CHARACTERISTIC_UUID
                )
                self._bt_connection_manager.set_icom_serial_characteristic(
                    characteristic=rx_tx_characteristic
                )
                
                # subscribe to BT notifications for this characteristic
                await rx_tx_characteristic.subscribe(notify=True, indicate=False)
                
                # perform the ic 705 pairing sequence
                await self._perform_pairing_sequence(
                    characteristic=rx_tx_characteristic,
                )
                self._bt_connection_manager.set_icom_civ_access_granted()
                
            except Exception as e:
                self._logger.info(
                    f"Got error when initializing BT service "
                    f"or BT characteristic or when subscribing to notifications: "
                    f"'{type(e)}: {str(e)}'"
                )
                self._bt_connection_manager.reset_device_connection()
                self._bt_connection_manager.reset_icom_serial_characteristic()
                self._bt_connection_manager.reset_icom_civ_access_granted()
                continue
                
            self._logger.info(
                f"Successfully connected and paired to {self._icom_bt_device_name}",
            )
            
    def stop(self):
        """
        Stop the running task
        """
        self._is_running = False
    
    
    async def _perform_pairing_sequence(self, characteristic):
        our_uuid_message = (
            "FEF1006130303030313130312D303030302D313030302D383030302D303038303546394233344642FD"
        )
        device_name_message = f"FEF10062{binascii.hexlify(OUR_DEVICE_NAME).decode()}FD"
        token_message = "FEF10063EE390910FD"
        
        civ_access_granted_reply = "FEF10064FD"
        
        try:
            self._logger.debug("Pairing sequence step 1: Sending 'UUID' message")
            await characteristic.write(bytes.fromhex(our_uuid_message), response=True)
            data = await characteristic.notified(timeout_ms=1000)
            self._logger.debug(f"'UUID' message reply: 0x{data.hex().upper()}")
        except Exception as e:
            raise e

        try:
            self._logger.debug("Pairing sequence step 2: Sending 'device name' message")
            await characteristic.write(bytes.fromhex(device_name_message), response=True)
            data = await characteristic.notified(timeout_ms=1000)
            self._logger.debug(f"'device name' message reply: 0x{data.hex().upper()}")
        except asyncio.TimeoutError:
            # ignore this exception, as the radio does reply to this message only until
            # it is "registered" (paired) with ic705 for the first time and then never again
            pass
        except Exception as e:
            raise e

        try:
            self._logger.debug("Pairing sequence step 3: Sending 'token' message")
            await characteristic.write(bytes.fromhex(token_message), response=True)
            data = await characteristic.notified(timeout_ms=1000)
            self._logger.debug(f"'token' message reply: 0x{data.hex().upper()}")
            if data.hex().upper() != civ_access_granted_reply:
                raise Exception(
                    f"Expected receiving CI-V access granted reply from "
                    f"radio ({civ_access_granted_reply}), but something "
                    f"different was received ({data.hex().upper()})"
                )
        except Exception as e:
            raise e
    
    
    async def _find_icom_device(self):
        """
        Scan for 5 seconds, in active mode, with very low interval/window
        (to maximise detection rate) and return BT device if found 
        """
        device_of_interest = None
        async with aioble.scan(5000, interval_us=30000, window_us=30000, active=True) as scanner:
            async for result in scanner:
                found_device_name = result.name()
                if found_device_name is None:
                    continue
                    
                self._logger.debug(f"Found device '{found_device_name}'")
                if (
                    result.name() == self._icom_bt_device_name
                    and ICOM_705_SERVICE_UUID in result.services()
                ):
                    return result.device
        return device_of_interest
        