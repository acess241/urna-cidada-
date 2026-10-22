FROM python:3.12-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home urna && mkdir /data && chown urna:urna /data
COPY --chown=urna:urna server.py ./
COPY --chown=urna:urna public ./public
USER urna
ENV PORT=8080 DATABASE_PATH=/data/urna.sqlite PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
CMD ["python", "server.py"]
