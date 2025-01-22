import asyncio
import re
import time

class TrxStatus:
    def __init__(
        self,
        status_values_supported_by_trx: set,
        mode: str,
        active_vfo: str,
        freq: int = None,
        freq_a: int = None,
        freq_b: int = None,
        split_enabled: bool = False,
        rit_enabled: bool = False,
        xit_enabled: bool = False,
        rit_offset_freq: int = None,
        rf_power: int = None,
    ):
        self._status_values_supported_by_trx = status_values_supported_by_trx
        self.mode = mode
        self.active_vfo = active_vfo
        self.freq = freq
        self.freq_a = freq_a
        self.freq_b = freq_b
        self.split_enabled = split_enabled
        self.rit_enabled = rit_enabled
        self.xit_enabled = xit_enabled
        self.rit_offset_freq = rit_offset_freq
        self.rf_power = rf_power
        
    def current_tx_frequency(self):
        if not self._status_values_supported_by_trx:
            return 0
        
        if (
            "pmFreqA" in self._status_values_supported_by_trx
            and self.active_vfo in ["pmVfoAA", "pmVfoBA"]
        ):
            tx_freq = self.freq_a
        elif (
            "pmFreqB" in self._status_values_supported_by_trx
            and self.active_vfo in ["pmVfoAB", "pmVfoBB"]
        ):
            tx_freq = self.freq_b
        elif self.active_vfo == "pmVfoA" and not self.split_enabled:
            tx_freq = self.freq_a
        elif self.active_vfo == "pmVfoA" and self.split_enabled:
            tx_freq = self.freq_b
        elif self.active_vfo == "pmVfoB" and not self.split_enabled:
            tx_freq = self.freq_b
        elif self.active_vfo == "pmVfoB" and self.split_enabled:
            tx_freq = self.freq_a
        else:
            tx_freq = self.freq

        # include XIT
        if self.xit_enabled and self.rit_offset_freq:
            tx_freq += int(self.rit_offset_freq)
        
        return tx_freq
    
    def current_rx_frequency(self):
        if not self._status_values_supported_by_trx:
            return 0
        
        if (
            "pmFreqA" in self._status_values_supported_by_trx
            and self.active_vfo in ["pmVfoA", "pmVfoAA", "pmVfoAB"]
        ):
            rx_freq = self.freq_a
        elif (
            "pmFreqB" in self._status_values_supported_by_trx
            and self.active_vfo in ["pmVfoB", "pmVfoBA", "pmVfoBB"]
        ):
            rx_freq = self.freq_b
        elif not self.split_enabled:
            rx_freq = self.freq
        else:
            rx_freq = 0
            
        # include RIT
        if self.rit_enabled and self.rit_offset_freq:
            rx_freq += int(self.rit_offset_freq)
        
        return rx_freq
    
