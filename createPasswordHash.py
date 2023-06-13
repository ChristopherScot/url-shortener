from werkzeug.security import generate_password_hash

password = input("Enter password: ")
print("hash: " + generate_password_hash(password))
