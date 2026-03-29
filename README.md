# HygionX

HygionX is a Flask-based AI medical triage assistant with user authentication, symptom analysis, follow-up questioning, session history, and an admin analytics dashboard.

## Features

- User registration and login with Firebase
- AI-assisted symptom extraction and triage guidance
- Follow-up questioning when symptom data is incomplete
- Session history stored in MySQL
- Health timeline and profile pages
- Admin login using `.env` credentials
- Admin dashboard with analytics cards and multiple charts

## Tech Stack

- Python
- Flask
- Flask-SQLAlchemy
- MySQL
- Firebase Authentication
- SciSpaCy
- Sentence Transformers
- FAISS
- Tailwind CSS

## Project Structure

- `app.py` - main Flask application
- `models.py` - SQLAlchemy models and migrations
- `templates/` - HTML templates
- `static/` - frontend assets
- `Datasets/` - CSV datasets used by the ML pipeline
- `Models/` - trained model artifacts
- `llm/` - LLM helper code
- `requirements.txt` - Python dependencies
- `.env` - local environment configuration

## Prerequisites

Before running the project, make sure you have:

- Python 3.10 or newer
- `pip`
- MySQL installed and running
- A Firebase project for authentication
- A Firebase service account JSON file
- A Google reCAPTCHA setup for your app

## Setup

Follow these steps in order.

### 1. Open the project folder

```powershell
cd "c:\Users\chips\Desktop\Final HygionX - Tested OK"
```

### 2. Create a virtual environment

```powershell
python -m venv venv
```

### 3. Activate the virtual environment

```powershell
venv\Scripts\activate
```

### 4. Install the requirements

```powershell
pip install -r requirements.txt
```

### 5. Configure the environment variables

Create or update `.env` in the project root.

Required values include:

```env
DATABASE_URL=mysql+pymysql://USERNAME:PASSWORD@localhost/hygionx

FIREBASE_API_KEY=your-firebase-api-key
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_STORAGE_BUCKET=your-project.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your-sender-id
FIREBASE_APP_ID=your-app-id
FIREBASE_MEASUREMENT_ID=your-measurement-id
FIREBASE_CREDENTIALS_PATH=firebase-service-account.json

RECAPTCHA_SECRET_KEY=your-recaptcha-secret

ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password

SARVAM_API_KEY=your-sarvam-api-key
SARVAM_API_URL=https://api.sarvam.ai/v1/chat/completions
```

Notes:

- `firebase-service-account.json` is not included in this repository. You must generate and download it from your own Firebase project, then place it in the project root.
- `RECAPTCHA_SECRET_KEY` is also not included in this repository. You must create your own reCAPTCHA configuration in Google reCAPTCHA and add your secret key to `.env`.
- Change the admin password before using this project outside local testing.
- Do not commit `.env` or service account files to GitHub.

### 6. Create the database

Create a MySQL database named `hygionx`, or update `DATABASE_URL` to match your existing database name.

Example:

```sql
CREATE DATABASE hygionx;
```

Tables are created automatically when the Flask app starts.

### 7. Run the application

```powershell
python app.py
```

Important first-run note:

- The first setup may take a while because `pip install -r requirements.txt` includes heavy ML/NLP dependencies.
- The first app startup may also be slower because the system loads NLP and embedding components and may download required model assets from Hugging Face.
- Later runs are usually faster once dependencies and model files are already available locally.

By default, the app runs on:

```text
http://127.0.0.1:5000
```

## How To Access The System

After starting the app, open your browser and use these routes:

### Main user flow

1. Open `http://127.0.0.1:5000/`
2. Click `Login` or `Register`
3. Sign in with Firebase-based user credentials
4. After login, you will be redirected to the chat system

### Admin flow

1. Open `http://127.0.0.1:5000/admin/login`
2. Enter the admin username and password stored in `.env`
3. After login, you will be redirected to the admin dashboard
4. The dashboard shows user counts, session counts, severity trends, emergency trends, and other analytics

## Main Routes

- `/` - landing page
- `/login` - user login
- `/register` - user registration
- `/chat` - main triage chat page
- `/profile` - user profile
- `/timeline` - health timeline
- `/settings` - settings page
- `/admin/login` - admin login
- `/admin/dashboard` - admin analytics dashboard

## API Highlights

- `/api/login` - user login
- `/api/register` - user registration
- `/api/chat` - triage chat API
- `/api/user/profile` - user profile API
- `/api/admin/login` - admin login API
- `/api/admin/analytics` - admin analytics API

## Example Run Order

If someone is running the project for the first time, this is the correct order:

1. Clone or download the project
2. Open the project folder in terminal
3. Create virtual environment
4. Activate virtual environment
5. Run `pip install -r requirements.txt`
6. Configure `.env`
7. Download your own `firebase-service-account.json` from Firebase and place it in the root folder
8. Create your own Google reCAPTCHA key and add the secret key to `.env`
9. Make sure MySQL is running and the database exists
10. Run `python app.py`
11. Wait a little longer on the first run because some dependencies and model assets may need to finish loading or downloading
12. Open the app in the browser
13. Use `/login` for normal users or `/admin/login` for admin access

## Notes About ML Dependencies

This project includes a heavier ML stack for symptom extraction. Packages like `torch`, `spacy`, `scispacy`, and `faiss-cpu` may take time to install.

On the first run, the app may also download model-related files required by the NLP pipeline and Hugging Face-based components, so startup can take longer than usual.

If one of those packages is missing, the app may still start, but the advanced ML-assisted symptom extraction can fall back or become limited.

## Safety Notice

This system is for educational and project purposes. It does not replace licensed medical advice, diagnosis, or emergency care.

In urgent situations, users should contact emergency services or qualified healthcare professionals immediately.

## GitHub Safety

Before pushing to GitHub, make sure you do not upload:

- `.env`
- `firebase-service-account.json`
- any other secret or credential file

## License

This project is intended for educational, demo, and research-oriented use.
