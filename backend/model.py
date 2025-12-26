import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from collections import deque
import re
import json
def extract_pdf_links_from_page(soup, current_url):
    """
    fieldBox 내부에서 PDF 링크(URL)만 추출하여 리스트로 반환
    다운로드는 하지 않음
    """

    result_links = []

    # fieldBox 안에서만 찾기
    field_box = soup.find(class_="fieldBox")
    if not field_box:
        return result_links

    # fieldBox 안의 dl → dd → a 태그 검색
    dl_tag = field_box.find("dl")
    if not dl_tag:
        return result_links

    a_tags = dl_tag.find_all("a", href=True)

    for a in a_tags:
        href = a["href"]
        text = a.get_text(strip=True)

        # 미리보기 링크 제외
        if "preview" in href:
            continue

        # PDF인지 확인
        if ".pdf" not in href.lower() and ".pdf" not in text.lower():
            continue

        # 절대 URL 변환
        pdf_url = urljoin(current_url, href)

        # 파일명 후보 (텍스트 기반)
        filename = text
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        # 결과 추가
        result_links.append({
            "filename": filename,
            "url": pdf_url
        })

    return result_links

# ----------------------------------------------------------
# 본문(title, contents, pdf 텍스트) 추출
# ----------------------------------------------------------
def parse_page_content(url, html):
    soup = BeautifulSoup(html, "html.parser")

    # 제목 추출
    h1_tags = soup.find_all("h1", class_="tit")
    title = None
    if h1_tags:
        target_h1 = h1_tags[-1] 
        title_parts = []
        
        for element in target_h1.children:
        # strong은 건너뛰기
            if element.name == "strong":
                continue
        # 텍스트 노드만 수집
            if isinstance(element, str):
                title_parts.append(element.strip())
        title = " ".join([t for t in title_parts if t])

    # 본문 내용
    content_tag = soup.find(class_="viewBox")
    contents = content_tag.get_text(" ", strip=True) if content_tag else ""

    # 첨부파일 PDF 추출
    pdf_files = []
    field_box = soup.find(class_="fieldBox")

    if field_box:
        pdf_file = extract_pdf_links_from_page(soup, url)
        if pdf_file:
            for i in pdf_file:
                pdf_files.append(i)

    return {
        "title": title,
        "contents": contents,
        "pdf": pdf_files
    }



def parse_goView_call(attribute_value):
    """
    onclick="javascript:goView('a','b','c', ...)"
    에서 goView 인자들을 추출하여 URL 문자열로 변환해주는 함수
    """
    match = re.search(r"goView\((.*?)\)", attribute_value)
    if not match:
        return None

    # '54793','9601676','0',... 형태에서 문자열만 추출
    args = [arg.strip().strip("'\"") for arg in match.group(1).split(",")]

    if len(args) < 7:
        return None

    boardID, boardSeq, lev, searchType, statusYN, page, opType = args

    # 실제 URL 패턴 (대전교육청 CMS 규칙)
    return f"/boardCnts/view.do?boardID={boardID}&boardSeq={boardSeq}&lev={lev}&searchType={searchType}&statusYN={statusYN}&page={page}&pSize=10&s=dsmhs&m=0201&opType={opType}"


