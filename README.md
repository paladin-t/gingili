Copyright (C) 2015 [Wang Renxin](https://twitter.com/wangrenxin)

[LinkedIn](https://cn.linkedin.com/pub/wang-renxin/43/494/20)

## Introduction

GINGILI is a program which turns a Raspberry Pi into a video guard monitor using a USB webcam.

## Requirement
 * Raspberry Pi main board:
  * USB webcam;
  * Network connection, Wifi recommended.
 * Raspbian, may need some modifications with other distribution versions:
  * arp-scan tool.
 * Python 2.7:
  * OpenCV module for Python;
  * imutils module for Python.

## Setup
arp-scan

    sudo apt-get install arp-scan

OpenCV

    sudo apt-get install cmake libopencv-dev
    sudo apt-get install libopencv-dev python-opencv

imutils

    pip install imutils

## Usage
 * Modify the configuration in `gingili.ini`:
  * `mailto_list` receivers' mail address list;
  * `mail_smtp_host` SMTP host address;
  * `mail_pop_host` IMAP host address;
  * `mail_user` user name to send captures or receiving commands;
  * `mail_pass` password associated to user name;
  * `family_list` static IP addresses of family members.
 * Some other configurations are directly coded in `gingili.py`, most for time ticking, you can modify
 them as you need.
 * Start GINGILI by `python gingili.py`.

## Workflow
 * A thread receives commands via email to control the GINGILI service:
  * Command `help` shows help information;
  * Command `set_capture_interval N` sets intermittent capture interval, N is time in seconds;
  * Command `pause` pauses monitoring;
  * Command `resume` resumes monitoring;
  * Command `request` requests to capture once and sends to applicant's email;
  * Command `get` sends a capture once to receiver mail list.
 * A thread checks whether an IP address in `family_list` is reachable, GINGILI will change to safe state
 (pause monitoring) if at least one IP is reachable. It's recommended to set the family Wifi router's
 policy to assign static IP addresses for specific mobile phones, thus GINGILI would turn into safe mode
 when you or your family were home, and vice versa.
 * Main thread captures a frame and sends it to `mailto_list` intermittently with a specific interval even
 if no motion detected.
 * Main thread captures a sequence of frames and sends them to `mailto_list` if motion detected.

## TODO
 * Sound alarm.
 * Synchronizes frames to web.
 * Gas/fire detection.
 * Voice control.
 * Inductive switch.

## Note
Some webcams are not compatible with Raspberry Pi. If you already got one, just test it; if not or it
doesn't work, try to choose a new one, some compatibility information are listed at
[this page](http://elinux.org/RPi_USB_Webcams).
