from app import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# --- STUDENT MODEL (Updated with Password) ---
class Student(UserMixin, db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    registration_number = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    branch = db.Column(db.String(50), nullable=False)
    session = db.Column(db.String(20), nullable=False)
    profile_image = db.Column(db.String(200), nullable=False, default='default.jpg')
    
    # NEW: Password Field
    password_hash = db.Column(db.String(255), nullable=False) # Changed size for hash
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- NEW: ADMIN MODEL ---
class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
# ... (Keep Student and Admin classes above) ...

class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)   # e.g., "Lecture Hall 01"
    
    building = db.Column(db.String(50), nullable=False, default='Lecture Hall')
    
    total_rows = db.Column(db.Integer, nullable=False) # e.g., 10
    total_columns = db.Column(db.Integer, nullable=False) # e.g., 6
    capacity = db.Column(db.Integer, nullable=False)  # rows * columns (Auto-calculated usually)
    layout_matrix = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Room {self.name} ({self.total_rows}x{self.total_columns})>'

class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # e.g., "End Semester 2025"
    subject_code = db.Column(db.String(20), nullable=False) # e.g., "IT-301"
    date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(50), nullable=False) # e.g., "10:00 AM - 01:00 PM"

class SeatAssignment(db.Model):
    __tablename__ = 'seat_assignments'
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign Keys
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    
    # The Exact Location
    row_num = db.Column(db.Integer, nullable=False) # 1, 2, 3...
    col_num = db.Column(db.Integer, nullable=False) # 1, 2, 3...
    seat_label = db.Column(db.String(10)) # e.g., "R1-C2" or "A5"

    # Relationships for easy access
    student = db.relationship('Student', backref='seats')
    exam = db.relationship('Exam', backref='seatings')
    room = db.relationship('Room', backref='assignments')
    
# ... (Student, Room, Exam, SeatAssignment classes are above) ...

class Teacher(db.Model):
    __tablename__ = 'teachers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    employee_id = db.Column(db.String(50), unique=True, nullable=False) # e.g., T-101
    branch = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=True)

class Invigilation(db.Model):
    __tablename__ = 'invigilations'
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    
    # Relationships
    teacher = db.relationship('Teacher', backref='duties')
    exam = db.relationship('Exam', backref='invigilators')
    room = db.relationship('Room', backref='invigilations')