import os

# Server Configurations
HOST = os.getenv("EMR_GATEWAY_HOST", "127.0.0.1")
PORT = int(os.getenv("EMR_GATEWAY_PORT", "8000"))

# Database Credentials & Paths
DB_DIR = os.getenv("EMR_DB_DIR", "C:/mts3/db")
DB_USER = os.getenv("EMR_DB_USER", "SYSDBA")
DB_PASSWORD = os.getenv("EMR_DB_PASSWORD", "masterkey")

# Decryption Subprocess Settings
DECRYPT_WORKER_NAME = "DecryptWorker.exe"

# Default Check-In Settings
DEFAULT_ROOM_CODE = 1
DEFAULT_ROOM_NAME = "제1진료실"
DEFAULT_DEPT_CODE = "14"
DEFAULT_DEPT_NAME = "가정의학과"
DEFAULT_DOCTOR_CODE = "63221"
DEFAULT_DOCTOR_NAME = "한유석"
