#!/usr/bin/env python
"""
 Name:        sidfile.py
 Purpose:     Usage 1: Provide a Class to handle SID and SuperSID formatted files
              Usage 2: Please refer to the USAGE string for utilities information


 Author:      Eric Gibert

 Created:     13-10-2012
 Copyright:   (c) eric 2012
 Licence:     Open to All
"""
from __future__ import print_function   # use the new Python 3 'print' function
from datetime import datetime, timedelta
import numpy
from matplotlib.mlab import movavg

USAGE = """
Provide some utilities to manipulate SID/SuperSID files:
    - When one file is given as argument:
       - file is SID Format: DISPLAY some information - good for debugging
       - file is SuperSID format: SPLIT to one file per station in SID format
    - When two files are given as arguments:
       - both files are SID Format: MERGE in one SID Format
       - one file is SuperSID and one is SID: MERGE the SID file with the matching station from SuperSId file
       - both are SuperSID: MERGE in one SuperSID with "station to station" matching
"""

class SidFile():
    """Class to read SID or SuperSID files. 
    Provides header information and data content access.
    """
    _timestamp_format = "%Y-%m-%d %H:%M:%S"
    def __init__(self, filename = "", sid_params = {}, force_read_timestamp = False):
        """Two ways to create a SIDfile:
        1) A file already exists and you want to read it: use 'filename'
        2) A new empty file needs to be created: use 'sid_params'
            to indicate the parameters of the file's header.
            The dictionary retrieved from a config file can be used.
            Usually this means you need to write that file after data collection.
        
        Note: only one or the other parameter should be given. If both are given
        then 'filename' is taken and 'sid_params' is ignored.
        """
        self.version = "1.3.1 20130817"
        self.filename = filename
        self.sid_params = sid_params    # dictionary of all header pairs
        self.is_extended = False

        if filename:
            # Read all lines in a buffer used by 'read_data' and 'read_header'
            try:
                with open(self.filename,"rt") as fin:
                    self.lines = fin.readlines()
            except IOError as why:
                print ("Error reading", filename)
                print(str(why))
                exit(1)
            
            self.read_header()
            self.control_header()
            self.read_data(force_read_timestamp)

        elif self.sid_params:
            # create zeroes numpy arrays to receive data
            self.control_header()
            self.clear_buffer()

    def clear_buffer(self, next_day=False):
        """creates zeroes numpy arrays to receive data and generates the timestamp vector"""
        nb_data_per_day = int ( (24 * 3600) / self.LogInterval)
        if next_day:
            self.data.fill(0.0)
            self.startTime += timedelta(days=1)
        else:
            self.data = numpy.zeros((len(self.stations), nb_data_per_day))
        # create an array containing the timestamps for each data reading, default initialization     
        self.generate_timestamp()

    def control_header(self):
        '''Perform sanity check and assign standard attributes in a format independent way.
           SuperSID files have an entry "Stations" while SID files have "StationID"'''
        if "stations" in self.sid_params:
            self.isSuperSID = True
            self.stations = self.sid_params["stations"].split(",")
            self.frequencies = self.sid_params["frequencies"].split(",")
        elif "stationid" in self.sid_params:
            self.isSuperSID = False
            self.stations = [ self.sid_params["stationid"] ]
            self.frequencies = [ self.sid_params["frequency"] ]
        else:
            print("ERROR: No station ID found in this file or configuration. Please check!")
            exit(5)

        # get the datetime for UTC_StartTime
        if not self.sid_params.has_key("utc_starttime"):
            utcnow = datetime.utcnow()
            self.sid_params["utc_starttime"] = "%d-%02d-%02d 00:00:00" % (utcnow.year, utcnow.month, utcnow.day)
        self.UTC_StartTime = self.sid_params["utc_starttime"]
        SidFile._timestamp_format = "%Y-%m-%d %H:%M:%S"
        self.startTime = SidFile._StringToDatetime(self.sid_params["utc_starttime"])

        # do we have a LogInterval ?
        if self.sid_params.has_key("log_interval"):
            self.LogInterval = int(self.sid_params["log_interval"])
        elif self.sid_params.has_key("loginterval"):
            self.LogInterval = int(self.sid_params["loginterval"])
        else:
            print ("Warning: Log_Interval is missing! Please check. I assume 5 sec...")
            self.LogInterval, self.sid_params["log_interval"] = 5, 5

    def read_header(self):
        """Reads the first lines of a SID file to extract the 'sid_params'.
        No more file access: all in memory using 'self.lines'
        """
        self.sid_params.clear()
        self.headerNbLines = 0  # number of header lines
        for line in self.lines:
            if line[0] != "#": break   # end of header
            self.headerNbLines += 1
            tokens = line.split("=")
            if len(tokens) == 2:
                # remove the '#' and force the key to lower case to avoid ambiguity from user's supersid.cfg
                key = tokens[0][1:].strip().lower()  
                self.sid_params[key] = tokens[1].strip()

    def read_data(self, force_read_timestamp = False):
        """Using the self.lines buffer, converts the data lines in numpy arrays.
            - One array self.data for the data (one column/vector per station)
            - One array self.timestamp for the timestamps (i.e. timestamp vector)
        Reading method differs accordingly to the self.isSuperSID flag
        New: Extended format supports a timestamp for SuperSID format as well as .%f for second decimals
        """
        first_data_line = self.lines[self.headerNbLines].split(",")
        if '-' in first_data_line[0]: # yes, a time stamp is found in the first data column
            try:
                datetime.strptime(first_data_line[0], "%Y-%m-%d %H:%M:%S.%f")
                self.is_extended = True
                SidFile._timestamp_format = "%Y-%m-%d %H:%M:%S.%f"
            except ValueError:
                datetime.strptime(first_data_line[0], "%Y-%m-%d %H:%M:%S")
                self.is_extended = False
                SidFile._timestamp_format = "%Y-%m-%d %H:%M:%S"
            
        if self.isSuperSID and not self.is_extended:
            # classic SuperSID file format: one data column per station, no time stamp (has to be generated)
            print ("Warning: read SuperSid non extended file and generate time stamps.")  
            self.data = numpy.loadtxt(self.lines, comments='#', delimiter=",").transpose()
            self.generate_timestamp()
        elif self.isSuperSID and self.is_extended:
            # extended SuperSID file format: one extended time stamp then one data column per station
            print ("Warning: read SuperSid extended file, time stamps are read & converted from file.")
            inData = numpy.loadtxt(self.lines, dtype=datetime, comments='#', delimiter=",", converters={0: SidFile._StringToDatetime})
            self.timestamp = inData[:,0] # column 0
            self.data = numpy.array(inData[:,1:], dtype=float).transpose() 
        else:
            # classic SID file format: 
            # two columns file: [timestamp, data]. Try to avoid reading timestamps: date str to num conversion takes time
            # self.data must still be a 2 dimensions numpy.array even so only one vector is contained
            if len(self.lines) - self.headerNbLines != (60 * 60 * 24) / self.LogInterval  \
            or force_read_timestamp or self.is_extended:
                print ("Warning: read SID file, timestamps are read & converted from file.")
                inData = numpy.loadtxt(self.lines, dtype=datetime, comments='#', delimiter=",", converters={0: SidFile._StringToDatetime})
                self.timestamp = inData[:,0] # column 0
                self.data = numpy.array(inData[:,1], dtype=float, ndmin=2) # column 1
            else:
                print ("Optimization: read SID file, generate timestamp instead of reading & converting them from file.")
                self.data = numpy.array(numpy.loadtxt(self.lines, comments='#', delimiter=",", usecols=(1,)), ndmin=2) # only read data column
                self.generate_timestamp()
        #print("self.data.shape =", self.data.shape)


    @classmethod
    def _StringToDatetime(cls, strTimestamp):
        return datetime.strptime(strTimestamp, SidFile._timestamp_format)


    def generate_timestamp(self):
        """Create the timestamp vector by adding LogInterval seconds to UTC_StartTime"""
        self.timestamp = numpy.empty(len(self.data[0]), dtype=datetime)
        # add 'interval' seconds to UTC_StartTime for each entries
        interval =  timedelta(seconds=self.LogInterval)
        currentTimestamp = self.startTime
        for i in range(len(self.timestamp)):
            self.timestamp[i] =  currentTimestamp
            currentTimestamp += interval

    def get_station_data(self, stationId):
        """Return the numpy array of the given station's data"""
        if stationId not in self.stations:
            return []
        elif self.isSuperSID:
            idx = self.stations.index(stationId)
            return self.data[:,idx]
        else:
            return self.data

    def create_header(self, isSuperSid, log_type):
        """ Create a string matching the SID/SuperSID file header.
        Ensure the same header on both formats.
        - isSuperSid: request a SuperSid header if True else a SID header
        - log_type: must be 'raw' or 'filtered'
        """
        hdr = "%s %s\n" % ("# Site =", self.sid_params['site_name'] if 'site_name' in self.sid_params else self.sid_params['site'])
        if 'contact' in self.sid_params:
            hdr += "%s %s\n" % ("# Contact =", self.sid_params['contact'])
        hdr += "%s %s\n" % ("# Longitude =", self.sid_params['longitude'])
        hdr += "%s %s\n" % ("# Latitude =", self.sid_params['latitude'])
        hdr += "#\n"
        hdr += "%s %s\n" % ("# UTC_Offset =", self.sid_params['utc_offset'])
        hdr += "%s %s\n" % ("# TimeZone =", self.sid_params['time_zone'] if 'time_zone' in self.sid_params else self.sid_params['timezone'])
        hdr += "#\n"
        hdr += "%s %s\n" % ("# UTC_StartTime =", self.sid_params['utc_starttime']) #  + strftime("%Y-%m-%d %H:%M:%S", gmtime(date_begin_epoch)
        hdr += "%s %s\n" % ("# LogInterval =", self.sid_params['log_interval'] if 'log_interval' in self.sid_params else self.sid_params['loginterval'])
        hdr += "%s %s\n" % ("# LogType =", log_type)
        hdr += "%s %s\n" % ("# MonitorID =", self.sid_params['monitor_id'] if 'monitor_id' in self.sid_params else self.sid_params['monitorid'])
        if isSuperSid:
            hdr += "%s %s\n" % ("# Stations =", self.sid_params['stations'])
            hdr += "%s %s\n" % ("# Frequencies =", self.sid_params['frequencies'])
        else:
            hdr += "%s %s\n" % ("# StationID =", self.sid_params['stationid'])
            hdr += "%s %s\n" % ("# Frequency =", self.sid_params['frequency'])
        return hdr

    def get_station_index(self, station):
        """Returns the index of the station accordingly to the parameter station type"""
        if type(station) is int:
            assert( 0 <= station < len(self.stations) )
            return  station
        elif type(station) is str: # should be a station name/call_sign
            return self.stations.index(station)  # throw a ValueError if 'station' is not in the list
        elif type(station) is dict:
            return self.stations.index(station['call_sign'])  # throw a ValueError if 'station' is not in the list
        else:
            return self.stations.index(station.call_sign)  # throw a ValueError if 'station' is not in the list

    def write_data_sid(self, station, filename, log_type, apply_bema = True, extended = False):
        """Write in the file 'filename' the dataset of the given station using the SID format
        i.e. "TimeStamp, Data" lines
        Header respects the SID format definition i.e. conversion if self is SuperSid
        """
        iStation = self.get_station_index(station)
        # need extra information to create the header's SID file parameters if the exiting file is SuperSID
        if self.isSuperSID: 
            self.sid_params['stationid'] = self.stations[iStation]
            self.sid_params['frequency'] = self.frequencies[iStation]
            
        # intermediate buffer to have 'raw' or 'filtered' data
        if log_type == 'raw' or apply_bema == False:
            tmp_data = self.data[iStation]
        else: # filtered
            tmp_data = SidFile.filter_buffer(self.data[iStation], self.LogInterval);        
        # write file in SID format
        with open(filename, "wt") as fout:
            # generate header
            hdr = self.create_header(isSuperSid = False, log_type = log_type)
            print(hdr, file=fout, end="")
            # generate the "timestamp, data" serie i.e. data lines
            timestamp_format = "%Y-%m-%d %H:%M:%S.%f" if extended else "%Y-%m-%d %H:%M:%S"
            for t_stamp, x in zip(self.timestamp, tmp_data):
                print("%s, %.15f" % (t_stamp.strftime(timestamp_format), x), file=fout)

    def write_data_supersid(self, filename, log_type, apply_bema = True, extended = False):
        """Write the SuperSID file. Attention: self.sid_params must contain all expected entries."""
        # force to SuperSid format
        hdr = self.create_header(isSuperSid = True, log_type = log_type)
        # create file and write header
        with open(filename, "wt") as fout:
            print(hdr, file=fout, end="")
            # intermediate buffer to have 'raw' or 'filtered' data
            if log_type == 'raw' or apply_bema == False:
                tmp_data = self.data
            else: # filtered
                tmp_data = []
                for stationData in self.data:
                    tmp_data.append(SidFile.filter_buffer(stationData, self.LogInterval))
                tmp_data = numpy.array(tmp_data)       
            #print(tmp_data.shape)  # should be like (2, 17280)
            if extended:
                for t_stamp, row in zip(self.timestamp, numpy.transpose(tmp_data)):
                    floats_as_strings = ["%.15f" % x for x in row]             
                    print( t_stamp.strftime("%Y-%m-%d %H:%M:%S.%f,"), ", ".join(floats_as_strings), file=fout)                
            else:
                for row in numpy.transpose(tmp_data):
                    floats_as_strings = ["%.15f" % x for x in row]
                    print(", ".join(floats_as_strings), file=fout)
        
        # append data to file using numpy function (symmetric to loadtxt)
        # note for future: version 1.7 offers "header=hdr" as new function parameter
        # but for now (1.6) we write header first then savetxt() append data lines
        #numpy.savetxt(filename, tmp_data, delimiter=",", newline="\n", header=hdr)  

    @classmethod
    def filter_buffer(cls, raw_buffer, data_interval, bema_wing = 6, gmt_offset = 0):
            '''
            Return bema filtered version of the buffer, with optional time_zone_offset.
            bema filter uses the minimal found value to represent the data points within a range (bema_window)
            bema_wing = 6 => window = 13 (bema_wing + evaluating point + bema_wing)
            '''
            length = len(raw_buffer)
            # Extend 2 wings to the raw data buffer before taking min and average
            dstack = numpy.hstack((raw_buffer[length-bema_wing:length],\
                                   raw_buffer[0:length],\
                                   raw_buffer[0:bema_wing]))
            # Fill the 2 wings with the values at the edge
            dstack[0:bema_wing] = raw_buffer[0]  #  dstack[bema_wing]
            dstack[length+bema_wing:length+bema_wing*2] = raw_buffer[-1]  # dstack[length+bema_wing-1]    
            # Use the lowest point found in window to represent its value
            dmin = numpy.zeros(len(dstack))
            for i in range(bema_wing, length+bema_wing):
                dmin[i] = min(dstack[i-bema_wing:i+bema_wing])
            # The points beyond the left edge, set to the starting point value
            dmin[0:bema_wing] = dmin[bema_wing]
            # The points beyond the right edge, set to the ending point value
            dmin[length+bema_wing:length+bema_wing*2] = dmin[length+bema_wing-1]
            # Moving Average. This actually truncates array to original size
            daverage = movavg(dmin, (bema_wing*2+1))
        
            if gmt_offset == 0:
                return daverage
            else:
                gmt_mark = gmt_offset * (60/data_interval) * 60
                doffset = numpy.hstack((daverage[gmt_mark:length],daverage[0:gmt_mark]))
                return doffset