class OmnirigBaseCommand:
    COMMAND_TYPE_READ = "READ"
    COMMAND_TYPE_WRITE = "WRITE"

    DATA_TYPE_BIN = "BIN"
    DATA_TYPE_TEXT = "TEXT"
    
    def __init__(
        self,
        command_type: str,
        command_raw_data: dict,
    ):
        self.command_type = command_type
        
        # command init - Command
        command_expression = command_raw_data.get('Command')
        if self._is_text_command_or_reply(data=command_expression):
            self.command_data_type = OmnirigBaseCommand.DATA_TYPE_TEXT
            self.command = self._get_text_between_parentheses(text=command_expression)
        else:
            self.command_data_type = OmnirigBaseCommand.DATA_TYPE_BIN
            self.command = self._remove_dots_from_bin_encoded_data(
                data=command_expression
            )
        
        # reply data init - ReplyLength and ReplyEnd
        reply_length = command_raw_data.get('ReplyLength')
        self.command_has_reply_length = (
                reply_length is not None
                and reply_length != ""
                and int(reply_length) > 0
        )
        if self.command_has_reply_length:
            self.reply_length = int(reply_length)
        
        self.reply_end = command_raw_data.get('ReplyEnd')
        self.command_has_reply_end = (
                self.reply_end is not None
                and self.reply_end != ""
        )
        self.reply_end_data_type = None
        if self.command_has_reply_end:
            self.reply_end_data_type = (
                OmnirigStatusCommand.DATA_TYPE_TEXT
                if self._is_text_command_or_reply(data=self.reply_end)
                else OmnirigStatusCommand.DATA_TYPE_BIN
            )
        
        # validate init - Validate
        self.validate_mask = None
        self.validate_bits = None
        validate_val = command_raw_data.get('Validate')
        if validate_val is not None:
            validate_parts = validate_val.split("|")
            if len(validate_parts) == 2:
                self.validate_mask = self._remove_dots_from_bin_encoded_data(data=validate_parts[0])
                self.validate_bits = self._remove_dots_from_bin_encoded_data(data=validate_parts[1])
            else:
                data = validate_parts[0]
                if self._is_text_command_or_reply(data=data):
                    self.validate_mask = self._create_mask_for_text_data(data=data)
                    self.validate_bits = self._create_validate_bits_for_text_data(data=data)
                else:
                    self.validate_mask = self._create_mask_for_bin_data(data=data)
                    self.validate_bits = self._remove_dots_from_bin_encoded_data(data=data)
        
        self.validation_supported = (
            self.validate_mask is not None
            and self.validate_bits is not None
        )
    
    def _create_mask_for_bin_data(self, data: str):
        mask = ""
        data = self._remove_dots_from_bin_encoded_data(data=data)
        splitted = [data[i:i + 2] for i in range(0, len(data), 2)]
        for byte_str in splitted:
            mask += "00" if byte_str == "00" else "FF"
        
        return mask
    
    def _create_mask_for_text_data(self, data: str):
        data = self._get_text_between_parentheses(text=data)
        mask = ""
        for char in data:
            mask += "00" if char == "." else "FF"
        
        return mask
    
    def _create_validate_bits_for_text_data(self, data: str):
        data = self._get_text_between_parentheses(text=data)
        bits = ""
        for char in data:
            bits += "00" if char == "." else "%0.2X" % ord(char)
        
        return bits
    
    def _is_text_command_or_reply(self, data: str) -> bool:
        return data[0] == '(' and data[-1] == ')'
    
    def _get_text_between_parentheses(self, text: str) -> str:
        return text[1:-1]
    
    def _remove_dots_from_bin_encoded_data(self, data: str) -> str:
        return data.replace(".", "")

class OmnirigValueEntry():
    def __init__(
        self,
        start_pos: int,
        length: int,
        format: str,
        multiply: float,
        add: float,
    ):
        self.start_pos = start_pos
        self.length = length
        self.format = format
        self.multiply = multiply
        self.add = add

