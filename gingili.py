#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Version 1.1.1
# License LGPL v3
# Copyright (c) 2015 WRX. mailto:hellotony521@qq.com
#
# GINGILI is a program which turns a Raspberry Pi into a video guard monitor
# using a USB webcam.
#
# Requirement:
#   Raspberry Pi main board:
#     USB webcam;
#     Network connection, Wifi recommended.
#   Raspbian, may need some modifications with other distribution versions:
#     OpenCV library;
#     arp-scan tool.
#   Python 2.7:
#     OpenCV module for Python;
#     imutils module for Python.

import argparse
import ConfigParser
import cv2
import datetime
import email
import inspect
import imaplib
import imutils
import logging
import logging.handlers
import mimetypes
import os
import re
import smtplib
import subprocess
import sys
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

###############################################################################

# Configurations.

def script_path():
    this_file = inspect.getfile(inspect.currentframe())

    return os.path.abspath(os.path.dirname(this_file))

os.chdir(script_path())

# Opens configuration.
config = ConfigParser.ConfigParser()
config.read("gingili.ini")

# Opens logging.
log_handler = logging.handlers.RotatingFileHandler("gingili.log", maxBytes = 1024 * 1024 * 1024)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(message)s"))
logger = logging.getLogger('GINGILI')
logger.addHandler(log_handler)
logger.setLevel(logging.DEBUG)

# Basic refreshing interval.
refresh_interval = 5

# Screen capture interval if motion detected.
shot_interval = 1

# Forces flushing interval even if didn't captured enough frames.
flush_interval = 30

# Scheduled periodicity capture interval, GINGILI captures and sends one frame
# once this interval elapsed.
capture_interval = 60 * 60 * 4

# Email command parsing interval, GINGILI checks commands via email once this
# interval elapsed.
parsing_interval = 60 * 2

# Reboot system if dead too long.
revive_interval = 60 * 2

# Fill rate threshold for motion detection, maximum to 1.0. 
fill_rate_threshold = 0.1

# Cache directory to save captures temporarily.
save_folder = "gingili_captures"

normal_reason = "Captured by GINGILI on RasPi"
motion_reason = "Motion detected by GINGILI on RasPi"

# Reads configuration from a file.
mailto_list = map(lambda s: s.strip(), config.get("mail", "mailto_list").split(","))
mail_smtp_host = config.get("mail", "mail_smtp_host")
mail_pop_host = config.get("mail", "mail_pop_host")
mail_user = config.get("mail", "mail_user")
mail_pass = config.get("mail", "mail_pass")

family_list = map(lambda s: s.strip(), config.get("safety", "family_list").split(","))

alive_host = config.get("misc", "alive_host")

# Finishes reading.
config = None

###############################################################################

# Variables.

shots = []

args = None

camera = None

cached_frame = None

flush_tick = 0

safe_now = False

dead = False

dead_time = None

wakeup = False

wakeup_tick = 0

pause = False

pop_conn = None

command = None

command_from = None

width = 0

height = 0

###############################################################################

def log(msg):
    print time_str() + " " + msg
    logger.info(msg)

def init():
    global args
    global camera
    global save_folder
    global width
    global height

    # Initializes arguments.
    ap = argparse.ArgumentParser()
    ap.add_argument("-a", "--min-area", type = int, default = 500, help = "Minimum area size.")
    args = vars(ap.parse_args())

    # Initializes camera.
    camera = cv2.VideoCapture(0)
    time.sleep(0.25)

    # Initializes variables.
    width = camera.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH)
    height = camera.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT)

    # Initializes capture folder.
    cleanup(False)
    if not os.path.exists(save_folder):
        os.mkdir(save_folder)

def cleanup(cleancam = True):
    global camera
    global shots
    global save_folder

    # Does cleanup OpenCV.
    if cleancam:
        camera.release()
        cv2.destroyAllWindows()

    # Deletes captures.
    for s in shots:
        os.remove(s)

    for (dir_path, dir_names, file_names) in os.walk(save_folder):
        for file_name in file_names:
            path = save_folder + "/" + file_name
            if os.path.isfile(path):
                os.remove(path)

    # Deletes capture folder.
    if os.path.exists(save_folder):
        os.rmdir(save_folder)

