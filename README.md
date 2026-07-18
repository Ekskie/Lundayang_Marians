# Lundayang Marians - Digital Research Repository

Lundayang Marians is the official web-based research repository of Santa Maria (Laguna) Academy Inc., envisioned as the cradle of Marian scholarship. It preserves student academic outputs, offering a simple interface and organized categories (HUMSS, ABM, STEM) for easy access and exploration.

This repository is built using:
- **Backend**: Python Flask (designed for Vercel Serverless Functions)
- **Database & Storage**: Supabase (PostgreSQL, Row Level Security, and Storage Bucket)
- **Frontend**: Vanilla HTML5, premium custom CSS (with a dark/light mode academic color scheme), and modern Javascript
- **PDF Security**: Canvas-based PDF viewer utilizing PDF.js to block client-side copying, printing, and saving operations.

---

## 1. Database Setup (Supabase)

Before running the application, you need to configure your Supabase project:

1. **Create Tables**: Go to the **SQL Editor** in your Supabase dashboard, click "New query", paste the contents of [schema.sql](file:///c:/Users/Denn/Desktop/Lundayang_Marians/schema.sql), and click **Run**. This creates:
   - `profiles` table (with Student ID mappings)
   - `research_papers` table (metadata fields)
   - `bookmarks` table (user bookmark records)
   - Row Level Security (RLS) policies for secure access.

2. **Configure Storage**: 
   - Go to the **Storage** section in Supabase.
   - Click "New Bucket" and name it exactly `research_papers`.
   - Make sure **Public bucket** is **unchecked** (keep it private so PDFs cannot be accessed directly).

---

## 2. Local Development

1. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the project root directory and add the following keys:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-supabase-service-role-or-anon-key
   FLASK_SECRET_KEY=a_long_random_string_for_session_encryption
   ```
   *(Note: For admin upload functions to run smoothly, it is recommended to use the Supabase Service Role Key as your `SUPABASE_KEY` to bypass strict RLS inserts from the server).*

3. **Run the App**:
   ```bash
   python api/index.py
   ```
   Open your browser and navigate to `http://127.0.0.1:5000`.

---

## 3. Vercel Deployment

This project is fully structured for serverless deployment on Vercel:

1. **Install Vercel CLI** (if not already installed):
   ```bash
   npm install -g vercel
   ```

2. **Deploy via CLI**:
   Run the following command inside the project directory:
   ```bash
   vercel
   ```
   Follow the prompts to link the project and deploy it.

3. **Configure Environment Variables in Vercel**:
   - Go to your Project Settings on the Vercel Dashboard.
   - Under **Environment Variables**, add:
     - `SUPABASE_URL`
     - `SUPABASE_KEY`
     - `FLASK_SECRET_KEY`
   - Redeploy the project to apply the changes.
