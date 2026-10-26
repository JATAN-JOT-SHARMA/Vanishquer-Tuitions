# Vanishquer Tuitions - Official Website

A modern, fully dynamic, and responsive website built for **Vanishquer Tuitions (Vanquisher Academy)**, Solan. This project serves as both a public-facing educational portal and a comprehensive Content Management System (CMS) for the administration.

## 🌟 Key Features

### For Visitors (Frontend)
*   **Homepage:** A professional landing page featuring a Hero section, About Us, Why Choose Us, and dynamic previews of recent blogs and gallery images.
*   **Counselling & Services:** A dedicated page addressing student counselling, slow learners, emotional motivation, and study habits.
*   **Interactive Contact Form:** Includes a custom dropdown for users to select their specific counselling reasons (e.g., "Student feels frustrated", "Family disputes impacts").
*   **Dynamic Blog:** A fully functional blog where visitors can read full articles (SEO-friendly URLs).
*   **Media Gallery:** A responsive grid showcasing images and videos of the tuition center.
*   **User Registration & Login:** Students/parents can create accounts and log in.

### For Admin (Backend Dashboard)
*   **Secure Admin Login:** Protected admin dashboard.
*   **Inline Content Editor:** Easily edit the Homepage hero text, images, About Us content, and Contact details without touching the code.
*   **Services Manager:** Edit the Counselling and Slow Learners page content directly from the dashboard.
*   **Blog Management:** Create, edit, toggle visibility, and delete blog posts. Supports uploading images and videos.
*   **Gallery Management:** Upload and delete images/videos directly to the gallery.
*   **User Inquiries:** View all submitted contact forms, including the specific "Counselling Reason" selected by the user.
*   **CSV Export:** Download all user inquiries as a CSV file with one click.

## 🛠️ Tech Stack
*   **Backend:** Python (Flask)
*   **Database:** PostgreSQL (Neon Serverless Postgres)
*   **ORM:** SQLAlchemy
*   **Storage:** S3-Compatible Object Storage (Neon Storage) for media uploads (supports up to 1GB video files).
*   **Frontend:** HTML5, CSS3, JavaScript (Vanilla), Jinja2 Templating.
*   **Deployment:** Vercel

## 🚀 Local Setup & Installation

Follow these steps to run this project on your local machine:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/your-repo-name.git
   cd your-repo-name