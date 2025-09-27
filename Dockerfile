# 베이스 이미지: 경량 + 보안 업데이트 최신
FROM python:3.11-slim

# 필수 패키지 (휠 빌드 대비)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# 워킹 디렉터리
WORKDIR /app

# 의존성 먼저 복사 → 캐시 활용
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 전체 복사
COPY . /app

# 비루트 유저로 전환 (보안)
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# 포트/환경
ENV PORT=7860
EXPOSE 7860

# 실행
CMD ["python", "-m", "main"]