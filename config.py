import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BASE_URL = os.getenv("BASE_URL", "https://itcubefor.ru")
BOT_USERNAME = os.getenv("BOT_USERNAME", "ideya_fiks_59_bot")
SECRET_TEACHER_CODE = os.getenv("SECRET_TEACHER_CODE", "учитель11")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/database.db")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
