import api, api2, model

def run_crawl():
    api.make_json()
    api2.make_json()
    model.make_json()
    
if __name__=="__main__":
    run_crawl()