class OmnirigStatusCommand(OmnirigBaseCommand):
    
    def __init__(self, command_raw_data: dict):
        super().__init__(
            command_type=OmnirigBaseCommand.COMMAND_TYPE_READ,
            command_raw_data=command_raw_data,
        )
        
        # values init - ValueN
        value_entries = self._collect_value_entries(command_data=command_raw_data)
        self.value_entries = value_entries
        
        # flags init - FlagN
        flag_entries = self._collect_flag_entries(command_data=command_raw_data)
        self.flag_entries = flag_entries
        
        # prepare set of supported values that are retrieved with this omnirig status command
        self.command_values_retrieved = self._prepare_command_values_retrieved(
            value_entries=self.value_entries,
            flag_entries=self.flag_entries,
        )
        
    def _prepare_command_values_retrieved(
        self,
        value_entries: dict,
        flag_entries: dict,
    ) -> set:
        command_values = set()
        for value_name, _ in value_entries.items():
            command_values.add(value_name)
        for flag_name, _ in flag_entries.items():
            command_values.add(flag_name)
            
        return command_values
    
    def _collect_value_entries(self, command_data: dict) -> dict:
        _re_is_value_entry = re.compile(r"^Value(\d*)$")
        entries = {}
        for key, val in command_data.items():
            if _re_is_value_entry.match(key) is not None:
                value_parts = val.rsplit("|", 1)
                value_name = value_parts[1]
                value_data = value_parts[0]
                value_data_parts = value_data.split("|")
                
                entries[value_name] = OmnirigValueEntry(
                    start_pos=int(value_data_parts[0]),
                    length=int(value_data_parts[1]),
                    format=value_data_parts[2],
                    multiply=float(value_data_parts[3]),
                    add=float(value_data_parts[4]),
                )
        
        return entries
    
    def _collect_flag_entries(self, command_data: dict) -> dict:
        _re_is_flag_entry = re.compile(r"^Flag(\d+)$")
        entries = {}
        for key, val in command_data.items():
            if _re_is_flag_entry.match(key) is not None:
                value_parts = val.rsplit("|", 1)
                flag_name = value_parts[1]
                flag_data = value_parts[0]
                
                flag_data_parts = flag_data.split("|")
                if len(flag_data_parts) == 2:
                    flag_mask = self._remove_dots_from_bin_encoded_data(data=flag_data_parts[0])
                    flag_bits = self._remove_dots_from_bin_encoded_data(data=flag_data_parts[1])
                else:
                    data = flag_data_parts[0]
                    if self._is_text_command_or_reply(data=data):
                        flag_mask = self._create_mask_for_text_data(data=data)
                        flag_bits = self._create_validate_bits_for_text_data(data=data)
                    else:
                        flag_mask = self._create_mask_for_bin_data(data=data)
                        flag_bits = self._remove_dots_from_bin_encoded_data(data=data)
                
                entries[flag_name] = {"name": flag_name, "mask": flag_mask, "bits": flag_bits}
        
        return entries


class OmnirigValueSetCommand(OmnirigBaseCommand):
    
    def __init__(self, command_name: str, command_raw_data: dict):
        super().__init__(
            command_type=OmnirigBaseCommand.COMMAND_TYPE_WRITE,
            command_raw_data=command_raw_data,
        )
        self.command_name = command_name
        
        value_data = command_raw_data.get('Value')
        self.value_entry = self._get_value_entry(value_data=value_data) if value_data else None
    
    def _get_value_entry(self, value_data: str) -> OmnirigValueEntry:
        value_data_parts = value_data.split("|")
            
        return OmnirigValueEntry(
            start_pos=int(value_data_parts[0]),
            length=int(value_data_parts[1]),
            format=value_data_parts[2],
            multiply=float(value_data_parts[3]),
            add=float(value_data_parts[4]),
        )
    
class OmnirigCommandRawData:
    """
    Container class for single omnirig raw command data parsed from radio driver (rig) file
    """
    def __init__(self, command_name: str, command_data: dict):
        self.command_name = command_name
        self.command_data = command_data
    
class AllOmnirigCommandsRawData:
    """
    Container class for all omnirig commands parsed from radio driver (rig) file
    """
    def __init__(
        self,
        init_commands_raw_data: list,
        value_set_commands_raw_data: list,
        status_commands_raw_data: list,
    ):
        self.init_commands_raw_data = init_commands_raw_data
        self.value_set_commands_raw_data = value_set_commands_raw_data
        self.status_commands_raw_data = status_commands_raw_data

