-- people_intake schema: run once as a role with CREATE on the people and dealsdesk schemas.
-- Requested via knowledge_bridge by people_intake build (2026-10-07).

CREATE TABLE IF NOT EXISTS people.people (
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL,
  first_name TEXT,
  last_name TEXT,
  summary TEXT,
  facts JSONB NOT NULL DEFAULT '[]',
  history JSONB NOT NULL DEFAULT '[]',
  relationship TEXT,
  in_common JSONB NOT NULL DEFAULT '[]',
  open_threads JSONB NOT NULL DEFAULT '[]',
  source TEXT,
  source_ref TEXT,
  rank INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_people_slug ON people.people(slug);

CREATE TABLE IF NOT EXISTS dealsdesk.sightings (
  id SERIAL PRIMARY KEY,
  person_id INTEGER REFERENCES people.people(id),
  item TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'spotted',
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sightings_person ON dealsdesk.sightings(person_id);
CREATE INDEX IF NOT EXISTS idx_sightings_status ON dealsdesk.sightings(status);
