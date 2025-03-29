import asyncio

from application.config_manager import ConfigManager
from application.constants import (
    CFG_KEY_RADIO_POLLING_INTERVAL,
    CFG_KEY_RADIO_REPLY_TIMEOUT,
    TOPIC_TRX_STATUS,
)
from helpers.logger import Logger
from machine import UART

from helpers.omnirig_helper import OmnirigHelper
from lib.asyncio.broker import Broker
from lib.omnirig import (
    TrxStatus,
    OmnirigCommandExecutor,
)


class RigReadUartTask:
    
    def __init__(
        self,
        logger: Logger,
        config_manager: ConfigManager,
        message_broker: Broker,
        omnirig_helper: OmnirigHelper,
        omnirig_command_executor: OmnirigCommandExecutor,
    ):
        self._logger = logger
        self._message_broker = message_broker
        self._config = config_manager.get_config()
        
        self._commands_to_execute = omnirig_helper.get_default_status_commands_of_interest()
        self._status_values_supported_by_trx = omnirig_helper.get_status_values_supported_by_trx()
        
        self._omnirig_command_executor = omnirig_command_executor
        self._is_running = True
    
    async def run(self):
        radio_polling_interval_ms = int(
            float(self._config.get(CFG_KEY_RADIO_POLLING_INTERVAL)) * 1000
        )
        
        while self._is_running:
            try:
                trx_status = await self._read_trx_status()
                self._message_broker.publish(topic=TOPIC_TRX_STATUS, message=trx_status)
            except Exception as e:
                self._logger.exception(f"{type(e)}:{str(e)}")
                
            await asyncio.sleep_ms(radio_polling_interval_ms)
            
    def stop(self):
        """
        Stop the running task
        """
        self._is_running = False
    
    async def _read_trx_status(self):
        """
        Execute commands to get status data from TRX
        """
        results = {}
        for cmd in self._commands_to_execute:
            cmd_results = await self._omnirig_command_executor.execute_values_read_command(
                cmd=cmd,
                reply_timeout_secs=float(self._config[CFG_KEY_RADIO_REPLY_TIMEOUT]),
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
            status_values_supported_by_trx = self._status_values_supported_by_trx,
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
