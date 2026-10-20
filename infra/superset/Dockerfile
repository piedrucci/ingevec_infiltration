FROM apache/superset:6.1.0

USER root
# The image runs from a uv virtualenv (/app/.venv); plain pip would install outside it.
RUN uv pip install --no-cache psycopg2-binary==2.9.10 Authlib==1.3.2
COPY --chown=superset:superset infra/superset/branding/ingevec_logo.png /app/superset/static/assets/images/ingevec_logo.png
USER superset
