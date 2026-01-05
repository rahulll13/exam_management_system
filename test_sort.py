# test_sort.py
students = [
    "23030480039",  # The large number (23 Billion)
    "2311001",      # The small number (2 Million)
    "   2311002  "  # A number with spaces
]

print("--- OLD WAY (Text Sort - BAD) ---")
print(sorted(students)) 
# Result: ['   2311002  ', '23030480039', '2311001'] (WRONG ORDER)

print("\n--- NEW WAY (Nuclear Fix - GOOD) ---")
def smart_sort(val):
    clean = ''.join(filter(str.isdigit, val))
    return int(clean)

print(sorted(students, key=smart_sort))
# Result: ['2311001', '   2311002  ', '23030480039'] (CORRECT ORDER)