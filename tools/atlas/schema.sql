-- Atlas: the higher-level planning graph above the PM.
-- Nodes are plans, locations, racks, hardware, gates, decisions, people.
-- Edges are the relationships between them (blocks, enables, requires...).
-- Graphs, not trees: many-to-many, traversable both directions.

CREATE SCHEMA IF NOT EXISTS atlas;

CREATE TABLE IF NOT EXISTS atlas.nodes (
    id SERIAL PRIMARY KEY,
    node_key TEXT UNIQUE NOT NULL,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    details JSONB DEFAULT '{}'::jsonb,
    ref_kind TEXT,
    ref_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_atlas_nodes_type ON atlas.nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_atlas_nodes_status ON atlas.nodes(status);

CREATE TABLE IF NOT EXISTS atlas.edges (
    id SERIAL PRIMARY KEY,
    from_node TEXT NOT NULL REFERENCES atlas.nodes(node_key) ON DELETE CASCADE,
    to_node TEXT NOT NULL REFERENCES atlas.nodes(node_key) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (from_node, to_node, edge_type)
);
CREATE INDEX IF NOT EXISTS idx_atlas_edges_from ON atlas.edges(from_node);
CREATE INDEX IF NOT EXISTS idx_atlas_edges_to ON atlas.edges(to_node);
CREATE INDEX IF NOT EXISTS idx_atlas_edges_type ON atlas.edges(edge_type);
