import requests
import json
import time
import re
import os
import dotenv
#-----api key
dotenv.load_dotenv()
api_key = os.getenv('API_KEY')
# ===========================
# 수집 함수
# ===========================
def fetch_schedule(pIndex, base_url, params_template, info):
    params = params_template.copy()
    params["pIndex"] = pIndex

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        title=base_url.split('/')[-1]
        # NEIS API는 오류/비어있는 응답이 올 수 있으므로 체크
        if title in data:
            ret=[]
            for i in data[title][1]['row']:
                dic={}
                for k,v in info.items():
                    dic[k]=i[v]
                ret.append(dic)
            return ret
        else:
            print(f"[경고] pIndex={pIndex} 에 해당하는 데이터가 없습니다.")
            return []

    except Exception as e:
        print(f"[오류] pIndex={pIndex} 데이터를 가져오는 중 에러 발생:", e)
        return []

# ===========================
# 메인
# ===========================
def main(key, base_url, info, file):
    # ===========================
    # 설정
    # ===========================
    KEY = key
    BASE_URL = base_url
    PARAMS_TEMPLATE = {
        "ATPT_OFCDC_SC_CODE": "G10",
        "SD_SCHUL_CODE": "7430310",
        "DGHT_CRSE_SC_NM": "주간",
        "SCHUL_CRSE_SC_NM": "고등학교",
        "Type": "json",
        "Key": KEY
    }
    INFO=info

    all_schedules = []
    i=1
    while(True):  # pIndex 1 ~ 6
        print(f"📡 수집중: pIndex = {i} ...")
        schedule = fetch_schedule(i, base_url=BASE_URL, params_template=PARAMS_TEMPLATE, info=INFO)

        if schedule:
            all_schedules.extend(schedule)
            i+=1
        else:
            break

        time.sleep(0.5)  # 서버 부담 줄이기

    # 저장 또는 출력
    with open(file, "w", encoding="utf-8") as f:
        json.dump(all_schedules, f, ensure_ascii=False, indent=2)

    print("✅ 수집 완료!")
    print(f"총 레코드 수: {len(all_schedules)}")
if __name__ == "__main__":
    main(key=api_key, base_url="https://open.neis.go.kr/hub/SchoolSchedule", 
         info={'date':'AA_YMD', 'title':'EVENT_NM'},
         file='school_schedules.json'
         )
    main(key=api_key, base_url="https://open.neis.go.kr/hub/mealServiceDietInfo", 
         info={'날짜':'MLSV_YMD','시간':'MMEAL_SC_NM', '요리명':'DDISH_NM', '칼로리':'CAL_INFO'},
         file='school_meal.json'
         )
    print('전처리')
    with open('school_meal.json', 'r', encoding='utf-8') as f:
        file=json.load(f)
        patt=re.compile(r'([^\.\ ]+)[\.\ ]')
        exclude=re.compile(r'[\d\(]+')
        for i in file:
            li=[]
            for j in i['요리명'].split('<br/>'):
                matt=patt.findall(j)
                if matt != None:
                    mli=""
                    for k in matt:
                        if exclude.match(k):
                            # print(k, i['날짜'])
                            continue
                        mli+=k+" "
                    mli=mli[:len(mli)-1]
                    for l in range(len(mli)-1, -1, -1):
                        if mli[l]!="." and False==mli[l].isdigit():
                            break
                    
                    li.append(mli[:l+1])
            i['요리명']=li

    with open('school_meal.json', 'w', encoding='utf-8') as f:
        json.dump(file, f, ensure_ascii=False, indent=2)
        
    print('끄읕')

