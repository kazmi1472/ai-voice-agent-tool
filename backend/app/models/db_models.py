# Supabase schema SQL for reference
# Run this in Supabase SQL editor

CREATE TABLE agent_configs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text,
  prompt_template text NOT NULL,
  voice_settings jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_name text NOT NULL,
  phone_number text NOT NULL,
  load_number text,
  agent_config_id uuid REFERENCES agent_configs(id) ON DELETE SET NULL,
  retell_call_id text,  -- Store Retell's call_id for mapping
  status text CHECK (status IN ('queued','in_progress','completed','failed','processed')) DEFAULT 'queued',
  started_at timestamptz,
  ended_at timestamptz,
  duration_seconds int,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE call_transcripts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id uuid REFERENCES calls(id) ON DELETE CASCADE,
  segment_text text,
  speaker text,
  timestamp timestamptz,
  confidence float,
  is_final boolean DEFAULT true
);

CREATE TABLE call_summaries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id uuid REFERENCES calls(id) ON DELETE CASCADE,
  summary jsonb,
  summary_version text,
  created_at timestamptz DEFAULT now()
);
