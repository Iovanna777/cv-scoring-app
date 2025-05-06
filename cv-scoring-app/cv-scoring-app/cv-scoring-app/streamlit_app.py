import streamlit as st
import openai
import os
import requests
from bs4 import BeautifulSoup
import re
import base64

# Получение API-ключа из переменной окружения
api_key = os.environ.get("OPENAI_API_KEY")

# Проверка, что ключ существует
if not api_key:
    st.error("Ошибка: API-ключ OpenAI не найден в переменных окружения.")
    st.stop()

# Настройка OpenAI клиента
client = openai.OpenAI(api_key=api_key)

# Функция для извлечения оценки из текста
def extract_score(response_text):
    match = re.search(r'оценк[ау]\s*(\d+)', response_text.lower())
    return int(match.group(1)) if match else 5  # По умолчанию 5, если оценка не найдена

# Функция для получения HTML
def get_html(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response

# Функция для извлечения данных вакансии
def extract_vacancy_data(html):
    soup = BeautifulSoup(html, 'html.parser')
    def safe_text(selector, attrs=None):
        el = soup.find(selector, attrs or {})
        return el.text.strip() if el else "Не найдено"
    title = safe_text('h1')
    salary = safe_text('span', {'data-qa': 'vacancy-salary'})
    company = safe_text('a', {'data-qa': 'vacancy-company-name'})
    description = soup.find('div', {'data-qa': 'vacancy-description'})
    description_text = description.get_text(separator="\n").strip() if description else "Описание не найдено"
    markdown = f"# {title}\n\n"
    markdown += f"**Компания:** {company}\n\n"
    markdown += f"**Зарплата:** {salary}\n\n"
    markdown += f"## Описание\n\n{description_text}"
    return markdown.strip()

# Функция для извлечения данных резюме
def extract_resume_data(html):
    soup = BeautifulSoup(html, 'html.parser')
    def safe_text(selector, **kwargs):
        el = soup.find(selector, kwargs)
        return el.text.strip() if el else "Не найдено"
    name = safe_text('h2', data_qa='bloko-header-1')
    gender_age = safe_text('p')
    location = safe_text('span', data_qa='resume-personal-address')
    job_title = safe_text('span', data_qa='resume-block-title-position')
    job_status = safe_text('span', data_qa='job-search-status')
    experiences = []
    experience_section = soup.find('div', {'data-qa': 'resume-block-experience'})
    if experience_section:
        experience_items = experience_section.find_all('div', class_='resume-block-item-gap')
        for item in experience_items:
            try:
                period = item.find('div', class_='bloko-column_s-2').text.strip()
                duration = item.find('div', class_='bloko-text').text.strip()
                period = period.replace(duration, f" ({duration})")
                company = item.find('div', class_='bloko-text_strong').text.strip()
                position = item.find('div', {'data-qa': 'resume-block-experience-position'}).text.strip()
                description = item.find('div', {'data-qa': 'resume-block-experience-description'}).text.strip()
                experiences.append(f"**{period}**\n\n*{company}*\n\n**{position}**\n\n{description}\n")
            except Exception:
                continue
    skills = []
    skills_section = soup.find('div', {'data-qa': 'skills-table'})
    if skills_section:
        skills = [tag.text.strip() for tag in skills_section.find_all('span', {'data-qa': 'bloko-tag__text'})]
    markdown = f"# {name}\n\n"
    markdown += f"**{gender_age}**\n\n"
    markdown += f"**Местоположение:** {location}\n\n"
    markdown += f"**Должность:** {job_title}\n\n"
    markdown += f"**Статус:** {job_status}\n\n"
    markdown += "## Опыт работы\n\n"
    markdown += "\n".join(experiences) if experiences else "Опыт работы не найден.\n"
    markdown += "\n## Ключевые навыки\n\n"
    markdown += ", ".join(skills) if skills else "Навыки не указаны.\n"
    return markdown.strip()

# Заголовок приложения
st.title('CV Scoring App')

# Поля ввода для ссылок
job_url = st.text_input('Введите ссылку на описание вакансии')
cv_url = st.text_input('Введите ссылку на резюме')

# Кнопка для парсинга и оценки
if st.button("Оценить резюме"):
    with st.spinner("Оцениваем резюме..."):
        # Парсинг текста из ссылок
        html_vacancy = get_html(job_url).text
        html_resume = get_html(cv_url).text
        job_description = extract_vacancy_data(html_vacancy)
        cv = extract_resume_data(html_resume)
        
        if not job_description or not cv:
            st.error("Не удалось получить текст из одной или обеих ссылок. Проверьте URL.")
            st.stop()

        # Системный промпт
        SYSTEM_PROMPT = """
        Проскорь кандидата, насколько он подходит для данной вакансии.

        Сначала напиши короткий анализ, который будет пояснять оценку.
        Отдельно оцени качество заполнения резюме (понятно ли, с какими задачами сталкивался кандидат и каким образом их решал?). Эта оценка должна учитываться при выставлении финальной оценки - нам важно нанимать таких кандидатов, которые могут рассказать про свою работу.
        Потом представь результат в виде оценки от 1 до 10.
        """.strip()

        # Функция для запроса к GPT
        def request_gpt(system_prompt, user_prompt):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},  
                    {"role": "user", "content": user_prompt},     
                ],
                max_tokens=1000,
                temperature=0,
            )
            return response.choices[0].message.content

        # Формирование пользовательского промпта
        user_prompt = f"# ВАКАНСИЯ\n{job_description}\n\n# РЕЗЮМЕ\n{cv}"
        # Отправка запроса
        response = request_gpt(SYSTEM_PROMPT, user_prompt)
    
    # Вывод текста
    st.write(response)
    
    # Извлечение оценки
    score = extract_score(response)
    
    # Визуализация: Метрика
    st.metric(label="Оценка кандидата", value=f"{score}/10")
    
    # Визуализация: График
    import numpy as np
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.bar(['Оценка'], [score], color='green')
    ax.set_ylim(0, 10)
    ax.set_title("Оценка соответствия")
    st.pyplot(fig)
