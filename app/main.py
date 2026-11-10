import os
from datetime import date, time, datetime
from functools import wraps
from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Date, Time, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from passlib.context import CryptContext

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:admin@localhost:5432/sportbook"
)
SECRET_KEY = os.getenv("SECRET_KEY", "ganti-dengan-secret-key-acak-untuk-deployment")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="SportBook API", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="customer")
    bookings = relationship("Booking", back_populates="customer")


class Sport(Base):
    __tablename__ = "sports"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    description = Column(String(255))
    courts = relationship("Court", back_populates="sport")


class Court(Base):
    __tablename__ = "courts"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    sport_id = Column(Integer, ForeignKey("sports.id"), nullable=False)
    location = Column(String(150), nullable=False)
    price_per_hour = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="Aktif")
    sport = relationship("Sport", back_populates="courts")
    bookings = relationship("Booking", back_populates="court")


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    court_id = Column(Integer, ForeignKey("courts.id"), nullable=False)
    booking_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    total_price = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="Menunggu")
    created_at = Column(DateTime, default=datetime.utcnow)
    customer = relationship("User", back_populates="bookings")
    court = relationship("Court", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False)


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True, nullable=False)
    amount = Column(Integer, nullable=False)
    method = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False, default="Belum Dibayar")
    paid_at = Column(DateTime)
    booking = relationship("Booking", back_populates="payment")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id else None


def page(request: Request, name: str, db: Session, **context):
    return templates.TemplateResponse(
        request=request, name=name,
        context={"user": get_user(request, db), **context}
    )


def require_user(request: Request, db: Session):
    user = get_user(request, db)
    if not user:
        return None
    return user


