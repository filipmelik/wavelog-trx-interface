# Radio drivers

This directory contains two folders:

## omnirig_default_drivers
This folder contains copy of the omnirig drivers downloaded from [Omnirig downloads page](https://www.dxatlas.com/Download.asp).
You should use drivers from this folder in case there is no tested driver for your
radio available. 

There might be more drivers for the same rig available. Those are
usually some small modifications to the original driver for very specific use cases
of the driver file's author. Wavelog radio hardware interface use just the most basic 
commands of each radio, so do not worry too much about that - just pick one driver 
and try it. If it does not work, just try to use another one. But it should work in
99% of the cases.

If you successfully test the radio driver from this folder, please open an issue 
here on github, so we can add the driver to the `tested_drivers` to let other user 
know it works 100%. Thanks!

## tested_drivers
This folder contains radio driver files of the radios that was tested and are known 
to be working 100%. Those driver files might also be slightly modified, for example
to include command for reading the radio RF power, which Omnirig software does not 
support by default.
