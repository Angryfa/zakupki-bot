import os
import time
import json
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

# Настройки Flask
app = Flask(__name__)

# Отключаем предупреждения об SSL
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ZakupkiBot:
    def __init__(self, data):
        self.client = requests.Session()
        self.client.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': f'Bearer {data["token"]}'
        })
        self.base_url = "https://zakupki.mos.ru/newapi/api/EntityOperation"
        self.need_id = data["need_id"]
        self.end_date = data["end_date"]
        self.nds_rate_id = data["nds_rate_id"]
        self.cost_per_unit = data["cost_per_unit"]
        self.supplier_id = self.get_supplier_id()
        self.started_operation_log_id = None

    def get_supplier_id(self):
        """ Получает supplier_id через два запроса """
        auth_url = "https://old.zakupki.mos.ru/api/Cssp/Authentication/CheckAuthentication"
        company_url = "https://old.zakupki.mos.ru/api/Cssp/Company/GetFullEntity?companyId={}"

        print("🔄 Получаем companyId...")
        auth_response = self.client.get(auth_url, verify=False)
      #   print(f"📌 Ответ от сервера (CheckAuthentication): {auth_response.text}")

        try:
            auth_data = auth_response.json()
        except json.JSONDecodeError:
            print("❌ Ошибка JSON (CheckAuthentication)")
            return None

        if auth_response.status_code == 200 and auth_data.get("isAuthenticated"):
            company_id = auth_data["user"]["company"]["id"]
            print(f"✅ Получен companyId: {company_id}")
        else:
            print(f"❌ Ошибка авторизации: {auth_response.text}")
            return None

        print("🔄 Получаем supplierId...")
        company_response = self.client.get(company_url.format(company_id), verify=False)

        try:
            company_data = company_response.json()
        except json.JSONDecodeError:
            print("❌ Ошибка JSON (GetFullEntity)")
            return None

        if company_response.status_code == 200:
            supplier_id = company_data.get("supplierId")
            if supplier_id:
                print(f"✅ Получен supplierId: {supplier_id}")
                return supplier_id
            else:
                print("❌ SupplierId не найден!")
                return None
        else:
            return None

    def fetch_need_details(self):
        """ Извлекает данные по 'need' (включая costPerUnit и proposalEndDate) """
        url = f"https://zakupki.mos.ru/newapi/api/Need/Get?needId={self.need_id}"
        response = self.client.get(url, verify=False)

        try:
            data = response.json()
        except json.JSONDecodeError:
            print("❌ Ошибка JSON (Fetch Need Details)")
            return None 

        if response.status_code == 200:
            # Извлекаем все значения costPerUnit
            cost_per_unit_list = [item["costPerUnit"] for item in data.get("items", [])]
            proposal_end_date = data.get("proposalEndDate")

            print("✅ Получены данные: ")
            print("---✅ Cost Per Unit:", cost_per_unit_list)
            print("---✅ Proposal End Date:", proposal_end_date)

            return cost_per_unit_list, proposal_end_date
        else:
            print(f"❌ Ошибка {response.status_code}, тело ответа: {response.text}")
            return None, None

    def check_time_and_proposal_end(self, proposal_end_date):
        """ Проверка текущего времени, и если оно меньше proposal_end_date - 2 минуты, не начинаем процесс """
        current_time = datetime.now()  # Время с учетом +3 часов

        # Преобразуем proposal_end_date из строки в datetime
        proposal_end_date = datetime.strptime(proposal_end_date, "%d.%m.%Y %H:%M:%S")

        # Сравниваем время
        if current_time >= proposal_end_date - timedelta(minutes=2) or True:
            print("✅ Время подходящее для начала процесса.")
            return True
        else:
            print(f"❌ Время не подходит для начала процесса. Текущее время: {current_time}, предложение закончится в: {proposal_end_date}.")
            return False

    def create_operation_entity(self):
        """ Создание сущности покупки """
        url = f"{self.base_url}/CreateNewOperationEntity/8ab79a58-b8d4-494e-a0ec-bbb3b2e781f4"
        payload = {"creationData": {"needId": self.need_id, "supplierId": self.supplier_id}}

        response = self.client.post(url, json=payload, verify=False)
        try:
            data = response.json()
        except json.JSONDecodeError:
            print(f"❌ Ошибка JSON (CreateNewOperationEntity): {response.text}")
            return None

        print(f"📌 Ответ от сервера (Create Operation): {data}")

        if response.status_code == 200:
            if isinstance(data, dict):
                entity_id = data.get("entityId")
                if entity_id:
                    print(f"✅ Создана сущность покупки, entityId: {entity_id}")
                    return entity_id
            elif isinstance(data, (str, int)):
                print(f"⚠️ Сервер вернул entityId как число: {data}")
                return str(data)
            else:
                print(f"❌ Неожиданный формат ответа: {data}")
                return None
        else:
            print(f"❌ Ошибка {response.status_code}, тело ответа: {response.text}")
            return None

    def start_operation(self, entity_id):
        """ Запуск операции """
        url = f"{self.base_url}/StartOperation/8ab79a58-b8d4-494e-a0ec-bbb3b2e781f4"
        payload = {"entityId": entity_id, "operationId": "aa31f4c6-c31d-4012-ae99-2afeda2e24f7"}

        response = self.client.post(url, json=payload, verify=False)
        print(f"📌 Ответ от сервера (StartOperation): {response.text}")

        try:
            data = response.json()
        except json.JSONDecodeError:
            return None

        if response.status_code == 200:
            self.started_operation_log_id = data.get("startedOperationLogId")
            entity_version_id = data.get("entityVersionId")
            print(f"✅ Операция запущена, startedOperationLogId: {self.started_operation_log_id}")
            return entity_version_id
        return None

    def save_started_operation(self, entity_id,cost_per_unit_list):
        """ Сохранение операции """
        # Получаем информацию о сущности с использованием entityId
        get_started_operation_url = f"{self.base_url}/GetStartedOperation/8ab79a58-b8d4-494e-a0ec-bbb3b2e781f4?query"
        get_started_operation_payload = {"entityId": entity_id}

        get_started_operation_response = self.client.post(get_started_operation_url, json=get_started_operation_payload, verify=False)

        try:
            started_operation_data = get_started_operation_response.json()
        except json.JSONDecodeError:
            print("❌ Ошибка JSON (GetStartedOperation)")
            return None

        if get_started_operation_response.status_code == 200:
            # Извлекаем needItem, поддерживаем несколько элементов
            need_item = started_operation_data.get("editingEntity", {}).get("needItem", [])
            if need_item:
                item_ids = [item.get("id") for item in need_item if item.get("id")]  # Список itemId
                if item_ids:
                    print(f"✅ Получены itemIds: {item_ids}")
                else:
                    print("❌ itemId не найдены!")
                    return None
            else:
                print("❌ needItem пустой или не найден!")
                return None
        else:
            print(f"❌ Ошибка {get_started_operation_response.status_code} при получении StartedOperation")
            return None

        # Теперь используем все itemIds для дальнейшего запроса
        url = f"{self.base_url}/SaveStartedOperation/8ab79a58-b8d4-494e-a0ec-bbb3b2e781f4"
        
        # Модифицируем payload для обработки нескольких items
        need_item_offer = []
        for idx, item_id in enumerate(item_ids):
            if idx < len(cost_per_unit_list):
               cost_per_unit = cost_per_unit_list[idx]
            else:
               cost_per_unit = 0
            print(f"📌 Ответ от сервера (цена айтема): {cost_per_unit}"),
            need_item_offer.append({
                "itemId": item_id,  # Используем найденный itemId
                "needSupplierId": entity_id,
                "costPerUnit": cost_per_unit,
                
                "amountWithNds": 0,
                "ndsRateId": self.nds_rate_id
            })

         

        payload = {
            "startedOperationLogId": self.started_operation_log_id,
            "editingEntity": {
                "endDate": self.end_date,
                "needId": self.need_id,
                "supplierId": self.supplier_id,
                "needItemOffer": need_item_offer,  # Здесь мы передаем несколько needItemOffer
                "entityId": entity_id,
                "signer": {
                  "withoutPatronymic": False,
                  "givenName": "Георгий",
                  "familyName": "Осминин",
                  "patronymic": "Георгиевич",
                  "position": "Генеральный директор",
                  "powerOfAttorney": {
                     "name": "Устав",
                     "number": "нет",
                     "startDate": "16.07.2021 00:00:00",
                  }
                 }
                }
            }
        

        response = self.client.post(url, json=payload, verify=False)
        print(f"📌 Ответ от сервера (SaveStartedOperation): {response.text}")

        try:
            return response.json()
        except json.JSONDecodeError:
            print("❌ Ошибка JSON (SaveStartedOperation)")
            return None

    def finish_operation(self):
        """ Завершение операции """
        url = f"{self.base_url}/FinishOperation/8ab79a58-b8d4-494e-a0ec-bbb3b2e781f4"
        payload = {"startedOperationLogId": self.started_operation_log_id}

        response = self.client.post(url, json=payload, verify=False)
        print(f"📌 Ответ от сервера (FinishOperation): {response.text}")

        if response.status_code == 200 and response.text == "{}":
            print("✅ Предложение успешно создано!")
            return True
        else:
            print("❌ Ошибка при создании предложения.")
            return False

    def make_purchase(self):
        """ Основная функция, выполняющая все шаги покупки """
        cost_per_unit_list, proposal_end_date = self.fetch_need_details()
        if not cost_per_unit_list or not proposal_end_date:
            print("❌ Ошибка при получении данных для покупки.")
            return None
        print(f"📌 значение цены айтемов: {cost_per_unit_list}")
        # Проверяем, подходит ли время
        if not self.check_time_and_proposal_end(proposal_end_date):
            return None

        # Используем данные для выполнения дальнейших операций
      #   self.cost_per_unit = cost_per_unit_list[0] if cost_per_unit_list else self.cost_per_unit
        current_date = datetime.now()
        new_end_date = current_date + timedelta(days=30)
        self.end_date = new_end_date.strftime("%d.%m.%Y %H:%M:%S")
        print(f"📅 Новый end_date: {self.end_date}")

        entity_id = self.create_operation_entity()
        if not entity_id:
            return None
        time.sleep(2)

        entity_version_id = self.start_operation(entity_id)
        if not entity_version_id:
            return None

        time.sleep(2)

        self.save_started_operation(entity_id,cost_per_unit_list)

        time.sleep(2)

        return self.finish_operation()

