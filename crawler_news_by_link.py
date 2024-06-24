from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
import re
from konlpy.tag import Okt
import mysql.connector
import psutil

# DB 접속을 위한 정보 셋팅
mydb = mysql.connector.connect(
    host='spring-database.c7ms48g6s76s.ap-northeast-2.rds.amazonaws.com',
    user='root',
    passwd='mysql123!',
    database='issue'
)

# sql 실행을 위한 커서 생성
mycursor = mydb.cursor(prepared=True)

def create_webdriver():
    option = webdriver.ChromeOptions()
    option.add_argument('--headless')
    option.add_argument('--no-sandbox')
    option.add_argument('--disable-dev-shm-usage')
    option.add_argument('--remote-debugging-port=3000')

    option.add_experimental_option('detach', True)
    service = webdriver.ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=option)
    return driver


def kill_chromedriver_processes():
    for proc in psutil.process_iter():
        if proc.name() == "chromedriver.exe":
            proc.kill()


# 정규 표현식을 사용하여 기사 ID 추출
def extract_article_id(url):
    match = re.search(r'/(\d+)$', url)
    if match:
        return match.group(1)
    else:
        return None
    

def convert_to_datetime(input_time):
    # 입력값 전처리: "오전"을 "AM"으로, "오후"를 "PM"으로 변경
    if "오전" in input_time:
        input_time = input_time.replace("오전", "AM")
    elif "오후" in input_time:
        input_time = input_time.replace("오후", "PM")

    # 날짜/시간 포맷
    input_format = "%Y.%m.%d. %p %I:%M"

    try:
        # 입력값을 날짜/시간 객체로 변환
        datetime_obj = datetime.strptime(input_time, input_format)
        return datetime_obj
    except ValueError:
        return None
    
    
def extract_keywords(text):
    okt = Okt()
    # 형태소 분석
    morphs = okt.morphs(text)
    # 명사 추출
    nouns = okt.nouns(text)
    # 키워드 저장 (여기서는 명사만 키워드로 사용)
    keywords = set(nouns)
    return keywords

    
# 각 기사 링크에서 데이터 가져오기
def get_article_content(article_url):
    driver = create_webdriver()
    try:
        driver.get(article_url)
        time.sleep(1)
        page_source = driver.page_source.encode('utf-8')
        soup = BeautifulSoup(page_source, 'html.parser')

        # 기사 내용 추출
        article_code = extract_article_id(article_url)
        
        title = soup.find(class_='media_end_head_title')
        if title:
            title = title.get_text(strip=True)
        else:
            title = '제목을 찾을 수 없습니다'

        text = soup.find(class_='_article_content')
        if text:
            text = text.get_text()
        else:
            text = '본문을 찾을 수 없습니다'

        created_date = soup.find(class_='_ARTICLE_DATE_TIME')
        if created_date:
            created_date = created_date.get_text(strip=True)
            created_date = convert_to_datetime(created_date)
        else:
            created_date = '작성일을 찾을 수 없습니다'

        news_agency = soup.find(class_='media_end_head_top_logo_img')
        if news_agency:
            news_agency = news_agency.get('alt', '뉴스 기관을 찾을 수 없습니다')
        else:
            news_agency = '뉴스 기관을 찾을 수 없습니다'

        writer = soup.find(class_='byline_s')
        if writer:
            writer = writer.get_text(strip=True)
        else:
            writer = '기자를 찾을 수 없습니다'
        
        img = soup.find(id='img1')
        if img:
            img = img.get('src', '이미지를 찾을 수 없습니다')
        else:
            img = '이미지를 찾을 수 없습니다'

        print('기사코드:', article_code)
        print('제목:', title)
        print('본문:', text)
        print('작성일:', created_date)
        print('뉴스 기관:', news_agency)
        print('기자:', writer)
        print('링크:', article_url)
        print('이미지:', img)

        try:
            query = 'INSERT INTO tbl_article (article_code, title, text, created_date, news_agency, writer, img, article_link) VALUES(%s, %s, %s, %s, %s, %s, %s, %s)'
            values = (article_code, title, text, created_date, news_agency, writer, img, article_url)
            mycursor.execute(query, values)
        except mysql.connector.Error as err:
            print(f"Error: {err}")

        keywords = extract_keywords(text)
        for keyword in keywords:
            try:
                print('keyword : ', keyword.strip())
                query = 'INSERT INTO tbl_keywords (article_code, keyword) VALUES(%s, %s)'
                values = (article_code, keyword.strip())
                mycursor.execute(query, values)
            except mysql.connector.Error as err:
                print(f"Error: {err}")
            
    finally:
        delete_query = "DELETE FROM tbl_keywords WHERE keyword REGEXP '^[가-힣]$';"
        mycursor.execute(delete_query)
        driver.quit()


# 뉴스 기사 링크 가져오기
def get_news_list(date):
    driver = create_webdriver()
    driver.set_page_load_timeout(3600)  # 페이지 로드 타임아웃 (1시간)
    driver.set_script_timeout(3600)     # 스크립트 실행 타임아웃 (1시간)
    
    try:
        url = f"https://news.naver.com/breakingnews/section/102/249?date={date}"
        driver.get(url)

        # 기사 더보기 버튼을 누르기 위해 스크롤 및 클릭
        while True:
            try:
                more_button = driver.find_element(By.CLASS_NAME, '_CONTENT_LIST_LOAD_MORE_BUTTON')
                more_button.click()
                time.sleep(1)
            except:
                break

        # 페이지 소스 가져오기
        page_source = driver.page_source
        driver.quit()

        soup = BeautifulSoup(page_source, 'html.parser')

        # 원하는 정보 추출
        headlines = soup.find_all('a', class_='sa_text_title')
        
        kill_chromedriver_processes()

        # 링크 리스트 나누기
        total_links = [headline.parent.a['href'] for headline in headlines]
        mid_index = len(total_links) // 2
        first_half_links = total_links[:mid_index]
        second_half_links = total_links[mid_index:]

        # 추출한 정보 출력
        for i, headline in enumerate(headlines):
            if i > 0 and i % 10 == 0:  # 10개의 URL마다 WebDriver 재생성
                driver.quit()
                kill_chromedriver_processes()
                driver = create_webdriver()

            try:
                link = headline.parent.a['href']
                get_article_content(link)
            except WebDriverException as e:
                print(f"Exception occurred: {e}. Restarting WebDriver.")
                driver.quit()
                kill_chromedriver_processes()
                driver = create_webdriver()
                get_article_content(link)

            time.sleep(1)
                  
    finally:
        driver.quit()


# # 날짜 범위 설정 (start_date부터 end_date까지)
# start_date = datetime.strptime('20240617', '%Y%m%d')
# end_date = datetime.strptime('20240617', '%Y%m%d')
# date_generated = [start_date + timedelta(days=x) for x in range(0, (end_date - start_date).days + 1)]

# # 날짜를 역순으로 처리하여 크롤링
# for date in sorted(date_generated, reverse=True):
#     date_str = date.strftime('%Y%m%d')
#     get_news_list(date_str)

# get_news_list(datetime.today().strftime('%Y%m%d'))
get_news_list((datetime.today()-timedelta(days=1)).strftime('%Y%m%d'))

mydb.commit()
# mydb.rollback() -> 예외 처리와 함께 사용해서, 중간에 에러가 발생했을 시 롤백 처리

mycursor.close()
mydb.close()