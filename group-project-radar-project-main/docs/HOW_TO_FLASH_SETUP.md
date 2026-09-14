# IWR6843AOPEVM Flashing and Setup Guide

## 1. Requirements
- [IWR6843AOPEVM Out-of-box Demo Firmware](https://dev.ti.com/tirex/explore/node?a=1AslXXD__1.00.01.07&isTheia=false&node=A__AEJIihHrihnJ5tOjhHRLRA__radar_toolbox__1AslXXD__LATEST&r=1AslXXD__1.00.00.26)
- [TI UniFlash](https://www.ti.com/tool/UNIFLASH)
- [CP210x USB to UART Bridge VCP Drivers](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers?tab=downloads)
- Windows/Linux

## 2. How to flash

1. Download and install Uniflash on Windows/Linux PC
2. Download and install board drivers (CP210x)
3. Set up the EVM board in "Flashing mode" by switching S1.3 and S1.4 (front switches) to **OFF**, then switching S3 (back switch) to **ON**
4. Connect EVM board to computer and identify its COM port numbers in Device Manager > Ports (COM & LPT) (Windows)
    - Silicon Labs ... Enhanced COM Port (Config/application port)
    - Silicon Labs ... Standard COM Port (Data port)
5. Open Uniflash, create new config and select "IWR6843AOP", then click Start
6. Scroll down to "Quick Settings" and enter **config** COM port from Device Manager (e.g., "COM5")
7. Click "Browse" for Meta Image 1 and select out-of-box firmware file (.bin) from `group-project-radar-project/firmware`
8. Power-cycle EVM board by clicking "RST_SW" button 2-3 times on top left, then click "Load Image" to flash

## 2. Using `radar_interface.py`
- When setting up interface for logger, make sure to use correct COM port numbers for `--config-port` and `--data-port`
    - e.g., `radar_interface.py --config-port COM3 --data-port COM4`
- For the config file flag, enter the config file name + path in `group-project-radar-project/firmware/profile_3d.cfg`
    - e.g., `--cfg-file profile_3d.cfg`