class OmnirigConfigParser:
    
    def extract_all_commands_raw_data(self, filepath: str) -> AllOmnirigCommandsRawData:
        _re_is_start_of_section = re.compile(r"^\[(.*?)]$")
        
        parsed_raw_commands = []
        with open(filepath, 'r') as file:
            command_name = None
            command_data = {}
            for line in file:
                stripped_line = line.strip()
                
                if stripped_line[0:1] == ';' or len(stripped_line) == 0:
                    continue  # commented-out or empty line
                    
                section_matches = _re_is_start_of_section.match(stripped_line)
                line_is_start_of_new_section = section_matches is not None
                if line_is_start_of_new_section:
                    if command_data:
                        # finalize previous command prior to starting the new one
                        parsed_raw_commands.append(
                            OmnirigCommandRawData(
                                command_name=command_name,
                                command_data=command_data,
                            )
                        )
                        
                    # start of the new command section
                    section_name = section_matches.group(1)
                    command_name = section_name
                    command_data = {}
                else:
                    cmd_parts = stripped_line.split("=", 1)
                    property = cmd_parts[0].strip()
                    value = cmd_parts[1].strip()
                    command_data[property] = value
                        
            if command_data:
                # do not forget the last section that was not finalized due to EOF, if any
                parsed_raw_commands.append(
                    OmnirigCommandRawData(
                        command_name=command_name,
                        command_data=command_data,
                    )
                )
        
        # split commands to corresponding "buckets"
        init_commands_raw_data = []
        value_set_commands_raw_data = []
        status_commands_raw_data = []

        for raw_command in parsed_raw_commands:
            if raw_command.command_name[0:6] == "STATUS":
                status_commands_raw_data.append(raw_command)
            elif raw_command.command_name[0:4] == "INIT":
                init_commands_raw_data.append(raw_command)
            else:
                value_set_commands_raw_data.append(raw_command)
                
        return AllOmnirigCommandsRawData(
            init_commands_raw_data=init_commands_raw_data,
            value_set_commands_raw_data=value_set_commands_raw_data,
            status_commands_raw_data=status_commands_raw_data,
        )
    
class OmnirigValueDecoder:
    
    def decode_value(self, value_format: str, data: bytes) -> float:
        if value_format == "vfText":  # ascii codes of digits
            return int(data.decode().encode('ascii'))
        elif value_format == "vfBinL":  # integer, little endian
            return int.from_bytes(data, byteorder="little", signed=True)
        elif value_format == "vfBinB":  # integer, big endian
            return int.from_bytes(data, byteorder="big", signed=True)
        elif value_format == "vfBcdLU":  # BCD, little endian, unsigned
            return self._bcd_decode(data=data, is_little_endian=True, is_signed=False)
        elif value_format == "vfBcdLS":  # BCD, little endian, signed; the sign is in the MSB byte (0x00 or 0xFF)
            return self._bcd_decode(data=data, is_little_endian=True, is_signed=True)
        elif value_format == "vfBcdBU":  # BCD, big endian, unsigned
            return self._bcd_decode(data=data, is_little_endian=False, is_signed=False)
        elif value_format == "vfBcdBS":  # BCD, big endian, signed
            return self._bcd_decode(data=data, is_little_endian=False, is_signed=True)
        elif value_format == "vfYaesu":  # special format used by Yaesu
            return self._decode_yaesu_format(data=data)
        else:
            raise Exception(f"unsupported value format: {value_format}")
        
    def _decode_yaesu_format(self, data: bytes) -> float:
        # 16 bits. high bit of the 1-st byte is sign,
        #  the rest is integer, absolute value, big endian (not complementary!)
        data_copy = bytearray(data)
        has_negative_number_flag = False
        if data_copy[0] & 0x80 > 0:
            has_negative_number_flag = True
            data_copy[0] = data_copy[0] & 0x7F  # reset the signedness flag

        number = int.from_bytes(data_copy, byteorder="big")
        return -number if has_negative_number_flag else number

    
    def _bcd_decode(
        self,
        data: bytes,
        is_little_endian: bool,
        is_signed: bool,
    ) -> float:
        has_negative_number_flag = False
        if is_signed:
            if is_little_endian and hex(data[-1]) == '0xff':
                has_negative_number_flag = True
                data = data[:-1] # strip the signedness flag from end of the data
            elif not is_little_endian and hex(data[0]) == '0xff':
                has_negative_number_flag = True
                data = data[1:]  # strip the signedness flag from beginning of the data
        
        digits = []
        for byte in data:
            for val in (byte >> 4, byte & 0xF):
                if val == 0xF and not is_signed:
                    return float(''.join(map(str, digits)))
                digits.append(val)
                
        convert_to_big_endian = is_little_endian
        if convert_to_big_endian:
            converted = []
            # reverse data order and swap the nibbles
            i = len(digits) - 2
            while i >= 0:
                converted.append(''.join(map(str, digits[i:i+2])))
                i -= 2
                
            digits = converted
        
        joined_digits = ''.join(map(str, digits))
        number = float(joined_digits)
        
        return -number if has_negative_number_flag else number


