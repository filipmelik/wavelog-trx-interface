from lib.omnirig import OmnirigValueDecoder, OmnirigValueEncoder

# OmnirigValueDecoder tests
value_decoder = OmnirigValueDecoder()
value_decoder_test_data = [
    {"hex_data": "3083150700", "value_format": "vfBcdLU", "expected": 7158330},
    {"hex_data": "23010000", "value_format": "vfBcdLU", "expected": 123},
    {"hex_data": "00000123", "value_format": "vfBcdBU", "expected": 123},
    {"hex_data": "230100FF", "value_format": "vfBcdLS", "expected": -123},
    {"hex_data": "23010000", "value_format": "vfBcdLS", "expected": 123},
    {"hex_data": "00000123", "value_format": "vfBcdBS", "expected": 123},
    {"hex_data": "FF000123", "value_format": "vfBcdBS", "expected": -123},
    {"hex_data": "0000007B", "value_format": "vfBinB", "expected": 123},
    {"hex_data": "FFFFFF85", "value_format": "vfBinB", "expected": -123},
    {"hex_data": "7B000000", "value_format": "vfBinL", "expected": 123},
    {"hex_data": "85FFFFFF", "value_format": "vfBinL", "expected": -123},
    {"hex_data": "2D313233", "value_format": "vfText", "expected": -123},
    {"hex_data": "30313233", "value_format": "vfText", "expected": 123},
    {"hex_data": "0000007B", "value_format": "vfYaesu", "expected": 123},
    {"hex_data": "8000007B", "value_format": "vfYaesu", "expected": -123},
]
for test_data in value_decoder_test_data:
    value_format = test_data["value_format"]
    data = test_data["hex_data"]
    expected = test_data["expected"]
    
    print(f"--- test decode {value_format} with hex data {data}")
    data_as_bytes = bytes.fromhex(data)
    result = value_decoder.decode_value(data=data_as_bytes, value_format=value_format)
    if (result == expected):
        print(">>> test decode: OK!")
    else:
        print(f"FAIL. got '{result}', expected '{expected}'")
        exit(1)

# OmnirigValueEncoder tests
value_encoder = OmnirigValueEncoder()
value_encoder_test_data = [
    {"expected": "3083150700", "value_format": "vfBcdLU", "numeric_value": 7158330, "target_bytes_length": 5},
    {"expected": "23010000", "value_format": "vfBcdLU", "numeric_value": 123, "target_bytes_length": 4},
    {"expected": "000123", "value_format": "vfBcdBU", "numeric_value": 123, "target_bytes_length": 3},
    {"expected": "23010000FF", "value_format": "vfBcdLS", "numeric_value": -123, "target_bytes_length": 5},
    {"expected": "23010000", "value_format": "vfBcdLS", "numeric_value": 123, "target_bytes_length": 4},
    {"expected": "00000123", "value_format": "vfBcdBS", "numeric_value": 123, "target_bytes_length": 4},
    {"expected": "FF000123", "value_format": "vfBcdBS", "numeric_value": -123, "target_bytes_length": 4},
    {"expected": "0000007B", "value_format": "vfBinB", "numeric_value": 123, "target_bytes_length": 4},
    {"expected": "FFFFFF85", "value_format": "vfBinB", "numeric_value": -123, "target_bytes_length": 4},
    {"expected": "7B000000", "value_format": "vfBinL", "numeric_value": 123, "target_bytes_length": 4},
    {"expected": "85FFFFFF", "value_format": "vfBinL", "numeric_value": -123, "target_bytes_length": 4},
    {"expected": "2D313233", "value_format": "vfText", "numeric_value": -123, "target_bytes_length": 4},
    {"expected": "30313233", "value_format": "vfText", "numeric_value": 123, "target_bytes_length": 4},
    {"expected": "0000007B", "value_format": "vfYaesu", "numeric_value": 123, "target_bytes_length": 4},
    {"expected": "8000007B", "value_format": "vfYaesu", "numeric_value": -123, "target_bytes_length": 4},
]
for test_data in value_encoder_test_data:
    value_format = test_data["value_format"]
    value = test_data["numeric_value"]
    target_bytes_length = test_data["target_bytes_length"]
    expected = test_data["expected"]
    
    print(f"--- test encode {value_format} with numeric value {value}")
    result = value_encoder.encode_value(
        value=value,
        value_format=value_format,
        target_bytes_length=target_bytes_length,
    )
    if (result == expected):
        print("test encode: OK!")
    else:
        print(f"FAIL. got {repr(result)}, expected '{expected}'")
        exit(1)
        
# TODO EXECUTOR TEST