def crawl_site_with_params(base_url, target_params: dict, target_fragment:dict):
    #---------------------------------------------

    # res = session.get("https://dsmhs.djsch.kr/index.do")
    # print(session.cookies.get_dict())
    # print(res.status_code)
    # print(res.text)
    # print(res.url)
    #---------------------------------------------
    visited = set()
    queue = deque(base_url)
    extracted_data = []

    base_domain = urlparse(base_url[0]).netloc
    #--------------------------------------------------
    while queue:
        url = queue.popleft()

        if url in visited:
            continue

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        fg = parsed.fragment

        # --- 조건 검사 시작 -----------------------------------------------------
        match_all = True
        for key, target_values in target_params.items():
            val, opt = target_values
            # 1) URL에 해당 key 자체가 없으면 실패
            if key not in qs:
                match_all = False
                break

            # 2) 값 리스트가 None이 아닐 때, 값이 포함되는지 검사
            if val is not None:
                # qs[key]는 ['54793'] 같이 리스트 형태
                if not any(i in qs[key] if opt==1 else i not in qs[key] for i in val):
                    match_all = False
                    break
        
        # --- fragment 조건 검사 -----------------------------------------------------
        for key, target_values in target_fragment.items():
            # 1) In 중에 1개라도 있으면 True
            if key == "In":
                if target_values is not None:
                # fragment = string 형태
                    if not any(True for val in target_values if val == fg):
                        match_all = False
                        break

            # 2) notIn 중에 1개라도 있으면 False
            else:
                if target_values is not None:
                    if any(True for val in target_values if val == fg):
                        match_all = False
                        break

        # 모든 조건이 충족되지 않으면 skip
        if not match_all:
            continue
        # -------------------------------------------------------------------------

        visited.add(url)
        #print(f'doing...{url}')
        #print("크롤링:", url)

        try:
            response = requests.get(url, timeout=5)
        except:
            continue

        if response.status_code != 200:
            visited.remove(url)
            queue.append(url)
            

        soup = BeautifulSoup(response.text, "html.parser")

        html = response.text

        # ----------------------------------------------------------------------
        # 페이지 내용 추출(title / contents / pdf text)
        data=parse_page_content(url, html)
        data['link']=url
        extracted_data.append(
            data
        )
        # ----------------------------------------------------------------------

        for a in soup.find_all("a", href=True):
            # 1) href 처리
            if a.has_attr("href"):
                next_url = urljoin(url, a["href"])
                if urlparse(next_url).netloc == base_domain:
                    if next_url not in visited:
                        queue.append(next_url)

            # 2) onclick="goView(...)" 처리
            if a.has_attr("onclick"):
                url_from_js = parse_goView_call(a["onclick"])
                if url_from_js:
                    next_url = urljoin(url, url_from_js)
                    if urlparse(next_url).netloc == base_domain:
                        if next_url not in visited:
                            queue.append(next_url)

    return extracted_data

#로그인 메타데이터
login_url = 'https://dsmhs.djsch.kr/doLogin.do'
login_data = {
    "usrType": "imem",
    "usrID": 'kimwonshin',
    "usrPass": 'Mwkxkfahdi1!',
    "LastSysID": "dsmhs"
}

# 크롤링 메타데이터
base_url = ["https://dsmhs.djsch.kr/boardCnts/view.do?boardID=54793&boardSeq=9606314&lev=0&searchType=null&statusYN=W&page=1&pSize=10&s=dsmhs&m=0201&opType=N",
            "https://dsmhs.djsch.kr/boardCnts/view.do?boardID=54794&boardSeq=9608539&lev=0&searchType=null&statusYN=W&page=1&pSize=10&s=dsmhs&m=0202&opType=N",
            "https://dsmhs.djsch.kr/boardCnts/view.do?boardID=54813&boardSeq=9325361&lev=0&searchType=null&statusYN=W&page=1&pSize=10&s=dsmhs&m=0505&opType=N"
            ]

target_params = {
    "boardID": [["54793", "54794", "54813"],1],
    "boardSeq": [["0"],0],
}

target_fragment = {
    "notIn" :["showMenu","gnb","container","wrap","contents"],
    "In":None
}

# parsed = urlparse(base_url)
# qs = parse_qs(parsed.query)
# print(qs)
# print(parsed.fragment)
# print([i for i in target_params.keys() if target_params[i] is not None])
# path=os.path.join('../pdf/','a.txt')
# print(path)
if __name__ == "__main__":
    found_pages = {'crawling':crawl_site_with_params(base_url, target_params, target_fragment, login_url, login_data)}

    with open("./data/crawling.json", "w", encoding="utf-8") as f:
        json.dump(found_pages, f, ensure_ascii=False, indent=4)

#print("\n=== 크롤링된 페이지 ===")

# for page in found_pages:
#     #stop = input()
#     print(f'link: {page[1]}')
#     print(
#     f'''content: 
#         'title': {page[0]['title']},

#         'contents': {page[0]['contents']}

#         'link': {page[0]['link']}
# ''')
#     print('--------------------------------------')
#print(found_pages)
#print(len(found_pages))
