import os
import csv
import io
import re
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, Response,
    session, redirect, url_for, flash, render_template_string
)
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

from storage import make_presigned_upload, delete_object

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-" + os.urandom(8).hex())

db_url = os.getenv("DATABASE_URL", "")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 

db = SQLAlchemy(app)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

MIN_MEDIA_BYTES = 500 * 1024 * 1024   
MAX_MEDIA_BYTES = 1024 * 1024 * 1024  

# ---------------- MODELS ----------------

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    contact = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Inquiry(db.Model):
    __tablename__ = "inquiries"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    contact = db.Column(db.String(50))
    counselling_reason = db.Column(db.String(200)) # NEW COLUMN ADDED
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SiteContent(db.Model):
    __tablename__ = "site_content"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, default="")

class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False) 
    meta_description = db.Column(db.String(160))                  
    body = db.Column(db.Text, nullable=False)
    media_url = db.Column(db.Text)
    media_key = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    media_size = db.Column(db.BigInteger)
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GalleryItem(db.Model):
    __tablename__ = "gallery"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    media_url = db.Column(db.Text, nullable=False)
    media_key = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    media_size = db.Column(db.BigInteger)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    try:
        db.create_all()
        defaults = {
            "hero_title": "Vanishquer Tuitions",
            "hero_subtitle": "Solan’s trusted center for quality learning and academic development.",
            "about": "Welcome to Vanishquer Tuitions (Vanquisher Academy), Solan’s trusted center for quality learning and academic development.\n\nAt Vanishquer Tuitions, we believe that every student possesses unique potential. Located conveniently in the heart of Solan (Kotla Nala / Dhobighat), our mission is to break down complex concepts, eliminate learning hurdles, and empower students to become confident, self-reliant achievers.\n\n🎯 Our Mission\nOur mission is to make quality education accessible, engaging, and result-oriented. We strive to go beyond traditional rote learning by fostering critical thinking, fundamental clarity, and academic resilience in every student we mentor.",
            "contact_address": "Solan, Himachal Pradesh",
            "contact_email": "samiksha.kaant@gmail.com",
            "contact_phone": "+91 70182 27042",
            
            "social_facebook": "https://www.facebook.com/share/19YxaSrGGg/",
            "social_instagram": "https://www.instagram.com/vanquishertuition?rpxt=MWs0a3FlN3d5aXlvcA==",
            "social_youtube": "https://youtube.com/@vanquishertuition?si=KOeXrTyJzlXOMPKE",
            "social_whatsapp": "+91 70182 27042",
            
            "hero_image": "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
            "about_image": "https://images.unsplash.com/photo-1541339907198-e08756dedf3f?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
            
            "feature1_title": "Expert Faculty",
            "feature1_desc": "Learn from highly qualified and experienced teachers dedicated to your success.",
            "feature2_title": "Personalized Attention",
            "feature2_desc": "Small batch sizes ensuring every student gets the individual focus they deserve.",
            "feature3_title": "Result Oriented",
            "feature3_desc": "Proven track record of helping students achieve top ranks in their exams.",

            "counselling_title": "Counselling & Slow Learners",
            "counselling_content": "When a student does not want to study, feels frustrated with studies & behaves badly at home, our counselling focuses on emotional motivation, family relationships, and study habits."
        }
        for k, v in defaults.items():
            if not SiteContent.query.filter_by(key=k).first():
                db.session.add(SiteContent(key=k, value=v))
        db.session.commit()
    except Exception as e:
        print("DB init skipped:", e)

# ---------------- HELPERS ----------------

def is_admin():
    return session.get("admin") is True

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not is_admin():
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return f(*a, **kw)
    return wrapper

# ---------------- PUBLIC ROUTES ----------------

