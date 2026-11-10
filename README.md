# SportBook - FastAPI + PostgreSQL + Psycopg 3

## 1. Persiapan database PostgreSQL
Pastikan PostgreSQL sudah terpasang dan berjalan. Buat database:

```sql
CREATE DATABASE sportbook;
```

## 2. Instalasi project (Windows / VS Code)
Buka folder project di VS Code, lalu terminal:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Atur koneksi database
Buka `app/main.py`, sesuaikan default `DATABASE_URL`, atau atur environment variable di PowerShell:

```powershell
$env:DATABASE_URL="postgresql+psycopg://postgres:password@localhost:5432/sportbook"
$env:SECRET_KEY="ganti-dengan-secret-acak"
```

Ganti `postgres`, `password`, dan nama database sesuai PostgreSQL di komputer kamu.

## 4. Jalankan aplikasi

```powershell
uvicorn app.main:app --reload
```

Buka:
- Aplikasi: http://127.0.0.1:8000
- Dokumentasi API FastAPI: http://127.0.0.1:8000/docs

Tabel akan dibuat otomatis saat aplikasi pertama kali dijalankan dan data contoh akan dimasukkan.

## Akun admin demo
- Email: `admin@sportbook.com`
- Password: `admin123`

Pelanggan bisa register dari halaman Register.

## Modul
- Login dan register
- Role admin dan customer
- Dashboard
- Master jenis olahraga (tambah dan hapus)
- CRUD lapangan
- Booking dengan validasi bentrok jadwal
- Konfirmasi / penolakan booking
- Pencatatan pembayaran simulasi
- Laporan berdasarkan rentang tanggal

## Catatan
Koneksi memakai SQLAlchemy 2.0 dengan driver Psycopg 3 (`postgresql+psycopg://`), bukan psycopg2.
Pembayaran adalah simulasi. Untuk produksi, tambahkan proteksi CSRF, validasi input lebih lengkap, rate limiting, migrasi Alembic, HTTPS, dan secret key yang aman.