# Главная страница для ввода данных
@app.route('/')
def index():
    return render_template('index.html')

# Обработчик формы
@app.route('/start_bot', methods=['POST'])
def start_bot():
    need_id = request.form.get('need_id')
    
    data = {
        "token": "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJwbDgxLVYyWUNyQ1V0bmVRTWxxRUNmSVluS1Z3VExnQVIwZXhiTkF1SF9nIn0.eyJleHAiOjIwNTUwNjQzNDMsImlhdCI6MTczOTcwNTg5MywiYXV0aF90aW1lIjoxNzM5NzA0MzQzLCJqdGkiOiJhN2E1NzRkMi0yMTBjLTQxNDktYmM0Ni1iMjNmNGI3MWQwMzkiLCJpc3MiOiJodHRwczovL3pha3Vwa2kubW9zLnJ1L2F1dGgvcmVhbG1zL1BwUmVhbG0iLCJhdWQiOiJJbnRlZ3JhdGlvbkFwcCIsInN1YiI6IjdhZDUwNmY5LTM5Y2EtNGNhOC04YmZiLWY0MzE1MjNhYzJiMSIsInR5cCI6IkJlYXJlciIsImF6cCI6IlBwQXBwIiwic2Vzc2lvbl9zdGF0ZSI6IjU3OTY0Njk3LTJlNTItNGQ0Ni04NTBhLTA1YjRlZWZlNmQzMSIsInNjb3BlIjoiSW50ZWdyYXRpb25TY29wZSIsInNpZCI6IjU3OTY0Njk3LTJlNTItNGQ0Ni04NTBhLTA1YjRlZWZlNmQzMSJ9.UXsHSF3UAM9UBq9-yq7_D9UkYs9w6CaXwdVQa_p1YkRhxRXgwY0F2CRaLDuRSp2_m0Kr5D7lHJ8BXvqHd0RFPNNMrtGbK6ULwGevNwQb719IxdlZV69vzyDpJSyLOlgVxikgEAr4H9sYYsmCGaVD6vxvvNvUVdO8UlB82OgpNhI4Bmylh6TETznN1Rgh20D4GGj8Hox70I9l6ciUVN1B0nFaBupwnv4BVAIw-z2QqfpHrf2cLjpl5UE78a2prRQR7tN-NeHQrNYvzxj0SVkVRg30dqJ0iNWEeaHwDIJqEd7LkBv8t8aChKxFMf528DlxDb15uo5n2cJni-oAdRuu9w",  # Замените на ваш токен
        "need_id": need_id,
        "end_date": "0",
        "nds_rate_id": 4,
        "cost_per_unit": 0
    }

    bot = ZakupkiBot(data)
    purchase_result = bot.make_purchase()

    # Если покупка успешна
    if purchase_result:
        return jsonify({"status": "success", "message": "🎉 Покупка успешно завершена!"})
    else:
        return jsonify({"status": "error", "message": "❌ Ошибка при оформлении покупки."})

if __name__ == '__main__':
    app.run(debug=True)
