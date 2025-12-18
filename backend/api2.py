from pycomcigan import TimeTable, get_school_code
import json
import datetime


#학교 설정=대마고
school_name="대덕소프트웨어마이스터고등학교"
# 시간표 가져오기
# week_num: 0이면 이번주, 1이면 다음주
this_timetable = TimeTable(school_name, week_num=0)
next_timetable = TimeTable(school_name, week_num=1)

today = datetime.date.today()
idx=datetime.timedelta(days=today.weekday())

today=today-idx
nextday = today + datetime.timedelta(weeks=1)

weekday=['월','화','수','목','금']


def extract_from_comcigan_to_json(timetable:TimeTable, monday:datetime.date):
    ret={}
    for i in range(1,4):
        grade={}
        for j in range(1,5):
            class_num={}
            for k in range(1,6):
                day={}
                for l in range(0,7):
                    data=timetable[i][j][k][l]
                    ori=None
                    if data.replaced:
                        ori=data.original
                        ori={f'{ori.period}교시':{"과목":ori.subject, "선생님":ori.teacher}}
                    data={"과목":data.subject, "선생님":data.teacher}
                    if ori:
                        data['원래 과목']=ori
                # data={"a":data.}
                # if data.replaced:
                    # data={}
                
                    day[str(l+1)+"교시"]=data
                date=monday+datetime.timedelta(days=k-1)
                class_num[f'{date.strftime("%Y%m%d")}-{weekday[k-1]}요일']=day
            grade[f'{j}반']=class_num
        ret[str(i)+'학년']=grade
    
    return ret 

ret=[]
ret.append(extract_from_comcigan_to_json(this_timetable.timetable, today))
ret.append(extract_from_comcigan_to_json(next_timetable.timetable, nextday))
with open("comcigan.json", 'w', encoding="utf-8") as f:
    json.dump(ret, f, ensure_ascii=False, indent=2)

# 3학년 1반 화요일 시간표
# print(timetable.timetable[3][1][timetable.TUESDAY])

# 3학년 1반 담임선생님
# print(timetable.homeroom(3, 1))

