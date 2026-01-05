import mysql.connector
from mysql.connector import Error

# REPLACE 'YOUR_PASSWORD' BELOW WITH WHAT YOU THINK IT IS
# Leave it empty '' if you think there is no password
password_to_test = '1234' 

try:
    connection = mysql.connector.connect(
        host='localhost',
        user='root',
        password=password_to_test
    )
    if connection.is_connected():
        print("✅ SUCCESS! The password is correct.")
        print("Use this password in your .env file.")
except Error as e:
    print(f"❌ ERROR: {e}")
    if "Access denied" in str(e):
        print(">> This means the password is WRONG. Try a different one.")
    elif "Unknown database" in str(e):
        print(">> Password is CORRECT, but the database name is wrong (that's okay for now).")
    elif "Can't connect" in str(e):
        print(">> MySQL Server is NOT RUNNING. Please start MySQL Service or XAMPP.")