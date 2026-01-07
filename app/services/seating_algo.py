from app import db
from app.models import SeatAssignment, Room, Student

def generate_multi_branch_seating(exam_id, room_id, student_groups):
    """
    Matrix-Aware Seating Strategy:
    - Checks room.layout_matrix to see if a seat physically exists.
    - If layout says '0', skip that seat.
    - Fills valid seats ('1') vertically using shifted interleaving.
    """
    print(f"--- 🔵 STARTING MATRIX SEATING FOR ROOM {room_id} ---")
    
    room = Room.query.get(room_id)
    if not room: return {"error": "Room not found"}

    rows = room.total_rows
    cols = room.total_columns
    
    # Parse Layout: Convert "1,0,1..." string to 2D Array
    # Default to all 1s if no layout exists
    if room.layout_matrix:
        flat_list = [int(x) for x in room.layout_matrix.split(',')]
        # Create 2D grid: layout_grid[row][col]
        layout_grid = [flat_list[i * cols:(i + 1) * cols] for i in range(rows)]
    else:
        layout_grid = [[1 for _ in range(cols)] for _ in range(rows)]

    # --- CRITICAL FIX: SORT BY ROLL NUMBER ---
    # Previously: key=lambda x: x.registration_number
    # Now: key=lambda x: x.roll_number (Ensures 2311001 sits before 2311002)
    sorted_groups = []
    for g in student_groups:
        sorted_g = sorted(g, key=lambda x: int(''.join(filter(str.isdigit, str(x.registration_number or '0')))))
        sorted_groups.append(sorted_g)
    # -----------------------------------------

    group_counters = [0] * len(sorted_groups)
    num_groups = len(sorted_groups)
    
    assignments = []
    
    # Loop Columns -> Rows (Vertical Filling)
    for c in range(1, cols + 1):          
        col_start_offset = (c - 1)
        
        for r in range(1, rows + 1):
            
            # --- CHECK: DOES THIS SEAT EXIST? ---
            # Grid is 0-indexed, database is 1-indexed
            if layout_grid[r-1][c-1] == 0:
                # print(f"Skipping R{r}-C{c} (Space/Pillar)")
                continue # Skip this loop iteration
            # ------------------------------------

            student_to_seat = None
            ideal_branch_idx = ((r - 1) + col_start_offset) % num_groups
            
            for i in range(num_groups):
                try_idx = (ideal_branch_idx + i) % num_groups
                if group_counters[try_idx] < len(sorted_groups[try_idx]):
                    student_to_seat = sorted_groups[try_idx][group_counters[try_idx]]
                    group_counters[try_idx] += 1
                    break
            
            if student_to_seat:
                new_seat = SeatAssignment(
                    student_id=student_to_seat.id, exam_id=exam_id, room_id=room.id,
                    row_num=r, col_num=c, seat_label=f"R{r}-C{c}"
                )
                assignments.append(new_seat)

    try:
        # Note: We do NOT delete here anymore because routes.py handles the cleanup 
        # before calling this function for multiple rooms.
        # But for safety in single-run contexts, we append.
        
        db.session.add_all(assignments)
        db.session.commit()
        return {"success": True, "allocated": len(assignments)}
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}