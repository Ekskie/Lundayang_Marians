-- SQL Schema for Lundayang Marians Research Repository
-- Run this in your Supabase SQL Editor

-- 1. Create Profiles Table (Linked to auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID REFERENCES auth.users ON DELETE CASCADE PRIMARY KEY,
  student_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  grade_section TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  role TEXT DEFAULT 'student' CHECK (role IN ('student', 'admin')),
  avatar_url TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Create Research Papers Table
CREATE TABLE IF NOT EXISTS public.research_papers (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  title TEXT NOT NULL,
  abstract TEXT NOT NULL,
  strand TEXT NOT NULL CHECK (strand IN ('HUMSS', 'ABM', 'STEM')),
  academic_year TEXT NOT NULL,
  research_type TEXT NOT NULL,
  subject_area TEXT NOT NULL,
  authors TEXT[] NOT NULL,
  adviser TEXT NOT NULL,
  awards TEXT,
  keywords TEXT[] DEFAULT '{}'::TEXT[],
  pdf_path TEXT NOT NULL,
  created_by UUID REFERENCES public.profiles(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Create Bookmarks Table
CREATE TABLE IF NOT EXISTS public.bookmarks (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
  paper_id UUID REFERENCES public.research_papers(id) ON DELETE CASCADE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
  UNIQUE (user_id, paper_id)
);

-- 4. Enable Row Level Security (RLS) on Profiles, Research Papers, and Bookmarks
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookmarks ENABLE ROW LEVEL SECURITY;

-- 5. Policies for Profiles
CREATE POLICY "Public profiles are viewable by everyone" ON public.profiles
  FOR SELECT USING (true);

CREATE POLICY "Users can update their own profile" ON public.profiles
  FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users can insert their own profile" ON public.profiles
  FOR INSERT WITH CHECK (auth.uid() = id);

-- 6. Policies for Research Papers
CREATE POLICY "Research papers are viewable by authenticated users" ON public.research_papers
  FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Only admins can insert research papers" ON public.research_papers
  FOR INSERT WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
    )
  );

CREATE POLICY "Only admins can update research papers" ON public.research_papers
  FOR UPDATE USING (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
    )
  );

CREATE POLICY "Only admins can delete research papers" ON public.research_papers
  FOR DELETE USING (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
    )
  );

-- 7. Policies for Bookmarks
CREATE POLICY "Users can view their own bookmarks" ON public.bookmarks
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own bookmarks" ON public.bookmarks
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own bookmarks" ON public.bookmarks
  FOR DELETE USING (auth.uid() = user_id);

-- ============================================================
-- MIGRATION: If you already have the profiles table, run this:
-- ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;
-- ============================================================

-- ============================================================
-- SEED DATA: Insert mock research papers
-- Run this AFTER creating the tables above.
-- NOTE: created_by is set to NULL since these are seeded, not uploaded by a user.
-- ============================================================

INSERT INTO public.research_papers (title, abstract, strand, academic_year, research_type, subject_area, authors, adviser, awards, keywords, pdf_path)
VALUES
(
  'KALAT MO, SAGOT KO: THE ACCEPTABILITY OF THE PROTOTYPE WASTE SEGREGATOR MACHINE IN SANTA MARIA, LAGUNA',
  'A prototype waste segregator machine designed to automatically classify garbage into biodegradable, non-biodegradable, and recyclable materials using inductive, capacitive, and photoelectric sensors controlled by an Arduino microcontroller. The acceptability testing was conducted within the local barangays of Santa Maria, Laguna to evaluate its efficacy, reliability, and social impact.',
  'STEM',
  '2023-2024',
  'Experimental / Quantitative',
  'Applied Engineering & Electronics',
  ARRAY['Gabrielle A. Dimatatac', 'Bridgette S. Panaligan', 'Mark Andrew Y. Montales', 'Fiona Sheryn A. Hernandez', 'Kristel Anne Nicole L. Jaen', 'Godwel Ivan D. Razon', 'Fatima Victoria I. Valentino'],
  'Ms. Maureen L. Cruz',
  'Best in Research (STEM)',
  ARRAY['waste segregator', 'arduino', 'automation', 'recycling'],
  'seed/waste_segregator.pdf'
),
(
  'PAWSITIVE LIFESTYLE: THE EFFECTS OF PETS ON TEENAGERS'' WELL-BEING AS PERCEIVED BY THEIR BIOLOGICAL SEX',
  'This study examines how pet ownership impacts the mental health and emotional well-being of teenagers, comparative between biological sexes. Utilizing a descriptive research design, data was gathered from junior and senior high school students to analyze gender-based differences in coping strategies and companion animal attachment scales.',
  'HUMSS',
  '2024-2025',
  'Descriptive / Quantitative',
  'Social Psychology & Adolescent Well-being',
  ARRAY['Aiah Arceta', 'Mikha Lim', 'Stacey Sevilleja'],
  'Mr. Jose R. Santos',
  'Best in Research (HUMSS)',
  ARRAY['pets', 'teenagers', 'biological sex', 'mental health'],
  'seed/pawsitive_lifestyle.pdf'
),
(
  'ECO-BRICKS: SOLID WASTE MANAGEMENT STRATEGY IN BARANGAY POBLACION',
  'The research explores the production of eco-bricks from shredded plastics as an alternative building material, validating its load-bearing capacity and cost-effectiveness. The physical structural strength of plastic-stuffed bottles was tested against traditional hollow blocks to assess durability and community safety factors.',
  'STEM',
  '2024-2025',
  'Experimental',
  'Environmental Science',
  ARRAY['Xian Yvan V. Evangelio', 'Carlene Jane P. Dela Cruz'],
  'Mrs. Elena M. Reyes',
  'Outstanding STEM Project',
  ARRAY['eco-bricks', 'plastic waste', 'structural engineering'],
  'seed/eco_bricks.pdf'
),
(
  'FINANCIAL LITERACY AND SPENDING HABITS OF SENIOR HIGH SCHOOL STUDENTS',
  'This descriptive research evaluates the correlation between financial literacy programs and personal budgeting behaviors of SHS students. It outlines key financial stressors, savings triggers, and impulse spending patterns in order to draft financial education curricula recommendations.',
  'ABM',
  '2024-2025',
  'Descriptive Correlational',
  'Financial Management',
  ARRAY['Jean Mary E. De Torres', 'Jhandy Faye B. Consignado'],
  'Mr. Allan B. Perez',
  'Best Business Research',
  ARRAY['financial literacy', 'budgeting', 'spending habits', 'savings'],
  'seed/financial_literacy.pdf'
);
