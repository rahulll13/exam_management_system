from app import create_app, db
from app.models import Room

app = create_app()

print("\n====== DIAGNOSTIC REPORT ======")

# TEST 1: Check if the Code exists (The Route)
route_found = False
for rule in app.url_map.iter_rules():
    if "get-seating-chart" in str(rule):
        print(f"✅ SUCCESS: Route found -> {rule}")
        route_found = True
        break

if not route_found:
    print("❌ FAILURE: The Route is MISSING from Flask.")
    print("   -> Solution: The code in routes.py didn't save or is in the wrong place.")

# TEST 2: Check if the Data exists (The Room)
print("\n====== CHECKING DATABASE ======")
with app.app_context():
    rooms = Room.query.all()
    if not rooms:
        print("❌ FAILURE: No Rooms found in the database.")
        print("   -> Solution: Go to 'Manage Rooms' and create a room first.")
    else:
        print(f"✅ SUCCESS: Found {len(rooms)} room(s).")
        for r in rooms:
            print(f"   -> Room ID: {r.id} | Name: {r.name}")
            
print("===============================\n")