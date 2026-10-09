FROM apache/superset:4.1.2

USER root
RUN pip install --no-cache-dir psycopg2-binary==2.9.10 Authlib==1.3.2
COPY --chown=superset:superset infra/superset/branding/ingevec_logo.png /app/superset/static/assets/images/ingevec_logo.png
USER superset