class OmnirigValueEncoder:
    
    def encode_value(self, value_format: str, value: int, target_bytes_length: int) -> str:
        if value_format == "vfText":  # ascii codes of digits
            padded_value = '{:0>PLACEHOLDER}'.replace("PLACEHOLDER", str(target_bytes_length)).format(
                str(value)
            )  # left pad with zeroes up to target_bytes_length
            return ''.join('{:02X}'.format(ord(char)) for char in padded_value)
        elif value_format == "vfBinL":  # integer, little endian
            return value.to_bytes(target_bytes_length, byteorder='little', signed=True).hex().upper()
        elif value_format == "vfBinB":  # integer, big endian
            return value.to_bytes(target_bytes_length, byteorder='big', signed=True).hex().upper()
        elif value_format == "vfBcdLU":  # BCD, little endian, unsigned
            return self._bcd_encode(
                data=value,
                target_bytes_length=target_bytes_length,
                is_little_endian=True,
                is_signed=False,
            )
        elif value_format == "vfBcdLS":  # BCD, little endian, signed; the sign is in the MSB byte (0x00 or 0xFF)
            return self._bcd_encode(
                data=value,
                target_bytes_length=target_bytes_length,
                is_little_endian=True,
                is_signed=True,
            )
        elif value_format == "vfBcdBU":  # BCD, big endian, unsigned
            return self._bcd_encode(
                data=value,
                target_bytes_length=target_bytes_length,
                is_little_endian=False,
                is_signed=False,
            )
        elif value_format == "vfBcdBS":  # BCD, big endian, signed
            return self._bcd_encode(
                data=value,
                target_bytes_length=target_bytes_length,
                is_little_endian=False,
                is_signed=True,
            )
        elif value_format == "vfYaesu":  # special format used by Yaesu
            return self._encode_yaesu_format(data=value, target_bytes_length=target_bytes_length)
        else:
            raise Exception(f"unsupported value format: {value_format}")
    
    def _encode_yaesu_format(self, data: int, target_bytes_length: int) -> str:
        # 16 bits. high bit of the 1-st byte is sign,
        #  the rest is integer, absolute value, big endian (not complementary!)
        is_negative_number = data < 0
        if is_negative_number:
            data *= -1
            
        data_bytes = data.to_bytes(target_bytes_length, byteorder='big', signed=False)
        mutable_data_bytes = bytearray(data_bytes)
        if is_negative_number:
            # do bitwise or on highest byte (byte with index 0)
            mutable_data_bytes[0] = mutable_data_bytes[0] | 0x80
        
        return mutable_data_bytes.hex().upper()
        
        data_copy = bytearray(data)
        has_negative_number_flag = False
        if data_copy[0] & 0x80 > 0:
            has_negative_number_flag = True
            data_copy[0] = data_copy[0] & 0x7F  # reset the signedness flag
        
        number = int.from_bytes(data_copy, byteorder="big")
        return -number if has_negative_number_flag else number
        
    def _bcd_encode(
        self,
        data: int,
        target_bytes_length: int,
        is_little_endian: bool,
        is_signed: bool,
    ) -> str:
        is_negative_number = data < 0
        
        if is_signed and is_negative_number:
            data = data * -1
            
        n = str(data)
        n = '{:0>PLACEHOLDER}'.replace("PLACEHOLDER", str(target_bytes_length * 2)).format(n) # left pad with zeroes
        k = 2
        digit_pairs = [n[i:i + k] for i in range(0, len(n), k)]
        
        res = ""
        
        if is_little_endian:
            for i in range(len(digit_pairs) - 1, -1, -1):
                pair = digit_pairs[i]
                res += pair
        else:
            for i in range(0, len(digit_pairs), 1):
                pair = digit_pairs[i]
                res += pair
        
        if is_signed and is_negative_number:
            if is_little_endian:
                res = res[:-2]
                res += "FF"
            else:
                temp = "FF"
                res = temp + res[2:]
        return res
    
