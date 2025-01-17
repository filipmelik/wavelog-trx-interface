from application.constants import RADIO_DRIVER_FILE_PATH
from helpers.logger import Logger
from lib.omnirig import OmnirigConfigParser, OmnirigStatusCommand, AllOmnirigCommandsRawData, OmnirigValueSetCommand, \
    TrxStatus


class OmnirigHelper:
    
    DEFAULT_STATUS_VALUES_OF_INTEREST = [
        "pmFreq",  # operating frequency
        "pmFreqA",  # VFO A frequency
        "pmFreqB",  # VFO B frequency
        "pmVfoAA",  # receive and transmit on VFO A
        "pmVfoAB",  # receive on VFO A, transmit on VFO B
        "pmVfoBA",  # receive on VFO B, transmit on VFO A
        "pmVfoBB",  # receive and transmit on VFO B
        "pmVfoA",  # receive on VFO A, transmit VFO unknown
        "pmVfoB",  # receive on VFO B, transmit VFO unknown
        "pmSplitOn",  # enable split operation
        "pmSplitOff",  # disable split operation
        "pmRitOffset",  # RIT offset frequency
        "pmRitOn",  # enable RIT
        "pmRitOff",  # disable RIT
        "pmXitOn",  # enable XIT
        "pmXitOff",  # disable XIT
        "pmCW_U",  # CW mode, upper sideband
        "pmCW_L",  # CW mode, lower sideband
        "pmSSB_U",  # USB mode
        "pmSSB_L",  # LSB mode
        "pmDIG_U",  # Digital mode (RTTY, FSK, etc.), upper sideband
        "pmDIG_L",  # Digital mode, lower sideband
        "pmAM",  # AM mode
        "pmFM",  # FM mode
        "pmRfPower",  # RF Output power
    ]
    
    def __init__(
        self,
        logger: Logger,
    ):
        self._logger = logger
        
        # read all raw commands data from driver file
        parser = OmnirigConfigParser()
        all_commands_raw_data = parser.extract_all_commands_raw_data(
            filepath=RADIO_DRIVER_FILE_PATH
        )
        
        self._value_set_commands = self._prepare_value_set_commands(
            all_commands_raw_data=all_commands_raw_data
        )
        self._status_commands_of_interest = self._get_status_commands_of_interest(
            all_commands_raw_data=all_commands_raw_data,
            values_of_interest=self.DEFAULT_STATUS_VALUES_OF_INTEREST,
        )
        self._status_values_supported_by_trx = self._get_status_values_supported_by_trx(
            status_commands=self._status_commands_of_interest,
        )
        
    def get_default_status_commands_of_interest(self) -> list:
        """
        Return cached default STATUS (read) commands of interest
        """
        return self._status_commands_of_interest
    
    def get_status_values_supported_by_trx(self) -> set:
        """
        Return cached status values of interest supported by TRX
        """
        return self._status_values_supported_by_trx
    
    def get_value_set_commands(self) -> dict:
        """
        Return cached value-set commands supported by TRX in form of dict where key is command name
        """
        return self._value_set_commands
    
    def get_frequency_set_command_for_currently_active_vfo(self, trx_status: TrxStatus):
        if not self._status_values_supported_by_trx:
            return None
        
        if not trx_status.active_vfo:
            return None
        
        if (
            "pmFreqA" in self._status_values_supported_by_trx
            and trx_status.active_vfo in ["pmVfoAA", "pmVfoBA"]
        ):
            command_name = "pmFreqA"
        elif (
            "pmFreqB" in self._status_values_supported_by_trx
            and trx_status.active_vfo in ["pmVfoAB", "pmVfoBB"]
        ):
            command_name = "pmFreqB"
        elif trx_status.active_vfo == "pmVfoA":
            command_name = "pmFreqA"
        elif trx_status.active_vfo == "pmVfoB":
            command_name = "pmFreqB"
        else:
            command_name = "pmFreq"
        
        value_set_commands = self.get_value_set_commands()

        return value_set_commands.get(command_name)
    
    def _get_status_commands_of_interest(
        self,
        all_commands_raw_data: AllOmnirigCommandsRawData,
        values_of_interest: list,
    ) -> list:
        """
        Prepare list of STATUS (read) commands from radio driver currently
        present in the device. The list is further filtered, so only the
        commands that are providing values we are interested in are returned
        """
        commands = []
        for status_cmd_data_container in all_commands_raw_data.status_commands_raw_data:
            cmd = OmnirigStatusCommand(
                command_raw_data=status_cmd_data_container.command_data
            )
            commands.append(cmd)
        
        # filter out just commands that provides values we are interested in
        relevant_status_commands = []
        for cmd in commands:
            for val_of_interest in values_of_interest:
                if val_of_interest in cmd.command_values_retrieved:
                    relevant_status_commands.append(cmd)
                    break
        
        return relevant_status_commands
    
    def _prepare_value_set_commands(
        self,
        all_commands_raw_data: AllOmnirigCommandsRawData
    ) -> dict:
        """
        Get value set commands in form of dict where key is command name
        """
        value_write_commands = {}
        
        for cmd_data_container in all_commands_raw_data.value_set_commands_raw_data:
            cmd = OmnirigValueSetCommand(
                command_name=cmd_data_container.command_name,
                command_raw_data=cmd_data_container.command_data,
            )
            value_write_commands[cmd_data_container.command_name] = cmd
        
        return value_write_commands
    
    def _get_status_values_supported_by_trx(self, status_commands: list) -> set:
        """
        Get status values supported by TRX from provided list of status commands
        """
        values = set()
        for cmd in status_commands:
            if type(cmd) is not OmnirigStatusCommand:
                err_msg = "Programming error, given command is not a OmnirigStatusCommand"
                self._logger.exception(err_msg)
                raise Exception(err_msg)
                
            for val_name in cmd.command_values_retrieved:
                values.add(val_name)
        return values