# raspicorder

You must install usbmount on your target.
    sudo apt-get install usbmount
    
and configure as following:
    FS_MOUNTOPTIONS="-fstype=vfat,gid=users,dmask=0007,fmask=0117"
    

