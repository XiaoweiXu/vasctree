#processendpointSet5x5.py

"""takes the output from 5x5Config_of_Endpoints.py and returns
Orientedendpoints5x5.pckle. The main purpose of this code is to make sure
the the endpoints are aligned in the same direction for the 5x5 neighborhood,
to be sure they are all rotationally invariant"""

from sliceOrientation import OrientMask
import sys
import cPickle
import numpy as na

def main():
    fle=open("Configuration5x5.pckle",'rb') #Contains a list of 2
    data = cPickle.load(fle)
    output=open("OrientedEndpoints5x5.pckle",  'wb')
    modifiedEp = []
    """The original code used barring any exceptions"""
    print "%d endpoints"%len(data[0])
    count =0
    for ep in data[0]:
        count +=1
        if len(ep)<5:
            print count
            pass
        else:
            om = OrientMask(ep)
            om.orient()
            modifiedEp.append(om.mask) 
        print len(modifiedEp)
    cPickle.dump(modifiedEp , output)

if __name__ == '__main__':
    main()
