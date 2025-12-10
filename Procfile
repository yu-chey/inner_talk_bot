worker-main: python -m src.main
worker-stats: python -m stats_bot.stats_bot
web: uvicorn server.api_server:app --host 0.0.0.0 --port $PORT