@app.route("/")
def index():
    content = {c.key: c.value for c in SiteContent.query.all()}
    posts = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).limit(3).all()
    gallery = GalleryItem.query.order_by(GalleryItem.created_at.desc()).limit(4).all()
    
    # Render index.html
    html = render_template("index.html", content=content, posts=posts, gallery=gallery)
    
    # Inject Services Section
    services_html = f"""
    <section id="services" class="features-section" style="background: #fff;">
      <div class="container">
        <h2 class="section-title">{content.get('counselling_title', 'Our Services & Counselling')}</h2>
        <div class="card" style="max-width: 900px; margin: 0 auto; padding: 40px; border-left: 6px solid #e6b84a; box-shadow: 0 10px 30px rgba(0,0,0,0.05);">
          <p style="font-size: 1.15rem; color: #444; white-space: pre-wrap; line-height: 1.8;">
            {content.get('counselling_content', 'Information coming soon.')}
          </p>
          <div style="text-align: center; margin-top: 30px;">
            <a href="/counselling" class="hero-btn" style="padding: 12px 24px; font-size: 1rem;">Read Full Services Page →</a>
          </div>
        </div>
      </div>
    </section>
    """
    html = html.replace('<!-- WHY CHOOSE US -->', services_html + '\n<!-- WHY CHOOSE US -->')
    
    # Inject Counselling Dropdown into the Contact Form
    counselling_dropdown = """
    <select name="counselling_reason" style="width: 100%; padding: 15px; margin-bottom: 20px; border: 1px solid #ccc; border-radius: 8px; font-size: 1rem; font-family: inherit; color: #555; background: #fff;">
        <option value="" disabled selected>Select a reason for counselling (Optional)</option>
        <option value="Student does not study">Student does not study</option>
        <option value="Student feels frustrated">Student feels frustrated</option>
        <option value="Behaves badly at home">Behaves badly at home</option>
        <option value="Family disputes impacts">Family disputes impacts</option>
    </select>
    """
    html = html.replace('<textarea name="message"', counselling_dropdown + '\n<textarea name="message"')
    
    return html

@app.route("/about")
def about():
    content = {c.key: c.value for c in SiteContent.query.all()}
    return render_template("about.html", content=content)

