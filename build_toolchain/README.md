After building the Dockerfile in this directory, the firmware for the boards
defined (i.e. ESP32_GENERIC_S3_WAVELOG_TRX_INTERFACE whose data is located in 
`../board_definitions`) will be built inside the container. After building this 
container, you need to copy the compiled firmware out of the docker container
so you can actually use it.

If you are using docker instead of podman, substitute `podman` with `
docker` in following commands:

- `podman build --no-cache -t wl-trx-interface-builder-image .`
- `podman container create localhost/wl-trx-interface-builder-image:latest wl-trx-firmware-container`

This will build firmware for all the board variants defined in Dockerfile.
Now you need to copy the built firmware binary images *for each board* 
(currently, there is only one: ESP32_GENERIC_S3_WAVELOG_TRX_INTERFACE) out 
of the built image:

- `podman container cp <CONTAINER_ID FROM PREVIOUS COMMAND>:/micropython/ports/esp32/build-ESP32_GENERIC_S3_WAVELOG_TRX_INTERFACE-SPIRAM_OCT/firmware.bin ~/firmware-s3-oct-spiram.bin`

Now the firmware files are ready to be flashed to the ESP32 board using esptool/web based flash esp32 tool.

### Notes
- non python files (like html, jpg, etc...) need to be "frozen" using i.e. `freezefs` utility before bundling into firmware
- `boot.py` is created in `base_mpy_modules/inisetup.py`

### References
https://github.com/orgs/micropython/discussions/11612
https://docs.micropython.org/en/latest/reference/manifest.html
https://github.com/spasea/docker-micropython-build/blob/master/Dockerfile
https://github.com/micropython/micropython/wiki/Bundling-and-deploying-application-code-and-files