CATEGORIES: tuple[str, ...] = (
    "Технічна підтримка",
    "Співпраця",
    "Скарга",
    "Пропозиція",
    "Інше",
)

MAX_FULL_NAME = 200
MAX_CONTACT = 200
MAX_DESCRIPTION = 1000
MIN_DESCRIPTION = 10

# Реєстрація співробітника
MAX_FULLNAME = 200
MIN_PHONE = 6
MAX_PHONE = 32
MAX_COMPANY_NAME = 200
MAX_TAX_ID = 32
MAX_ADDRESS = 300
MAX_POSITION = 64

# Транспорт
MAX_VEHICLE_BRAND = 64
MAX_VEHICLE_MODEL = 64
MIN_LICENSE_PLATE = 3
MAX_LICENSE_PLATE = 16

# Рейси
MAX_TTN = 64
#: Спільна межа для коротких текстових полів рейсу: марка тягача, причіп,
#: тип причепа, культура, ПІБ водія.
MAX_TRIP_TEXT = 120
#: Кг. Верхня межа свідомо із запасом — вона ловить описку на зайвий нуль,
#: а не встановлює норматив завантаження.
MAX_TRIP_MASS = 200_000
MAX_TRIP_STATUS = 64

#: Формати, у яких рейс зберігає дату й час. Валідація вводу спирається
#: на них же, щоб у колонці не опинилось двох різних написань.
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M"
