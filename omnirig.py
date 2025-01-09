import re
import time

class TrxStatus:
    def __init__(
        self,
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
        
    def current_tx_frequency(self, status_values_supported_by_trx: set):
        if not status_values_supported_by_trx:
            return 0
        
        if (
            "pmFreqA" in status_values_supported_by_trx
            and self.active_vfo in ["pmVfoAA", "pmVfoBA"]
        ):
            tx_freq = self.freq_a
        elif (
            "pmFreqB" in status_values_supported_by_trx
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
    
    def current_rx_frequency(self, status_values_supported_by_trx: set):
        if not status_values_supported_by_trx:
            return 0
        
        if (
            "pmFreqA" in status_values_supported_by_trx
            and self.active_vfo in ["pmVfoA", "pmVfoAA", "pmVfoAB"]
        ):
            rx_freq = self.freq_a
        elif (
            "pmFreqB" in status_values_supported_by_trx
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

class OmnirigStatusCommand:
    DATA_TYPE_BIN = "BIN"
    DATA_TYPE_TEXT = "TEXT"
    
    def __init__(self, status_command_data: dict):
        # command init - Command
        command_expression = status_command_data.get('Command')
        if self._is_text_command_or_reply(data=command_expression):
            self.command_data_type = OmnirigStatusCommand.DATA_TYPE_TEXT
            self.command = self._get_text_between_parentheses(text=command_expression)
        else:
            self.command_data_type = OmnirigStatusCommand.DATA_TYPE_BIN
            self.command = self._remove_dots_from_bin_encoded_data(
                data=command_expression
            )
        
        # reply data init - ReplyLength and ReplyEnd
        reply_length = status_command_data.get('ReplyLength')
        self.command_has_reply_length = (
                reply_length is not None
                and reply_length != ""
                and int(reply_length) > 0
        )
        if self.command_has_reply_length:
            self.reply_length = int(reply_length)
        
        self.reply_end = status_command_data.get('ReplyEnd')
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
        validate_val = status_command_data.get('Validate')
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
        
        # values init - ValueN
        value_entries = self._collect_value_entries(command_data=status_command_data)
        self.value_entries = value_entries
        
        # flags init - FlagN
        flag_entries = self._collect_flag_entries(command_data=status_command_data)
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
        _re_is_value_entry = re.compile(r"^Value(\d+)$")
        entries = {}
        for key, val in command_data.items():
            if _re_is_value_entry.match(key) is not None:
                value_parts = val.rsplit("|", 1)
                value_name = value_parts[1]
                value_data = value_parts[0]
                value_data_parts = value_data.split("|")
                
                entries[value_name] = {
                    "start_pos": int(value_data_parts[0]),
                    "length": int(value_data_parts[1]),
                    "format": value_data_parts[2],
                    "multiply": float(value_data_parts[3]),
                    "add": float(value_data_parts[4]),
                }
        
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
        return  data[0] == '(' and data[-1] == ')'
        
    def _get_text_between_parentheses(self, text: str) -> str:
        return text[1:-1]
    
    def _remove_dots_from_bin_encoded_data(self, data: str) -> str:
        return data.replace(".", "")

class OmnirigConfigParser:
    
    def extract_status_commands_sections(self, filepath: str):
        _re_is_start_of_section = re.compile(r"^\[(.*?)]$")

        status_command_sections = []
        with open(filepath, 'r') as file:
            status_section_data = {}
            in_status_section = False
            for line in file:
                stripped_line = line.strip()
                
                if stripped_line[0:1] == ';' or len(stripped_line) == 0:
                    continue  # commented-out line
                    
                section_matches = _re_is_start_of_section.match(stripped_line)
                line_is_start_of_new_section = section_matches is not None
                if line_is_start_of_new_section:
                    if in_status_section:
                        # finalize the previous section first
                        in_status_section = False
                        status_command_sections.append(status_section_data)
                    
                    section_name = section_matches.group(1)
                    if section_name[0:6] == "STATUS":
                        # start the new status section
                        status_section_data = {}
                        in_status_section = True

                else:
                    if in_status_section:
                        cmd_parts = stripped_line.split("=", 1)
                        property = cmd_parts[0].strip()
                        value = cmd_parts[1].strip()
                        status_section_data[property] = value
                        
            if status_section_data:
                # do not forget the last section that was not finalized due to EOF, if any
                status_command_sections.append(status_section_data)
                
        return status_command_sections
    
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
    
    
class OmnirigCommandExecutor:
    
    def __init__(self, value_decoder: OmnirigValueDecoder, debug: bool = False):
        self.value_decoder = value_decoder
        self.debug = debug
    
    def execute_status_command(
        self,
        cmd: OmnirigStatusCommand,
        reply_timeout_secs: float,
        uart
    ) -> dict:
        _ = uart.read()  # read and discard everything in UART buffer prior to sending command
        
        self._debug_print(f"Sending command: {cmd.command}")
        if cmd.command_data_type == OmnirigStatusCommand.DATA_TYPE_BIN:
            uart.write(bytes.fromhex(cmd.command))
        else:
            # todo needs to be tested, as I do not have rig with text command support
            uart.write(cmd.command)
        
        should_wait_for_reply = cmd.command_has_reply_length or cmd.command_has_reply_end
        if not should_wait_for_reply:
            return {}
        
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
                self._debug_print("Timeout waiting for TRX reply")
                break
        
        if not trx_reply_buffer:
            return {}
        
        is_valid_reply = self._is_valid_trx_reply_for_command(
            command=cmd, trx_reply=trx_reply_buffer
        )
        self._debug_print(f"TRX reply: {trx_reply_buffer.hex()}")
        self._debug_print(f"Is valid reply: {str(is_valid_reply)}")
        
        if not is_valid_reply:
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
        for value_name, value_data in cmd.value_entries.items():
            start_pos = value_data["start_pos"]
            length_bytes = value_data["length"]
            value_format = value_data["format"]
            multiplier = value_data["multiply"]
            add_constant = value_data["add"]
            # take <length> bytes, starting at <start_pos>
            data = trx_reply_buffer[start_pos:start_pos+length_bytes]
            # convert then to a numeric value according to <format>
            value = self.value_decoder.decode_value(value_format=value_format, data=data)
            value *= multiplier  # multiplied by the <multiply> constant
            value += add_constant  # <add> constant is added
            
            results[value_name] = value
            
        return results
    
    def _is_valid_trx_reply_for_command(self, command: OmnirigStatusCommand, trx_reply):
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
        return ((int.from_bytes(a, 'big') & int.from_bytes(b, 'big'))
                .to_bytes(max(len(a), len(b)), 'big'))

    def _debug_print(self, value):
        if self.debug:
            print(f"DEBUG: {value}")