# import crawler.api as api, model, time
# import crawler.api2 as api2

# def func():
#     print('호출됨')
# #   1분  1시간 1일
# t = 60 * 60 * 24
# while True:
#     time.sleep(t)
#     api.make_json()
#     model.make_json()
#     api2.make_json()
    
    
import api, api2, model

def run_crawl():
    api.make_json()
    api2.make_json()
    model.make_json()
    
if __name__=="__main__":
    run_crawl()