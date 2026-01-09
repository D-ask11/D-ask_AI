import api, model, time
import api2

def func():
    print('호출됨')
#   1분  1시간 1일
t = 60 * 60 * 24
while True:
    time.sleep(t)
    api.make_json()
    model.make_json()
    api2.make_json()