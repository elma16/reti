#!/usr/bin/env python3

import re
import sys
import matplotlib.pyplot as plt
import numpy as np
from sklearn import model_selection
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn import metrics
from sklearn.metrics import classification_report

######################
## TESTS
######################
t1 = [0,0,0,0]
t2 = [0,1,1,0]
t3 = [0,6,0]
t4 = [1,0,-1]
t5 = [10,10,-10,-10]

test_value = [0,2,6,0,0]
tests = [t1,t2,t3,t4,t5]
for test in tests:
    np.testing.assert_allclose(np.trapz(test),test_value[tests.index(test)])

######################
## MAIN
######################

'''
If we have a pgn file with games which have analysis (e.g some lichess dbs) run evals.cql to remove it to just this
o/w do some sf analysis
'''

def find_analysed_games():
    cql_command = cql_dir+' -i '+db_dir+' -o '+pgn_file+' -matchcount 2 100 '+file_dir
    subprocess.run(cql_command,shell=True)
    return 0

with open(sys.argv[1]) as f:
    content = str(f.readlines())
    content = content.split('[Event')
content = content[1:]
result_array = []
tc_array = []
eval_array = np.zeros((len(content),400))
game_len_max = 0

# extract time controls
# extract game evals
# extract result
# extract max length of game
for item in content:
    game_index = content.index(item)
    game_evals = re.findall(r'eval\s(-?\d{1,2}.\d{1,2}|#-?\d{1,2})', item)
    timecontrol = re.findall(r'(Rated\s\w{1,9}\sgame|TimeControl\s".{1,9}")', item)
    result = re.findall(r'Result\s".{3,7}"', item)
    tc_array.append(timecontrol[0].split()[1])
    result_array.append(result[0][7:])
    if len(game_evals) > game_len_max:
        game_len_max = len(game_evals)
    try:
        eval_array[game_index, 0:len(game_evals)] = game_evals
    except ValueError:
        for value in game_evals:
            if '#' in value:
                game_evals[game_evals.index(value)] = np.copysign(200,int(value[1:]))
        eval_array[game_index, 0:len(game_evals)] = game_evals

eval_array = eval_array[:,0:game_len_max]

def auc(eval_array):
    auc_score = []
    avg_auc = []
    for game in range(np.shape(eval_array)[0]):
        auc_score.append(np.trapz(eval_array[game,:]))
        avg_auc.append(np.trapz(eval_array[game,:])/len(eval_array[game,:]))
    return auc_score, avg_auc

game = eval_array[400,:]
plt.plot(game[0:len(game) - np.equal(game,0)[::-1].argmin()])
plt.show()
# filter game by time control

'''
blitz = np.array([tc == 'Bullet' for tc in tc_array])
print((len(blitz),len(auc_score),len(result_array)))
for idx in range(len(blitz)):
    if blitz[idx] == 0:
        auc_score[idx] = 0
        result_array[idx] = 0
auc_score = [i for i in auc_score if i != 0]
result_array = [i for i in result_array if i != 0]
plt.scatter(auc_score, result_array)
plt.show()
'''
#######################
## CORR
#######################

codes = {'1-0':1,'0-1':0,'1/2-1/2':0.5}
for result in result_array:
    if result == '"1-0"':
        result_array[result_array.index(result)] = 1
    elif result == '"0-1"':
        result_array[result_array.index(result)] = -1
    elif result == '"1/2-1/2"':
        result_array[result_array.index(result)] = 0
print(np.mean(result_array))
print(np.corrcoef(auc_score, result_array))

X = np.array(avg_auc).reshape(-1,1)
Y = np.array(result_array)
X_train,X_test,y_train,y_test=train_test_split(X,Y,test_size=0.4,random_state=100)

logreg= LogisticRegression()
logreg.fit(X_train,y_train)

y_pred=logreg.predict(X_test)
#print(X_test) #test dataset
#print(y_pred) #predicted values

print('Accuracy: ',metrics.accuracy_score(y_test, y_pred))
print('Recall: ',metrics.recall_score(y_test, y_pred, zero_division=1,average='micro'))
print('Precision: ',metrics.precision_score(y_test, y_pred, zero_division=1,average='micro'))
print('CL Report: ',metrics.classification_report(y_test, y_pred, zero_division=1))
