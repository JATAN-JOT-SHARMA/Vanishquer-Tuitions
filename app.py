import os
import csv
import io
import re
from datetime import datetime
from functools import wraps
import uuid
import boto3
from botocore.config import Config
from flask import (
    Flask, request, jsonify, Response,
    session, redirect, url_for, flash, render_template_string,
    send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
@app.route("/google8c6c685808935f55.html")
def google_verify():
    # Search Console verification file. On Vercel it is shipped via
    # vercel.json "includeFiles"; locally it sits at the project root.
    # Try each plausible location instead of assuming one cwd.
    filename = "google8c6c685808935f55.html"
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (os.getcwd(), here, os.path.join(here, "..")):
        if os.path.exists(os.path.join(base, filename)):
            return send_from_directory(base, filename)
    return "Verification file not found", 404


@app.route("/google0bd254d159ad95bf.html")
def google_verify_new():
    # Second Search Console verification file, issued for the
    # vanishqertuitions.vercel.app property. Same pattern as google_verify.
    filename = "google0bd254d159ad95bf.html"
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (os.getcwd(), here, os.path.join(here, "..")):
        if os.path.exists(os.path.join(base, filename)):
            return send_from_directory(base, filename)
    return "Verification file not found", 404


@app.route("/robots.txt")
def robots_txt():
    """Tells search engines what they may crawl + where the sitemap lives."""
    base = request.host_url.rstrip("/") + "/"
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /admin/\n"
        "Sitemap: " + base + "sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    """Dynamic sitemap: static pages + every published blog post."""
    from xml.sax.saxutils import escape as xml_escape

    base = request.host_url.rstrip("/") + "/"
    urls = [("", None), ("about", None), ("counselling", None),
            ("blog", None), ("gallery", None)]
    try:
        posts = Post.query.filter_by(published=True).order_by(
            Post.created_at.desc()).all()
    except Exception:
        posts = []
    for post in posts:
        urls.append(("blog/" + post.slug, post.created_at))

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod in urls:
        parts.append("<url><loc>" + xml_escape(base + path) + "</loc>")
        if lastmod is not None:
            try:
                parts.append("<lastmod>" + lastmod.date().isoformat() + "</lastmod>")
            except Exception:
                pass
        parts.append("</url>")
    parts.append("</urlset>")
    return Response("\n".join(parts), mimetype="application/xml")
    
app.secret_key = os.getenv("SECRET_KEY", "dev-" + os.urandom(8).hex())

db_url = os.getenv("DATABASE_URL", "")
# Wasmer Edge auto-attached Postgres provides DB_HOST/DB_PORT/DB_NAME/
# DB_USERNAME/DB_PASSWORD instead of DATABASE_URL. Build the URL from
# those when DATABASE_URL is not set, so the same code works on both.
if not db_url and os.getenv("DB_HOST"):
    from urllib.parse import quote as _quote
    _user = _quote(os.getenv("DB_USERNAME", ""), safe="")
    _pw = _quote(os.getenv("DB_PASSWORD", ""), safe="")
    _host = os.getenv("DB_HOST", "")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "")
    db_url = f"postgresql://{_user}:{_pw}@{_host}:{_port}/{_name}"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
# Fallback: Flask-SQLAlchemy crashes at import on an empty URL, which
# is exactly what happens on Wasmer if no database is attached yet.
# Use a local SQLite file so the public pages still start; a real
# Postgres URL (DATABASE_URL or Wasmer DB_* vars) overrides this.
if not db_url:
    db_url = "sqlite:////tmp/vanishquer.db"

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 

db = SQLAlchemy(app)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
MIN_MEDIA_BYTES = 500 * 1024 * 1024   
MAX_MEDIA_BYTES = 1024 * 1024 * 1024  

# --- S3 Storage Setup ---
# S3 is only used for media uploads; do not let a missing S3 config
# break the public pages on Wasmer.
try:
    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("AWS_ENDPOINT_URL_S3"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-2"),
        config=Config(signature_version="s3v4")
    )
except Exception:
    s3 = None
BUCKET = os.getenv("NEON_S3_BUCKET", "s3-bucket-1232")

def make_presigned_upload(filename, content_type, folder="uploads"):
    ext = os.path.splitext(filename)[1].lower()
    key = f"{folder}/{uuid.uuid4().hex}{ext}"
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=3600
    )
    public_url = f"{os.getenv('AWS_ENDPOINT_URL_S3')}/{BUCKET}/{key}"
    return {"upload_url": upload_url, "public_url": public_url, "key": key}

def delete_object(key):
    try:
        s3.delete_object(Bucket=BUCKET, Key=key)
    except Exception as e:
        print("Delete failed:", e)

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
    counselling_reason = db.Column(db.String(200))
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
            "contact_email": "hello@vanishquer.com", 
            "contact_phone": "+91 70182 27042",
            "social_whatsapp": "+91 70182 27042",
            "social_facebook": "https://www.facebook.com/share/19YxaSrGGg/",
            "social_instagram": "https://www.instagram.com/vanquishertuition?rpxt=MWs0a3FlN3d5aXlvcA==",
            "social_youtube": "https://youtube.com/@vanquishertuition?si=KOeXrTyJzlXOMPKE",
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
            else:
                if k in ["contact_phone", "social_whatsapp", "social_facebook", "social_instagram", "social_youtube"]:
                    row = SiteContent.query.filter_by(key=k).first()
                    row.value = v
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
    
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>{{ content.get('hero_title', 'Vanishquer Tuitions') }}</title>
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
        .hero { padding: 80px 0; background: #f8fafc; }
        .hero-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 50px; align-items: center; }
        .hero-text h2 { font-size: 3.2rem; color: #0f4c81; line-height: 1.15; margin-bottom: 20px; font-weight: 800; }
        .hero-text p { font-size: 1.15rem; color: #555; margin-bottom: 30px; }
        .hero-btn { display: inline-block; background: #0f4c81; color: #fff; padding: 16px 32px; border-radius: 8px; font-weight: 700; font-size: 1.05rem; box-shadow: 0 10px 20px rgba(15,76,129,0.2); }
        .hero-btn:hover { background: #e6b84a; color: #0f4c81; transform: translateY(-2px); }
        .hero-image img { max-width: 100%; border-radius: 20px; box-shadow: 0 20px 40px rgba(0,0,0,0.15); }
        .about-section { padding: 80px 0; background: #fff; }
        .about-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 50px; align-items: center; }
        .about-text h2 { font-size: 2.2rem; color: #0f4c81; margin-bottom: 20px; font-weight: 800; position: relative; }
        .about-text h2::after { content: ''; display: block; width: 50px; height: 4px; background: #e6b84a; margin-top: 10px; border-radius: 2px; }
        .about-text p { font-size: 1.05rem; color: #555; margin-bottom: 15px; line-height: 1.8; white-space: pre-wrap; }
        .about-image img { width: 100%; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
        .features-section { padding: 80px 0; background: #f8fafc; }
        .features-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 30px; margin-top: 50px; }
        .feature-card { text-align: center; padding: 40px 20px; background: #fff; border-radius: 16px; border: 1px solid #eaeaea; transition: 0.3s; }
        .feature-card:hover { transform: translateY(-10px); box-shadow: 0 15px 30px rgba(0,0,0,0.08); border-color: #e6b84a; }
        .feature-icon { width: 70px; height: 70px; background: #0f4c81; color: #fff; border-radius: 50%; display: flex; justify-content: center; align-items: center; font-size: 2rem; margin: 0 auto 20px; }
        .feature-card h3 { color: #0f4c81; margin-bottom: 12px; font-size: 1.3rem; }
        .feature-card p { color: #666; font-size: 0.95rem; }
        section { padding: 70px 0; }
        .section-title { font-size: 2.2rem; color: #0f4c81; text-align: center; margin-bottom: 40px; font-weight: 800; position: relative; }
        .section-title::after { content: ''; display: block; width: 60px; height: 4px; background: #e6b84a; margin: 10px auto 0; border-radius: 2px; }
        .grid { display: grid; gap: 30px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
        .card { background: #fff; border: 1px solid #eaeaea; border-radius: 12px; overflow: hidden; transition: 0.3s; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        .card:hover { transform: translateY(-5px); box-shadow: 0 15px 30px rgba(0,0,0,0.1); border-color: #0f4c81; }
        .card img, .card video { width: 100%; height: 220px; object-fit: cover; background: #000; }
        .card-body { padding: 24px; }
        .card h3 { font-size: 1.3rem; color: #0f4c81; margin-bottom: 12px; font-weight: 700; line-height: 1.4; }
        .card p { color: #666; font-size: 0.95rem; margin-bottom: 16px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
        .read-more { color: #e6b84a; font-weight: 700; font-size: 0.9rem; text-transform: uppercase; }
        .gallery { display: grid; gap: 20px; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); }
        .gallery-item { border-radius: 12px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.08); }
        .gallery img, .gallery video { width: 100%; height: 200px; object-fit: cover; transition: 0.3s; }
        .gallery-item:hover img, .gallery-item:hover video { transform: scale(1.05); }
        .contact-wrap { background: #f8fafc; padding: 60px 0; }
        .form-card { background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); max-width: 700px; margin: 0 auto; }
        input, textarea, select { width: 100%; padding: 15px; margin-bottom: 20px; border: 1px solid #ccc; border-radius: 8px; font-size: 1rem; font-family: inherit; outline: none; transition: 0.3s; background: #fff; }
        input:focus, textarea:focus, select:focus { border-color: #0f4c81; box-shadow: 0 0 0 3px rgba(15,76,129,0.1); }
        button { width: 100%; padding: 16px; border: none; border-radius: 8px; background: #0f4c81; color: #fff; font-weight: 700; font-size: 1.1rem; cursor: pointer; transition: 0.3s; }
        button:hover { background: #e6b84a; color: #0f4c81; }
        footer { background: #0a2e4d; color: #b0c4de; padding: 60px 0 20px; }
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
          .hero-grid, .features-grid, .about-grid { grid-template-columns: 1fr; text-align: center; }
          .hero-text h2 { font-size: 2.5rem; }
          .nav-links { flex-wrap: wrap; gap: 15px; padding: 15px; }
          .footer-grid { grid-template-columns: 1fr; }
          .about-text h2::after { margin: 10px auto 0; }
        }
      </style>
    </head>
    <body>
      <div class="top-bar">
        Practical, Personalized Classroom Training with Placement Support. <a href="#contact">Book Free Demo Now</a>
      </div>
      <header>
        <div class="container header-content">
          <div class="logo">
            <h1>{{ content.get('hero_title', 'Vanishquer Tuitions') }}</h1>
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
      <div class="hero">
        <div class="container hero-grid">
          <div class="hero-text">
            <h2>{{ content.get('hero_subtitle', 'Shaping Future Minds with Expert Guidance') }}</h2>
            <p>Vanishquer Tuitions is committed to academic excellence. We provide personalized tutoring, exam preparation, and career counseling for students looking to secure a bright future.</p>
            <a href="#contact" class="hero-btn">Book a Free Demo Class</a>
          </div>
          <div class="hero-image">
            <img src="{{ content.get('hero_image', 'https://images.unsplash.com/photo-1522202176988-66273c2fd55f') }}" alt="Students learning">
          </div>
        </div>
      </div>
      <section id="about" class="about-section">
        <div class="container about-grid">
          <div class="about-image">
            <img src="{{ content.get('about_image', 'https://images.unsplash.com/photo-1541339907198-e08756dedf3f') }}" alt="About Vanishquer">
          </div>
          <div class="about-text">
            <h2>About Vanishquer Tuitions</h2>
            <p>{{ content.get('about', 'Welcome to Vanishquer Tuitions.') }}</p>
            <a href="/about" class="hero-btn" style="padding: 12px 24px; font-size: 1rem; margin-top: 10px;">Read Full About Us →</a>
          </div>
        </div>
      </section>
      <section class="features-section">
        <div class="container">
          <h2 class="section-title">Why Choose Us?</h2>
          <div class="features-grid">
            <div class="feature-card">
              <div class="feature-icon">🎓</div>
              <h3>{{ content.get('feature1_title', 'Expert Faculty') }}</h3>
              <p>{{ content.get('feature1_desc', 'Learn from highly qualified teachers.') }}</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon">🎯</div>
              <h3>{{ content.get('feature2_title', 'Personalized Attention') }}</h3>
              <p>{{ content.get('feature2_desc', 'Small batch sizes for individual focus.') }}</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon">🏆</div>
              <h3>{{ content.get('feature3_title', 'Result Oriented') }}</h3>
              <p>{{ content.get('feature3_desc', 'Proven track record of student success.') }}</p>
            </div>
          </div>
        </div>
      </section>
      {% if posts %}
      <section id="blog-preview" style="background: #fff;">
        <div class="container">
          <h2 class="section-title">Latest Blogs & Updates</h2>
          <div class="grid">
            {% for p in posts %}
            <div class="card">
              {% if p.media_type == 'video' %}
                <video src="{{ p.media_url }}" muted playsinline></video>
              {% elif p.media_type == 'image' %}
                <img src="{{ p.media_url }}" alt="{{ p.title }}">
              {% endif %}
              <div class="card-body">
                <h3><a href="/blog/{{ p.slug }}">{{ p.title }}</a></h3>
                <p>{{ p.body }}</p>
                <a href="/blog/{{ p.slug }}" class="read-more">Read Full Article →</a>
              </div>
            </div>
            {% endfor %}
          </div>
          <div style="text-align: center; margin-top: 40px;">
            <a href="/blog" class="hero-btn" style="padding: 12px 24px; font-size: 1rem;">View All Blogs</a>
          </div>
        </div>
      </section>
      {% endif %}
      {% if gallery %}
      <section id="gallery-preview" style="background: #f8fafc;">
        <div class="container">
          <h2 class="section-title">Our Work & Gallery</h2>
          <div class="gallery">
            {% for g in gallery %}
            <div class="gallery-item">
              {% if g.media_type == 'video' %}
                <video src="{{ g.media_url }}" muted controls></video>
              {% else %}
                <img src="{{ g.media_url }}" alt="{{ g.title or 'Gallery Image' }}">
              {% endif %}
            </div>
            {% endfor %}
          </div>
          <div style="text-align: center; margin-top: 40px;">
            <a href="/gallery" class="hero-btn" style="padding: 12px 24px; font-size: 1rem;">View Full Gallery</a>
          </div>
        </div>
      </section>
      {% endif %}
      <div class="contact-wrap" id="contact">
        <div class="container">
          <h2 class="section-title">Send Us a Message</h2>
          <div class="form-card">
            <form id="queryForm">
              <input type="text" name="name" placeholder="Full name *" required>
              <input type="email" name="email" placeholder="Email address *" required>
              <input type="text" name="contact" placeholder="Contact number">
              <input type="text" name="address" placeholder="Your City / Address">
              <select name="counselling_reason">
                <option value="" disabled selected>Select a reason for counselling (Optional)</option>
                <option value="Student does not study">Student does not study</option>
                <option value="Student feels frustrated">Student feels frustrated</option>
                <option value="Behaves badly at home">Behaves badly at home</option>
                <option value="Family disputes impacts">Family disputes impacts</option>
              </select>
              <textarea name="message" placeholder="How can we help you? *" required></textarea>
              <button type="submit" id="submitBtn">Submit Inquiry</button>
              <div id="msg" style="text-align:center; margin-top:15px; font-weight:600;"></div>
            </form>
          </div>
        </div>
      </div>
      <footer>
        <div class="container">
          <div class="footer-grid">
            <div class="footer-logo">
              <h2>{{ content.get('hero_title', 'Vanishquer Tuitions') }}</h2>
              <p>Solan’s trusted center for quality learning and academic development.</p>
              <div class="social-links">
                <a href="{{ content.get('social_facebook', '#') }}" target="_blank" title="Facebook">
                  <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><path d="M9 8h-3v4h3v12h5v-12h3.642l.358-4h-4v-1.667c0-.955.192-1.333 1.115-1.333h2.885v-5h-3.808c-3.596 0-5.192 1.583-5.192 4.615v3.385z"/></svg>
                </a>
                <a href="{{ content.get('social_instagram', '#') }}" target="_blank" title="Instagram">
                  <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zm0 10.162a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>
                </a>
                <a href="{{ content.get('social_youtube', '#') }}" target="_blank" title="YouTube">
                  <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z"/></svg>
                </a>
              </div>
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
      <script>
        const form = document.getElementById('queryForm');
        const btn = document.getElementById('submitBtn');
        const msg = document.getElementById('msg');
        form.addEventListener('submit', async (e) => {
          e.preventDefault();
          btn.disabled = true; btn.textContent = 'Sending...';
          msg.textContent = ''; msg.style.color = '';
          try {
            const res = await fetch('/submit', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(Object.fromEntries(new FormData(form)))
            });
            const data = await res.json();
            if(data.ok) {
                msg.textContent = data.message;
                msg.style.color = '#10b981';
                form.reset();
            } else {
                msg.textContent = data.error;
                msg.style.color = '#ef4444';
            }
          } catch { 
              msg.textContent = 'Network error, please try again.'; 
              msg.style.color = '#ef4444'; 
          }
          finally { 
              btn.disabled = false; 
              btn.textContent = 'Submit Inquiry'; 
          }
        });
      </script>
    </body>
    </html>
    """
    
    # Injecting Services Section onto Homepage
    services_html = f"""
    <section id="services" class="features-section" style="background: #fff; padding-top: 20px;">
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
    html_code = html_code.replace('<!-- WHY CHOOSE US -->', services_html + '\n<!-- WHY CHOOSE US -->')
    
    return render_template_string(html_code, content=content, posts=posts, gallery=gallery)

@app.route("/about")
def about():
    content = {c.key: c.value for c in SiteContent.query.all()}
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <title>About Us - {{ content.get('hero_title') }}</title>
      <style>
        body { font-family: sans-serif; padding: 50px; background: #f8fafc; line-height: 1.8; }
        .box { max-width: 800px; margin: 0 auto; background: #fff; padding: 40px; border-radius: 10px; border-left: 5px solid #e6b84a; white-space: pre-wrap; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
        h1 { color: #0f4c81; margin-bottom: 20px; }
        a { color: #0f4c81; text-decoration: none; font-weight: bold; display: inline-block; margin-bottom: 20px; }
      </style>
    </head>
    <body>
      <div class="box">
        <a href="/">← Back to Home</a>
        <h1>About Vanishquer Tuitions</h1>
        <p>{{ content.get('about', '') }}</p>
      </div>
    </body>
    </html>
    """
    return render_template_string(html_code, content=content)

@app.route("/counselling")
def counselling():
    content = {c.key: c.value for c in SiteContent.query.all()}
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <title>{{ content.get('counselling_title') }} - {{ content.get('hero_title') }}</title>
      <style>
        body { font-family: sans-serif; padding: 50px; background: #f8fafc; line-height: 1.8; }
        .box { max-width: 800px; margin: 0 auto; background: #fff; padding: 40px; border-radius: 10px; border-left: 5px solid #e6b84a; white-space: pre-wrap; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
        h1 { color: #0f4c81; margin-bottom: 20px; }
        a { color: #0f4c81; text-decoration: none; font-weight: bold; display: inline-block; margin-bottom: 20px; }
        .whatsapp-btn { display: inline-block; background: #25D366; color: white; padding: 10px 20px; border-radius: 5px; margin-top: 20px; text-decoration: none; }
      </style>
    </head>
    <body>
      <div class="box">
        <a href="/">← Back to Home</a>
        <h1>{{ content.get('counselling_title') }}</h1>
        <p>{{ content.get('counselling_content', '') }}</p>
        <a href="https://wa.me/{{ content.get('social_whatsapp', '')|replace(' ', '')|replace('+', '') }}" class="whatsapp-btn">Contact on WhatsApp</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(html_code, content=content)

@app.route("/blog")
def blog_list():
    content = {c.key: c.value for c in SiteContent.query.all()}
    posts = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).all()
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <title>Blog - {{ content.get('hero_title') }}</title>
      <style>
        body { font-family: sans-serif; padding: 50px; background: #f8fafc; line-height: 1.8; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; max-width: 1000px; margin: 0 auto; }
        .card { background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-top: 4px solid #0f4c81; }
        h1 { color: #0f4c81; text-align: center; margin-bottom: 30px; }
        a { color: #0f4c81; text-decoration: none; font-weight: bold; display: inline-block; margin-bottom: 20px; }
      </style>
    </head>
    <body>
      <a href="/">← Back to Home</a>
      <h1>Latest Blogs & Updates</h1>
      <div class="grid">
        {% for p in posts %}
        <div class="card">
          <h3>{{ p.title }}</h3>
          <p>{{ p.body[:100] }}...</p>
          <a href="/blog/{{ p.slug }}">Read More →</a>
        </div>
        {% else %}
        <p>No posts available yet.</p>
        {% endfor %}
      </div>
    </body>
    </html>
    """
    return render_template_string(html_code, content=content, posts=posts)

@app.route("/blog/<slug>")
def view_post(slug):
    post = Post.query.filter_by(slug=slug, published=True).first_or_404()
    content = {c.key: c.value for c in SiteContent.query.all()}
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <title>{{ post.title }}</title>
      <style>
        body { font-family: sans-serif; padding: 50px; background: #f8fafc; line-height: 1.8; }
        .box { max-width: 800px; margin: 0 auto; background: #fff; padding: 40px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
        h1 { color: #0f4c81; }
        a { color: #0f4c81; text-decoration: none; font-weight: bold; display: inline-block; margin-bottom: 20px; }
        img, video { max-width: 100%; border-radius: 10px; margin: 20px 0; }
      </style>
    </head>
    <body>
      <div class="box">
        <a href="/blog">← Back to Blogs</a>
        <h1>{{ post.title }}</h1>
        {% if post.media_url %}
          {% if post.media_type == 'video' %}<video src="{{ post.media_url }}" controls></video>
          {% else %}<img src="{{ post.media_url }}">{% endif %}
        {% endif %}
        <p>{{ post.body }}</p>
      </div>
    </body>
    </html>
    """
    return render_template_string(html_code, post=post, content=content)

@app.route("/gallery")
def gallery_page():
    content = {c.key: c.value for c in SiteContent.query.all()}
    gallery = GalleryItem.query.order_by(GalleryItem.created_at.desc()).all()
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <title>Gallery - {{ content.get('hero_title') }}</title>
      <style>
        body { font-family: sans-serif; padding: 50px; background: #f8fafc; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; max-width: 1000px; margin: 0 auto; }
        img, video { width: 100%; height: 200px; object-fit: cover; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        h1 { color: #0f4c81; text-align: center; margin-bottom: 30px; }
        a { color: #0f4c81; text-decoration: none; font-weight: bold; display: inline-block; margin-bottom: 20px; }
      </style>
    </head>
    <body>
      <a href="/">← Back to Home</a>
      <h1>Our Gallery</h1>
      <div class="grid">
        {% for g in gallery %}
          {% if g.media_type == 'video' %}<video src="{{ g.media_url }}" muted controls></video>
          {% else %}<img src="{{ g.media_url }}">{% endif %}
        {% else %}
          <p>No media in gallery yet.</p>
        {% endfor %}
      </div>
    </body>
    </html>
    """
    return render_template_string(html_code, content=content, gallery=gallery)

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
        counselling_reason=(data.get("counselling_reason") or "").strip() or None,
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
            return "Logged in successfully! <a href='/'>Go to Home</a>"
            
        return "Invalid credentials. <a href='/login'>Try again</a>"
        
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <title>Login</title>
      <style>
        body { font-family: sans-serif; padding: 50px; background: #f8fafc; text-align: center; }
        form { max-width: 300px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        input, button { width: 100%; padding: 10px; margin: 10px 0; border-radius: 5px; border: 1px solid #ccc; }
        button { background: #0f4c81; color: white; border: none; cursor: pointer; }
      </style>
    </head>
    <body>
      <form method="POST">
        <h2>Login</h2>
        <input type="text" name="email" placeholder="Email or 'admin'" required>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Login</button>
        <p style="font-size:0.8rem; margin-top:15px;"><a href="/">Back to Home</a></p>
      </form>
    </body>
    </html>
    """
    return render_template_string(html_code)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        contact = request.form.get("contact")
        
        if User.query.filter_by(email=email).first():
            return "Email already exists. <a href='/login'>Log in</a>"
            
        new_user = User(email=email, password=password, contact=contact)
        db.session.add(new_user)
        db.session.commit()
        return "Account created! <a href='/login'>Log in here</a>"
        
    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <title>Register</title>
      <style>
        body { font-family: sans-serif; padding: 50px; background: #f8fafc; text-align: center; }
        form { max-width: 300px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        input, button { width: 100%; padding: 10px; margin: 10px 0; border-radius: 5px; border: 1px solid #ccc; }
        button { background: #0f4c81; color: white; border: none; cursor: pointer; }
      </style>
    </head>
    <body>
      <form method="POST">
        <h2>Student Registration</h2>
        <input type="email" name="email" placeholder="Email" required>
        <input type="text" name="contact" placeholder="Contact Number" required>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Register</button>
        <p style="font-size:0.8rem; margin-top:15px;"><a href="/login">Already have an account? Login</a></p>
      </form>
    </body>
    </html>
    """
    return render_template_string(html_code)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("login"))
    
    content = {c.key: c.value for c in SiteContent.query.all()}
    inquiries = Inquiry.query.order_by(Inquiry.created_at.desc()).all()

    html_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Admin · {{ content.get('hero_title') }}</title>
      <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: system-ui, sans-serif; background:#0a1128; color:#e8eef7; padding: 40px 20px; }
        .container { max-width:1100px; margin:0 auto; }
        h1 { margin-bottom:20px; color: #fff; } h1 span { color:#e6b84a; }
        h2 { color:#e6b84a; margin:32px 0 14px; font-size:1.25rem; }
        .card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:20px; margin-bottom:16px; }
        table { width:100%; border-collapse:collapse; font-size:0.88rem; }
        th, td { text-align:left; padding:10px 12px; border-bottom:1px solid rgba(255,255,255,0.08); vertical-align:top; }
        th { color:#94a3b8; font-weight:500; }
        input, textarea { width:100%; padding:10px 14px; margin:6px 0 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.15); background:rgba(255,255,255,0.05); color:#fff; font-size:0.95rem; outline:none; }
        input:focus, textarea:focus { border-color:#e6b84a; }
        label { font-size:0.85rem; color:#94a3b8; }
        button, .btn { display:inline-block; padding:9px 16px; border:none; border-radius:8px; background:linear-gradient(135deg,#f4d47c,#e6b84a); color:#0a1128; font-weight:700; cursor:pointer; text-decoration:none; font-size:0.88rem; }
        .btn-outline { background:transparent; border:1px solid rgba(255,255,255,0.25); color:#e8eef7; }
        .btn-danger { background:rgba(248,113,113,0.15); color:#f87171; border:1px solid rgba(248,113,113,0.3); }
        .row { display:grid; gap:12px; grid-template-columns:1fr 1fr; }
        .toast { position:fixed; bottom:24px; right:24px; background:#e6b84a; color:#0a1128; padding:12px 20px; border-radius:10px; font-weight:600; display:none; z-index:100; }
      </style>
    </head>
    <body>
      <div class="container">
        <div style="display:flex;justify-content:space-between;align-items:center;">
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
            <div><label>Facebook URL</label><input id="social_facebook" value="{{ content.get('social_facebook','') }}"></div>
            <div><label>Instagram URL</label><input id="social_instagram" value="{{ content.get('social_instagram','') }}"></div>
            <div><label>YouTube URL</label><input id="social_youtube" value="{{ content.get('social_youtube','') }}"></div>
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

        <h2>User Inquiries ({{ inquiries|length }})</h2>
        <div class="card">
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
            social_facebook: social_facebook.value,
            social_instagram: social_instagram.value,
            social_youtube: social_youtube.value,
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
    return render_template_string(html_code, content=content, inquiries=inquiries)

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