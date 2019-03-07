import os
import sys
from pkg_resources import require
require('cothread==2.12')
require('epicsdbbuilder==1.0')
require('numpy>=1.10')
require('scipy>=0.16')
# require('pytac')
# require('at-python')


here = os.path.realpath('.')
sys.path.append(os.path.split(here)[0])


from softioc import builder, softioc
import atip
import atip_server


# Create lattice.
lattice = atip.utils.loader()

# Create PVs.
server = atip_server.ATIPServer(lattice, os.path.join(here, 'feedback.csv'))

# Add special case out record for SOFB to write to.
builder.SetDeviceName('CS-CS-MSTAT-01')
builder.aOut('FBHEART', initial_value=10)

# Start the IOC.
builder.LoadDatabase()
softioc.iocInit()

softioc.interactive_ioc(globals())
