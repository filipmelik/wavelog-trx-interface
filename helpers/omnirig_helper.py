from application.constants import RADIO_DRIVER_FILE_PATH
from helpers.logger import Logger
from lib.omnirig import OmnirigConfigParser, OmnirigStatusCommand


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
        
        self._status_commands_of_interest = self._get_status_commands_of_interest(
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
    
    def _get_status_commands_of_interest(
        self,
        values_of_interest: list,
    ) -> list:
        """
        Prepare list of STATUS (read) commands from radio driver currently
        present in the device. The list is further filtered, so only the
        commands that are providing
        """
        # read all STATUS commands from driver file
        parser = OmnirigConfigParser()
        status_command_sections = parser.extract_status_commands_sections(
            filepath=RADIO_DRIVER_FILE_PATH
        )
        commands = []
        for status_cmd_section in status_command_sections:
            cmd = OmnirigStatusCommand(status_command_data=status_cmd_section)
            commands.append(cmd)
        
        # filter out just commands that provides values we are interested in
        relevant_status_commands = []
        for cmd in commands:
            for val_of_interest in values_of_interest:
                if val_of_interest in cmd.command_values_retrieved:
                    relevant_status_commands.append(cmd)
                    break
        
        return relevant_status_commands
    
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