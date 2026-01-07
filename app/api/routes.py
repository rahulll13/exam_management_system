import os
import csv
import io
from datetime import datetime, timedelta
from itertools import groupby

from flask import Blueprint, request, jsonify, current_app, render_template
from sqlalchemy import func 
from app import db
from app.models import Student, Admin, Room, Exam, SeatAssignment, Teacher, Invigilation
from app.services.ai_engine import ai_engine
from app.services.seating_algo import generate_multi_branch_seating
from app.models import SeatAssignment, Student, Room, Exam  # Ensure these are imported at the top

api_bp = Blueprint('api', __name__)

@api_bp.route('/favicon.ico')
def favicon():
    return '', 204

# ==========================================
# 1. PAGE ROUTES
# ==========================================

@api_bp.route('/landing')
def landing_page():
    return render_template('landing.html')

@api_bp.route('/auth-ui/<role>') 
def auth_ui(role):
    if role == 'admin':
        return render_template('auth.html')
    return "Student Login Disabled.", 403

@api_bp.route('/student/search')
def student_search_ui():
    return render_template('student_search.html')

@api_bp.route('/dashboard/admin')
def admin_dashboard_ui():
    return render_template('admin_dashboard.html')

@api_bp.route('/teacher/search')
def teacher_search_ui(): 
    return render_template('teacher_search.html')

# ==========================================
# 2. AUTHENTICATION & AI
# ==========================================

@api_bp.route('/auth/admin/register', methods=['POST'])
def register_admin():
    data = request.json
    if data.get('admin_secret_code') != os.environ.get('ADMIN_SECRET_CODE', 'MySecureCollegeCode2025!'):
        return jsonify({"error": "Unauthorized"}), 403
    if Admin.query.filter_by(email=data.get('email')).first():
        return jsonify({"error": "Admin already exists"}), 400
    new_admin = Admin(username=data.get('username'), email=data.get('email'))
    new_admin.set_password(data.get('password'))
    db.session.add(new_admin); db.session.commit()
    return jsonify({"message": "Admin Access Granted"}), 201

@api_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    user = Admin.query.filter_by(email=data.get('email')).first()
    if user and user.check_password(data.get('password')):
        return jsonify({"message": "Welcome!", "redirect_url": "/dashboard/admin"}), 200
    return jsonify({"error": "Invalid Credentials"}), 401

def perform_training():
    assignments = SeatAssignment.query.all()
    if not assignments: return 0 
    real_data = []
    for seat in assignments:
        if seat.student and seat.room:
            real_data.append({
                'registration_number': seat.student.registration_number,
                'roll_number': seat.student.roll_number, 
                'seat': seat.seat_label,
                'room': seat.room.name, 'building': seat.room.building
            })
    if real_data: ai_engine.train(real_data); return len(real_data)
    return 0

@api_bp.route('/admin/train-ai', methods=['GET']) 
def train_ai_model():
    count = perform_training()
    return jsonify({"message": f"✅ AI learned {count} locations."})

@api_bp.route('/seat-lookup', methods=['GET'])
def lookup_seat():
    query = request.args.get('query')
    if not query: return jsonify({"error": "Query required"}), 400
    if not ai_engine.is_trained: perform_training()
    result = ai_engine.find_seat(query)
    
    # Auto-recovery
    if result.get('status') != 'success':
        perform_training()
        result = ai_engine.find_seat(query)
        
    if result.get('status') == 'success':
        sid = result['match_found']
        student = Student.query.filter((Student.registration_number == sid) | (Student.roll_number == sid)).first()
        if student:
            result['student_info'] = {'name': student.name, 'branch': student.branch, 'pic': student.profile_image}
            seat = SeatAssignment.query.filter_by(student_id=student.id).first()
            if seat:
                result['seat_details']['exam_name'] = seat.exam.name
                result['seat_details']['exam_date'] = seat.exam.date.strftime('%d-%b-%Y')
                result['seat_details']['exam_time'] = seat.exam.time_slot
                if seat.room:
                    result['layout'] = {'total_rows': seat.room.total_rows, 'total_cols': seat.room.total_columns, 'my_row': seat.row_num, 'my_col': seat.col_num}
    return jsonify(result)

