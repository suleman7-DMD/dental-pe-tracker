-- Applied 2026-04-24 for Launchpad Phase 3 AI integration
-- Run via Supabase SQL editor (https://supabase.com/dashboard → SQL Editor)
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS succession_intent_detected VARCHAR(20);
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS new_grad_friendly_score INTEGER;
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS mentorship_signals TEXT;
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS associate_runway VARCHAR(32);
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS compensation_signals TEXT;
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS red_flags_for_grad TEXT;
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS green_flags_for_grad TEXT;

-- Anti-hallucination verification block (April 2026, commit 59e8403)
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_searches INTEGER;
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_quality VARCHAR(20);
CREATE INDEX IF NOT EXISTS ix_practice_intel_verification_quality ON practice_intel(verification_quality);
ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_urls TEXT;
