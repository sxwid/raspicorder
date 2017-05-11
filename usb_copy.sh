#!/bin/bash
# call with path as first argument (/home/pi/data/)
# Check for USB device

DATA_PATH=$1
USB_PATH="/media/usb/"

if [ -w $USB_PATH ]; then
    #echo "USB Pfad schreibbar"
    cp -r $DATA_PATH $USB_PATH
    cd $DATA_PATH
    find -type f -exec md5sum "{}" + > /tmp/checklist.chk
    cd $USB_PATH/$(basename $DATA_PATH)
    md5sum -c --quiet /tmp/checklist.chk
    if [ $? -eq 0 ]; then
        #echo "Checksum ok"
        rm /tmp/checklist.chk
        exit 0
    else
        #echo "Error Checksum"
        rm /tmp/checklist.chk
        exit 2
    fi

else
    #echo "Fehler, USB Pfad nicht beschreibbar "
    exit 1
fi
