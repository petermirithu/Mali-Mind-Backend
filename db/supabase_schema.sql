-- ============================================================
-- Mali — Supabase Database Schema
-- Run this in your Supabase SQL Editor to set up all tables.
-- ============================================================


-- ── 1. Fuel Prices ────────────────────────────────────────────────────────────
CREATE TABLE fuel_prices (
    id                  BIGSERIAL PRIMARY KEY,
    petrol_per_litre    NUMERIC(8, 2)   NOT NULL,
    diesel_per_litre    NUMERIC(8, 2)   NOT NULL,
    kerosene_per_litre  NUMERIC(8, 2)   NOT NULL,
    effective_date      TIMESTAMPTZ     NOT NULL,
    source              TEXT            NOT NULL DEFAULT 'EPRA',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Index for quick latest-record queries
CREATE INDEX idx_fuel_created_at ON fuel_prices (created_at DESC);


-- ── 2. Forex Rates ────────────────────────────────────────────────────────────
CREATE TABLE forex_rates (
    id          BIGSERIAL PRIMARY KEY,
    usd_kes     NUMERIC(10, 4)  NOT NULL,
    eur_kes     NUMERIC(10, 4),
    gbp_kes     NUMERIC(10, 4),    
    source      TEXT            NOT NULL DEFAULT 'open_exchange_rates',
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_forex_created_at ON forex_rates (created_at DESC);


-- ── 3. Food Basket ────────────────────────────────────────────────────────────
CREATE TABLE food_basket (
    id          BIGSERIAL PRIMARY KEY,
    maize_flour NUMERIC(8, 2)   NOT NULL,
    wheat_flour NUMERIC(8, 2)   NOT NULL,
    rice        NUMERIC(8, 2)   NOT NULL,
    sugar       NUMERIC(8, 2)   NOT NULL,
    cooking_oil NUMERIC(8, 2)   NOT NULL,
    milk        NUMERIC(8, 2)   NOT NULL,
    eggs        NUMERIC(8, 2)   NOT NULL,
    bread       NUMERIC(8, 2)   NOT NULL,
    tomatoes    NUMERIC(8, 2)   NOT NULL,
    onions      NUMERIC(8, 2)   NOT NULL,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_food_created_at ON food_basket (created_at DESC);


-- ── 4. AI Insights ────────────────────────────────────────────────────────────
CREATE TABLE ai_insights (
    id              BIGSERIAL PRIMARY KEY,
    trigger         TEXT            NOT NULL,   -- e.g. 'fuel_update', 'forex_update'
    summary         TEXT            NOT NULL,   -- 2-sentence household impact
    impact_score    NUMERIC(4, 3)   NOT NULL,   -- -1.000 to +1.000
    affected_areas  TEXT            NOT NULL,   -- JSON array stored as text    
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_insights_created_at ON ai_insights (created_at DESC);


-- ── 5. Feed Items (Kenya Pulse) ───────────────────────────────────────────────
CREATE TABLE feed_items (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT        NOT NULL,
    category        TEXT,
    what_happened   TEXT        NOT NULL,
    why_it_happened TEXT        NOT NULL,
    what_it_means   TEXT        NOT NULL,
    source_url      TEXT,    
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_feed_published_at ON feed_items (published_at DESC);
CREATE INDEX idx_feed_created_at ON feed_items (created_at DESC);

-- 6. User Model (for auth, optional)
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    fullname TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    firebase_uid TEXT NOT NULL UNIQUE,
    account_type TEXT NOT NULL DEFAULT "Email",
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_code_hash TEXT,
    verification_expires TIMESTAMPTZ,
    verification_attempts INT DEFAULT 0,
    reset_password_token TEXT,
    reset_password_expires TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()    
)

create index idx_users_email on users (email);
create index idx_users_firebase_uid on users (firebase_uid);
create index idx_users_created_at on users (created_at desc);

-- 7 User Impact Profiles
CREATE TABLE user_impact_profiles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    income NUMERIC(12, 2) NOT NULL,
    rent NUMERIC(12, 2) NOT NULL,
    food_budget NUMERIC(12, 2) NOT NULL,
    transport TEXT NOT NULL,
    commute NUMERIC(12, 2) NOT NULL,
    electricity NUMERIC(12, 2) NOT NULL,
    water NUMERIC(12, 2) NOT NULL,
    savings NUMERIC(12, 2) NOT NULL,
    custom_categories JSONB, -- Optional JSON field for user-defined categories
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id) -- Ensure one profile per user
);

create index idx_impact_profiles_user_id on user_impact_profiles (user_id);
create index idx_impact_profiles_created_at on user_impact_profiles (created_at desc);

-- Monthly Spending Snapshots
CREATE TABLE monthly_spending (
  id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  month DATE NOT NULL,
  total_spending NUMERIC(10, 2) NOT NULL DEFAULT 0,
  transport_spending NUMERIC(10, 2) NOT NULL DEFAULT 0,
  food_spending NUMERIC(10, 2) NOT NULL DEFAULT 0,
  utilities_spending NUMERIC(10, 2) NOT NULL DEFAULT 0,
  other_spending NUMERIC(10, 2) DEFAULT 0,
  change_pct_from_prev NUMERIC(5, 2) DEFAULT 0,  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, month)
);

create index idx_monthly_spending_user_id on monthly_spending (user_id);
create index idx_monthly_spending_created_at on monthly_spending (created_at desc);


CREATE TABLE custom_spending_tracker (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  custom_item_name VARCHAR(255) NOT NULL,
  classified_category VARCHAR(50) NOT NULL,  -- "Transport" | "Food & Groceries" | "Utilities" | "Other"
  monthly_cost NUMERIC(10, 2) NOT NULL,
  affected_by_fuel BOOLEAN DEFAULT false,
  affected_by_forex BOOLEAN DEFAULT false,
  affected_by_food BOOLEAN DEFAULT false,
  estimated_impact_pct NUMERIC(5, 2) DEFAULT 0,
  ai_classification_reasoning TEXT,
  current_month_impact_kes NUMERIC(10, 2),
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_custom_spending_user_id ON custom_spending_tracker(user_id);
CREATE INDEX idx_custom_spending_classified_category ON custom_spending_tracker(classified_category);
CREATE INDEX idx_custom_spending_active ON custom_spending_tracker(is_active);
CREATE INDEX idx_custom_spending_created_at ON custom_spending_tracker(created_at desc);


-- ============================================================
-- Row Level Security (RLS) — enable for production
-- ============================================================

-- Allow public read access to all tables (mobile app reads without auth)
ALTER TABLE fuel_prices   ENABLE ROW LEVEL SECURITY;
ALTER TABLE forex_rates   ENABLE ROW LEVEL SECURITY;
ALTER TABLE food_basket   ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_insights   ENABLE ROW LEVEL SECURITY;
ALTER TABLE feed_items    ENABLE ROW LEVEL SECURITY;
AlTER TABLE users         ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_impact_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE monthly_spending ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_spending_tracker ENABLE ROW LEVEL SECURITY;

-- Public read policies
CREATE POLICY "Public read fuel"    ON fuel_prices   FOR SELECT USING (true);
CREATE POLICY "Public read forex"   ON forex_rates   FOR SELECT USING (true);
CREATE POLICY "Public read food"    ON food_basket   FOR SELECT USING (true);
CREATE POLICY "Public read insight" ON ai_insights   FOR SELECT USING (true);
CREATE POLICY "Public read feed"    ON feed_items    FOR SELECT USING (true);
CREATE POLICY "Public read users"   ON users         FOR SELECT USING (true);
CREATE POLICY "Public read impact profiles" ON user_impact_profiles FOR SELECT USING (true);
CREATE POLICY "Public read monthly spending" ON monthly_spending FOR SELECT USING (true);
CREATE POLICY "Public read custom spending" ON custom_spending_tracker FOR SELECT USING (true);

-- Backend insert policies (allows anon/service role to insert)
CREATE POLICY "Backend insert fuel"    ON fuel_prices   FOR INSERT WITH CHECK (true);
CREATE POLICY "Backend insert forex"   ON forex_rates   FOR INSERT WITH CHECK (true);
CREATE POLICY "Backend insert food"    ON food_basket   FOR INSERT WITH CHECK (true);
CREATE POLICY "Backend insert insight" ON ai_insights   FOR INSERT WITH CHECK (true);
CREATE POLICY "Backend insert feed"    ON feed_items    FOR INSERT WITH CHECK (true);
CREATE POLICY "Backend insert users"   ON users         FOR INSERT WITH CHECK (true);
CREATE POLICY "Backend insert impact profiles" ON user_impact_profiles FOR INSERT WITH CHECK (true);
CREATE POLICY "Backend insert monthly spending" ON monthly_spending FOR INSERT WITH CHECK (true);
CREATE POLICY "Backend insert custom spending" ON custom_spending_tracker FOR INSERT WITH CHECK (true);

-- Backend update policies (allows anon/service role to update)
CREATE POLICY "Backend update users"   ON users         FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Backend update fuel"    ON fuel_prices   FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Backend update forex"   ON forex_rates   FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Backend update food"    ON food_basket   FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Backend update insight" ON ai_insights   FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Backend update feed"    ON feed_items    FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Backend update impact profiles" ON user_impact_profiles FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Backend update monthly spending" ON monthly_spending FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Backend update custom spending" ON custom_spending_tracker FOR UPDATE USING (true) WITH CHECK (true);

--Backend delete policies (allows anon/service role to delete)
CREATE POLICY "Backend delete fuel"    ON fuel_prices   FOR DELETE USING (true);
CREATE POLICY "Backend delete forex"   ON forex_rates   FOR DELETE USING (true);
CREATE POLICY "Backend delete food"    ON food_basket   FOR DELETE USING (true);
CREATE POLICY "Backend delete insight" ON ai_insights   FOR DELETE USING (true);
CREATE POLICY "Backend delete feed"    ON feed_items    FOR DELETE USING (true);
CREATE POLICY "Backend delete users"   ON users         FOR DELETE USING (true);
CREATE POLICY "Backend delete impact profiles" ON user_impact_profiles FOR DELETE USING (true);
CREATE POLICY "Backend delete monthly spending" ON monthly_spending FOR DELETE USING (true);
CREATE POLICY "Backend delete custom spending" ON custom_spending_tracker FOR DELETE USING (true);