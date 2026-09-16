FROM python:3.11-slim

WORKDIR /app

# 設定環境變數防止 Python 寫入 pyc 與啟用即時輸出
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安裝相依套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . .

# 預設連接埠為 8000 (雲端環境會自動以 $PORT 覆蓋)
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
