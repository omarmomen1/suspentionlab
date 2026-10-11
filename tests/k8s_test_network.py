import socket
import sys

print("Testing Redis Service...")
try:
    s = socket.socket()
    s.settimeout(3)
    s.connect(("redis.suspensionlab.svc.cluster.local", 6379))
    print("Redis Service connected successfully!")
except Exception as e:
    print(f"Redis Service connection failed: {e}")

print("Testing Redis Direct Pod IP 10.42.0.6:6379...")
try:
    s = socket.socket()
    s.settimeout(3)
    s.connect(("10.42.0.6", 6379))
    print("Redis Direct Pod IP connected successfully!")
except Exception as e:
    print(f"Redis Direct Pod IP failed: {e}")

print("Testing Postgres Service...")
try:
    s2 = socket.socket()
    s2.settimeout(3)
    s2.connect(("postgres.suspensionlab.svc.cluster.local", 5432))
    print("Postgres Service connected successfully!")
except Exception as e:
    print(f"Postgres Service connection failed: {e}")

print("Testing Postgres Direct Pod IP 10.42.0.5:5432...")
try:
    s2 = socket.socket()
    s2.settimeout(3)
    s2.connect(("10.42.0.5", 5432))
    print("Postgres Direct Pod IP connected successfully!")
except Exception as e:
    print(f"Postgres Direct Pod IP failed: {e}")
