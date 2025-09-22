FROM python:3.13-slim

# 安裝必要的系統依賴和 MSSQL 驅動程序
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 設置工作目錄
WORKDIR /app

# 拷貝依賴文件
COPY . .

# 安裝 Python 依賴
RUN cd backend && pip install --no-cache-dir -r requirements.txt

# 運行應用
CMD ["python", "backend/main.py"]
