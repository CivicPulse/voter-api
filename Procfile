release: voter-api db upgrade
web: exec uvicorn --factory voter_api.main:create_app --host 0.0.0.0 --port $PORT
