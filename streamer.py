# IF YOU FOUND THIS USEFUL, Please Donate some Bitcoin .... 1FWt366i5PdrxCC6ydyhD8iywUHQ2C7BWC

# !/usr/bin/env python3
# -*- coding: utf-8 -*-

from ig import API
import pandas as pd
import time
import datetime
import numpy as np

import logging

# Setup logging
LOG_FILENAME = 'streamer-logfile.txt'
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%y-%m-%d %H:%M:%S',
                    filename=LOG_FILENAME,
                    filemode='w')

# Setup simple logging to console @ INFO
console = logging.StreamHandler()
console.setLevel(logging.INFO)
#console.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

api = API()

class TickDB:
    agg_size = 100  # size of buffer before aggregation is triggered
    keep_time_secs = 5  # only aggregate ticks more than 3 seconds old, to avoid splitting up partial reads
    def __init__(self):
        logging.debug('streamer.py TickDB __init__:')
        self._idx = 0
        self._tick_buffer = self.initialise_tick_buffer()
        self._tick_df = pd.DataFrame(columns=['idx',
                                              'timestamp',
                                              'epic_id',
                                              'O', 'H', 'L', 'C', 'spread'])

    def initialise_tick_buffer(self):
        return pd.DataFrame(columns=['idx',
                                     'timestamp',
                                     'epic_id',
                                     'bid',
                                     'offer',
                                     'time_delta'])
        
    def add_tick(self, new_data):
        logging.debug('streamer.py TickDB add_tick:')
        logging.debug(new_data)
        self._idx += 1
        new_data['idx'] = self._idx
        self._tick_buffer = self._tick_buffer.append(new_data, ignore_index=True)

        if (self._idx % self.agg_size) == 0:
            logging.debug('streamer.py TickDB add_tick: Aggregating')
            # Aggregate data in buffer if old enough, move to DF
            self._tick_buffer['time_delta'] = self._tick_buffer['timestamp'].copy() - time.time()
            aggregated = self.aggregate_ticks(self._tick_buffer.loc[self._tick_buffer['time_delta'].abs() > self.keep_time_secs, :])
            self._tick_df = self._tick_df.append(aggregated, ignore_index=True)
            # self._tick_buffer = self.initialise_tick_buffer()  # Clear buffer
            self._tick_buffer = self._tick_buffer.loc[self._tick_buffer['time_delta'].abs() <= self.keep_time_secs, :]

    def aggregate_ticks(self, tick_data):
        logging.debug('streamer.py TickDB aggregate_ticks:')
        # Calculate OHLC for each epic each second
        aggregated_OHLC = pd.DataFrame()
        for epic_id in tick_data['epic_id'].unique():
            tick_subset1 = tick_data.loc[tick_data['epic_id'] == epic_id, :]
            for timestamp in tick_subset1['timestamp'].unique():
                tick_subset2 = tick_subset1.loc[tick_subset1['timestamp'] == timestamp, :]
                # Calculate key values
                spread = (tick_subset2['offer'] - tick_subset2['bid']).mean()
                mid_prices = ((tick_subset2['offer'] + tick_subset2['bid']) / 2)
                O = mid_prices.head(1).values[0]
                H = mid_prices.max()
                L = mid_prices.min()
                C = mid_prices.tail(1).values[0]

                this_row = {'timestamp': timestamp, 'epic_id': epic_id, 'O': O, 'H': H, 'L': L, 'C': C, 'spread': spread}

                aggregated_OHLC = aggregated_OHLC.append(this_row, ignore_index=True)

        return aggregated_OHLC


# listener function
def handle_update(item_update):
    logging.debug('streamer.py handle_update:')
    logging.debug(item_update)
    print(item_update)
    try:
        # Rehash data, and append to data table
        epic_id = item_update['name'].strip('MARKET:')
        datestr = datetime.datetime.now().strftime("%Y-%m-%d ") + item_update['values']['UPDATE_TIME']
        timestamp = int(time.mktime(datetime.datetime.strptime(datestr, "%Y-%m-%d %H:%M:%S").timetuple()))

        new_row = {'timestamp': timestamp,
                   'epic_id': epic_id,
                   'bid': float(item_update['values']['BID']),
                   'offer': float(item_update['values']['OFFER'])}

        tick_db.add_tick(new_row)
    except:
        logging.warning('streamer.py handle_update: Unable to handle item_update')


#%%
        
# Data storage
tick_db = TickDB()

# Manage subscriptions
epic_list = ["IX.D.FTSE.CFD.IP",
             "CS.D.BITCOIN.CFD.IP"]

for epic_id in epic_list:
    res = api.subscribe(epic_id, listener=handle_update)

# api.clientsentiment(epic_id)
    
time_base = time.time()
hold = True
wait_secs = 3600
save_file = 'tick_data_'
file_counter=0

while hold:
    if (time.time()-time_base) > wait_secs:
        print('Saving data...')
        tick_db._tick_df.to_csv(save_file+'%04d'%file_counter+'.csv')
        file_counter += 1
        time_base = time.time()
    else:
        time.sleep(10)   
        
#%%

input("Hit any key to exit...")

for epic_id in epic_list:
    res = api.unsubscribe(epic_id)
    
tick_data = tick_db._tick_df