if __name__ == '__main__':
    import sys
    from os import path
    fname = lambda x: "%s.merge%s" % path.splitext(x)  # /original/path/name.merge.ext
    # check that one or two arguments are given
    if not(2 <= len(sys.argv) <= 3):
        print (USAGE)
        exit()
    # one argument only
    elif len(sys.argv) == 2: 
        sid = SidFile(sys.argv[1], force_read_timestamp = True)
        if sid.is_extended:
            print("Time stamps are extended.")
        if sid.isSuperSID:
            print("SuperSID file format: -- Header information --")
            for key, value in sid.sid_params.iteritems():
                print(" " * 5, key, "=", value)
            print("Monitored Stations List:", sid.stations)
            print("Dataset shape:", sid.data.shape)
            # explode this SuperSID file in one file per station in SID format
            answer = raw_input("Proceed to split this SuperSID file in %d SID files? [y/N]" % sid.data.shape[0])
            if answer == 'y':
                for station in sid.stations:
                    fname = "%s/%s_%s_%s.split.csv" % (path.dirname(sid.filename),
                                                 sid.sid_params['site'], 
                                                 station, 
                                                 sid.sid_params['utc_starttime'][:10])
                    print(fname, "created.")
                    sid.write_data_sid(station, fname, sid.sid_params['logtype'], apply_bema = False)   
        else:
            print("SID File Format: -- Header information --")
            for key, value in sid.sid_params.iteritems():
                print(" " * 5, key, "=", value)
            print("Stations:", sid.stations)
            print("Start Time:", sid.startTime)
            print("Number of TimeStamps:", len(sid.timestamp))
            print("Dataset shape:", sid.data.shape)
            print(sid.data[0][5881:5891])
            print(sid.timestamp[5881:5891])
    # two files given as arguments    
    else:  
        sid1, sid2 = SidFile(sys.argv[1]), SidFile(sys.argv[2])
        # two SuperSID files to merge station by station
        if sid1.isSuperSID and sid2.isSuperSID:
            for istation in range(len(sid1.stations)):
                sid1.data[:, istation] += sid2.get_station_data(sid1.stations[istation])
            sid1.write_data_supersid(fname(sid1.filename))
            print(fname(sid1.filename), "created.")
            
        # one SID file and one SuperSID file: merge the SuperSID's matching station to SDI file       
        elif sid1.isSuperSID != sid2.isSuperSID:
            if sid1.isSuperSID:
                supersid = sid1
                sid = sid2
            else:
                sid = sid1
                supersid = sid2
            station = sid.stations[0]
            if station not in supersid.stations:
                print("Error: station %s in not found in the superSId file. Cannot merge." % station)
            else:
                sid.data += supersid.get_station_data(station)
                sid.write_data_sid(station, fname(sid.filename))
                print(fname(sid.filename), "created.")
        # two SID files to merge in one SID file - sid1's header is kept
        else:
            sid1.data += sid2.data
            sid1.write_data_sid(sid1.stations[0], fname(sid1.filename), sid1.sid_params['logtype'], apply_bema = False)
            print(fname(sid1.filename), "created.")                
             
            

