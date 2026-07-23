import jwt

# Since JWT_SECRET is not set, it's empty string "" in JS: new TextEncoder().encode("")
# In python, empty string bytes is b""
encoded_jwt = jwt.encode({"user_id": "test"}, b"", algorithm="HS256")
print(encoded_jwt)
