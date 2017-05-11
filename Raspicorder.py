#!/usr/bin/python
# -*- encoding: utf-8 -*-
#
# Raspicorder
# Simon Widmer
# 07/04/2017
#
#
__version__ = "1.0"

###############################################################################
# Imports
###############################################################################

import sys
import time
from datetime import datetime
import threading
from threading import Timer,Thread,Event
import logging
import subprocess
import spidev
import random
import smbus
import csv
import math
import os
from threading import Timer
from time import sleep
import RPi.GPIO as GPIO


###############################################################################
# Defines
###############################################################################

COMPANY             = 'Adrenio Refurbishment GmbH'
OFFSET_CURRENT      = 0.04
DISK_WARNING        = 600*1024*1024 #600MB
DISK_ERROR          = 200*1024*1024 #200MB
TM_SHORT            = 5000 #ms

TEMP_THRESHOLD		= 45

PIN_BT_START	    = 17
PIN_BT_STOP		    = 12
PIN_BT_USB		    = 14
PIN_SW_SAMPLING0	= 15
PIN_SW_SAMPLING1	= 18
PIN_LED_RDY		    = 4
PIN_LED_REC		    = 5
PIN_LED_USB		    = 6
PIN_LED_ERR		    = 13

CH_CURRENT          = 0
CH_VOLTAGE          = 1
CH_SUPPLY           = 2

TM_BLINK            = 0.050 #s
TM_WAIT_S           = 0.4 #s
TM_WAIT_L           = TM_WAIT_S * 4 #s

LED_OFF             = 0
LED_SLOW            = 1
LED_FAST            = 2
LED_ON              = 3
LED_RDY		        = 0
LED_REC		        = 1
LED_USB		        = 2
LED_ERR		        = 3

SAMPLING_1          = 0.1 #s
SAMPLING_2          = 1 #s
SAMPLING_3          = 2 #s
SAMPLING_4          = 3 #s
samplingrate        = SAMPLING_2

I2CBUS              = smbus.SMBus(1)
I2CADDRESS          = 0x68

DEFAULTPATH         = '/home/pi/logger/'
DATAPATH            = '/home/pi/data/'
USBSCRIPT          = './usb_copy.sh'
LOGFILE             = 'outfile.log'

#Logging
logger = logging.getLogger('Recorder')
logger.setLevel(logging.DEBUG)

