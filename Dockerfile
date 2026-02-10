# ベースイメージにPython 3.11の軽量版を使用
# ARM(ラズパイ)でも動作するマルチプラットフォーム対応
FROM python:3.11-slim

# 作業ディレクトリの設定
WORKDIR /app

# 依存関係ファイルのコピーとインストール
# opencv-python-headless を使うので、apt-get でのシステムライブラリは不要！
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードのコピー
COPY . .

# 環境変数の設定
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# ポートの開放
EXPOSE 8000

# サーバー（FastAPI）の起動
# ホストを 0.0.0.0 にすることで外部からアクセス可能にする
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
