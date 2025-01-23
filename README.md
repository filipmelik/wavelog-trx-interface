# Wavelog Radio Hardware Interface
Are you lazy typing frequency and mode each time you are logging 
a QSO using fantastic web-based [Wavelog](https://www.wavelog.org/) 
logger? If the answer is yes, this little device got you covered!

The device currently supports radios that are connected via 
**UART-based CAT** control port (Serial COM port). 

Radios that can be controlled
only through Bluetooth, Wi-fi, Ethernet or USB (This is especially 
the case of recently released radios) are not supported.

### Features:
- Easy to build
- Standalone device, no PC connected to the radio is needed
- Supports radios that has **UART-based CAT** control port and are supported by [Omnirig](https://dxatlas.com/OmniRig/)
- Automatically reports current frequency (both TX and RX) and mode to Wavelog
- If the radio driver file supports it, it can also report the rig RF power setting
- With the help of websockets proxy server, the radio can QSY to the frequency of Wavelog's DX Cluster spot on click (if the radio driver file supports it)

## Supported radios
In theory, all radios that has UART-based CAT control port 
and are supported by [Omnirig](https://dxatlas.com/OmniRig/) should work.
This is because this device uses radio commands stored in omnirig ini 
driver files to read & control the radio. This makes this device 
vendor-and-model-independent as long as the radio has UART-based CAT 
control port and you use the correct UART voltage level-shifter for 
connecting this device to the radio (if applicable).

### Tested radios
Those are the radios known to be 100% working with the device, because
somebody has tested them already. If you tested the your radio and it 
is missing in this list, raise the issue and we will add it here.

- Icom IC-7300

### How to build the HW
todo -  which esp32 boards are supported, per-rig level shifter instructions - possibly in separate wiki page 

### How to install firmware to the device
todo esp webtool, esptool.py, maybe arduino/thonny?

### How to develop
explain the repo's directory structure and build process

### Future plans
custom hardware board

### Credits and thanks


