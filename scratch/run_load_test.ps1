locust -f tests/load/locustfile.py --host=http://localhost:8000 --headless -u 10 -r 2 --run-time 30s