def reboot():
    cleanup()

    log("Revive GINGILI.")

    os.system("sudo reboot")

def clear():
    global shots

    if len(shots) == 0:
        return

    for s in shots:
        os.remove(s)
    shots = []

def time_str():
    return datetime.datetime.now().strftime("%b-%d-%y %H:%M:%S")

def motion_detect():
    global args
    global fill_rate_threshold
    global width
    global height
    global cached_frame

    # Grabs the current frame.
    (grabbed, frame) = camera.read()

    if not grabbed:
        log("Nothing grabbed.")

        return ("Not grabbed", False, None, None, None, None, None, None)

    # Converts to image object.
    img = cv2.cv.fromarray(frame)

    # Resizes the frame, converts it to grayscale, and blurs it.
    frame = imutils.resize(frame, width = 500)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    # If the first frame is None, initializes it.
    if cached_frame is None:
        cached_frame = gray

        return (True, False, None, None, None, None, None, None)

    # Computes the absolute difference between the current frame and the first
    # frame.
    frame_delta = cv2.absdiff(cached_frame, gray)
    thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]

    # Dilates the thresholded image to fill in holes, then finds contours on
    # thresholded image.
    thresh = cv2.dilate(thresh, None, iterations = 2)
    (cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Processes motion contents.
    area = 0
    for c in cnts:
        # Ignores small ones.
        if cv2.contourArea(c) < args["min_area"]:
            continue

        # Calculates area.
        (x, y, w, h) = cv2.boundingRect(c)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        area += w * h

    # Checks whether it's enough filled.
    filled = area / (width * height)
    if filled > fill_rate_threshold and filled < 1.0:
        return (False, True, frame, img, gray, frame_delta, thresh, cnts)

    return (False, False, frame, img, gray, frame_delta, thresh, cnts)

def save(f):
    global shots

    # Saves to a file.
    p = save_folder + "/" + time_str() + ".jpg"
    cv2.cv.SaveImage(p, f)

    return p

def routine_help(rcv):
    global mail_smtp_host
    global mail_user
    global mail_pass

    server = smtplib.SMTP()
    server.connect(mail_smtp_host)
    server.login(mail_user, mail_pass)

    if not rcv.startswith("<"): rcv = "<" + rcv
    if not rcv.endswith(">"): rcv = rcv + ">"

    msg = MIMEMultipart()
    msg["From"] = mail_user
    msg["To"] = rcv
    msg["Subject"] = "GINGILI commands list"

    log("Sending mail to: " + msg["To"] + ".")

    txt = """
        Command `help` shows help information;\n
        Command `set_capture_interval N` sets intermittent capture interval, N is time in seconds;\n
        Command `pause` pauses monitoring;\n
        Command `resume` resumes monitoring;\n
        Command `request` requests to capture once and sends to applicant's email;\n
        Command `get` sends a capture once to receiver mail list.\n
        Command `reboot` reboots system.\n
    """
    txt = MIMEText(txt, "plain", "gb2312")
    msg.attach(txt)

    server.sendmail(msg["From"], msg["To"], msg.as_string())

    server.quit()

def async_help(rcv):
    t = threading.Thread(target = routine_help, args = [rcv])
    t.setDaemon(True)
    t.start()

def routine_flush(imgs, rcvs, reason):
    global mail_smtp_host
    global mail_user
    global mail_pass

    server = smtplib.SMTP()
    server.connect(mail_smtp_host)
    server.login(mail_user, mail_pass)

    for rcv in rcvs:
        if not rcv.startswith("<"): rcv = "<" + rcv
        if not rcv.endswith(">"): rcv = rcv + ">"

        msg = MIMEMultipart()
        msg["From"] = mail_user
        msg["To"] = rcv
        msg["Subject"] = reason

        log("Sending mail to: " + msg["To"] + ".")

        txt = MIMEText("Flushed at " + time_str(), "plain", "gb2312")     
        msg.attach(txt)    

        for i in range(len(imgs)):
            file = imgs[i]
            image = MIMEImage(open(file, "rb").read())
            image.add_header("Content-ID", "<image" + str(i + 1) + ">")
            msg.attach(image)

        server.sendmail(msg["From"], msg["To"], msg.as_string())

    server.quit()

    for i in imgs:
        os.remove(i)

def async_flush(imgs, rcvs, reason):
    t = threading.Thread(target = routine_flush, args = [imgs, rcvs, reason])
    t.setDaemon(True)
    t.start()

def flush():
    global shots
    global mailto_list
    global flush_interval
    global flush_tick
    global motion_reason

    count = 10

    time_to_flush = False
    now = time.time()
    if len(shots) > 0:
        if flush_tick == 0:
            flush_tick = now
        if now - flush_tick >= flush_interval:
            flush_tick = now
            time_to_flush = True
    else:
        flush_tick = 0

    imgs = []
    if len(shots) > count or time_to_flush:
        for i in range(count):
            if i >= len(shots):
                break
            imgs.append(shots[i])
    for i in imgs:
        shots.remove(i)

    if len(imgs) > 0:
        async_flush(imgs, mailto_list, motion_reason)
        flush_tick = now

def render(frame, frame_delta, thresh, text):
    cv2.putText(frame, "Status: {}".format(text), (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    cv2.putText(frame, time_str(), (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)

    cv2.imshow("Security Feed", frame)
    cv2.imshow("Frame Delta", frame_delta)
    cv2.imshow("Thresh", thresh)

def routine_safe():
    global family_list
    global safe_now

    try:
        while True:
            s = None
            for f in family_list:
                for i in range(15):
                    pingaling = subprocess.Popen(["sudo", "arp-scan", "--interface=wlan0", "--retry=5", "--timeout=100", f], shell = False, stdin = subprocess.PIPE, stdout = subprocess.PIPE)
                    while True:
                        pingaling.stdout.flush()
                        line = pingaling.stdout.readline()
                        if not line:
                            break
    
                        if f in line:
                            s = f
    
                            break
    
                    if s != None:
                        break
    
                if s != None:
                    break
    
            if (not not safe_now) != (not not s):
                if s != None:
                    log("Family member " + s + " detected, pause flushing.")
                else:
                    log("No family member detected, resume flushing.")
            safe_now = s
    
            time.sleep(30)
    except Exception, e:
        log("Thread routine_safe got exception: " + str(e) + ".")
        check_safe()

def check_safe():
    t = threading.Thread(target = routine_safe)
    t.setDaemon(True)
    t.start()

def routine_alive():
    global dead
    global alive_host
    global dead_time

    try:
        while True:
            s = None
            if alive_host != "0":
                for i in range(15):
                    pingaling = subprocess.Popen(["ping", "-c 2", alive_host], shell = False, stdin = subprocess.PIPE, stdout = subprocess.PIPE)
                    while True:
                        pingaling.stdout.flush()
                        line = pingaling.stdout.readline()
                        if not line:
                            break

                        igot = re.findall(lifeline,line)
                        if igot != 0:
                            s = igot

                            break;

                    if s != None:
                        break
            else:
                s = True

            dead = s == None

            if dead:
                if dead_time == None:
                    dead_time = time.time()
                log("Dead.")
            else:
                dead_time = None

            time.sleep(30)
    except Exception, e:
        log("Thread routine_alive got exception: " + str(e) + ".")
        check_safe()

def check_alive():
    t = threading.Thread(target = routine_alive)
    t.setDaemon(True)
    t.start();

def extract_body(payload):
    if isinstance(payload, str):
        return payload
    else:
        return '\n'.join([extract_body(part.get_payload()) for part in payload])

def routine_command():
    global command
    global command_from
    global pop_conn
    global mail_pop_host
    global mail_user
    global mail_pass
    global parsing_interval

    pattern = r"(\<.*?\>)"

    while True:
        if command != None:
            continue

        try:
            pop_conn = imaplib.IMAP4_SSL(mail_pop_host, 993)
            pop_conn.login(mail_user, mail_pass)
            pop_conn.select()
            typ, data = pop_conn.search(None, "UNSEEN")
            try:
                for num in data[0].split():
                    typ, msgData = pop_conn.fetch(num, "(RFC822)")
                    for responsePart in msgData:
                        if isinstance(responsePart, tuple):
                            msg = email.message_from_string(responsePart[1])
                            subject = msg["subject"]
                            command_from = msg["from"]
                            command_from = re.findall(pattern, command_from, re.M)
                            if len(command_from) > 0:
                                command_from = command_from[0].replace("<", "").replace(">", "")
                            command = subject.strip().lower()
                            payload = msg.get_payload()
                            body = extract_body(payload)
                    typ, response = pop_conn.store(num, "+FLAGS", r"(\Seen)")
            except Exception, e:
                log("Thread routine_command got exception when parsing: " + str(e) + ".")

            pop_conn.close()
            pop_conn.logout()

            time.sleep(parsing_interval)
        except Exception, e:
            log("Thread routine_command got exception when connecting: " + str(e) + ".")

    pop_conn.close()
    pop_conn.logout()

def check_command():
    t = threading.Thread(target = routine_command)
    t.setDaemon(True)
    t.start()

def parse_command(img):
    global command
    global command_from
    global capture_interval
    global pause
    global normal_reason
    global motion_reason

    if command == None:
        return

    if command != normal_reason and command != motion_reason:
        log("Received command: " + command + ".")

    if command == "help":
        async_help(command_from)
    elif command.startswith("set_capture_interval"):
        t = command[len("set_capture_interval") : ]
        t = int(t)
        capture_interval = t
    elif command == "pause":
        pause = True
    elif command == "resume":
        pause = False
    elif command == "request":
        if isinstance(command_from, str):
            imgs = [save(img)]
            async_flush(imgs, [command_from], normal_reason)
    elif command == "get":
        imgs = [save(img)]
        async_flush(imgs, mailto_list, normal_reason)
    elif command == "reboot":
        reboot()

    command = None
    command_from = None

def paused():
    global safe_now
    global pause

    return safe_now or pause

def wake():
    global wakeup
    global wakeup_tick

    wakeup = True
    wakeup_tick = time.time()

def lazy_mode():
    global wakeup
    global wakeup_tick

    now = time.time()
    if now - wakeup_tick > 60 * 2:
        wakeup = False

    return paused() or not wakeup

def try_revive():
    global dead_time
    global revive_interval

    if dead_time == None:
        return

    if time.time() - dead_time > revive_interval:
        reboot()

def main():
    global refresh_interval
    global fill_rate_threshold
    global args
    global camera
    global cached_frame
    global safe_now
    global pause
    global mailto_list
    global normal_reason

    log("Start GINGILI.")

    # Initializes.
    init()

    # Starts a thread to check whether it's safe.
    check_safe()

    # Starts a thread to process email commands.
    check_command()

    # Starts a thread to check whether network is alive.
    check_alive()

    # Initializes states.
    occupied = False

    cached_frame = None

    now = time.time()

    refresh_timestamp = now

    shot_timestamp = now

    capture_timestamp = now

    # Main loop.
    while True:
        # Detects motion.
        (cont, filled, frame, img, gray, frame_delta, thresh, cnts) = motion_detect()
        if cont == "Not grabbed":
            break

        if cont:
            continue

        text = "Unoccupied"

        # Reinitializes the first frame every 'refresh_interval' seconds.
        now = time.time()
        if now - refresh_timestamp > refresh_interval:
            refresh_timestamp = now
            cached_frame = gray

            continue

        # Counts to capture.
        if not paused() and now - capture_timestamp > capture_interval:
            capture_timestamp = now
            imgs = [save(img)]
            async_flush(imgs, mailto_list, normal_reason)

        # Checks fill rate.
        if filled:
            text = "Occupied"
            # Saves a capture every 'shot_interval' seconds.
            if not paused() and now - shot_timestamp > shot_interval:
                shot_timestamp = now
                shots.append(save(img))

        # Parses command.
        parse_command(img)

        # Checks whether it's safe now.
        if paused():
            clear()

        # Tries to send captures.
        flush()

        # Shows the frames.
        render(frame, frame_delta, thresh, text)

        # If the `q` key is pressed, breaks from the loop.
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("p"):
            pause = True
            log("Paused manually.")
        elif key == ord("r"):
            pause = False
            log("Resumed manually.")

        if lazy_mode():
            time.sleep(0.33)
        else:
            time.sleep(0.01)

        # Revives system if it's dead.
        try_revive()

    # Cleanups the camera and closes all opened windows.
    cleanup()

    log("Shutdown GINGILI.")

main()