def redirect_login():
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse("/dashboard" if get_user(request, db) else "/login", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    return page(request, "register.html", db)


@app.post("/register")
def register(request: Request, name: str = Form(...), email: str = Form(...),
             password: str = Form(...), db: Session = Depends(get_db)):
    name, email = name.strip(), email.strip().lower()
    if len(password) < 6 or not name:
        return page(request, "register.html", db, error="Nama wajib diisi dan password minimal 6 karakter.")
    if db.query(User).filter(User.email == email).first():
        return page(request, "register.html", db, error="Email sudah terdaftar.")
    user = User(name=name, email=email, password_hash=pwd_context.hash(password), role="customer")
    db.add(user)
    db.commit()
    return RedirectResponse("/login?registered=1", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    return page(request, "login.html", db, registered=request.query_params.get("registered"))


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        return page(request, "login.html", db, error="Email atau password salah.")
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return redirect_login()
    if user.role == "admin":
        court_count = db.query(Court).count()
        booking_query = db.query(Booking)
        pending = db.query(Booking).filter(Booking.status == "Menunggu").count()
        revenue = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.status == "Lunas").scalar()
    else:
        court_count = db.query(Court).filter(Court.status == "Aktif").count()
        booking_query = db.query(Booking).filter(Booking.user_id == user.id)
        pending = booking_query.filter(Booking.status == "Menunggu").count()
        revenue = db.query(func.coalesce(func.sum(Payment.amount), 0)).join(Booking).filter(
            Booking.user_id == user.id, Payment.status == "Lunas").scalar()
    recent = booking_query.order_by(Booking.created_at.desc()).limit(8).all()
    total_bookings = booking_query.count()
    return page(request, "dashboard.html", db, court_count=court_count,
                total_bookings=total_bookings, pending=pending, revenue=revenue, recent=recent)


# MASTER DATA: SPORTS
@app.get("/sports", response_class=HTMLResponse)
def sports_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user: return redirect_login()
    if user.role != "admin": return RedirectResponse("/dashboard", status_code=303)
    return page(request, "sports.html", db, sports=db.query(Sport).order_by(Sport.name).all())


@app.post("/sports")
def create_sport(request: Request, name: str = Form(...), description: str = Form(""),
                 db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    if db.query(Sport).filter(func.lower(Sport.name) == name.strip().lower()).first():
        return RedirectResponse("/sports?error=duplicate", status_code=303)
    db.add(Sport(name=name.strip(), description=description.strip()))
    db.commit()
    return RedirectResponse("/sports", status_code=303)


@app.post("/sports/{sport_id}/delete")
def delete_sport(sport_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    sport = db.get(Sport, sport_id)
    if sport:
        if sport.courts:
            return RedirectResponse("/sports?error=used", status_code=303)
        db.delete(sport)
        db.commit()
    return RedirectResponse("/sports", status_code=303)


# MASTER DATA: COURTS
@app.get("/courts", response_class=HTMLResponse)
def courts_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user: return redirect_login()
    query = db.query(Court)
    if user.role != "admin": query = query.filter(Court.status == "Aktif")
    return page(request, "courts.html", db, courts=query.order_by(Court.name).all())


@app.get("/courts/new", response_class=HTMLResponse)
def court_new_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    return page(request, "court_form.html", db, court=None, sports=db.query(Sport).all())


@app.post("/courts/new")
def court_create(request: Request, name: str = Form(...), sport_id: int = Form(...),
                 location: str = Form(...), price_per_hour: int = Form(...),
                 status: str = Form("Aktif"), db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    if price_per_hour <= 0 or not db.get(Sport, sport_id):
        return RedirectResponse("/courts/new?error=invalid", status_code=303)
    db.add(Court(name=name.strip(), sport_id=sport_id, location=location.strip(),
                 price_per_hour=price_per_hour, status=status))
    db.commit()
    return RedirectResponse("/courts", status_code=303)


@app.get("/courts/{court_id}/edit", response_class=HTMLResponse)
def court_edit_page(court_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    court = db.get(Court, court_id)
    if not court: raise HTTPException(404, "Lapangan tidak ditemukan")
    return page(request, "court_form.html", db, court=court, sports=db.query(Sport).all())


@app.post("/courts/{court_id}/edit")
def court_edit(court_id: int, request: Request, name: str = Form(...),
               sport_id: int = Form(...), location: str = Form(...),
               price_per_hour: int = Form(...), status: str = Form("Aktif"),
               db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    court = db.get(Court, court_id)
    if not court: raise HTTPException(404)
    if price_per_hour <= 0 or not db.get(Sport, sport_id):
        return RedirectResponse(f"/courts/{court_id}/edit?error=invalid", status_code=303)
    court.name, court.sport_id = name.strip(), sport_id
    court.location, court.price_per_hour, court.status = location.strip(), price_per_hour, status
    db.commit()
    return RedirectResponse("/courts", status_code=303)


@app.post("/courts/{court_id}/delete")
def court_delete(court_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    court = db.get(Court, court_id)
    if court:
        if court.bookings:
            court.status = "Tidak Aktif"
        else:
            db.delete(court)
        db.commit()
    return RedirectResponse("/courts", status_code=303)


# TRANSACTIONS: BOOKINGS
def booking_conflict(db, court_id, booking_date, start, end):
    return db.query(Booking).filter(
        Booking.court_id == court_id,
        Booking.booking_date == booking_date,
        Booking.status != "Dibatalkan",
        Booking.status != "Ditolak",
        Booking.start_time < end,
        Booking.end_time > start
    ).first() is not None


@app.get("/bookings", response_class=HTMLResponse)
def bookings_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user: return redirect_login()
    query = db.query(Booking)
    if user.role != "admin": query = query.filter(Booking.user_id == user.id)
    rows = query.order_by(Booking.created_at.desc()).all()
    return page(request, "bookings.html", db, bookings=rows)


@app.get("/bookings/new", response_class=HTMLResponse)
def booking_new_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user: return redirect_login()
    courts = db.query(Court).filter(Court.status == "Aktif").order_by(Court.name).all()
    return page(request, "booking_form.html", db, courts=courts, today=date.today().isoformat())


@app.post("/bookings/new")
def booking_create(request: Request, court_id: int = Form(...), booking_date: date = Form(...),
                   start_time: time = Form(...), end_time: time = Form(...),
                   db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user: return redirect_login()
    court = db.get(Court, court_id)
    if not court or court.status != "Aktif" or booking_date < date.today():
        return RedirectResponse("/bookings/new?error=invalid", status_code=303)
    if end_time <= start_time or start_time < time(7, 0) or end_time > time(23, 0):
        return RedirectResponse("/bookings/new?error=time", status_code=303)
    duration_seconds = (datetime.combine(date.today(), end_time) -
                        datetime.combine(date.today(), start_time)).total_seconds()
    if duration_seconds % 3600 != 0:
        return RedirectResponse("/bookings/new?error=duration", status_code=303)
    if booking_conflict(db, court_id, booking_date, start_time, end_time):
        return RedirectResponse("/bookings/new?error=conflict", status_code=303)
    hours = int(duration_seconds // 3600)
    booking = Booking(user_id=user.id, court_id=court_id, booking_date=booking_date,
                      start_time=start_time, end_time=end_time,
                      total_price=hours * court.price_per_hour, status="Menunggu")
    db.add(booking)
    db.commit()
    return RedirectResponse("/bookings", status_code=303)


@app.post("/bookings/{booking_id}/status")
def booking_status(booking_id: int, request: Request, status: str = Form(...),
                   db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    booking = db.get(Booking, booking_id)
    if booking and status in ["Dikonfirmasi", "Ditolak", "Dibatalkan"]:
        booking.status = status
        if status in ["Ditolak", "Dibatalkan"] and booking.payment:
            booking.payment.status = "Dikembalikan"
        db.commit()
    return RedirectResponse("/bookings", status_code=303)


# PAYMENT DEMO
@app.get("/bookings/{booking_id}/pay", response_class=HTMLResponse)
def payment_page(booking_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user: return redirect_login()
    booking = db.get(Booking, booking_id)
    if not booking: raise HTTPException(404)
    if user.role != "admin" and booking.user_id != user.id: raise HTTPException(403)
    if booking.status != "Dikonfirmasi": return RedirectResponse("/bookings", status_code=303)
    return page(request, "payment.html", db, booking=booking)


@app.post("/bookings/{booking_id}/pay")
def payment_create(booking_id: int, request: Request, method: str = Form(...),
                   db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user: return redirect_login()
    booking = db.get(Booking, booking_id)
    if not booking: raise HTTPException(404)
    if user.role != "admin" and booking.user_id != user.id: raise HTTPException(403)
    if booking.status != "Dikonfirmasi" or method not in ["Transfer Bank", "QRIS", "Tunai"]:
        raise HTTPException(400, "Pembayaran tidak valid")
    payment = booking.payment or Payment(booking_id=booking.id, amount=booking.total_price)
    payment.amount, payment.method = booking.total_price, method
    payment.status, payment.paid_at = "Lunas", datetime.utcnow()
    db.add(payment)
    db.commit()
    return RedirectResponse("/bookings", status_code=303)


# REPORT
@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, start: Optional[date] = None,
                 end: Optional[date] = None, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user or user.role != "admin": return redirect_login()
    query = db.query(Booking)
    if start: query = query.filter(Booking.booking_date >= start)
    if end: query = query.filter(Booking.booking_date <= end)
    rows = query.order_by(Booking.booking_date.desc()).all()
    paid_total = sum(b.payment.amount for b in rows if b.payment and b.payment.status == "Lunas")
    return page(request, "reports.html", db, rows=rows, paid_total=paid_total,
                start=start.isoformat() if start else "", end=end.isoformat() if end else "")


def seed_data():
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(email="admin@sportbook.com").first():
            db.add(User(name="Administrator", email="admin@sportbook.com",
                        password_hash=pwd_context.hash("admin123"), role="admin"))
        if db.query(Sport).count() == 0:
            db.add_all([
                Sport(name="Badminton", description="Olahraga bulu tangkis"),
                Sport(name="Futsal", description="Sepak bola dalam ruangan"),
                Sport(name="Basket", description="Olahraga bola basket")
            ])
            db.commit()
        if db.query(Court).count() == 0:
            sports = {s.name: s.id for s in db.query(Sport).all()}
            db.add_all([
                Court(name="Badminton A", sport_id=sports["Badminton"], location="Gedung A", price_per_hour=50000),
                Court(name="Badminton B", sport_id=sports["Badminton"], location="Gedung A", price_per_hour=50000),
                Court(name="Futsal 1", sport_id=sports["Futsal"], location="Area Outdoor", price_per_hour=150000),
                Court(name="Basket 1", sport_id=sports["Basket"], location="Gedung B", price_per_hour=100000)
            ])
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    seed_data()
