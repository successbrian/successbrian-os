-- Blog idea sorting: Brian's 50K/month filter as deterministic SQL
ALTER TABLE successbrian_os.blog_idea_ranking
  ADD COLUMN IF NOT EXISTS is_blog BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS est_monthly_visits INTEGER,
  ADD COLUMN IF NOT EXISTS competition_level TEXT
    CHECK (competition_level IN ('low','medium','high')),
  ADD COLUMN IF NOT EXISTS monetization_fit NUMERIC(3,2)
    CHECK (monetization_fit BETWEEN 0 AND 1);

-- Flag polluted rows: infra tasks and learning items, not blogs
UPDATE successbrian_os.blog_idea_ranking SET is_blog = FALSE
WHERE status = 'blocked'
   OR name ILIKE 'learning:%'
   OR name ILIKE 'gemini verdict%';

-- The shortlist: Brian's filter. 50K monthly visits minimum, ranked by
-- visits * monetization fit, low competition first.
CREATE OR REPLACE VIEW successbrian_os.blog_idea_shortlist AS
SELECT name, niche, monetization_angle, est_monthly_visits, competition_level,
       monetization_fit, composite_score, rank_position, status
FROM successbrian_os.blog_idea_ranking
WHERE is_blog
  AND est_monthly_visits >= 50000
ORDER BY
  CASE competition_level WHEN 'low' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
  (est_monthly_visits * COALESCE(monetization_fit, 0.5)) DESC;