# ==========================================
# 3. ADMIN FEATURES (ROOMS & STATS)
# ==========================================

@api_bp.route('/admin/get-all-rooms', methods=['GET'])
def get_all_rooms():
    rooms = Room.query.all()
    return jsonify([{'id': r.id, 'name': r.name, 'building': r.building, 'capacity': r.capacity} for r in rooms])

@api_bp.route('/admin/add-room', methods=['POST'])
def add_room():
    data = request.json
    try:
        matrix = data.get('layout_matrix', '')
        cap = matrix.count('1') if matrix else (int(data['rows']) * int(data['cols']))
        new_room = Room(name=data['name'], building=data.get('building', 'Main'), total_rows=int(data['rows']), total_columns=int(data['cols']), capacity=cap, layout_matrix=matrix)
        db.session.add(new_room); db.session.commit()
        return jsonify({"message": "Room created!"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@api_bp.route('/admin/update-room', methods=['POST'])
def update_room():
    data = request.json
    room = Room.query.get(int(data['room_id']))
    if not room: return jsonify({"error": "Room not found"}), 404
    room.total_rows = int(data['rows']); room.total_columns = int(data['cols'])
    room.capacity = room.total_rows * room.total_columns
    db.session.commit()
    return jsonify({"status": "success", "message": "Updated!"})

@api_bp.route('/admin/student-stats', methods=['POST'])
def get_student_stats():
    data = request.json
    query = db.session.query(Student.branch, func.count(Student.id))
    if data.get('session'): query = query.filter(Student.session.like(f"%{data['session']}%"))
    if data.get('branches'): 
        branch_list = [b.strip() for b in data['branches'].split(',')]
        query = query.filter(Student.branch.in_(branch_list))
    results = query.group_by(Student.branch).all()
    return jsonify({"matching_students": sum(c for _, c in results), "branch_breakdown": {b: c for b, c in results}})

@api_bp.route('/admin/bulk-upload', methods=['POST'])
def bulk_upload_students():
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['file']
    try:
        content = file.stream.read().decode("utf-8-sig")
        stream = io.StringIO(content, newline=None)
        
        sample = stream.read(1024); stream.seek(0)
        try: dialect = csv.Sniffer().sniff(sample)
        except: dialect = csv.excel; dialect.delimiter = ','
            
        reader = csv.reader(stream, dialect)
        try: raw_headers = next(reader)
        except: return jsonify({"error": "Empty CSV"}), 400
        
        headers = [h.strip().lower().replace(' ', '_') for h in raw_headers]
        if 'roll_number' not in headers: return jsonify({"error": "Missing roll_number"}), 400
        
        stream.seek(0); next(stream)
        csv_input = csv.DictReader(stream, fieldnames=headers, dialect=dialect)
        
        success, skipped = 0, 0
        for row in csv_input:
            roll = row.get('roll_number', '').strip()
            if not roll: continue
            
            # Use CSV Registration Number if present, otherwise use Roll Number
            csv_reg = row.get('registration_number', '').strip()
            final_reg_no = csv_reg if csv_reg else roll

            # Check exist (Roll OR Reg)
            if Student.query.filter((Student.roll_number == roll) | (Student.registration_number == final_reg_no)).first():
                skipped += 1; continue
                
            student = Student(
                name=row.get('name', '').strip(), 
                roll_number=roll,
                registration_number=final_reg_no, 
                email=row.get('email', '').strip(), 
                branch=row.get('branch', '').strip(),
                session=row.get('session', '2025').strip(), 
                profile_image='default.jpg'
            )
            student.set_password('welcome123')
            db.session.add(student)
            success += 1
        db.session.commit()
        return jsonify({"message": f"Added {success}, Skipped {skipped}"})
    except Exception as e:
        db.session.rollback(); return jsonify({"error": str(e)}), 500

# ==========================================
# 4. SEATING ALGORITHM & CHARTS
# ==========================================

@api_bp.route('/admin/generate-seating', methods=['POST'])
def run_seating_algo():
    data = request.json
    
    if data['branches'].strip().upper() == 'ALL':
        unique_branches = db.session.query(Student.branch).distinct().all()
        branch_names = [b[0] for b in unique_branches] 
    else:
        branch_names = [b.strip() for b in data['branches'].split(',')]

    target_session = data.get('target_session', '').strip()

    all_students_pool = []
    for branch in branch_names:
        query = Student.query.filter_by(branch=branch)
        if target_session:
            query = query.filter_by(session=target_session)
        students = query.all()
        if students:
            all_students_pool.extend(students)
    
    if not all_students_pool:
        return jsonify({"success": False, "error": "No students found."})

    # Strict Sort by Roll Number
    all_students_pool.sort(key=lambda s: (s.branch, s.roll_number))

    try:
        exam_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        
        raw_name = data['exam_name']
        sem = data.get('semester', '')
        final_exam_name = f"{raw_name} - {sem}" if sem else raw_name
        
        # Check if exam exists strictly
        exam = Exam.query.filter_by(name=final_exam_name, date=exam_date, time_slot=data['time']).first()
        if not exam:
            exam = Exam(name=final_exam_name, subject_code="MIXED", date=exam_date, time_slot=data['time'])
            db.session.add(exam); db.session.commit()

        SeatAssignment.query.filter_by(exam_id=exam.id).delete()
        db.session.commit()

        total_allocated = 0
        if str(data['room_id']).lower() == 'all':
            target_rooms = Room.query.order_by(Room.capacity.desc()).all()
        else:
            target_rooms = [Room.query.get(int(data['room_id']))]

        if not target_rooms: return jsonify({"success": False, "error": "No rooms found."})

        # --- Allocation Loop ---
        global_seated_ids = set()

        for room in target_rooms:
            # Filter pool: Remove students already seated in previous loop iterations
            current_pool = [s for s in all_students_pool if s.id not in global_seated_ids]
            if not current_pool: break 

            grouped_data = {}
            for s in current_pool:
                if s.branch not in grouped_data: grouped_data[s.branch] = []
                grouped_data[s.branch].append(s)
            
            result = generate_multi_branch_seating(exam.id, room.id, list(grouped_data.values()))
            
            if "allocated" in result and result["allocated"] > 0:
                total_allocated += result["allocated"]
                
                # Force DB Refresh
                db.session.commit()
                db.session.expire_all()
                
                just_seated = SeatAssignment.query.filter_by(exam_id=exam.id, room_id=room.id).all()
                for seat in just_seated:
                    global_seated_ids.add(seat.student_id)
            else:
                print(f"Room {room.name}: Full or Error - {result.get('error')}")

        return jsonify({
            "success": True, 
            "allocated": total_allocated, 
            "message": f"Allocated {total_allocated} students. {len(all_students_pool) - len(global_seated_ids)} remaining."
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@api_bp.route('/admin/get-exams-in-room/<int:room_id>', methods=['GET'])
def get_exams_in_room(room_id):
    if room_id == 0:
        assignments = db.session.query(SeatAssignment.exam_id).distinct().all()
        exam_ids = [r[0] for r in assignments]
    else:
        assignments = SeatAssignment.query.filter_by(room_id=room_id).all()
        exam_ids = {seat.exam_id for seat in assignments}
    
    exams_data = []
    for eid in exam_ids:
        exam = Exam.query.get(eid)
        if exam:
            sample = SeatAssignment.query.filter_by(exam_id=eid).first()
            batch = sample.student.session if (sample and sample.student) else "Unknown"
            exams_data.append({'id': exam.id, 'name': f"{exam.name} ({exam.date} | {exam.time_slot}) - Batch: {batch}"})
    return jsonify(exams_data)

@api_bp.route('/admin/get-seating-chart/<int:room_id>', methods=['GET'])
def get_seating_chart(room_id):
    exam_id = request.args.get('exam_id')
    
    def get_room_data(tid):
        room = Room.query.get(tid)
        if not room: return None
        assigns = SeatAssignment.query.filter_by(room_id=tid, exam_id=exam_id).all()
        seats = []
        for s in assigns:
            if s.student:
                seats.append({
                    'row': s.row_num, 'col': s.col_num, 'label': s.seat_label,
                    'student_name': s.student.name, 'branch': s.student.branch,
                    'roll': s.student.roll_number, 'session': s.student.session,
                    # --- ADDED REG NO FOR VISUAL TOGGLE ---
                    'reg_no': s.student.registration_number
                })
        return {"room_name": f"{room.building} - {room.name}", "rows": room.total_rows, "cols": room.total_columns, "seats": seats}

    if room_id == 0:
        active = db.session.query(SeatAssignment.room_id).filter_by(exam_id=exam_id).distinct().all()
        return jsonify({"mode": "multi", "rooms": [get_room_data(r[0]) for r in active if get_room_data(r[0])]})
    else:
        return jsonify(get_room_data(room_id) or {"error": "Not found"})

# ==========================================
# 5. RESET FUNCTIONS
# ==========================================

# Option A: Reset only Seating (Operational)
@api_bp.route('/admin/reset-seating', methods=['POST'])
def reset_seating():
    try:
        # 1. Delete Seat Assignments (Child of Exam)
        num_deleted = db.session.query(SeatAssignment).delete()
        
        # 2. Delete Invigilations (Child of Exam)
        db.session.query(Invigilation).delete()
        
        # 3. Now it is safe to delete Exams (Parent)
        db.session.query(Exam).delete()
        
        db.session.commit()
        return jsonify({"success": True, "message": f"System Reset! Cleared {num_deleted} seats and all duties."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

# Option B: Full Database Reset
@api_bp.route('/admin/reset-database', methods=['POST'])
def reset_database():
    try:
        # Delete operational data only, KEEP ADMINS
        SeatAssignment.query.delete()
        Invigilation.query.delete()
        Student.query.delete()
        Teacher.query.delete()
        Exam.query.delete()
        Room.query.delete()
        
        db.session.commit()
        
        # Clear AI
        ai_engine.is_trained = False
        ai_engine.search_tokens = []
        
        return jsonify({"message": "System Reset Successful. All operational data wiped."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ==========================================
# 6. STUDENT CRUD
# ==========================================

@api_bp.route('/admin/get-all-students', methods=['GET'])
def get_all_students_orm():
    try:
        students = Student.query.order_by(Student.roll_number).all()
        student_list = []
        for s in students:
            student_list.append({
                'id': s.id,
                'name': s.name,
                'reg_no': s.registration_number, 
                'roll_no': s.roll_number, 
                'branch': s.branch,
                'session': s.session
            })
        return jsonify(student_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/add-student', methods=['POST'])
def add_student_orm():
    try:
        data = request.json
        name = data.get('name')
        roll_no = data.get('roll_no')
        branch = data.get('branch')
        session = data.get('session')

        # If reg_no is provided, use it. Otherwise, use roll_no as Temporary Reg No.
        reg_no = data.get('registration_number')
        if not reg_no or reg_no.strip() == "":
            reg_no = roll_no 

        # Check if Roll OR Reg No exists
        existing = Student.query.filter(
            (Student.roll_number == roll_no) | 
            (Student.registration_number == reg_no)
        ).first()

        if existing:
            return jsonify({'status': 'error', 'message': 'Student with this Roll or Reg Number already exists'}), 400

        new_student = Student(
            name=name,
            roll_number=roll_no,
            registration_number=reg_no, 
            branch=branch,
            session=session,
            email="",
            profile_image='default.jpg'
        )
        new_student.set_password('welcome123') 

        db.session.add(new_student)
        db.session.commit()

        return jsonify({'status': 'success', 'message': 'Student added successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/admin/update-student', methods=['POST'])
def update_student_orm():
    try:
        data = request.json
        s_id = data.get('id')
        
        student = Student.query.get(s_id)
        if not student:
            return jsonify({'status': 'error', 'message': 'Student not found'}), 404

        student.name = data.get('name')
        student.registration_number = data.get('registration_number') 
        student.roll_number = data.get('roll_no')
        student.branch = data.get('branch')
        student.session = data.get('session')

        db.session.commit()

        return jsonify({'status': 'success', 'message': 'Student updated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/admin/delete-student', methods=['POST'])
def delete_student_orm():
    try:
        data = request.json
        s_id = data.get('id')

        student = Student.query.get(s_id)
        if not student:
            return jsonify({'status': 'error', 'message': 'Student not found'}), 404

        # Delete any associated Seat Assignments first
        SeatAssignment.query.filter_by(student_id=s_id).delete()
        
        db.session.delete(student)
        db.session.commit()

        return jsonify({'status': 'success', 'message': 'Student deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 7. TEACHERS & INVIGILATION
# ==========================================

@api_bp.route('/admin/add-teacher', methods=['POST'])
def add_teacher():
    data = request.json
    if Teacher.query.filter_by(employee_id=data['employee_id']).first(): return jsonify({"error": "Exists"}), 400
    db.session.add(Teacher(name=data['name'], employee_id=data['employee_id'], branch=data['branch'], email=data.get('email')))
    db.session.commit()
    return jsonify({"message": "Added!"})

@api_bp.route('/admin/get-all-teachers', methods=['GET'])
def get_all_teachers():
    return jsonify([{'id': t.id, 'name': t.name, 'empid': t.employee_id, 'branch': t.branch, 'email': t.email} for t in Teacher.query.all()])

@api_bp.route('/admin/assign-invigilator', methods=['POST'])
def assign_invigilator():
    data = request.json
    if Invigilation.query.filter_by(teacher_id=data['teacher_id'], exam_id=data['exam_id'], room_id=data['room_id']).first(): return jsonify({"error": "Assigned"}), 400
    db.session.add(Invigilation(teacher_id=data['teacher_id'], exam_id=data['exam_id'], room_id=data['room_id'])); db.session.commit()
    return jsonify({"message": "Assigned!"})

@api_bp.route('/teacher/get-schedule', methods=['GET'])
def get_teacher_schedule():
    t = Teacher.query.filter_by(employee_id=request.args.get('id')).first()
    if not t: return jsonify({"status": "error", "message": "Not found"})
    duties = Invigilation.query.filter_by(teacher_id=t.id).all()
    return jsonify({"status": "success", "teacher_name": t.name, "branch": t.branch, "schedule": [{"exam_name": d.exam.name, "date": d.exam.date.strftime('%d-%b-%Y'), "time": d.exam.time_slot, "room": d.room.name} for d in duties]})

@api_bp.route('/admin/get-all-duties', methods=['GET'])
def get_all_duties():
    return jsonify([{'id': d.id, 'teacher_name': d.teacher.name, 'teacher_id': d.teacher.employee_id, 'exam_name': d.exam.name, 'date': d.exam.date.strftime('%d-%b-%Y'), 'time': d.exam.time_slot, 'room': d.room.name} for d in Invigilation.query.all()])

@api_bp.route('/admin/delete-duty', methods=['POST'])
def delete_duty():
    data = request.json
    duty_id = data.get('duty_id')
    try:
        duty = Invigilation.query.get(duty_id)
        if duty:
            db.session.delete(duty)
            db.session.commit()
            return jsonify({"message": "Duty removed successfully"})
        return jsonify({"error": "Duty not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# 8. REPORTS (NOTICE BOARD / ATTENDANCE / MASTER)
# ==========================================

@api_bp.route('/admin/notice-board-data', methods=['GET'])
def get_notice_board_data():
    date_str = request.args.get('date'); time = request.args.get('time')
    batch = request.args.get('batch'); room_id = request.args.get('room_id')
    semester = request.args.get('semester', '')
    
    # --- UPDATE: GET ID TYPE PREFERENCE ---
    id_type = request.args.get('id_type', 'roll') # Default to roll if not provided

    if not date_str or not time: return jsonify({"error": "Date/Time required"}), 400

    try:
        exam_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        query = db.session.query(SeatAssignment).join(Exam).filter(Exam.date == exam_date, Exam.time_slot == time).join(Student)

        if batch: query = query.filter(Student.session == batch.strip())
        if room_id: query = query.filter(SeatAssignment.room_id == int(room_id))
        
        # Initial sort by room building/name
        assignments = query.join(Room).order_by(Room.building, Room.name, Room.id, Student.branch).all()

        if not assignments: return jsonify({"error": "No data found."}), 404

        report_data = []
        for room, r_seats in groupby(assignments, key=lambda x: x.room):
            seats_list = list(r_seats)
            room_entry = {"hall_no": f"{room.building} - {room.name}", "branches": [], "room_total": len(seats_list)}

            # Group by branch
            seats_list.sort(key=lambda x: x.student.branch)
            for branch, b_seats in groupby(seats_list, key=lambda x: x.student.branch):
                students = [s.student for s in b_seats]
                
                # --- UPDATE: SORT & CALCULATE RANGE BASED ON ID TYPE ---
                if id_type == 'reg':
                    # Sort by Registration Number (Handle None values safely)
                    students.sort(key=lambda s: s.registration_number if s.registration_number else "ZZZZ")
                    
                    start_val = students[0].registration_number if students[0].registration_number else "N/A"
                    end_val = students[-1].registration_number if students[-1].registration_number else "N/A"
                    range_str = f"{start_val} To {end_val}"
                else:
                    # Sort by Roll Number (Default)
                    students.sort(key=lambda s: s.roll_number)
                    
                    start_val = students[0].roll_number
                    end_val = students[-1].roll_number
                    range_str = f"{start_val} To {end_val}"

                room_entry["branches"].append({
                    "name": branch,
                    "range": range_str,
                    "count": len(students)
                })
            report_data.append(room_entry)

        return jsonify({
            "status": "success",
            "exam_info": { 
                "date": exam_date.strftime('%d-%m-%Y'), 
                "time": time, 
                "title": assignments[0].exam.name, 
                "batch": batch or "All",
                "semester": semester
            },
            "data": report_data
        })
    except Exception as e: return jsonify({"error": str(e)}), 500
    


# --- REPLACE existing 'get_attendance_sheet_data' with this IMPROVED version --

@api_bp.route('/admin/question-distribution', methods=['GET'])
def get_question_distribution():
    date_str = request.args.get('date')
    time = request.args.get('time')

    if not date_str or not time:
        return jsonify({"error": "Date and Time are required"}), 400

    try:
        exam_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        query = (db.session.query(SeatAssignment)
                 .join(Exam)
                 .filter(Exam.date == exam_date)
                 .filter(Exam.time_slot.ilike(f"%{time.strip()}%"))
                 .join(Student)
                 .join(Room)
                 .order_by(Student.branch, Room.name))
        
        assignments = query.all()

        if not assignments:
            return jsonify({"error": "No seating found for this date/time."}), 404

        distribution_data = []
        
        for branch, branch_seats in groupby(assignments, key=lambda x: x.student.branch):
            branch_seats_list = list(branch_seats)
            room_breakdown = []
            total_students = 0
            
            branch_seats_list.sort(key=lambda x: x.room.name)
            for room, room_seats in groupby(branch_seats_list, key=lambda x: x.room):
                count = len(list(room_seats))
                room_breakdown.append(f"{room.name} = {count}")
                total_students += count
            
            breakdown_str = ", ".join(room_breakdown)

            distribution_data.append({
                "branch": branch,
                "breakdown": breakdown_str,
                "total": total_students
            })

        exam_info = {
            "name": assignments[0].exam.name,
            "date": exam_date.strftime('%d-%m-%Y'),
            "time": assignments[0].exam.time_slot
        }

        return jsonify({
            "status": "success",
            "exam": exam_info,
            "data": distribution_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/admin/master-chart', methods=['GET'])
def get_master_chart():
    date_str = request.args.get('date')
    time = request.args.get('time')
    
    if not date_str or not time:
        return jsonify({"error": "Date and Time are required"}), 400
    
    try:
        exam_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        assignments = (db.session.query(SeatAssignment)
                       .join(Exam).filter(Exam.date == exam_date, Exam.time_slot.ilike(f"%{time.strip()}%"))
                       .join(Room).join(Student)
                       .order_by(Room.building, Room.name, Student.branch)
                       .all())
                          
        if not assignments:
            return jsonify({"error": "No seating found for this date/time."}), 404
            
        master_data = []
        grand_total = 0
        
        for room, r_seats in groupby(assignments, key=lambda x: x.room):
            r_seats_list = list(r_seats)
            room_entry = {
                "hall_no": f"{room.building} - {room.name}", 
                "branches": []
            }
            
            r_seats_list.sort(key=lambda x: x.student.branch)
            
            for branch, b_seats in groupby(r_seats_list, key=lambda x: x.student.branch):
                count = len(list(b_seats))
                room_entry["branches"].append({
                    "name": branch,
                    "count": count
                })
                grand_total += count
            
            master_data.append(room_entry)
            
        date_headers = []
        for i in range(6):
            d = exam_date + timedelta(days=i)
            date_headers.append(d.strftime('%d.%m.%y'))

        return jsonify({
            "status": "success",
            "exam_title": assignments[0].exam.name,
            "timing": time,
            "date_headers": date_headers,
            "data": master_data,
            "grand_total": grand_total
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ADD THIS NEW ROUTE ---
@api_bp.route('/admin/get-exam-times', methods=['GET'])
def get_exam_times():
    try:
        # 1. Get the date string (YYYY-MM-DD) from the frontend
        date_str = request.args.get('date')
        
        if not date_str:
            return jsonify([]), 400

        # 2. Convert string to Python Date object (Required because your model uses db.Date)
        try:
            search_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400

        # 3. Query the 'Exam' table defined in your models.py
        # We look for all exams happening on that specific date
        exams = Exam.query.filter_by(date=search_date).all()
        
        # 4. Extract unique time slots
        # We use set() to remove duplicates (e.g., if two exams are at 10:00 AM, we only want "10:00 AM" once)
        unique_times = list(set([exam.time_slot for exam in exams]))
        
        # 5. Send back as JSON
        return jsonify(unique_times)

    except Exception as e:
        print(f"Error fetching times: {e}")
        return jsonify({'error': str(e)}), 500


# --- PASTE THIS NEW FUNCTION AT THE BOTTOM ---

@api_bp.route('/admin/attendance-sheet-data', methods=['GET'])
def attendance_sheet_data():
    try:
        # 1. Get parameters
        date_str = request.args.get('date')
        time_slot = request.args.get('time')
        room_id = request.args.get('room_id')

        if not date_str or not time_slot:
            return jsonify({'error': 'Date and Time are required'}), 400

        search_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # 2. Query Data
        query = db.session.query(SeatAssignment).join(Exam).join(Student).join(Room).filter(
            Exam.date == search_date,
            Exam.time_slot.ilike(f"%{time_slot.strip()}%")
        )

        if room_id and room_id != 'all':
            query = query.filter(Room.id == int(room_id))

        # Initial Sort: Group by Room and Branch so we can build the dictionaries easily
        assignments = query.order_by(Room.name, Student.branch, Student.registration_number).all()

        if not assignments:
            return jsonify({'sheets': []})

        # 3. Group Data
        sheets_data = {}
        
        for seat in assignments:
            r_name = seat.room.name
            b_name = seat.student.branch
            
            # Unique key ensures separate sheets for different branches in the same room
            unique_key = f"{r_name}_{b_name}"
            
            if unique_key not in sheets_data:
                sheets_data[unique_key] = {
                    'hall_no': r_name,
                    'exam_name': seat.exam.name,
                    'semester': seat.student.session, 
                    'branch': b_name,
                    'students': []
                }
            
            sheets_data[unique_key]['students'].append({
                'sl': len(sheets_data[unique_key]['students']) + 1,
                'reg_no': seat.student.registration_number, 
                'name': seat.student.name
            })

        # 4. FINAL SORTING (The Fix)
        # Convert the dictionary values to a list
        final_sheets = list(sheets_data.values())

        # Sort the list of sheets so that:
        # 1. Branches are grouped together (e.g., all CSE sheets first)
        # 2. Inside a branch, sheets are ordered by the Registration Number of the first student
        final_sheets.sort(key=lambda x: (x['branch'], x['students'][0]['reg_no']))

        return jsonify({'sheets': final_sheets})

    except Exception as e:
        print(f"Error generating attendance: {e}")
        return jsonify({'error': str(e)}), 500