class OmnirigCommandExecutor:
    
    def __init__(
        self,
        value_decoder: OmnirigValueDecoder,
        value_encoder: OmnirigValueEncoder,
        uart,
        logger = None
    ):
        self._value_decoder = value_decoder
        self._value_encoder = value_encoder
        self._uart = uart
        self._logger = logger
    
    
    async def execute_values_read_command(
        self,
        cmd: OmnirigStatusCommand,
        reply_timeout_secs: float,
    ) -> dict:
        """
        Execute READ command and return dict with values read in form of {value_name: value}
        """
        if cmd.command_type != OmnirigBaseCommand.COMMAND_TYPE_READ:
            raise Exception(f"Given command is not a READ command")
        
        success, trx_reply_buffer = await self._send_command(
            cmd=cmd,
            value=None,
            reply_timeout_secs=reply_timeout_secs,
            uart=self._uart
        )
        
        if not success:
            return {}
        
        # process flags
        results = {}
        for flag_name, flag_data in cmd.flag_entries.items():
            masked_flag = self._bytes_and(
                a=trx_reply_buffer,
                b=bytes.fromhex(flag_data["mask"]),
            )
            expected_value = bytes.fromhex(flag_data["bits"])
            flag_value = masked_flag == expected_value
            results[flag_name] = flag_value
        
        # process values
        for value_name, value_entry in cmd.value_entries.items():
            start_pos = value_entry.start_pos
            length_bytes = value_entry.length
            value_format = value_entry.format
            multiplier = value_entry.multiply
            add_constant = value_entry.add
            # take <length> bytes, starting at <start_pos>
            data = trx_reply_buffer[start_pos:start_pos + length_bytes]
            # convert then to a numeric value according to <format>
            value = self._value_decoder.decode_value(value_format=value_format, data=data)
            value *= multiplier  # multiplied by the <multiply> constant
            value += add_constant  # <add> constant is added
            
            results[value_name] = value
        
        return results
    
    async def execute_write_command(
        self,
        cmd,
        value,
        reply_timeout_secs: float,
    ) -> bool:
        """
        Execute WRITE command and return True if successful, False otherwise
        """
        if cmd.command_type != OmnirigBaseCommand.COMMAND_TYPE_WRITE:
            raise Exception(f"Given command is not a WRITE command")
        
        success, _ = await self._send_command(
            cmd=cmd,
            value=value,
            reply_timeout_secs=reply_timeout_secs,
            uart=self._uart
        )
        
        return success
    
    async def _send_command(
        self,
        cmd,
        value,
        reply_timeout_secs: float,
        uart,
    ) -> tuple:
        """
        Execute given command. Can be either READ or WRITE command.
        Returns tuple: (Success, TRX Reply data)
        """
        _ = uart.read()  # read and discard everything in UART buffer prior to sending command
        
        if cmd.command_type == OmnirigBaseCommand.COMMAND_TYPE_READ:
            # prepare READ command
            command_to_execute = cmd.command
            execute_debug_message = f"Sending {cmd.command_type} command: {cmd.command}"
        elif cmd.command_type == OmnirigBaseCommand.COMMAND_TYPE_WRITE:
            # prepare WRITE command
            if value:
                # command contains a value. We need to encode it a put in on correct
                # position in original "write command template"
                encoded_value = self._value_encoder.encode_value(
                    value_format=cmd.value_entry.format,
                    value=value,
                    target_bytes_length=cmd.value_entry.length
                )
                prepared_command = cmd.command[0:(2 * cmd.value_entry.start_pos)]
                prepared_command += encoded_value
                prepared_command += cmd.command[(2 * cmd.value_entry.start_pos + 2 * cmd.value_entry.length):]
            else:
                # write command has no value, use the "write command template" as-is
                prepared_command = cmd.command
            
            execute_debug_message = f"Sending {cmd.command_type} command: {prepared_command}"
            command_to_execute = prepared_command
        else:
            error_message = f"Unknown command type: {cmd.command_type}"
            self._logger.exception(error_message)
            raise Exception(error_message)
        
        self._debug_log(execute_debug_message)
        if cmd.command_data_type == OmnirigBaseCommand.DATA_TYPE_BIN:
            uart.write(bytes.fromhex(command_to_execute))
        elif cmd.command_data_type == OmnirigBaseCommand.DATA_TYPE_TEXT:
            # todo this needs to be tested, as I do not have rig with text command support
            uart.write(command_to_execute)
        else:
            error_message = f"Unknown command data type: {cmd.command_data_type}"
            self._logger.exception(error_message)
            raise Exception(error_message)
        
        should_wait_for_reply = cmd.command_has_reply_length or cmd.command_has_reply_end
        if not should_wait_for_reply:
            return True, {}
        
        # wait for reply from trx with timeout
        reply_timeout_not_reached = True
        reply_not_received = True
        trx_reply_buffer = bytearray()
        start_time = time.time_ns()
        while (reply_not_received and reply_timeout_not_reached):
            chunk = uart.read()
            if chunk:
                trx_reply_buffer.extend(chunk)
            
            if cmd.command_has_reply_length and len(trx_reply_buffer) == cmd.reply_length:
                reply_not_received = False
            if cmd.command_has_reply_end:
                # todo I do not have rig of this type to test ReplyEnd
                pass
            elapsed_ns = time.time_ns() - start_time
            if elapsed_ns > (reply_timeout_secs * 10 ** 9):
                self._debug_log("Timeout waiting for TRX reply")
                break
            await asyncio.sleep(0)
        
        if not trx_reply_buffer:
            return False, {}
        
        is_valid_reply = self._is_valid_trx_reply_for_command(
            command=cmd, trx_reply=trx_reply_buffer
        )
        self._debug_log(f"TRX reply: {trx_reply_buffer.hex()}")
        self._debug_log(f"Is valid reply: {str(is_valid_reply)}")
        
        if not is_valid_reply:
            return False, {}
        
        return True, trx_reply_buffer
    
    def _is_valid_trx_reply_for_command(self, command: OmnirigBaseCommand, trx_reply):
        if not command.validation_supported:
            # driver do not provide validation rule for this command, so assume reply is ok
            return True
        
        masked_reply = self._bytes_and(
            a=trx_reply,
            b=bytes.fromhex(command.validate_mask),
        )
        expected_value = bytes.fromhex(command.validate_bits)
        return masked_reply == expected_value
    
    def _bytes_and(self, a: bytes, b: bytes):
        """
        Perform bitwise AND of two bytes
        """
        return ((int.from_bytes(a, 'big') & int.from_bytes(b, 'big'))
                .to_bytes(max(len(a), len(b)), 'big'))

    def _debug_log(self, value):
        if self._logger:
            self._logger.debug(f"OMNIRIG: {value}")