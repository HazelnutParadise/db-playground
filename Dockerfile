FROM python:3.13-slim

# 安裝必要的系統依賴和 MSSQL 驅動程序
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    unixodbc-dev \
    curl \
    apt-transport-https \
    gnupg \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && echo "deb [arch=amd64] https://packages.microsoft.com/debian/10/prod buster main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 設置工作目錄
WORKDIR /app

# 拷貝依賴文件
COPY . .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 運行應用
CMD ["python", "main.py"]
