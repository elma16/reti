#!/usr/bin/env python3

'''
Given a pgn of games by a person, extract the score against people in different “rating brackets”
'''

import re
import sys
import numpy as np
from scipy.interpolate import interp1d
from datetime import datetime
'''
Check to make sure this is a collection of games by a single player.
'''

player_name = sys.argv[1]
db_name = sys.argv[2]

with open(db_name) as f:
    content = str(f.readlines())

w_re_str = r'White\s"' + re.escape(player_name) + r'"'
b_re_str = r'Black\s"' + re.escape(player_name) + r'"'

w_game_evals = re.findall(w_re_str, content)
b_game_evals = re.findall(b_re_str, content)
event = re.findall(r'Event',content)

assert((len(w_game_evals)+len(b_game_evals) == len(event)) and len(event) != 0)

'''
Compute the score with respect to people from different rating brackets
'''

white_players = re.findall('(?<=White\s\").*?(?=\")', content)
whiteelo = re.findall(r'WhiteElo\s\"\d{1,4}\"', content)
blackelo = re.findall(r'BlackElo\s\"\d{1,4}\"', content)
results = re.findall(r'Result\s".{3,7}"', content)

w_elo = []
b_elo = []
result_array = []
for w, b, r in zip(whiteelo,blackelo,results):
    w_elo.append(int(w.split()[1][1:-1]))
    b_elo.append(int(b.split()[1][1:-1]))
    result_array.append(r.split()[1][1:-1])

assert(len(w_elo) == len(b_elo) == len(result_array))

elo_result = []
player_elo = []
for idx in range(len(result_array)):
    if white_players[idx] == player_name:
        if result_array[idx] == '1-0':
            result_array[idx] = 'W'
        elif result_array[idx] == '0-1':
            result_array[idx] = 'L'
        else:
            result_array[idx] = 'D'
        elo_result.append((b_elo[idx],result_array[idx]))
        player_elo.append(w_elo[idx])
    else:
        if result_array[idx] == '1-0':
            result_array[idx] = 'L'
        elif result_array[idx] == '0-1':
            result_array[idx] = 'W'
        else:
            result_array[idx] = 'D'
        elo_result.append((w_elo[idx],result_array[idx]))
        player_elo.append(b_elo[idx])

import matplotlib.pyplot as plt
import pandas as pd

'''
Histogram by rating, then overlay?
'''

elo_win = [x[0] for x in elo_result if x[1] == 'W']
elo_loss = [x[0] for x in elo_result if x[1] == 'L']
elo_draw = [x[0] for x in elo_result if x[1] == 'D']

plt.hist(elo_win,bins=100,alpha=0.5,label='win')
plt.hist(elo_loss,bins=100,alpha=0.5,label='loss')
plt.hist(elo_draw,bins=100,alpha=0.5,label='draw')
plt.xlabel("Opponent Elo")
plt.ylabel('Frequency')
plt.title('Frequency of win/loss/draw for {}'.format(player_name))
plt.axvline(x=np.mean(player_elo), color='b', label='Avg Rating')
plt.legend()
plt.show()

'''
Plot the rating change of the player over time
'''
#predict = interp1d(player_elo[::-1],np.arange(0,len(player_elo[::-1])),kind='slinear',fill_value='extrapolate')

#x2 = np.linspace(0,len(player_elo[::-1]),1)
#y2 = np.array([predict(x) for x in range(len(player_elo))])
#plt.plot(player_elo[::-1])
#plt.show()
#plt.plot(y2)

'''
Find the most common time to be playing chess
'''
def most_common(lst):
    return max(set(lst), key=lst.count)

times = re.findall(r'UTCTime \"\d{2}:\d{2}:\d{2}\"',content)
days = re.findall(r'UTCDate \"\d{4}.\d{2}.\d{2}\"',content)
time_array = [x.split()[1][1:-1] for x in times]
day_array = [x.split()[1][1:-1] for x in days]

hour = [int(x[0:2]) for x in time_array]
day_datetime = [datetime.strptime(x, "%Y.%m.%d").weekday() for x in day_array]
dayoftheweek = {0:'Mon',1:'Tues',2:'Weds',3:'Thur',4:'Fri',5:'Sat',6:'Sun'}
day_conv = [dayoftheweek[x] for x in day_datetime]
plt.hist(hour,bins=24)
plt.xlabel('Hour of the day')
plt.ylabel('Frequency')
plt.title('What time of day does {} play chess most often?'.format(player_name))
plt.show()

plt.hist(day_conv,bins=7)
plt.xlabel('Day of the week')
plt.ylabel('Frequency')
plt.title('What day of the week does {} play chess most often?'.format(player_name))
plt.show()

print(most_common(day_conv))

'''
Find the hour and day with the best score for playing
'''

wld = [x[1] for x in elo_result]
conv = {'W':1,'D':0.5,'L':-1}
wld_conv = [conv[x] for x in wld]

wld_hour = []
for idx in range(len(wld_conv)):
    wld_hour.append((hour[idx],wld_conv[idx]))

hr_score = []
num_of_games = np.zeros((1,24))
total_score = np.zeros((1,24))

for hr in range(24):
    for idx in range(len(wld_hour)):
        if wld_hour[idx][0] == hr:
            num_of_games[:,hr] += 1
            total_score[:,hr] += wld_hour[idx][1]

x = np.arange(0,24,1)
plt.plot(x,np.squeeze(np.divide(total_score,num_of_games)))
plt.xlabel('Hour of the day')
plt.ylabel('Normalised score')
plt.title('What time of day does {} play best?'.format(player_name))
plt.show()

day_score = []
num_of_games = np.zeros((1,7))
total_score = np.zeros((1,7))

wld_day = []

for idx in range(len(wld_conv)):
    wld_day.append((day_datetime[idx], wld_conv[idx]))

for day in range(7):
    for idx in range(len(wld_day)):
        if wld_day[idx][0] == day:
            num_of_games[:,day] += 1
            total_score[:,day] += wld_day[idx][1]

x = np.arange(0,7,1)
plt.plot(x,np.squeeze(np.divide(total_score,num_of_games)))
plt.xlabel('Day of the week')
plt.ylabel('Normalised score')
plt.title('What day of the week does {} play best?'.format(player_name))
plt.show()