# Konsolenlogger
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('(%(threadName)-10s) %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Filelogger
fh = logging.FileHandler(filename=LOGFILE, mode='w')
fh.setLevel(logging.DEBUG)
formatter2 = logging.Formatter('%(asctime)s - (%(threadName)-10s)  %(levelname)s - %(message)s')
fh.setFormatter(formatter2)
logger.addHandler(fh)

#logger.debug('DEBUG')
#logger.info('INFO')
#logger.warning('WARNING')
#logger.critical('CRITICAL')

###############################################################################
# Functions
###############################################################################

def shutdown_now():
    logger.info('Verlasse Programm')
    global shutdown
    shutdown = True

# Copy to USB
def copy_usb():
    pass

# Function to read SPI data from MCP3004 chip
# Channel must be an integer 0-3
def ReadChannel(channel):
    logger.info('Reading Data from Channel %d', channel)
    spi = spidev.SpiDev()
    spi.open(0,0)
    adc = spi.xfer2([1,(8+channel)<<4,0])
    data = ((adc[1]&3) << 8) + adc[2]
    spi.close()
    logger.debug('Data CH %d: %d', channel, data)
    return data

# Function to convert data to voltage level,
# rounded to specified number of decimal places.
def ConvertVoltage(data,places):
    volts = (data * 3.3) / float(1023)
    volts = round(volts,places)
    logger.debug('Voltage: %f', volts)
    return volts

# Function to convert data to voltage level,
# rounded to specified number of decimal places.
def ConvertCurrent(data,places):
    volts = (data * 3.3) / float(1023)
    current = round((volts-1.65) / (0.01*20.0)+OFFSET_CURRENT,places) # (Vout-Vref) / (R*Av) + Offset
    logger.debug('Current: %f', current)
    return current

# LED Blink
def led_blink(pin):
    GPIO.output(pin,GPIO.HIGH)
    time.sleep(TM_BLINK)
    GPIO.output(pin,GPIO.LOW)

def handle_led(pin, led):
    logger.debug('Hello')
    while shutdown == False:
        if led_state[led] == LED_OFF:
            #logger.debug('led aus')
            GPIO.output(pin,GPIO.LOW)
        elif led_state[led] == LED_ON:
            #logger.debug('led ein')
            GPIO.output(pin,GPIO.HIGH)
        elif led_state[led] == LED_SLOW:
            #logger.debug('blink langsam')
            led_blink(pin)
            time.sleep(TM_WAIT_L)
        elif led_state[led] == LED_FAST:
            #logger.debug('blink schnell')
            led_blink(pin)
            time.sleep(TM_WAIT_S)
        time.sleep(0.01)
    logger.debug('Bye')

def register_data():
    logger.debug('Hello')
    while shutdown == False:
        if(measurement.is_running is True and measurement.is_paused is False):
            reg_data()
            led_blink(PIN_LED_ERR)
            logger.debug('Sampling: %d', measurement.get_samplingrate())
            sleep(measurement.get_samplingrate())
        else:
            sleep(0.01)
    logger.debug('Bye')

# Check Batterylevel
def check_battery():
    print ConvertVoltage(ReadChannel(CH_SUPPLY),2)

# Get Temperature
def getTemp():
    logger.debug('Accessing Temperature')
    os.system('sudo rmmod rtc_ds1307')
    byte_tmsb = I2CBUS.read_byte_data(I2CADDRESS,0x11)
    byte_tlsb = bin(I2CBUS.read_byte_data(I2CADDRESS,0x12))[2:].zfill(8)
    os.system('sudo modprobe rtc_ds1307')
    temperature = byte_tmsb+int(byte_tlsb[0])*2**(-1)+int(byte_tlsb[1])*2**(-2)
    logger.debug('Temperature: %.1f °C', round(temperature,1))
    return round(temperature,1)

# Check Diskspace sufficent
def check_disk():
    st = os.statvfs("/")
    free = st.f_bavail * st.f_frsize
    logger.debug('Free: %s', convert_size(free))
    logger.debug('Total:  %d', st.f_blocks * st.f_frsize)
    logger.debug('Used:  %d', (st.f_blocks - st.f_bfree) * st.f_frsize)
    if free < DISK_WARNING:
        led_state[LED_ERR] = LED_FAST
        return True
    elif free < DISK_ERROR:
        led_state[LED_ERR] = LED_ON
        return False
    else:
        return True

# Convert Size in Bytes into human readable String
def convert_size(size_bytes):
   if size_bytes == 0:
       return "0B"
   size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return "%s %s" % (s, size_name[i])

# Delete all measurements
def del_data():
    for the_file in os.listdir(DATAPATH):
        file_path = os.path.join(DATAPATH, the_file)
        try:
            logger.debug('Deleting: %s',file_path)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(e)

# Update Sampling Rate
def update_samplingrate():
    global samplingrate
    if (GPIO.input(PIN_SW_SAMPLING0)==0 and GPIO.input(PIN_SW_SAMPLING1)==0):
        samplingrate = SAMPLING_1
    elif(GPIO.input(PIN_SW_SAMPLING0)==0 and GPIO.input(PIN_SW_SAMPLING1)==1):
        samplingrate = SAMPLING_2
    elif(GPIO.input(PIN_SW_SAMPLING0)==1 and GPIO.input(PIN_SW_SAMPLING1)==0):
        samplingrate = SAMPLING_3
    elif(GPIO.input(PIN_SW_SAMPLING0)==1 and GPIO.input(PIN_SW_SAMPLING1)==1):
        samplingrate = SAMPLING_4
    logger.info('Set Samplingrate to %ds', samplingrate)

# Button Action start
def bt_start_action(channel):
    if(measurement.is_running == True and measurement.is_paused == False):
        logger.info('Pausing Measurement')
        measurement.pause()
    elif(measurement.is_running == True and measurement.is_paused == True):
        logger.info('Restarting Measurement')
        measurement.restart()
    elif(measurement.is_running == False):
        logger.info('Starting Measurement')
        measurement.start()

# Button Action start
def bt_stop_action(channel):
    #logger.debug('Button Stop pressed')
    # Detect Length of Buttonpress
    stopcounter = 0
    while GPIO.input(PIN_BT_STOP) == 0:
        stopcounter += 10
        sleep(0.01)
    if stopcounter <= TM_SHORT:
        #logger.debug('Shortpress')
        if measurement.is_running:
            logger.info('Stopping Measurement')
            measurement.stop()
        else:
            # Fehlerausgabe quittieren und abschalten
            logger.info('Clear Errors')
            led_state[LED_ERR] = LED_OFF
    elif stopcounter > TM_SHORT :
        #logger.debug('Longpress')
        logger.info('Shutdown now')
        shutdown_now()

# Button Action start
def bt_usb_action(channel):
    #logger.debug('Button USB pressed')
    # Detect Length of Buttonpress
    stopcounter = 0
    while GPIO.input(PIN_BT_USB) == 0:
        stopcounter += 10
        sleep(0.01)
    if stopcounter <= TM_SHORT:
        logger.info('Copy to USB')
        led_state[LED_USB] = LED_ON
        y=subprocess.call([USBSCRIPT, DATAPATH])
        if y == 0:
            logger.debug('USB copy successful')
        elif y == 1:
            led_state[LED_ERR] = LED_SLOW
            logger.debug('USB Stick not found')
        elif y == 2:
            led_state[LED_ERR] = LED_FAST
            logger.debug('Checksum Error')
        else:
            pass
        led_state[LED_USB] = LED_OFF
    elif stopcounter > TM_SHORT :
        logger.info('Deleting Files')
        led_state[LED_USB] = LED_ON
        led_state[LED_ERR] = LED_ON
        del_data()
        led_state[LED_USB] = LED_OFF
        led_state[LED_ERR] = LED_OFF

# Create a CSV File
def csv_creator(filename):
    logger.debug('Creating file %s', filename)
    with open(filename, "wb") as csv_file:
        writer = csv.writer(csv_file, delimiter=',')
        writer.writerows([['Raspicorder Logfile'],
                        ['Firma:',COMPANY],
                        ['Datum:',datetime.now().strftime('%d.%m.%Y')],
                        ['Startzeit:',datetime.now().strftime('%H:%M:%S')],
                        [],
                        ['Zeit','Spannung','Strom']])

# Add a line to a CSV file
def csv_writer(data, filename):
    logger.debug('Writing %s to file %s',data, filename)
    with open(filename, "a") as csv_file:
        writer = csv.writer(csv_file, delimiter=',')
        for line in data:
            writer.writerow(line)

# Write Data Sample to CSV File
def reg_data():
    csv_writer([[(int(round(time.time()))-measurement.get_start()-measurement.get_totalpause()),
        ConvertVoltage(ReadChannel(CH_VOLTAGE),2),
        ConvertCurrent(ReadChannel(CH_CURRENT),2)]],measurement.get_filename())

# Init GPIO Pins
def init_gpio():
    logger.info('GPIO initialize start.')
    #setup GPIO using Board numbering
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    # LED Setup
    GPIO.setup(PIN_LED_RDY, GPIO.OUT)
    GPIO.setup(PIN_LED_REC, GPIO.OUT)
    GPIO.setup(PIN_LED_USB, GPIO.OUT)
    GPIO.setup(PIN_LED_ERR, GPIO.OUT)

    # Buttons Setup
    GPIO.setup(PIN_BT_START, GPIO.IN)
    GPIO.setup(PIN_BT_STOP, GPIO.IN)
    GPIO.setup(PIN_BT_USB, GPIO.IN)
    GPIO.setup(PIN_SW_SAMPLING0, GPIO.IN)
    GPIO.setup(PIN_SW_SAMPLING1, GPIO.IN)
    GPIO.add_event_detect(PIN_BT_START, GPIO.FALLING, callback=bt_start_action, bouncetime=150)
    GPIO.add_event_detect(PIN_BT_STOP, GPIO.FALLING, callback=bt_stop_action, bouncetime=150)
    GPIO.add_event_detect(PIN_BT_USB, GPIO.FALLING, callback=bt_usb_action, bouncetime=150)
    GPIO.add_event_detect(PIN_SW_SAMPLING0, GPIO.BOTH, callback=update_samplingrate, bouncetime=150)
    GPIO.add_event_detect(PIN_SW_SAMPLING1, GPIO.BOTH, callback=update_samplingrate, bouncetime=150)
    logger.info('GPIO initialize done.')

###############################################################################
# Klassen
###############################################################################

# Messung starten
class Messung(object):
    def __init__(self):
        self.reset()

    def reset(self):
        #General init stuff
        self.is_running = False
        self.is_paused = False
        self.filename = ""
        self.starttime = 0
        self.total_pausetime = 0
        self.pause_started = 0

    def start(self):
        logger.info('Starting new Measurement')
        #reset all values
        self.reset()
        self.filename = os.path.join(DATAPATH, datetime.now().strftime('%Y%m%d-%H%M%S-record.csv'))
        self.starttime = int(round(time.time()))
        #Uodate Samplingrate
        update_samplingrate()
        self.samplingrate = samplingrate
        #Check Disk Space
        check_disk()
        #Create File
        csv_creator(self.filename)
        self.is_running = True
        led_state[LED_RDY] = LED_OFF

    def restart(self):
        led_state[LED_RDY] = LED_OFF
        self.total_pausetime += (int(round(time.time()))-self.pause_started)
        self.is_paused = False

    def pause(self):
        logger.info('Pausing Measurement')
        led_state[LED_RDY] = LED_FAST
        self.pause_started = int(round(time.time()))
        self.is_paused = True

    def stop(self):
        logger.info('Stopping Measurement')
        led_state[LED_RDY] = LED_ON
        self.is_running = False

    def is_paused(self):
        return self.is_paused

    def is_running(self):
        return self.is_running

    def get_filename(self):
        return self.filename

    def get_start(self):
        return self.starttime

    def get_samplingrate(self):
        return self.samplingrate

    def get_totalpause(self):
        return self.total_pausetime


###############################################################################
# Globals
###############################################################################
led_state           = [0,0,0,0]
shutdown            = False
measurement         = Messung()

t_led_rdy = threading.Thread(name='LED_RDY', target=handle_led, args=(PIN_LED_RDY, LED_RDY))
t_led_rec = threading.Thread(name='LED_REC', target=handle_led, args=(PIN_LED_REC, LED_REC))
t_led_err = threading.Thread(name='LED_ERR', target=handle_led, args=(PIN_LED_ERR, LED_ERR))
t_led_usb = threading.Thread(name='LED_USB', target=handle_led, args=(PIN_LED_USB, LED_USB))
t_data = threading.Thread(name='DATA',target=register_data)

t_led_rdy.setDaemon(True)
t_led_rec.setDaemon(True)
t_led_err.setDaemon(True)
t_led_usb.setDaemon(True)

###############################################################################
# Main Program
###############################################################################

def main(debug=None):
    #print debug
    # Init everything
    init_gpio()

    t_led_rdy.start()
    t_led_rec.start()
    t_led_err.start()
    t_led_usb.start()
    t_data.start()

    getTemp()
    led_state[LED_ERR] = LED_ON

    while (shutdown == False):
        pass

    t_led_rdy.join()
    t_led_rec.join()
    t_led_err.join()
    t_led_usb.join()
    t_data.join()
    sys.exit()
    #os.system("shutdown now -h")

if __name__ == "__main__" :
    print sys.argv
    main(*sys.argv[1:])