@app.route("/counselling")
def counselling():
    content = {c.key: c.value for c in SiteContent.query.all()}
    
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>{{ content.get('counselling_title', 'Services') }} - Vanishquer Tuitions</title>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap" rel="stylesheet">
      <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: #ffffff; color: #333; line-height: 1.7; }
        a { text-decoration: none; color: inherit; transition: 0.3s; }
        .container { max-width: 1200px; margin: 0 auto; padding: 0 20px; }
        .top-bar { background: #0f4c81; color: #fff; text-align: center; padding: 8px 0; font-size: 0.9rem; font-weight: 500; }
        .top-bar a { color: #f4d47c; font-weight: 700; }
        header { padding: 20px 0; background: #fff; border-bottom: 1px solid #eee; }
        .header-content { display: flex; justify-content: space-between; align-items: center; }
        .logo h1 { font-size: 2rem; font-weight: 800; color: #0f4c81; }
        .header-contact { display: flex; align-items: center; gap: 10px; font-weight: 700; color: #0f4c81; font-size: 1.1rem; }
        .header-contact svg { width: 28px; height: 28px; fill: #25D366; }
        .navbar { background: #0f4c81; position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        .nav-links { display: flex; justify-content: center; gap: 40px; list-style: none; padding: 15px 0; }
        .nav-links a { color: #fff; font-weight: 600; font-size: 0.95rem; text-transform: uppercase; }
        .nav-links a:hover { color: #f4d47c; }
        .page-header { text-align: center; padding: 80px 0 40px; background: #f8fafc; border-bottom: 1px solid #eee; }
        .page-header h2 { font-size: 3rem; color: #0f4c81; font-weight: 800; margin-bottom: 15px; }
        .services-section { padding: 60px 0; min-height: 40vh; }
        .content-box { background: #fff; padding: 50px; border-radius: 16px; border-left: 6px solid #e6b84a; font-size: 1.2rem; color: #333; white-space: pre-wrap; box-shadow: 0 10px 40px rgba(0,0,0,0.08); max-width: 800px; margin: 0 auto; line-height: 1.8; }
        .whatsapp-btn { display: flex; align-items: center; justify-content: center; gap: 10px; background: #25D366; color: white; padding: 16px 32px; border-radius: 50px; font-weight: 700; font-size: 1.1rem; width: fit-content; margin: 40px auto 0 auto; box-shadow: 0 10px 20px rgba(37,211,102,0.3); transition: 0.3s; }
        .whatsapp-btn:hover { transform: translateY(-3px); box-shadow: 0 15px 25px rgba(37,211,102,0.4); }
        .whatsapp-btn svg { width: 24px; height: 24px; fill: white; }
        footer { background: #0a2e4d; color: #b0c4de; padding: 60px 0 20px; margin-top: 60px; }
        .footer-grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 40px; margin-bottom: 40px; }
        .footer-logo h2 { color: #fff; margin-bottom: 20px; }
        .footer-grid h4 { color: #fff; font-size: 1.1rem; margin-bottom: 20px; }
        .footer-grid ul { list-style: none; }
        .footer-grid ul li { margin-bottom: 12px; }
        .footer-grid ul li a:hover { color: #e6b84a; padding-left: 5px; }
        .social-links { display: flex; gap: 15px; margin-top: 20px; }
        .social-links a { display: flex; align-items: center; justify-content: center; width: 40px; height: 40px; background: rgba(255,255,255,0.1); border-radius: 50%; color: #fff; transition: 0.3s; }
        .social-links a:hover { background: #e6b84a; color: #0a2e4d; transform: translateY(-3px); }
        .footer-bottom { text-align: center; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.1); font-size: 0.9rem; }
        .whatsapp-float { position: fixed; left: 20px; bottom: 40px; background: #25D366; width: 60px; height: 60px; border-radius: 50%; display: flex; justify-content: center; align-items: center; box-shadow: 0 4px 15px rgba(37,211,102,0.4); z-index: 1000; transition: 0.3s; }
        .whatsapp-float:hover { transform: scale(1.1); }
        .whatsapp-float svg { width: 35px; height: 35px; fill: #fff; }
        @media (max-width: 768px) {
          .nav-links { flex-wrap: wrap; gap: 15px; padding: 15px; }
          .footer-grid { grid-template-columns: 1fr; }
          .content-box { padding: 30px; }
        }
      </style>
    </head>
    <body>
      <div class="top-bar">
        Practical, Personalized Classroom Training with Placement Support. <a href="/#contact">Book Free Demo Now</a>
      </div>
      <header>
        <div class="container header-content">
          <div class="logo">
            <a href="/"><h1>{{ content.get('hero_title', 'Vanishquer Tuitions') }}</h1></a>
          </div>
          <div class="header-contact">
            <svg viewBox="0 0 32 32"><path d="M16 2a13 13 0 0 0-11 20l-2 6 6-2a13 13 0 0 0 20-11A13 13 0 0 0 16 2zm0 23a11 11 0 0 1-5-1l-3 1 1-3a11 11 0 1 1 7 3zm5-7s-1 1-2 1a8 8 0 0 1-5-3c-1-2-2-3-2-3s-1-1 0-2c1-2 1-2 1-2a1 1 0 0 1 1 0l1 3a1 1 0 0 1 0 1l-1 1s1 2 2 3c1 1 3 2 3 2l1-1a1 1 0 0 1 1 0l2 1z"/></svg>
            <span>{{ content.get('contact_phone', '+91 90000 00000') }}</span>
          </div>
        </div>
      </header>
      <nav class="navbar">
        <div class="container">
          <ul class="nav-links">
            <li><a href="/">Home</a></li>
            <li><a href="/#about">About Us</a></li>
            <li><a href="/counselling">Services</a></li>
            <li><a href="/blog">Blogs & Updates</a></li>
            <li><a href="/gallery">Gallery</a></li>
            <li><a href="/login" style="color: #e6b84a;">Login / Register</a></li>
          </ul>
        </div>
      </nav>
      <div class="page-header">
        <div class="container">
          <h2>{{ content.get('counselling_title', 'Counselling') }}</h2>
        </div>
      </div>
      <div class="services-section">
        <div class="container">
          <div class="content-box">
            {{ content.get('counselling_content', 'Information coming soon.') }}
          </div>
          <a href="https://wa.me/{{ content.get('social_whatsapp', '919000000000')|replace(' ', '')|replace('+', '') }}" class="whatsapp-btn" target="_blank">
            <svg viewBox="0 0 32 32"><path d="M16 2a13 13 0 0 0-11 20l-2 6 6-2a13 13 0 0 0 20-11A13 13 0 0 0 16 2zm0 23a11 11 0 0 1-5-1l-3 1 1-3a11 11 0 1 1 7 3zm5-7s-1 1-2 1a8 8 0 0 1-5-3c-1-2-2-3-2-3s-1-1 0-2c1-2 1-2 1-2a1 1 0 0 1 1 0l1 3a1 1 0 0 1 0 1l-1 1s1 2 2 3c1 1 3 2 3 2l1-1a1 1 0 0 1 1 0l2 1z"/></svg>
            Contact on WhatsApp
          </a>
        </div>
      </div>
      <footer>
        <div class="container">
          <div class="footer-grid">
            <div class="footer-logo">
              <h2>{{ content.get('hero_title', 'Vanishquer Tuitions') }}</h2>
              <p>Solan’s trusted center for quality learning and academic development.</p>
            </div>
            <div class="footer-links">
              <h4>Quick Links</h4>
              <ul>
                <li><a href="/">Home</a></li>
                <li><a href="/#about">About Us</a></li>
                <li><a href="/counselling">Services</a></li>
                <li><a href="/blog">Latest Blogs</a></li>
                <li><a href="/gallery">Gallery</a></li>
                <li><a href="/login">Student/Admin Login</a></li>
              </ul>
            </div>
            <div class="footer-contact">
              <h4>Contact Info</h4>
              <ul>
                <li>📍 {{ content.get('contact_address', 'Solan, Himachal Pradesh') }}</li>
                <li>📞 {{ content.get('contact_phone', '+91 90000 00000') }}</li>
                <li>📧 {{ content.get('contact_email', 'hello@vanishquer.com') }}</li>
              </ul>
            </div>
          </div>
          <div class="footer-bottom">
            © 2026 Vanishquer Tuitions. All rights reserved.
          </div>
        </div>
      </footer>
      <a href="https://wa.me/{{ content.get('social_whatsapp', '919000000000')|replace(' ', '')|replace('+', '') }}" class="whatsapp-float" target="_blank">
        <svg viewBox="0 0 32 32"><path d="M16 2a13 13 0 0 0-11 20l-2 6 6-2a13 13 0 0 0 20-11A13 13 0 0 0 16 2zm0 23a11 11 0 0 1-5-1l-3 1 1-3a11 11 0 1 1 7 3zm5-7s-1 1-2 1a8 8 0 0 1-5-3c-1-2-2-3-2-3s-1-1 0-2c1-2 1-2 1-2a1 1 0 0 1 1 0l1 3a1 1 0 0 1 0 1l-1 1s1 2 2 3c1 1 3 2 3 2l1-1a1 1 0 0 1 1 0l2 1z"/></svg>
      </a>
    </body>
    </html>
    """
    
    return render_template_string(html_code, content=content)

@app.route("/blog")
def blog_list():
    content = {c.key: c.value for c in SiteContent.query.all()}
    posts = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).all()
    return render_template("blog.html", content=content, posts=posts)

@app.route("/blog/<slug>")
def view_post(slug):
    post = Post.query.filter_by(slug=slug, published=True).first_or_404()
    content = {c.key: c.value for c in SiteContent.query.all()}
    return render_template("post.html", post=post, content=content)

@app.route("/gallery")
def gallery_page():
    content = {c.key: c.value for c in SiteContent.query.all()}
    gallery = GalleryItem.query.order_by(GalleryItem.created_at.desc()).all()
    return render_template("gallery.html", content=content, gallery=gallery)

@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json() or request.form
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    message = (data.get("message") or "").strip()
    
    if not (name and email and message):
        return jsonify({"ok": False, "error": "Name, email and message are required."}), 400
    
    db.session.add(Inquiry(
        name=name, email=email,
        address=(data.get("address") or "").strip() or None,
        contact=(data.get("contact") or "").strip() or None,
        counselling_reason=(data.get("counselling_reason") or "").strip() or None, # SAVING NEW FIELD
        message=message,
    ))
    db.session.commit()
    return jsonify({"ok": True, "message": "Thanks! We will contact you soon."})

# ---------------- AUTH ROUTES ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        if email == "admin" and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
            
        user = User.query.filter_by(email=email, password=password).first()
        if user:
            session["user_id"] = user.id
            flash("Logged in successfully!")
            return redirect(url_for("index"))
            
        flash("Invalid credentials. Please try again.")
        return redirect(url_for("login"))
        
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        contact = request.form.get("contact")
        
        if User.query.filter_by(email=email).first():
            flash("Email already exists. Please log in.")
            return redirect(url_for("login"))
            
        new_user = User(email=email, password=password, contact=contact)
        db.session.add(new_user)
        db.session.commit()
        flash("Account created! You can now log in.")
        return redirect(url_for("login"))
        
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("index"))

# ==========================================
# ADMIN DASHBOARD (WITH SERVICES & ADDRESS PANEL)
# ==========================================
@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("login"))
    
    content = {c.key: c.value for c in SiteContent.query.all()}
    posts = Post.query.order_by(Post.created_at.desc()).all()
    inquiries = Inquiry.query.order_by(Inquiry.created_at.desc()).all()
    users = User.query.order_by(User.created_at.desc()).all()

    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Admin · Vanishquer Tuitions</title>
      <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: system-ui, sans-serif; background:#0a1128; color:#e8eef7; line-height:1.6; }
        .container { max-width:1100px; margin:0 auto; padding:40px 24px; }
        h1 { margin-bottom:20px; } h1 span { color:#e6b84a; }
        h2 { color:#e6b84a; margin:32px 0 14px; font-size:1.25rem; }
        .card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:20px; margin-bottom:16px; }
        table { width:100%; border-collapse:collapse; font-size:0.88rem; }
        th, td { text-align:left; padding:10px 12px; border-bottom:1px solid rgba(255,255,255,0.08); vertical-align:top; }
        th { color:#94a3b8; font-weight:500; }
        input, textarea { width:100%; padding:10px 14px; margin:6px 0 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.15); background:rgba(255,255,255,0.05); color:#fff; font-size:0.95rem; outline:none; font-family:inherit; }
        input:focus, textarea:focus { border-color:#e6b84a; }
        label { font-size:0.85rem; color:#94a3b8; }
        button, .btn { display:inline-block; padding:9px 16px; border:none; border-radius:8px; background:linear-gradient(135deg,#f4d47c,#e6b84a); color:#0a1128; font-weight:700; cursor:pointer; text-decoration:none; font-size:0.88rem; }
        .btn-outline { background:transparent; border:1px solid rgba(255,255,255,0.25); color:#e8eef7; }
        .btn-danger { background:rgba(248,113,113,0.15); color:#f87171; border:1px solid rgba(248,113,113,0.3); }
        .row { display:grid; gap:12px; grid-template-columns:1fr 1fr; }
        .toast { position:fixed; bottom:24px; right:24px; background:#e6b84a; color:#0a1128; padding:12px 20px; border-radius:10px; font-weight:600; display:none; z-index:100; }
        .empty { color:#64748b; text-align:center; padding:20px; }
        .thumb { width:70px; height:70px; object-fit:cover; border-radius:8px; }
      </style>
    </head>
    <body>
      <div class="container">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
          <h1>Admin <span>Dashboard</span></h1>
          <div>
            <a href="/" class="btn btn-outline">View Site ↗</a>
            <a href="/logout" class="btn btn-danger">Logout</a>
          </div>
        </div>

        <h2>🏠 Edit Homepage</h2>
        <div class="card">
          <label>Hero Headline</label><input id="hero_subtitle" value="{{ content.get('hero_subtitle','') }}">
          <label>Hero Image URL</label><input id="hero_image" value="{{ content.get('hero_image','') }}">
          <label>About Us Image URL</label><input id="about_image" value="{{ content.get('about_image','') }}">
          <button onclick="saveContent()">💾 Save Homepage</button>
        </div>

        <h2>ℹ️ About Us, Socials & Contact</h2>
        <div class="card">
          <div class="row">
            <div><label>Website Name</label><input id="hero_title" value="{{ content.get('hero_title','') }}"></div>
            <div><label>Contact Phone</label><input id="contact_phone" value="{{ content.get('contact_phone','') }}"></div>
            <div><label>Contact Email</label><input id="contact_email" value="{{ content.get('contact_email','') }}"></div>
            <div><label>Contact Address</label><input id="contact_address" value="{{ content.get('contact_address','') }}"></div>
            <div><label>WhatsApp Number</label><input id="social_whatsapp" value="{{ content.get('social_whatsapp','') }}"></div>
          </div>
          <label>About Us Content</label>
          <textarea id="about" rows="4">{{ content.get('about','') }}</textarea>
          <button onclick="saveContent()">💾 Save Content</button>
        </div>

        <h2>🧠 Services & Counselling</h2>
        <div class="card">
          <label>Page Title</label>
          <input id="counselling_title" value="{{ content.get('counselling_title','') }}">
          <label>Page Content</label>
          <textarea id="counselling_content" rows="4">{{ content.get('counselling_content','') }}</textarea>
          <button onclick="saveContent()">💾 Save Services Content</button>
        </div>

        <h2>📝 Blog Posts ({{ posts|length }})</h2>
        <div class="card">
          {% if posts %}
          <table>
            <thead><tr><th>Title</th><th>Date</th><th>Action</th></tr></thead>
            <tbody>
            {% for p in posts %}
            <tr>
              <td>{{ p.title }}</td>
              <td>{{ p.created_at.strftime('%d %b %y') }}</td>
              <td><a href="/blog/{{ p.slug }}" target="_blank" class="btn btn-outline">View</a></td>
            </tr>
            {% endfor %}
            </tbody>
          </table>
          {% else %}<p class="empty">No posts yet.</p>{% endif %}
        </div>

        <h2>User Inquiries ({{ inquiries|length }})</h2>
        <div class="card">
          {% if inquiries %}
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Counselling Reason</th><th>Message</th></tr></thead>
            <tbody>
            {% for q in inquiries %}
            <tr>
              <td>{{ q.name }}</td>
              <td>{{ q.email }}</td>
              <td style="color: #e6b84a; font-weight: bold;">{{ q.counselling_reason or '—' }}</td>
              <td>{{ q.message[:40] }}...</td>
            </tr>
            {% endfor %}
            </tbody>
          </table>
          {% else %}<p class="empty">No inquiries yet.</p>{% endif %}
        </div>
        <a href="/admin/export" class="btn" style="margin-top:10px;">⬇ Download Inquiries CSV</a>
      </div>

      <div class="toast" id="toast"></div>

      <script>
        function toast(msg, ok=true) {
          const t = document.getElementById('toast');
          t.textContent = msg;
          t.style.background = ok ? '#e6b84a' : '#f87171';
          t.style.color = ok ? '#0a1128' : '#fff';
          t.style.display = 'block';
          setTimeout(() => t.style.display = 'none', 3500);
        }

        async function saveContent() {
          const data = {
            hero_title: hero_title.value,
            hero_subtitle: hero_subtitle.value,
            hero_image: hero_image.value,
            about_image: about_image.value,
            about: about.value,
            contact_email: contact_email.value,
            contact_phone: contact_phone.value,
            contact_address: contact_address.value,
            social_whatsapp: social_whatsapp.value,
            counselling_title: counselling_title.value,
            counselling_content: counselling_content.value
          };
          const r = await fetch('/admin/content', {
            method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)
          });
          toast(r.ok ? '✅ Content updated successfully' : '❌ Failed', r.ok);
        }
      </script>
    </body>
    </html>
    """
    
    return render_template_string(
        html_code, 
        content=content, 
        posts=posts, 
        inquiries=inquiries, 
        users=users
    )

# ---------------- ADMIN ACTIONS ----------------

@app.route("/admin/content", methods=["POST"])
@admin_required
def update_content():
    for key, value in (request.get_json() or {}).items():
        row = SiteContent.query.filter_by(key=key).first()
        if row: row.value = value
        else: db.session.add(SiteContent(key=key, value=value))
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/admin/presign", methods=["POST"])
@admin_required
def presign():
    data = request.get_json() or {}
    filename = data.get("filename", "")
    content_type = data.get("content_type", "")
    
    if not content_type.startswith(("image/", "video/")):
        return jsonify({"ok": False, "error": "Only image/* or video/* allowed"}), 400
    
    try:
        result = make_presigned_upload(filename, content_type)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/admin/posts", methods=["POST"])
@admin_required
def create_post():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title or not body:
        return jsonify({"ok": False, "error": "Title and body required"}), 400

    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    base_slug = slug
    counter = 1
    while Post.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    p = Post(
        title=title, slug=slug, meta_description=data.get("meta_description", ""),
        body=body, media_url=data.get("media_url"), media_key=data.get("media_key"),
        media_type=data.get("media_type"), media_size=int(data.get("media_size") or 0) or None,
        published=True,
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({"ok": True, "id": p.id, "slug": p.slug})

@app.route("/admin/posts/<int:pid>", methods=["DELETE"])
@admin_required
def delete_post(pid):
    p = Post.query.get_or_404(pid)
    if p.media_key: delete_object(p.media_key)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/admin/inquiries/<int:qid>", methods=["DELETE"])
@admin_required
def delete_inquiry(qid):
    q = Inquiry.query.get_or_404(qid)
    db.session.delete(q)
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/admin/export")
@admin_required
def export_csv():
    rows = Inquiry.query.order_by(Inquiry.created_at.desc()).all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ID", "Name", "Email", "Address", "Contact", "Counselling Reason", "Message", "Time"])
    for q in rows:
        w.writerow([q.id, q.name, q.email, q.address or "", q.contact or "", q.counselling_reason or "",
                    q.message, q.created_at.strftime("%Y-%m-%d %H:%M")])
    out.seek(0)
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=inquiries.csv"})

if __name__ == "__main__":
    app.run(debug=True)