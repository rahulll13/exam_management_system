from app import db
from app.models import SeatAssignment, Room, Student
import math

# --- 1. CORE SEATING FUNCTION (Places students in seats) ---
def generate_multi_branch_seating(exam_id, room_id, student_groups):
    """
    Matrix-Aware Seating Strategy:
    - Fills valid seats ('1' in layout_matrix) vertically.
    - Uses Shifted Interleaving to prevent same-branch neighbors.
    - Sorting: Registration Number (Numeric Priority).
    """
    # print(f"--- 🔵 SEATING ROOM {room_id} | Groups: {len(student_groups)} ---")
    
    room = Room.query.get(room_id)
    if not room: return {"error": "Room not found"}

    rows = room.total_rows
    cols = room.total_columns
    
    # Parse Layout Matrix
    if room.layout_matrix:
        flat_list = [int(x) for x in room.layout_matrix.split(',')]
        if len(flat_list) != rows * cols:
            layout_grid = [[1 for _ in range(cols)] for _ in range(rows)]
        else:
            layout_grid = [flat_list[i * cols:(i + 1) * cols] for i in range(rows)]
    else:
        layout_grid = [[1 for _ in range(cols)] for _ in range(rows)]

    # Sorting Strategy: Registration Number (Numeric)
    def sort_key(student):
        s_reg = str(student.registration_number or "").strip()
        # Extract numeric part to ensure "2301" < "23010"
        numeric_part = ''.join(filter(str.isdigit, s_reg))
        val_reg = int(numeric_part) if numeric_part else float('inf')
        return val_reg

    sorted_groups = []
    for g in student_groups:
        # Sort each branch list internally by Reg No
        sorted_g = sorted(g, key=sort_key)
        sorted_groups.append(sorted_g)

    group_counters = [0] * len(sorted_groups)
    num_groups = len(sorted_groups)
    
    assignments = []
    
    # Filling Logic (Vertical Traverse with Offset)
    for c in range(1, cols + 1):          
        col_start_offset = (c - 1)
        
        for r in range(1, rows + 1):
            
            if layout_grid[r-1][c-1] == 0: continue # Skip Invalid Seat

            student_to_seat = None
            
            # Smart Branch Selection:
            # Rotates the "Preferred Branch" based on Row/Col to create Checkerboard
            ideal_branch_idx = ((r - 1) + col_start_offset) % num_groups
            
            # Try finding a student, starting from the ideal branch
            for i in range(num_groups):
                try_idx = (ideal_branch_idx + i) % num_groups
                if group_counters[try_idx] < len(sorted_groups[try_idx]):
                    student_to_seat = sorted_groups[try_idx][group_counters[try_idx]]
                    group_counters[try_idx] += 1
                    break
            
            if student_to_seat:
                new_seat = SeatAssignment(
                    student_id=student_to_seat.id, 
                    exam_id=exam_id, 
                    room_id=room.id,
                    row_num=r, 
                    col_num=c, 
                    seat_label=f"R{r}-C{c}"
                )
                assignments.append(new_seat)

    try:
        db.session.add_all(assignments)
        db.session.commit()
        return {"success": True, "allocated": len(assignments)}
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}

# --- 2. GLOBAL DISTRIBUTION LOGIC (Fixes the "All PIE in one room" issue) ---
def allocate_and_seat_global(exam_id, session, branch_list_str, room_ids):
    """
    Proportional Distributor:
    Instead of filling Room 1 with Branch A, then Room 2 with Branch B...
    This calculates the Global Ratio and ensures EVERY room gets a mix 
    (e.g., 30% CSE, 30% MECH, 40% PIE) before seating begins.
    """
    
    # 1. Fetch ALL relevant students
    branch_names = [b.strip() for b in branch_list_str.split(',') if b.strip()]
    
    all_students_by_branch = {}
    total_students_count = 0

    for b_name in branch_names:
        # Fetch students for this branch & session
        # (Assuming you have a Student.session and Student.branch field)
        students = Student.query.filter(
            Student.session == session, 
            Student.branch == b_name
        ).all()
        
        if students:
            all_students_by_branch[b_name] = students
            total_students_count += len(students)

    if total_students_count == 0:
        return {"error": "No students found for the selected branches."}

    # 2. Fetch All Rooms & Sort by Capacity (Largest first usually better)
    rooms = Room.query.filter(Room.id.in_(room_ids)).all()
    # Optional: Sort rooms by capacity if desired
    # rooms.sort(key=lambda x: int(x.capacity or 0), reverse=True)

    success_log = []
    
    # 3. Distribute & Seat Room by Room
    for room in rooms:
        room_capacity = int(room.capacity) if room.capacity else 0
        if room_capacity <= 0: continue

        # Calculate this room's "Slice" of the pie
        room_groups = []
        
        # Determine how many students from each branch go into THIS room
        for b_name, student_pool in all_students_by_branch.items():
            pool_size = len(student_pool)
            if pool_size == 0: continue

            # Proportional Quota: (Branch_Total / Global_Total) * Room_Capacity
            # Example: If CSE is 50% of total students, they get 50% of this room.
            quota = math.ceil((pool_size / total_students_count) * room_capacity)
            
            # Take students from the pool
            take_count = min(quota, len(student_pool))
            chunk = student_pool[:take_count]
            
            # Remove them from the global pool so they aren't seated twice
            all_students_by_branch[b_name] = student_pool[take_count:]
            
            # Add to this room's group
            room_groups.append(chunk)

        # Update remaining count for next iteration
        total_students_count = sum(len(s) for s in all_students_by_branch.values())

        # 4. Run the Seating Algo for THIS room with the Mixed Group
        if any(len(g) > 0 for g in room_groups):
            res = generate_multi_branch_seating(exam_id, room.id, room_groups)
            if res.get("success"):
                success_log.append(f"Room {room.name}: {res['allocated']} seated")
        
        if total_students_count == 0:
            break # All students seated

    return {"success": True, "message": f"Global Allocation Complete. {', '.join(success_log)}"}