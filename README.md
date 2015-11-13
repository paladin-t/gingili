Copyright (C) 2015 [Wang Renxin](https://twitter.com/wangrenxin)

[LinkedIn](https://cn.linkedin.com/pub/wang-renxin/43/494/20)

## Introduction

GINGILI is a program which turns a Raspberry Pi into a smart home manager.
Now it supplies watchdog monitor service using a USB webcam.

## Principle topoloty

![](https://github.com/paladin-t/gingili/blob/master/topology.png)

 * A USB webcam is connected to a Raspberry Pi to capture images;
 * The Raspberry Pi is connected to the same WAN domain with family members'
mobile phones do;
 * GINGILI detects family members' mobile phones to tell whether they're home,
to change monitor strategies;
 * GINGILI receives command via email to manage it;
 * GINGILI sends captured images via email if motion detected or an interval
heartbeat triggered;
 * GINGILI reboots system when network come invalid.

## Requirement

 * Raspberry Pi main board:
  * USB webcam;
  * Network connection, Wifi recommended.
 * Raspbian:
  * OpenCV library;
  * arp-scan tool.
 * Python 2.7:
  * OpenCV module for Python;
  * imutils module for Python.

## Setup

There are some requirement to be installed before using GINGILI.

OpenCV

    sudo apt-get install cmake libopencv-dev
    sudo apt-get install libopencv-dev python-opencv

arp-scan

    sudo apt-get install arp-scan

pip

    sudo apt-get install python-pip

imutils

    sudo pip install imutils

## Usage

 * Modify the configuration in `gingili.ini`:
  * `mailto_list` receivers' mail address list;
  * `mail_smtp_host` host address for receiving email;
  * `mail_pop_host` host address for sending email;
  * `mail_user` user name to send captures or receive commands;
  * `mail_pass` password associated with user name;
  * `family_list` static IP addresses of family members.
 * Some other configurations are directly coded in `gingili.py`, eg. event
intervals, etc. You can modify them as you need.
 * Start GINGILI by `python gingili.py`.

## Workflow

 * A thread receives commands via email to control the GINGILI service:
  * Command `help` shows help information;
  * Command `set_capture_interval N` sets intermittent capture interval, N is
time in seconds;
  * Command `pause` pauses monitoring;
  * Command `resume` resumes monitoring;
  * Command `request` requests to capture once and sends to applicant's email;
  * Command `get` sends a capture once to receiver mail list;
  * Command `reboot` terminates GINGILI and reboots the system.
 * A thread checks whether an IP address in `family_list` is reachable, GINGILI
will change to safe state (pause monitoring) if at least one IP is reachable.
It's recommended to set the family Wifi router's policy to assign static IP
addresses for specific mobile phones, thus GINGILI would turn into safe mode
when your family were home, and changes to guard state if no family detected.
 * Main thread captures a frame and sends it to `mailto_list` intermittently
with a specific interval even if no motion detected.
 * Main thread captures a sequence of frames and sends them to `mailto_list` if
motion detected.
 * A revive thread checks whether network is alive, it reboots the system if
not. It's recommended to use `gingili.desktop` to let GINGILI start
automatically when system booted.

## Note

Some webcams are not compatible with Raspberry Pi. If you already got one, just
test it; if not or it doesn't work, try to choose a new one, some compatibility
information are listed at [this page](http://elinux.org/RPi_USB_Webcams).
