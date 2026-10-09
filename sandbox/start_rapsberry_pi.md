# Raspberry Pi YOLO Setup & Detection Guide

This guide outlines how to connect to a Raspberry Pi without a pre-configured network, set up a Python virtual environment for YOLO, run object detection using a Pi Camera, transfer files back to your PC, and stream live video.

## Table of Contents

1. [Initial Connection via Ethernet](#1-initial-connection-via-ethernet)

2. [Environment Setup](#2-environment-setup)

3. [Running Object Detection](#3-running-object-detection)

4. [Downloading Files to PC](#4-downloading-files-to-pc)

5. [Live Streaming to PC](#5-live-streaming-to-pc)

## 1. Initial Connection via Ethernet

If the Raspberry Pi does not have access to its configured Wi-Fi network:

1. Connect the Raspberry Pi to your laptop using an Ethernet cable and power it on.

2. Open a terminal on Windows and configure network sharing:

   ```
   ncpa.cpl
   
   ```

   *(In the network connections window, allow your Wi-Fi network to be shared via the Ethernet adapter).*

3. Find the Raspberry Pi's IP address:

   ```
   arp -a
   
   ```

   *(Look for the IP address associated with your connection, typically `192.168.137.200`).*

4. Test the connection:

   ```
   ping 192.168.137.200
   
   ```

5. Connect via SSH:

   ```
   ssh pi@192.168.137.200
   # Or using mDNS:
   ssh pi@cerema-pi.local
   
   ```

   * **Default Username:** `pi`

   * **Default Password:** `cerema`

## 2. Environment Setup

Once logged into the Raspberry Pi, create a dedicated workspace and virtual environment:

```
# Navigate to Desktop and create a workspace
cd Desktop
mkdir Yolo_test
cd Yolo_test

# Create and activate virtual environment (inheriting system site-packages)
python3 -m venv --system-site-packages yolo_env
source yolo_env/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install ultralytics --no-deps
pip install opencv-python

# Download the YOLO model
python -c "from ultralytics import YOLO; model = YOLO('yolo11n.pt')"

```

## 3. Running Object Detection

Create your detection script:

```
nano yolo_detect_rasp.py

```

*(Copy and paste your detection script into the file, save, and exit).*

### Run on a Single Image

```
python yolo_detect_rasp.py --model yolo11n.pt --source picamera0 --resolution 640x480 --no-display

```

### Run on Video (Recording)

```
python yolo_detect_rasp.py --model yolo11n.pt --source picamera0 --resolution 640x480 --record --no-display

```

## 4. Downloading Files to PC

Open a **new terminal on your PC** (not the SSH session) and use `scp` to download generated files:

* **Download an image:**

  ```
  scp pi@192.168.137.200:/home/pi/Desktop/Yolo_test/out_last.jpg .
  
  ```

* **Download a recorded video:**

  ```
  scp pi@192.168.137.200:/home/pi/Desktop/Yolo_test/demo1.avi .
  
  ```

## 5. Live Streaming to PC

To stream and view the camera feed directly on your PC in real time:

1. Install FFmpeg on Windows (if not already installed):

   ```
   winget install Gyan.FFmpeg
   
   ```

2. Run the stream pipeline from your PC terminal:

   ```
   ssh pi@cerema-pi.local "rpicam-vid -t 0 -n --inline --rotation 180 --width 1280 --height 720 --framerate 15 --post-process-file /usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json -o -" | ffplay -fflags nobuffer -flags low_delay -framedrop -
   
   ```
